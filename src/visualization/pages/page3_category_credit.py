"""
页面3：分类信用限额 - 现代金融看板风格（标签页模式）
"""
import streamlit as st
import pandas as pd
from src.visualization.components.filters import apply_filters
from src.visualization.components.tables import render_data_table


def _render_category_kpi_cards(df, highlight_column):
    """渲染分类维度的KPI卡片"""
    total_count = len(df)
    overlimit_count = 0
    normal_count = total_count
    
    if highlight_column in df.columns:
        overlimit_count = len(df[df[highlight_column] == '是'])
        normal_count = total_count - overlimit_count
    
    total_position = df['库存数量(万)_PR'].sum() if '库存数量(万)_PR' in df.columns else 0
    overlimit_rate = (overlimit_count / total_count * 100) if total_count > 0 else 0
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown(f"""
        <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px;">
            <p style="font-size: 0.7rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; margin: 0 0 8px 0;">总债券数</p>
            <p style="font-size: 1.75rem; font-weight: 700; color: #1e293b; margin: 0;">{total_count:,}</p>
            <p style="font-size: 0.75rem; color: #94a3b8; margin: 4px 0 0 0;">只</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        status_color = "#22c55e" if overlimit_count == 0 else "#ef4444"
        status_bg = "#f0fdf4" if overlimit_count == 0 else "#fef2f2"
        st.markdown(f"""
        <div style="background: {status_bg}; border: 1px solid {'#bbf7d0' if overlimit_count == 0 else '#fecaca'}; border-radius: 12px; padding: 20px;">
            <p style="font-size: 0.7rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; margin: 0 0 8px 0;">超限债券</p>
            <p style="font-size: 1.75rem; font-weight: 700; color: {status_color}; margin: 0;">{overlimit_count}</p>
            <p style="font-size: 0.75rem; color: {status_color}; margin: 4px 0 0 0;">{'无超限' if overlimit_count == 0 else f'超限率 {overlimit_rate:.1f}%'}</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown(f"""
        <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px;">
            <p style="font-size: 0.7rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; margin: 0 0 8px 0;">正常债券</p>
            <p style="font-size: 1.75rem; font-weight: 700; color: #22c55e; margin: 0;">{normal_count:,}</p>
            <p style="font-size: 0.75rem; color: #94a3b8; margin: 4px 0 0 0;">只</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col4:
        st.markdown(f"""
        <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px;">
            <p style="font-size: 0.7rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; margin: 0 0 8px 0;">总持仓</p>
            <p style="font-size: 1.75rem; font-weight: 700; color: #1e293b; margin: 0;">{total_position/10000:,.1f}</p>
            <p style="font-size: 0.75rem; color: #94a3b8; margin: 4px 0 0 0;">亿元</p>
        </div>
        """, unsafe_allow_html=True)


def render(filters: dict, data_loader):
    """渲染分类信用限额页面"""
    # 页面标题
    st.markdown("""
    <div style="margin-bottom: 24px;">
        <h1 style="font-size: 1.75rem; font-weight: 700; color: #0f172a; margin: 0;">
            📑 分类信用限额
        </h1>
        <p style="font-size: 0.875rem; color: #64748b; margin: 8px 0 0 0;">
            按行业、省份、地域和城投维度的集中度监控
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    with st.spinner("加载数据中..."):
        df = data_loader.load_stage2_credit_2()
    
    # 创建标签页（4个维度）
    tab1, tab2, tab3, tab4 = st.tabs([
        "高风险行业",
        "高风险省份",
        "地域集中度",
        "城投集中度"
    ])
    
    # ==================== Tab1: 高风险行业 ====================
    with tab1:
        if '高风险行业是否超限' in df.columns:
            # 筛选该维度数据
            filtered_df = apply_filters(df, filters)
            dimension_df = filtered_df[filtered_df['高风险行业是否超限'].notna()].copy()
            
            # KPI卡片
            _render_category_kpi_cards(dimension_df, '高风险行业是否超限')
            st.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)
            
            # 数据表格
            display_columns = [
                '日期', '内部证券账户名称', '资产代码', '资产名称',
                '债务主体', 'wind行业', '库存数量(万)_PR',
                '高风险行业是否超限', '是否超限'
            ]
            
            display_columns = [col for col in display_columns if col in dimension_df.columns]
            display_df = dimension_df[display_columns]
            
            render_data_table(
                display_df,
                highlight_column='高风险行业是否超限',
                height=450,
                export_key="export_page3_tab1_industry",
                add_total_row=True,
                total_columns=['库存数量(万)_PR']
            )
        else:
            st.info("该维度数据不可用")
    
    # ==================== Tab2: 高风险省份 ====================
    with tab2:
        if '高风险省份是否超限' in df.columns:
            # 筛选该维度数据
            filtered_df = apply_filters(df, filters)
            dimension_df = filtered_df[filtered_df['高风险省份是否超限'].notna()].copy()
            
            # KPI卡片
            _render_category_kpi_cards(dimension_df, '高风险省份是否超限')
            st.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)
            
            # 数据表格
            display_columns = [
                '日期', '内部证券账户名称', '资产代码', '资产名称',
                '债务主体', '省份', '库存数量(万)_PR',
                '高风险省份是否超限', '是否超限'
            ]
            
            display_columns = [col for col in display_columns if col in dimension_df.columns]
            display_df = dimension_df[display_columns]
            
            render_data_table(
                display_df,
                highlight_column='高风险省份是否超限',
                height=450,
                export_key="export_page3_tab2_province",
                add_total_row=True,
                total_columns=['库存数量(万)_PR']
            )
        else:
            st.info("该维度数据不可用")
    
    # ==================== Tab3: 地域集中度 ====================
    with tab3:
        if '地域集中度是否超限' in df.columns:
            # 筛选该维度数据
            filtered_df = apply_filters(df, filters)
            dimension_df = filtered_df[filtered_df['地域集中度是否超限'].notna()].copy()
            
            # KPI卡片
            _render_category_kpi_cards(dimension_df, '地域集中度是否超限')
            st.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)
            
            # 数据表格
            display_columns = [
                '日期', '内部证券账户名称', '资产代码', '资产名称',
                '债务主体', '省份', '库存数量(万)_PR',
                '地域集中度是否超限', '是否超限'
            ]
            
            display_columns = [col for col in display_columns if col in dimension_df.columns]
            display_df = dimension_df[display_columns]
            
            render_data_table(
                display_df,
                highlight_column='地域集中度是否超限',
                height=450,
                export_key="export_page3_tab3_regional",
                add_total_row=True,
                total_columns=['库存数量(万)_PR']
            )
        else:
            st.info("该维度数据不可用")
    
    # ==================== Tab4: 城投集中度 ====================
    with tab4:
        if '城投集中度是否超限' in df.columns:
            # 筛选该维度数据
            filtered_df = apply_filters(df, filters)
            dimension_df = filtered_df[filtered_df['城投集中度是否超限'].notna()].copy()
            
            # KPI卡片
            _render_category_kpi_cards(dimension_df, '城投集中度是否超限')
            st.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)
            
            # 数据表格
            display_columns = [
                '日期', '内部证券账户名称', '资产代码', '资产名称',
                '债务主体', '省份', '库存数量(万)_PR',
                '城投集中度是否超限', '是否超限'
            ]
            
            display_columns = [col for col in display_columns if col in dimension_df.columns]
            display_df = dimension_df[display_columns]
            
            render_data_table(
                display_df,
                highlight_column='城投集中度是否超限',
                height=450,
                export_key="export_page3_tab4_citybond",
                add_total_row=True,
                total_columns=['库存数量(万)_PR']
            )
        else:
            st.info("该维度数据不可用")
