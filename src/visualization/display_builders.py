"""
展示构造层：页面与快照复用同一套最终展示对象构造逻辑。
"""

from __future__ import annotations

from typing import Any, Dict, List
import pandas as pd

from src.visualization.bond_quota_query import query_bond_remaining_quota


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _apply_filters(df: pd.DataFrame, filters: dict | None) -> pd.DataFrame:
    """无 Streamlit 依赖版本的筛选逻辑（与 filters.apply_filters 一致）。"""
    filtered_df = df.copy()
    if not filters:
        return filtered_df

    if filters.get("bond_type") and filters["bond_type"] != "全部" and "债券分类2" in filtered_df.columns:
        filtered_df = filtered_df[filtered_df["债券分类2"] == filters["bond_type"]]
    if filters.get("account") and filters["account"] != "全部" and "内部证券账户名称" in filtered_df.columns:
        filtered_df = filtered_df[filtered_df["内部证券账户名称"] == filters["account"]]

    if filters.get("search_keyword"):
        keyword = str(filters["search_keyword"]).lower()
        search_columns = [
            "代码", "ISIN码", "资产代码", "资产名称", "证券名称",
            "债务主体", "实际控制人名称_修正", "调整后实际控制人", "担保人",
        ]
        mask = False
        for col in search_columns:
            if col in filtered_df.columns:
                mask = mask | filtered_df[col].astype(str).str.lower().str.contains(keyword, na=False)
        if not (isinstance(mask, bool) and not mask):
            filtered_df = filtered_df[mask]

    quality_field = filters.get("quality_field")
    if filters.get("quality") and filters["quality"] != "全部" and quality_field and quality_field in filtered_df.columns:
        filtered_df = filtered_df[filtered_df[quality_field] == filters["quality"]]

    mapping = {
        "high_risk_industry": "高风险行业是否超限",
        "high_risk_province": "高风险省份是否超限",
        "regional_concentration": "地域集中度是否超限",
        "citybond_concentration": "城投集中度是否超限",
    }
    for key, col in mapping.items():
        if filters.get(key) and filters[key] != "全部" and col in filtered_df.columns:
            filtered_df = filtered_df[filtered_df[col] == filters[key]]

    return filtered_df


