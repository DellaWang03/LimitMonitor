"""
单债归并键工具。
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from .security_code_normalizer import normalize_security_code_series


SINGLE_BOND_GROUP_KEY_COL = "单一债券归并键"
SINGLE_BOND_GROUP_KEY_SOURCE_COL = "单一债券归并键来源"

_EMPTY_TEXT_VALUES = {"", "nan", "none", "nat", "<na>", "null"}


def clean_bond_group_value(value: Any, *, upper: bool = True) -> str | None:
    """清洗单债归并用字段，统一空值。"""
    if pd.isna(value):
        return None
    text = str(value).strip()
    if text.lower() in _EMPTY_TEXT_VALUES:
        return None
    return text.upper() if upper else text


def ensure_single_bond_group_key(df: pd.DataFrame, *, copy: bool = True) -> pd.DataFrame:
    """
    添加单债归并键。

    业务优先级：主证券代码_标准 -> ISIN码 -> 资产代码_标准 -> 资产名称。
    当所有字段均缺失时使用行级缺省键，避免 pandas groupby 将空 key 全部丢弃或误并为一组。
    """
    result = df.copy() if copy else df

    if "主证券代码_标准" not in result.columns and "主证券代码" in result.columns:
        result["主证券代码_标准"] = normalize_security_code_series(result["主证券代码"])
    if "资产代码_标准" not in result.columns and "资产代码" in result.columns:
        result["资产代码_标准"] = normalize_security_code_series(result["资产代码"])

    result[SINGLE_BOND_GROUP_KEY_COL] = pd.NA
    result[SINGLE_BOND_GROUP_KEY_SOURCE_COL] = pd.NA

    priorities = [
        ("主证券代码_标准", "主证券代码_标准", True),
        ("ISIN码", "ISIN码", True),
        ("资产代码_标准", "资产代码_标准", True),
        ("资产名称", "资产名称", False),
    ]

    for col, source, upper in priorities:
        if col not in result.columns:
            continue
        values = result[col].apply(lambda value: clean_bond_group_value(value, upper=upper))
        fill_mask = result[SINGLE_BOND_GROUP_KEY_COL].isna() & values.notna()
        result.loc[fill_mask, SINGLE_BOND_GROUP_KEY_COL] = (
            source + "::" + values.loc[fill_mask].astype(str)
        )
        result.loc[fill_mask, SINGLE_BOND_GROUP_KEY_SOURCE_COL] = source

    missing_mask = result[SINGLE_BOND_GROUP_KEY_COL].isna()
    if missing_mask.any():
        result.loc[missing_mask, SINGLE_BOND_GROUP_KEY_COL] = [
            f"缺归并主键::{idx}" for idx in result.index[missing_mask]
        ]
        result.loc[missing_mask, SINGLE_BOND_GROUP_KEY_SOURCE_COL] = "缺归并主键"

    return result
