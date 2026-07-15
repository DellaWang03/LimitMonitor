from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pandas as pd

from ..common import ProvinceNormalizer, normalize_security_code_series
from ..common.financial_tool_pool import (
    build_financial_tool_pool_sets,
    row_in_financial_tool_pool,
)
from .contracts import _copy_frame


SOURCE_ROW_ID_COL = "_源行号"


def _coerce_numeric_columns(df: pd.DataFrame, columns) -> pd.DataFrame:
    for col in columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _clean_code_like_value(value):
    if pd.isna(value):
        return None
    text = str(value).strip()
    if text in {"", "nan", "None", "<NA>"}:
        return None
    return text


def validate_source_row_id(df: pd.DataFrame, table_name: str) -> None:
    if SOURCE_ROW_ID_COL not in df.columns:
        raise KeyError(f"{table_name} 缺少 {SOURCE_ROW_ID_COL}，无法安全保留真实重复持仓")
    if df[SOURCE_ROW_ID_COL].isna().any():
        raise ValueError(f"{table_name} 的 {SOURCE_ROW_ID_COL} 存在空值")
    duplicated = df[df[SOURCE_ROW_ID_COL].duplicated(keep=False)]
    if not duplicated.empty:
        sample_ids = duplicated[SOURCE_ROW_ID_COL].drop_duplicates().head(5).tolist()
        raise ValueError(f"{table_name} 的 {SOURCE_ROW_ID_COL} 不唯一，示例: {sample_ids}")


def ensure_source_row_id(df: pd.DataFrame, table_name: str) -> pd.DataFrame:
    result = _copy_frame(df)
    if SOURCE_ROW_ID_COL not in result.columns:
        result = result.reset_index(drop=True).copy()
        result[SOURCE_ROW_ID_COL] = np.arange(1, len(result) + 1, dtype="int64")
    validate_source_row_id(result, table_name)
    return result


def collapse_credit_merged_to_source_rows(df: pd.DataFrame) -> pd.DataFrame:
    result = _copy_frame(df)
    if SOURCE_ROW_ID_COL not in result.columns:
        raise KeyError(f"债券持仓明细表_信用债_合并风险限额相关 缺少 {SOURCE_ROW_ID_COL}")
    if result[SOURCE_ROW_ID_COL].isna().any():
        raise ValueError(f"债券持仓明细表_信用债_合并风险限额相关 的 {SOURCE_ROW_ID_COL} 存在空值")

    duplicated = result[result[SOURCE_ROW_ID_COL].duplicated(keep=False)]
    if duplicated.empty:
        return result

    conflicts = []
    check_cols = [col for col in result.columns if col != SOURCE_ROW_ID_COL]
    for source_id, group in duplicated.groupby(SOURCE_ROW_ID_COL, sort=False):
        for col in check_cols:
            values = group[col].dropna()
            if values.empty:
                continue
            if values.dtype == object or pd.api.types.is_string_dtype(values):
                values = values.astype(str).str.strip()
                values = values[~values.isin(["", "nan", "None", "<NA>"])]
                if values.empty:
                    continue
            if values.drop_duplicates().shape[0] > 1:
                conflicts.append(f"{SOURCE_ROW_ID_COL}={source_id}, 字段={col}")
                break
        if len(conflicts) >= 10:
            break

    if conflicts:
        raise ValueError(
            "合并风险限额相关出现同一源持仓的冲突展开，已中止以避免静默取错值；"
            f"示例: {conflicts}"
        )

    priority_cols = [col for col in result.columns if col != SOURCE_ROW_ID_COL]
    result["_非空字段数"] = result[priority_cols].notna().sum(axis=1)
    if "实际控制人名称_修正" in result.columns:
        result["_实控人非空"] = result["实际控制人名称_修正"].notna()
        result = result.sort_values(
            by=[SOURCE_ROW_ID_COL, "_非空字段数", "_实控人非空"],
            ascending=[True, False, False],
        )
        result = result.drop(columns=["_非空字段数", "_实控人非空"])
    else:
        result = result.sort_values(
            by=[SOURCE_ROW_ID_COL, "_非空字段数"],
            ascending=[True, False],
        )
        result = result.drop(columns=["_非空字段数"])
    return result.drop_duplicates(subset=[SOURCE_ROW_ID_COL], keep="first")


