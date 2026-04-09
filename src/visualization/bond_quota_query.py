"""
单券可购额度查询模块
根据信用债1_2与信用债2合并结果，按债券代码/名称查询各维度剩余额度与最终可购额度。
"""
import pandas as pd
from typing import Any, Dict, List, Optional

# 维度名称 -> (剩余额度列名, 是否超限列名)，顺序与计划第1节一致
# 来源：信用债1_2 = Stage1 限额明细_债券持仓明细表_信用债1_2；信用债2 = Stage2 限额明细_债券持仓明细表_信用债2
DIMENSION_MAPPING: List[tuple] = [
    ("单一债券规模", "单一债券规模剩余额度(万)", "单一债券是否超限"),
    ("单一债券集中度", "单一债券集中度剩余额度(万)", "单一债券集中度是否超限"),
    ("单一主体规模", "单一主体规模剩余额度(万)", "单一主体是否超限"),
    ("单一实控人规模", "单一实控人规模剩余额度(万)", "单一实控人是否超限"),
    ("单一担保公司规模", "单一担保公司规模剩余额度(万)", "单一担保人是否超限"),
    ("特定主体限额", "特定主体限额剩余额度", "特定主体限额是否超限"),
    ("特定实控人限额", "特定实控人限额剩余额度", "特定实控人限额是否超限"),
    ("地域集中度", "地域集中度剩余额度(万)", "地域集中度是否超限"),
    ("城投集中度", "城投集中度剩余额度(万)", "城投集中度是否超限"),
    ("高风险行业集中度", "高风险行业集中度剩余额度(万)", "高风险行业是否超限"),
    ("高风险省份集中度", "高风险省份集中度剩余额度(万)", "高风险省份是否超限"),
]

MERGE_KEYS = ["日期", "资产代码", "内部证券账户名称"]


def _normalize_date(d: Any) -> pd.Timestamp:
    """统一为可比较的日期类型"""
    if d is None:
        return d
    if isinstance(d, pd.Timestamp):
        return d.normalize() if hasattr(d, "normalize") else d
    return pd.Timestamp(d).normalize()


