"""将共同内核既有输出投影为交易前服务结果，不含限额公式。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from math import isfinite
from typing import Any

import pandas as pd

from .service_models import MasterResolution, MasterSource, PretradeLine


class CalculationStatus(StrEnum):
    CALCULATED = "CALCULATED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNCOMPUTABLE = "UNCOMPUTABLE"
    MISSING_INPUT = "MISSING_INPUT"
    MISSING_MASTER = "MISSING_MASTER"
    MISSING_SNAPSHOT = "MISSING_SNAPSHOT"


@dataclass(frozen=True)
class DimensionResult:
    name: str
    scope: str
    measure: str
    current_used_wan: float | None
    trade_amount_wan: float | None
    limit_value: float | None
    limit_unit: str | None
    raw_remaining_wan: float | None
    breached: bool
    calculation_status: CalculationStatus
    required: bool
    input_line_ids: tuple[int, ...]
    reason: str | None = None


@dataclass(frozen=True)
class InputLineAudit:
    line_id: int
    master_status: str
    master_source: MasterSource | None
    wind_fetched_at: datetime | None
    wind_data_date: str | None
    uncomputable_reason: str | None


@dataclass(frozen=True)
class BasketCheck:
    snapshot_data_date: str
    status: str
    total_pr_wan: float
    confirmed_breach_count: int
    uncomputable_count: int
    line_reasons: dict[int, str]
    dimensions: tuple[DimensionResult, ...]
    line_audits: tuple[InputLineAudit, ...]


@dataclass(frozen=True)
class SingleBondQuote:
    snapshot_data_date: str
    status: str
    raw_pr_remaining_wan: float | None
    purchasable_pr_cap_wan: float | None
    full_price_cost_remaining_wan: float | None
    binding_dimension: str | None
    dimensions: tuple[DimensionResult, ...]
    line_audits: tuple[InputLineAudit, ...]


@dataclass(frozen=True)
class KernelProjectionRun:
    """同一快照基线与叠加交易后的两套共同内核输出。"""

    data_date: str
    lines: tuple[PretradeLine, ...]
    resolutions: Mapping[int, MasterResolution]
    baseline_stage1: Mapping[str, pd.DataFrame]
    baseline_stage2: Mapping[str, pd.DataFrame]
    overlay_stage1: Mapping[str, pd.DataFrame]
    overlay_stage2: Mapping[str, pd.DataFrame]


@dataclass(frozen=True)
class DimensionProjection:
    name: str
    stage: int
    table: str
    remaining_column: str
    limit_column: str
    used_column: str
    overlimit_column: str
    key_columns: tuple[str, ...]
    scope_columns: tuple[str, ...]
    measure: str = "PR_WAN"
    unit: str = "万元"
    reason_column: str | None = None
    computable_column: str | None = None


_PROJECTIONS: tuple[DimensionProjection, ...] = (
    DimensionProjection("单一债券规模", 1, "限额明细_债券持仓明细表_信用债1_2", "单一债券规模剩余额度(万)", "单一债券规模限额指标值", "单一债券总持仓_PR", "单一债券是否超限", ("日期", "业务分类", "主证券代码_标准"), ("业务分类", "主证券代码_标准")),
    DimensionProjection("单一债券集中度", 1, "限额明细_债券持仓明细表_信用债1_2", "单一债券集中度剩余额度(万)", "单一债券集中度限额指标值", "单一债券总持仓_PR", "单一债券集中度是否超限", ("日期", "业务分类", "主证券代码_标准"), ("业务分类", "主证券代码_标准"), unit="比例"),
    DimensionProjection("单一主体规模", 1, "限额明细_债券持仓明细表_信用债1_2", "单一主体规模剩余额度(万)", "单一主体规模限额指标值", "单一主体总持仓_PR", "单一主体是否超限", ("日期", "业务分类", "债务主体"), ("业务分类", "债务主体")),
    DimensionProjection("单一实控人规模", 1, "限额明细_债券持仓明细表_信用债1_2", "单一实控人规模剩余额度(万)", "单一实控人规模限额指标值", "单一实控人总持仓_PR", "单一实控人是否超限", ("日期", "业务分类", "实际控制人名称_修正"), ("业务分类", "实际控制人名称_修正")),
    DimensionProjection("单一担保人规模", 1, "限额明细_债券持仓明细表_信用债1_2", "单一担保公司规模剩余额度(万)", "单一担保公司规模限额", "单一担保人总持仓_PR", "单一担保人是否超限", ("日期", "业务分类", "担保人wind代码"), ("业务分类", "担保人wind代码")),
    DimensionProjection("特定主体规模", 1, "限额明细_债券持仓明细表_信用债1_1", "特定主体限额剩余额度", "特定主体限额指标值", "特定主体总持仓", "特定主体限额是否超限", ("日期", "业务分类", "特定主体限额名称"), ("业务分类", "特定主体限额名称")),
    DimensionProjection("特定实控人规模", 1, "限额明细_债券持仓明细表_信用债1_1", "特定实控人限额剩余额度", "特定实控人限额指标值", "特定实控人总持仓", "特定实控人限额是否超限", ("日期", "业务分类", "特定实控人限额名称"), ("业务分类", "特定实控人限额名称")),
    DimensionProjection("监管集中度", 1, "限额明细_全量债券监管集中度", "监管集中度剩余额度(万)", "监管集中度限额指标值", "单债总持仓_PR", "监管集中度是否超限", ("日期", "监管归并主键"), ("监管归并主键",), unit="比例", reason_column="不可计算原因", computable_column="是否可计算"),
    DimensionProjection("地域集中度", 2, "限额明细_债券持仓明细表_信用债2", "地域集中度剩余额度(万)", "指标值_地域集中度限额", "单一地域总持仓_PR", "地域集中度是否超限", ("日期", "省份"), ("省份",), unit="比例"),
    DimensionProjection("城投地域集中度", 2, "限额明细_债券持仓明细表_信用债2", "城投集中度剩余额度(万)", "指标值_城投集中度限额", "单一地域城投总持仓_PR", "城投集中度是否超限", ("日期", "省份", "是否城投债"), ("省份", "是否城投债"), unit="比例"),
    DimensionProjection("高风险行业集中度", 2, "限额明细_债券持仓明细表_信用债2", "高风险行业集中度剩余额度(万)", "高风险行业之和集中度限额指标值", "高风险行业总持仓_PR", "高风险行业是否超限", ("日期", "wind行业"), ("wind行业",), unit="比例"),
    DimensionProjection("高风险省份集中度", 2, "限额明细_债券持仓明细表_信用债2", "高风险省份集中度剩余额度(万)", "高风险省份之和集中度限额指标值", "高风险省份总持仓_PR", "高风险省份是否超限", ("日期", "省份"), ("省份",), unit="比例"),
    DimensionProjection("高收益单一债券", 2, "限额明细_高收益", "高收益单债剩余额度(万)", "高收益单债限额(万)", "高收益单债总持仓(万)", "高收益单债是否超限", ("日期", "高收益单债归并键"), ("高收益单债归并键",)),
    DimensionProjection("高收益单一主体", 2, "限额明细_高收益", "高收益主体剩余额度(万)", "高收益主体限额(万)", "高收益主体总持仓(万)", "高收益主体是否超限", ("日期", "债务主体"), ("债务主体",)),
)
_ANNUAL_PROJECTION = DimensionProjection(
    "高收益年度全价成本", 2, "限额明细_高收益_投资本金规模", "高收益年度限额剩余额度(万)", "年度限额(万)", "高收益年度总投资本金(万)", "高收益年度限额是否超限", ("日期",), ("日期",), measure="FULL_PRICE_COST_WAN"
)

class PretradeResultAdapter:
    """只读取共同内核已经产生的列；不得自行计算限额或阈值。"""

    def basket_from_kernel(self, run: KernelProjectionRun) -> BasketCheck:
        dimensions, line_reasons = self._project(run, probe=False)
        breaches = sum(
            item.breached
            for item in dimensions
            if item.calculation_status is CalculationStatus.CALCULATED
        )
        uncomputable = sum(
            item.required
            and item.calculation_status
            not in {CalculationStatus.CALCULATED, CalculationStatus.NOT_APPLICABLE}
            for item in dimensions
        )
        return BasketCheck(
            snapshot_data_date=run.data_date,
            status=_overall_status(dimensions),
            total_pr_wan=sum(line.pr_wan for line in run.lines),
            confirmed_breach_count=breaches,
            uncomputable_count=uncomputable,
            line_reasons=line_reasons,
            dimensions=tuple(dimensions),
            line_audits=_line_audits(run),
        )

    def single_from_probe(self, run: KernelProjectionRun) -> SingleBondQuote:
        dimensions, _ = self._project(run, probe=True)
        pr_dimensions = [
            item
            for item in dimensions
            if item.measure == "PR_WAN"
            and item.calculation_status is CalculationStatus.CALCULATED
            and item.raw_remaining_wan is not None
        ]
        missing_required_pr = any(
            item.measure == "PR_WAN"
            and item.required
            and item.calculation_status
            not in {CalculationStatus.CALCULATED, CalculationStatus.NOT_APPLICABLE}
            for item in dimensions
        )
        raw_remaining = (
            min(item.raw_remaining_wan for item in pr_dimensions)
            if pr_dimensions
            else None
        )
        cap = None if missing_required_pr or raw_remaining is None else max(0.0, raw_remaining)
        binding = (
            next(item.name for item in pr_dimensions if item.raw_remaining_wan == raw_remaining)
            if raw_remaining is not None
            else None
        )
        full_price = [
            item.raw_remaining_wan
            for item in dimensions
            if item.measure == "FULL_PRICE_COST_WAN"
            and item.calculation_status is CalculationStatus.CALCULATED
            and item.raw_remaining_wan is not None
        ]
        return SingleBondQuote(
            snapshot_data_date=run.data_date,
            status=_overall_status(dimensions),
            raw_pr_remaining_wan=raw_remaining,
            purchasable_pr_cap_wan=cap,
            full_price_cost_remaining_wan=min(full_price) if full_price else None,
            binding_dimension=binding,
            dimensions=tuple(dimensions),
            line_audits=_line_audits(run),
        )

    def _project(
        self, run: KernelProjectionRun, *, probe: bool
    ) -> tuple[list[DimensionResult], dict[int, str]]:
        dimensions: list[DimensionResult] = []
        line_reasons: dict[int, str] = {}
        resolvable_lines: list[PretradeLine] = []
        for line in run.lines:
            resolution = run.resolutions.get(line.line_id)
            if resolution is None or resolution.master is None:
                source = (
                    resolution.source
                    if resolution is not None
                    else MasterSource.MISSING_MASTER
                )
                status = CalculationStatus(source.value)
                line_reasons[line.line_id] = status.value
                dimensions.append(
                    DimensionResult(
                        name="主数据",
                        scope=f"输入第 {line.line_id} 行",
                        measure="PR_WAN",
                        current_used_wan=None,
                        trade_amount_wan=None,
                        limit_value=None,
                        limit_unit="万元",
                        raw_remaining_wan=None,
                        breached=False,
                        calculation_status=status,
                        required=True,
                        input_line_ids=(line.line_id,),
                        reason=(resolution.reason if resolution is not None else "缺少主数据解析结果"),
                    )
                )
            else:
                resolvable_lines.append(line)

        for spec in _PROJECTIONS:
            dimensions.extend(self._project_spec(run, spec, resolvable_lines))
        dimensions.extend(self._project_annual_cost(run, resolvable_lines, probe=probe))
        return dimensions, line_reasons

    def _project_spec(
        self,
        run: KernelProjectionRun,
        spec: DimensionProjection,
        lines: list[PretradeLine],
    ) -> list[DimensionResult]:
        overlay = _stage_tables(run, spec.stage, overlay=True).get(spec.table)
        baseline = _stage_tables(run, spec.stage, overlay=False).get(spec.table)
        selected = (
            _select_target_rows(overlay, lines, run.resolutions)
            if isinstance(overlay, pd.DataFrame)
            else pd.DataFrame()
        )
        if selected.empty:
            baseline_selected = (
                _select_target_rows(baseline, lines, run.resolutions)
                if isinstance(baseline, pd.DataFrame)
                else pd.DataFrame()
            )
            baseline_proves_applicable = any(
                _row_proves_applicable(spec, row)
                for _, row in baseline_selected.iterrows()
            )
            if baseline_proves_applicable:
                return [
                    _missing_dimension(
                        spec,
                        lines,
                        reason=(
                            "共同内核缺少适用维度结果表"
                            if not isinstance(overlay, pd.DataFrame)
                            else "共同内核缺少适用维度结果行"
                        ),
                    )
                ]
            return []
        results: list[DimensionResult] = []
        processed: set[tuple[Any, ...]] = set()
        for _, row in selected.iterrows():
            key = _row_key(row, spec.key_columns)
            if key in processed:
                continue
            processed.add(key)
            line_ids = _line_ids_for_row(row, lines, run.resolutions)
            base_row = _matching_row(baseline, spec.key_columns, key)
            results.append(_dimension_from_rows(spec, row, base_row, line_ids))
        return results

    def _project_annual_cost(
        self,
        run: KernelProjectionRun,
        lines: list[PretradeLine],
        *,
        probe: bool,
    ) -> list[DimensionResult]:
        high_yield = _stage_tables(run, 2, overlay=True).get("限额明细_高收益")
        if not isinstance(high_yield, pd.DataFrame) or high_yield.empty:
            return []
        high_yield_lines = [
            line
            for line in lines
            if not _select_target_rows(high_yield, [line], run.resolutions).empty
        ]
        if not high_yield_lines:
            return []
        missing_cost = [line for line in high_yield_lines if line.full_price_cost_wan is None]
        results: list[DimensionResult] = []
        if missing_cost and not probe:
            results.append(
                DimensionResult(
                    name=_ANNUAL_PROJECTION.name,
                    scope="全账户/年度",
                    measure=_ANNUAL_PROJECTION.measure,
                    current_used_wan=None,
                    trade_amount_wan=None,
                    limit_value=None,
                    limit_unit="万元",
                    raw_remaining_wan=None,
                    breached=False,
                    calculation_status=CalculationStatus.UNCOMPUTABLE,
                    required=True,
                    input_line_ids=tuple(line.line_id for line in missing_cost),
                    reason="高收益债券缺少拟买全价成本",
                )
            )
        overlay = _stage_tables(run, 2, overlay=True).get(_ANNUAL_PROJECTION.table)
        baseline = _stage_tables(run, 2, overlay=False).get(_ANNUAL_PROJECTION.table)
        if not isinstance(overlay, pd.DataFrame) or overlay.empty:
            if any(line.full_price_cost_wan is not None for line in high_yield_lines):
                results.append(
                    DimensionResult(
                        name=_ANNUAL_PROJECTION.name,
                        scope="全账户/年度",
                        measure=_ANNUAL_PROJECTION.measure,
                        current_used_wan=None,
                        trade_amount_wan=None,
                        limit_value=None,
                        limit_unit="万元",
                        raw_remaining_wan=None,
                        breached=False,
                        calculation_status=CalculationStatus.MISSING_INPUT,
                        required=True,
                        input_line_ids=tuple(line.line_id for line in high_yield_lines),
                        reason="共同内核未产生高收益年度本金结果",
                    )
                )
            return results
        for _, row in overlay.head(1).iterrows():
            key = _row_key(row, _ANNUAL_PROJECTION.key_columns)
            base_row = _matching_row(baseline, _ANNUAL_PROJECTION.key_columns, key)
            results.append(
                _dimension_from_rows(
                    _ANNUAL_PROJECTION,
                    row,
                    base_row,
                    tuple(line.line_id for line in high_yield_lines),
                )
            )
        return results


def _line_audits(run: KernelProjectionRun) -> tuple[InputLineAudit, ...]:
    audits: list[InputLineAudit] = []
    for line in run.lines:
        resolution = run.resolutions.get(line.line_id)
        audits.append(
            InputLineAudit(
                line_id=line.line_id,
                master_status=(
                    "主数据可用"
                    if resolution is not None and resolution.master is not None
                    else "主数据不可用"
                ),
                master_source=resolution.source if resolution is not None else None,
                wind_fetched_at=(
                    resolution.wind_fetched_at if resolution is not None else None
                ),
                wind_data_date=(
                    resolution.wind_data_date if resolution is not None else None
                ),
                uncomputable_reason=(
                    resolution.reason if resolution is not None else None
                ),
            )
        )
    return tuple(audits)


def _overall_status(dimensions: list[DimensionResult]) -> str:
    """汇总后端维度状态；页面只消费该结果，不从数值重新判断。"""

    if any(
        item.breached
        for item in dimensions
        if item.calculation_status is CalculationStatus.CALCULATED
    ):
        return "已超限"
    if any(
        item.required
        and item.calculation_status
        not in {CalculationStatus.CALCULATED, CalculationStatus.NOT_APPLICABLE}
        for item in dimensions
    ):
        return "不可计算"
    return "未超限"


def _stage_tables(run: KernelProjectionRun, stage: int, *, overlay: bool) -> Mapping[str, pd.DataFrame]:
    if stage == 1:
        return run.overlay_stage1 if overlay else run.baseline_stage1
    return run.overlay_stage2 if overlay else run.baseline_stage2


def _dimension_from_rows(
    spec: DimensionProjection,
    overlay_row: pd.Series,
    baseline_row: pd.Series | None,
    line_ids: tuple[int, ...],
) -> DimensionResult:
    remaining = _as_finite_float(overlay_row.get(spec.remaining_column))
    limit = _as_finite_float(overlay_row.get(spec.limit_column))
    overlay_used = _as_finite_float(overlay_row.get(spec.used_column))
    baseline_used = (
        _as_finite_float(baseline_row.get(spec.used_column))
        if baseline_row is not None
        else None
    )
    production_overlimit = _as_text(overlay_row.get(spec.overlimit_column))
    if _is_production_uncomputable(spec, overlay_row):
        status = CalculationStatus.UNCOMPUTABLE
        reason = _as_text(
            overlay_row.get(spec.reason_column) if spec.reason_column else None
        ) or "生产结果标记为不可计算"
        required = True
    elif remaining is not None and limit is not None and overlay_used is not None:
        if production_overlimit in {"是", "否"}:
            status = CalculationStatus.CALCULATED
            reason = None
            required = True
        else:
            status = CalculationStatus.UNCOMPUTABLE
            reason = "生产结果缺少是否超限状态"
            required = True
    elif _row_proves_applicable(spec, overlay_row) or (
        baseline_row is not None and _row_proves_applicable(spec, baseline_row)
    ):
        status = CalculationStatus.UNCOMPUTABLE
        missing = [
            label
            for label, value in (
                ("剩余额度", remaining),
                ("限额", limit),
                ("占用", overlay_used),
            )
            if value is None
        ]
        reason = f"生产结果缺少适用维度的{','.join(missing)}"
        required = True
    else:
        status = CalculationStatus.NOT_APPLICABLE
        reason = "生产结果未给出适用限额"
        required = False
    trade_amount = (
        overlay_used - baseline_used
        if overlay_used is not None and baseline_used is not None
        else None
    )
    return DimensionResult(
        name=spec.name,
        scope=_scope(overlay_row, spec.scope_columns),
        measure=spec.measure,
        current_used_wan=baseline_used,
        trade_amount_wan=trade_amount,
        limit_value=limit,
        limit_unit=spec.unit,
        raw_remaining_wan=remaining,
        breached=production_overlimit == "是",
        calculation_status=status,
        required=required,
        input_line_ids=line_ids,
        reason=reason,
    )


def _missing_dimension(
    spec: DimensionProjection,
    lines: list[PretradeLine],
    *,
    reason: str,
) -> DimensionResult:
    return DimensionResult(
        name=spec.name,
        scope="输入交易",
        measure=spec.measure,
        current_used_wan=None,
        trade_amount_wan=None,
        limit_value=None,
        limit_unit=spec.unit,
        raw_remaining_wan=None,
        breached=False,
        calculation_status=CalculationStatus.UNCOMPUTABLE,
        required=True,
        input_line_ids=tuple(line.line_id for line in lines),
        reason=reason,
    )


def _row_proves_applicable(spec: DimensionProjection, row: pd.Series) -> bool:
    return (
        _is_production_uncomputable(spec, row)
        or _as_text(row.get(spec.overlimit_column)) == "是"
        or _as_finite_float(row.get(spec.remaining_column)) is not None
        or _as_finite_float(row.get(spec.limit_column)) is not None
    )


def _is_production_uncomputable(spec: DimensionProjection, row: pd.Series) -> bool:
    if spec.computable_column and spec.computable_column in row:
        return _as_text(row.get(spec.computable_column)) not in {None, "是", "TRUE", "True"}
    if spec.reason_column:
        return _as_text(row.get(spec.reason_column)) is not None
    return False


def _select_target_rows(
    frame: pd.DataFrame,
    lines: list[PretradeLine] | tuple[PretradeLine, ...],
    resolutions: Mapping[int, MasterResolution],
) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    codes: set[str] = set()
    isins: set[str] = set()
    for line in lines:
        resolution = resolutions.get(line.line_id)
        master = resolution.master if resolution is not None else None
        if master is None:
            continue
        codes.update(
            value
            for value in (line.bond_code, master.input_code, master.main_security_code)
            if _as_text(value) is not None
        )
        if master.isin_code:
            isins.add(master.isin_code.upper())
    codes = {_normalised_code(code) for code in codes}
    isins = {_normalised_code(isin) for isin in isins}
    mask = pd.Series(False, index=frame.index)
    for column in ("资产代码", "主证券代码", "主证券代码_标准", "监管归并主键", "高收益单债归并键"):
        if column in frame:
            mask |= frame[column].map(_normalised_code).isin(codes)
    if "ISIN码" in frame:
        mask |= frame["ISIN码"].map(_normalised_code).isin(isins)
    return frame.loc[mask].copy()


def _line_ids_for_row(
    row: pd.Series,
    lines: list[PretradeLine],
    resolutions: Mapping[int, MasterResolution],
) -> tuple[int, ...]:
    one_row = pd.DataFrame([row])
    return tuple(
        sorted(
            line.line_id
            for line in lines
            if not _select_target_rows(one_row, [line], resolutions).empty
        )
    )


def _row_key(row: pd.Series, columns: tuple[str, ...]) -> tuple[Any, ...]:
    return tuple(_value_key(row.get(column)) for column in columns)


def _matching_row(
    frame: pd.DataFrame | None,
    columns: tuple[str, ...],
    key: tuple[Any, ...],
) -> pd.Series | None:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return None
    if any(column not in frame for column in columns):
        return None
    mask = pd.Series(True, index=frame.index)
    for column, wanted in zip(columns, key, strict=True):
        mask &= frame[column].map(_value_key) == wanted
    matched = frame.loc[mask]
    return matched.iloc[0] if not matched.empty else None


def _value_key(value: Any) -> str:
    text = _as_text(value)
    if text is None:
        return "<NULL>"
    if isinstance(value, pd.Timestamp):
        return value.normalize().isoformat()
    return text.upper()


def _scope(row: pd.Series, columns: tuple[str, ...]) -> str:
    values = [_as_text(row.get(column)) for column in columns]
    return "/".join(value for value in values if value is not None) or "全账户"


def _normalised_code(value: Any) -> str:
    text = _as_text(value)
    return text.upper() if text is not None else ""


def _as_text(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    return None if text.lower() in {"", "nan", "none", "null", "nat", "<na>"} else text


def _as_finite_float(value: Any) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if isfinite(numeric) else None
