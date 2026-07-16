"""交易前共同服务结果的页面展示转换；不含限额计算。"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pandas as pd

from src.pretrade.result_adapter import (
    BasketCheck,
    CalculationStatus,
    DimensionResult,
    SingleBondQuote,
)
from src.pretrade.service_models import PretradeLine


_BASKET_COLUMNS = (
    "债券代码",
    "拟买金额(万)_PR",
    "拟买入账户",
    "拟买全价成本(万)",
)


def basket_lines_from_frame(frame: pd.DataFrame) -> tuple[PretradeLine, ...]:
    """将可编辑交易清单变成服务输入；空行不构成交易。"""

    if not isinstance(frame, pd.DataFrame):
        raise TypeError("交易清单必须是表格")
    missing = [column for column in _BASKET_COLUMNS if column not in frame]
    if missing:
        raise ValueError(f"交易清单缺少列: {', '.join(missing)}")

    lines: list[PretradeLine] = []
    for line_id, (_, row) in enumerate(frame.iterrows(), start=1):
        values = {column: _cell_value(row[column]) for column in _BASKET_COLUMNS}
        if all(value is None for value in values.values()):
            continue
        lines.append(
            PretradeLine(
                line_id=line_id,
                bond_code=values["债券代码"],
                account=values["拟买入账户"],
                pr_wan=values["拟买金额(万)_PR"],
                full_price_cost_wan=values["拟买全价成本(万)"],
            )
        )
    return tuple(lines)


def dimension_frame(
    dimensions: Sequence[DimensionResult], *, remaining_label: str
) -> pd.DataFrame:
    """将服务维度结果直接投影为可导出的展示表。"""

    rows = [
        {
            "维度名称": item.name,
            "状态": _dimension_status(item),
            remaining_label: item.raw_remaining_wan,
            "适用范围": item.scope,
            "当前占用(万)": item.current_used_wan,
            "本次拟买(万)": item.trade_amount_wan,
            "限额值": item.limit_value,
            "限额单位": item.limit_unit,
            "涉及输入行": ", ".join(str(line_id) for line_id in item.input_line_ids),
            "原因": item.reason,
        }
        for item in dimensions
    ]
    return pd.DataFrame(
        rows,
        columns=(
            "维度名称",
            "状态",
            remaining_label,
            "适用范围",
            "当前占用(万)",
            "本次拟买(万)",
            "限额值",
            "限额单位",
            "涉及输入行",
            "原因",
        ),
    )


def single_quote_status(quote: SingleBondQuote) -> str:
    if quote.purchasable_pr_cap_wan is None:
        return "不可计算"
    if quote.raw_pr_remaining_wan is not None and quote.raw_pr_remaining_wan < 0:
        return "当前已超限"
    return "可计算"


def basket_summary(result: BasketCheck) -> dict[str, Any]:
    """返回篮子顶部指标所需的服务原值。"""

    return {
        "总体状态": result.status,
        "本次拟买总额(万)": result.total_pr_wan,
        "超限维度": result.confirmed_breach_count,
        "不可计算维度": result.uncomputable_count,
        "快照日期": result.snapshot_data_date,
    }


def _cell_value(value: Any) -> Any | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped if stripped else None
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _dimension_status(item: DimensionResult) -> str:
    if item.calculation_status is CalculationStatus.CALCULATED:
        return "超限" if item.breached else "可计算"
    if item.calculation_status is CalculationStatus.NOT_APPLICABLE:
        return "不适用"
    return "不可计算"
