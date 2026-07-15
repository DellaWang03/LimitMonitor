from __future__ import annotations

import numpy as np
import pandas as pd

from ..common import (
    SINGLE_BOND_GROUP_KEY_COL,
    SINGLE_BOND_GROUP_KEY_SOURCE_COL,
    ensure_single_bond_group_key,
    normalize_security_code_series,
)
from ..common.financial_tool_pool import (
    build_financial_tool_pool_sets,
    normalize_tool_pool_code,
    row_in_financial_tool_pool,
)


def _coerce_numeric_columns(df: pd.DataFrame, columns) -> pd.DataFrame:
    for col in columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _first_non_null(series: pd.Series):
    non_null = series.dropna()
    return non_null.iloc[0] if not non_null.empty else None


def _build_penetration_high_yield_codes(
    penetrate_high_yield: pd.DataFrame | None,
) -> set[str]:
    if (
        penetrate_high_yield is None
        or penetrate_high_yield.empty
        or "类型" not in penetrate_high_yield.columns
    ):
        return set()

    high_yield_rows = penetrate_high_yield[
        penetrate_high_yield["类型"].astype(str).str.strip() == "高收益"
    ]
    code_columns = [
        col
        for col in ("债券代码", "资产代码", "主证券代码", "主证券代码_标准", "代码")
        if col in high_yield_rows.columns
    ]
    codes: set[str] = set()
    for col in code_columns:
        codes.update(
            code for code in high_yield_rows[col].apply(normalize_tool_pool_code) if code
        )
    return codes


def filter_non_high_yield_credit_rows(
    frame: pd.DataFrame,
    penetrate_high_yield: pd.DataFrame | None,
    financial_tool_pool: pd.DataFrame | None,
) -> pd.DataFrame:
    """Production high-yield exclusion used only by the original query nodes."""
    result = frame.copy()
    high_yield_mask = pd.Series(False, index=result.index)

    if "是否属于高收益" in result.columns:
        high_yield_mask |= result["是否属于高收益"].astype(str).str.strip() == "是"

    if "内部证券账户名称" in result.columns:
        high_yield_mask |= result["内部证券账户名称"].astype(str).str.contains(
            "高收益", na=False
        )

    penetration_codes = _build_penetration_high_yield_codes(penetrate_high_yield)
    if penetration_codes:
        for col in ("资产代码", "资产代码_标准", "主证券代码", "主证券代码_标准"):
            if col in result.columns:
                high_yield_mask |= result[col].apply(normalize_tool_pool_code).isin(
                    penetration_codes
                )

    tool_pool_names, tool_pool_codes = build_financial_tool_pool_sets(
        financial_tool_pool
    )
    if tool_pool_names or tool_pool_codes:
        high_yield_mask |= result.apply(
            row_in_financial_tool_pool,
            axis=1,
            tool_pool_names=tool_pool_names,
            tool_pool_codes=tool_pool_codes,
        )

    return result[~high_yield_mask].copy()


def calculate_single_bond_total_position(credit_position: pd.DataFrame) -> pd.DataFrame:
    df = credit_position.copy()
    df["业务分类"] = df["内部证券账户名称"].apply(
        lambda x: "做市业务" if x == "做市交易部做市业务" else "自营业务"
    )
    df = df[df["债券分类2"] != "利率债"]

    if "主证券代码_标准" not in df.columns and "主证券代码" in df.columns:
        df["主证券代码_标准"] = normalize_security_code_series(df["主证券代码"])

    df = ensure_single_bond_group_key(df)

    if "主证券代码" in df.columns and "主证券代码_标准" in df.columns:
        df["_主证券代码_已标准化"] = df["主证券代码"] == df["主证券代码_标准"]
        df = df.sort_values(
            ["日期", "业务分类", SINGLE_BOND_GROUP_KEY_COL, "_主证券代码_已标准化"],
            ascending=[True, True, True, False],
        )

    df = _coerce_numeric_columns(df, ["库存数量(万)_PR", "债券余额(亿)"])

    aggregation_map = {
        "库存数量(万)_PR": "sum",
        "债券余额(亿)": "mean",
    }
    for col in [
        "主证券代码",
        "主证券代码_标准",
        "主证券名称",
        "资产代码",
        "资产代码_标准",
        "资产名称",
        "ISIN码",
        SINGLE_BOND_GROUP_KEY_SOURCE_COL,
    ]:
        if col in df.columns:
            aggregation_map[col] = _first_non_null

    result = df.groupby(
        ["日期", "业务分类", SINGLE_BOND_GROUP_KEY_COL], as_index=False
    ).agg(aggregation_map)
    result = result.rename(columns={"库存数量(万)_PR": "单一债券总持仓_PR"})
    result["单一债券集中度"] = (
        result["单一债券总持仓_PR"] / result["债券余额(亿)"] * 0.0001
    )
    result["单一债券集中度"] = result["单一债券集中度"].replace(
        [np.inf, -np.inf], None
    )
    result = result.drop(columns=["债券余额(亿)"])
    result = result.drop(columns=["_主证券代码_已标准化"], errors="ignore")
    return result.sort_values("单一债券集中度", ascending=False)


