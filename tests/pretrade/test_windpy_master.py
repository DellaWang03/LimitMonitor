from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import pytest

from src.pretrade.service_models import MasterSource
from src.pretrade.windpy_master import WindFieldMap, WindPyBondMasterProvider


FIELD_MAP = WindFieldMap(
    main_security_code="SECURITY_CODE",
    isin_code="ISIN",
    bond_name="SEC_NAME",
    issuer_name="ISSUER",
    issuer_wind_code="ISSUER_CODE",
    controller_name="CONTROLLER",
    guarantor_name="GUARANTOR",
    guarantor_wind_code="GUARANTOR_CODE",
    outstanding_balance_yi="OUTSTANDING",
    bond_classification="BOND_CLASS",
    bond_type="BOND_TYPE",
    issuer_type="ISSUER_TYPE",
    is_city_investment_bond="CITY_INVESTMENT",
    bond_category="BOND_CATEGORY",
    wind_industry="WIND_INDUSTRY",
    province="PROVINCE",
    wind_data_date="TRADE_DATE",
)


COMPLETE_WIND_ROW = {
    "SECURITY_CODE": "102480811.IB",
    "ISIN": "CND1000TEST1",
    "SEC_NAME": "24测试MTN001",
    "ISSUER": "测试发行人",
    "ISSUER_CODE": "10000001.WI",
    "CONTROLLER": "测试实控人",
    "GUARANTOR": None,
    "GUARANTOR_CODE": None,
    "OUTSTANDING": 123.45,
    "BOND_CLASS": "信用债",
    "BOND_TYPE": "中期票据",
    "ISSUER_TYPE": "地方国企",
    "CITY_INVESTMENT": "否",
    "BOND_CATEGORY": "产业债",
    "WIND_INDUSTRY": "公用事业",
    "PROVINCE": "河北省",
    "TRADE_DATE": "2026-07-10",
}


@dataclass
class FakeGateway:
    start_result: object = 0
    wss_result: object | None = None
    calls: list[tuple[str, str, bool]] | None = None

    def __post_init__(self) -> None:
        self.calls = []

    @classmethod
    def single(cls, row: dict[str, object]) -> "FakeGateway":
        return cls(wss_result=(0, pd.DataFrame([row])))

    @classmethod
    def start_failure(cls) -> "FakeGateway":
        return cls(start_result=-1)

    @classmethod
    def error(cls) -> "FakeGateway":
        return cls(wss_result=(-40522017, pd.DataFrame()))

    @classmethod
    def multiple_rows(cls) -> "FakeGateway":
        return cls(wss_result=(0, pd.DataFrame([COMPLETE_WIND_ROW, COMPLETE_WIND_ROW])))

    def start(self):
        return self.start_result

    def wss(self, bond_code: str, fields: str, *, usedf: bool):
        assert self.calls is not None
        self.calls.append((bond_code, fields, usedf))
        return self.wss_result


def test_provider_normalizes_one_complete_wind_record() -> None:
    gateway = FakeGateway.single(COMPLETE_WIND_ROW)
    provider = WindPyBondMasterProvider(gateway=gateway, field_map=FIELD_MAP)

    result = provider.resolve("102480811.IB")

    assert result.source is MasterSource.WIND
    assert result.master is not None
    assert result.master.input_code == "102480811.IB"
    assert result.master.main_security_code == "102480811"
    assert result.master.issuer_name == "测试发行人"
    assert result.wind_fetched_at is not None
    assert result.wind_data_date == "2026-07-10"
    assert gateway.calls == [("102480811.IB", FIELD_MAP.request_fields, True)]


@pytest.mark.parametrize(
    "gateway",
    [FakeGateway.start_failure(), FakeGateway.error(), FakeGateway.multiple_rows()],
)
def test_provider_returns_missing_master_without_fallback(gateway: FakeGateway) -> None:
    result = WindPyBondMasterProvider(gateway=gateway, field_map=FIELD_MAP).resolve(
        "102480811.IB"
    )

    assert result.source is MasterSource.MISSING_MASTER
    assert result.master is None
    assert result.reason


def test_provider_rejects_required_source_field_missing() -> None:
    incomplete = COMPLETE_WIND_ROW.copy()
    incomplete["ISSUER"] = None

    result = WindPyBondMasterProvider(
        gateway=FakeGateway.single(incomplete), field_map=FIELD_MAP
    ).resolve("102480811.IB")

    assert result.source is MasterSource.MISSING_MASTER
    assert result.master is None
    assert "issuer_name" in (result.reason or "")


def test_provider_does_not_issue_guessed_request_without_verified_field_map() -> None:
    gateway = FakeGateway.single(COMPLETE_WIND_ROW)

    result = WindPyBondMasterProvider(gateway=gateway).resolve("102480811.IB")

    assert result.source is MasterSource.MISSING_MASTER
    assert result.master is None
    assert result.reason == "Wind 字段映射尚未通过连通性验收"
    assert gateway.calls == []
