"""
页面6：地域类明细 - 现代金融看板风格
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from src.visualization.components.tables import render_data_table
from src.visualization.display_builders import build_page6_regional_views


def render(filters: dict, data_loader):
    """渲染地域类明细页面"""
    # 页面标题
    st.markdown("""
    <div style="margin-bottom: 24px;">
        <h1 style="font-size: 1.75rem; font-weight: 700; color: #0f172a; margin: 0;">
            🗺️ 地域类明细
        </h1>
        <p style="font-size: 0.875rem; color: #64748b; margin: 8px 0 0 0;">
            各省份地域集中度及城投集中度监控
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    # 加载数据（优化：只加载一次）
    with st.spinner("加载数据中..."):
        views = build_page6_regional_views(data_loader, filters)
    
    # 创建标签页
    tab1, tab2 = st.tabs([
        "地域集中度明细",
        "区域集中度汇总"
    ])
    
    # ==================== Tab1: 地域集中度限额（含城投）明细 ====================
    with tab1:
        st.markdown("### 地域集中度限额（含城投）明细")
        st.caption("各省份地域及城投集中度详细监控数据")
        
        # 省份搜索框（文本输入）
        search_province_tab1 = st.text_input(
            "搜索省份",
            placeholder="🔍 输入省份名称...",
            key="province_search_tab1",
            label_visibility="collapsed"
        )
        
        st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
        
        # 应用省份搜索筛选
        display_df = views["tables"].get("tab1_detail", pd.DataFrame()).copy()
        if search_province_tab1 and '省份' in display_df.columns:
            display_df = display_df[
                display_df['省份'].astype(str).str.contains(search_province_tab1, na=False, case=False)
            ]
        
        display_df_tab1 = display_df.copy()
        
        # 渲染表格
        render_data_table(
            display_df_tab1,
            height=600,
            show_summary=True,
            enable_export=True,
            export_key="export_page6_tab1_detail",
            add_total_row=True,
            total_columns=['单一地域总持仓_PR', '单一地域城投总持仓_PR']
        )
        
        # 可视化
        st.markdown("### 📊 地域持仓分布")
        
        if '省份' in display_df_tab1.columns and '单一地域总持仓_PR' in display_df_tab1.columns:
            col1, col2 = st.columns(2)
            
            with col1:
                # 地域持仓Top10
                top10 = display_df_tab1.nlargest(10, '单一地域总持仓_PR')
                
                fig = px.bar(
                    top10,
                    x='省份',
                    y='单一地域总持仓_PR',
                    title='地域持仓Top10',
                    labels={'单一地域总持仓_PR': 'PR后规模(万)', '省份': '省份'}
                )
                fig.update_layout(xaxis_tickangle=-45)
                st.plotly_chart(fig, width='stretch')
            
            with col2:
                # 城投持仓Top10
                if '单一地域城投总持仓_PR' in display_df_tab1.columns:
                    top10_city = display_df_tab1.nlargest(10, '单一地域城投总持仓_PR')
                    
                    fig2 = px.bar(
                        top10_city,
                        x='省份',
                        y='单一地域城投总持仓_PR',
                        title='城投持仓Top10',
                        labels={'单一地域城投总持仓_PR': 'PR后规模(万)', '省份': '省份'}
                    )
                    fig2.update_layout(xaxis_tickangle=-45)
                    st.plotly_chart(fig2, width='stretch')
    
    # ==================== Tab2: 区域集中度汇总 ====================
    with tab2:
        st.markdown("### 区域集中度汇总")
        st.caption("按地域集中度限额降序排列，汇总显示各省份持仓情况")
        
        # 省份搜索框（文本输入）
        search_province_tab2 = st.text_input(
            "搜索省份",
            placeholder="🔍 输入省份名称...",
            key="province_search_tab2",
            label_visibility="collapsed"
        )
        
        st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
        
        # 应用省份搜索筛选
        summary_base = views["tables"].get("tab2_summary", pd.DataFrame()).copy()
        if search_province_tab2 and '省份' in summary_base.columns:
            summary_base = summary_base[
                summary_base['省份'].astype(str).str.contains(search_province_tab2, na=False, case=False)
            ]
        summary_df = summary_base.copy()
        
        # 渲染汇总表格
        render_data_table(
            summary_df,
            height=600,
            highlight_column='是否超限',
            show_summary=True,
            enable_export=True,
            export_key="export_page6_tab2_summary",
            add_total_row=True,
            total_columns=['PR后规模(万)']
        )
        
        # 可视化 - 集中度对比
        st.markdown("### 📊 集中度分析")
        
        if '省份' in summary_df.columns and '持仓占净资产比' in summary_df.columns and '地域集中度限额' in summary_df.columns:
            col1, col2 = st.columns(2)
            
            with col1:
                # 集中度vs限额对比（Top15）
                top15 = summary_df.head(15).copy()
                
                fig = go.Figure()
                fig.add_trace(go.Bar(
                    x=top15['省份'],
                    y=top15['持仓占净资产比'] * 100,  # 转换为百分比
                    name='实际集中度',
                    marker_color='lightblue'
                ))
                fig.add_trace(go.Bar(
                    x=top15['省份'],
                    y=top15['地域集中度限额'] * 100,  # 转换为百分比
                    name='集中度限额',
                    marker_color='orange'
                ))
                
                fig.update_layout(
                    title='地域集中度 vs 限额对比（Top15）',
                    xaxis_title='省份',
                    yaxis_title='集中度 (%)',
                    barmode='group',
                    xaxis_tickangle=-45
                )
                
                st.plotly_chart(fig, width='stretch')
            
            with col2:
                # 剩余额度分布
                if '剩余额度(万)' in summary_df.columns:
                    # 只显示前15个
                    top15_remaining = summary_df.head(15).copy()
                    
                    # 添加颜色标识（正数绿色，负数红色）
                    top15_remaining['颜色'] = top15_remaining['剩余额度(万)'].apply(
                        lambda x: '正常' if x >= 0 else '超限'
                    )
                    
                    fig2 = px.bar(
                        top15_remaining,
                        x='省份',
                        y='剩余额度(万)',
                        title='剩余额度分布（Top15）',
                        color='颜色',
                        color_discrete_map={'正常': 'green', '超限': 'red'},
                        labels={'剩余额度(万)': '剩余额度(万)', '省份': '省份'}
                    )
                    fig2.update_layout(xaxis_tickangle=-45)
                    st.plotly_chart(fig2, width='stretch')