def calculate_single_issuer_total_position(credit_position: pd.DataFrame) -> pd.DataFrame:
    df = credit_position.copy()
    df["业务分类"] = df["内部证券账户名称"].apply(
        lambda x: "做市业务" if x == "做市交易部做市业务" else "自营业务"
    )
    result = df.groupby(
        ["日期", "业务分类", "债务主体wind代码", "债务主体"], as_index=False
    ).agg({"库存数量(万)_PR": "sum"})
    return result.rename(columns={"库存数量(万)_PR": "单一主体总持仓_PR"})


def calculate_specific_issuer_total_position(
    credit_position: pd.DataFrame,
    specific_issuer_limit: pd.DataFrame | None,
    penetrate_high_yield: pd.DataFrame | None,
    financial_tool_pool: pd.DataFrame | None,
) -> pd.DataFrame:
    df = filter_non_high_yield_credit_rows(
        credit_position, penetrate_high_yield, financial_tool_pool
    )
    df = df[~df["内部证券账户名称"].str.contains("关注池", na=False)]

    if specific_issuer_limit is None:
        return pd.DataFrame()

    df = df.merge(
        specific_issuer_limit[["主体wind代码", "日期", "指标名称", "指标值"]],
        left_on=["债务主体wind代码", "日期"],
        right_on=["主体wind代码", "日期"],
        how="left",
    )
    df = df.drop(columns=["主体wind代码"], errors="ignore")
    df = df.rename(columns={"指标名称": "限额名称"})
    df = df[df["限额名称"].notna()]
    df["业务分类"] = df["内部证券账户名称"].apply(
        lambda x: "做市业务" if x == "做市交易部做市业务" else "自营业务"
    )
    result = df.groupby(["日期", "业务分类", "限额名称"], as_index=False).agg(
        {"库存数量(万)_PR": "sum"}
    )
    return result.rename(
        columns={"限额名称": "特定主体名称", "库存数量(万)_PR": "特定主体总持仓"}
    )


def calculate_single_controller_total_position(
    credit_risk_context: pd.DataFrame,
) -> pd.DataFrame:
    df = credit_risk_context.copy()
    df["业务分类"] = df["内部证券账户名称"].apply(
        lambda x: "做市业务" if x == "做市交易部做市业务" else "自营业务"
    )
    result = df.groupby(
        ["日期", "业务分类", "实际控制人名称_修正"], as_index=False
    ).agg({"库存数量(万)_PR": "sum"})
    result = result.rename(columns={"库存数量(万)_PR": "单一实控人总持仓_PR"})
    return result[result["实际控制人名称_修正"].notna()]


