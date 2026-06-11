"""
页面2：特定信用限额 - 现代金融看板风格
"""
import pandas as pd
import streamlit as st
from src.visualization.components.tables import render_data_table
from src.visualization.components.controls import (
    inject_compact_controls_css,
    render_kpi_cards,
    apply_dimension_filter,
)
from src.visualization.display_builders import build_page2_specific_credit_views

_PAGE2_SHARED_KEY = "page2_current_dimension_overlimit_shared"


def render(filters: dict, data_loader):
    """渲染特定信用限额页面"""
    # 页面标题
    st.markdown("""
    <div style="margin-bottom: 24px;">
        <h1 style="font-size: 1.75rem; font-weight: 700; color: #0f172a; margin: 0;">
            📌 特定信用限额
        </h1>
        <p style="font-size: 0.875rem; color: #64748b; margin: 8px 0 0 0;">
            特定主体及特定实控人的规模限额监控
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    inject_compact_controls_css("_page2_compact_controls_css_injected")
    views = build_page2_specific_credit_views(data_loader, filters)
    tables = views.get("tables", {})
    unresolved_groups = int(views.get("meta", {}).get("unresolved_groups", 0))

    # 创建标签页
    tab1, tab2 = st.tabs([
        "特定主体限额",
        "特定实控人限额"
    ])

    with tab1:
        if unresolved_groups:
            st.warning(f"有 {unresolved_groups} 组记录因关键字段不一致，已保留原明细未合并。")

        table = tables.get("tab1_specific_entity", pd.DataFrame())
        filtered_df = apply_dimension_filter(
            table, "特定主体限额是否超限",
            "page2_tab1_current_dimension_overlimit",
            _PAGE2_SHARED_KEY,
        )

        render_kpi_cards(filtered_df, "特定主体限额是否超限", position_column="PR后规模(万)")
        st.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)

        display_columns = [
            '日期', '代码', '资产名称', '内部证券账户名称',
            '债务主体', 'PR后规模(万)', '特定主体限额名称',
            '特定主体限额指标值', '特定主体总持仓',
            '特定主体限额剩余额度', '特定主体限额是否超限', '是否超限'
        ]

        display_columns = [col for col in display_columns if col in filtered_df.columns]
        display_df = filtered_df[display_columns].copy()

        render_data_table(
            display_df,
            highlight_column='特定主体限额是否超限',
            height=500,
            export_key="export_page2_tab1_specific_entity",
            add_total_row=True,
            total_columns=['PR后规模(万)']
        )

    with tab2:
        if unresolved_groups:
            st.warning(f"有 {unresolved_groups} 组记录因关键字段不一致，已保留原明细未合并。")

        table = tables.get("tab2_specific_controller", pd.DataFrame())
        filtered_df = apply_dimension_filter(
            table, "特定实控人限额是否超限",
            "page2_tab2_current_dimension_overlimit",
            _PAGE2_SHARED_KEY,
        )

        render_kpi_cards(filtered_df, "特定实控人限额是否超限", position_column="PR后规模(万)")
        st.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)

        display_columns = [
            '日期', '代码', '资产名称', '内部证券账户名称',
            '债务主体', '实际控制人名称_修正', 'PR后规模(万)',
            '特定实控人限额名称', '特定实控人限额指标值',
            '特定实控人总持仓', '特定实控人限额剩余额度',
            '特定实控人限额是否超限', '是否超限'
        ]

        display_columns = [col for col in display_columns if col in filtered_df.columns]
        display_df = filtered_df[display_columns].copy()

        render_data_table(
            display_df,
            highlight_column='特定实控人限额是否超限',
            height=500,
            export_key="export_page2_tab2_specific_controller",
            add_total_row=True,
            total_columns=['PR后规模(万)']
        )
