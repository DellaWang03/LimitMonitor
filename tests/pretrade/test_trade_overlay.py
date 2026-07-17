from __future__ import annotations

from dataclasses import replace

import pandas as pd

from src.pretrade.service_models import BondMaster, MasterResolution, MasterSource, PretradeLine
from src.pretrade.trade_overlay import TradeOverlayBuilder
from src.risk_core.high_yield_capital_sources import (
    append_high_yield_capital_sources,
    select_accounting_high_yield_capital_rows,
)
from src.risk_core.position_context import normalize_credit_position
from src.risk_core.stage1_aggregates import calculate_single_bond_total_position

from .conftest import make_kernel_input


def _master() -> BondMaster:
    return BondMaster(
        input_code="900003.IB",
        main_security_code="900003",
        isin_code="CND1000TEST3",
        bond_name="测试债券",
        issuer_name="测试发行人",
        issuer_wind_code="10000003.WI",
        controller_name="测试实控人",
        guarantor_name=None,
        guarantor_wind_code=None,
        outstanding_balance_yi=100.0,
        bond_classification="信用债",
        bond_type="中期票据",
        issuer_type="地方国企",
        is_city_investment_bond="否",
        bond_category="产业债",
        wind_industry="公用事业",
        province="河北省",
    )


def _overlay_input():
    frames = make_kernel_input().detached_frames()
    raw_columns = [
        "日期", "内部证券账户名称", "资产代码", "资产名称", "债券分类2",
        "债券类型1", "主证券代码", "主证券名称", "库存数量(万)_PR",
        "债券余额(亿)", "发行人类型", "债务主体", "债务主体wind代码",
        "实际控制人名称", "实际控制人名称_修正", "担保人", "担保人wind代码",
        "是否城投债", "债券类别", "wind行业", "省份", "ISIN码", "合并辅助列",
    ]
    frames["债券持仓明细表"] = pd.DataFrame(columns=raw_columns)
    frames["债券持仓明细表_信用债"] = pd.DataFrame(columns=raw_columns)
    frames["债券持仓明细表_全量债券监管集中度"] = pd.DataFrame(columns=raw_columns)
    frames["债券持仓表_核算系统"] = pd.DataFrame(
        columns=["日期", "账户", "简称", "代码", "持仓面额(元)", "全价成本(元)"]
    )
    frames["穿透高收益_投资本金规模"] = pd.DataFrame(
        columns=["日期", "账户", "简称", "代码", "持仓面额(元)", "全价成本(元)"]
    )
    frames["穿透高收益债券"] = pd.DataFrame(
        [{"ISIN代码": "CND1000TEST3", "类型": "高收益"}]
    )
    return make_kernel_input(frames)


def test_overlay_appends_only_raw_position_frames_and_keeps_else_account_mapping() -> None:
    kernel_input = _overlay_input()
    line = PretradeLine(1, "900003.IB", "任意未列账户", 123.45)
    resolution = MasterResolution(MasterSource.WIND, _master(), None)

    overlay = TradeOverlayBuilder().build(kernel_input, [line], {1: resolution})

    for name in (
        "债券持仓明细表",
        "债券持仓明细表_信用债",
        "债券持仓明细表_全量债券监管集中度",
    ):
        assert len(overlay.frames[name]) == len(kernel_input.frames[name]) + 1
    normalized = normalize_credit_position(overlay.frames["债券持仓明细表_信用债"])
    positions = calculate_single_bond_total_position(normalized)
    assert positions["业务分类"].tolist() == ["自营业务"]
    assert len(kernel_input.frames["债券持仓明细表_信用债"]) == 0


def test_overlay_keeps_asset_and_anchor_fields_distinct() -> None:
    master = replace(
        _master(),
        input_code="184072.SH",
        main_security_code="2180399.IB",
        bond_name="不应写入原始行的旧名称",
        asset_name="21台州01",
        main_security_name="21台州债01",
        controller_name="原始实控人",
    )
    overlay = TradeOverlayBuilder().build(
        _overlay_input(),
        [PretradeLine(1, "184072.SH", "自营部交易性", 10.0)],
        {1: MasterResolution(MasterSource.WIND, master, None)},
    )

    row = overlay.frames["债券持仓明细表_信用债"].iloc[-1]
    assert row["资产代码"] == "184072.SH"
    assert row["资产名称"] == "21台州01"
    assert row["主证券代码"] == "2180399.IB"
    assert row["主证券名称"] == "21台州债01"
    assert row["实际控制人名称"] == "原始实控人"
    assert row["实际控制人名称_修正"] == "原始实控人"


def test_full_price_cost_uses_both_existing_high_yield_source_routes() -> None:
    line = PretradeLine(1, "900003.IB", "高收益测试账户", 10.0, 12.34)
    resolution = MasterResolution(MasterSource.WIND, _master(), None)

    overlay = TradeOverlayBuilder().build(_overlay_input(), [line], {1: resolution})
    accounting = select_accounting_high_yield_capital_rows(
        overlay.frames["债券持仓表_核算系统"], overlay.frames["金融工具池设置"]
    )
    penetration = overlay.frames["穿透高收益_投资本金规模"]
    actual = append_high_yield_capital_sources(accounting, penetration)

    assert len(actual) == 2
    assert actual["代码"].tolist() == ["900003", "900003.IB"]
    assert actual["全价成本(元)"].sum() == 246_800.0