def calculate_specific_controller_total_position(
    credit_risk_context: pd.DataFrame,
    specific_controller_limit: pd.DataFrame | None,
    penetrate_high_yield: pd.DataFrame | None,
    financial_tool_pool: pd.DataFrame | None,
) -> pd.DataFrame:
    df = filter_non_high_yield_credit_rows(
        credit_risk_context, penetrate_high_yield, financial_tool_pool
    )
    df = df[~df["内部证券账户名称"].str.contains("关注池", na=False)]

    if specific_controller_limit is None:
        return pd.DataFrame()

    df = df.merge(
        specific_controller_limit[["实控人名称", "日期", "指标名称", "指标值"]],
        left_on=["实际控制人名称_修正", "日期"],
        right_on=["实控人名称", "日期"],
        how="left",
    )
    df = df[(df["指标名称"].notna()) & (df["指标名称"] != "")]
    df["业务分类"] = df["内部证券账户名称"].apply(
        lambda x: "做市业务" if x == "做市交易部做市业务" else "自营业务"
    )
    result = df.groupby(["日期", "业务分类", "实控人名称"], as_index=False).agg(
        {"库存数量(万)_PR": "sum"}
    )
    return result.rename(
        columns={
            "实控人名称": "特定实控人名称",
            "库存数量(万)_PR": "特定实控人总持仓",
        }
    )


