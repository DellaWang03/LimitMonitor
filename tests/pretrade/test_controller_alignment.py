from dataclasses import replace

import pandas as pd
import pandas.testing as pdt
import pytest

from src.pretrade.master_resolution import SnapshotBondMasterResolver
from src.pretrade.service_models import PretradeLine
from src.pretrade.trade_overlay import TradeOverlayBuilder
from src.risk_core.position_context import build_credit_risk_context
from src.risk_core.stage1_aggregates import calculate_single_controller_total_position

from .conftest import make_kernel_input
from .test_master_resolution import CountingProvider, _complete_master, _held_row


def _inputs(adjusted, corrected, raw):
    row = _held_row("900001.IB")
    row.update({
        "实际控制人名称_修正": corrected, "实际控制人名称": raw,
        "内部证券账户名称": "自营部交易性", "库存数量(万)_PR": 10000.0,
    })
    positions = pd.DataFrame([row])
    return make_kernel_input({
        "债券持仓明细表": positions,
        "债券持仓明细表_信用债": positions,
        "债券持仓明细表_全量债券监管集中度": positions,
        "调整实控人名单": pd.DataFrame({
            "主体wind代码": ["10000001"] * len(adjusted),
            "调整后实际控制人": pd.Series(adjusted, dtype=object),
        }),
        "穿透高收益债券": pd.DataFrame(columns=["债券代码", "类型"]),
    })


@pytest.mark.parametrize("held", [True, False])
@pytest.mark.parametrize("adjusted,corrected,raw,expected", [
    (["名单实控人"], "手工修正", "原始值", "名单实控人"),
    ([None], "手工修正", "原始值", "手工修正"),
    ([], "手工修正", None, "手工修正"),
    ([], None, "原始值", "原始值"),
    ([], "0", "原始值", "0"),
    (["名单实控人", "名单实控人"], None, None, "名单实控人"),
])
def test_trial_controller_matches_unchanged_production_priority(
    held, adjusted, corrected, raw, expected
):
    inputs = _inputs(adjusted, corrected, raw)
    before = inputs.detached_frames()
    daily = build_credit_risk_context(before)
    assert daily["实际控制人名称_修正"].tolist() == [expected]
    code = "900001.IB" if held else "900002.IB"
    wind_master = replace(_complete_master(code), issuer_wind_code="10000001.WI",
                          controller_name="不应采用的实时Wind值")
    wind = CountingProvider(wind_master)
    result = SnapshotBondMasterResolver(wind).resolve(inputs, code)
    assert result.master is not None
    assert result.master.controller_name == expected
    assert wind.calls == ([] if held else [code])
    if not held:
        assert result.master == replace(wind_master, controller_name=expected)
    for name, frame in inputs.frames.items():
        pdt.assert_frame_equal(frame, before[name], check_exact=True)


@pytest.mark.parametrize("adjusted", [[], [None], [""], [" "]])
def test_no_snapshot_controller_does_not_fall_back_to_live_wind(adjusted):
    inputs = _inputs(adjusted, None, None)
    wind = CountingProvider(replace(_complete_master("900002.IB"),
                                    issuer_wind_code="10000001.WI"))
    result = SnapshotBondMasterResolver(wind).resolve(inputs, "900002.IB")
    assert result.master is None
    assert "无可用实控人" in result.reason


@pytest.mark.parametrize("conflict_source", ["调整名单", "同主体持仓"])
def test_controller_conflicts_block_trial_without_changing_daily_rules(conflict_source):
    inputs = _inputs(["集团A", "集团B"] if conflict_source == "调整名单" else [],
                     "集团A", None)
    frames = inputs.detached_frames()
    if conflict_source == "同主体持仓":
        second = frames["债券持仓明细表_信用债"].copy()
        second["资产代码"] = "900003.IB"
        second["实际控制人名称_修正"] = "集团B"
        frames["债券持仓明细表_信用债"] = pd.concat(
            [frames["债券持仓明细表_信用债"], second], ignore_index=True
        )
    wind = CountingProvider(replace(_complete_master("900002.IB"),
                                    issuer_wind_code="10000001.WI"))
    result = SnapshotBondMasterResolver(wind).resolve(make_kernel_input(frames), "900002.IB")
    assert result.master is None
    assert "冲突" in result.reason


@pytest.mark.parametrize("held", [True, False])
def test_trial_retains_manual_group_position_and_adds_only_trade_amount(held):
    group = "湖北光谷东国有资本投资运营集团有限公司"
    frames = _inputs([], group, None).detached_frames()
    second = frames["债券持仓明细表_信用债"].copy()
    second["资产代码"] = "900003.IB"
    second["债务主体wind代码"] = "10000002.WI"
    second["实际控制人名称_修正"] = None
    second["库存数量(万)_PR"] = 11800.0
    for name in ("债券持仓明细表", "债券持仓明细表_信用债", "债券持仓明细表_全量债券监管集中度"):
        frames[name] = pd.concat([frames[name], second], ignore_index=True)
    frames["调整实控人名单"] = pd.DataFrame([
        {"主体wind代码": "10000002", "调整后实际控制人": group},
    ])
    inputs = make_kernel_input(frames)
    baseline = build_credit_risk_context(inputs.frames)
    assert calculate_single_controller_total_position(baseline)["单一实控人总持仓_PR"].tolist() == [21800.0]
    code = "900001.IB" if held else "900002.IB"
    wind = CountingProvider(replace(_complete_master(code), issuer_wind_code="10000001.WI",
                                    controller_name=None))
    result = SnapshotBondMasterResolver(wind).resolve(inputs, code)
    assert result.master.controller_name == group
    overlay = TradeOverlayBuilder().build(inputs, [PretradeLine(1, code, "自营部交易性", 100)], {1: result})
    after = build_credit_risk_context(overlay.frames)
    assert calculate_single_controller_total_position(after)["单一实控人总持仓_PR"].tolist() == [21900.0]
    pdt.assert_frame_equal(after.iloc[:len(baseline)].reset_index(drop=True), baseline.reset_index(drop=True))
    for name, frame in inputs.frames.items():
        pdt.assert_frame_equal(frame, frames[name], check_exact=True)
