"""Production-equivalent sources for high-yield annual full-price cost."""

from __future__ import annotations

import pandas as pd

from ..common.financial_tool_pool_rules import (
    build_financial_tool_pool_sets,
    row_in_financial_tool_pool,
)


HIGH_YIELD_CAPITAL_COLUMNS: tuple[str, ...] = (
    "日期",
    "账户",
    "简称",
    "代码",
    "持仓面额(元)",
    "全价成本(元)",
)


def select_accounting_high_yield_capital_rows(
    accounting_positions: pd.DataFrame | None,
    financial_tool_pool: pd.DataFrame | None,
) -> pd.DataFrame:
    """Select the existing accounting-system branch of the annual-cost input.

    This is the row-level transformation previously embedded in
    ``Stage2RiskEngine.query_high_yield_capital``.  It intentionally de-dupes
    only within this source; cross-source append semantics are handled below.
    """

    if accounting_positions is None or accounting_positions.empty:
        return pd.DataFrame()

    df_src = accounting_positions.copy()
    if "日期" in df_src.columns:
        df_src["日期"] = pd.to_datetime(df_src["日期"], errors="coerce")

    if "账户" not in df_src.columns and "内部证券账户名称" in df_src.columns:
        df_src["账户"] = df_src["内部证券账户名称"]
    if "简称" not in df_src.columns and "资产名称" in df_src.columns:
        df_src["简称"] = df_src["资产名称"]
    if "代码" not in df_src.columns and "资产代码" in df_src.columns:
        df_src["代码"] = df_src["资产代码"].astype(str).str.split(".").str[0]
    if "代码" in df_src.columns and df_src["代码"].dtype != object:
        df_src["代码"] = df_src["代码"].astype(str).str.split(".").str[0]

    missing = [column for column in HIGH_YIELD_CAPITAL_COLUMNS if column not in df_src]
    if missing:
        return pd.DataFrame()

    tool_pool_names, tool_pool_codes = build_financial_tool_pool_sets(financial_tool_pool)
    if tool_pool_names or tool_pool_codes:
        df_src["高收益量化可转债"] = df_src.apply(
            lambda row: (
                row.get("简称")
                if row_in_financial_tool_pool(row, tool_pool_names, tool_pool_codes)
                else pd.NA
            ),
            axis=1,
        )
    else:
        df_src["高收益量化可转债"] = pd.NA

    account_contains = df_src["账户"].astype(str).str.contains("高收益", na=False)
    has_convertible = df_src["高收益量化可转债"].notna()
    return df_src.loc[account_contains | has_convertible, list(HIGH_YIELD_CAPITAL_COLUMNS)].drop_duplicates()


def select_penetration_high_yield_capital_rows(
    penetrate_positions: pd.DataFrame | None,
    penetrate_high_yield: pd.DataFrame | None,
) -> pd.DataFrame:
    """Select the existing ISIN-inner-join branch of the annual-cost input."""

    if penetrate_positions is None or penetrate_positions.empty:
        return pd.DataFrame()
    if penetrate_high_yield is None or penetrate_high_yield.empty:
        return pd.DataFrame()

    source_columns = (
        "日期",
        "ISIN码",
        "资产代码",
        "资产名称",
        "内部证券账户名称",
        "库存数量(万)_PR",
        "本币成本",
    )
    missing = [column for column in source_columns if column not in penetrate_positions]
    if missing:
        return pd.DataFrame()

    isin_column = "ISIN代码" if "ISIN代码" in penetrate_high_yield else "ISIN码"
    if isin_column not in penetrate_high_yield:
        return pd.DataFrame()

    df_src = penetrate_positions.loc[:, list(source_columns)].copy()
    if "日期" in df_src.columns:
        df_src["日期"] = pd.to_datetime(df_src["日期"], errors="coerce")
    df_src = df_src.dropna(subset=["ISIN码"])

    penetrate_isin = penetrate_high_yield[[isin_column]].drop_duplicates(keep="last")
    penetrate_isin = penetrate_isin.dropna(subset=[isin_column])
    penetrate_isin.columns = ["ISIN码"]

    selected = df_src.merge(penetrate_isin, on="ISIN码", how="inner")
    selected = selected.rename(
        columns={
            "内部证券账户名称": "账户",
            "资产名称": "简称",
            "资产代码": "代码",
            "本币成本": "全价成本(元)",
        }
    )
    selected["持仓面额(元)"] = selected["库存数量(万)_PR"] * 10000
    return selected.loc[:, list(HIGH_YIELD_CAPITAL_COLUMNS)]


def append_high_yield_capital_sources(
    accounting_rows: pd.DataFrame,
    penetration_rows: pd.DataFrame,
) -> pd.DataFrame:
    """Append accounting then penetration rows without cross-source de-duplication."""

    if penetration_rows.empty:
        return accounting_rows.copy()
    return pd.concat([accounting_rows, penetration_rows], ignore_index=True)
