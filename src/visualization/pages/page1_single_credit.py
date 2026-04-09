"""
页面1：单一信用限额 - 现代金融看板风格
"""
import streamlit as st
import pandas as pd
from src.visualization.components.filters import apply_filters
from src.visualization.components.tables import render_data_table

if hasattr(st, "fragment"):
    _fragment = st.fragment
else:
    def _fragment(func):
        return func


def _inject_compact_controls_css():
    if st.session_state.get("_page1_compact_controls_css_injected"):
        return
    st.session_state["_page1_compact_controls_css_injected"] = True

    st.markdown(
        """
        <style>
          /* Reduce vertical whitespace around segmented controls */
          div[data-testid="stSegmentedControl"] {
            margin-top: -6px;
            margin-bottom: 6px;
          }
          /* Slightly reduce padding so the control feels less bulky */
          div[data-testid="stSegmentedControl"] > div {
            padding-top: 0.1rem;
            padding-bottom: 0.1rem;
          }
        </style>
        """,
        unsafe_allow_html=True
    )


def _render_kpi_cards(df, highlight_column, position_column='库存数量(万)_PR'):
    """
    渲染现代KPI卡片
    
    注意：总持仓统一使用明细级别的持仓列（库存数量(万)_PR），
    不使用已汇总的XX总持仓_PR列，避免重复计算
    """
    total_count = len(df)
    overlimit_count = 0
    normal_count = total_count
    
    if highlight_column in df.columns:
        overlimit_count = len(df[df[highlight_column] == '是'])
        normal_count = total_count - overlimit_count
    
    # 总持仓：统一使用明细级别的持仓列
    total_position = 0
    if position_column in df.columns:
        total_position = df[position_column].sum()
    
    # 计算超限率
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
        status_color = "#22c55e" if overlimit_count == 0 else "#ef4444"
        status_bg = "#f0fdf4" if overlimit_count == 0 else "#fef2f2"
        st.markdown(f"""
        <div style="background: {status_bg}; border: 1px solid {'#bbf7d0' if overlimit_count == 0 else '#fecaca'}; border-radius: 12px; padding: 20px;">
            <p style="font-size: 0.7rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; margin: 0 0 8px 0;">超限对象</p>
            <p style="font-size: 1.75rem; font-weight: 700; color: {status_color}; margin: 0;">{overlimit_count}</p>
            <p style="font-size: 0.75rem; color: {status_color}; margin: 4px 0 0 0;">{'无超限' if overlimit_count == 0 else f'超限率 {overlimit_rate:.1f}%'}</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown(f"""
        <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px;">
            <p style="font-size: 0.7rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; margin: 0 0 8px 0;">正常对象</p>
            <p style="font-size: 1.75rem; font-weight: 700; color: #22c55e; margin: 0;">{normal_count:,}</p>
            <p style="font-size: 0.75rem; color: #94a3b8; margin: 4px 0 0 0;">个</p>
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


def _render_shared_current_dimension_control(filter_key: str) -> str:
    shared_key = "page1_current_dimension_overlimit_shared"
    version_key = "page1_current_dimension_overlimit_shared_version"
    tab_version_key = f"{filter_key}__shared_version"
    options = ["全部", "是", "否"]
    shared_value = st.session_state.get(shared_key, "全部")
    shared_version = st.session_state.get(version_key, 0)

    if filter_key not in st.session_state:
        st.session_state[filter_key] = shared_value
        st.session_state[tab_version_key] = shared_version
    elif st.session_state.get(tab_version_key) != shared_version:
        st.session_state[filter_key] = shared_value
        st.session_state[tab_version_key] = shared_version

    label_col, control_col, _ = st.columns([1.4, 2.2, 4.4])
    with label_col:
        st.markdown(
            """
            <div style="
                padding-top: 8px;
                font-size: 0.84rem;
                font-weight: 600;
                color: #64748b;
                letter-spacing: 0.02em;
                white-space: nowrap;
            ">本维度超限</div>
            """,
            unsafe_allow_html=True
        )

    with control_col:
        selected_value = st.segmented_control(
            label="本维度超限筛选",
            options=options,
            key=filter_key,
            label_visibility="collapsed"
        )

    st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
    current = selected_value or "全部"

    # 在 fragment 主体内（非回调中）检测值变化并触发全量重跑，使所有 Tab 同步
    # st.rerun(scope="app") 在 fragment 主体内合法；在 on_change 回调内会被 Streamlit 忽略
    if st.session_state.get(shared_key) != current:
        st.session_state[shared_key] = current
        st.session_state[version_key] = st.session_state.get(version_key, 0) + 1
        if hasattr(st, "fragment"):
            st.rerun(scope="app")

    return current


def _apply_current_dimension_filter(df, dimension_column: str, filter_key: str):
    """
    渲染当前标签页的单维度超限筛选，并返回筛选后的数据
    """
    if dimension_column not in df.columns:
        return df

    selected_value = _render_shared_current_dimension_control(filter_key)

    if not selected_value or selected_value == "全部":
        return df

    return df[df[dimension_column] == selected_value]

def _apply_six_dimension_display(df: pd.DataFrame) -> pd.DataFrame:
    """单一信用限额页统一展示六维综合超限结果。"""
    if '六维综合是否超限' not in df.columns:
        raise KeyError("缺少字段：六维综合是否超限")
    result = df.copy()
    result['是否超限'] = result['六维综合是否超限']
    return result


def _aggregate_by_asset_and_account(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """
    按 日期+资产代码+内部证券账户名称 聚合。

    规则：
    - 仅对「库存数量(万)_PR」求和
    - 其余字段在组内一致时取首条
    - 若组内关键字段不一致，则该组保留原明细，不做合并
    """
    group_keys = ['日期', '资产代码', '内部证券账户名称']
    sum_columns = {'库存数量(万)_PR'}
    ignored_columns = {'合并辅助列'}

    if df.empty or any(col not in df.columns for col in group_keys):
        return df, 0

    working_df = df.copy()
    duplicate_mask = working_df.duplicated(group_keys, keep=False)
    duplicate_df = working_df[duplicate_mask]
    non_duplicate_df = working_df[~duplicate_mask]

    if duplicate_df.empty:
        return working_df, 0

    aggregated_rows = []
    unresolved_groups = []

    for _, group in duplicate_df.groupby(group_keys, sort=False, dropna=False):
        varying_columns = []
        for column in group.columns:
            if column in group_keys or column in sum_columns or column in ignored_columns:
                continue
            if group[column].nunique(dropna=False) > 1:
                varying_columns.append(column)

        if varying_columns:
            unresolved_groups.append(group)
            continue

        row = group.iloc[0].copy()
        if '库存数量(万)_PR' in group.columns:
            row['库存数量(万)_PR'] = group['库存数量(万)_PR'].sum()
        aggregated_rows.append(row)

    parts = [non_duplicate_df]
    if aggregated_rows:
        parts.append(pd.DataFrame(aggregated_rows))
    if unresolved_groups:
        parts.append(pd.concat(unresolved_groups, ignore_index=True))

    result_df = pd.concat(parts, ignore_index=True)
    return result_df, len(unresolved_groups)


@_fragment
def _render_tab1_single_bond_fragment(base_df: pd.DataFrame, unresolved_groups: int):
    filtered_df = _apply_current_dimension_filter(
        base_df,
        '单一债券是否超限',
        'page1_tab1_current_dimension_overlimit'
    )

    if unresolved_groups:
        st.warning(f"有 {unresolved_groups} 组记录因关键字段不一致，已保留原明细未合并。")
    
    _render_kpi_cards(filtered_df, '单一债券是否超限', '库存数量(万)_PR')
    
    st.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)
    
    display_columns = [
        '日期', '代码', '资产名称', '内部证券账户名称',
        '债务主体', '库存数量(万)_PR', '单一债券规模限额适用类别',
        '单一债券规模限额指标值',
        '单一债券总持仓_PR', '单一债券规模剩余额度(万)',
        '单一债券是否超限', '是否超限'
    ]
    
    display_columns = [col for col in display_columns if col in filtered_df.columns]
    display_df = filtered_df[display_columns]
    
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


@_fragment
def _render_dimension_fragment(
    base_df: pd.DataFrame,
    unresolved_groups: int,
    dimension_column: str,
    filter_key: str,
    display_columns: list[str],
    export_key: str,
):
    filtered_df = _apply_current_dimension_filter(base_df, dimension_column, filter_key)

    if unresolved_groups:
        st.warning(f"有 {unresolved_groups} 组记录因关键字段不一致，已保留原明细未合并。")

    _render_kpi_cards(filtered_df, dimension_column, '库存数量(万)_PR')
    st.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)

    visible_columns = [col for col in display_columns if col in filtered_df.columns]
    display_df = filtered_df[visible_columns]

    render_data_table(
        display_df,
        highlight_column=dimension_column,
        height=450,
        export_key=export_key,
        add_total_row=True,
        total_columns=['库存数量(万)_PR']
    )


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

    _inject_compact_controls_css()
    
    # 加载数据
    df_1_1 = data_loader.load_stage1_credit_1_1()
    df_1_2 = data_loader.load_stage1_credit_1_2()
    required_frames = {
        "限额明细_债券持仓明细表_信用债1_2": df_1_2,
    }
    missing_frames = [
        name for name, df in required_frames.items()
        if '六维综合是否超限' not in df.columns
    ]
    if missing_frames:
        missing_text = "、".join(missing_frames)
        st.error(
            f"单一信用限额页缺少六维综合字段：{missing_text}。请先重新生成 Stage1 数据后再查看。"
        )
        return
    
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "债券规模",
        "债券集中度",
        "主体规模",
        "实控人规模",
        "担保人规模",
    ])

    # Tab1: 单一债券规模限额
    with tab1:
        # 应用筛选
        filtered_df = apply_filters(df_1_2, filters)
        filtered_df, unresolved_groups = _aggregate_by_asset_and_account(filtered_df)
        filtered_df = _apply_six_dimension_display(filtered_df)
        _render_tab1_single_bond_fragment(filtered_df, unresolved_groups)
    
    # Tab2: 单一债券集中度（分账户）
    with tab2:
        filtered_df = apply_filters(df_1_2, filters)
        filtered_df, unresolved_groups = _aggregate_by_asset_and_account(filtered_df)
        filtered_df = _apply_six_dimension_display(filtered_df)
        display_columns = [
            '日期', '代码', '资产名称', '内部证券账户名称',
            '债务主体', '库存数量(万)_PR', '单一债券集中度限额适用类别',
            '单一债券集中度限额指标值',
            '单一债券集中度', '单一债券集中度剩余额度(万)',
            '单一债券集中度是否超限', '是否超限'
        ]
        _render_dimension_fragment(
            filtered_df,
            unresolved_groups,
            '单一债券集中度是否超限',
            'page1_tab2_current_dimension_overlimit',
            display_columns,
            "export_page1_tab2_concentration",
        )
    
    # Tab3: 主体规模限额
    with tab3:
        filtered_df = apply_filters(df_1_2, filters)
        filtered_df, unresolved_groups = _aggregate_by_asset_and_account(filtered_df)
        filtered_df = _apply_six_dimension_display(filtered_df)
        display_columns = [
            '日期', '代码', '资产名称', '内部证券账户名称',
            '债务主体', '库存数量(万)_PR', '单一主体限额适用类别',
            '单一主体规模限额指标值',
            '单一主体总持仓_PR', '单一主体规模剩余额度(万)',
            '单一主体是否超限', '是否超限'
        ]
        _render_dimension_fragment(
            filtered_df,
            unresolved_groups,
            '单一主体是否超限',
            'page1_tab3_current_dimension_overlimit',
            display_columns,
            "export_page1_tab3_entity",
        )
    
    # Tab4: 实控人规模限额
    with tab4:
        filtered_df = apply_filters(df_1_2, filters)
        filtered_df, unresolved_groups = _aggregate_by_asset_and_account(filtered_df)
        filtered_df = _apply_six_dimension_display(filtered_df)
        display_columns = [
            '日期', '代码', '资产名称', '内部证券账户名称',
            '债务主体', '实际控制人名称_修正', '库存数量(万)_PR',
            '单一实控人限额适用类别',
            '单一实控人规模限额指标值', '单一实控人总持仓_PR',
            '单一实控人规模剩余额度(万)', '单一实控人是否超限', '是否超限'
        ]
        _render_dimension_fragment(
            filtered_df,
            unresolved_groups,
            '单一实控人是否超限',
            'page1_tab4_current_dimension_overlimit',
            display_columns,
            "export_page1_tab4_controller",
        )
    
    # Tab5: 担保人规模限额
    with tab5:
        filtered_df = apply_filters(df_1_2, filters)
        filtered_df, unresolved_groups = _aggregate_by_asset_and_account(filtered_df)
        filtered_df = _apply_six_dimension_display(filtered_df)
        display_columns = [
            '日期', '代码', '资产名称', '内部证券账户名称',
            '债务主体', '担保人', '库存数量(万)_PR',
            '单一担保公司规模限额', '单一担保人总持仓_PR',
            '单一担保公司规模剩余额度(万)', '单一担保人是否超限', '是否超限'
        ]
        _render_dimension_fragment(
            filtered_df,
            unresolved_groups,
            '单一担保人是否超限',
            'page1_tab5_current_dimension_overlimit',
            display_columns,
            "export_page1_tab5_guarantor",
        )
