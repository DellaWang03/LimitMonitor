"""
页面2：特定信用限额 - 现代金融看板风格
"""
import streamlit as st
from src.visualization.components.filters import apply_filters
from src.visualization.components.tables import render_data_table


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
    
    with st.spinner("加载数据中..."):
        df = data_loader.load_stage1_credit_1_1()
    
    # 创建标签页
    tab1, tab2 = st.tabs([
        "特定主体限额",
        "特定实控人限额"
    ])
    
    with tab1:
        filtered_df = apply_filters(df, filters)
        
        display_columns = [
            '日期', '内部证券账户名称', '资产代码', '资产名称',
            '债务主体', '库存数量(万)_PR', '特定主体限额名称',
            '特定主体限额指标值', '特定主体总持仓', 
            '特定主体限额剩余额度', '特定主体限额是否超限', '是否超限'
        ]
        
        display_columns = [col for col in display_columns if col in filtered_df.columns]
        display_df = filtered_df[display_columns]
        
        render_data_table(
            display_df,
            highlight_column='特定主体限额是否超限',
            height=500,
            export_key="export_page2_tab1_specific_entity",
            add_total_row=True,
            total_columns=['库存数量(万)_PR']
        )
    
    with tab2:
        filtered_df = apply_filters(df, filters)
        
        display_columns = [
            '日期', '内部证券账户名称', '资产代码', '资产名称',
            '债务主体', '实际控制人名称_修正', '库存数量(万)_PR',
            '特定实控人限额名称', '特定实控人限额指标值',
            '特定实控人总持仓', '特定实控人限额剩余额度',
            '特定实控人限额是否超限', '是否超限'
        ]
        
        display_columns = [col for col in display_columns if col in filtered_df.columns]
        display_df = filtered_df[display_columns]
        
        render_data_table(
            display_df,
            highlight_column='特定实控人限额是否超限',
            height=500,
            export_key="export_page2_tab2_specific_controller",
            add_total_row=True,
            total_columns=['库存数量(万)_PR']
        )
