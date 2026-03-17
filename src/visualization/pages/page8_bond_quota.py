"""
页面8：单券可购额度查询 - 输入债券代码或名称，展示各维度剩余额度与最终可购额度
"""
import streamlit as st
import pandas as pd
from src.visualization.bond_quota_query import query_bond_remaining_quota


def render(filters: dict, data_loader):
    """渲染单券可购额度查询页面"""
    st.markdown("""
    <div style="margin-bottom: 24px;">
        <h1 style="font-size: 1.75rem; font-weight: 700; color: #0f172a; margin: 0;">
            单券可购额度查询
        </h1>
        <p style="font-size: 0.875rem; color: #64748b; margin: 8px 0 0 0;">
            输入债券代码或名称，查看各维度剩余额度与最终可购额度
        </p>
    </div>
    """, unsafe_allow_html=True)

    bond_input = st.text_input(
        "债券代码或名称",
        placeholder="输入债券代码或债券名称后点击查询",
        key="page8_bond_quota_input",
    )
    col_btn, _ = st.columns([1, 4])
    with col_btn:
        do_query = st.button("查询", type="primary", key="page8_bond_quota_btn")

    if not do_query and not bond_input:
        st.info("请输入债券代码或名称并点击「查询」。")
        return

    query_text = (bond_input or "").strip()
    if do_query and not query_text:
        st.warning("请输入债券代码或名称。")
        return

    if not do_query:
        return

    with st.spinner("查询中..."):
        target_date = getattr(data_loader, "target_date", None)
        result = query_bond_remaining_quota(data_loader, query_text, target_date=target_date)

    if result.get("error"):
        st.error(result["error"])
        return

    bond_info = result.get("bond_info", {})
    dimensions = result.get("dimensions", [])
    final_quota_wan = result.get("final_quota_wan", 0.0)

    # 债券基本信息
    st.markdown("#### 债券基本信息")
    if bond_info:
        info_cols = st.columns(min(4, len(bond_info)) or 1)
        for i, (k, v) in enumerate(bond_info.items()):
            with info_cols[i % len(info_cols)]:
                st.caption(k)
                st.write(v if pd.notna(v) else "—")
    st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)

    # 各维度剩余额度表格
    st.markdown("#### 各维度剩余额度")
    if dimensions:
        df_dim = pd.DataFrame(dimensions)
        st.dataframe(df_dim, width='stretch', height=min(400, 80 + len(dimensions) * 38))
    st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)

    # 最终可购额度卡片（与 page1 KPI 风格一致）
    st.markdown("#### 最终可购额度")
    color = "#22c55e" if final_quota_wan > 0 else "#ef4444"
    bg = "#f0fdf4" if final_quota_wan > 0 else "#fef2f2"
    border = "#bbf7d0" if final_quota_wan > 0 else "#fecaca"
    st.markdown(f"""
    <div style="background: {bg}; border: 1px solid {border}; border-radius: 12px; padding: 24px; max-width: 320px;">
        <p style="font-size: 0.7rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; margin: 0 0 8px 0;">最终可购额度</p>
        <p style="font-size: 1.75rem; font-weight: 700; color: {color}; margin: 0;">{final_quota_wan:,.2f}</p>
        <p style="font-size: 0.75rem; color: #64748b; margin: 4px 0 0 0;">万元</p>
    </div>
    """, unsafe_allow_html=True)
