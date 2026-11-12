"""从交易前 current 快照识别持仓债；仅确认非持仓时请求 Wind。"""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import replace
from math import isfinite, isnan
from typing import Any, ContextManager

import pandas as pd

from src.common.security_code_normalizer import normalize_security_code_series
from src.risk_core import ProductionKernelInput
from src.risk_core.position_context import build_credit_risk_context

from .service_models import (
    BondMaster,
    BondMasterProvider,
    MasterResolution,
    MasterSource,
    missing_required_bond_master_fields,
)


_HELD_POSITION_DATASET = "债券持仓明细表_信用债"
_CODE_COLUMNS = ("资产代码", "主证券代码")
_MASTER_COLUMNS = {
    "main_security_code": ("主证券代码",),
    "isin_code": ("ISIN码",),
    "bond_name": ("资产名称", "主证券名称"),
    "asset_name": ("资产名称",),
    "main_security_name": ("主证券名称",),
    "issuer_name": ("债务主体",),
    "issuer_wind_code": ("债务主体wind代码",),
    "guarantor_name": ("担保人",),
    "guarantor_wind_code": ("担保人wind代码",),
    "outstanding_balance_yi": ("债券余额(亿)",),
    "bond_classification": ("债券分类2",),
    "bond_type": ("债券类型1",),
    "issuer_type": ("发行人类型",),
    "is_city_investment_bond": ("是否城投债",),
    "bond_category": ("债券类别",),
    "wind_industry": ("wind行业",),
    "province": ("省份",),
}
class SnapshotBondMasterResolver:
    """遵循“持仓快照优先、数据不全绝不补 Wind”的主数据解析器。"""

    def __init__(self, wind_provider: BondMasterProvider) -> None:
        self._wind_provider = wind_provider

    def master_session(self) -> ContextManager[None]:
        """把一次试算里全部 Wind 取数收进同一个外部会话。"""

        session = getattr(self._wind_provider, "master_session", None)
        return session() if callable(session) else nullcontext()

    def resolve(
        self, inputs: ProductionKernelInput, bond_code: str
    ) -> MasterResolution:
        normalized_code = _normalize_code(bond_code)
        if normalized_code is None:
            return _missing_snapshot("债券代码为空或非法")
        if not isinstance(inputs, ProductionKernelInput):
            raise TypeError("inputs 必须是 ProductionKernelInput")

        frames = inputs.frames
        frame = frames.get(_HELD_POSITION_DATASET)
        if frame is None or not isinstance(frame, pd.DataFrame):
            return _missing_snapshot("持仓快照缺少信用债原始持仓")
        available_code_columns = [column for column in _CODE_COLUMNS if column in frame]
        if not available_code_columns:
            return _missing_snapshot("持仓快照缺少可用债券代码列")

        matched = pd.Series(False, index=frame.index)
        for column in available_code_columns:
            matched |= normalize_security_code_series(frame[column]) == normalized_code
        held_rows = frame.loc[matched].copy()
        if held_rows.empty:
            result = self._wind_provider.resolve(normalized_code, inputs.business_date)
            if result.master is None:
                return result
            missing = missing_required_bond_master_fields(result.master, require_controller=False)
            if missing:
                return MasterResolution(
                    MasterSource.MISSING_MASTER,
                    None,
                    f"Wind 主数据缺少必填字段: {', '.join(missing)}",
                )
            return _with_snapshot_controller(result, frames.get("调整实控人名单"), frame)
        if "资产代码" in held_rows:
            exact_asset = (
                normalize_security_code_series(held_rows["资产代码"])
                == normalized_code
            )
            if exact_asset.any():
                held_rows = held_rows.loc[exact_asset].copy()
        return _with_snapshot_controller(
            _master_from_held_rows(normalized_code, held_rows), frames.get("调整实控人名单"), held_rows
        )


def _with_snapshot_controller(
    result: MasterResolution,
    adjustments: pd.DataFrame | None,
    positions: pd.DataFrame,
) -> MasterResolution:
    """仅为拟买行解析实控人，复用原有持仓修正规则，不改动日常输入。"""
    master = result.master
    if master is None or master.bond_classification == "利率债":
        return result

    # 持仓券使用本券底稿；非持仓券可继承同主体已在快照中的底稿修正值。
    issuer_key = str(master.issuer_wind_code).strip().split(".")[0]
    issuer_codes = positions.get(
        "债务主体wind代码", pd.Series(None, index=positions.index, dtype=object)
    )
    matched = issuer_codes.astype(str).str.strip().str.split(".").str[0].eq(issuer_key)
    columns = ["资产代码", "债务主体wind代码", "实际控制人名称", "实际控制人名称_修正"]
    rows = positions.loc[matched].reindex(columns=columns).copy()
    if rows.empty:
        rows = pd.DataFrame([{
            "资产代码": master.input_code,
            "债务主体wind代码": master.issuer_wind_code,
            "实际控制人名称": None,
            "实际控制人名称_修正": None,
        }])
    rows["内部证券账户名称"] = ""
    rows["库存数量(万)_PR"] = 0.0
    frames = {
        "债券持仓明细表_信用债": rows,
        "穿透高收益债券": pd.DataFrame(columns=["债券代码", "类型"]),
    }
    if adjustments is not None and {"主体wind代码", "调整后实际控制人"}.issubset(adjustments.columns):
        frames["调整实控人名单"] = adjustments
    try:
        context = build_credit_risk_context(frames)
    except (KeyError, ValueError) as exc:
        return replace(result, source=MasterSource.MISSING_SNAPSHOT, master=None,
                       reason=f"试算实控人无法按持仓口径解析: {exc}")
    names = _distinct_values(context["实际控制人名称_修正"].tolist())
    if len(names) != 1:
        reason = ("快照中同主体实控人存在冲突记录" if names else
                  "快照调整实控人名单及持仓底稿均无可用实控人")
        return replace(result, source=MasterSource.MISSING_SNAPSHOT, master=None, reason=reason)
    master = replace(master, controller_name=_as_optional_text(names[0]))
    missing = missing_required_bond_master_fields(master)
    if missing:
        return replace(result, source=MasterSource.MISSING_SNAPSHOT, master=None,
                       reason=f"主数据缺少必填字段: {', '.join(missing)}")
    return replace(result, master=master)


