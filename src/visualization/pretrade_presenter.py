"""交易前共同服务结果的页面展示转换；不含限额计算。"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

import pandas as pd

from src.pretrade.result_adapter import (
    BasketCheck,
    CalculationStatus,
    DimensionResult,
    InputLineAudit,
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
        values["拟买金额(万)_PR"] = _numeric_cell_value(
            values["拟买金额(万)_PR"],
            label="拟买金额",
            line_id=line_id,
        )
        values["拟买全价成本(万)"] = _numeric_cell_value(
            values["拟买全价成本(万)"],
            label="高收益全价成本",
            line_id=line_id,
        )
        if all(
            values[column] is None
            for column in ("债券代码", "拟买金额(万)_PR", "拟买全价成本(万)")
        ):
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
    """原样返回后端总体状态，不从金额字段推导。"""

    return quote.status


def line_audit_frame(audits: Sequence[InputLineAudit]) -> pd.DataFrame:
    """将后端逐输入行审计契约直接投影为稳定展示文本。"""

    rows = [
        {
            "输入行": item.line_id,
            "主数据解析状态": item.master_status,
            "master_source": (
                item.master_source.value
                if item.master_source is not None
                else "—"
            ),
            "wind_fetched_at": (
                item.wind_fetched_at.isoformat(sep=" ", timespec="seconds")
                if item.wind_fetched_at is not None
                else "—"
            ),
            "wind_data_date": item.wind_data_date or "—",
            "uncomputable_reason": item.uncomputable_reason or "—",
        }
        for item in audits
    ]
    return pd.DataFrame(
        rows,
        columns=(
            "输入行",
            "主数据解析状态",
            "master_source",
            "wind_fetched_at",
            "wind_data_date",
            "uncomputable_reason",
        ),
    )


def business_dimension_frame(
    dimensions: Sequence[DimensionResult], *, remaining_label: str
) -> pd.DataFrame:
    """将全部维度转换为面向业务用户的展示表，并按风险优先级排序。"""

    rows = [
        {
            "风险维度": item.name,
            "状态": _business_dimension_status(item),
            "适用对象": item.scope,
            "当前占用（万元）": item.current_used_wan,
            "本次拟买（万元）": item.trade_amount_wan,
            "拟买后占用（万元）": _sum_if_complete(
                item.current_used_wan, item.trade_amount_wan
            ),
            remaining_label: item.raw_remaining_wan,
            "限额": _format_business_limit(item.limit_value, item.limit_unit),
            "涉及交易行": ", ".join(
                str(line_id) for line_id in item.input_line_ids
            )
            or "—",
            "说明": _business_reason(item.reason),
            "_排序": _dimension_sort_key(item),
        }
        for item in dimensions
    ]
    columns = (
        "风险维度",
        "状态",
        "适用对象",
        "当前占用（万元）",
        "本次拟买（万元）",
        "拟买后占用（万元）",
        remaining_label,
        "限额",
        "涉及交易行",
        "说明",
        "_排序",
    )
    frame = pd.DataFrame(rows, columns=columns)
    if frame.empty:
        return frame.drop(columns="_排序")
    return (
        frame.sort_values(
            by=["_排序", remaining_label, "风险维度"],
            ascending=[True, True, True],
            na_position="last",
            kind="stable",
        )
        .drop(columns="_排序")
        .reset_index(drop=True)
    )


def business_line_audit_frame(
    audits: Sequence[InputLineAudit], *, snapshot_data_date: str
) -> pd.DataFrame:
    """将主数据审计转换为业务文案，隐藏内部枚举和技术字段名。"""

    rows = []
    for item in audits:
        source = _business_source(item.master_source)
        data_date = (
            snapshot_data_date
            if item.master_source is not None
            and item.master_source.value == "SNAPSHOT"
            else item.wind_data_date or "—"
        )
        rows.append(
            {
                "输入行": item.line_id,
                "主数据状态": item.master_status,
                "数据来源": source,
                "数据日期": data_date,
                "说明": _business_reason(item.uncomputable_reason),
            }
        )
    return pd.DataFrame(
        rows,
        columns=("输入行", "主数据状态", "数据来源", "数据日期", "说明"),
    )


def basket_input_result_frame(
    frame: pd.DataFrame,
    audits: Sequence[InputLineAudit],
    line_reasons: dict[int, str],
) -> pd.DataFrame:
    """把已提交篮子与逐行状态合并为用户可读的交易结果。"""

    audit_by_line = {item.line_id: item for item in audits}
    rows = []
    for line in basket_lines_from_frame(frame):
        audit = audit_by_line.get(line.line_id)
        reason = line_reasons.get(line.line_id)
        if reason:
            explanation = _business_reason(reason)
        elif audit is not None and audit.uncomputable_reason:
            explanation = audit.uncomputable_reason
        else:
            explanation = "可计算"
        rows.append(
            {
                "输入行": line.line_id,
                "债券代码": line.bond_code,
                "拟买金额（万元）": line.pr_wan,
                "拟买账户": line.account,
                "高收益全价成本（万元）": line.full_price_cost_wan,
                "主数据状态": (
                    audit.master_status if audit is not None else "—"
                ),
                "计算说明": explanation,
            }
        )
    return pd.DataFrame(
        rows,
        columns=(
            "输入行",
            "债券代码",
            "拟买金额（万元）",
            "拟买账户",
            "高收益全价成本（万元）",
            "主数据状态",
            "计算说明",
        ),
    )


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


def _numeric_cell_value(
    value: Any | None,
    *,
    label: str,
    line_id: int,
) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"输入第 {line_id} 行的{label}必须为数字")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"输入第 {line_id} 行的{label}必须为数字") from exc
    if pd.isna(number):
        return None
    return number


def _dimension_status(item: DimensionResult) -> str:
    if item.calculation_status is CalculationStatus.CALCULATED:
        return "超限" if item.breached else "可计算"
    if item.calculation_status is CalculationStatus.NOT_APPLICABLE:
        return "不适用"
    return "不可计算"


def _business_dimension_status(item: DimensionResult) -> str:
    if item.calculation_status is CalculationStatus.CALCULATED:
        return "已超限" if item.breached else "未超限"
    if item.calculation_status is CalculationStatus.NOT_APPLICABLE:
        return "不适用"
    return "不可计算"


def _dimension_sort_key(item: DimensionResult) -> int:
    status = _business_dimension_status(item)
    return {
        "已超限": 0,
        "不可计算": 1,
        "未超限": 2,
        "不适用": 3,
    }[status]


def _sum_if_complete(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    return float(left) + float(right)


def _format_business_limit(value: float | None, unit: str | None) -> str:
    if value is None:
        return "—"
    if unit == "比例":
        return f"{float(value) * 100:.2f}%"
    suffix = f" {unit}" if unit else ""
    return f"{float(value):,.2f}{suffix}"


def _business_source(source: Any | None) -> str:
    if source is None:
        return "—"
    return {
        "SNAPSHOT": "交易前快照",
        "WIND": "Wind 主数据",
        "MISSING_SNAPSHOT": "快照数据缺失",
        "MISSING_MASTER": "主数据缺失",
    }.get(source.value, "其他来源")


_DIMENSION_REASON_MAP = {
    "MISSING_SNAPSHOT": "交易前快照缺少该债券主数据",
    "MISSING_MASTER": "未取得该债券完整主数据",
    "UNCOMPUTABLE": "该交易当前不可计算",
    "MISSING_INPUT": "缺少计算所需输入",
    "缺少主数据解析结果": "缺少该债券主数据",
    "共同内核缺少适用维度结果表": "限额快照缺少该维度结果",
    "共同内核缺少适用维度结果行": "限额快照缺少该维度适用记录",
    "共同内核未产生高收益年度本金结果": "高收益年度本金结果未生成",
    "生产结果标记为不可计算": "该维度当前不可计算",
    "生产结果缺少是否超限状态": "缺少该维度超限状态",
    "生产结果未给出适用限额": "该维度不适用",
    "生产结果缺少适用维度的剩余额度": "缺少该维度剩余额度",
    "生产结果缺少适用维度的限额": "缺少该维度限额",
    "生产结果缺少适用维度的占用": "缺少该维度当前占用",
    "生产结果缺少适用维度的剩余额度,限额": "缺少该维度剩余额度与限额",
    "生产结果缺少适用维度的剩余额度,占用": "缺少该维度剩余额度与占用",
    "生产结果缺少适用维度的限额,占用": "缺少该维度限额与占用",
    "生产结果缺少适用维度的剩余额度,限额,占用": "缺少该维度剩余额度、限额与占用",
    "高收益债券缺少拟买全价成本": "高收益债需填写拟买全价成本",
    "Wind 字段映射尚未通过连通性验收": "主数据字段不完整",
}


def _business_reason(reason: str | None) -> str:
    """把后端内部 reason 转换为业务用户可读的说明。"""
    if not reason:
        return "—"
    if reason in _DIMENSION_REASON_MAP:
        return _DIMENSION_REASON_MAP[reason]
    # 兜底：替换常见内部架构措辞
    cleaned = (
        reason.replace("生产结果", "限额快照")
        .replace("共同内核", "交易前内核")
        .replace("适用维度", "该维度")
        .replace("是否超限状态", "超限状态")
        .replace("主数据解析结果", "主数据结果")
        .replace("Wind 字段映射", "主数据字段")
    )
    return cleaned
