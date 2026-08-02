from __future__ import annotations

import builtins
import os
from pathlib import Path
import shutil
from types import SimpleNamespace

import pandas as pd
import pytest

sqlalchemy = pytest.importorskip("sqlalchemy")
from sqlalchemy import create_engine

from src.pipeline.daily_runtime import run_daily_runtime
from src.pipeline.paths import PipelinePaths
from src.pretrade.context_build import build_ready_context
from src.pretrade.context_store import PretradeContextStore
from src.pretrade.pretrade_service import PretradeRiskService
from src.pretrade.service_models import BondMaster, MasterResolution, MasterSource, PretradeLine
from src.testing.current_issuer_resolver import stage_current_issuer_resolver
from src.testing.frozen_config import FrozenInputConfig
from src.testing.frozen_manifest import FrozenInputManifest
from src.testing.legacy_local_compat import (
    cleanup_legacy_local_limit_config,
    stage_legacy_local_limit_config,
)
from src.utils.config_loader import ConfigLoader

from scripts.run_pretrade_context import _frozen_issuer_resolver

from .conftest import make_kernel_input


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FROZEN_INPUT_ROOT = (
    Path.home() / "Desktop" / "LimitMonitorAutomation" / "data_source_0123"
)
FROZEN_MANIFEST = (
    PROJECT_ROOT / "config" / "test_manifests" / "data_source_0123-20260710-v1.json"
)
FROZEN_BASELINE_ROOT = (
    Path.home()
    / "Desktop"
    / "LimitMonitorAutomation-test-output"
    / "pretrade-baseline-20260710-main1"
)
_RUN_FROZEN_INTEGRATION = os.environ.get("RUN_FROZEN_PRETRADE_INTEGRATION") == "1"
_FROZEN_FIXTURES_AVAILABLE = FROZEN_INPUT_ROOT.is_dir() and FROZEN_BASELINE_ROOT.is_dir()


def _master(code: str, *, issuer: str = "共同发行人") -> BondMaster:
    return BondMaster(
        input_code=code,
        main_security_code=code.split(".")[0],
        isin_code=f"ISIN-{code}",
        bond_name=f"债券-{code}",
        issuer_name=issuer,
        issuer_wind_code="10000001.WI",
        controller_name="共同实控人",
        guarantor_name=None,
        guarantor_wind_code=None,
        outstanding_balance_yi=100.0,
        bond_classification="信用债",
        bond_type="中期票据",
        issuer_type="国企",
        is_city_investment_bond="否",
        bond_category="国企债",
        wind_industry="公用事业",
        province="河北省",
        asset_name=f"债券-{code}",
        main_security_name=f"债券-{code}",
    )


def _raw_position(master: BondMaster, amount: float = 0.0) -> dict[str, object]:
    return {
        "日期": pd.Timestamp("2026-07-10"),
        "内部证券账户名称": "自营部交易性",
        "资产代码": master.input_code,
        "ISIN码": master.isin_code,
        "资产名称": master.bond_name,
        "债券分类2": master.bond_classification,
        "债券类型1": master.bond_type,
        "主证券代码": master.input_code,
        "主证券名称": master.bond_name,
        "库存数量(万)_PR": amount,
        "债券余额(亿)": master.outstanding_balance_yi,
        "发行人类型": master.issuer_type,
        "债务主体": master.issuer_name,
        "债务主体wind代码": master.issuer_wind_code,
        "实际控制人名称": master.controller_name,
        "实际控制人名称_修正": master.controller_name,
        "担保人": None,
        "担保人wind代码": None,
        "是否城投债": master.is_city_investment_bond,
        "债券类别": master.bond_category,
        "wind行业": master.wind_industry,
        "省份": master.province,
        "合并辅助列": None,
    }


def _service_input():
    held = _master("900001.IB")
    frames = make_kernel_input().detached_frames()
    columns = list(_raw_position(held).keys())
    for name in (
        "债券持仓明细表",
        "债券持仓明细表_信用债",
        "债券持仓明细表_全量债券监管集中度",
    ):
        frames[name] = pd.DataFrame([_raw_position(held)], columns=columns)
    frames["债券持仓表_核算系统"] = pd.DataFrame(
        columns=["日期", "账户", "简称", "代码", "持仓面额(元)", "全价成本(元)"]
    )
    frames["穿透高收益_投资本金规模"] = pd.DataFrame(
        columns=["日期", "账户", "简称", "代码", "持仓面额(元)", "全价成本(元)"]
    )
    return make_kernel_input(frames)