def _master_from_held_rows(
    input_code: str, held_rows: pd.DataFrame
) -> MasterResolution:
    values: dict[str, Any | None] = {}
    for attribute, candidates in _MASTER_COLUMNS.items():
        # 候选列是生产口径的优先级链，并非需相互一致的多份同义数据。
        distinct: list[Any] = []
        for column in candidates:
            if column not in held_rows:
                continue
            observed = [
                value
                for value in held_rows[column].tolist()
                if _clean_value(value) is not None
            ]
            if attribute == "main_security_code":
                observed = normalize_security_code_series(
                    pd.Series(observed, dtype="object")
                ).dropna().tolist()
            distinct = _distinct_values(observed)
            if distinct:
                break
        if len(distinct) > 1:
            return _missing_snapshot(f"持仓快照主数据矛盾: {attribute}")
        values[attribute] = distinct[0] if distinct else None

    try:
        master = BondMaster(
            input_code=input_code,
            main_security_code=_as_required_text(values["main_security_code"]),
            isin_code=_as_optional_text(values["isin_code"]),
            bond_name=_as_required_text(values["bond_name"]),
            issuer_name=_as_required_text(values["issuer_name"]),
            issuer_wind_code=_as_optional_text(values["issuer_wind_code"]),
            controller_name=None,  # 由原有持仓修正规则解析后执行完整校验。
            guarantor_name=_as_optional_text(values["guarantor_name"]),
            guarantor_wind_code=_as_optional_text(values["guarantor_wind_code"]),
            outstanding_balance_yi=_as_optional_finite_float(
                values["outstanding_balance_yi"]
            ),
            bond_classification=_as_optional_text(values["bond_classification"]),
            bond_type=_as_optional_text(values["bond_type"]),
            issuer_type=_as_optional_text(values["issuer_type"]),
            is_city_investment_bond=_as_optional_text(
                values["is_city_investment_bond"]
            ),
            bond_category=_as_optional_text(values["bond_category"]),
            wind_industry=_as_optional_text(values["wind_industry"]),
            province=_as_optional_text(values["province"]),
            asset_name=_as_required_text(values["asset_name"]),
            main_security_name=_as_required_text(values["main_security_name"]),
        )
    except (TypeError, ValueError) as exc:
        return _missing_snapshot(f"持仓快照主数据规范化失败: {exc}")
    missing = missing_required_bond_master_fields(master, require_controller=False)
    if missing:
        return _missing_snapshot(f"持仓快照主数据缺少必填字段: {', '.join(missing)}")
    return MasterResolution(MasterSource.SNAPSHOT, master, None)


def _missing_snapshot(reason: str) -> MasterResolution:
    return MasterResolution(MasterSource.MISSING_SNAPSHOT, None, reason)


def _normalize_code(value: object) -> str | None:
    if _clean_value(value) is None:
        return None
    return str(value).strip().upper()


def _clean_value(value: Any) -> Any | None:
    if value is None:
        return None
    if isinstance(value, float) and isnan(value):
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return None if stripped.lower() in {"", "nan", "none", "null", "nat"} else stripped
    return value


def _distinct_values(values: list[Any]) -> list[Any]:
    result: list[Any] = []
    seen: set[tuple[type[Any], str]] = set()
    for value in values:
        normalized = _clean_value(value)
        if normalized is None:
            continue
        key = (type(normalized), str(normalized).strip())
        if key not in seen:
            result.append(normalized)
            seen.add(key)
    return result


def _as_required_text(value: Any | None) -> str:
    text = _as_optional_text(value)
    if text is None:
        raise ValueError("文本字段为空")
    return text


def _as_optional_text(value: Any | None) -> str | None:
    value = _clean_value(value)
    return str(value).strip() if value is not None else None


def _as_optional_finite_float(value: Any | None) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("数值字段不是数字") from exc
    if not isfinite(numeric):
        raise ValueError("数值字段不是有限数")
    return numeric
