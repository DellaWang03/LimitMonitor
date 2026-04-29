"""
页面5：高风险类明细 - 现代金融看板风格
"""
import streamlit as st
import plotly.express as px
from src.visualization.components.tables import render_data_table
from src.visualization.display_builders import build_page5_high_risk_views


def render(filters: dict, data_loader):
    """渲染高风险类明细页面"""
    # 页面标题
    st.markdown("""
    <div style="margin-bottom: 24px;">
        <h1 style="font-size: 1.75rem; font-weight: 700; color: #0f172a; margin: 0;">
            ⚠️ 高风险类明细
        </h1>
        <p style="font-size: 0.875rem; color: #64748b; margin: 8px 0 0 0;">
            高风险省份及行业的集中度监控
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    with st.spinner("加载数据中..."):
        views = build_page5_high_risk_views(data_loader, filters)
    
    # 使用tabs分隔省份和行业
    tab1, tab2 = st.tabs(["🗺️ 高风险省份集中度", "🏭 高风险行业集中度"])
    
    # ==================== Tab1: 高风险省份 ====================
    with tab1:
        kpi = views["kpis"].get("tab1_province", {})
        province_summary = views["tables"].get("tab1_province_summary")
        if province_summary is not None and len(province_summary) > 0:
            
            # 核心KPI（3个关键指标）
            col1, col2, col3 = st.columns(3)
            
            with col1:
                concentration = float(kpi.get('concentration', 0))
                limit = float(kpi.get('limit', 0))
                st.metric(
                    "🎯 集中度",
                    f"{concentration:.2%}",
                    delta=f"限额: {limit:.2%}",
                    delta_color="normal"
                )
            
            with col2:
                total_position = float(kpi.get('total_position_wan', 0))
                st.metric(
                    "💰 总持仓",
                    f"{total_position:,.2f}万"
                )
            
            with col3:
                remaining = float(kpi.get('remaining_wan', 0))
                is_overlimit = remaining < 0
                status = "⚠️ 超限" if is_overlimit else "✅ 正常"
                st.metric(
                    "状态",
                    status,
                    delta=f"剩余: {remaining:,.2f}万",
                    delta_color="inverse" if is_overlimit else "normal"
                )
            
            st.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)
            
            col_left, col_right = st.columns([1, 1])
            with col_left:
                st.markdown("### 📋 省份明细")
                render_data_table(
                    province_summary,
                    highlight_column='是否超限',
                    height=450,
                    show_summary=True,
                    enable_export=True,
                    export_key="export_page5_province_summary",
                )
            with col_right:
                st.markdown("### 📊 持仓分布")
                fig = px.pie(
                    province_summary.head(10),
                    values='PR后规模(万)',
                    names='省份',
                    title='Top10省份持仓分布',
                    hole=0.4
                )
                fig.update_traces(textposition='inside', textinfo='percent+label')
                st.plotly_chart(fig, width='stretch')
        else:
            st.info("📭 暂无省份集中度明细。请确认 Stage2 高风险省份相关数据已生成。")

    # ==================== Tab2: 高风险行业 ====================
    with tab2:
        kpi = views["kpis"].get("tab2_industry", {})
        industry_summary = views["tables"].get("tab2_industry_summary")
        if industry_summary is not None and len(industry_summary) > 0:
            
            # 核心KPI（3个关键指标）
            col1, col2, col3 = st.columns(3)
            
            with col1:
                concentration = float(kpi.get('concentration', 0))
                limit = float(kpi.get('limit', 0))
                st.metric(
                    "🎯 集中度",
                    f"{concentration:.2%}",
                    delta=f"限额: {limit:.2%}",
                    delta_color="normal"
                )
            
            with col2:
                total_position = float(kpi.get('total_position_wan', 0))
                st.metric(
                    "💰 总持仓",
                    f"{total_position:,.2f}万"
                )
            
            with col3:
                remaining = float(kpi.get('remaining_wan', 0))
                is_overlimit = remaining < 0
                status = "⚠️ 超限" if is_overlimit else "✅ 正常"
                st.metric(
                    "状态",
                    status,
                    delta=f"剩余: {remaining:,.2f}万",
                    delta_color="inverse" if is_overlimit else "normal"
                )
            
            st.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)
            
            col_left, col_right = st.columns([1, 1])
            with col_left:
                st.markdown("### 📋 行业明细")
                render_data_table(
                    industry_summary,
                    highlight_column='是否超限',
                    height=450,
                    show_summary=True,
                    enable_export=True,
                    export_key="export_page5_industry_summary",
                )
            with col_right:
                st.markdown("### 📊 持仓分布")
                fig = px.bar(
                    industry_summary.head(10),
                    x='行业',
                    y='PR后规模(万)',
                    color='状态',
                    title='Top10行业持仓分布',
                    labels={'PR后规模(万)': 'PR后规模(万)', '行业': '行业'},
                    color_discrete_map={'✅ 正常': '#2ecc71', '⚠️ 超限': '#e74c3c'}
                )
                fig.update_layout(xaxis_tickangle=-45)
                st.plotly_chart(fig, width='stretch')
        else:
            st.info("📭 暂无行业集中度明细。请确认 Stage2 高风险行业相关数据已生成。")
