"""
页面3：分类信用限额 - 现代金融看板风格（标签页模式）
"""
import pandas as pd
import streamlit as st
from src.visualization.components.tables import render_data_table
from src.visualization.components.controls import (
    inject_compact_controls_css,
    render_kpi_cards,
    apply_dimension_filter,
)
from src.visualization.display_builders import build_page3_category_credit_views

_PAGE3_SHARED_KEY = "page3_current_dimension_overlimit_shared"


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
    views = build_page3_category_credit_views(data_loader, filters)
    tables = views.get("tables", {})
    unresolved_groups = views.get("meta", {}).get("unresolved_groups", {})

    # 创建标签页（4个维度）
    tab1, tab2, tab3, tab4 = st.tabs([
        "高风险行业",
        "高风险省份",
        "地域集中度",
        "城投集中度"
    ])

    # ==================== Tab1: 高风险行业 ====================
    with tab1:
        dimension_df = tables.get("tab1_industry", pd.DataFrame())
        if '高风险行业是否超限' in dimension_df.columns:
            unresolved = int(unresolved_groups.get("tab1_industry", 0))
            if unresolved:
                st.warning(f"有 {unresolved} 组记录因关键字段不一致，已保留原明细未合并。")

            dimension_df = apply_dimension_filter(
                dimension_df, "高风险行业是否超限",
                "page3_tab1_current_dimension_overlimit",
                _PAGE3_SHARED_KEY,
            )

            render_kpi_cards(dimension_df, '高风险行业是否超限', position_column="PR后规模(万)")
            st.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)

            display_columns = [
                '日期', '代码', '资产名称', '内部证券账户名称',
                '债务主体', 'wind行业', 'PR后规模(万)',
                '集中度限额', '集中度', '维度总持仓(万)', '剩余额度(万)',
                '高风险行业是否超限', '是否超限'
            ]

            display_columns = [col for col in display_columns if col in dimension_df.columns]
            display_df = dimension_df[display_columns].copy()

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
        dimension_df = tables.get("tab2_province", pd.DataFrame())
        if '高风险省份是否超限' in dimension_df.columns:
            unresolved = int(unresolved_groups.get("tab2_province", 0))
            if unresolved:
                st.warning(f"有 {unresolved} 组记录因关键字段不一致，已保留原明细未合并。")

            dimension_df = apply_dimension_filter(
                dimension_df, "高风险省份是否超限",
                "page3_tab2_current_dimension_overlimit",
                _PAGE3_SHARED_KEY,
            )

            render_kpi_cards(dimension_df, '高风险省份是否超限', position_column="PR后规模(万)")
            st.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)

            display_columns = [
                '日期', '代码', '资产名称', '内部证券账户名称',
                '债务主体', '省份', 'PR后规模(万)',
                '集中度限额', '集中度', '维度总持仓(万)', '剩余额度(万)',
                '高风险省份是否超限', '是否超限'
            ]

            display_columns = [col for col in display_columns if col in dimension_df.columns]
            display_df = dimension_df[display_columns].copy()

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
        dimension_df = tables.get("tab3_regional", pd.DataFrame())
        if '地域集中度是否超限' in dimension_df.columns:
            unresolved = int(unresolved_groups.get("tab3_regional", 0))
            if unresolved:
                st.warning(f"有 {unresolved} 组记录因关键字段不一致，已保留原明细未合并。")

            dimension_df = apply_dimension_filter(
                dimension_df, "地域集中度是否超限",
                "page3_tab3_current_dimension_overlimit",
                _PAGE3_SHARED_KEY,
            )

            render_kpi_cards(dimension_df, '地域集中度是否超限', position_column="PR后规模(万)")
            st.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)

            display_columns = [
                '日期', '代码', '资产名称', '内部证券账户名称',
                '债务主体', '省份', 'PR后规模(万)',
                '集中度限额', '集中度', '维度总持仓(万)', '剩余额度(万)',
                '地域集中度是否超限', '是否超限'
            ]

            display_columns = [col for col in display_columns if col in dimension_df.columns]
            display_df = dimension_df[display_columns].copy()

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
        dimension_df = tables.get("tab4_citybond", pd.DataFrame())
        if '城投集中度是否超限' in dimension_df.columns:
            unresolved = int(unresolved_groups.get("tab4_citybond", 0))
            if unresolved:
                st.warning(f"有 {unresolved} 组记录因关键字段不一致，已保留原明细未合并。")

            dimension_df = apply_dimension_filter(
                dimension_df, "城投集中度是否超限",
                "page3_tab4_current_dimension_overlimit",
                _PAGE3_SHARED_KEY,
            )

            render_kpi_cards(dimension_df, '城投集中度是否超限', position_column="PR后规模(万)")
            st.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)

            display_columns = [
                '日期', '代码', '资产名称', '内部证券账户名称',
                '债务主体', '省份', 'PR后规模(万)',
                '集中度限额', '集中度', '维度总持仓(万)', '剩余额度(万)',
                '城投集中度是否超限', '是否超限'
            ]

            display_columns = [col for col in display_columns if col in dimension_df.columns]
            display_df = dimension_df[display_columns].copy()

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
