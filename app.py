"""
限额监控可视化系统 - 主应用入口（支持历史数据）
"""
import streamlit as st
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.visualization.data_loader import DataLoader
from src.visualization.components.styles import apply_custom_styles
from src.visualization.components.sidebar import render_sidebar
from src.visualization.components.filters import render_top_filters
from src.visualization.pages import (
    page1_single_credit,
    page2_specific_credit,
    page3_category_credit,
    page9_full_regulatory,
    page4_guarantee,
    page5_high_risk,
    page6_regional,
    page7_high_yield,
    page8_bond_quota,
)


# 页面配置
st.set_page_config(
    page_title="限额监控系统",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 应用自定义样式
apply_custom_styles()


def _cleanup_page_state(previous_page: str, selected_page: str):
    """清理已离开页面的瞬时控件状态，减少切页时的额外重绘。"""
    if previous_page == selected_page:
        return

    if previous_page == '单一信用限额':
        keys_to_remove = [
            '_page1_compact_controls_css_injected',
            'page1_current_dimension_overlimit_shared',
            'page1_current_dimension_overlimit_shared_version',
            'page1_tab1_current_dimension_overlimit',
            'page1_tab1_current_dimension_overlimit__shared_version',
            'page1_tab2_current_dimension_overlimit',
            'page1_tab2_current_dimension_overlimit__shared_version',
            'page1_tab3_current_dimension_overlimit',
            'page1_tab3_current_dimension_overlimit__shared_version',
            'page1_tab4_current_dimension_overlimit',
            'page1_tab4_current_dimension_overlimit__shared_version',
            'page1_tab5_current_dimension_overlimit',
            'page1_tab5_current_dimension_overlimit__shared_version',
        ]
        for key in keys_to_remove:
            st.session_state.pop(key, None)

    elif previous_page == '特定信用限额':
        keys_to_remove = [
            '_page2_compact_controls_css_injected',
            'page2_current_dimension_overlimit_shared',
            'page2_current_dimension_overlimit_shared_version',
            'page2_tab1_current_dimension_overlimit',
            'page2_tab1_current_dimension_overlimit__shared_version',
            'page2_tab2_current_dimension_overlimit',
            'page2_tab2_current_dimension_overlimit__shared_version',
        ]
        for key in keys_to_remove:
            st.session_state.pop(key, None)

    elif previous_page == '分类信用限额':
        keys_to_remove = [
            '_page3_compact_controls_css_injected',
            'page3_current_dimension_overlimit_shared',
            'page3_current_dimension_overlimit_shared_version',
            'page3_tab1_current_dimension_overlimit',
            'page3_tab1_current_dimension_overlimit__shared_version',
            'page3_tab2_current_dimension_overlimit',
            'page3_tab2_current_dimension_overlimit__shared_version',
            'page3_tab3_current_dimension_overlimit',
            'page3_tab3_current_dimension_overlimit__shared_version',
            'page3_tab4_current_dimension_overlimit',
            'page3_tab4_current_dimension_overlimit__shared_version',
        ]
        for key in keys_to_remove:
            st.session_state.pop(key, None)


def main():
    """主函数"""
    try:
        # 获取当前页面（用于sidebar显示统计信息）
        if 'current_page' not in st.session_state:
            st.session_state.current_page = '单一信用限额'

        # 渲染左侧导航栏（包含日期选择器），获取选中的页面和日期
        selected_page, target_date = render_sidebar(st.session_state.current_page)

        # 切页后清理上一页的瞬时状态，避免页面树差异较大时出现额外状态框闪现
        _cleanup_page_state(st.session_state.current_page, selected_page)
        
        # 更新当前页面
        st.session_state.current_page = selected_page
        
        # ========== 根据选中的日期初始化数据加载器 ==========
        date_mode = st.session_state.get("date_mode", "最新数据")
        if date_mode == "历史数据":
            if target_date is None:
                raise FileNotFoundError("DB 中暂无可用历史快照，请先运行 scripts/daily_archive.py。")
            data_loader = DataLoader(target_date=target_date)
        else:
            data_loader = DataLoader(target_date=None)
        
        # 只在需要筛选器的页面显示顶部筛选器
        pages_with_filters = ['单一信用限额', '特定信用限额', '分类信用限额']
        
        if selected_page in pages_with_filters:
            filters = render_top_filters(data_loader, selected_page)
        else:
            filters = {}  # 不显示筛选器
        
        # 根据选中页面渲染对应内容
        page_map = {
            '单一信用限额': page1_single_credit,
            '特定信用限额': page2_specific_credit,
            '分类信用限额': page3_category_credit,
            '全量债券监管集中度': page9_full_regulatory,
            '专业担保明细': page4_guarantee,
            '高风险类明细': page5_high_risk,
            '地域类明细': page6_regional,
            '高收益明细': page7_high_yield,
            '单券可购额度查询': page8_bond_quota,
        }
        
        # 渲染选中的页面
        if selected_page in page_map:
            page_map[selected_page].render(filters, data_loader)
        else:
            st.error(f"未找到页面: {selected_page}")
    
    except FileNotFoundError as e:
        st.error(f"❌ 数据文件未找到: {str(e)}")
        st.info("💡 提示: 请先运行每日数据更新脚本生成数据")
        st.code("bash run_daily.sh  # macOS/Linux\nrun_daily.bat     # Windows")
    
    except Exception as e:
        st.error(f"❌ 系统错误: {str(e)}")
        import traceback
        with st.expander("查看详细错误信息"):
            st.code(traceback.format_exc())


if __name__ == "__main__":
    main()
