"""
页面3：分类信用限额 - 现代金融看板风格（标签页模式）
"""
import streamlit as st
import pandas as pd
from src.visualization.components.filters import apply_filters
from src.visualization.components.tables import render_data_table, aggregate_by_asset_and_account
from src.visualization.components.controls import (
    inject_compact_controls_css,
    render_kpi_cards,
    apply_dimension_filter,
)

_PAGE3_SHARED_KEY = "page3_current_dimension_overlimit_shared"


_aggregate_by_asset_and_account = aggregate_by_asset_and_account


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
    
    inject_compact_controls_css("_page3_compact_controls_css_injected")

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
            filtered_df = apply_filters(df, filters)
            dimension_df = filtered_df[filtered_df['高风险行业是否超限'].notna()].copy()
            dimension_df, unresolved_groups = _aggregate_by_asset_and_account(dimension_df)

            if unresolved_groups:
                st.warning(f"有 {unresolved_groups} 组记录因关键字段不一致，已保留原明细未合并。")

            dimension_df = apply_dimension_filter(
                dimension_df, "高风险行业是否超限",
                "page3_tab1_current_dimension_overlimit",
                _PAGE3_SHARED_KEY,
            )

            render_kpi_cards(dimension_df, '高风险行业是否超限')
            st.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)

            display_columns = [
                '日期', '代码', '资产名称', '内部证券账户名称',
                '债务主体', 'wind行业', '库存数量(万)_PR',
                '高风险行业是否超限', '是否超限'
            ]

            display_columns = [col for col in display_columns if col in dimension_df.columns]
            display_df = dimension_df[display_columns].rename(columns={
                '库存数量(万)_PR': 'PR后规模(万)'
            })

            render_data_table(
                display_df,
                highlight_column='高风险行业是否超限',
                height=450,
                export_key="export_page3_tab1_industry",
                add_total_row=True,
                total_columns=['PR后规模(万)']
            )
        else:
            st.info("该维度数据不可用")

    # ==================== Tab2: 高风险省份 ====================
    with tab2:
        if '高风险省份是否超限' in df.columns:
            filtered_df = apply_filters(df, filters)
            dimension_df = filtered_df[filtered_df['高风险省份是否超限'].notna()].copy()
            dimension_df, unresolved_groups = _aggregate_by_asset_and_account(dimension_df)

            if unresolved_groups:
                st.warning(f"有 {unresolved_groups} 组记录因关键字段不一致，已保留原明细未合并。")

            dimension_df = apply_dimension_filter(
                dimension_df, "高风险省份是否超限",
                "page3_tab2_current_dimension_overlimit",
                _PAGE3_SHARED_KEY,
            )

            render_kpi_cards(dimension_df, '高风险省份是否超限')
            st.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)

            display_columns = [
                '日期', '代码', '资产名称', '内部证券账户名称',
                '债务主体', '省份', '库存数量(万)_PR',
                '高风险省份是否超限', '是否超限'
            ]

            display_columns = [col for col in display_columns if col in dimension_df.columns]
            display_df = dimension_df[display_columns].rename(columns={
                '库存数量(万)_PR': 'PR后规模(万)'
            })

            render_data_table(
                display_df,
                highlight_column='高风险省份是否超限',
                height=450,
                export_key="export_page3_tab2_province",
                add_total_row=True,
                total_columns=['PR后规模(万)']
            )
        else:
            st.info("该维度数据不可用")

    # ==================== Tab3: 地域集中度 ====================
    with tab3:
        if '地域集中度是否超限' in df.columns:
            filtered_df = apply_filters(df, filters)
            dimension_df = filtered_df[filtered_df['地域集中度是否超限'].notna()].copy()
            dimension_df, unresolved_groups = _aggregate_by_asset_and_account(dimension_df)

            if unresolved_groups:
                st.warning(f"有 {unresolved_groups} 组记录因关键字段不一致，已保留原明细未合并。")

            dimension_df = apply_dimension_filter(
                dimension_df, "地域集中度是否超限",
                "page3_tab3_current_dimension_overlimit",
                _PAGE3_SHARED_KEY,
            )

            render_kpi_cards(dimension_df, '地域集中度是否超限')
            st.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)

            display_columns = [
                '日期', '代码', '资产名称', '内部证券账户名称',
                '债务主体', '省份', '库存数量(万)_PR',
                '地域集中度是否超限', '是否超限'
            ]

            display_columns = [col for col in display_columns if col in dimension_df.columns]
            display_df = dimension_df[display_columns].rename(columns={
                '库存数量(万)_PR': 'PR后规模(万)'
            })

            render_data_table(
                display_df,
                highlight_column='地域集中度是否超限',
                height=450,
                export_key="export_page3_tab3_regional",
                add_total_row=True,
                total_columns=['PR后规模(万)']
            )
        else:
            st.info("该维度数据不可用")

    # ==================== Tab4: 城投集中度 ====================
    with tab4:
        if '城投集中度是否超限' in df.columns:
            filtered_df = apply_filters(df, filters)
            dimension_df = filtered_df[filtered_df['城投集中度是否超限'].notna()].copy()
            dimension_df, unresolved_groups = _aggregate_by_asset_and_account(dimension_df)

            if unresolved_groups:
                st.warning(f"有 {unresolved_groups} 组记录因关键字段不一致，已保留原明细未合并。")

            dimension_df = apply_dimension_filter(
                dimension_df, "城投集中度是否超限",
                "page3_tab4_current_dimension_overlimit",
                _PAGE3_SHARED_KEY,
            )

            render_kpi_cards(dimension_df, '城投集中度是否超限')
            st.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)

            display_columns = [
                '日期', '代码', '资产名称', '内部证券账户名称',
                '债务主体', '省份', '库存数量(万)_PR',
                '城投集中度是否超限', '是否超限'
            ]

            display_columns = [col for col in display_columns if col in dimension_df.columns]
            display_df = dimension_df[display_columns].rename(columns={
                '库存数量(万)_PR': 'PR后规模(万)'
            })

            render_data_table(
                display_df,
                highlight_column='城投集中度是否超限',
                height=450,
                export_key="export_page3_tab4_citybond",
                add_total_row=True,
                total_columns=['PR后规模(万)']
            )
        else:
            st.info("该维度数据不可用")
