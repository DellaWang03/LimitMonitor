from __future__ import annotations

from dataclasses import replace
from datetime import datetime

import pandas as pd
import pytest

from src.pretrade.result_adapter import (
    CalculationStatus,
    KernelProjectionRun,
    PretradeResultAdapter,
)
from src.pretrade.service_models import BondMaster, MasterResolution, MasterSource, PretradeLine


def _master() -> BondMaster:
    return BondMaster(
        input_code="900001.IB",
        main_security_code="900001",
        isin_code="ISIN-900001",
        bond_name="测试债券",
        issuer_name="测试发行人",
        issuer_wind_code="10000001.WI",
        controller_name="0",
        guarantor_name="0",
        guarantor_wind_code=None,
        outstanding_balance_yi=10.0,
        bond_classification="信用债",
        bond_type="中期票据",
        issuer_type="国企",
        is_city_investment_bond="否",
        bond_category="国企债",
        wind_industry="公用事业",
        province="河北省",
        asset_name="测试债券",
        main_security_name="测试债券",
    )


def _credit_row(*, bond_used: float, bond_remaining: float, issuer_used: float, issuer_remaining: float):
    return {
        "日期": pd.Timestamp("2026-07-10"),
        "业务分类": "自营业务",
        "资产代码": "900001.IB",
        "主证券代码_标准": "900001.IB",
        "债务主体": "测试发行人",
        "实际控制人名称_修正": "0",
        "担保人": "0",
        "担保人wind代码": None,
        "单一债券总持仓_PR": bond_used,
        "单一债券规模限额指标值": 100.0,
        "单一债券规模剩余额度(万)": bond_remaining,
        "单一债券是否超限": "是" if bond_remaining < 0 else "否",
        "单一债券集中度限额指标值": 0.16,
        "单一债券集中度剩余额度(万)": 0.0,
        "单一债券集中度是否超限": "否",
        "单一主体总持仓_PR": issuer_used,
        "单一主体规模限额指标值": 100.0,
        "单一主体规模剩余额度(万)": issuer_remaining,
        "单一主体是否超限": "是" if issuer_remaining < 0 else "否",
        "单一实控人总持仓_PR": None,
        "单一实控人规模限额指标值": None,
        "单一实控人规模剩余额度(万)": None,
        "单一实控人是否超限": "否",
        "单一担保人总持仓_PR": None,
        "单一担保公司规模限额": None,
        "单一担保公司规模剩余额度(万)": None,
        "单一担保人是否超限": "否",
    }


def _run(*, include_annual: bool = False) -> KernelProjectionRun:
    baseline_credit = pd.DataFrame(
        [_credit_row(bond_used=90.0, bond_remaining=10.0, issuer_used=99.0, issuer_remaining=1.0)]
    )
    overlay_credit = pd.DataFrame(
        [_credit_row(bond_used=100.0, bond_remaining=0.0, issuer_used=101.0, issuer_remaining=-1.0)]
    )
    baseline_stage2: dict[str, pd.DataFrame] = {}
    overlay_stage2: dict[str, pd.DataFrame] = {}
    if include_annual:
        annual = pd.DataFrame(
            [
                {
                    "日期": pd.Timestamp("2026-07-10"),
                    "年度限额(万)": 100.0,
                    "高收益年度总投资本金(万)": 50.0,
                    "高收益年度限额剩余额度(万)": 50.0,
                    "高收益年度限额是否超限": "否",
                }
            ]
        )
        baseline_stage2["限额明细_高收益_投资本金规模"] = annual
        overlay_stage2["限额明细_高收益_投资本金规模"] = annual
        overlay_stage2["限额明细_高收益"] = pd.DataFrame(
            [{"资产代码": "900001.IB", "主证券代码_标准": "900001.IB"}]
        )
    return KernelProjectionRun(
        data_date="2026-07-10",
        lines=(PretradeLine(1, "900001.IB", "自营部交易性", 10.0, 12.34),),
        resolutions={1: MasterResolution(MasterSource.SNAPSHOT, _master(), None)},
        baseline_stage1={"限额明细_债券持仓明细表_信用债1_2": baseline_credit},
        baseline_stage2=baseline_stage2,
        overlay_stage1={"限额明细_债券持仓明细表_信用债1_2": overlay_credit},
        overlay_stage2=overlay_stage2,
    )


