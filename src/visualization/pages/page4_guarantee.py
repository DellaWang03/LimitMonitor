"""
页面4：专业担保明细 - 现代金融看板风格
"""
import pandas as pd
import streamlit as st
from src.visualization.components.tables import render_data_table
from src.visualization.display_builders import build_page4_guarantee_views


def render(filters: dict, data_loader):
    """渲染专业担保明细页面"""
    # 页面标题
    st.markdown("""
    <div style="margin-bottom: 24px;">
        <h1 style="font-size: 1.75rem; font-weight: 700; color: #0f172a; margin: 0;">
            🏢 专业担保明细
        </h1>
        <p style="font-size: 0.875rem; color: #64748b; margin: 8px 0 0 0;">
            授信担保公司的规模限额与持仓监控
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    with st.spinner("加载数据中..."):
        views = build_page4_guarantee_views(data_loader)

    df = views.get("tables", {}).get("main", pd.DataFrame())
    kpi = views.get("kpis", {}).get("main", {})
    
    total_companies = int(kpi.get("total_companies", 0))
    total_position = float(kpi.get("total_position_wan", 0))
    total_limit = float(kpi.get("total_limit_wan", 0))
    usage_rate = float(kpi.get("usage_rate", 0)) * 100
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown(f"""
        <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px;">
            <p style="font-size: 0.7rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; margin: 0 0 8px 0;">担保公司</p>
            <p style="font-size: 1.75rem; font-weight: 700; color: #1e293b; margin: 0;">{total_companies}</p>
            <p style="font-size: 0.75rem; color: #94a3b8; margin: 4px 0 0 0;">家</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
        <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px;">
            <p style="font-size: 0.7rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; margin: 0 0 8px 0;">总担保持仓</p>
            <p style="font-size: 1.75rem; font-weight: 700; color: #3b82f6; margin: 0;">{total_position/10000:,.2f}</p>
            <p style="font-size: 0.75rem; color: #94a3b8; margin: 4px 0 0 0;">亿元</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown(f"""
        <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px;">
            <p style="font-size: 0.7rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; margin: 0 0 8px 0;">总限额</p>
            <p style="font-size: 1.75rem; font-weight: 700; color: #1e293b; margin: 0;">{total_limit/10000:,.2f}</p>
            <p style="font-size: 0.75rem; color: #94a3b8; margin: 4px 0 0 0;">亿元</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col4:
        thresholds = data_loader.load_alert_thresholds()
        _warn = thresholds['warning'] * 100
        _over = thresholds['overlimit'] * 100
        usage_color = "#22c55e" if usage_rate < _warn else ("#eab308" if usage_rate < _over else "#ef4444")
        st.markdown(f"""
        <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px;">
            <p style="font-size: 0.7rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; margin: 0 0 8px 0;">使用率</p>
            <p style="font-size: 1.75rem; font-weight: 700; color: {usage_color}; margin: 0;">{usage_rate:.1f}%</p>
            <p style="font-size: 0.75rem; color: #94a3b8; margin: 4px 0 0 0;">{'正常' if usage_rate < _warn else ('警戒' if usage_rate < _over else '超限')}</p>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)
    
    # 搜索框
    search_keyword = st.text_input(
        "搜索", 
        placeholder="🔍 输入担保公司名称...",
        key="guarantee_search",
        label_visibility="collapsed"
    )
    
    # 显示列
    display_columns = [
        '日期', '业务分类', '授信担保公司名称', '单一担保公司规模限额',
        '单一担保人总持仓_PR', '单一担保公司规模剩余额度(万)',
        '单一担保人是否超限'
    ]
    
    display_columns = [col for col in display_columns if col in df.columns]
    display_df = df[display_columns]
    
    # 应用搜索筛选
    if search_keyword and '授信担保公司名称' in display_df.columns:
        display_df = display_df[
            display_df['授信担保公司名称'].astype(str).str.contains(search_keyword, na=False, case=False)
        ]
    
    st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
    
    # 渲染表格
    render_data_table(
        display_df,
        highlight_column='单一担保人是否超限',
        height=500,
        show_summary=True,
        enable_export=True,
        export_key="export_page4_guarantee"
    )