class FakeStore:
    def __init__(self, inputs) -> None:
        self.inputs = inputs

    def get_current_snapshot(self):
        return SimpleNamespace(data_date="2026-07-10", snapshot_id="snapshot")

    def load_kernel_input(self, snapshot_id):
        assert snapshot_id == "snapshot"
        return self.inputs


class FixedProvider:
    def __init__(self, masters: dict[str, BondMaster], missing: set[str] = set()) -> None:
        self.masters = masters
        self.missing = missing
        self.calls: list[str] = []

    def resolve(self, code: str, business_date: pd.Timestamp) -> MasterResolution:
        self.calls.append(code)
        if code in self.missing:
            return MasterResolution(MasterSource.MISSING_MASTER, None, "Wind 无记录")
        return MasterResolution(MasterSource.WIND, self.masters[code], None)


class DateRecordingProvider:
    def __init__(self, master: BondMaster) -> None:
        self.master = master
        self.calls: list[tuple[str, pd.Timestamp]] = []

    def resolve(self, code: str, business_date: pd.Timestamp) -> MasterResolution:
        self.calls.append((code, business_date))
        return MasterResolution(MasterSource.WIND, self.master, None)


class ProjectionKernel:
    """Test-only kernel returning production-shaped fields from its received raw overlay."""

    def run_stage1(self, inputs):
        credit = inputs.frames["债券持仓明细表_信用债"].copy()
        rows = []
        issuer_totals = credit.groupby("债务主体")["库存数量(万)_PR"].sum().to_dict()
        bond_totals = credit.groupby("资产代码")["库存数量(万)_PR"].sum().to_dict()
        for _, raw in credit.iterrows():
            code = raw["资产代码"]
            bond_used = float(bond_totals[code])
            issuer_used = float(issuer_totals[raw["债务主体"]])
            rows.append(
                {
                    "日期": raw["日期"],
                    "业务分类": "做市业务" if raw["内部证券账户名称"] == "做市交易部做市业务" else "自营业务",
                    "资产代码": code,
                    "主证券代码_标准": code,
                    "债务主体": raw["债务主体"],
                    "实际控制人名称_修正": raw["实际控制人名称_修正"],
                    "担保人wind代码": raw["担保人wind代码"],
                    "单一债券总持仓_PR": bond_used,
                    "单一债券规模限额指标值": 100.0,
                    "单一债券规模剩余额度(万)": 100.0 - bond_used,
                    "单一债券是否超限": "是" if bond_used > 100.0 else "否",
                    "单一债券集中度限额指标值": 0.16,
                    "单一债券集中度剩余额度(万)": 100.0 - bond_used,
                    "单一债券集中度是否超限": (
                        "是" if bond_used > 100.0 else "否"
                    ),
                    "单一主体总持仓_PR": issuer_used,
                    "单一主体规模限额指标值": 100.0,
                    "单一主体规模剩余额度(万)": 100.0 - issuer_used,
                    "单一主体是否超限": "是" if issuer_used > 100.0 else "否",
                    "单一实控人总持仓_PR": None,
                    "单一实控人规模限额指标值": None,
                    "单一实控人规模剩余额度(万)": None,
                    "单一实控人是否超限": "否",
                    "单一担保人总持仓_PR": None,
                    "单一担保公司规模限额": None,
                    "单一担保公司规模剩余额度(万)": None,
                    "单一担保人是否超限": "否",
                }
            )
        return {"限额明细_债券持仓明细表_信用债1_2": pd.DataFrame(rows)}

    def run_stage2(self, inputs, stage1):
        codes = set(inputs.frames["债券持仓明细表_信用债"]["资产代码"])
        if "900088.IB" in codes:
            return {
                "限额明细_高收益": pd.DataFrame(
                    [{"资产代码": "900088.IB", "主证券代码_标准": "900088.IB"}]
                )
            }
        return {}