def test_adapter_uses_raw_remaining_and_does_not_apply_tolerance() -> None:
    result = PretradeResultAdapter().basket_from_kernel(_run())

    assert result.status == "已超限"
    assert result.confirmed_breach_count == 1
    zero_dimension = next(
        item for item in result.dimensions if item.name == "单一债券集中度"
    )
    assert zero_dimension.raw_remaining_wan == 0.0
    assert zero_dimension.breached is False
    assert zero_dimension.calculation_status is CalculationStatus.CALCULATED


def test_adapter_traces_all_rows_after_controller_correction() -> None:
    first_master = replace(_master(), controller_name="原实控人甲")
    second_master = replace(
        _master(),
        input_code="900002.IB",
        main_security_code="900002",
        isin_code="ISIN-900002",
        controller_name="原实控人乙",
    )
    baseline_rows = []
    overlay_rows = []
    for code in ("900001.IB", "900002.IB"):
        baseline = _credit_row(
            bond_used=0.0,
            bond_remaining=100.0,
            issuer_used=0.0,
            issuer_remaining=100.0,
        )
        overlay = _credit_row(
            bond_used=60.0,
            bond_remaining=40.0,
            issuer_used=120.0,
            issuer_remaining=-20.0,
        )
        for row, used, remaining, overlimit in (
            (baseline, 0.0, 100.0, "否"),
            (overlay, 120.0, -20.0, "是"),
        ):
            row["资产代码"] = code
            row["主证券代码_标准"] = code
            row["实际控制人名称_修正"] = "修正后共同实控人"
            row["单一实控人总持仓_PR"] = used
            row["单一实控人规模限额指标值"] = 100.0
            row["单一实控人规模剩余额度(万)"] = remaining
            row["单一实控人是否超限"] = overlimit
        baseline_rows.append(baseline)
        overlay_rows.append(overlay)
    run = KernelProjectionRun(
        data_date="2026-07-10",
        lines=(
            PretradeLine(1, "900001.IB", "自营部交易性", 60.0),
            PretradeLine(2, "900002.IB", "自营部交易性", 60.0),
        ),
        resolutions={
            1: MasterResolution(MasterSource.SNAPSHOT, first_master, None),
            2: MasterResolution(MasterSource.SNAPSHOT, second_master, None),
        },
        baseline_stage1={
            "限额明细_债券持仓明细表_信用债1_2": pd.DataFrame(baseline_rows)
        },
        baseline_stage2={},
        overlay_stage1={
            "限额明细_债券持仓明细表_信用债1_2": pd.DataFrame(overlay_rows)
        },
        overlay_stage2={},
    )

    result = PretradeResultAdapter().basket_from_kernel(run)

    controller = next(
        item for item in result.dimensions if item.name == "单一实控人规模"
    )
    assert controller.trade_amount_wan == 120.0
    assert controller.input_line_ids == (1, 2)


def test_adapter_keeps_full_price_out_of_pr_minimum() -> None:
    quote = PretradeResultAdapter().single_from_probe(_run(include_annual=True))

    assert quote.status == "已超限"
    assert quote.raw_pr_remaining_wan == -1.0
    assert quote.purchasable_pr_cap_wan == 0.0
    assert quote.full_price_cost_remaining_wan == 50.0
    assert all(
        item.measure != "FULL_PRICE_COST_WAN" or item.raw_remaining_wan == 50.0
        for item in quote.dimensions
    )


def test_adapter_surfaces_missing_master_as_uncomputable_not_zero() -> None:
    run = _run()
    missing = KernelProjectionRun(
        data_date=run.data_date,
        lines=(PretradeLine(1, "900099.IB", "自营部交易性", 10.0),),
        resolutions={
            1: MasterResolution(MasterSource.MISSING_MASTER, None, "Wind 无记录")
        },
        baseline_stage1=run.baseline_stage1,
        baseline_stage2=run.baseline_stage2,
        overlay_stage1=run.overlay_stage1,
        overlay_stage2=run.overlay_stage2,
    )

    result = PretradeResultAdapter().basket_from_kernel(missing)

    assert result.status == "不可计算"
    assert result.line_reasons == {1: "MISSING_MASTER"}
    assert result.dimensions[0].calculation_status is CalculationStatus.MISSING_MASTER