def normalize_bond_position(raw: pd.DataFrame) -> pd.DataFrame:
    df = _copy_frame(raw)
    for col in df.columns:
        if df[col].dtype == "object" or pd.api.types.is_string_dtype(df[col]):
            df[col] = df[col].astype(str).str.strip()
    if "日期" in df.columns:
        df["日期"] = pd.to_datetime(df["日期"])

    selected_cols = [
        "日期",
        "金融资产会计属性",
        "部门",
        "内部证券账户名称",
        "资产代码",
        "资产名称",
        "库存数量(万)",
        "库存数量(万)_空头为负",
        "债券分类2",
        "主证券代码",
        "主证券名称",
        "库存数量(万)_PR",
        "债券余额(亿)",
        "债务主体wind代码",
        "担保人wind代码",
    ]
    df = df[[col for col in selected_cols if col in df.columns]]
    df = _coerce_numeric_columns(
        df,
        ["库存数量(万)", "库存数量(万)_空头为负", "库存数量(万)_PR", "债券余额(亿)"],
    )
    if "资产代码" in df.columns:
        df["资产代码_标准"] = normalize_security_code_series(df["资产代码"])
    if "主证券代码" in df.columns:
        df["主证券代码_标准"] = normalize_security_code_series(df["主证券代码"])
    return df


def _clean_sppi_strings(raw: pd.DataFrame) -> pd.DataFrame:
    df = _copy_frame(raw)
    controller_cols = ["实际控制人名称", "实际控制人名称_修正"]
    for col in df.columns:
        if df[col].dtype == "object" or pd.api.types.is_string_dtype(df[col]):
            if col in controller_cols:
                df[col] = df[col].apply(
                    lambda x: str(x).strip()
                    if pd.notna(x) and str(x).strip() not in ["", "nan", "None"]
                    else None
                )
            else:
                df[col] = df[col].astype(str).str.strip()
    if "日期" in df.columns:
        df["日期"] = pd.to_datetime(df["日期"], errors="coerce")
    return df


def normalize_credit_position(raw: pd.DataFrame) -> pd.DataFrame:
    df = _clean_sppi_strings(raw)
    selected_cols = [
        "日期",
        "金融资产会计属性",
        "部门",
        "内部证券账户名称",
        "资产代码",
        "ISIN码",
        "资产名称",
        "债券分类2",
        "债券类型1",
        "主证券代码",
        "主证券名称",
        "库存数量(万)_PR",
        "债券余额(亿)",
        "发行人类型",
        "债务主体",
        "债务主体wind代码",
        "实际控制人名称",
        "实际控制人名称_修正",
        "担保人",
        "担保人wind代码",
        "是否城投债",
        "债券类别",
        "wind行业",
        "省份",
        "合并辅助列",
    ]
    df = df[[col for col in selected_cols if col in df.columns]]
    df = df[df["债券分类2"] != "利率债"]
    if "内部证券账户名称" in df.columns:
        df = df[~df["内部证券账户名称"].str.contains("代申购代缴款", na=False)]
    df = df[df["日期"].notna()]
    df = _coerce_numeric_columns(df, ["库存数量(万)_PR", "债券余额(亿)"])
    if "资产代码" in df.columns:
        df["资产代码_标准"] = normalize_security_code_series(df["资产代码"])
    if "主证券代码" in df.columns:
        df["主证券代码_标准"] = normalize_security_code_series(df["主证券代码"])
    if "省份" in df.columns:
        df = ProvinceNormalizer.add_normalized_column(
            df,
            source_column="省份",
            target_column="省份_标准",
        )
        df["省份"] = df["省份_标准"]
        df = df.drop(columns=["省份_标准"], errors="ignore")
    return ensure_source_row_id(df, "债券持仓明细表_信用债")


