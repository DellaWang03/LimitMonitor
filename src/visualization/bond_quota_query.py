"""
单券可购额度查询模块。

设计目标：
1. 支持全量债券查询；
2. 明确区分账户级约束与债券级公共约束；
3. 关键数据源异常时显式失败，避免把缺数伪装成“不适用”。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

import pandas as pd

from src.common.security_code_normalizer import normalize_security_code_series
from src.visualization.code_utils import clean_code_like_value


DIMENSION_MAPPING: List[tuple[str, str, str]] = [
    ("单一债券规模", "单一债券规模剩余额度(万)", "单一债券是否超限"),
    ("单一债券集中度", "单一债券集中度剩余额度(万)", "单一债券集中度是否超限"),
    ("监管集中度", "监管集中度剩余额度(万)", "监管集中度是否超限"),
    ("单一主体规模", "单一主体规模剩余额度(万)", "单一主体是否超限"),
    ("单一实控人规模", "单一实控人规模剩余额度(万)", "单一实控人是否超限"),
    ("单一担保公司规模", "单一担保公司规模剩余额度(万)", "单一担保人是否超限"),
    ("特定主体限额", "特定主体限额剩余额度", "特定主体限额是否超限"),
    ("特定实控人限额", "特定实控人限额剩余额度", "特定实控人限额是否超限"),
    ("地域集中度", "地域集中度剩余额度(万)", "地域集中度是否超限"),
    ("城投集中度", "城投集中度剩余额度(万)", "城投集中度是否超限"),
    ("高风险行业集中度", "高风险行业集中度剩余额度(万)", "高风险行业是否超限"),
    ("高风险省份集中度", "高风险省份集中度剩余额度(万)", "高风险省份是否超限"),
    ("高收益年度限额", "高收益年度限额剩余额度(万)", "高收益年度限额是否超限"),
    ("高收益单债限额", "高收益单债剩余额度(万)", "高收益单债是否超限"),
    ("高收益主体限额", "高收益主体剩余额度(万)", "高收益主体是否超限"),
]

MERGE_KEYS = ["日期", "资产代码", "内部证券账户名称"]
LOOKUP_INFO_COLUMNS = [
    "日期",
    "资产代码",
    "代码",
    "资产名称",
    "债务主体",
    "内部证券账户名称",
    "库存数量(万)_PR",
]

ACCOUNT_CONSTRAINT_SPECS = {
    "credit_1_2": [
        {"name": "单一债券规模", "remaining": "单一债券规模剩余额度(万)", "overlimit": "单一债券是否超限"},
        {"name": "单一债券集中度", "remaining": "单一债券集中度剩余额度(万)", "overlimit": "单一债券集中度是否超限"},
        {"name": "单一主体规模", "remaining": "单一主体规模剩余额度(万)", "overlimit": "单一主体是否超限"},
        {"name": "单一实控人规模", "remaining": "单一实控人规模剩余额度(万)", "overlimit": "单一实控人是否超限"},
        {"name": "单一担保公司规模", "remaining": "单一担保公司规模剩余额度(万)", "overlimit": "单一担保人是否超限"},
    ],
    "credit_1_1": [
        {"name": "特定主体限额", "remaining": "特定主体限额剩余额度", "overlimit": "特定主体限额是否超限"},
        {"name": "特定实控人限额", "remaining": "特定实控人限额剩余额度", "overlimit": "特定实控人限额是否超限"},
    ],
    "credit_2": [
        {"name": "地域集中度", "remaining": "地域集中度剩余额度(万)", "overlimit": "地域集中度是否超限"},
        {"name": "城投集中度", "remaining": "城投集中度剩余额度(万)", "overlimit": "城投集中度是否超限"},
        {"name": "高风险行业集中度", "remaining": "高风险行业集中度剩余额度(万)", "overlimit": "高风险行业是否超限"},
        {"name": "高风险省份集中度", "remaining": "高风险省份集中度剩余额度(万)", "overlimit": "高风险省份是否超限"},
    ],
}

BOND_CONSTRAINT_SPECS = {
    "full_reg": [
        {"name": "监管集中度", "remaining": "监管集中度剩余额度(万)", "overlimit": "监管集中度是否超限"},
    ],
    "high_yield": [
        {"name": "高收益年度限额", "remaining": "高收益年度限额剩余额度(万)", "overlimit": "高收益年度限额是否超限"},
        {"name": "高收益单债限额", "remaining": "高收益单债剩余额度(万)", "overlimit": "高收益单债是否超限"},
        {"name": "高收益主体限额", "remaining": "高收益主体剩余额度(万)", "overlimit": "高收益主体是否超限"},
    ],
}

REQUIRED_CONSTRAINT_DIMENSIONS = {
    "credit_1_2": {"单一债券规模", "单一债券集中度", "单一主体规模"},
    "credit_1_1": set(),
    "credit_2": {"地域集中度"},
    "full_reg": {"监管集中度"},
}

DATAFRAME_SOURCES = [
    ("credit_1_1", "信用债1_1", "load_stage1_credit_1_1"),
    ("credit_1_2", "信用债1_2", "load_stage1_credit_1_2"),
    ("credit_2", "信用债2", "load_stage2_credit_2"),
    ("full_reg", "全量债券监管集中度", "load_stage1_full_regulatory_concentration"),
    ("high_yield", "高收益明细", "load_stage2_high_yield"),
]

LOOKUP_SEARCH_COLUMNS = ["资产代码", "代码", "主证券代码_标准", "主证券代码", "ISIN码"]
ASSET_CODE_NORM_COL = "_资产代码_norm"
MAIN_CODE_NORM_COL = "_主证券代码_norm"
ISIN_NORM_COL = "_ISIN_norm"
ENTITY_KEY_COL = "_entity_key"
ENTITY_KEY_TYPE_COL = "_entity_key_type"


def _normalize_date(d: Any) -> Any:
    """统一为可比较的日期类型。"""
    if d is None:
        return d
    if isinstance(d, pd.Timestamp):
        return d.normalize() if hasattr(d, "normalize") else d
    return pd.Timestamp(d).normalize()


def _clean_text(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def _coerce_float(value: Any) -> Optional[float]:
    if pd.isna(value) or type(value).__name__ == "NAType":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pick_first_non_empty(series: pd.Series) -> Any:
    for value in series:
        if pd.notna(value) and _clean_text(value):
            return value
    return None


def _pick_first_float(series: pd.Series) -> Optional[float]:
    for value in series:
        numeric_value = _coerce_float(value)
        if numeric_value is not None:
            return numeric_value
    return None


def _has_numeric_value(series: pd.Series) -> bool:
    return bool(pd.to_numeric(series, errors="coerce").notna().any())


def _clean_code_text(value: Any) -> Optional[str]:
    return clean_code_like_value(value)


def _normalize_search_token(value: Any) -> str:
    cleaned = _clean_code_text(value)
    if cleaned is None:
        return ""
    normalized = cleaned.upper()
    return normalized[:-2] if normalized.endswith(".0") else normalized


def _normalize_main_code_value(value: Any) -> Optional[str]:
    normalized = normalize_security_code_series(pd.Series([value])).iloc[0]
    return normalized if isinstance(normalized, str) and normalized else None


def _build_entity_key(main_code: Optional[str], isin_code: Optional[str], asset_code: Optional[str]) -> Optional[str]:
    if main_code:
        return f"MAIN::{main_code}"
    if isin_code:
        return f"ISIN::{isin_code}"
    if asset_code:
        return f"ASSET::{asset_code}"
    return None


def _prepare_identifier_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()

    result = df.copy()

    if "资产代码" in result.columns:
        result["资产代码"] = result["资产代码"].apply(_clean_code_text)
        result[ASSET_CODE_NORM_COL] = result["资产代码"].apply(_normalize_search_token)
    else:
        result[ASSET_CODE_NORM_COL] = ""

    if "主证券代码_标准" in result.columns:
        result["主证券代码_标准"] = result["主证券代码_标准"].apply(_normalize_main_code_value)
    elif "主证券代码" in result.columns:
        result["主证券代码_标准"] = normalize_security_code_series(result["主证券代码"])
    else:
        result["主证券代码_标准"] = None
    result[MAIN_CODE_NORM_COL] = result["主证券代码_标准"].apply(_normalize_main_code_value)

    if "ISIN码" in result.columns:
        result["ISIN码"] = result["ISIN码"].apply(_clean_code_text)
    else:
        result["ISIN码"] = None
    result[ISIN_NORM_COL] = result["ISIN码"].apply(
        lambda value: value.upper() if isinstance(value, str) and value else None
    )

    if "代码" in result.columns:
        result["代码"] = result["代码"].apply(_clean_code_text)
    elif "资产代码" in result.columns:
        result["代码"] = result["ISIN码"].combine_first(result["资产代码"])

    return result


def _build_asset_entity_map(
    frames: List[pd.DataFrame],
    data_health: Dict[str, Any],
) -> Dict[str, Dict[str, str]]:
    records: List[Dict[str, str]] = []
    for frame in frames:
        if frame.empty or "资产代码" not in frame.columns:
            continue
        cols = [ASSET_CODE_NORM_COL, MAIN_CODE_NORM_COL, ISIN_NORM_COL]
        subset = frame[[col for col in cols if col in frame.columns]].copy()
        if ASSET_CODE_NORM_COL not in subset.columns:
            continue
        subset = subset[subset[ASSET_CODE_NORM_COL] != ""]
        if subset.empty:
            continue
        records.extend(subset.to_dict(orient="records"))

    if not records:
        return {}

    mapping: Dict[str, Dict[str, str]] = {}
    grouped = pd.DataFrame(records).groupby(ASSET_CODE_NORM_COL, dropna=False)
    for asset_code, group in grouped:
        asset_code = _clean_text(asset_code)
        if not asset_code:
            continue

        main_codes = sorted({value for value in group.get(MAIN_CODE_NORM_COL, pd.Series(dtype="object")) if isinstance(value, str) and value})
        isins = sorted({value for value in group.get(ISIN_NORM_COL, pd.Series(dtype="object")) if isinstance(value, str) and value})

        if len(main_codes) > 1:
            data_health["warnings"].append(
                f"资产代码 {asset_code} 映射到多个主证券代码，按首个主证券代码归一。"
            )
        if not main_codes and len(isins) > 1:
            data_health["warnings"].append(
                f"资产代码 {asset_code} 映射到多个 ISIN，按首个 ISIN 归一。"
            )

        main_code = main_codes[0] if main_codes else None
        isin_code = isins[0] if isins else None
        entity_key = _build_entity_key(main_code, isin_code, asset_code)
        if not entity_key:
            continue

        mapping[asset_code] = {
            "entity_key": entity_key,
            "key_type": "主证券代码" if main_code else ("ISIN" if isin_code else "资产代码"),
        }

    fallback_count = sum(1 for item in mapping.values() if item["key_type"] == "资产代码")
    if fallback_count:
        data_health["warnings"].append(
            f"当前快照有 {fallback_count} 只债券缺少主证券代码与 ISIN，已退回资产代码归一。"
        )
    return mapping


def _attach_entity_key(
    df: pd.DataFrame,
    asset_entity_map: Dict[str, Dict[str, str]],
) -> pd.DataFrame:
    if df.empty:
        return df.copy()

    result = _prepare_identifier_columns(df)
    entity_keys: List[Optional[str]] = []
    key_types: List[str] = []
    for _, row in result.iterrows():
        asset_code = _clean_text(row.get(ASSET_CODE_NORM_COL))
        main_code = _clean_text(row.get(MAIN_CODE_NORM_COL))
        isin_code = _clean_text(row.get(ISIN_NORM_COL))

        if main_code:
            entity_keys.append(_build_entity_key(main_code, None, asset_code))
            key_types.append("主证券代码")
            continue
        if isin_code:
            entity_keys.append(_build_entity_key(None, isin_code, asset_code))
            key_types.append("ISIN")
            continue

        mapped = asset_entity_map.get(asset_code)
        if mapped:
            entity_keys.append(mapped["entity_key"])
            key_types.append(mapped["key_type"])
            continue

        entity_keys.append(_build_entity_key(None, None, asset_code))
        key_types.append("资产代码")

    result[ENTITY_KEY_COL] = entity_keys
    result[ENTITY_KEY_TYPE_COL] = key_types
    return result


def _new_data_health() -> Dict[str, Any]:
    return {
        "errors": [],
        "warnings": [],
        "loaded_sources": [],
        "failed_sources": [],
    }


def _empty_query_result(
    *,
    error: Optional[str] = None,
    message: Optional[str] = None,
    candidates: Optional[List[Dict[str, Any]]] = None,
    data_health: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "bond_info": {},
        "common_bond_info": {},
        "dimensions": [],
        "account_results": [],
        "account_summary": [],
        "bond_level_result": None,
        "public_dimensions": [],
        "final_quota_wan": 0.0,
        "selected_account_name": None,
        "matched_account_count": 0,
        "result_scope": "unknown",
        "data_health": data_health or _new_data_health(),
        "error": error,
        "message": message,
        "candidates": candidates or [],
    }


def _normalize_overlimit_flag(value: Any) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    if text in {"是", "否", "不适用"}:
        return text
    return text


def _is_yes_flag(value: Any) -> bool:
    return _clean_text(value) == "是"


def _filter_non_high_yield_credit_rows(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()

    result = df.copy()
    if "是否属于高收益" in result.columns:
        result = result[~result["是否属于高收益"].apply(_is_yes_flag)].copy()
    if "内部证券账户名称" in result.columns:
        account_text = result["内部证券账户名称"].astype(str)
        result = result[~account_text.str.contains("高收益", na=False)].copy()
    return result


def _has_high_yield_indicator_rows(df: pd.DataFrame) -> bool:
    if df.empty:
        return False

    mask = pd.Series(False, index=df.index)
    for flag_col in ["是否属于高收益", "是否高收益"]:
        if flag_col in df.columns:
            mask |= df[flag_col].apply(_is_yes_flag)
    if "内部证券账户名称" in df.columns:
        mask |= df["内部证券账户名称"].astype(str).str.contains("高收益", na=False)
    return bool(mask.any())


def _is_high_yield_data_error(data_health: Dict[str, Any]) -> bool:
    return any("高收益" in _clean_text(item) for item in data_health.get("errors", []))


def _find_regulatory_not_calculable_reason(full_reg_df: pd.DataFrame) -> Optional[str]:
    if full_reg_df.empty or "是否可计算" not in full_reg_df.columns:
        return None

    calculable_mask = full_reg_df["是否可计算"].apply(_is_yes_flag)
    not_calculable_df = full_reg_df[~calculable_mask].copy()
    if not_calculable_df.empty:
        return None

    if "不可计算原因" in not_calculable_df.columns:
        reason = _pick_first_non_empty(not_calculable_df["不可计算原因"])
        if reason:
            return _clean_text(reason)
    return "原因未注明"


def _load_dataframe_source(
    data_loader,
    source_key: str,
    source_label: str,
    method_name: str,
    data_health: Dict[str, Any],
) -> pd.DataFrame:
    loader = getattr(data_loader, method_name, None)
    if loader is None:
        message = f"{source_label}数据源不可用：缺少 {method_name}()"
        data_health["errors"].append(message)
        data_health["failed_sources"].append({"source": source_key, "label": source_label, "error": message})
        return pd.DataFrame()

    try:
        df = loader()
    except Exception as exc:  # noqa: BLE001 - 风控页这里需要把真实失败面向用户暴露出来
        message = f"{source_label}加载失败：{exc}"
        data_health["errors"].append(message)
        data_health["failed_sources"].append({"source": source_key, "label": source_label, "error": message})
        return pd.DataFrame()

    if not isinstance(df, pd.DataFrame):
        message = f"{source_label}加载结果不是 DataFrame"
        data_health["errors"].append(message)
        data_health["failed_sources"].append({"source": source_key, "label": source_label, "error": message})
        return pd.DataFrame()

    data_health["loaded_sources"].append({
        "source": source_key,
        "label": source_label,
        "rows": int(len(df)),
    })
    return df.copy()


def _load_value_source(
    data_loader,
    source_key: str,
    source_label: str,
    method_name: str,
    data_health: Dict[str, Any],
) -> Any:
    loader = getattr(data_loader, method_name, None)
    if loader is None:
        message = f"{source_label}不可用：缺少 {method_name}()"
        data_health["errors"].append(message)
        data_health["failed_sources"].append({"source": source_key, "label": source_label, "error": message})
        return None

    try:
        value = loader()
    except Exception as exc:  # noqa: BLE001 - 同上，关键配置不应静默降级
        message = f"{source_label}加载失败：{exc}"
        data_health["errors"].append(message)
        data_health["failed_sources"].append({"source": source_key, "label": source_label, "error": message})
        return None

    data_health["loaded_sources"].append({"source": source_key, "label": source_label, "rows": None})
    return value


def _get_query_date(
    target_date: Optional[Any],
    frames: List[pd.DataFrame],
) -> Optional[pd.Timestamp]:
    if target_date is not None:
        return _normalize_date(target_date)

    normalized_dates: List[pd.Timestamp] = []
    for df in frames:
        if df.empty or "日期" not in df.columns:
            continue
        normalized_dates.append(_normalize_date(df["日期"].max()))

    if not normalized_dates:
        return None
    return max(normalized_dates)


def _filter_frame_by_query_date(
    df: pd.DataFrame,
    query_date: Optional[pd.Timestamp],
) -> pd.DataFrame:
    if df.empty or query_date is None or "日期" not in df.columns:
        return df.copy()

    result = df.copy()
    result["_日期_norm"] = result["日期"].apply(_normalize_date)
    return result[result["_日期_norm"] == query_date].copy()


def _filter_frame_by_code(
    df: pd.DataFrame,
    resolved_code: str,
) -> pd.DataFrame:
    if df.empty or "资产代码" not in df.columns:
        return df.copy()

    result = df.copy()
    result["_代码_str"] = result["资产代码"].astype(str).str.strip()
    return result[result["_代码_str"] == resolved_code].copy()


def _filter_frame_by_entity(
    df: pd.DataFrame,
    entity_key: str,
) -> pd.DataFrame:
    if df.empty or ENTITY_KEY_COL not in df.columns:
        return df.copy()

    result = df.copy()
    return result[result[ENTITY_KEY_COL] == entity_key].copy()


def _prepare_lookup_frame(
    df: pd.DataFrame,
    query_date: Optional[pd.Timestamp],
) -> pd.DataFrame:
    filtered = _filter_frame_by_query_date(df, query_date)
    cols = []
    for col in LOOKUP_INFO_COLUMNS + LOOKUP_SEARCH_COLUMNS + [ENTITY_KEY_COL]:
        if col in filtered.columns and col not in cols:
            cols.append(col)
    if not cols:
        return pd.DataFrame()
    return filtered[cols].copy().drop_duplicates()


def _prepare_base_frame(
    df: pd.DataFrame,
    query_date: Optional[pd.Timestamp],
    entity_key: str,
) -> pd.DataFrame:
    filtered = _filter_frame_by_entity(_filter_frame_by_query_date(df, query_date), entity_key)
    if "库存数量(万)_PR" not in filtered.columns and "单债总持仓_PR" in filtered.columns:
        filtered["库存数量(万)_PR"] = filtered["单债总持仓_PR"]
    cols = [col for col in LOOKUP_INFO_COLUMNS if col in filtered.columns]
    if not cols:
        return pd.DataFrame(columns=MERGE_KEYS)

    result = filtered[cols].copy()
    for key in MERGE_KEYS:
        if key not in result.columns:
            result[key] = None
    return result


def _collapse_base_frames(frames: List[pd.DataFrame]) -> pd.DataFrame:
    valid_frames = [frame for frame in frames if not frame.empty]
    if not valid_frames:
        return pd.DataFrame(columns=MERGE_KEYS)

    combined = pd.concat(valid_frames, ignore_index=True)
    for key in MERGE_KEYS:
        if key not in combined.columns:
            combined[key] = None

    value_cols = [
        col for col in LOOKUP_INFO_COLUMNS
        if col in combined.columns and col not in MERGE_KEYS
    ]
    if not value_cols:
        return combined[MERGE_KEYS].drop_duplicates().reset_index(drop=True)

    aggregation = {col: _pick_first_non_empty for col in value_cols}
    return (
        combined
        .groupby(MERGE_KEYS, dropna=False, as_index=False)
        .agg(aggregation)
    )


def _build_candidate_rows(df: pd.DataFrame) -> List[Dict[str, Any]]:
    if df.empty:
        return []

    cols = [c for c in ["资产代码", "代码", "资产名称", "债务主体", "主证券代码_标准", "ISIN码"] if c in df.columns]
    candidate_df = df[[ENTITY_KEY_COL] + cols].copy() if ENTITY_KEY_COL in df.columns and cols else df[cols].copy() if cols else pd.DataFrame()
    if ENTITY_KEY_COL in candidate_df.columns:
        aggregation = {col: _pick_first_non_empty for col in cols}
        candidate_df = (
            candidate_df.groupby(ENTITY_KEY_COL, dropna=False, as_index=False)
            .agg(aggregation)
        )
    if "资产代码" in candidate_df.columns:
        candidate_df["资产代码"] = candidate_df["资产代码"].astype(str).str.strip()
    candidate_df = candidate_df[cols].drop_duplicates().head(10)
    return candidate_df.to_dict(orient="records")


def _resolve_bond_rows(
    df: pd.DataFrame,
    raw: str,
) -> tuple[Optional[pd.DataFrame], Optional[str], Optional[List[Dict[str, Any]]]]:
    """
    在目标日期数据内解析债券。

    顺序：
    1. 资产代码精确匹配（兼容尾随 .0）
    2. 资产名称精确匹配
    3. 资产名称包含匹配
    """
    if "资产代码" not in df.columns or ENTITY_KEY_COL not in df.columns:
        return None, "数据中无可用于识别债券的字段", None

    raw_norm = _normalize_search_token(raw)
    for column in LOOKUP_SEARCH_COLUMNS:
        if column not in df.columns:
            continue
        token_series = df[column].apply(_normalize_search_token)
        exact_df = df[token_series == raw_norm].copy()
        if exact_df.empty:
            continue

        entity_count = exact_df[ENTITY_KEY_COL].nunique(dropna=True)
        if entity_count > 1:
            return None, "匹配到多只债券，请输入更精确的债券代码或全称。", _build_candidate_rows(exact_df)
        resolved_entity_key = _pick_first_non_empty(exact_df[ENTITY_KEY_COL])
        return df[df[ENTITY_KEY_COL] == resolved_entity_key].copy(), _clean_text(resolved_entity_key), None

    if "资产名称" not in df.columns:
        return None, "未找到该债券", None

    name_series = df["资产名称"].astype(str).str.strip()
    exact_name_df = df[name_series == raw].copy()
    if not exact_name_df.empty:
        entity_count = exact_name_df[ENTITY_KEY_COL].nunique(dropna=True)
        if entity_count > 1:
            return None, "匹配到多只同名债券，请输入更精确的债券代码。", _build_candidate_rows(exact_name_df)
        resolved_entity_key = _pick_first_non_empty(exact_name_df[ENTITY_KEY_COL])
        return df[df[ENTITY_KEY_COL] == resolved_entity_key].copy(), _clean_text(resolved_entity_key), None

    contains_df = df[name_series.str.contains(raw, na=False, case=False, regex=False)].copy()
    if contains_df.empty:
        return None, "未找到该债券", None

    entity_count = contains_df[ENTITY_KEY_COL].nunique(dropna=True)
    if entity_count > 1:
        return None, "匹配到多只债券，请输入更精确的债券代码或全称。", _build_candidate_rows(contains_df)

    resolved_entity_key = _pick_first_non_empty(contains_df[ENTITY_KEY_COL])
    return df[df[ENTITY_KEY_COL] == resolved_entity_key].copy(), _clean_text(resolved_entity_key), None


def _build_constraints_from_frame(
    df: pd.DataFrame,
    specs: List[Dict[str, str]],
    *,
    scope_type: str,
    scope_name: str,
    source_name: str,
    required_dimension_names: Optional[Set[str]] = None,
) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    if df.empty:
        return pd.DataFrame()

    required_dimension_names = required_dimension_names or set()
    for _, row in df.iterrows():
        current_scope_name = scope_name
        if scope_type == "account":
            current_scope_name = _clean_text(row.get("内部证券账户名称")) or "未识别账户"

        for spec in specs:
            remaining = _coerce_float(row.get(spec["remaining"]))
            overlimit_flag = _normalize_overlimit_flag(row.get(spec["overlimit"]))
            if remaining is None and spec["name"] in required_dimension_names and overlimit_flag != "是":
                rows.append(
                    {
                        "scope_type": scope_type,
                        "scope_name": current_scope_name,
                        "dimension_name": spec["name"],
                        "remaining_wan": None,
                        "overlimit_flag": "不可计算",
                        "source_name": source_name,
                    }
                )
                continue
            if remaining is None and overlimit_flag in {"", "不适用"}:
                continue

            if not overlimit_flag and remaining is not None:
                overlimit_flag = "是" if remaining < 0 else "否"

            rows.append(
                {
                    "scope_type": scope_type,
                    "scope_name": current_scope_name,
                    "dimension_name": spec["name"],
                    "remaining_wan": remaining,
                    "overlimit_flag": overlimit_flag or "不适用",
                    "source_name": source_name,
                }
            )

    return pd.DataFrame(rows)


def _build_validated_constraints_from_frame(
    df: pd.DataFrame,
    specs: List[Dict[str, str]],
    *,
    scope_type: str,
    scope_name: str,
    source_name: str,
    data_health: Dict[str, Any],
    required_dimension_names: Optional[Set[str]] = None,
) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    if required_dimension_names is None:
        required_dimension_names = {spec["name"] for spec in specs}
    available_specs = [spec for spec in specs if spec["remaining"] in df.columns]
    missing_specs = [
        spec
        for spec in specs
        if spec["remaining"] not in df.columns and spec["name"] in required_dimension_names
    ]
    warning_dimensions = []
    for spec in missing_specs:
        warning_dimensions.append(f"{spec['name']}（缺少 {spec['remaining']}）")
    for spec in available_specs:
        if spec["name"] not in required_dimension_names:
            continue
        has_blank_required_value = False
        for _, row in df.iterrows():
            remaining = _coerce_float(row.get(spec["remaining"]))
            overlimit_flag = _normalize_overlimit_flag(row.get(spec["overlimit"]))
            if remaining is None and overlimit_flag != "是":
                has_blank_required_value = True
                break
        if has_blank_required_value:
            warning_dimensions.append(f"{spec['name']}（{spec['remaining']} 为空，无法计算剩余额度）")
    for spec in available_specs:
        if spec["overlimit"] not in df.columns:
            data_health["warnings"].append(
                f"{source_name}{spec['name']}缺少 {spec['overlimit']}，已按剩余额度推导是否超限。"
            )
    if warning_dimensions:
        data_health["warnings"].append(
            f"{source_name}部分维度不可计算：" + "、".join(warning_dimensions)
        )

    constraint_df = _build_constraints_from_frame(
        df,
        available_specs,
        scope_type=scope_type,
        scope_name=scope_name,
        source_name=source_name,
        required_dimension_names=required_dimension_names,
    )
    if not missing_specs:
        return constraint_df

    rows: List[Dict[str, Any]] = []
    for _, row in df.iterrows():
        current_scope_name = scope_name
        if scope_type == "account":
            current_scope_name = _clean_text(row.get("内部证券账户名称")) or "未识别账户"
        for spec in missing_specs:
            rows.append(
                {
                    "scope_type": scope_type,
                    "scope_name": current_scope_name,
                    "dimension_name": spec["name"],
                    "remaining_wan": None,
                    "overlimit_flag": "不可计算",
                    "source_name": source_name,
                }
            )

    missing_df = pd.DataFrame(rows)
    if constraint_df.empty:
        return missing_df
    return pd.concat([constraint_df, missing_df], ignore_index=True)


def _build_high_yield_constraints(
    data_loader,
    df_hy_date: pd.DataFrame,
    entity_key: str,
    query_date: Optional[pd.Timestamp],
    data_health: Dict[str, Any],
) -> pd.DataFrame:
    if df_hy_date.empty:
        return pd.DataFrame()

    df_hy_filtered = _filter_frame_by_entity(df_hy_date, entity_key)
    if df_hy_filtered.empty:
        return pd.DataFrame()

    df_capital = _load_value_source(
        data_loader,
        "high_yield_capital",
        "高收益投资本金规模",
        "load_stage2_high_yield_capital",
        data_health,
    )
    if data_health["errors"]:
        return pd.DataFrame()

    if not isinstance(df_capital, pd.DataFrame):
        data_health["errors"].append("高收益投资本金规模加载结果不是 DataFrame")
        return pd.DataFrame()
    df_capital = _filter_frame_by_query_date(df_capital, query_date)

    result_row: Dict[str, Any] = {
        "scope_type": "bond",
        "scope_name": "债券级结果",
        "source_name": "高收益限额",
    }

    annual_remaining_wan = None
    if "高收益年度限额剩余额度(万)" in df_capital.columns:
        annual_remaining_wan = _pick_first_float(df_capital["高收益年度限额剩余额度(万)"])
    if annual_remaining_wan is not None:
        result_row["高收益年度限额剩余额度(万)"] = annual_remaining_wan
        if "高收益年度限额是否超限" in df_capital.columns:
            result_row["高收益年度限额是否超限"] = _pick_first_non_empty(df_capital["高收益年度限额是否超限"])
    else:
        if df_capital.empty:
            data_health["errors"].append("高收益投资本金规模缺失：目标日期无可用数据，无法计算高收益年度限额。")
            return pd.DataFrame()
        if "全价成本(元)" not in df_capital.columns:
            data_health["errors"].append("高收益投资本金规模缺少 全价成本(元)，无法计算高收益年度限额。")
            return pd.DataFrame()
        capital_cost = pd.to_numeric(df_capital["全价成本(元)"], errors="coerce")
        if capital_cost.empty or capital_cost.isna().any():
            data_health["errors"].append("高收益投资本金规模 全价成本(元) 存在空值或非法值，无法计算高收益年度限额。")
            return pd.DataFrame()

        annual_limit = _load_value_source(
            data_loader,
            "high_yield_annual_limit",
            "高收益年度限额配置",
            "load_high_yield_annual_limit",
            data_health,
        )
        if data_health["errors"]:
            return pd.DataFrame()

        total_capital_wan = float(capital_cost.sum()) / 10000
        annual_remaining_wan = float(annual_limit) - total_capital_wan
        result_row["高收益年度限额剩余额度(万)"] = annual_remaining_wan
        result_row["高收益年度限额是否超限"] = "是" if annual_remaining_wan < 0 else "否"

    has_persisted_detail = all(
        col in df_hy_filtered.columns
        for col in [
            "高收益单债剩余额度(万)", "高收益单债是否超限",
            "高收益主体剩余额度(万)", "高收益主体是否超限",
        ]
    )
    has_usable_persisted_detail = (
        has_persisted_detail
        and _has_numeric_value(df_hy_filtered["高收益单债剩余额度(万)"])
        and _has_numeric_value(df_hy_filtered["高收益主体剩余额度(万)"])
    )
    if has_usable_persisted_detail:
        result_row["高收益单债剩余额度(万)"] = _pick_first_float(
            df_hy_filtered["高收益单债剩余额度(万)"]
        )
        result_row["高收益单债是否超限"] = _pick_first_non_empty(
            df_hy_filtered["高收益单债是否超限"]
        )
        result_row["高收益主体剩余额度(万)"] = _pick_first_float(
            df_hy_filtered["高收益主体剩余额度(万)"]
        )
        result_row["高收益主体是否超限"] = _pick_first_non_empty(
            df_hy_filtered["高收益主体是否超限"]
        )
    else:
        limit_maps = _load_value_source(
            data_loader,
            "high_yield_limit_maps",
            "高收益限额映射",
            "load_high_yield_limit_maps",
            data_health,
        )
        if data_health["errors"]:
            return pd.DataFrame()
        if not isinstance(limit_maps, dict):
            data_health["errors"].append("高收益限额映射加载结果不是 dict")
            return pd.DataFrame()

        bond_limits = limit_maps.get("bond_limits", {})
        entity_limits = limit_maps.get("entity_limits", {})
        default_bond_limit = bond_limits.get("__default__")
        default_entity_limit = entity_limits.get("__default__")

        asset_name = _clean_text(_pick_first_non_empty(df_hy_filtered["资产名称"])) if "资产名称" in df_hy_filtered.columns else ""
        issuer_name = _clean_text(_pick_first_non_empty(df_hy_filtered["债务主体"])) if "债务主体" in df_hy_filtered.columns else ""
        if "库存数量(万)_PR" not in df_hy_filtered.columns:
            data_health["errors"].append("高收益明细缺少 库存数量(万)_PR，无法计算高收益单债/主体剩余额度。")
            return pd.DataFrame()

        asset_position_series = pd.to_numeric(df_hy_filtered["库存数量(万)_PR"], errors="coerce")
        if asset_position_series.empty or asset_position_series.isna().any():
            data_health["errors"].append("高收益明细 库存数量(万)_PR 存在空值或非法值，无法计算高收益单债/主体剩余额度。")
            return pd.DataFrame()
        asset_position = float(asset_position_series.sum())

        asset_limit = bond_limits.get(asset_name, default_bond_limit)
        if asset_limit is not None:
            asset_remaining = float(asset_limit) - asset_position
            result_row["高收益单债剩余额度(万)"] = asset_remaining
            result_row["高收益单债是否超限"] = "是" if asset_remaining < 0 else "否"

        issuer_total = 0.0
        if issuer_name and "债务主体" in df_hy_date.columns:
            issuer_position_series = pd.to_numeric(
                df_hy_date.loc[
                    df_hy_date["债务主体"].astype(str).str.strip() == issuer_name,
                    "库存数量(万)_PR",
                ],
                errors="coerce",
            )
            if issuer_position_series.empty or issuer_position_series.isna().any():
                data_health["errors"].append("高收益明细 库存数量(万)_PR 存在空值或非法值，无法计算高收益主体剩余额度。")
                return pd.DataFrame()
            issuer_total = float(issuer_position_series.sum())
        issuer_limit = entity_limits.get(issuer_name, default_entity_limit)
        if issuer_limit is not None:
            issuer_remaining = float(issuer_limit) - issuer_total
            result_row["高收益主体剩余额度(万)"] = issuer_remaining
            result_row["高收益主体是否超限"] = "是" if issuer_remaining < 0 else "否"

    result_df = pd.DataFrame([result_row])
    return _build_constraints_from_frame(
        result_df,
        BOND_CONSTRAINT_SPECS["high_yield"],
        scope_type="bond",
        scope_name="债券级结果",
        source_name="高收益限额",
    )


def _collapse_constraints(constraint_frames: List[pd.DataFrame]) -> pd.DataFrame:
    valid_frames = [frame for frame in constraint_frames if not frame.empty]
    if not valid_frames:
        return pd.DataFrame(columns=[
            "scope_type",
            "scope_name",
            "dimension_name",
            "remaining_wan",
            "overlimit_flag",
            "source_name",
        ])

    df = pd.concat(valid_frames, ignore_index=True)

    def agg_remaining(series: pd.Series) -> Optional[float]:
        values = [value for value in (_coerce_float(v) for v in series) if value is not None]
        if not values:
            return None
        return min(values)

    def agg_overlimit(series: pd.Series) -> str:
        flags = [_normalize_overlimit_flag(v) for v in series if _normalize_overlimit_flag(v)]
        if "是" in flags:
            return "是"
        if "否" in flags:
            return "否"
        if "不可计算" in flags:
            return "不可计算"
        if "不适用" in flags:
            return "不适用"
        return ""

    def agg_source(series: pd.Series) -> str:
        unique_values = []
        for value in series:
            text = _clean_text(value)
            if text and text not in unique_values:
                unique_values.append(text)
        return "、".join(unique_values)

    return (
        df.groupby(["scope_type", "scope_name", "dimension_name"], dropna=False, as_index=False)
        .agg(
            remaining_wan=("remaining_wan", agg_remaining),
            overlimit_flag=("overlimit_flag", agg_overlimit),
            source_name=("source_name", agg_source),
        )
    )


def _build_bond_info(scope_name: str, info_df: pd.DataFrame, *, result_scope: str) -> Dict[str, Any]:
    bond_info: Dict[str, Any] = {
        "代码": _pick_first_non_empty(info_df["代码"]) if "代码" in info_df.columns else None,
        "资产名称": _pick_first_non_empty(info_df["资产名称"]) if "资产名称" in info_df.columns else None,
        "债务主体": _pick_first_non_empty(info_df["债务主体"]) if "债务主体" in info_df.columns else None,
        "日期": _pick_first_non_empty(info_df["日期"]) if "日期" in info_df.columns else None,
        "库存数量(万)_PR": (
            round(
                float(pd.to_numeric(info_df["库存数量(万)_PR"], errors="coerce").fillna(0).sum()),
                4,
            )
            if "库存数量(万)_PR" in info_df.columns
            else None
        ),
    }
    if result_scope == "account":
        bond_info["内部证券账户名称"] = scope_name
    else:
        bond_info["内部证券账户名称"] = "不区分账户"

    if hasattr(bond_info.get("日期"), "strftime"):
        bond_info["日期"] = bond_info["日期"].strftime("%Y-%m-%d")

    return {
        key: value for key, value in bond_info.items()
        if value is not None and (not isinstance(value, str) or value)
    }


def _build_scope_result(
    scope_name: str,
    info_df: pd.DataFrame,
    constraints_df: pd.DataFrame,
    *,
    result_scope: str,
) -> Dict[str, Any]:
    dimensions: List[Dict[str, Any]] = []
    valid_remaining: List[float] = []
    limiting_dimensions: List[str] = []
    overlimit_dimensions: List[str] = []

    for dim_name, _, _ in DIMENSION_MAPPING:
        dim_df = constraints_df[constraints_df["dimension_name"] == dim_name].copy()
        if dim_df.empty:
            dimensions.append({"维度名称": dim_name, "剩余额度(万)": None, "是否超限": "不适用"})
            continue

        remaining_values = [
            value
            for value in (_coerce_float(v) for v in dim_df["remaining_wan"])
            if value is not None
        ]
        remaining_value = min(remaining_values) if remaining_values else None

        flags = [_normalize_overlimit_flag(v) for v in dim_df["overlimit_flag"] if _normalize_overlimit_flag(v)]
        is_overlimit = (remaining_value is not None and remaining_value < 0) or ("是" in flags)
        is_uncalculable = remaining_value is None and "不可计算" in flags
        over_str = (
            "是"
            if is_overlimit
            else (
                "不可计算"
                if is_uncalculable
                else ("否" if remaining_value is not None or "否" in flags else "不适用")
            )
        )
        if is_overlimit:
            overlimit_dimensions.append(dim_name)
            limiting_dimensions.append(dim_name)

        if remaining_value is not None:
            valid_remaining.append(remaining_value)

        dimensions.append(
            {
                "维度名称": dim_name,
                "剩余额度(万)": round(remaining_value, 4) if remaining_value is not None else None,
                "是否超限": over_str,
            }
        )

    if overlimit_dimensions:
        final_quota_wan = 0.0
    elif any(value < 0 for value in valid_remaining):
        final_quota_wan = 0.0
    elif valid_remaining:
        final_quota_wan = max(0.0, min(valid_remaining))
    else:
        final_quota_wan = 0.0

    for item in dimensions:
        value = item.get("剩余额度(万)")
        if value is None:
            continue
        if float(value) < 0:
            limiting_dimensions.append(item["维度名称"])
        elif valid_remaining and abs(float(value) - final_quota_wan) < 1e-9:
            limiting_dimensions.append(item["维度名称"])

    if overlimit_dimensions:
        status = "超限"
    elif valid_remaining:
        status = "可买" if final_quota_wan > 0 else "不可买"
    else:
        status = "不可计算"

    return {
        "account_name": scope_name,
        "bond_info": _build_bond_info(scope_name, info_df, result_scope=result_scope),
        "dimensions": dimensions,
        "final_quota_wan": round(final_quota_wan, 4),
        "limiting_dimensions": list(dict.fromkeys(limiting_dimensions)),
        "overlimit_dimensions": list(dict.fromkeys(overlimit_dimensions)),
        "status": status,
    }


def _build_common_bond_info(
    resolved_rows: pd.DataFrame,
    *,
    result_scope: str,
    account_count: int,
    single_account_name: Optional[str] = None,
) -> Dict[str, Any]:
    common_bond_info = {
        "代码": _pick_first_non_empty(resolved_rows["代码"]) if "代码" in resolved_rows.columns else None,
        "资产名称": _pick_first_non_empty(resolved_rows["资产名称"]) if "资产名称" in resolved_rows.columns else None,
        "债务主体": _pick_first_non_empty(resolved_rows["债务主体"]) if "债务主体" in resolved_rows.columns else None,
        "日期": _pick_first_non_empty(resolved_rows["日期"]) if "日期" in resolved_rows.columns else None,
        "结果层级": "账户级" if result_scope == "account" else "债券级",
    }
    if hasattr(common_bond_info.get("日期"), "strftime"):
        common_bond_info["日期"] = common_bond_info["日期"].strftime("%Y-%m-%d")

    if result_scope == "account":
        common_bond_info["内部证券账户数"] = account_count
        common_bond_info["内部证券账户名称"] = (
            "多账户"
            if account_count > 1
            else (single_account_name or "未识别账户")
        )
    else:
        common_bond_info["内部证券账户名称"] = "不区分账户"

    return {
        key: value
        for key, value in common_bond_info.items()
        if value is not None and (not isinstance(value, str) or value)
    }


def query_bond_remaining_quota(
    data_loader,
    bond_code_or_name: str,
    target_date: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    查询单只债券在各限额维度下的剩余额度与最终可购额度。

    返回结构兼容旧页面，但新增：
    - ``result_scope``: ``account`` / ``bond``
    - ``bond_level_result``: 仅债券级场景的结果对象
    - ``public_dimensions``: 所有账户共享的公共约束维度
    - ``data_health``: 数据源加载与完整性信息
    """
    raw = _clean_text(bond_code_or_name)
    data_health = _new_data_health()
    if not raw:
        return _empty_query_result(error="请输入债券代码或名称", data_health=data_health)

    source_frames: Dict[str, pd.DataFrame] = {}
    for source_key, source_label, method_name in DATAFRAME_SOURCES:
        source_frames[source_key] = _load_dataframe_source(
            data_loader,
            source_key,
            source_label,
            method_name,
            data_health,
        )

    if data_health["errors"]:
        return _empty_query_result(
            error="单券可购额度查询关键数据源加载失败，请先修复数据后再查询。",
            data_health=data_health,
        )

    if all(df.empty for df in source_frames.values()):
        return _empty_query_result(error="单券可购额度查询数据为空", data_health=data_health)

    query_date = _get_query_date(target_date, list(source_frames.values()))
    if query_date is None:
        return _empty_query_result(error="查询数据缺少日期字段", data_health=data_health)

    dated_sources = {
        key: _prepare_identifier_columns(_filter_frame_by_query_date(df, query_date))
        for key, df in source_frames.items()
    }
    asset_entity_map = _build_asset_entity_map(list(dated_sources.values()), data_health)
    dated_sources = {
        key: _attach_entity_key(df, asset_entity_map)
        for key, df in dated_sources.items()
    }

    lookup_frames = [
        _prepare_lookup_frame(df, query_date=None)
        for df in dated_sources.values()
    ]
    lookup_df = (
        pd.concat([df for df in lookup_frames if not df.empty], ignore_index=True)
        if any(not df.empty for df in lookup_frames)
        else pd.DataFrame()
    )
    if lookup_df.empty:
        return _empty_query_result(error="目标日期无可查询债券数据", data_health=data_health)

    resolved_rows, resolved_entity_key, candidates = _resolve_bond_rows(lookup_df, raw)
    if resolved_rows is None or not resolved_entity_key:
        return _empty_query_result(
            error="未找到该债券" if candidates is None else None,
            message=None if candidates is None else "匹配到多只债券，请输入更精确的债券代码或全称。",
            candidates=candidates,
            data_health=data_health,
        )

    filtered_sources = {
        key: _filter_frame_by_entity(df, resolved_entity_key)
        for key, df in dated_sources.items()
    }
    high_yield_date_df = dated_sources["high_yield"]
    high_yield_entity_df = _filter_frame_by_entity(high_yield_date_df, resolved_entity_key)
    is_high_yield_query = (
        not high_yield_entity_df.empty
        or any(_has_high_yield_indicator_rows(df) for df in filtered_sources.values())
    )
    if is_high_yield_query and high_yield_entity_df.empty:
        data_health["errors"].append(
            "高收益明细缺失：该债券已识别为高收益，但目标日期高收益明细中未找到对应记录，无法计算高收益专属限额。"
        )
        return _empty_query_result(
            error="高收益限额数据缺失，无法计算单券可购额度。",
            data_health=data_health,
        )

    regulatory_not_calculable_reason = _find_regulatory_not_calculable_reason(filtered_sources["full_reg"])
    if regulatory_not_calculable_reason:
        message = f"监管集中度不可计算：{regulatory_not_calculable_reason}"
        data_health["warnings"].append(message)

    account_base_frames = [
        _prepare_base_frame(filtered_sources["credit_1_1"], query_date=None, entity_key=resolved_entity_key),
        _prepare_base_frame(filtered_sources["credit_1_2"], query_date=None, entity_key=resolved_entity_key),
        _prepare_base_frame(filtered_sources["credit_2"], query_date=None, entity_key=resolved_entity_key),
        _prepare_base_frame(filtered_sources["high_yield"], query_date=None, entity_key=resolved_entity_key),
    ]
    account_base_df = _collapse_base_frames(account_base_frames)
    full_reg_base_df = _prepare_base_frame(filtered_sources["full_reg"], query_date=None, entity_key=resolved_entity_key)

    constraint_frames = [
        _build_validated_constraints_from_frame(
            _filter_non_high_yield_credit_rows(filtered_sources["credit_1_2"]),
            ACCOUNT_CONSTRAINT_SPECS["credit_1_2"],
            scope_type="account",
            scope_name="",
            source_name="信用债1_2",
            data_health=data_health,
            required_dimension_names=REQUIRED_CONSTRAINT_DIMENSIONS["credit_1_2"],
        ),
        _build_validated_constraints_from_frame(
            _filter_non_high_yield_credit_rows(filtered_sources["credit_1_1"]),
            ACCOUNT_CONSTRAINT_SPECS["credit_1_1"],
            scope_type="account",
            scope_name="",
            source_name="信用债1_1",
            data_health=data_health,
            required_dimension_names=REQUIRED_CONSTRAINT_DIMENSIONS["credit_1_1"],
        ),
        _build_validated_constraints_from_frame(
            filtered_sources["credit_2"],
            ACCOUNT_CONSTRAINT_SPECS["credit_2"],
            scope_type="account",
            scope_name="",
            source_name="信用债2",
            data_health=data_health,
            required_dimension_names=REQUIRED_CONSTRAINT_DIMENSIONS["credit_2"],
        ),
    ]

    full_reg_constraint_df = filtered_sources["full_reg"].copy()
    if not full_reg_constraint_df.empty and "是否可计算" in full_reg_constraint_df.columns:
        full_reg_constraint_df = full_reg_constraint_df[full_reg_constraint_df["是否可计算"] != "否"].copy()
    constraint_frames.append(
        _build_validated_constraints_from_frame(
            full_reg_constraint_df,
            BOND_CONSTRAINT_SPECS["full_reg"],
            scope_type="bond",
            scope_name="债券级结果",
            source_name="全量债券监管集中度",
            data_health=data_health,
            required_dimension_names=REQUIRED_CONSTRAINT_DIMENSIONS["full_reg"],
        )
    )
    constraint_frames.append(
        _build_high_yield_constraints(
            data_loader,
            high_yield_date_df,
            resolved_entity_key,
            query_date,
            data_health,
        )
    )
    if data_health["errors"]:
        if _is_high_yield_data_error(data_health):
            return _empty_query_result(
                error="高收益限额数据缺失，无法计算单券可购额度。",
                data_health=data_health,
            )
        return _empty_query_result(
            error="单券可购额度查询关键数据源加载失败，请先修复数据后再查询。",
            data_health=data_health,
        )

    constraints_df = _collapse_constraints(constraint_frames)
    public_constraints_df = constraints_df[constraints_df["scope_type"] == "bond"].copy()
    public_dimensions = public_constraints_df["dimension_name"].drop_duplicates().tolist()

    if not account_base_df.empty:
        account_results = []
        for account_name, info_df in account_base_df.groupby("内部证券账户名称", sort=True, dropna=False):
            account_name = _clean_text(account_name) or "未识别账户"
            account_constraints = constraints_df[
                (constraints_df["scope_type"] == "bond")
                | (
                    (constraints_df["scope_type"] == "account")
                    & (constraints_df["scope_name"] == account_name)
                )
            ].copy()
            account_results.append(
                _build_scope_result(
                    account_name,
                    info_df.copy(),
                    account_constraints,
                    result_scope="account",
                )
            )

        account_results.sort(key=lambda item: (item["final_quota_wan"], item["account_name"]))
        primary_result = account_results[0]
        final_quota_wan = min(item["final_quota_wan"] for item in account_results)
        account_summary = [
            {
                "内部证券账户名称": item["account_name"],
                "库存数量(万)_PR": item["bond_info"].get("库存数量(万)_PR"),
                "最终可购额度(万)": item["final_quota_wan"],
                "限制维度": "、".join(item["limiting_dimensions"]) or "—",
                "是否存在超限维度": "是" if item["overlimit_dimensions"] else "否",
                "状态": item["status"],
            }
            for item in account_results
        ]
        return {
            "bond_info": primary_result["bond_info"],
            "common_bond_info": _build_common_bond_info(
                resolved_rows,
                result_scope="account",
                account_count=len(account_results),
                single_account_name=primary_result["account_name"],
            ),
            "dimensions": primary_result["dimensions"],
            "account_results": account_results,
            "account_summary": account_summary,
            "bond_level_result": None,
            "public_dimensions": public_dimensions,
            "final_quota_wan": round(final_quota_wan, 4),
            "selected_account_name": primary_result["account_name"],
            "matched_account_count": len(account_results),
            "result_scope": "account",
            "data_health": data_health,
            "error": None,
            "message": None,
            "candidates": [],
        }

    bond_info_df = full_reg_base_df if not full_reg_base_df.empty else _collapse_base_frames([
        _prepare_base_frame(resolved_rows, query_date=None, entity_key=resolved_entity_key)
    ])
    bond_result = _build_scope_result(
        "债券级结果",
        bond_info_df if not bond_info_df.empty else resolved_rows.copy(),
        public_constraints_df,
        result_scope="bond",
    )
    return {
        "bond_info": bond_result["bond_info"],
        "common_bond_info": _build_common_bond_info(
            resolved_rows,
            result_scope="bond",
            account_count=0,
            single_account_name=None,
        ),
        "dimensions": bond_result["dimensions"],
        "account_results": [bond_result],
        "account_summary": [],
        "bond_level_result": bond_result,
        "public_dimensions": public_dimensions,
        "final_quota_wan": bond_result["final_quota_wan"],
        "selected_account_name": None,
        "matched_account_count": 0,
        "result_scope": "bond",
        "data_health": data_health,
        "error": None,
        "message": None,
        "candidates": [],
    }