@pytest.fixture
def service():
    provider = FixedProvider(
        {
            "900002.IB": _master("900002.IB"),
            "900088.IB": _master("900088.IB"),
        },
        missing={"900099.IB"},
    )
    instance = PretradeRiskService(
        store=FakeStore(_service_input()), wind_provider=provider, kernel=ProjectionKernel()
    )
    instance._test_provider = provider
    return instance


def test_same_issuer_basket_is_combined_by_kernel_not_page_sum(service) -> None:
    result = service.check_basket(
        [
            PretradeLine(1, "900001.IB", "自营部交易性", 60.0),
            PretradeLine(2, "900002.IB", "自营部交易性", 60.0),
        ]
    )

    assert result.status == "已超限"
    assert any(
        item.name == "单一主体规模" and item.trade_amount_wan == 120.0
        for item in result.dimensions
    )
    issuer = next(item for item in result.dimensions if item.name == "单一主体规模")
    controller = next(
        item for item in result.dimensions if item.name == "单一实控人规模"
    )
    assert issuer.input_line_ids == (1, 2)
    assert controller.input_line_ids == (1, 2)
    assert service._test_provider.calls == ["900002.IB"]


def test_split_merge_and_line_order_do_not_change_basket_decision(service) -> None:
    merged = service.check_basket([PretradeLine(1, "900001.IB", "自营部交易性", 100.0)])
    split = service.check_basket(
        [
            PretradeLine(2, "900001.IB", "自营部交易性", 40.0),
            PretradeLine(1, "900001.IB", "自营部交易性", 60.0),
        ]
    )

    assert merged.status == split.status == "未超限"
    assert min(
        item.raw_remaining_wan
        for item in merged.dimensions
        if item.name == "单一主体规模"
    ) == min(
        item.raw_remaining_wan
        for item in split.dimensions
        if item.name == "单一主体规模"
    )


@pytest.mark.parametrize("amount", [0.0, -1.0, float("nan"), float("inf")])
def test_user_non_positive_or_non_finite_pr_is_invalid(service, amount) -> None:
    with pytest.raises(ValueError, match="有限正数"):
        service.check_basket([PretradeLine(1, "900001.IB", "自营部交易性", amount)])


@pytest.mark.parametrize("full_price", [0.0, -1.0, float("nan"), float("inf")])
def test_provided_full_price_cost_must_be_finite_and_positive(
    service, full_price
) -> None:
    with pytest.raises(ValueError, match="有限正数"):
        service.check_basket(
            [
                PretradeLine(
                    1,
                    "900001.IB",
                    "自营部交易性",
                    10.0,
                    full_price,
                )
            ]
        )


def test_single_quote_matches_direct_zero_probe(service) -> None:
    quote = service.quote_single_bond("900001.IB", "自营部交易性")

    assert quote.snapshot_data_date == "2026-07-10"
    assert quote.raw_pr_remaining_wan == 100.0
    assert quote.purchasable_pr_cap_wan == 100.0


def test_confirmed_breach_wins_over_missing_master(service) -> None:
    result = service.check_basket(
        [
            PretradeLine(1, "900001.IB", "自营部交易性", 101.0),
            PretradeLine(2, "900099.IB", "自营部交易性", 10.0),
        ]
    )

    assert result.status == "已超限"
    assert any(item.calculation_status.value == "MISSING_MASTER" for item in result.dimensions)


def test_nonheld_missing_master_is_not_silently_excluded(service) -> None:
    result = service.check_basket([PretradeLine(1, "900099.IB", "自营部交易性", 10.0)])

    assert result.status == "不可计算"
    assert result.line_reasons == {1: "MISSING_MASTER"}


def test_nonheld_master_resolution_receives_snapshot_business_date() -> None:
    provider = DateRecordingProvider(_master("900002.IB"))
    service = PretradeRiskService(
        store=FakeStore(_service_input()),
        wind_provider=provider,
        kernel=ProjectionKernel(),
    )

    service.check_basket([PretradeLine(1, "900002.IB", "自营部交易性", 10.0)])

    assert provider.calls == [("900002.IB", pd.Timestamp("2026-07-10"))]