def query_bond_remaining_quota(
    data_loader,
    bond_code_or_name: str,
    target_date: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    查询单只债券在各限额维度下的剩余额度与最终可购额度。

    Args:
        data_loader: DataLoader 实例（需有 load_stage1_credit_1_2、load_stage2_credit_2）
        bond_code_or_name: 债券代码或债券名称
        target_date: 查询日期，None 表示使用数据最新日期

    Returns:
        {
            "bond_info": {"资产代码", "资产名称", "债务主体", "日期", "库存数量(万)_PR", ...} 或空,
            "dimensions": [{"维度名称", "剩余额度(万)", "是否超限"}, ...],
            "final_quota_wan": float,
            "error": str  # 仅当未找到债券时存在
        }
    """
    raw = (bond_code_or_name or "").strip()
    if not raw:
        return {"bond_info": {}, "dimensions": [], "final_quota_wan": 0.0, "error": "请输入债券代码或名称"}

    df_1_2 = data_loader.load_stage1_credit_1_2()
    df_2 = data_loader.load_stage2_credit_2()

    if df_1_2.empty:
        return {"bond_info": {}, "dimensions": [], "final_quota_wan": 0.0, "error": "信用债1_2数据为空"}

    # 查询日期
    if target_date is None:
        query_date = _normalize_date(df_1_2["日期"].max())
    else:
        query_date = _normalize_date(target_date)

    # 解析债券：先按资产代码，再按资产名称（代码比较时忽略尾随 .0）
    if "资产代码" not in df_1_2.columns:
        return {"bond_info": {}, "dimensions": [], "final_quota_wan": 0.0, "error": "数据中无资产代码列"}
    codes = df_1_2["资产代码"].astype(str).str.strip()
    codes_normalized = codes.str.replace(r"\.0$", "", regex=True)
    if raw in codes.values:
        resolved_code = raw
    elif raw in codes_normalized.values:
        idx = codes_normalized[codes_normalized == raw].index[0]
        resolved_code = df_1_2.loc[idx, "资产代码"]
    else:
        if "资产名称" in df_1_2.columns:
            name_match = df_1_2["资产名称"].astype(str).str.strip().str.contains(raw, na=False)
            hit = df_1_2.loc[name_match]
            if hit.empty:
                return {"bond_info": {}, "dimensions": [], "final_quota_wan": 0.0, "error": "未找到该债券"}
            resolved_code = hit["资产代码"].iloc[0]
        else:
            return {"bond_info": {}, "dimensions": [], "final_quota_wan": 0.0, "error": "未找到该债券"}
    resolved_code_str = str(resolved_code).strip() if resolved_code is not None else ""

    # 信用债2 中仅合并键 + 剩余额度/是否超限列，避免列名冲突
    credit2_quota_cols = [
        "地域集中度剩余额度(万)", "城投集中度剩余额度(万)",
        "高风险行业集中度剩余额度(万)", "高风险省份集中度剩余额度(万)",
        "地域集中度是否超限", "城投集中度是否超限",
        "高风险行业是否超限", "高风险省份是否超限",
    ]
    right_cols = [c for c in MERGE_KEYS + credit2_quota_cols if c in df_2.columns]
    df_2_sub = df_2[right_cols].drop_duplicates(subset=MERGE_KEYS, keep="first")

    merged = df_1_2.merge(
        df_2_sub,
        on=MERGE_KEYS,
        how="left",
    )

    merged["_日期_norm"] = merged["日期"].apply(_normalize_date)
    merged["_代码_str"] = merged["资产代码"].astype(str).str.strip()
    filtered = merged[
        (merged["_日期_norm"] == query_date) & (merged["_代码_str"] == resolved_code_str)
    ].copy()
    if filtered.empty:
        return {"bond_info": {}, "dimensions": [], "final_quota_wan": 0.0, "error": "未找到该债券"}

    row = filtered.iloc[0]
    valid_remaining: List[float] = []

    dimensions: List[Dict[str, Any]] = []
    for dim_name, col_remaining, col_over in DIMENSION_MAPPING:
        if col_remaining not in row.index:
            dimensions.append({"维度名称": dim_name, "剩余额度(万)": None, "是否超限": "不适用"})
            continue
        val = row[col_remaining]
        if pd.isna(val) or type(val).__name__ == "NAType":
            dimensions.append({"维度名称": dim_name, "剩余额度(万)": None, "是否超限": "不适用"})
            continue
        try:
            v_float = float(val)
        except (TypeError, ValueError):
            # NAType、非数值等无法转为 float 时视为缺失
            dimensions.append({"维度名称": dim_name, "剩余额度(万)": None, "是否超限": "不适用"})
            continue
        valid_remaining.append(v_float)
        if col_over in row.index and pd.notna(row[col_over]):
            over = row[col_over]
            over_str = "是" if over == "是" else "否"
        else:
            over_str = "是" if v_float < 0 else "否"
        dimensions.append({"维度名称": dim_name, "剩余额度(万)": round(v_float, 4), "是否超限": over_str})

    if any(r < 0 for r in valid_remaining):
        final_quota_wan = 0.0
    elif valid_remaining:
        final_quota_wan = max(0.0, min(valid_remaining))
    else:
        final_quota_wan = 0.0

    bond_info = {}
    for k in ["代码", "资产名称", "债务主体", "日期", "库存数量(万)_PR", "内部证券账户名称"]:
        if k in row.index and pd.notna(row[k]):
            bond_info[k] = row[k]
    if "日期" in bond_info and hasattr(bond_info["日期"], "strftime"):
        bond_info["日期"] = bond_info["日期"].strftime("%Y-%m-%d")

    return {
        "bond_info": bond_info,
        "dimensions": dimensions,
        "final_quota_wan": round(final_quota_wan, 4),
    }
