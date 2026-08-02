from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from src.pretrade.result_adapter import (
    CalculationStatus,
    DimensionResult,
    InputLineAudit,
    SingleBondQuote,
)
from src.pretrade.service_models import MasterSource, PretradeLine
from src.visualization.pretrade_presenter import (
    basket_input_result_frame,
    basket_lines_from_frame,
    business_dimension_frame,
    business_line_audit_frame,
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
    name: str = "主数据",
    scope: str = "输入第 1 行",
    current_used_wan: float | None = None,
    trade_amount_wan: float | None = None,
    limit_value: float | None = None,
) -> DimensionResult:
    return DimensionResult(
        name=name,
        scope=scope,
        measure="PR_WAN",
        current_used_wan=current_used_wan,
        trade_amount_wan=trade_amount_wan,
        limit_value=limit_value,
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
                    "拟买入账户": "自营部交易性",
                    "拟买全价成本(万)": pd.NA,
                },
            ]
        )
    )

    assert lines == (PretradeLine(1, "102480811.IB", "任意账户", 100.0, None),)


def test_basket_parser_accepts_user_facing_numeric_text_and_rejects_invalid_text() -> None:
    source = pd.DataFrame(
        [
            {
                "债券代码": "1980082.IB",
                "拟买金额(万)_PR": "2000.50",
                "拟买入账户": "自营部交易性",
                "拟买全价成本(万)": "",
            }
        ]
    )

    assert basket_lines_from_frame(source) == (
        PretradeLine(1, "1980082.IB", "自营部交易性", 2000.5, None),
    )

    source.loc[0, "拟买金额(万)_PR"] = "两千"
    with pytest.raises(ValueError, match="输入第 1 行的拟买金额必须为数字"):
        basket_lines_from_frame(source)


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


def test_business_dimension_frame_keeps_all_dimensions_and_sorts_risk_first() -> None:
    frame = business_dimension_frame(
        (
            _dimension(
                status=CalculationStatus.NOT_APPLICABLE,
                remaining=None,
                name="不适用维度",
            ),
            _dimension(
                status=CalculationStatus.CALCULATED,
                remaining=500.0,
                name="普通维度",
                current_used_wan=100.0,
                trade_amount_wan=20.0,
                limit_value=620.0,
            ),
            _dimension(
                status=CalculationStatus.MISSING_INPUT,
                remaining=None,
                name="缺输入维度",
            ),
            _dimension(
                status=CalculationStatus.CALCULATED,
                remaining=-10.0,
                breached=True,
                name="超限维度",
                current_used_wan=100.0,
                trade_amount_wan=30.0,
                limit_value=120.0,
            ),
            _dimension(
                status=CalculationStatus.CALCULATED,
                remaining=30.0,
                name="比例维度",
                limit_unit="比例",
                limit_value=0.125,
            ),
        ),
        remaining_label="交易后剩余额度（万元）",
    )

    assert frame["风险维度"].tolist() == [
        "超限维度",
        "缺输入维度",
        "比例维度",
        "普通维度",
        "不适用维度",
    ]
    assert frame["状态"].tolist() == [
        "已超限",
        "不可计算",
        "未超限",
        "未超限",
        "不适用",
    ]
    assert frame.loc[0, "拟买后占用（万元）"] == 130.0
    assert frame.loc[2, "限额"] == "12.50%"
    assert len(frame) == 5


def test_business_line_audit_frame_hides_technical_fields_and_uses_snapshot_date() -> None:
    frame = business_line_audit_frame(
        (
            InputLineAudit(
                line_id=1,
                master_status="主数据可用",
                master_source=MasterSource.SNAPSHOT,
                wind_fetched_at=None,
                wind_data_date=None,
                uncomputable_reason=None,
            ),
            InputLineAudit(
                line_id=2,
                master_status="主数据可用",
                master_source=MasterSource.WIND,
                wind_fetched_at=datetime(2026, 7, 23, 9, 30),
                wind_data_date="2026-07-22",
                uncomputable_reason=None,
            ),
        ),
        snapshot_data_date="2026-07-23",
    )

    assert frame.columns.tolist() == [
        "输入行",
        "主数据状态",
        "数据来源",
        "数据日期",
        "说明",
    ]
    assert frame.to_dict("records") == [
        {
            "输入行": 1,
            "主数据状态": "主数据可用",
            "数据来源": "交易前快照",
            "数据日期": "2026-07-23",
            "说明": "—",
        },
        {
            "输入行": 2,
            "主数据状态": "主数据可用",
            "数据来源": "Wind 主数据",
            "数据日期": "2026-07-22",
            "说明": "—",
        },
    ]


def test_basket_input_result_frame_uses_only_submitted_rows_and_business_reason() -> None:
    source = pd.DataFrame(
        [
            {
                "债券代码": "1980082.IB",
                "拟买金额(万)_PR": 2000.0,
                "拟买入账户": "自营部交易性",
                "拟买全价成本(万)": pd.NA,
            },
            {
                "债券代码": "",
                "拟买金额(万)_PR": pd.NA,
                "拟买入账户": "自营部交易性",
                "拟买全价成本(万)": pd.NA,
            },
        ]
    )
    frame = basket_input_result_frame(
        source,
        (
            InputLineAudit(
                line_id=1,
                master_status="主数据不可用",
                master_source=MasterSource.MISSING_SNAPSHOT,
                wind_fetched_at=None,
                wind_data_date=None,
                uncomputable_reason="快照缺少该债券",
            ),
        ),
        {1: "MISSING_SNAPSHOT"},
    )

    assert len(frame) == 1
    assert frame.loc[0, "债券代码"] == "1980082.IB"
    assert frame.loc[0, "拟买金额（万元）"] == 2000.0
    assert frame.loc[0, "计算说明"] == "交易前快照缺少该债券主数据"


def test_single_bond_page_uses_pretrade_service_not_legacy_query() -> None:
    source = Path("src/visualization/pages/page8_bond_quota.py").read_text(
        encoding="utf-8"
    )

    assert "query_bond_remaining_quota" not in source
    assert "get_pretrade_risk_service" in source
    assert "business_line_audit_frame" in source
    assert "business_dimension_frame" in source
    assert 'st.tabs(["风险约束", "数据说明"])' in source
    assert "master_source" not in source
    assert "wind_fetched_at" not in source


def test_basket_page_displays_backend_status_and_line_audits() -> None:
    source = Path("src/visualization/pages/page10_basket_pretrade.py").read_text(
        encoding="utf-8"
    )

    assert "_render_status(result)" in source
    assert 'if result.status == "已超限"' in source
    assert 'if result.status == "不可计算"' in source
    assert "business_line_audit_frame" in source
    assert "business_dimension_frame" in source
    assert "basket_input_result_frame" in source
    assert '["交易结果", "风险约束", "数据说明"]' in source
    assert "master_source" not in source
    assert "wind_fetched_at" not in source


def test_app_and_sidebar_expose_only_the_new_basket_route() -> None:
    assert "债券组合超限试算" in Path("app.py").read_text(encoding="utf-8")
    assert "债券组合超限试算" in Path(
        "src/visualization/components/sidebar.py"
    ).read_text(encoding="utf-8")
