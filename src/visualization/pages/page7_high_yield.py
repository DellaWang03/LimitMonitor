"""
页面7：高收益明细 - 现代金融看板风格
"""
import streamlit as st
import pandas as pd
from src.visualization.components.tables import render_data_table


def render(filters: dict, data_loader):
    """渲染高收益明细页面"""
    # 页面标题
    st.markdown("""
    <div style="margin-bottom: 24px;">
        <h1 style="font-size: 1.75rem; font-weight: 700; color: #0f172a; margin: 0;">
            💰 高收益明细
        </h1>
        <p style="font-size: 0.875rem; color: #64748b; margin: 8px 0 0 0;">
            年度高收益债券投资本金规模监控
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    with st.spinner("加载数据中..."):
        df_high_yield = data_loader.load_stage2_high_yield()
        df_capital = data_loader.load_stage2_high_yield_capital()
    
    # KPI卡片区域
    if len(df_capital) > 0:
        total_capital = df_capital['全价成本(元)'].sum() / 10000  # 转为万元
        limit = 50000  # 限额5万
        remaining = limit - total_capital
        usage_rate = (total_capital / limit * 100) if limit > 0 else 0
        is_overlimit = remaining < 0
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.markdown(f"""
            <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px;">
                <p style="font-size: 0.7rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; margin: 0 0 8px 0;">全价成本</p>
                <p style="font-size: 1.75rem; font-weight: 700; color: #3b82f6; margin: 0;">{total_capital/10000:,.2f}</p>
                <p style="font-size: 0.75rem; color: #94a3b8; margin: 4px 0 0 0;">亿元</p>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            st.markdown(f"""
            <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px;">
                <p style="font-size: 0.7rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; margin: 0 0 8px 0;">限额</p>
                <p style="font-size: 1.75rem; font-weight: 700; color: #1e293b; margin: 0;">{limit/10000:,.0f}</p>
                <p style="font-size: 0.75rem; color: #94a3b8; margin: 4px 0 0 0;">亿元</p>
            </div>
            """, unsafe_allow_html=True)
        
        with col3:
            remaining_color = "#ef4444" if is_overlimit else "#22c55e"
            remaining_bg = "#fef2f2" if is_overlimit else "#f0fdf4"
            st.markdown(f"""
            <div style="background: {remaining_bg}; border: 1px solid {'#fecaca' if is_overlimit else '#bbf7d0'}; border-radius: 12px; padding: 20px;">
                <p style="font-size: 0.7rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; margin: 0 0 8px 0;">剩余额度</p>
                <p style="font-size: 1.75rem; font-weight: 700; color: {remaining_color}; margin: 0;">{remaining/10000:,.2f}</p>
                <p style="font-size: 0.75rem; color: {remaining_color}; margin: 4px 0 0 0;">亿元</p>
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
    
    # 标签页
    tab1, tab2 = st.tabs(["投资本金明细", "持仓汇总分析"])
    
    with tab1:
        if len(df_capital) > 0:
            # 搜索框
            search_keyword = st.text_input(
                "搜索", 
                placeholder="🔍 输入账户、代码或简称...",
                key="high_yield_search",
                label_visibility="collapsed"
            )
            
            display_columns = [
                '日期', '账户', '简称', '代码',
                '持仓面额(元)', '全价成本(元)'
            ]
            
            display_columns = [col for col in display_columns if col in df_capital.columns]
            display_df = df_capital[display_columns].copy()
            
            # 应用搜索筛选
            if search_keyword:
                mask = False
                search_columns = ['账户', '简称', '代码']
                for col in search_columns:
                    if col in display_df.columns:
                        mask = mask | display_df[col].astype(str).str.contains(search_keyword, na=False, case=False)
                display_df = display_df[mask]
            
            # 转换单位（元 -> 万元）
            if '持仓面额(元)' in display_df.columns:
                display_df['持仓面额(万)'] = display_df['持仓面额(元)'] / 10000
            if '全价成本(元)' in display_df.columns:
                display_df['全价成本(万)'] = display_df['全价成本(元)'] / 10000
            
            # 删除原始列
            display_df = display_df.drop(columns=['持仓面额(元)', '全价成本(元)'], errors='ignore')
            
            # 格式化数值列（智能保留小数）
            def smart_format(val):
                if pd.isna(val):
                    return ''
                if isinstance(val, (int, float)):
                    if val == int(val):
                        return f"{int(val):,}"
                    elif abs(val * 10 - int(val * 10)) < 0.01:
                        return f"{val:,.1f}"
                    else:
                        return f"{val:,.2f}"
                return str(val)
            
            for col in display_df.columns:
                if pd.api.types.is_datetime64_any_dtype(display_df[col]):
                    display_df[col] = display_df[col].dt.strftime('%Y-%m-%d')
                elif pd.api.types.is_numeric_dtype(display_df[col]):
                    display_df[col] = display_df[col].apply(smart_format)
            
            # 统计信息
            st.markdown(f"""
            <div style="display: flex; gap: 16px; margin: 12px 0;">
                <span style="background: #f1f5f9; padding: 6px 12px; border-radius: 6px; font-size: 0.8rem;">
                    📊 共 <strong>{len(display_df)}</strong> 条
                </span>
            </div>
            """, unsafe_allow_html=True)
            
            st.dataframe(
                display_df,
                use_container_width=True,
                height=450,
                hide_index=True
            )
            
            # 导出按钮
            from io import BytesIO
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                display_df.to_excel(writer, index=False, sheet_name='高收益投资本金')
            excel_data = output.getvalue()
            
            st.download_button(
                label="📥 导出",
                data=excel_data,
                file_name=f"高收益投资本金规模_{pd.Timestamp.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="export_page7_high_yield_capital"
            )
    
    with tab2:
        col_left, col_right = st.columns([1, 1])
        
        with col_left:
            st.markdown("#### 按资产名称汇总")
            
            if len(df_high_yield) > 0:
                # 按资产代码汇总
                asset_summary = df_high_yield.groupby(['资产代码', '资产名称']).agg({
                    '库存数量(万)_PR': 'sum'
                }).reset_index()
                asset_summary.columns = ['资产代码', '资产名称', 'PR后规模(万)']
                asset_summary = asset_summary.sort_values('PR后规模(万)', ascending=False)
                
                # 计算总计值
                total_val = asset_summary['PR后规模(万)'].sum()
                
                # 格式化数值列
                def smart_format(val):
                    if pd.isna(val):
                        return ''
                    if isinstance(val, (int, float)):
                        if val == int(val):
                            return f"{int(val):,}"
                        elif abs(val * 10 - int(val * 10)) < 0.01:
                            return f"{val:,.1f}"
                        else:
                            return f"{val:,.2f}"
                    return str(val)
                
                asset_summary['PR后规模(万)'] = asset_summary['PR后规模(万)'].apply(smart_format)
                
                # 添加总计行
                total_row = pd.DataFrame([{
                    '资产代码': '合计',
                    '资产名称': '',
                    'PR后规模(万)': smart_format(total_val)
                }])
                asset_summary_with_total = pd.concat([asset_summary, total_row], ignore_index=True)
                
                st.dataframe(
                    asset_summary_with_total,
                    use_container_width=True,
                    height=350,
                    hide_index=True
                )
        
        with col_right:
            st.markdown("#### 按债务主体汇总")
            
            if len(df_high_yield) > 0:
                # 按债务主体汇总
                issuer_summary = df_high_yield.groupby('债务主体').agg({
                    '库存数量(万)_PR': 'sum'
                }).reset_index()
                issuer_summary.columns = ['债务主体', 'PR后规模(万)']
                issuer_summary = issuer_summary.sort_values('PR后规模(万)', ascending=False)
                
                # 计算总计值
                total_val = issuer_summary['PR后规模(万)'].sum()
                
                # 格式化数值列
                def smart_format(val):
                    if pd.isna(val):
                        return ''
                    if isinstance(val, (int, float)):
                        if val == int(val):
                            return f"{int(val):,}"
                        elif abs(val * 10 - int(val * 10)) < 0.01:
                            return f"{val:,.1f}"
                        else:
                            return f"{val:,.2f}"
                    return str(val)
                
                issuer_summary['PR后规模(万)'] = issuer_summary['PR后规模(万)'].apply(smart_format)
                
                # 添加总计行
                total_row = pd.DataFrame([{
                    '债务主体': '合计',
                    'PR后规模(万)': smart_format(total_val)
                }])
                issuer_summary_with_total = pd.concat([issuer_summary, total_row], ignore_index=True)
                
                st.dataframe(
                    issuer_summary_with_total,
                    use_container_width=True,
                    height=350,
                    hide_index=True
                )
