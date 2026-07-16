from __future__ import annotations

import pandas as pd

from src.pretrade.master_resolution import SnapshotBondMasterResolver
from src.pretrade.service_models import BondMaster, MasterResolution, MasterSource

from .conftest import make_kernel_input


def _held_row(code: str, *, issuer: object = "测试发行人") -> dict[str, object]:
    return {
        "日期": pd.Timestamp("2026-07-10"),
        "资产代码": code,
        "ISIN码": "CND1000TEST1",
        "资产名称": "测试债券",
        "债券分类2": "信用债",
        "债券类型1": "中期票据",
        "主证券代码": code,
        "主证券名称": "测试债券",
        "债券余额(亿)": 100.0,
        "发行人类型": "地方国企",
        "债务主体": issuer,
        "债务主体wind代码": "10000001.WI",
        "实际控制人名称_修正": "测试实控人",
        "担保人": None,
        "担保人wind代码": None,
        "是否城投债": "否",
        "债券类别": "产业债",
        "wind行业": "公用事业",
        "省份": "河北省",
    }


def _kernel_input() -> object:
    frames = make_kernel_input().detached_frames()
    frames["债券持仓明细表_信用债"] = pd.DataFrame(
        [
            _held_row("102480811.IB"),
            _held_row("900002.IB", issuer=None),
        ]
    )
    return make_kernel_input(frames)


def _complete_master(code: str) -> BondMaster:
    return BondMaster(
        input_code=code,
        main_security_code=code.split(".")[0],
        isin_code="CND1000TEST2",
        bond_name="Wind 测试债券",
        issuer_name="Wind 测试发行人",
        issuer_wind_code="10000002.WI",
        controller_name="Wind 测试实控人",
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


class CountingProvider:
    def __init__(self, master: BondMaster) -> None:
        self.master = master
        self.calls: list[str] = []

    def resolve(self, bond_code: str) -> MasterResolution:
        self.calls.append(bond_code)
        return MasterResolution(MasterSource.WIND, self.master, None)


def test_complete_held_bond_uses_snapshot_without_wind() -> None:
    wind = CountingProvider(_complete_master("900001.IB"))

    result = SnapshotBondMasterResolver(wind).resolve(_kernel_input(), "102480811.ib")

    assert result.source is MasterSource.SNAPSHOT
    assert result.master is not None
    assert result.master.issuer_name == "测试发行人"
    assert result.master.main_security_code == "102480811"
    assert wind.calls == []


def test_incomplete_held_bond_never_falls_back_to_wind() -> None:
    wind = CountingProvider(_complete_master("900001.IB"))

    result = SnapshotBondMasterResolver(wind).resolve(_kernel_input(), "900002.IB")

    assert result.source is MasterSource.MISSING_SNAPSHOT
    assert result.master is None
    assert result.reason
    assert wind.calls == []


def test_confirmed_nonheld_bond_calls_wind_once() -> None:
    wind = CountingProvider(_complete_master("900003.IB"))

    result = SnapshotBondMasterResolver(wind).resolve(_kernel_input(), "900003.IB")

    assert result.source is MasterSource.WIND
    assert result.master is not None
    assert wind.calls == ["900003.IB"]


def test_held_master_keeps_production_corrected_controller_precedence() -> None:
    frames = _kernel_input().detached_frames()
    frames["债券持仓明细表_信用债"].loc[
        0, "实际控制人名称"
    ] = "原始实控人"
    frames["债券持仓明细表_信用债"].loc[
        0, "实际控制人名称_修正"
    ] = "修正后实控人"
    inputs = make_kernel_input(frames)

    result = SnapshotBondMasterResolver(
        CountingProvider(_complete_master("900001.IB"))
    ).resolve(inputs, "102480811.IB")

    assert result.source is MasterSource.SNAPSHOT
    assert result.master is not None
    assert result.master.controller_name == "修正后实控人"
