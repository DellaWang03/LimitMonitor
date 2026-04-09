"""
页面9：全量债券监管集中度
"""
import streamlit as st
import pandas as pd
from src.visualization.components.tables import render_data_table


def _render_kpi_cards(df: pd.DataFrame):
    total_count = len(df)
    calculable_count = len(df[df['是否可计算'] == '是']) if '是否可计算' in df.columns else 0
    overlimit_count = len(df[df['监管集中度是否超限'] == '是']) if '监管集中度是否超限' in df.columns else 0
    total_position = df['单债总持仓_PR'].sum() if '单债总持仓_PR' in df.columns else 0
    overlimit_rate = (overlimit_count / total_count * 100) if total_count > 0 else 0

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.markdown(f"""
        <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px;">
            <p style="font-size: 0.7rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; margin: 0 0 8px 0;">总监控对象数</p>
            <p style="font-size: 1.75rem; font-weight: 700; color: #1e293b; margin: 0;">{total_count:,}</p>
            <p style="font-size: 0.75rem; color: #94a3b8; margin: 4px 0 0 0;">个</p>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown(f"""
        <div style="background: #f0fdfa; border: 1px solid #99f6e4; border-radius: 12px; padding: 20px;">
            <p style="font-size: 0.7rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; margin: 0 0 8px 0;">可计算对象</p>
            <p style="font-size: 1.75rem; font-weight: 700; color: #0f766e; margin: 0;">{calculable_count:,}</p>
            <p style="font-size: 0.75rem; color: #94a3b8; margin: 4px 0 0 0;">个</p>
        </div>
        """, unsafe_allow_html=True)

    with col3:
        overlimit_color = "#22c55e" if overlimit_count == 0 else "#ef4444"
        overlimit_bg = "#f0fdf4" if overlimit_count == 0 else "#fef2f2"
        overlimit_border = "#bbf7d0" if overlimit_count == 0 else "#fecaca"
        overlimit_sub = "无超限" if overlimit_count == 0 else f"超限率 {overlimit_rate:.1f}%"
        st.markdown(f"""
        <div style="background: {overlimit_bg}; border: 1px solid {overlimit_border}; border-radius: 12px; padding: 20px;">
            <p style="font-size: 0.7rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; margin: 0 0 8px 0;">监管超限对象</p>
            <p style="font-size: 1.75rem; font-weight: 700; color: {overlimit_color}; margin: 0;">{overlimit_count:,}</p>
            <p style="font-size: 0.75rem; color: {overlimit_color}; margin: 4px 0 0 0;">{overlimit_sub}</p>
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


def _apply_local_filters(df: pd.DataFrame) -> pd.DataFrame:
    col1, col2, col3, col4 = st.columns(4)

    bond_types = ['全部']
    if '债券分类2' in df.columns:
        bond_types += sorted(df['债券分类2'].dropna().astype(str).unique().tolist())

    with col1:
        selected_bond_type = st.selectbox(
            "债券分类",
            bond_types,
            index=0,
            key="page9_bond_type"
        )

    with col2:
        selected_calculable = st.selectbox(
            "是否可计算",
            ["全部", "是", "否"],
            index=0,
            key="page9_calculable"
        )

    with col3:
        selected_overlimit = st.selectbox(
            "监管超限",
            ["全部", "是", "否"],
            index=0,
            key="page9_overlimit"
        )

    with col4:
        search_keyword = st.text_input(
            "关键词搜索",
            placeholder="输入代码、名称或主体",
            key="page9_search"
        )

    filtered_df = df.copy()

    if selected_bond_type != '全部' and '债券分类2' in filtered_df.columns:
        filtered_df = filtered_df[filtered_df['债券分类2'] == selected_bond_type]

    if selected_calculable != '全部' and '是否可计算' in filtered_df.columns:
        filtered_df = filtered_df[filtered_df['是否可计算'] == selected_calculable]

    if selected_overlimit != '全部' and '监管集中度是否超限' in filtered_df.columns:
        filtered_df = filtered_df[filtered_df['监管集中度是否超限'] == selected_overlimit]

    if search_keyword:
        keyword = search_keyword.lower()
        mask = False
        search_columns = ['代码', 'ISIN码', '资产代码', '资产名称', '债务主体']
        for col in search_columns:
            if col in filtered_df.columns:
                mask = mask | filtered_df[col].astype(str).str.lower().str.contains(keyword, na=False)
        if not isinstance(mask, bool):
            filtered_df = filtered_df[mask]

    return filtered_df


def render(filters: dict, data_loader):
    st.markdown("""
    <div style="margin-bottom: 24px;">
        <h1 style="font-size: 1.75rem; font-weight: 700; color: #0f172a; margin: 0;">
            🌐 全量债券监管集中度
        </h1>
        <p style="font-size: 0.875rem; color: #64748b; margin: 8px 0 0 0;">
            基于全量债券口径的单债监管集中度监控，缺少归并主键或债券余额的债券将保留展示并标记不可计算
        </p>
    </div>
    """, unsafe_allow_html=True)

    df = data_loader.load_stage1_full_regulatory_concentration()
    filtered_df = _apply_local_filters(df)

    _render_kpi_cards(filtered_df)
    st.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)

    display_columns = [
        '日期', '代码', '资产名称', '债务主体', '债券分类2',
        '单债总持仓_PR', '债券余额(亿)',
        '监管集中度限额指标值', '监管集中度', '监管集中度剩余额度(万)',
        '监管集中度是否超限', '是否可计算', '内部证券账户覆盖数'
    ]
    display_columns = [col for col in display_columns if col in filtered_df.columns]
    display_df = filtered_df[display_columns]

    render_data_table(
        display_df,
        highlight_column='监管集中度是否超限',
        height=560,
        show_summary=True,
        enable_export=True,
        export_key="export_page9_full_regulatory",
        add_total_row=True,
        total_columns=['单债总持仓_PR']
    )