def normalize_regulatory_position(raw: pd.DataFrame) -> pd.DataFrame:
    df = _clean_sppi_strings(raw)
    selected_cols = [
        "日期",
        "金融资产会计属性",
        "部门",
        "内部证券账户名称",
        "资产代码",
        "ISIN码",
        "资产名称",
        "债券分类2",
        "债券类型1",
        "主证券代码",
        "主证券名称",
        "库存数量(万)_PR",
        "债券余额(亿)",
        "发行人类型",
        "债务主体",
        "债务主体wind代码",
        "实际控制人名称",
        "实际控制人名称_修正",
        "担保人",
        "担保人wind代码",
        "是否城投债",
        "债券类别",
        "wind行业",
        "省份",
    ]
    df = df[[col for col in selected_cols if col in df.columns]]
    df = df[df["日期"].notna()].copy()
    df = _coerce_numeric_columns(df, ["库存数量(万)_PR", "债券余额(亿)"])
    if "资产代码" in df.columns:
        df["资产代码_标准"] = normalize_security_code_series(df["资产代码"])
    if "主证券代码" in df.columns:
        df["主证券代码_标准"] = normalize_security_code_series(df["主证券代码"])
    if "省份" in df.columns:
        df = ProvinceNormalizer.add_normalized_column(
            df,
            source_column="省份",
            target_column="省份_标准",
        )
        df["省份"] = df["省份_标准"]
        df = df.drop(columns=["省份_标准"], errors="ignore")
    return df


