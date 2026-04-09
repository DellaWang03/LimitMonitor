"""
共享 UI 控件 - 供多个页面复用

提供三类公共组件：
- inject_compact_controls_css: segmented control 紧凑样式注入
- render_kpi_cards: 4 张标准 KPI 卡片（总监控对象数 / 超限对象 / 正常对象 / 总持仓）
- apply_dimension_filter: 渲染「本维度超限」筛选控件并返回过滤后的 DataFrame
"""
import pandas as pd
import streamlit as st


def inject_compact_controls_css(css_injected_key: str) -> None:
    """
    注入 segmented control 紧凑样式。
    每个页面使用独立的 session_state 键，确保每次进入页面时仅注入一次。
    """
    if st.session_state.get(css_injected_key):
        return
    st.session_state[css_injected_key] = True
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
        unsafe_allow_html=True,
    )


def render_kpi_cards(
    df: pd.DataFrame,
    highlight_column: str,
    position_column: str = "库存数量(万)_PR",
) -> None:
    """
    渲染 4 张标准 KPI 卡片：总监控对象数 / 超限对象 / 正常对象 / 总持仓。

    样式与 page1/page3 完全一致：
    - 超限对象卡片：超限数为 0 时显示绿色+「无超限」，否则红色+超限率
    - 总持仓使用明细级别持仓列（position_column），避免重复计算
    """
    total_count = len(df)
    overlimit_count = 0
    normal_count = total_count

    if highlight_column in df.columns:
        overlimit_count = len(df[df[highlight_column] == "是"])
        normal_count = total_count - overlimit_count

    total_position = 0
    if position_column in df.columns:
        total_position = df[position_column].sum()

    overlimit_rate = (overlimit_count / total_count * 100) if total_count > 0 else 0

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.markdown(
            f"""
        <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px;">
            <p style="font-size: 0.7rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; margin: 0 0 8px 0;">总监控对象数</p>
            <p style="font-size: 1.75rem; font-weight: 700; color: #1e293b; margin: 0;">{total_count:,}</p>
            <p style="font-size: 0.75rem; color: #94a3b8; margin: 4px 0 0 0;">个</p>
        </div>
        """,
            unsafe_allow_html=True,
        )

    with col2:
        status_color = "#22c55e" if overlimit_count == 0 else "#ef4444"
        status_bg = "#f0fdf4" if overlimit_count == 0 else "#fef2f2"
        status_border = "#bbf7d0" if overlimit_count == 0 else "#fecaca"
        st.markdown(
            f"""
        <div style="background: {status_bg}; border: 1px solid {status_border}; border-radius: 12px; padding: 20px;">
            <p style="font-size: 0.7rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; margin: 0 0 8px 0;">超限对象</p>
            <p style="font-size: 1.75rem; font-weight: 700; color: {status_color}; margin: 0;">{overlimit_count}</p>
            <p style="font-size: 0.75rem; color: {status_color}; margin: 4px 0 0 0;">{'无超限' if overlimit_count == 0 else f'超限率 {overlimit_rate:.1f}%'}</p>
        </div>
        """,
            unsafe_allow_html=True,
        )

    with col3:
        st.markdown(
            f"""
        <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px;">
            <p style="font-size: 0.7rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; margin: 0 0 8px 0;">正常对象</p>
            <p style="font-size: 1.75rem; font-weight: 700; color: #22c55e; margin: 0;">{normal_count:,}</p>
            <p style="font-size: 0.75rem; color: #94a3b8; margin: 4px 0 0 0;">个</p>
        </div>
        """,
            unsafe_allow_html=True,
        )

    with col4:
        st.markdown(
            f"""
        <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px;">
            <p style="font-size: 0.7rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; margin: 0 0 8px 0;">总持仓</p>
            <p style="font-size: 1.75rem; font-weight: 700; color: #1e293b; margin: 0;">{total_position / 10000:,.1f}</p>
            <p style="font-size: 0.75rem; color: #94a3b8; margin: 4px 0 0 0;">亿元</p>
        </div>
        """,
            unsafe_allow_html=True,
        )


def _render_shared_dimension_control(filter_key: str, shared_key: str) -> str:
    """
    渲染「本维度超限」Segmented Control，并同步多 Tab 间的选中状态。

    原理：
    - 每个 Tab 使用独立 filter_key（避免 DuplicateWidgetID）
    - shared_key 存放最新选中值，version_key 跟踪变更版本号
    - 当本 Tab 的版本号落后于 shared_version 时，先将控件同步到共享值
    - 当用户改变控件值后，更新共享值并触发全量重跑，使其他 Tab 立即同步
    """
    version_key = f"{shared_key}_version"
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
            unsafe_allow_html=True,
        )

    with control_col:
        selected_value = st.segmented_control(
            label="本维度超限筛选",
            options=options,
            key=filter_key,
            label_visibility="collapsed",
        )

    st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
    current = selected_value or "全部"

    # 检测值变化并触发全量重跑，使所有 Tab 同步
    # st.rerun(scope="app") 在 tab/fragment 主体内合法，不在 on_change 回调内调用
    if st.session_state.get(shared_key) != current:
        st.session_state[shared_key] = current
        st.session_state[version_key] = st.session_state.get(version_key, 0) + 1
        if hasattr(st, "fragment"):
            st.rerun(scope="app")

    return current


def apply_dimension_filter(
    df: pd.DataFrame,
    dimension_column: str,
    filter_key: str,
    shared_key: str,
) -> pd.DataFrame:
    """
    渲染「本维度超限」筛选控件，并返回筛选后的 DataFrame。

    若 dimension_column 不在 df 中，直接返回原始 df（控件不渲染）。
    """
    if dimension_column not in df.columns:
        return df

    selected_value = _render_shared_dimension_control(filter_key, shared_key)

    if not selected_value or selected_value == "全部":
        return df

    return df[df[dimension_column] == selected_value]