def test_high_yield_without_full_price_keeps_pr_and_blocks_annual_cost(service) -> None:
    result = service.check_basket(
        [PretradeLine(1, "900088.IB", "自营部交易性", 10.0, None)]
    )

    assert any(item.measure == "PR_WAN" for item in result.dimensions)
    assert any(
        item.measure == "FULL_PRICE_COST_WAN"
        and item.calculation_status.value == "UNCOMPUTABLE"
        for item in result.dimensions
    )


@pytest.mark.integration
@pytest.mark.skipif(
    not _RUN_FROZEN_INTEGRATION or not _FROZEN_FIXTURES_AVAILABLE,
    reason="set RUN_FROZEN_PRETRADE_INTEGRATION=1 with frozen data_source_0123 fixtures",
)
def test_frozen_held_bond_service_reads_only_persisted_snapshot(
    monkeypatch, tmp_path
) -> None:
    """真实 27 项快照同时验收持仓单券与代表性篮子路径。"""

    manifest = FrozenInputManifest.load(FROZEN_MANIFEST).validate(FROZEN_INPUT_ROOT)
    pipeline_root = tmp_path / "pipeline"
    pipeline_root.mkdir()
    paths = PipelinePaths.create(pipeline_root)
    current_dir = tmp_path / "current"
    current_dir.mkdir()

    resolver = _frozen_issuer_resolver()
    stage_current_issuer_resolver(resolver, paths)
    runtime_stage0_dir = current_dir / "stage0_output"
    runtime_stage0_dir.mkdir()
    shutil.copy2(
        paths.stage0 / "issuer_wind_code_mapping.csv",
        runtime_stage0_dir / "issuer_wind_code_mapping.csv",
    )

    compatibility = stage_legacy_local_limit_config(manifest, PROJECT_ROOT)
    previous_cwd = Path.cwd()
    try:
        config = FrozenInputConfig(
            base=ConfigLoader(config_dir=str(PROJECT_ROOT / "config")),
            manifest=manifest,
            pipeline_root=paths.root,
            access_export_dir=paths.access_export,
        )
        monkeypatch.setenv("ENV", "test")
        monkeypatch.setenv("LIMIT_MONITOR_PROFILE", "local")
        os.chdir(paths.tmp)
        runtime = run_daily_runtime(
            config=config,
            data_dir=manifest.input_root,
            current_dir=current_dir,
            target_date=manifest.expected_business_date.isoformat(),
        )
    finally:
        os.chdir(previous_cwd)
        cleanup_legacy_local_limit_config(compatibility)

    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    store = PretradeContextStore(engine)
    store.prepare_schema()
    snapshot_id = build_ready_context(runtime, store)
    store.publish_current(snapshot_id)

    class NoWindForHeldBond:
        calls: list[str] = []

        def resolve(self, bond_code: str):
            self.calls.append(bond_code)
            raise AssertionError("持仓债不应请求 Wind")

    fake_wind = NoWindForHeldBond()
    service = PretradeRiskService(store=store, wind_provider=fake_wind)

    def _forbidden_read(*args, **kwargs):
        raise AssertionError("service must read snapshot only")

    monkeypatch.setattr(builtins, "open", _forbidden_read)
    monkeypatch.setattr(pd, "read_excel", _forbidden_read)
    monkeypatch.setattr(pd, "read_csv", _forbidden_read)
    monkeypatch.setattr(pd, "read_parquet", _forbidden_read)

    quote = service.quote_single_bond("102480811.IB", "自营部交易性")

    assert quote.snapshot_data_date == "2026-07-10"
    assert quote.dimensions
    assert quote.purchasable_pr_cap_wan is None or quote.purchasable_pr_cap_wan >= 0
    assert [
        (
            item.line_id,
            item.master_source.value if item.master_source is not None else None,
            item.wind_fetched_at,
            item.wind_data_date,
            item.uncomputable_reason,
        )
        for item in quote.line_audits
    ] == [(1, "SNAPSHOT", None, None, None)]

    zero_sentinel = service.check_basket(
        [PretradeLine(1, "102682469.IB", "自营部交易性", 1.0)]
    )
    for name in ("单一实控人规模", "单一担保人规模"):
        dimension = next(item for item in zero_sentinel.dimensions if item.name == name)
        assert (
            dimension.current_used_wan,
            dimension.trade_amount_wan,
            dimension.limit_value,
            dimension.raw_remaining_wan,
            dimension.breached,
            dimension.calculation_status.value,
            dimension.required,
        ) == (None, None, None, None, False, "NOT_APPLICABLE", False)

    merged = service.check_basket(
        [PretradeLine(1, "1980184.IB", "自营部交易性", 100.0)]
    )
    split = service.check_basket(
        [
            PretradeLine(1, "1980184.IB", "自营部交易性", 40.0),
            PretradeLine(2, "1980184.IB", "自营部交易性", 60.0),
        ]
    )
    golden_dimensions = {
        "单一债券规模": (7000.0, 100.0, 25000.0, 17900.0, False, "CALCULATED"),
        "单一主体规模": (10000.0, 100.0, 30000.0, 19900.0, False, "CALCULATED"),
    }
    for name, expected in golden_dimensions.items():
        merged_dimension = next(item for item in merged.dimensions if item.name == name)
        split_dimension = next(item for item in split.dimensions if item.name == name)
        merged_values = (
            merged_dimension.current_used_wan,
            merged_dimension.trade_amount_wan,
            merged_dimension.limit_value,
            merged_dimension.raw_remaining_wan,
            merged_dimension.breached,
            merged_dimension.calculation_status.value,
        )
        split_values = (
            split_dimension.current_used_wan,
            split_dimension.trade_amount_wan,
            split_dimension.limit_value,
            split_dimension.raw_remaining_wan,
            split_dimension.breached,
            split_dimension.calculation_status.value,
        )
        assert merged_values == expected
        assert split_values == expected
    assert [
        (
            item.line_id,
            item.master_source.value if item.master_source is not None else None,
            item.wind_fetched_at,
            item.wind_data_date,
            item.uncomputable_reason,
        )
        for item in split.line_audits
    ] == [
        (1, "SNAPSHOT", None, None, None),
        (2, "SNAPSHOT", None, None, None),
    ]

    same_issuer = service.check_basket(
        [
            PretradeLine(1, "1980082.IB", "自营部交易性", 60.0),
            PretradeLine(2, "1980184.IB", "自营部交易性", 60.0),
        ]
    )
    issuer_dimension = next(
        item for item in same_issuer.dimensions if item.name == "单一主体规模"
    )
    assert (
        issuer_dimension.current_used_wan,
        issuer_dimension.trade_amount_wan,
        issuer_dimension.limit_value,
        issuer_dimension.raw_remaining_wan,
        issuer_dimension.breached,
        issuer_dimension.calculation_status.value,
    ) == (10000.0, 120.0, 30000.0, 19880.0, False, "CALCULATED")

    missing_cost = service.check_basket(
        [PretradeLine(1, "281735.SH", "自营部可供（高收益）-张欣", 1.0)]
    )
    missing_annual = next(
        item
        for item in missing_cost.dimensions
        if item.measure == "FULL_PRICE_COST_WAN"
        and item.calculation_status.value == "UNCOMPUTABLE"
    )
    assert (
        missing_annual.current_used_wan,
        missing_annual.trade_amount_wan,
        missing_annual.limit_value,
        missing_annual.raw_remaining_wan,
        missing_annual.breached,
        missing_annual.calculation_status.value,
        missing_annual.required,
        missing_annual.reason,
    ) == (
        None,
        None,
        None,
        None,
        False,
        "UNCOMPUTABLE",
        True,
        "高收益债券缺少拟买全价成本",
    )
    positive_cost = service.check_basket(
        [PretradeLine(1, "281735.SH", "自营部可供（高收益）-张欣", 1.0, 1.01)]
    )
    positive_annual = next(
        item
        for item in positive_cost.dimensions
        if item.measure == "FULL_PRICE_COST_WAN"
        and item.calculation_status.value == "CALCULATED"
    )
    assert (
        positive_annual.current_used_wan,
        positive_annual.trade_amount_wan,
        positive_annual.limit_value,
        positive_annual.raw_remaining_wan,
        positive_annual.breached,
        positive_annual.calculation_status.value,
        positive_annual.required,
    ) == (
        32552.904125999998,
        1.0100000000020373,
        100000.0,
        67446.085874,
        False,
        "CALCULATED",
        True,
    )

    assert fake_wind.calls == []
    engine.dispose()