def _aggregate_by_asset_and_account(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    group_keys = ["日期", "资产代码", "内部证券账户名称"]
    sum_columns = {"库存数量(万)_PR"}
    ignored_columns = {"合并辅助列"}
    if df.empty or any(col not in df.columns for col in group_keys):
        return df, 0

    duplicate_mask = df.duplicated(group_keys, keep=False)
    dup = df[duplicate_mask]
    non_dup = df[~duplicate_mask]
    if dup.empty:
        return df.copy(), 0

    aggregated_rows = []
    unresolved = []
    for _, grp in dup.groupby(group_keys, sort=False, dropna=False):
        varying = [
            col for col in grp.columns
            if col not in group_keys and col not in sum_columns and col not in ignored_columns
            and grp[col].nunique(dropna=False) > 1
        ]
        if varying:
            unresolved.append(grp)
            continue
        row = grp.iloc[0].copy()
        row["库存数量(万)_PR"] = grp["库存数量(万)_PR"].sum()
        aggregated_rows.append(row)

    parts = [non_dup]
    if aggregated_rows:
        parts.append(pd.DataFrame(aggregated_rows))
    if unresolved:
        parts.append(pd.concat(unresolved, ignore_index=True))
    return pd.concat(parts, ignore_index=True), len(unresolved)


def _load_high_yield_limits_from_loader(data_loader) -> tuple[dict, dict]:
    """从配置读取高收益限额：返回(债券限额映射, 主体限额映射)。"""
    bond_limits = {"__default__": 5000.0}
    entity_limits = {"__default__": 7000.0}

    try:
        from src.utils.config_loader import ConfigLoader

        config = ConfigLoader(str(data_loader.project_root / "config"))
        source_file = config.get_data_file_path("限额监控_阶段0_指标设置.xlsx")
        df = pd.read_excel(str(source_file), sheet_name="高收益限额")
        if "指标" not in df.columns or "限额(万)" not in df.columns:
            return bond_limits, entity_limits

        for _, row in df.iterrows():
            indicator = str(row["指标"]).strip()
            limit_val = row["限额(万)"]
            if pd.isna(limit_val):
                continue
            limit_val = float(limit_val)
            if indicator == "单一债券票面规模":
                bond_limits["__default__"] = limit_val
            elif indicator == "单一主体票面规模":
                entity_limits["__default__"] = limit_val
            elif indicator not in ("年度高收益债券投资本金规模",):
                bond_limits[indicator] = limit_val
                entity_limits[indicator] = limit_val
    except Exception:
        pass

    return bond_limits, entity_limits


def _calc_overlimit_status(remaining: float, limit: float) -> str:
    if remaining < 0:
        return "是"
    if limit > 0 and (limit - remaining) / limit >= 0.5:
        return "预警"
    return "否"


def _build_common_kpi(df: pd.DataFrame, overlimit_col: str, position_col: str = "PR后规模(万)") -> dict:
    total_count = len(df)
    overlimit_count = 0
    if overlimit_col in df.columns:
        overlimit_count = int((df[overlimit_col] == "是").sum())
    normal_count = total_count - overlimit_count
    total_position = _safe_float(df[position_col].sum()) if position_col in df.columns else 0.0
    return {
        "total_count": int(total_count),
        "overlimit_count": int(overlimit_count),
        "normal_count": int(normal_count),
        "total_position_wan": float(total_position),
    }


def _merge_on_keys(base: pd.DataFrame, append_df: pd.DataFrame, keys: list[str], append_cols: list[str]) -> pd.DataFrame:
    if base.empty or append_df.empty:
        return base
    join_keys = [k for k in keys if k in base.columns and k in append_df.columns]
    if not join_keys:
        return base

    existing = set(base.columns)
    cols = [c for c in append_cols if c in append_df.columns and c not in existing and c not in join_keys]
    if not cols:
        return base

    slim = append_df[join_keys + cols].drop_duplicates(subset=join_keys, keep="first")
    return base.merge(slim, on=join_keys, how="left")


def _ensure_column_order(df: pd.DataFrame, expected_cols: list[str]) -> pd.DataFrame:
    out = df.copy()
    for col in expected_cols:
        if col not in out.columns:
            out[col] = pd.NA
    return out[expected_cols]


def build_page1_single_credit_views(data_loader, filters: dict | None = None) -> dict:
    df_1_2 = data_loader.load_stage1_credit_1_2()
    filtered = _apply_filters(df_1_2, filters or {})
    aggregated, unresolved_groups = _aggregate_by_asset_and_account(filtered)

    tab_specs = [
        (
            "tab1_single_bond",
            "单一债券是否超限",
            [
                "日期", "代码", "资产名称", "内部证券账户名称", "债务主体",
                "库存数量(万)_PR", "单一债券规模限额适用类别", "单一债券规模限额指标值",
                "单一债券总持仓_PR", "单一债券规模剩余额度(万)", "单一债券是否超限", "是否超限",
            ],
        ),
        (
            "tab2_concentration",
            "单一债券集中度是否超限",
            [
                "日期", "代码", "资产名称", "内部证券账户名称", "债务主体",
                "库存数量(万)_PR", "单一债券集中度限额适用类别", "单一债券集中度限额指标值",
                "单一债券集中度", "单一债券集中度剩余额度(万)", "单一债券集中度是否超限", "是否超限",
            ],
        ),
        (
            "tab3_entity",
            "单一主体是否超限",
            [
                "日期", "代码", "资产名称", "内部证券账户名称", "债务主体",
                "库存数量(万)_PR", "单一主体限额适用类别", "单一主体规模限额指标值",
                "单一主体总持仓_PR", "单一主体规模剩余额度(万)", "单一主体是否超限", "是否超限",
            ],
        ),
        (
            "tab4_controller",
            "单一实控人是否超限",
            [
                "日期", "代码", "资产名称", "内部证券账户名称", "债务主体",
                "实际控制人名称_修正", "库存数量(万)_PR", "单一实控人限额适用类别",
                "单一实控人规模限额指标值", "单一实控人总持仓_PR", "单一实控人规模剩余额度(万)",
                "单一实控人是否超限", "是否超限",
            ],
        ),
        (
            "tab5_guarantor",
            "单一担保人是否超限",
            [
                "日期", "代码", "资产名称", "内部证券账户名称", "债务主体", "担保人",
                "库存数量(万)_PR", "单一担保公司规模限额", "单一担保人总持仓_PR",
                "单一担保公司规模剩余额度(万)", "单一担保人是否超限", "是否超限",
            ],
        ),
    ]

    tables = {}
    kpis = {}
    for tab_name, overlimit_col, cols in tab_specs:
        use_cols = [c for c in cols if c in aggregated.columns]
        table = aggregated[use_cols].rename(columns={"库存数量(万)_PR": "PR后规模(万)"}).copy()
        tables[tab_name] = table
        kpis[tab_name] = _build_common_kpi(table, overlimit_col)

    return {
        "tables": tables,
        "kpis": kpis,
        "meta": {"unresolved_groups": int(unresolved_groups)},
    }


def build_page2_specific_credit_views(data_loader, filters: dict | None = None) -> dict:
    df = _apply_filters(data_loader.load_stage1_credit_1_1(), filters or {})
    aggregated, unresolved_groups = _aggregate_by_asset_and_account(df)

    tab1_cols = [
        "日期", "代码", "资产名称", "内部证券账户名称", "债务主体", "库存数量(万)_PR",
        "特定主体限额名称", "特定主体限额指标值", "特定主体总持仓", "特定主体限额剩余额度",
        "特定主体限额是否超限", "是否超限",
    ]
    tab2_cols = [
        "日期", "代码", "资产名称", "内部证券账户名称", "债务主体", "实际控制人名称_修正",
        "库存数量(万)_PR", "特定实控人限额名称", "特定实控人限额指标值", "特定实控人总持仓",
        "特定实控人限额剩余额度", "特定实控人限额是否超限", "是否超限",
    ]

    tab1 = aggregated[[c for c in tab1_cols if c in aggregated.columns]].rename(
        columns={"库存数量(万)_PR": "PR后规模(万)"}
    )
    tab2 = aggregated[[c for c in tab2_cols if c in aggregated.columns]].rename(
        columns={"库存数量(万)_PR": "PR后规模(万)"}
    )

    return {
        "tables": {"tab1_specific_entity": tab1, "tab2_specific_controller": tab2},
        "kpis": {
            "tab1_specific_entity": _build_common_kpi(tab1, "特定主体限额是否超限"),
            "tab2_specific_controller": _build_common_kpi(tab2, "特定实控人限额是否超限"),
        },
        "meta": {"unresolved_groups": int(unresolved_groups)},
    }


def build_page3_category_credit_views(data_loader, filters: dict | None = None) -> dict:
    df = _apply_filters(data_loader.load_stage2_credit_2(), filters or {})
    tabs = [
        ("tab1_industry", "高风险行业是否超限", "wind行业"),
        ("tab2_province", "高风险省份是否超限", "省份"),
        ("tab3_regional", "地域集中度是否超限", "省份"),
        ("tab4_citybond", "城投集中度是否超限", "省份"),
    ]
    tables = {}
    kpis = {}
    unresolved_counts: Dict[str, int] = {}

    for tab_name, over_col, dim_col in tabs:
        if over_col not in df.columns:
            tables[tab_name] = pd.DataFrame()
            kpis[tab_name] = _build_common_kpi(pd.DataFrame(), over_col)
            unresolved_counts[tab_name] = 0
            continue
        dim_df = df[df[over_col].notna()].copy()
        dim_df, unresolved = _aggregate_by_asset_and_account(dim_df)
        cols = [
            "日期", "代码", "资产名称", "内部证券账户名称", "债务主体",
            dim_col, "库存数量(万)_PR", over_col, "是否超限",
        ]
        table = dim_df[[c for c in cols if c in dim_df.columns]].rename(
            columns={"库存数量(万)_PR": "PR后规模(万)"}
        )
        tables[tab_name] = table
        kpis[tab_name] = _build_common_kpi(table, over_col)
        unresolved_counts[tab_name] = int(unresolved)

    return {"tables": tables, "kpis": kpis, "meta": {"unresolved_groups": unresolved_counts}}


def export_legacy_page1_single_credit_table(data_loader, filters: dict | None = None) -> pd.DataFrame:
    views = build_page1_single_credit_views(data_loader, filters)
    tables = views.get("tables", {})
    key_cols = ["日期", "代码", "资产名称", "内部证券账户名称", "债务主体"]
    base = tables.get("tab1_single_bond", pd.DataFrame()).copy()
    if base.empty:
        return pd.DataFrame()

    base = _merge_on_keys(base, tables.get("tab2_concentration", pd.DataFrame()), key_cols, [
        "单一债券集中度是否超限", "单一债券集中度限额适用类别", "单一债券集中度限额指标值",
        "单一债券集中度", "单一债券集中度剩余额度(万)",
    ])
    base = _merge_on_keys(base, tables.get("tab3_entity", pd.DataFrame()), key_cols, [
        "单一主体是否超限", "单一主体限额适用类别", "单一主体规模限额指标值",
        "单一主体总持仓_PR", "单一主体规模剩余额度(万)",
    ])
    base = _merge_on_keys(base, tables.get("tab4_controller", pd.DataFrame()), key_cols, [
        "实际控制人名称_修正", "单一实控人是否超限", "单一实控人限额适用类别",
        "单一实控人规模限额指标值", "单一实控人总持仓_PR", "单一实控人规模剩余额度(万)",
    ])
    base = _merge_on_keys(base, tables.get("tab5_guarantor", pd.DataFrame()), key_cols, [
        "担保人", "单一担保人是否超限", "单一担保公司规模限额",
        "单一担保人总持仓_PR", "单一担保公司规模剩余额度(万)",
    ])

    raw = _apply_filters(data_loader.load_stage1_credit_1_2(), filters or {})
    raw, _ = _aggregate_by_asset_and_account(raw)
    base = _merge_on_keys(base, raw, key_cols, ["资产代码", "部门", "是否新老划断"])

    legacy = base.rename(columns={
        "PR后规模(万)": "库存数量(万)_PR",
        "单一债券规模限额指标值": "单一债券规模限额(万)",
        "单一债券总持仓_PR": "单一债券总持仓(万)_PR",
        "单一债券集中度限额指标值": "单一债券集中度限额",
        "单一主体规模限额指标值": "单一主体规模限额(万)",
        "单一实控人规模限额指标值": "单一实控人规模限额",
    })

    expected_cols = [
        "是否超限", "是否新老划断", "部门", "内部证券账户名称", "资产代码", "资产名称", "库存数量(万)_PR",
        "单一债券是否超限", "单一债券规模限额适用类别", "单一债券规模限额(万)", "单一债券总持仓(万)_PR",
        "单一债券规模剩余额度(万)", "单一债券集中度是否超限", "单一债券集中度限额适用类别", "单一债券集中度限额",
        "债券余额(亿)", "单一债券集中度总额度", "单一债券集中度", "单一债券集中度剩余额度(万)",
        "债务主体", "单一主体是否超限", "单一主体限额适用类别", "单一主体规模限额(万)", "单一主体总持仓_PR",
        "单一主体规模剩余额度(万)", "实际控制人名称_修正", "单一实控人是否超限", "单一实控人限额适用类别",
        "单一实控人规模限额", "单一实控人总持仓_PR", "单一实控人规模剩余额度(万)", "担保人", "单一担保人是否超限",
        "单一担保公司规模限额", "单一担保人总持仓_PR", "单一担保公司规模剩余额度(万)",
    ]
    return _ensure_column_order(legacy, expected_cols)


def export_legacy_page2_specific_credit_table(data_loader, filters: dict | None = None) -> pd.DataFrame:
    views = build_page2_specific_credit_views(data_loader, filters)
    tables = views.get("tables", {})
    key_cols = ["日期", "代码", "资产名称", "内部证券账户名称", "债务主体"]
    base = tables.get("tab1_specific_entity", pd.DataFrame()).copy()
    if base.empty:
        return pd.DataFrame()

    base = _merge_on_keys(base, tables.get("tab2_specific_controller", pd.DataFrame()), key_cols, [
        "实际控制人名称_修正", "特定实控人限额名称", "特定实控人限额指标值", "特定实控人总持仓",
        "特定实控人限额剩余额度", "特定实控人限额是否超限",
    ])

    raw = _apply_filters(data_loader.load_stage1_credit_1_1(), filters or {})
    raw, _ = _aggregate_by_asset_and_account(raw)
    base = _merge_on_keys(base, raw, key_cols, ["资产代码", "部门"])

    legacy = base.rename(columns={
        "PR后规模(万)": "库存数量(万)_PR",
        "特定主体限额指标值": "特定主体限额",
        "特定实控人限额指标值": "特定实控人限额",
    })
    expected_cols = [
        "是否超限", "部门", "内部证券账户名称", "资产代码", "资产名称", "库存数量(万)_PR", "债务主体",
        "特定主体限额名称", "特定主体限额是否超限", "特定主体限额", "特定主体总持仓", "特定主体限额剩余额度",
        "实际控制人名称_修正", "特定实控人限额名称", "特定实控人限额是否超限", "特定实控人限额", "特定实控人总持仓", "特定实控人限额剩余额度",
    ]
    return _ensure_column_order(legacy, expected_cols)


def export_legacy_page3_category_credit_table(data_loader, filters: dict | None = None) -> pd.DataFrame:
    views = build_page3_category_credit_views(data_loader, filters)
    tables = views.get("tables", {})
    key_cols = ["日期", "代码", "资产名称", "内部证券账户名称", "债务主体"]

    raw = _apply_filters(data_loader.load_stage2_credit_2(), filters or {})
    raw, _ = _aggregate_by_asset_and_account(raw)
    if raw.empty:
        return pd.DataFrame()

    legacy = raw.copy()
    legacy = _merge_on_keys(legacy, tables.get("tab1_industry", pd.DataFrame()), key_cols, ["高风险行业是否超限"])
    legacy = _merge_on_keys(legacy, tables.get("tab2_province", pd.DataFrame()), key_cols, ["高风险省份是否超限"])
    legacy = _merge_on_keys(legacy, tables.get("tab3_regional", pd.DataFrame()), key_cols, ["地域集中度是否超限"])
    legacy = _merge_on_keys(legacy, tables.get("tab4_citybond", pd.DataFrame()), key_cols, ["城投集中度是否超限"])

    expected_cols = [
        "是否超限", "部门", "内部证券账户名称", "资产代码", "资产名称", "库存数量(万)_PR", "债务主体",
        "wind行业", "行业类别", "高风险行业是否超限", "高风险行业之和集中度限额", "高风险行业集中度", "高风险行业总持仓_PR", "高风险行业集中度剩余额度(万)",
        "省份", "省份类别", "高风险省份是否超限", "高风险省份之和集中度限额", "高风险省份集中度", "高风险省份总持仓_PR", "高风险省份集中度剩余额度(万)",
        "地域集中度是否超限", "地域集中度限额", "地域集中度", "单一地域总持仓_PR", "地域集中度剩余额度(万)",
        "是否城投债", "城投集中度是否超限", "城投集中度限额指标值 ", "城投地域集中度", "单一地域城投总持仓_PR", "城投集中度剩余额度(万)",
    ]
    return _ensure_column_order(legacy, expected_cols)


def build_page4_guarantee_views(data_loader, filters: dict | None = None) -> dict:
    df = data_loader.load_stage1_guarantee()
    if filters:
        df = _apply_filters(df, filters)

    latest_date = df["日期"].max() if "日期" in df.columns and len(df) > 0 else None
    latest_df = df[df["日期"] == latest_date].copy() if latest_date is not None else df.copy()
    total_companies = int(latest_df["授信担保公司名称"].nunique()) if "授信担保公司名称" in latest_df.columns else int(len(latest_df))
    total_position = _safe_float(latest_df["单一担保人总持仓_PR"].sum()) if "单一担保人总持仓_PR" in latest_df.columns else 0.0
    total_limit = _safe_float(latest_df["单一担保公司规模限额"].sum()) if "单一担保公司规模限额" in latest_df.columns else 0.0
    usage_rate = (total_position / total_limit) if total_limit > 0 else 0.0

    display_columns = ["业务分类", "授信担保公司名称", "日期", "单一担保公司规模限额", "单一担保人总持仓_PR", "单一担保公司规模剩余额度(万)"]
    table = df[[c for c in display_columns if c in df.columns]].copy()

    return {
        "tables": {"main": table},
        "kpis": {
            "main": {
                "total_companies": total_companies,
                "total_position_wan": total_position,
                "total_limit_wan": total_limit,
                "usage_rate": usage_rate,
            }
        },
        "meta": {"latest_date": str(latest_date) if latest_date is not None else ""},
    }


def build_page5_high_risk_views(data_loader, filters: dict | None = None) -> dict:
    df_industry = data_loader.load_stage2_high_risk_industry()
    df_province = data_loader.load_stage2_high_risk_province()
    df_province_detail = data_loader.load_stage2_high_risk_province_detail()
    df_industry_detail = data_loader.load_stage2_high_risk_industry_detail()
    df_detail = data_loader.load_stage2_credit_2()
    filtered_detail = _apply_filters(df_detail, filters or {})

    province_table = df_province_detail.rename(columns={"高风险省份总持仓_PR": "PR后规模(万)"}).copy()
    if "省份类别" in filtered_detail.columns:
        p_stats = (
            filtered_detail[filtered_detail["省份类别"] == "高风险省份"]
            .groupby("省份", as_index=False)
            .agg({"资产代码": "count", "高风险省份是否超限": lambda x: int((x == "是").sum())})
            .rename(columns={"资产代码": "债券数", "高风险省份是否超限": "超限数"})
        )
        province_table = province_table.merge(p_stats, on="省份", how="left")
    if "PR后规模(万)" in province_table.columns and len(province_table) > 0:
        total = province_table["PR后规模(万)"].sum()
        province_table["占比"] = province_table["PR后规模(万)"] / total if total else 0
    province_table["债券数"] = province_table.get("债券数", 0).fillna(0).astype(int)
    province_table["超限数"] = province_table.get("超限数", 0).fillna(0).astype(int)
    province_table["状态"] = province_table["超限数"].apply(lambda x: "⚠️ 超限" if x > 0 else "✅ 正常")
    province_table = province_table.sort_values("PR后规模(万)", ascending=False)
    province_table = province_table[[c for c in ["省份", "PR后规模(万)", "占比", "债券数", "超限数", "状态"] if c in province_table.columns]]

    industry_table = df_industry_detail.rename(columns={"wind行业": "行业", "高风险行业总持仓_PR": "PR后规模(万)"}).copy()
    if "行业类别" in filtered_detail.columns:
        i_stats = (
            filtered_detail[filtered_detail["行业类别"] == "高风险行业"]
            .groupby("wind行业", as_index=False)
            .agg({"资产代码": "count", "高风险行业是否超限": lambda x: int((x == "是").sum())})
            .rename(columns={"wind行业": "行业", "资产代码": "债券数", "高风险行业是否超限": "超限数"})
        )
        industry_table = industry_table.merge(i_stats, on="行业", how="left")
    if "PR后规模(万)" in industry_table.columns and len(industry_table) > 0:
        total = industry_table["PR后规模(万)"].sum()
        industry_table["占比"] = industry_table["PR后规模(万)"] / total if total else 0
    industry_table["债券数"] = industry_table.get("债券数", 0).fillna(0).astype(int)
    industry_table["超限数"] = industry_table.get("超限数", 0).fillna(0).astype(int)
    industry_table["状态"] = industry_table["超限数"].apply(lambda x: "⚠️ 超限" if x > 0 else "✅ 正常")
    industry_table = industry_table.sort_values("PR后规模(万)", ascending=False)
    industry_table = industry_table[[c for c in ["行业", "PR后规模(万)", "占比", "债券数", "超限数", "状态"] if c in industry_table.columns]]

    province_kpi_row = df_province.iloc[0] if len(df_province) > 0 else pd.Series(dtype=object)
    industry_kpi_row = df_industry.iloc[0] if len(df_industry) > 0 else pd.Series(dtype=object)
    return {
        "tables": {
            "tab1_province_summary": province_table,
            "tab2_industry_summary": industry_table,
        },
        "kpis": {
            "tab1_province": {
                "concentration": _safe_float(province_kpi_row.get("高风险省份集中度")),
                "limit": _safe_float(province_kpi_row.get("集中度限额")),
                "total_position_wan": _safe_float(province_kpi_row.get("高风险省份总持仓_PR")),
                "remaining_wan": _safe_float(province_kpi_row.get("高风险省份总持仓剩余额度(万)")),
            },
            "tab2_industry": {
                "concentration": _safe_float(industry_kpi_row.get("高风险行业集中度")),
                "limit": _safe_float(industry_kpi_row.get("集中度限额")),
                "total_position_wan": _safe_float(industry_kpi_row.get("高风险行业总持仓_PR")),
                "remaining_wan": _safe_float(industry_kpi_row.get("高风险行业总持仓剩余额度(万)")),
            },
        },
        "meta": {"source_note": "PR后规模来自_2汇总表，债券数/超限数来自信用债2明细"},
    }


def build_page6_regional_views(data_loader, filters: dict | None = None) -> dict:
    df = data_loader.load_stage2_regional()
    if "单一地域总持仓_PR" in df.columns:
        df = df[df["单一地域总持仓_PR"] > 0]

    tab1_cols = [
        "日期", "指标名称", "指标值_地域集中度限额", "单一地域总持仓_PR", "地域集中度",
        "单一地域总持仓剩余额度", "公司净资产(万)", "指标值_城投集中度限额",
        "单一地域城投总持仓_PR", "城投地域集中度", "单一地域城投持仓剩余额度",
    ]
    tab1 = df[[c for c in tab1_cols if c in df.columns]].rename(
        columns={"指标名称": "省份", "指标值_地域集中度限额": "地域集中度限额", "指标值_城投集中度限额": "城投集中度限额"}
    )

    tab2_cols = ["指标名称", "指标值_地域集中度限额", "单一地域总持仓_PR", "地域集中度", "单一地域总持仓剩余额度"]
    tab2 = df[[c for c in tab2_cols if c in df.columns]].rename(
        columns={
            "指标名称": "省份",
            "指标值_地域集中度限额": "地域集中度限额",
            "单一地域总持仓_PR": "PR后规模(万)",
            "地域集中度": "持仓占净资产比",
            "单一地域总持仓剩余额度": "剩余额度(万)",
        }
    )
    if "地域集中度限额" in tab2.columns:
        tab2 = tab2.sort_values("地域集中度限额", ascending=False)
    if "剩余额度(万)" in tab2.columns:
        tab2["是否超限"] = (tab2["剩余额度(万)"] < 0).map({True: "是", False: "否"})

    return {"tables": {"tab1_detail": tab1, "tab2_summary": tab2}, "kpis": {}, "meta": {}}


def build_page7_high_yield_views(data_loader, filters: dict | None = None) -> dict:
    df_hy = data_loader.load_stage2_high_yield()
    df_capital = data_loader.load_stage2_high_yield_capital()
    annual_limit_wan = float(data_loader.load_high_yield_annual_limit())

    total_capital_wan = _safe_float(df_capital["全价成本(元)"].sum()) / 10000 if "全价成本(元)" in df_capital.columns else 0.0
    remaining_wan = annual_limit_wan - total_capital_wan
    usage_rate = (total_capital_wan / annual_limit_wan) if annual_limit_wan > 0 else 0.0

    if {"日期", "资产代码", "内部证券账户名称"}.issubset(df_capital.columns):
        cap_agg, unresolved_groups = _aggregate_by_asset_and_account(df_capital)
    else:
        cap_agg, unresolved_groups = df_capital.copy(), 0

    cap_cols = ["日期", "代码", "简称", "账户", "持仓面额(元)", "全价成本(元)"]
    tab1 = cap_agg[[c for c in cap_cols if c in cap_agg.columns]].copy()
    if "持仓面额(元)" in tab1.columns:
        tab1["PR后规模(万)"] = tab1["持仓面额(元)"] / 10000
    if "全价成本(元)" in tab1.columns:
        tab1["全价成本(万)"] = tab1["全价成本(元)"] / 10000
    tab1 = tab1.drop(columns=["持仓面额(元)", "全价成本(元)"], errors="ignore")

    bond_limits, entity_limits = _load_high_yield_limits_from_loader(data_loader)
    code_col = "代码" if "代码" in df_hy.columns else "资产代码"

    asset_summary = (
        df_hy.groupby([c for c in [code_col, "资产名称"] if c in df_hy.columns], as_index=False)["库存数量(万)_PR"].sum()
        .rename(columns={code_col: "代码", "库存数量(万)_PR": "PR后规模(万)"})
    )
    default_bond_limit = bond_limits["__default__"]
    asset_summary["限额(万)"] = asset_summary["资产名称"].apply(lambda x: bond_limits.get(str(x).strip(), default_bond_limit))
    asset_summary["剩余投资额度(万)"] = asset_summary["限额(万)"] - asset_summary["PR后规模(万)"]
    asset_summary["是否超限"] = asset_summary.apply(
        lambda r: _calc_overlimit_status(float(r["剩余投资额度(万)"]), float(r["限额(万)"])),
        axis=1,
    )
    asset_summary = asset_summary.sort_values("PR后规模(万)", ascending=False)

    issuer_summary = (
        df_hy.groupby("债务主体", as_index=False)["库存数量(万)_PR"].sum()
        .rename(columns={"库存数量(万)_PR": "PR后规模(万)"})
    )
    default_entity_limit = entity_limits["__default__"]
    issuer_summary["限额(万)"] = issuer_summary["债务主体"].apply(lambda x: entity_limits.get(str(x).strip(), default_entity_limit))
    issuer_summary["剩余投资额度(万)"] = issuer_summary["限额(万)"] - issuer_summary["PR后规模(万)"]
    issuer_summary["是否超限"] = issuer_summary.apply(
        lambda r: _calc_overlimit_status(float(r["剩余投资额度(万)"]), float(r["限额(万)"])),
        axis=1,
    )
    issuer_summary = issuer_summary.sort_values("PR后规模(万)", ascending=False)

    return {
        "tables": {
            "tab1_capital_detail": tab1,
            "tab2_asset_summary": asset_summary,
            "tab2_issuer_summary": issuer_summary,
        },
        "kpis": {
            "main": {
                "total_capital_wan": total_capital_wan,
                "annual_limit_wan": annual_limit_wan,
                "remaining_wan": remaining_wan,
                "usage_rate": usage_rate,
            }
        },
        "meta": {"tab1_unresolved_groups": int(unresolved_groups)},
    }


def build_page8_bond_quota_cases(data_loader) -> dict:
    df = data_loader.load_stage1_credit_1_2()
    if df.empty:
        return {"cases": []}
    latest_date = df["日期"].max()
    latest_df = df[df["日期"] == latest_date].copy()
    latest_df["__code__"] = latest_df["资产代码"].astype(str).str.strip()
    latest_df = latest_df[latest_df["__code__"].str.len() > 0]
    case_queries = sorted(latest_df["__code__"].dropna().unique().tolist())[:5]

    cases: List[dict] = []
    for query in case_queries:
        result = query_bond_remaining_quota(data_loader, query, target_date=latest_date)
        if result.get("error"):
            continue
        cases.append({
            "query": query,
            "bond_info": result.get("bond_info", {}),
            "dimensions": result.get("dimensions", []),
            "final_quota_wan": result.get("final_quota_wan", 0.0),
        })

    return {"cases": cases, "meta": {"latest_date": str(latest_date)}}


def build_page9_full_regulatory_views(data_loader) -> dict:
    df = data_loader.load_stage1_full_regulatory_concentration()
    display_columns = [
        "日期", "代码", "资产名称", "债务主体", "债券分类2", "单债总持仓_PR", "债券余额(亿)",
        "监管集中度限额指标值", "监管集中度", "监管集中度剩余额度(万)", "监管集中度是否超限", "是否可计算",
        "内部证券账户覆盖数",
    ]
    table = df[[c for c in display_columns if c in df.columns]].copy()
    total_count = len(table)
    calculable_count = int((table["是否可计算"] == "是").sum()) if "是否可计算" in table.columns else 0
    overlimit_count = int((table["监管集中度是否超限"] == "是").sum()) if "监管集中度是否超限" in table.columns else 0
    total_position_wan = _safe_float(table["单债总持仓_PR"].sum()) if "单债总持仓_PR" in table.columns else 0.0
    return {
        "tables": {"main": table},
        "kpis": {
            "main": {
                "total_count": int(total_count),
                "calculable_count": int(calculable_count),
                "overlimit_count": int(overlimit_count),
                "total_position_wan": float(total_position_wan),
            }
        },
        "meta": {},
    }
