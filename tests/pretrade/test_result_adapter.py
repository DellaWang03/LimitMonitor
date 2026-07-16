from __future__ import annotations

import pandas as pd

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
        controller_name="测试实控人",
        guarantor_name=None,
        guarantor_wind_code=None,
        outstanding_balance_yi=10.0,
        bond_classification="信用债",
        bond_type="中期票据",
        issuer_type="国企",
        is_city_investment_bond="否",
        bond_category="国企债",
        wind_industry="公用事业",
        province="河北省",
    )


def _credit_row(*, bond_used: float, bond_remaining: float, issuer_used: float, issuer_remaining: float):
    return {
        "日期": pd.Timestamp("2026-07-10"),
        "业务分类": "自营业务",
        "资产代码": "900001.IB",
        "主证券代码_标准": "900001.IB",
        "债务主体": "测试发行人",
        "实际控制人名称_修正": "测试实控人",
        "担保人wind代码": None,
        "单一债券总持仓_PR": bond_used,
        "单一债券规模限额指标值": 100.0,
        "单一债券规模剩余额度(万)": bond_remaining,
        "单一债券集中度限额指标值": 0.16,
        "单一债券集中度剩余额度(万)": 0.0,
        "单一主体总持仓_PR": issuer_used,
        "单一主体规模限额指标值": 100.0,
        "单一主体规模剩余额度(万)": issuer_remaining,
        "单一实控人总持仓_PR": None,
        "单一实控人规模限额指标值": None,
        "单一实控人规模剩余额度(万)": None,
        "单一担保人总持仓_PR": None,
        "单一担保公司规模限额": None,
        "单一担保公司规模剩余额度(万)": None,
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


def test_adapter_keeps_full_price_out_of_pr_minimum() -> None:
    quote = PretradeResultAdapter().single_from_probe(_run(include_annual=True))

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
