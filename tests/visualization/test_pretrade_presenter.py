from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.pretrade.result_adapter import (
    CalculationStatus,
    DimensionResult,
    InputLineAudit,
    SingleBondQuote,
)
from src.pretrade.service_models import MasterSource, PretradeLine
from src.visualization.pretrade_presenter import (
    basket_lines_from_frame,
    dimension_frame,
    line_audit_frame,
    single_quote_status,
)


def _dimension(
    *,
    status: CalculationStatus,
    remaining: float | None,
    breached: bool = False,
    limit_unit: str | None = "万元",
) -> DimensionResult:
    return DimensionResult(
        name="主数据",
        scope="输入第 1 行",
        measure="PR_WAN",
        current_used_wan=None,
        trade_amount_wan=None,
        limit_value=None,
        limit_unit=limit_unit,
        raw_remaining_wan=remaining,
        breached=breached,
        calculation_status=status,
        required=True,
        input_line_ids=(1,),
        reason="Wind 字段映射尚未通过连通性验收",
    )


def test_basket_parser_discards_blank_rows_and_preserves_user_account() -> None:
    lines = basket_lines_from_frame(
        pd.DataFrame(
            [
                {
                    "债券代码": "102480811.IB",
                    "拟买金额(万)_PR": 100.0,
                    "拟买入账户": "任意账户",
                    "拟买全价成本(万)": pd.NA,
                },
                {
                    "债券代码": "",
                    "拟买金额(万)_PR": pd.NA,
                    "拟买入账户": "",
                    "拟买全价成本(万)": pd.NA,
                },
            ]
        )
    )

    assert lines == (PretradeLine(1, "102480811.IB", "任意账户", 100.0, None),)


def test_dimension_frame_keeps_missing_master_as_uncomputable_not_zero() -> None:
    frame = dimension_frame(
        (_dimension(status=CalculationStatus.MISSING_MASTER, remaining=None),),
        remaining_label="交易后剩余(万)",
    )

    assert frame.loc[0, "状态"] == "不可计算"
    assert pd.isna(frame.loc[0, "交易后剩余(万)"])
    assert frame.loc[0, "原因"] == "Wind 字段映射尚未通过连通性验收"


def test_dimension_frame_uses_backend_status_flags_and_keeps_units() -> None:
    frame = dimension_frame(
        (
            _dimension(
                status=CalculationStatus.CALCULATED,
                remaining=999.0,
                breached=True,
                limit_unit="万元",
            ),
            _dimension(
                status=CalculationStatus.CALCULATED,
                remaining=-999.0,
                breached=False,
                limit_unit="比例",
            ),
        ),
        remaining_label="交易后剩余(万)",
    )

    assert frame["状态"].tolist() == ["超限", "可计算"]
    assert frame["限额单位"].tolist() == ["万元", "比例"]


def test_single_quote_status_uses_backend_when_numbers_conflict() -> None:
    quote = SingleBondQuote(
        snapshot_data_date="2026-07-10",
        status="不可计算",
        raw_pr_remaining_wan=-999.0,
        purchasable_pr_cap_wan=123.0,
        full_price_cost_remaining_wan=None,
        binding_dimension=None,
        dimensions=(),
        line_audits=(),
    )

    assert single_quote_status(quote) == "不可计算"


def test_line_audit_frame_displays_source_dates_reason_and_none_stably() -> None:
    fetched_at = datetime(2026, 7, 23, 9, 30, 45, tzinfo=timezone.utc)
    frame = line_audit_frame(
        (
            InputLineAudit(
                line_id=1,
                master_status="主数据可用",
                master_source=MasterSource.WIND,
                wind_fetched_at=fetched_at,
                wind_data_date="2026-07-22",
                uncomputable_reason=None,
            ),
            InputLineAudit(
                line_id=2,
                master_status="主数据不可用",
                master_source=MasterSource.MISSING_MASTER,
                wind_fetched_at=None,
                wind_data_date=None,
                uncomputable_reason="Wind 返回记录缺少省份",
            ),
            InputLineAudit(
                line_id=3,
                master_status="主数据不可用",
                master_source=None,
                wind_fetched_at=None,
                wind_data_date=None,
                uncomputable_reason=None,
            ),
        )
    )

    assert frame.to_dict("records") == [
        {
            "输入行": 1,
            "主数据解析状态": "主数据可用",
            "master_source": "WIND",
            "wind_fetched_at": "2026-07-23 09:30:45+00:00",
            "wind_data_date": "2026-07-22",
            "uncomputable_reason": "—",
        },
        {
            "输入行": 2,
            "主数据解析状态": "主数据不可用",
            "master_source": "MISSING_MASTER",
            "wind_fetched_at": "—",
            "wind_data_date": "—",
            "uncomputable_reason": "Wind 返回记录缺少省份",
        },
        {
            "输入行": 3,
            "主数据解析状态": "主数据不可用",
            "master_source": "—",
            "wind_fetched_at": "—",
            "wind_data_date": "—",
            "uncomputable_reason": "—",
        },
    ]


def test_single_bond_page_uses_pretrade_service_not_legacy_query() -> None:
    source = Path("src/visualization/pages/page8_bond_quota.py").read_text(
        encoding="utf-8"
    )

    assert "query_bond_remaining_quota" not in source
    assert "get_pretrade_risk_service" in source
    assert "line_audit_frame" in source
    assert "主数据来源与解析审计" in source
    assert "逐行审计状态" not in source


def test_basket_page_displays_backend_status_and_line_audits() -> None:
    source = Path("src/visualization/pages/page10_basket_pretrade.py").read_text(
        encoding="utf-8"
    )

    assert 'status = str(summary["总体状态"])' in source
    assert "line_audit_frame" in source
    assert "主数据来源与解析审计" in source
    assert "逐行审计状态" not in source


def test_app_and_sidebar_expose_only_the_new_basket_route() -> None:
    assert "一揽子债券超限试算" in Path("app.py").read_text(encoding="utf-8")
    assert "一揽子债券超限试算" in Path(
        "src/visualization/components/sidebar.py"
    ).read_text(encoding="utf-8")
