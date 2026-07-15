"""Pure financial-tool-pool matching rules shared by production calculations."""

from __future__ import annotations

from typing import Any

import pandas as pd


_EMPTY_TEXT_VALUES = {"", "nan", "none", "nat", "<na>", "null"}
_EXCHANGE_SUFFIXES = {"SH", "SZ", "IB", "BJ", "OF", "HK", "MOX"}


def clean_tool_pool_text(value: Any) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() in _EMPTY_TEXT_VALUES else text


def normalize_tool_pool_code(value: Any) -> str:
    text = clean_tool_pool_text(value)
    if not text:
        return ""

    if text.endswith(".0"):
        prefix = text[:-2]
        if prefix.isdigit():
            text = prefix

    if "." in text:
        prefix, suffix = text.rsplit(".", 1)
        if suffix.upper() in _EXCHANGE_SUFFIXES or suffix.isdigit():
            text = prefix

    return text.strip().upper()


def build_financial_tool_pool_sets(
    df_tool_pool: pd.DataFrame | None,
) -> tuple[set[str], set[str]]:
    if df_tool_pool is None or df_tool_pool.empty:
        return set(), set()

    names: set[str] = set()
    codes: set[str] = set()

    if "简称" in df_tool_pool.columns:
        names = {
            text
            for text in df_tool_pool["简称"].apply(clean_tool_pool_text)
            if text
        }

    if "代码" in df_tool_pool.columns:
        codes = {
            code
            for code in df_tool_pool["代码"].apply(normalize_tool_pool_code)
            if code
        }

    return names, codes


def row_in_financial_tool_pool(
    row: pd.Series,
    tool_pool_names: set[str],
    tool_pool_codes: set[str],
) -> bool:
    if tool_pool_names:
        for col in ("资产名称", "主证券名称", "简称"):
            if clean_tool_pool_text(row.get(col)) in tool_pool_names:
                return True

    if tool_pool_codes:
        for col in ("资产代码", "主证券代码", "主证券代码_标准", "代码"):
            if normalize_tool_pool_code(row.get(col)) in tool_pool_codes:
                return True

    return False
