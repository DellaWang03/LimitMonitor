"""
页面7：高收益明细 - 现代金融看板风格
"""
import streamlit as st
from src.visualization.components.tables import render_data_table
from src.visualization.display_builders import build_page7_high_yield_views


def _filter_by_keyword(df, keyword: str, columns: list[str]):
    if df is None or not keyword:
        return df
    mask = False
    for col in columns:
        if col in df.columns:
            mask = mask | df[col].astype(str).str.contains(keyword, na=False, case=False)
    if isinstance(mask, bool):
        return df
    return df[mask]


def render(filters: dict, data_loader):
    """渲染高收益明细页面"""
    # 页面标题
    st.markdown("""
    <div style="margin-bottom: 24px;">
        <h1 style="font-size: 1.75rem; font-weight: 700; color: #0f172a; margin: 0;">
            💰 高收益明细
        </h1>
        <p style="font-size: 0.875rem; color: #64748b; margin: 8px 0 0 0;">
            年度高收益债券投资本金规模监控
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    with st.spinner("加载数据中..."):
        views = build_page7_high_yield_views(data_loader, filters)
    
    # KPI卡片区域
    kpi = views["kpis"].get("main", {})
    total_capital = float(kpi.get("total_capital_wan", 0))
    limit = float(kpi.get("annual_limit_wan", 0))
    remaining = float(kpi.get("remaining_wan", 0))
    usage_rate = float(kpi.get("usage_rate", 0)) * 100
    annual_overlimit = str(kpi.get("annual_overlimit", "否"))
    if limit <= 0:
        st.info("未配置年度高收益限额或限额为 0，顶部概览卡片暂不展示。明细与汇总仍可按实际数据展示。")

    if limit > 0:
        thresholds = data_loader.load_alert_thresholds()
        _warn = thresholds['warning'] * 100
        _over = thresholds['overlimit'] * 100
        is_overlimit = annual_overlimit == "是"
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.markdown(f"""
            <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px;">
                <p style="font-size: 0.7rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; margin: 0 0 8px 0;">全价成本</p>
                <p style="font-size: 1.75rem; font-weight: 700; color: #3b82f6; margin: 0;">{total_capital/10000:,.2f}</p>
                <p style="font-size: 0.75rem; color: #94a3b8; margin: 4px 0 0 0;">亿元</p>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            st.markdown(f"""
            <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px;">
                <p style="font-size: 0.7rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; margin: 0 0 8px 0;">限额</p>
                <p style="font-size: 1.75rem; font-weight: 700; color: #1e293b; margin: 0;">{limit/10000:,.0f}</p>
                <p style="font-size: 0.75rem; color: #94a3b8; margin: 4px 0 0 0;">亿元</p>
            </div>
            """, unsafe_allow_html=True)
        
        with col3:
            remaining_color = "#ef4444" if is_overlimit else "#22c55e"
            remaining_bg = "#fef2f2" if is_overlimit else "#f0fdf4"
            st.markdown(f"""
            <div style="background: {remaining_bg}; border: 1px solid {'#fecaca' if is_overlimit else '#bbf7d0'}; border-radius: 12px; padding: 20px;">
                <p style="font-size: 0.7rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; margin: 0 0 8px 0;">剩余额度</p>
                <p style="font-size: 1.75rem; font-weight: 700; color: {remaining_color}; margin: 0;">{remaining/10000:,.2f}</p>
                <p style="font-size: 0.75rem; color: {remaining_color}; margin: 4px 0 0 0;">亿元</p>
            </div>
            """, unsafe_allow_html=True)
        
        with col4:
            usage_color = "#22c55e" if usage_rate < _warn else ("#eab308" if usage_rate < _over else "#ef4444")
            st.markdown(f"""
            <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px;">
                <p style="font-size: 0.7rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; margin: 0 0 8px 0;">使用率</p>
                <p style="font-size: 1.75rem; font-weight: 700; color: {usage_color}; margin: 0;">{usage_rate:.1f}%</p>
                <p style="font-size: 0.75rem; color: #94a3b8; margin: 4px 0 0 0;">{'正常' if usage_rate < _warn else ('警戒' if usage_rate < _over else '超限')}</p>
            </div>
            """, unsafe_allow_html=True)
    
    st.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)
    
    # 标签页
    tab1, tab2 = st.tabs(["持仓明细", "持仓汇总分析"])
    
    with tab1:
        tab1_df = views["tables"].get("tab1_capital_detail")
        if tab1_df is not None and len(tab1_df) > 0:
            search_keyword = st.text_input(
                "搜索",
                placeholder="🔍 输入账户或资产名称...",
                key="high_yield_search",
                label_visibility="collapsed"
            )
            tab1_df = _filter_by_keyword(tab1_df, search_keyword, ["账户", "资产名称"])
            if len(tab1_df) > 0:
                render_data_table(
                    tab1_df,
                    highlight_column="是否超限",
                    height=450,
                    show_summary=True,
                    enable_export=True,
                    export_key="export_page7_high_yield_capital",
                )
            else:
                st.info("📭 当前搜索条件下暂无持仓明细。")
        else:
            st.info("📭 暂无持仓明细。请确认 Stage2 高收益投资本金数据已生成。")

    with tab2:
        summary_search = st.text_input(
            "搜索",
            placeholder="🔍 输入代码、资产名称或债务主体...",
            key="high_yield_summary_search",
            label_visibility="collapsed"
        )
        asset_summary = views["tables"].get("tab2_asset_summary")
        issuer_summary = views["tables"].get("tab2_issuer_summary")
        filtered_asset_summary = _filter_by_keyword(
            asset_summary,
            summary_search,
            ["代码", "资产名称", "债务主体"],
        )
        filtered_issuer_summary = issuer_summary
        if summary_search and issuer_summary is not None and len(issuer_summary) > 0:
            matched_subjects = []
            if (
                filtered_asset_summary is not None
                and len(filtered_asset_summary) > 0
                and "债务主体" in filtered_asset_summary.columns
            ):
                matched_subjects = filtered_asset_summary["债务主体"].dropna().astype(str).unique().tolist()
            if matched_subjects and "债务主体" in issuer_summary.columns:
                filtered_issuer_summary = issuer_summary[
                    issuer_summary["债务主体"].astype(str).isin(matched_subjects)
                ]
            else:
                filtered_issuer_summary = _filter_by_keyword(
                    issuer_summary,
                    summary_search,
                    ["债务主体"],
                )

        col_left, col_right = st.columns([1, 1])
        
        with col_left:
            st.markdown("#### 按资产名称汇总")
            if asset_summary is not None and len(asset_summary) > 0:
                if filtered_asset_summary is not None and len(filtered_asset_summary) > 0:
                    render_data_table(
                        filtered_asset_summary,
                        highlight_column="是否超限",
                        height=350,
                        show_summary=True,
                        enable_export=True,
                        export_key="export_page7_high_yield_asset",
                    )
                else:
                    st.info("📭 当前搜索条件下暂无按资产汇总数据。")
            else:
                st.info("📭 暂无按资产汇总数据。")

        with col_right:
            st.markdown("#### 按债务主体汇总")
            if issuer_summary is not None and len(issuer_summary) > 0:
                if filtered_issuer_summary is not None and len(filtered_issuer_summary) > 0:
                    render_data_table(
                        filtered_issuer_summary,
                        highlight_column="是否超限",
                        height=350,
                        show_summary=True,
                        enable_export=True,
                        export_key="export_page7_high_yield_issuer",
                    )
                else:
                    st.info("📭 当前搜索条件下暂无按债务主体汇总数据。")
            else:
                st.info("📭 暂无按债务主体汇总数据。")
