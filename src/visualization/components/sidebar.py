"""
左侧导航栏组件 - 现代金融看板风格
"""
import streamlit as st
from datetime import date
from typing import Optional

SIDEBAR_BADGE_BG = "rgba(59, 130, 246, 0.14)"
SIDEBAR_BADGE_BORDER = "rgba(96, 165, 250, 0.22)"
SIDEBAR_BADGE_TEXT = "#dbeafe"


def render_sidebar(current_page=None) -> tuple[str, Optional[date]]:
    """
    渲染左侧导航栏（包含日期选择器）
    
    Args:
        current_page: 当前选中的页面名称
    
    Returns:
        tuple: (选中的页面名称, 选中的日期)
    """
    from src.visualization.data_loader import DataLoader as DL

    with st.sidebar:
        # Logo和标题 - 现代简洁风格
        st.markdown("""
        <div style="padding: 1rem 0 1.5rem 0;">
            <h1 style="font-size: 1.5rem; font-weight: 700; color: #f8fafc; margin: 0; display: flex; align-items: center; gap: 10px;">
                <span style="font-size: 1.75rem;">📊</span> 限额监控
            </h1>
            <p style="font-size: 0.75rem; color: #cbd5e1; margin: 0.5rem 0 0 0;">
                Risk Limit Monitoring System
            </p>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("---")
        
        # ========== 日期选择器 ==========
        st.markdown("""
        <p style="font-size: 0.7rem; font-weight: 600; color: #cbd5e1; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 0.5rem;">
            数据日期
        </p>
        """, unsafe_allow_html=True)
        
        current_archive_date = DL.get_current_archive_date()
        current_data_date = DL.get_current_data_date()
        available_date_options = DL.get_available_date_options()
        available_dates = [data_date for data_date, _ in available_date_options]
        archive_dates_by_data = {
            data_date: archive_date
            for data_date, archive_date in available_date_options
        }

        if "date_mode" not in st.session_state:
            st.session_state.date_mode = (
                "最新数据" if current_archive_date is not None else "历史数据"
            )

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
            def _format_data_option(d):
                archive_date = archive_dates_by_data.get(d)
                if archive_date:
                    return f"{d.strftime('%Y年%m月%d日')} (归档: {archive_date})"
                return d.strftime('%Y年%m月%d日')

            if available_dates:
                target_date = st.selectbox(
                    "选择日期",
                    options=available_dates,
                    format_func=_format_data_option,
                    key="selected_date",
                    label_visibility="collapsed"
                )
                # 显示当前选中：数据日 + 归档日（若有）
                archive_date_str = archive_dates_by_data.get(target_date)
                date_label = f"数据: {target_date.strftime('%Y-%m-%d')}"
                if archive_date_str:
                    date_label += f" · 归档: {archive_date_str}"
                st.markdown(f"""
                <div style="background: {SIDEBAR_BADGE_BG}; border: 1px solid {SIDEBAR_BADGE_BORDER}; border-radius: 8px; padding: 8px 12px; margin-top: 8px;">
                    <span style="color: {SIDEBAR_BADGE_TEXT}; font-size: 0.8rem;">📅 {date_label}</span>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.warning("暂无历史数据")
        else:
            if current_archive_date is None:
                st.warning("当前没有 latest 快照，请切换到历史数据或先运行 run_daily.sh")
            else:
                date_label = f"归档: {current_archive_date.strftime('%Y-%m-%d')}"
                if current_data_date:
                    date_label = f"数据: {current_data_date} · {date_label}"
                st.markdown(f"""
                <div style="background: {SIDEBAR_BADGE_BG}; border: 1px solid {SIDEBAR_BADGE_BORDER}; border-radius: 8px; padding: 8px 12px; margin-top: 8px;">
                    <span style="color: {SIDEBAR_BADGE_TEXT}; font-size: 0.8rem;">📅 {date_label}</span>
                </div>
                """, unsafe_allow_html=True)
        
        st.markdown("---")
        
        # 页面导航
        st.markdown("""
        <p style="font-size: 0.7rem; font-weight: 600; color: #cbd5e1; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 0.5rem;">
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
            ("债券组合超限试算", "🧺"),
        ]
        
        # 使用radio按钮组
        page_names = [f"{emoji} {name}" for name, emoji in pages]
        selected = st.radio(
            "选择页面",
            page_names,
            label_visibility="collapsed",
        )
        
        # 提取页面名称（去掉emoji）
        selected_page = selected.split(" ", 1)[1]
        
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
            st.caption(f"📊 监控对象数: {df['资产代码'].nunique()}个")
            overlimit = len(df[df['是否超限'] == '是'])
            st.caption(f"⚠️ 超限对象: {overlimit}个")
            
        elif page_name == "特定信用限额":
            df = data_loader.load_stage1_credit_1_1()
            st.caption(f"📅 数据日期: {df['日期'].max().strftime('%Y-%m-%d')}")
            st.caption(f"📊 监控对象数: {df['资产代码'].nunique()}个")
            
        elif page_name == "分类信用限额":
            df = data_loader.load_stage1_credit_1_2()
            st.caption(f"📅 数据日期: {df['日期'].max().strftime('%Y-%m-%d')}")
            if '债券分类2' in df.columns:
                st.caption(f"📑 分类数量: {df['债券分类2'].nunique()}类")
            st.caption(f"📊 监控对象数: {df['资产代码'].nunique()}个")
            
        elif page_name == "专业担保明细":
            df = data_loader.load_stage1_guarantee()
            st.caption(f"📅 数据日期: {df['日期'].max().strftime('%Y-%m-%d')}")
            st.caption(f"🏢 担保公司: {len(df)}家")
            if '单一担保人总持仓_PR' in df.columns:
                total_pos = df['单一担保人总持仓_PR'].sum()
                st.caption(f"💰 总持仓: {total_pos:,.0f}万")

        elif page_name == "全量债券监管集中度":
            df = data_loader.load_stage1_full_regulatory_concentration()
            st.caption(f"📅 数据日期: {df['日期'].max().strftime('%Y-%m-%d')}")
            st.caption(f"📊 监控对象数: {len(df)}个")
            if '是否可计算' in df.columns:
                calculable = len(df[df['是否可计算'] == '是'])
                st.caption(f"🧮 可计算对象: {calculable}个")
            
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
        # 出错时直接暴露当前快照/统计问题，避免显示伪正常默认值
        st.caption("⚠️ 统计信息加载失败")
        st.caption(str(e))