def test_high_yield_missing_cost_keeps_master_status_narrow() -> None:
    run = _run(include_annual=True)
    overlay = run.overlay_stage1[
        "限额明细_债券持仓明细表_信用债1_2"
    ].copy()
    overlay.loc[0, "单一主体规模剩余额度(万)"] = 1.0
    overlay.loc[0, "单一主体是否超限"] = "否"
    missing_cost = replace(
        run,
        lines=(replace(run.lines[0], full_price_cost_wan=None),),
        overlay_stage1={
            "限额明细_债券持仓明细表_信用债1_2": overlay
        },
    )

    result = PretradeResultAdapter().basket_from_kernel(missing_cost)

    annual = next(
        item
        for item in result.dimensions
        if item.name == "高收益年度全价成本"
        and item.calculation_status is CalculationStatus.UNCOMPUTABLE
    )
    assert result.status == "不可计算"
    assert annual.reason == "高收益债券缺少拟买全价成本"
    assert result.line_audits[0].master_status == "主数据可用"
    assert result.line_audits[0].uncomputable_reason is None


def test_single_quote_exposes_backend_overall_status() -> None:
    run = _run()
    non_breaching_overlay = run.overlay_stage1[
        "限额明细_债券持仓明细表_信用债1_2"
    ].copy()
    non_breaching_overlay.loc[0, "单一主体规模剩余额度(万)"] = 1.0
    non_breaching_overlay.loc[0, "单一主体是否超限"] = "否"
    non_breaching = replace(
        run,
        overlay_stage1={
            "限额明细_债券持仓明细表_信用债1_2": non_breaching_overlay
        },
    )
    missing_master = replace(
        run,
        lines=(replace(run.lines[0], bond_code="900099.IB"),),
        resolutions={
            1: MasterResolution(
                MasterSource.MISSING_MASTER,
                None,
                "Wind 返回记录缺少省份",
            )
        },
    )

    assert (
        PretradeResultAdapter().single_from_probe(non_breaching).status
        == "未超限"
    )
    assert PretradeResultAdapter().single_from_probe(run).status == "已超限"
    assert (
        PretradeResultAdapter().single_from_probe(missing_master).status
        == "不可计算"
    )


def test_adapter_exposes_existing_master_resolution_audit_for_every_input_line() -> None:
    run = _run()
    fetched_at = datetime(2026, 7, 23, 9, 30)
    lines = (
        run.lines[0],
        replace(run.lines[0], line_id=2),
        replace(run.lines[0], line_id=3),
    )
    audited = replace(
        run,
        lines=lines,
        resolutions={
            1: MasterResolution(MasterSource.SNAPSHOT, _master(), None),
            2: MasterResolution(
                MasterSource.WIND,
                _master(),
                None,
                wind_fetched_at=fetched_at,
                wind_data_date="2026-07-22",
            ),
            3: MasterResolution(
                MasterSource.MISSING_MASTER,
                None,
                "Wind 返回记录缺少省份",
            ),
        },
    )

    basket = PretradeResultAdapter().basket_from_kernel(audited)
    quote = PretradeResultAdapter().single_from_probe(
        replace(
            run,
            resolutions={
                1: MasterResolution(
                    MasterSource.WIND,
                    _master(),
                    None,
                    wind_fetched_at=fetched_at,
                    wind_data_date="2026-07-22",
                )
            },
        )
    )

    assert [
        (
            item.line_id,
            item.master_status,
            item.master_source,
            item.wind_fetched_at,
            item.wind_data_date,
            item.uncomputable_reason,
        )
        for item in basket.line_audits
    ] == [
        (1, "主数据可用", MasterSource.SNAPSHOT, None, None, None),
        (2, "主数据可用", MasterSource.WIND, fetched_at, "2026-07-22", None),
        (
            3,
            "主数据不可用",
            MasterSource.MISSING_MASTER,
            None,
            None,
            "Wind 返回记录缺少省份",
        ),
    ]
    assert quote.line_audits[0].master_status == "主数据可用"
    assert quote.line_audits[0].master_source is MasterSource.WIND
    assert quote.line_audits[0].wind_fetched_at == fetched_at
    assert quote.line_audits[0].wind_data_date == "2026-07-22"
    assert quote.line_audits[0].uncomputable_reason is None


