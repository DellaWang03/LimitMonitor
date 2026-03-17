"""
页面5：高风险类明细 - 现代金融看板风格
"""
import streamlit as st
import plotly.express as px
from src.visualization.components.tables import render_data_table
from src.visualization.components.filters import apply_filters


def render(filters: dict, data_loader):
    """渲染高风险类明细页面"""
    # 页面标题
    st.markdown("""
    <div style="margin-bottom: 24px;">
        <h1 style="font-size: 1.75rem; font-weight: 700; color: #0f172a; margin: 0;">
            ⚠️ 高风险类明细
        </h1>
        <p style="font-size: 0.875rem; color: #64748b; margin: 8px 0 0 0;">
            高风险省份及行业的集中度监控
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    with st.spinner("加载数据中..."):
        df_industry = data_loader.load_stage2_high_risk_industry()
        df_province = data_loader.load_stage2_high_risk_province()
        df_province_detail = data_loader.load_stage2_high_risk_province_detail()
        df_detail = data_loader.load_stage2_credit_2()
    
    # 使用tabs分隔省份和行业
    tab1, tab2 = st.tabs(["🗺️ 高风险省份集中度", "🏭 高风险行业集中度"])
    
    # ==================== Tab1: 高风险省份 ====================
    with tab1:
        if len(df_province) > 0:
            row = df_province.iloc[0]
            
            # 核心KPI（3个关键指标）
            col1, col2, col3 = st.columns(3)
            
            with col1:
                concentration = row.get('高风险省份集中度', 0)
                limit = row.get('集中度限额', 0)
                st.metric(
                    "🎯 集中度",
                    f"{concentration:.2%}",
                    delta=f"限额: {limit:.2%}",
                    delta_color="normal"
                )
            
            with col2:
                total_position = row.get('高风险省份总持仓_PR', 0)
                st.metric(
                    "💰 总持仓",
                    f"{total_position:,.2f}万"
                )
            
            with col3:
                remaining = row.get('高风险省份总持仓剩余额度(万)', 0)
                is_overlimit = remaining < 0
                status = "⚠️ 超限" if is_overlimit else "✅ 正常"
                st.metric(
                    "状态",
                    status,
                    delta=f"剩余: {remaining:,.2f}万",
                    delta_color="inverse" if is_overlimit else "normal"
                )
            
            # 详细信息（可折叠）
            with st.expander("📊 查看详细指标"):
                col_a, col_b = st.columns(2)
                with col_a:
                    st.metric("省份类别", str(row.get('省份类别', 'N/A')))
                with col_b:
                    st.metric("集中度限额", f"{row.get('集中度限额', 0):.2%}")
            
            st.markdown("---")
            
            # 明细表格 + 可视化（使用专门的汇总表，包含做市业务，与Power BI一致）
            if len(df_province_detail) > 0:
                # 准备省份汇总数据
                province_summary = df_province_detail.copy()
                province_summary = province_summary.rename(columns={
                    '省份': '省份',
                    '高风险省份总持仓_PR': '持仓(万)'
                })
                
                # 从明细表获取债券数和超限数（仅用于统计，持仓以汇总表为准）
                if '省份类别' in df_detail.columns:
                    detail_stats = df_detail[df_detail['省份类别'] == '高风险省份'].groupby('省份').agg({
                        '资产代码': 'count',
                        '是否超限': lambda x: (x == '是').sum()
                    }).reset_index()
                    detail_stats.columns = ['省份', '债券数', '超限数']
                    
                    # 关联统计数据
                    province_summary = province_summary.merge(
                        detail_stats,
                        on='省份',
                        how='left'
                    )
                    province_summary['债券数'] = province_summary['债券数'].fillna(0).astype(int)
                    province_summary['超限数'] = province_summary['超限数'].fillna(0).astype(int)
                else:
                    province_summary['债券数'] = 0
                    province_summary['超限数'] = 0
                
                # 计算占比
                total = province_summary['持仓(万)'].sum()
                province_summary['占比'] = province_summary['持仓(万)'] / total * 100
                province_summary['占比'] = province_summary['占比'].map(lambda x: f"{x:.1f}%")
                
                # 添加状态
                province_summary['状态'] = province_summary['超限数'].apply(
                    lambda x: '⚠️ 超限' if x > 0 else '✅ 正常'
                )
                
                province_summary = province_summary.sort_values('持仓(万)', ascending=False)
                
                # 选择显示列
                display_cols = ['省份', '持仓(万)', '占比', '债券数', '超限数', '状态']
                province_summary = province_summary[[col for col in display_cols if col in province_summary.columns]]
                
                # 左右布局
                col_left, col_right = st.columns([1, 1])
                
                with col_left:
                    st.markdown("### 📋 省份明细")
                    st.dataframe(
                        province_summary,
                        width='stretch',
                        height=450,
                        hide_index=True
                    )
                
                with col_right:
                    st.markdown("### 📊 持仓分布")
                    # 饼图
                    fig = px.pie(
                        province_summary.head(10),
                        values='持仓(万)',
                        names='省份',
                        title='Top10省份持仓分布',
                        hole=0.4
                    )
                    fig.update_traces(textposition='inside', textinfo='percent+label')
                    st.plotly_chart(fig, width='stretch')
                
                # 可选：展开债券明细（仅供参考，注意不含做市业务数据）
                if '省份类别' in df_detail.columns:
                    with st.expander("🔍 查看债券级别明细（不含做市业务）"):
                        province_detail = df_detail[df_detail['省份类别'] == '高风险省份'].copy()
                        filtered_detail = apply_filters(province_detail, filters)
                        display_columns = [
                            '日期', '省份', '内部证券账户名称', '资产代码', '资产名称',
                            '债务主体', '库存数量(万)_PR', '是否超限'
                        ]
                        display_columns = [col for col in display_columns if col in filtered_detail.columns]
                        render_data_table(
                            filtered_detail[display_columns],
                            height=400,
                            export_key="export_page5_province_detail"
                        )
    
    # ==================== Tab2: 高风险行业 ====================
    with tab2:
        if len(df_industry) > 0:
            row = df_industry.iloc[0]
            
            # 核心KPI（3个关键指标）
            col1, col2, col3 = st.columns(3)
            
            with col1:
                concentration = row.get('高风险行业集中度', 0)
                limit = row.get('集中度限额', 0)
                st.metric(
                    "🎯 集中度",
                    f"{concentration:.2%}",
                    delta=f"限额: {limit:.2%}",
                    delta_color="normal"
                )
            
            with col2:
                total_position = row.get('高风险行业总持仓_PR', 0)
                st.metric(
                    "💰 总持仓",
                    f"{total_position:,.2f}万"
                )
            
            with col3:
                remaining = row.get('高风险行业总持仓剩余额度(万)', 0)
                is_overlimit = remaining < 0
                status = "⚠️ 超限" if is_overlimit else "✅ 正常"
                st.metric(
                    "状态",
                    status,
                    delta=f"剩余: {remaining:,.2f}万",
                    delta_color="inverse" if is_overlimit else "normal"
                )
            
            # 详细信息（可折叠）
            with st.expander("📊 查看详细指标"):
                col_a, col_b = st.columns(2)
                with col_a:
                    st.metric("行业类别", str(row.get('行业类别', 'N/A')))
                with col_b:
                    st.metric("集中度限额", f"{row.get('集中度限额', 0):.2%}")
            
            st.markdown("---")
            
            # 明细表格 + 可视化
            if '行业类别' in df_detail.columns:
                industry_detail = df_detail[df_detail['行业类别'] == '高风险行业'].copy()
                
                if len(industry_detail) > 0:
                    # 增强的汇总表
                    industry_summary = industry_detail.groupby('wind行业').agg({
                        '库存数量(万)_PR': 'sum',
                        '资产代码': 'count',
                        '是否超限': lambda x: (x == '是').sum()
                    }).reset_index()
                    industry_summary.columns = ['行业', '持仓(万)', '债券数', '超限数']
                    
                    # 计算占比
                    total = industry_summary['持仓(万)'].sum()
                    industry_summary['占比'] = industry_summary['持仓(万)'] / total * 100
                    industry_summary['占比'] = industry_summary['占比'].map(lambda x: f"{x:.1f}%")
                    
                    # 添加状态
                    industry_summary['状态'] = industry_summary['超限数'].apply(
                        lambda x: '⚠️ 超限' if x > 0 else '✅ 正常'
                    )
                    
                    industry_summary = industry_summary.sort_values('持仓(万)', ascending=False)
                    
                    # 左右布局
                    col_left, col_right = st.columns([1, 1])
                    
                    with col_left:
                        st.markdown("### 📋 行业明细")
                        st.dataframe(
                            industry_summary,
                            width='stretch',
                            height=450,
                            hide_index=True
                        )
                    
                    with col_right:
                        st.markdown("### 📊 持仓分布")
                        # 柱状图
                        fig = px.bar(
                            industry_summary.head(10),
                            x='行业',
                            y='持仓(万)',
                            color='状态',
                            title='Top10行业持仓分布',
                            labels={'持仓(万)': '持仓(万)', '行业': '行业'},
                            color_discrete_map={'✅ 正常': '#2ecc71', '⚠️ 超限': '#e74c3c'}
                        )
                        fig.update_layout(xaxis_tickangle=-45)
                        st.plotly_chart(fig, width='stretch')
                    
                    # 可选：展开债券明细
                    with st.expander("🔍 查看债券级别明细"):
                        filtered_detail = apply_filters(industry_detail, filters)
                        display_columns = [
                            '日期', 'wind行业', '内部证券账户名称', '资产代码', '资产名称',
                            '债务主体', '库存数量(万)_PR', '是否超限'
                        ]
                        display_columns = [col for col in display_columns if col in filtered_detail.columns]
                        render_data_table(
                            filtered_detail[display_columns],
                            height=400,
                            export_key="export_page5_industry_detail"
                        )