def calculate_single_guarantee_total_position(
    credit_risk_context: pd.DataFrame,
    specific_issuer_detail: pd.DataFrame | None,
    specific_controller_detail: pd.DataFrame | None,
    single_issuer_scale_limit: pd.DataFrame | None,
    single_guarantee_company_limit: pd.DataFrame | None,
    penetrate_high_yield: pd.DataFrame | None,
    financial_tool_pool: pd.DataFrame | None,
) -> pd.DataFrame:
    df = filter_non_high_yield_credit_rows(
        credit_risk_context, penetrate_high_yield, financial_tool_pool
    )
    df = df[~df["内部证券账户名称"].str.contains("关注池", na=False)]
    df = df[df["担保人wind代码"].notna()]

    if specific_issuer_detail is not None and len(specific_issuer_detail) > 0:
        df = df.merge(
            specific_issuer_detail[["资产代码", "日期", "指标名称"]],
            on=["资产代码", "日期"],
            how="left",
        )
        df = df.rename(columns={"指标名称": "特定主体指标名称"})
    else:
        df["特定主体指标名称"] = None

    if specific_controller_detail is not None and len(specific_controller_detail) > 0:
        df = df.merge(
            specific_controller_detail[["资产代码", "日期", "指标名称"]],
            on=["资产代码", "日期"],
            how="left",
            suffixes=("", "_ctrl"),
        )
        df = df.rename(columns={"指标名称": "特定实控人指标名称"})
    else:
        df["特定实控人指标名称"] = None

    df = df[
        (df["特定主体指标名称"].isna())
        & (df["特定实控人指标名称"].isna())
    ]
    df = df.drop(
        columns=["特定主体指标名称", "特定实控人指标名称"], errors="ignore"
    )

    def calc_custom_category(row):
        bond_type1 = row.get("债券类型1", "")
        if bond_type1 == "可转债":
            return "可转债"
        if bond_type1 == "可交换债":
            return "可交换债"
        if row.get("发行人类型") == "国企":
            return "国企"
        if row.get("发行人类型") == "非国企":
            return "非国企"
        return None

    df["自定义"] = df.apply(calc_custom_category, axis=1)
    if "债券池" in df.columns:
        df["债券池_复制"] = df["债券池"]
    df["单一债券规模限额适用类别"] = df.apply(
        lambda row: f"{row.get('自定义', '')}/{row.get('债券池_复制', '')}"
        if pd.notna(row.get("自定义")) and pd.notna(row.get("债券池_复制"))
        else row.get("自定义", ""),
        axis=1,
    )
    df["中债隐含评级_带前缀"] = df["中债隐含评级"].apply(
        lambda x: f"中债隐含评级{x}" if pd.notna(x) else None
    )

    def calc_issuer_limit_category(row):
        rating = row.get("中债隐含评级")
        if rating == "AAA":
            return "中债隐含评级AAA"
        if rating == "AAA+":
            return "中债隐含评级AAA+"
        issuer_type = row.get("发行人类型", "")
        pool = row.get("主体池", "")
        if pd.notna(issuer_type) and pd.notna(pool):
            return f"{issuer_type}/{pool}"
        if pd.notna(issuer_type):
            return issuer_type
        return ""

    df["单一主体限额适用类别"] = df.apply(calc_issuer_limit_category, axis=1)

    if single_issuer_scale_limit is not None:
        df = df.merge(
            single_issuer_scale_limit[["日期", "指标名称", "指标值"]].drop_duplicates(),
            left_on=["单一主体限额适用类别", "日期"],
            right_on=["指标名称", "日期"],
            how="left",
        )
        df = df.drop(columns=["指标名称"], errors="ignore")
        df = df.rename(columns={"指标值": "单一主体规模限额指标值1"})

    if single_issuer_scale_limit is not None and "担保公司是否准入" in df.columns:
        df = df.merge(
            single_issuer_scale_limit[["日期", "指标名称", "指标值"]].drop_duplicates(),
            left_on=["担保公司是否准入", "日期"],
            right_on=["指标名称", "日期"],
            how="left",
        )
        df = df.drop(columns=["指标名称"], errors="ignore")
        df = df.rename(columns={"指标值": "指标值_担保"})

    df = df.rename(columns={"单一主体限额适用类别": "单一主体限额适用类别1"})
    df["指标值_担保"] = df["指标值_担保"].fillna(0)
    df["单一主体规模限额指标值1"] = df["单一主体规模限额指标值1"].fillna(0)

    def select_issuer_limit_category(row):
        if pd.notna(row.get("指标值_担保")) and row.get("指标值_担保", 0) > row.get(
            "单一主体规模限额指标值1", 0
        ):
            return row.get("担保公司是否准入")
        return row["单一主体限额适用类别1"]

    def select_issuer_limit_value(row):
        if pd.notna(row.get("指标值_担保")) and row.get("指标值_担保", 0) > row.get(
            "单一主体规模限额指标值1", 0
        ):
            return row.get("指标值_担保")
        return row.get("单一主体规模限额指标值1")

    df["单一主体限额适用类别"] = df.apply(select_issuer_limit_category, axis=1)
    df["单一主体规模限额指标值"] = df.apply(select_issuer_limit_value, axis=1)

    if single_guarantee_company_limit is not None:
        df = df.merge(
            single_guarantee_company_limit[
                ["日期", "指标名称", "是否准入", "指标值"]
            ].drop_duplicates(),
            left_on=["日期", "担保人wind代码", "单一主体限额适用类别"],
            right_on=["日期", "指标名称", "是否准入"],
            how="left",
        )
        df = df.rename(columns={"指标值": "单一担保公司规模限额"})
        df = df[df["单一担保公司规模限额"].notna()]

    df["业务分类"] = df["内部证券账户名称"].apply(
        lambda x: "做市业务" if x == "做市交易部做市业务" else "自营业务"
    )
    result = df.groupby(
        ["日期", "业务分类", "担保人wind代码", "担保人"], as_index=False
    ).agg({"库存数量(万)_PR": "sum"})
    return result.rename(columns={"库存数量(万)_PR": "单一担保人总持仓_PR"})


def calculate_single_guarantee_total_position_unfiltered(
    single_guarantee_company_limit: pd.DataFrame | None,
    credit_risk_context: pd.DataFrame | None,
) -> pd.DataFrame:
    if single_guarantee_company_limit is None or credit_risk_context is None:
        return pd.DataFrame()

    df_guarantors = single_guarantee_company_limit[
        ["日期", "指标名称", "统一社会信用代码", "授信担保公司名称"]
    ].copy()
    df_guarantors = df_guarantors.drop_duplicates()
    df = df_guarantors.merge(
        credit_risk_context[["日期", "担保人wind代码", "库存数量(万)_PR"]],
        left_on=["日期", "指标名称"],
        right_on=["日期", "担保人wind代码"],
        how="right",
    )
    result = df.groupby(
        ["日期", "指标名称", "授信担保公司名称"], as_index=False
    ).agg({"库存数量(万)_PR": "sum"})
    return result.rename(columns={"库存数量(万)_PR": "单一担保人总持仓_PR"})