@pytest.mark.parametrize(
    ("column", "dimension_name"),
    [
        ("单一债券规模剩余额度(万)", "单一债券规模"),
        ("单一债券规模限额指标值", "单一债券规模"),
        ("单一债券总持仓_PR", "单一债券规模"),
    ],
)
def test_applicable_dimension_missing_value_is_uncomputable(
    column: str, dimension_name: str
) -> None:
    run = _run()
    overlay = run.overlay_stage1["限额明细_债券持仓明细表_信用债1_2"].copy()
    overlay.loc[0, "单一主体规模剩余额度(万)"] = 1.0
    overlay.loc[0, "单一主体是否超限"] = "否"
    overlay.loc[0, column] = None
    broken = replace(
        run,
        overlay_stage1={"限额明细_债券持仓明细表_信用债1_2": overlay},
    )

    basket = PretradeResultAdapter().basket_from_kernel(broken)
    quote = PretradeResultAdapter().single_from_probe(broken)

    dimension = next(item for item in basket.dimensions if item.name == dimension_name)
    assert dimension.calculation_status is CalculationStatus.UNCOMPUTABLE
    assert dimension.required is True
    assert basket.status == "不可计算"
    assert quote.purchasable_pr_cap_wan is None


@pytest.mark.parametrize("missing_kind", ["table", "row"])
def test_applicable_dimension_missing_output_is_uncomputable(
    missing_kind: str,
) -> None:
    run = _run()
    overlay_stage1 = (
        {}
        if missing_kind == "table"
        else {
            "限额明细_债券持仓明细表_信用债1_2": pd.DataFrame(
                columns=run.overlay_stage1[
                    "限额明细_债券持仓明细表_信用债1_2"
                ].columns
            )
        }
    )
    broken = replace(run, overlay_stage1=overlay_stage1)

    basket = PretradeResultAdapter().basket_from_kernel(broken)
    quote = PretradeResultAdapter().single_from_probe(broken)

    bond_dimension = next(
        item for item in basket.dimensions if item.name == "单一债券规模"
    )
    assert bond_dimension.calculation_status is CalculationStatus.UNCOMPUTABLE
    assert basket.status == "不可计算"
    assert quote.purchasable_pr_cap_wan is None


def test_production_zero_sentinels_do_not_make_controller_or_guarantor_uncomputable() -> None:
    run = _run()
    overlay = run.overlay_stage1["限额明细_债券持仓明细表_信用债1_2"].copy()
    overlay.loc[0, "单一主体规模剩余额度(万)"] = 1.0
    overlay.loc[0, "单一主体是否超限"] = "否"
    run = replace(
        run,
        overlay_stage1={
            **run.overlay_stage1,
            "限额明细_债券持仓明细表_信用债1_2": overlay,
        },
    )

    result = PretradeResultAdapter().basket_from_kernel(run)

    controller = next(
        item for item in result.dimensions if item.name == "单一实控人规模"
    )
    guarantor = next(
        item for item in result.dimensions if item.name == "单一担保人规模"
    )
    assert controller.calculation_status is CalculationStatus.NOT_APPLICABLE
    assert controller.required is False
    assert guarantor.calculation_status is CalculationStatus.NOT_APPLICABLE
    assert guarantor.required is False
    assert result.status == "未超限"


def test_adapter_preserves_production_breach_when_displayed_remaining_is_negative_zero() -> None:
    run = _run()
    overlay = run.overlay_stage1["限额明细_债券持仓明细表_信用债1_2"].copy()
    overlay.loc[0, "单一债券规模剩余额度(万)"] = -0.0
    overlay.loc[0, "单一债券是否超限"] = "是"
    overlay.loc[0, "单一主体规模剩余额度(万)"] = 1.0
    overlay.loc[0, "单一主体是否超限"] = "否"
    edge = replace(
        run,
        overlay_stage1={"限额明细_债券持仓明细表_信用债1_2": overlay},
    )

    result = PretradeResultAdapter().basket_from_kernel(edge)

    dimension = next(
        item for item in result.dimensions if item.name == "单一债券规模"
    )
    assert dimension.raw_remaining_wan == -0.0
    assert dimension.breached is True
    assert result.status == "已超限"