def build_credit_risk_context(frames: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    if "债券持仓明细表_信用债" not in frames:
        raise KeyError("共同内核缺少必需输入表: 债券持仓明细表_信用债")
    detached = {name: _copy_frame(frame) for name, frame in frames.items()}
    df = ensure_source_row_id(detached["债券持仓明细表_信用债"], "债券持仓明细表_信用债")
    source_row_count = len(df)
    source_inventory_sum = pd.to_numeric(
        df.get("库存数量(万)_PR", pd.Series(dtype=float)), errors="coerce"
    ).sum()

    df_high_yield = detached.get("穿透高收益债券")
    if df_high_yield is not None and "债券代码" in df_high_yield.columns:
        df = df.merge(
            df_high_yield[["债券代码", "类型"]],
            left_on="资产代码",
            right_on="债券代码",
            how="left",
        )
        df = df.drop(columns=["债券代码"], errors="ignore")
    if "类型" not in df.columns:
        df["类型"] = pd.NA

    tool_pool_names, tool_pool_codes = build_financial_tool_pool_sets(
        detached.get("金融工具池设置")
    )

    def is_high_yield(row):
        if "高收益" in str(row.get("内部证券账户名称", "")):
            return "是"
        if row.get("类型") == "高收益":
            return "是"
        if row_in_financial_tool_pool(row, tool_pool_names, tool_pool_codes):
            return "是"
        return "否"

    df["是否属于高收益"] = df.apply(is_high_yield, axis=1)
    df = df.drop(columns=["类型"], errors="ignore")

    df_rating = detached.get("中债隐含评级AAA&AAA+")
    if df_rating is not None and "wind代码" in df_rating.columns and "日期" in df_rating.columns:
        df = df.merge(
            df_rating[["wind代码", "日期", "中债隐含评级"]],
            left_on=["债务主体wind代码", "日期"],
            right_on=["wind代码", "日期"],
            how="left",
        )
        df = df.drop(columns=["wind代码"], errors="ignore")

    df_bond_pool = detached.get("风控部债券池")
    if df_bond_pool is not None:
        df = df.merge(
            df_bond_pool[["代码", "日期", "债券池", "主体池"]],
            left_on=["资产代码", "日期"],
            right_on=["代码", "日期"],
            how="left",
            suffixes=("", ".0"),
        )
        df = df.drop(columns=["代码"], errors="ignore")

    df_issuer_pool = detached.get("风控部主体池")
    if df_issuer_pool is not None:
        if "主体池" in df.columns:
            df = df.rename(columns={"主体池": "主体池.0"})
        df = df.merge(
            df_issuer_pool[["日期", "发行人名称", "主体池"]],
            left_on=["日期", "债务主体"],
            right_on=["日期", "发行人名称"],
            how="left",
        )
        df = df.drop(columns=["发行人名称"], errors="ignore")
        df = df.drop_duplicates()
        if "主体池" in df.columns and "主体池.0" in df.columns:
            df["主体池"] = df["主体池"].where(df["主体池"].notna(), df["主体池.0"])
            df = df.drop(columns=["主体池.0"], errors="ignore")
        elif "主体池.0" in df.columns:
            df = df.rename(columns={"主体池.0": "主体池"})

    if df_issuer_pool is not None and "担保人wind代码" in df.columns:
        df_issuer_pool_valid = df_issuer_pool[df_issuer_pool["主体wind代码"].notna()].copy()
        df = df.merge(
            df_issuer_pool_valid[["日期", "主体wind代码", "主体池"]],
            left_on=["日期", "担保人wind代码"],
            right_on=["日期", "主体wind代码"],
            how="left",
            suffixes=("", "_担保"),
        )
        df = df.drop(columns=["主体wind代码"], errors="ignore")

    for col in ["债券池", "主体池", "主体池_担保"]:
        if col in df.columns:
            df[col] = df[col].replace("", None)
    df = df.drop_duplicates()

    df_issuer_type = detached.get("发行人类型调整表")
    if df_issuer_type is not None:
        df = df.merge(
            df_issuer_type[["wind代码", "发行人类型"]],
            left_on="债务主体wind代码",
            right_on="wind代码",
            how="left",
            suffixes=("", ".1"),
        )
        df = df.drop(columns=["wind代码"], errors="ignore")
        if "发行人类型.1" in df.columns:
            df["发行人类型_调整"] = df["发行人类型.1"].fillna(df.get("发行人类型", ""))
            df = df.drop(columns=["发行人类型.1"], errors="ignore")

    df_controller = detached.get("调整实控人名单")
    if df_controller is not None and "主体wind代码" in df_controller.columns:
        if "债务主体wind代码" in df.columns:
            df["_债务主体wind代码_标准"] = df["债务主体wind代码"].astype(str).str.strip()
            df["_债务主体wind代码_标准"] = df["_债务主体wind代码_标准"].str.split(".").str[0]
            df["_债务主体wind代码_标准"] = df["_债务主体wind代码_标准"].apply(
                lambda x: None if x in ["nan", "None", ""] else x
            )
        df = df.merge(
            df_controller[["主体wind代码", "调整后实际控制人"]],
            left_on="_债务主体wind代码_标准",
            right_on="主体wind代码",
            how="left",
        )
        df = df.drop(columns=["主体wind代码", "_债务主体wind代码_标准"], errors="ignore")

    df_guarantee_limit = detached.get("单一担保公司规模限额")
    if df_guarantee_limit is not None and "担保人wind代码" in df.columns:
        df = df.merge(
            df_guarantee_limit[["日期", "指标名称", "是否准入"]],
            left_on=["日期", "担保人wind代码"],
            right_on=["日期", "指标名称"],
            how="left",
            suffixes=("", "_担保限额"),
        )
        df = df.drop(columns=["指标名称"], errors="ignore")

    if "实际控制人名称_修正" not in df.columns:
        if "实际控制人名称" in df.columns:
            df["实际控制人名称_修正"] = df["实际控制人名称"].copy()
        else:
            df["实际控制人名称_修正"] = pd.Series(dtype=object)
    if "调整后实际控制人" in df.columns:
        df["实际控制人名称_修正"] = df.apply(
            lambda row: row["调整后实际控制人"]
            if pd.notna(row["调整后实际控制人"])
            and str(row["调整后实际控制人"]).strip() not in ["", "nan"]
            else row["实际控制人名称_修正"],
            axis=1,
        )
    if "实际控制人名称" in df.columns:
        df["实际控制人名称_修正"] = df.apply(
            lambda row: row["实际控制人名称"]
            if pd.notna(row["实际控制人名称"])
            and (
                pd.isna(row["实际控制人名称_修正"])
                or str(row["实际控制人名称_修正"]).strip() in ["", "nan"]
            )
            else row["实际控制人名称_修正"],
            axis=1,
        )
    if "实际控制人名称_修正" in df.columns:
        df["实际控制人名称_修正"] = df["实际控制人名称_修正"].apply(
            lambda x: None
            if pd.isna(x) or (isinstance(x, str) and str(x).strip() in ["", "nan"])
            else x
        )

    for col in ["担保人wind代码", "中债隐含评级", "债券池", "主体池", "主体池_担保"]:
        if col in df.columns:
            df[col] = df[col].replace("", None)

    if "担保人" in df.columns:
        df["担保公司是否准入"] = df.apply(
            lambda row: row.get("是否准入")
            if pd.notna(row.get("是否准入"))
            else (
                "担保"
                if pd.notna(row.get("担保人")) and str(row.get("担保人")) != "0"
                else None
            ),
            axis=1,
        )
        df = df.drop(columns=["是否准入"], errors="ignore")

    if "资产代码" in df.columns and "资产名称" in df.columns and "债务主体" in df.columns:
        df["代码/名称/债务主体"] = (
            df["资产代码"].astype(str)
            + "/"
            + df["资产名称"].astype(str)
            + "/"
            + df["债务主体"].astype(str)
        )

    df = collapse_credit_merged_to_source_rows(df)

    df_high_risk_industry = detached.get("高风险行业")
    if df_high_risk_industry is not None and "wind行业" in df.columns:
        df["wind行业"] = df["wind行业"].astype(str).str.strip()
        df = df.merge(
            df_high_risk_industry[["日期", "行业名称", "行业类别"]],
            left_on=["日期", "wind行业"],
            right_on=["日期", "行业名称"],
            how="left",
        )
        df = df.drop(columns=["行业名称"], errors="ignore")

    df_high_risk_province = detached.get("高风险省份")
    if df_high_risk_province is not None and "省份" in df.columns:
        df["省份"] = df["省份"].astype(str).str.strip()
        df = ProvinceNormalizer.add_normalized_column(
            df, source_column="省份", target_column="省份_标准"
        )
        df_high_risk_province = ProvinceNormalizer.add_normalized_column(
            df_high_risk_province,
            source_column="省份名称",
            target_column="省份名称_标准",
        )
        df = df.merge(
            df_high_risk_province[["日期", "省份名称_标准", "省份类别"]],
            left_on=["日期", "省份_标准"],
            right_on=["日期", "省份名称_标准"],
            how="left",
        )
        df = df.drop(columns=["省份_标准", "省份名称_标准"], errors="ignore")

    validate_source_row_id(df, "债券持仓明细表_信用债_合并风险限额相关")
    if len(df) != source_row_count:
        raise ValueError(
            "合并风险限额相关行数与信用债源持仓不一致: "
            f"{len(df)} != {source_row_count}"
        )
    merged_inventory_sum = pd.to_numeric(
        df.get("库存数量(万)_PR", pd.Series(dtype=float)), errors="coerce"
    ).sum()
    if not np.isclose(float(merged_inventory_sum), float(source_inventory_sum), rtol=0, atol=1e-6):
        raise ValueError(
            "合并风险限额相关库存数量合计与信用债源持仓不一致: "
            f"{merged_inventory_sum} != {source_inventory_sum}"
        )
    return df


def attach_isin_to_results(
    results: Mapping[str, pd.DataFrame],
    isin_mapping: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    mapping_df = _copy_frame(isin_mapping)
    updated_results: dict[str, pd.DataFrame] = {}
    for name, df in results.items():
        if not isinstance(df, pd.DataFrame):
            updated_results[name] = df
            continue
        if "资产代码" not in df.columns or mapping_df.empty:
            updated_results[name] = _copy_frame(df)
            continue
        result_df = _copy_frame(df)
        result_df["资产代码"] = result_df["资产代码"].apply(_clean_code_like_value)
        result_df = result_df.merge(
            mapping_df,
            on="资产代码",
            how="left",
            suffixes=("", "_映射"),
        )
        if "ISIN码_映射" in result_df.columns:
            if "ISIN码" in result_df.columns:
                result_df["ISIN码"] = result_df["ISIN码"].apply(_clean_code_like_value)
                result_df["ISIN码"] = result_df["ISIN码"].combine_first(result_df["ISIN码_映射"])
            else:
                result_df["ISIN码"] = result_df["ISIN码_映射"]
            result_df = result_df.drop(columns=["ISIN码_映射"], errors="ignore")
        updated_results[name] = result_df
    return updated_results
