"""
页面7：高收益明细 - 现代金融看板风格
"""
import streamlit as st
from src.visualization.display_builders import build_page7_high_yield_views


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
    if limit > 0:
        thresholds = data_loader.load_alert_thresholds()
        _warn = thresholds['warning'] * 100
        _over = thresholds['overlimit'] * 100
        is_overlimit = remaining < 0
        
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
    tab1, tab2 = st.tabs(["投资本金明细", "持仓汇总分析"])
    
    with tab1:
        tab1_df = views["tables"].get("tab1_capital_detail")
        if tab1_df is not None and len(tab1_df) > 0:
            search_keyword = st.text_input(
                "搜索",
                placeholder="🔍 输入账户、代码或简称...",
                key="high_yield_search",
                label_visibility="collapsed"
            )
            if search_keyword:
                mask = False
                for col in ["账户", "简称", "代码"]:
                    if col in tab1_df.columns:
                        mask = mask | tab1_df[col].astype(str).str.contains(search_keyword, na=False, case=False)
                tab1_df = tab1_df[mask]
            st.dataframe(tab1_df, width='stretch', height=450, hide_index=True)
    
    with tab2:
        col_left, col_right = st.columns([1, 1])
        
        with col_left:
            st.markdown("#### 按资产名称汇总")
            asset_summary = views["tables"].get("tab2_asset_summary")
            if asset_summary is not None and len(asset_summary) > 0:
                st.dataframe(asset_summary, width='stretch', height=350, hide_index=True)
        
        with col_right:
            st.markdown("#### 按债务主体汇总")
            issuer_summary = views["tables"].get("tab2_issuer_summary")
            if issuer_summary is not None and len(issuer_summary) > 0:
                st.dataframe(issuer_summary, width='stretch', height=350, hide_index=True)
