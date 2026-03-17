"""
页面6：地域类明细 - 现代金融看板风格
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from src.visualization.components.tables import render_data_table


# Tab1显示列配置
TAB1_DISPLAY_COLUMNS = [
    '日期', '指标名称', '指标值_地域集中度限额', '单一地域总持仓_PR',
    '地域集中度', '单一地域总持仓剩余额度', '公司净资产(万)',
    '指标值_城投集中度限额', '单一地域城投总持仓_PR',
    '城投地域集中度', '单一地域城投持仓剩余额度'
]

TAB1_COLUMN_RENAME = {
    '指标名称': '省份',
    '指标值_地域集中度限额': '地域集中度限额',
    '指标值_城投集中度限额': '城投集中度限额'
}

# Tab2显示列配置
TAB2_SUMMARY_COLUMNS = [
    '指标名称', '指标值_地域集中度限额', '单一地域总持仓_PR',
    '地域集中度', '单一地域总持仓剩余额度'
]

TAB2_COLUMN_RENAME = {
    '指标名称': '省份',
    '指标值_地域集中度限额': '地域集中度限额',
    '单一地域总持仓_PR': '持仓金额(万)',
    '地域集中度': '持仓占净资产比',
    '单一地域总持仓剩余额度': '剩余额度(万)'
}


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
        df = data_loader.load_stage2_regional()
        
        # 过滤掉持仓为0的省份
        if '单一地域总持仓_PR' in df.columns:
            df = df[df['单一地域总持仓_PR'] > 0]
    
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
        display_df = df.copy()
        if search_province_tab1 and '指标名称' in display_df.columns:
            display_df = display_df[
                display_df['指标名称'].astype(str).str.contains(search_province_tab1, na=False, case=False)
            ]
        
        # 直接处理显示数据（避免不必要的缓存和转换开销）
        cols = [c for c in TAB1_DISPLAY_COLUMNS if c in display_df.columns]
        display_df_tab1 = display_df[cols].rename(columns=TAB1_COLUMN_RENAME)
        
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
                    labels={'单一地域总持仓_PR': '持仓(万)', '省份': '省份'}
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
                        labels={'单一地域城投总持仓_PR': '持仓(万)', '省份': '省份'}
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
        summary_base = df.copy()
        if search_province_tab2 and '指标名称' in summary_base.columns:
            summary_base = summary_base[
                summary_base['指标名称'].astype(str).str.contains(search_province_tab2, na=False, case=False)
            ]
        
        # 直接处理汇总数据（避免不必要的缓存和转换开销）
        cols = [c for c in TAB2_SUMMARY_COLUMNS if c in summary_base.columns]
        summary_df = summary_base[cols].rename(columns=TAB2_COLUMN_RENAME)
        
        # 按地域集中度限额降序排列
        if '地域集中度限额' in summary_df.columns:
            summary_df = summary_df.sort_values('地域集中度限额', ascending=False)
        
        # 添加超限标识
        if '剩余额度(万)' in summary_df.columns:
            summary_df['是否超限'] = (summary_df['剩余额度(万)'] < 0).map({True: '是', False: '否'})
        
        # 渲染汇总表格
        render_data_table(
            summary_df,
            height=600,
            highlight_column='是否超限',
            show_summary=True,
            enable_export=True,
            export_key="export_page6_tab2_summary",
            add_total_row=True,
            total_columns=['持仓金额(万)']
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
