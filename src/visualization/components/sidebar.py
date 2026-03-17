"""
左侧导航栏组件 - 现代金融看板风格
"""
import streamlit as st
from datetime import datetime, date
from typing import Optional


def render_sidebar(data_loader, current_page=None) -> tuple[str, Optional[date]]:
    """
    渲染左侧导航栏（包含日期选择器）
    
    Args:
        data_loader: 数据加载器实例
        current_page: 当前选中的页面名称
    
    Returns:
        tuple: (选中的页面名称, 选中的日期)
    """
    with st.sidebar:
        # Logo和标题 - 现代简洁风格
        st.markdown("""
        <div style="padding: 1rem 0 1.5rem 0;">
            <h1 style="font-size: 1.5rem; font-weight: 700; color: #f8fafc; margin: 0; display: flex; align-items: center; gap: 10px;">
                <span style="font-size: 1.75rem;">📊</span> 限额监控
            </h1>
            <p style="font-size: 0.75rem; color: #94a3b8; margin: 0.5rem 0 0 0;">
                Risk Limit Monitoring System
            </p>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("---")
        
        # ========== 日期选择器 ==========
        st.markdown("""
        <p style="font-size: 0.7rem; font-weight: 600; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 0.5rem;">
            数据日期
        </p>
        """, unsafe_allow_html=True)
        
        # 日期模式选择
        date_mode = st.radio(
            "数据源",
            options=["最新数据", "历史数据"],
            key="date_mode",
            label_visibility="collapsed",
            horizontal=True
        )
        
        target_date = None
        
        if date_mode == "历史数据":
            # 导入 DataLoader 以获取可用日期
            from src.visualization.data_loader import DataLoader as DL
            available_dates = DL.get_available_dates()
            
            if available_dates:
                target_date = st.selectbox(
                    "选择日期",
                    options=available_dates,
                    format_func=lambda d: d.strftime('%Y年%m月%d日'),
                    key="selected_date",
                    label_visibility="collapsed"
                )
                # 显示当前日期指示器
                st.markdown(f"""
                <div style="background: rgba(59, 130, 246, 0.15); border-radius: 6px; padding: 8px 12px; margin-top: 8px;">
                    <span style="color: #93c5fd; font-size: 0.8rem;">📅 {target_date.strftime('%Y-%m-%d')}</span>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.warning("暂无历史数据")
        else:
            # 显示最新数据日期
            latest_date = data_loader.get_latest_date()
            st.markdown(f"""
            <div style="background: rgba(34, 197, 94, 0.15); border-radius: 6px; padding: 8px 12px; margin-top: 8px;">
                <span style="color: #86efac; font-size: 0.8rem;">📅 {latest_date.strftime('%Y-%m-%d')}</span>
            </div>
            """, unsafe_allow_html=True)
        
        st.markdown("---")
        
        # 页面导航
        st.markdown("""
        <p style="font-size: 0.7rem; font-weight: 600; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 0.5rem;">
            功能模块
        </p>
        """, unsafe_allow_html=True)
        
        pages = [
            ("单一信用限额", "📋"),
            ("特定信用限额", "📌"),
            ("分类信用限额", "📑"),
            ("专业担保明细", "🏢"),
            ("高风险类明细", "⚠️"),
            ("地域类明细", "🗺️"),
            ("高收益明细", "💰"),
            ("单券可购额度查询", "🔍"),
        ]
        
        # 使用radio按钮组
        page_names = [f"{emoji} {name}" for name, emoji in pages]
        selected = st.radio(
            "选择页面",
            page_names,
            label_visibility="collapsed"
        )
        
        # 提取页面名称（去掉emoji）
        selected_page = selected.split(" ", 1)[1]
        
        st.markdown("---")
        
        # 快捷操作
        st.markdown("""
        <p style="font-size: 0.7rem; font-weight: 600; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 0.5rem;">
            快捷操作
        </p>
        """, unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 刷新", width='stretch'):
                st.cache_data.clear()
                st.rerun()
        with col2:
            if st.button("📥 导出", width='stretch'):
                st.info("开发中...")
        
    return selected_page, target_date


def _render_page_metrics(data_loader, page_name: str):
    """
    根据页面名称渲染对应的统计指标
    
    Args:
        data_loader: 数据加载器
        page_name: 页面名称
    """
    try:
        if page_name == "单一信用限额":
            df = data_loader.load_stage1_credit_1_2()
            st.caption(f"📅 数据日期: {df['日期'].max().strftime('%Y-%m-%d')}")
            st.caption(f"📊 债券总数: {df['资产代码'].nunique()}只")
            overlimit = len(df[df['是否超限'] == '是'])
            st.caption(f"⚠️ 超限债券: {overlimit}只")
            
        elif page_name == "特定信用限额":
            df = data_loader.load_stage1_credit_1_1()
            st.caption(f"📅 数据日期: {df['日期'].max().strftime('%Y-%m-%d')}")
            st.caption(f"📊 债券总数: {df['资产代码'].nunique()}只")
            
        elif page_name == "分类信用限额":
            df = data_loader.load_stage1_credit_1_2()
            st.caption(f"📅 数据日期: {df['日期'].max().strftime('%Y-%m-%d')}")
            if '债券分类2' in df.columns:
                st.caption(f"📑 分类数量: {df['债券分类2'].nunique()}类")
            st.caption(f"📊 债券总数: {df['资产代码'].nunique()}只")
            
        elif page_name == "专业担保明细":
            df = data_loader.load_stage1_guarantee()
            st.caption(f"📅 数据日期: {df['日期'].max().strftime('%Y-%m-%d')}")
            st.caption(f"🏢 担保公司: {len(df)}家")
            if '单一担保人总持仓_PR' in df.columns:
                total_pos = df['单一担保人总持仓_PR'].sum()
                st.caption(f"💰 总持仓: {total_pos:,.0f}万")
            
        elif page_name == "高风险类明细":
            df = data_loader.load_stage2_credit_2()
            st.caption(f"📅 数据日期: {df['日期'].max().strftime('%Y-%m-%d')}")
            if '省份类别' in df.columns:
                high_risk_province = df[df['省份类别'] == '高风险省份']
                st.caption(f"🗺️ 高风险省份: {high_risk_province['省份'].nunique()}个")
            if '行业类别' in df.columns:
                high_risk_industry = df[df['行业类别'] == '高风险行业']
                st.caption(f"🏭 高风险行业: {high_risk_industry['wind行业'].nunique()}个")
            
        elif page_name == "地域类明细":
            df = data_loader.load_stage2_regional()
            if '日期' in df.columns:
                st.caption(f"📅 数据日期: {df['日期'].max().strftime('%Y-%m-%d')}")
            st.caption(f"🗺️ 省份数量: {len(df)}个")
            if '单一地域总持仓_PR' in df.columns:
                total_pos = df['单一地域总持仓_PR'].sum()
                st.caption(f"💰 总持仓: {total_pos:,.0f}万")
            
        elif page_name == "高收益明细":
            df = data_loader.load_stage2_high_yield()
            st.caption(f"📅 数据日期: {df['日期'].max().strftime('%Y-%m-%d')}")
            st.caption(f"💎 高收益债券: {df['资产代码'].nunique()}只")
            if '库存数量(万)_PR' in df.columns:
                total_pos = df['库存数量(万)_PR'].sum()
                st.caption(f"💰 投资规模: {total_pos:,.0f}万")
        
        elif page_name == "单券可购额度查询":
            df = data_loader.load_stage1_credit_1_2()
            if '日期' in df.columns:
                st.caption(f"📅 数据日期: {df['日期'].max().strftime('%Y-%m-%d')}")
            st.caption("🔍 输入债券代码/名称查询可购额度")
        
        else:
            # 默认显示全局信息
            metrics = data_loader.get_summary_metrics()
            st.caption(f"📅 数据日期: {metrics['latest_date']}")
            st.caption(f"📊 总记录: {metrics['total_count']}条")
            st.caption(f"⚠️ 超限记录: {metrics['overlimit_count']}条")
    
    except Exception as e:
        # 出错时显示默认信息
        st.caption(f"📅 数据日期: {data_loader.get_latest_date().strftime('%Y-%m-%d')}")
        st.caption("ℹ️ 加载统计信息...")
