"""
页面1：单一信用限额 - 现代金融看板风格
"""
import streamlit as st
import pandas as pd
from src.visualization.components.filters import apply_filters
from src.visualization.components.tables import render_data_table


def _render_kpi_cards(df, highlight_column, position_column='库存数量(万)_PR', total_column=None):
    """渲染现代KPI卡片"""
    total_count = len(df)
    overlimit_count = 0
    normal_count = total_count
    
    if highlight_column in df.columns:
        overlimit_count = len(df[df[highlight_column] == '是'])
        normal_count = total_count - overlimit_count
    
    total_position = 0
    if total_column and total_column in df.columns:
        total_position = df[total_column].sum()
    elif position_column in df.columns:
        total_position = df[position_column].sum()
    
    # 计算超限率
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
    """
    渲染单一信用限额页面
    
    Args:
        filters: 筛选条件字典
        data_loader: 数据加载器实例
    """
    # 页面标题
    st.markdown("""
    <div style="margin-bottom: 24px;">
        <h1 style="font-size: 1.75rem; font-weight: 700; color: #0f172a; margin: 0;">
            📋 单一信用限额
        </h1>
        <p style="font-size: 0.875rem; color: #64748b; margin: 8px 0 0 0;">
            单一债券、主体、实控人及担保人的规模限额监控
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    # 加载数据
    with st.spinner("加载数据中..."):
        df_1_1 = data_loader.load_stage1_credit_1_1()
        df_1_2 = data_loader.load_stage1_credit_1_2()
    
    # 创建标签页
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "债券规模",
        "债券集中度",
        "主体规模",
        "实控人规模",
        "担保人规模"
    ])
    
    # Tab1: 单一债券规模限额
    with tab1:
        # 应用筛选
        filtered_df = apply_filters(df_1_2, filters)
        
        # KPI卡片
        _render_kpi_cards(filtered_df, '单一债券是否超限', '库存数量(万)_PR', '单一债券总持仓_PR')
        
        st.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)
        
        # 选择相关列
        display_columns = [
            '日期', '内部证券账户名称', '资产代码', '资产名称', 
            '债务主体', '库存数量(万)_PR', '单一债券规模限额指标值',
            '单一债券总持仓_PR', '单一债券规模剩余额度(万)', 
            '单一债券是否超限', '是否超限'
        ]
        
        # 过滤存在的列
        display_columns = [col for col in display_columns if col in filtered_df.columns]
        display_df = filtered_df[display_columns]
        
        # 渲染表格
        render_data_table(
            display_df,
            title=None,
            highlight_column='单一债券是否超限',
            height=450,
            show_summary=True,
            enable_export=True,
            export_key="export_page1_tab1_single_bond",
            add_total_row=True,
            total_columns=['库存数量(万)_PR']
        )
    
    # Tab2: 单一债券集中度
    with tab2:
        filtered_df = apply_filters(df_1_2, filters)
        
        # KPI卡片
        _render_kpi_cards(filtered_df, '单一债券集中度是否超限', '库存数量(万)_PR')
        st.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)
        
        display_columns = [
            '日期', '内部证券账户名称', '资产代码', '资产名称',
            '债务主体', '库存数量(万)_PR', '单一债券集中度限额指标值',
            '单一债券集中度', '单一债券集中度剩余额度(万)',
            '单一债券集中度是否超限', '是否超限'
        ]
        
        display_columns = [col for col in display_columns if col in filtered_df.columns]
        display_df = filtered_df[display_columns]
        
        render_data_table(
            display_df,
            highlight_column='单一债券集中度是否超限',
            height=450,
            export_key="export_page1_tab2_concentration",
            add_total_row=True,
            total_columns=['库存数量(万)_PR']
        )
    
    # Tab3: 主体规模限额
    with tab3:
        filtered_df = apply_filters(df_1_2, filters)
        
        # KPI卡片
        _render_kpi_cards(filtered_df, '单一主体是否超限', '库存数量(万)_PR', '单一主体总持仓_PR')
        st.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)
        
        display_columns = [
            '日期', '内部证券账户名称', '资产代码', '资产名称',
            '债务主体', '库存数量(万)_PR', '单一主体规模限额指标值',
            '单一主体总持仓_PR', '单一主体规模剩余额度(万)',
            '单一主体是否超限', '是否超限'
        ]
        
        display_columns = [col for col in display_columns if col in filtered_df.columns]
        display_df = filtered_df[display_columns]
        
        render_data_table(
            display_df,
            highlight_column='单一主体是否超限',
            height=450,
            export_key="export_page1_tab3_entity",
            add_total_row=True,
            total_columns=['库存数量(万)_PR']
        )
    
    # Tab4: 实控人规模限额
    with tab4:
        filtered_df = apply_filters(df_1_2, filters)
        
        # KPI卡片
        _render_kpi_cards(filtered_df, '单一实控人是否超限', '库存数量(万)_PR', '单一实控人总持仓_PR')
        st.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)
        
        display_columns = [
            '日期', '内部证券账户名称', '资产代码', '资产名称',
            '债务主体', '实际控制人名称_修正', '库存数量(万)_PR', 
            '单一实控人规模限额指标值', '单一实控人总持仓_PR',
            '单一实控人规模剩余额度(万)', '单一实控人是否超限', '是否超限'
        ]
        
        display_columns = [col for col in display_columns if col in filtered_df.columns]
        display_df = filtered_df[display_columns]
        
        render_data_table(
            display_df,
            highlight_column='单一实控人是否超限',
            height=450,
            export_key="export_page1_tab4_controller",
            add_total_row=True,
            total_columns=['库存数量(万)_PR']
        )
    
    # Tab5: 担保人规模限额
    with tab5:
        filtered_df = apply_filters(df_1_2, filters)
        
        # KPI卡片
        _render_kpi_cards(filtered_df, '单一担保人是否超限', '库存数量(万)_PR', '单一担保人总持仓_PR')
        st.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)
        
        display_columns = [
            '日期', '内部证券账户名称', '资产代码', '资产名称',
            '债务主体', '担保人', '库存数量(万)_PR',
            '单一担保公司规模限额', '单一担保人总持仓_PR',
            '单一担保公司规模剩余额度(万)', '单一担保人是否超限', '是否超限'
        ]
        
        display_columns = [col for col in display_columns if col in filtered_df.columns]
        display_df = filtered_df[display_columns]
        
        render_data_table(
            display_df,
            highlight_column='单一担保人是否超限',
            height=450,
            export_key="export_page1_tab5_guarantor",
            add_total_row=True,
            total_columns=['库存数量(万)_PR']
        )
