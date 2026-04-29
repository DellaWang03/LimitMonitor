"""
展示层通用代码字段清洗与映射工具。
"""
from __future__ import annotations

from typing import Any, Optional

import pandas as pd


_EMPTY_CODE_LIKE_VALUES = {"", "nan", "none", "<na>", "nat", "null"}


def clean_code_like_value(value: Any) -> Optional[str]:
    """清洗代码/ISIN类字段，统一空值口径。"""
    if pd.isna(value):
        return None
    text = str(value).strip()
    if text.lower() in _EMPTY_CODE_LIKE_VALUES:
        return None
    return text


def attach_display_code(df: pd.DataFrame) -> pd.DataFrame:
    """
    为展示数据补充代码列：优先 ISIN，兜底资产代码。
    与快照生成脚本保持一致，避免口径漂移。
    """
    if "资产代码" not in df.columns and "证券代码" in df.columns:
        df = df.copy()
        df["资产代码"] = df["证券代码"]

    if "资产代码" not in df.columns:
        return df

    result = df.copy()
    result["资产代码"] = result["资产代码"].apply(clean_code_like_value)

    if "ISIN码" in result.columns:
        result["ISIN码"] = result["ISIN码"].apply(clean_code_like_value)
        result["代码"] = result["ISIN码"].combine_first(result["资产代码"])
    else:
        result["代码"] = result["资产代码"]

    return result
