"""
页面4：专业担保明细 - 现代金融看板风格
"""
import streamlit as st
from src.visualization.components.tables import render_data_table


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
        df = data_loader.load_stage1_guarantee()
    
    # KPI卡片区域
    total_companies = len(df)
    total_position = df['单一担保人总持仓_PR'].sum() if '单一担保人总持仓_PR' in df.columns else 0
    total_limit = df['单一担保公司规模限额'].sum() if '单一担保公司规模限额' in df.columns else 0
    usage_rate = (total_position / total_limit * 100) if total_limit > 0 else 0
    
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
        usage_color = "#22c55e" if usage_rate < 80 else ("#eab308" if usage_rate < 100 else "#ef4444")
        st.markdown(f"""
        <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px;">
            <p style="font-size: 0.7rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; margin: 0 0 8px 0;">使用率</p>
            <p style="font-size: 1.75rem; font-weight: 700; color: {usage_color}; margin: 0;">{usage_rate:.1f}%</p>
            <p style="font-size: 0.75rem; color: #94a3b8; margin: 4px 0 0 0;">{'正常' if usage_rate < 80 else ('警戒' if usage_rate < 100 else '超限')}</p>
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
        '日期', '授信担保公司名称', '单一担保公司规模限额',
        '单一担保人总持仓_PR', '单一担保公司规模剩余额度(万)'
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
        height=500,
        show_summary=True,
        enable_export=True,
        export_key="export_page4_guarantee"
    )
