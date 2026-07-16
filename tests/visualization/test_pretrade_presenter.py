from __future__ import annotations

import pandas as pd
from pathlib import Path

from src.pretrade.result_adapter import CalculationStatus, DimensionResult
from src.pretrade.service_models import PretradeLine
from src.visualization.pretrade_presenter import basket_lines_from_frame, dimension_frame


def _dimension(*, status: CalculationStatus, remaining: float | None) -> DimensionResult:
    return DimensionResult(
        name="主数据",
        scope="输入第 1 行",
        measure="PR_WAN",
        current_used_wan=None,
        trade_amount_wan=None,
        limit_value=None,
        limit_unit="万元",
        raw_remaining_wan=remaining,
        breached=False,
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


def test_single_bond_page_uses_pretrade_service_not_legacy_query() -> None:
    source = Path("src/visualization/pages/page8_bond_quota.py").read_text(
        encoding="utf-8"
    )

    assert "query_bond_remaining_quota" not in source
    assert "get_pretrade_risk_service" in source


def test_app_and_sidebar_expose_only_the_new_basket_route() -> None:
    assert "一揽子债券超限试算" in Path("app.py").read_text(encoding="utf-8")
    assert "一揽子债券超限试算" in Path(
        "src/visualization/components/sidebar.py"
    ).read_text(encoding="utf-8")
