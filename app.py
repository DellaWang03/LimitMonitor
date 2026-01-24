"""
限额监控可视化系统 - 主应用入口（支持历史数据）
"""
import streamlit as st
import sys
from pathlib import Path
from datetime import datetime, date

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
    page4_guarantee,
    page5_high_risk,
    page6_regional,
    page7_high_yield
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


def main():
    """主函数"""
    try:
        # 获取当前页面（用于sidebar显示统计信息）
        if 'current_page' not in st.session_state:
            st.session_state.current_page = '单一信用限额'
        
        # 临时初始化数据加载器（用于sidebar渲染，将在后面重新初始化）
        temp_loader = DataLoader(target_date=None)
        
        # 渲染左侧导航栏（包含日期选择器），获取选中的页面和日期
        selected_page, target_date = render_sidebar(temp_loader, st.session_state.current_page)
        
        # 更新当前页面
        st.session_state.current_page = selected_page
        
        # ========== 根据选中的日期初始化数据加载器 ==========
        data_loader = DataLoader(target_date=target_date)
        
        # 只在需要筛选器的页面显示顶部筛选器
        pages_with_filters = ['单一信用限额', '特定信用限额', '分类信用限额']
        
        if selected_page in pages_with_filters:
            filters = render_top_filters(data_loader)
        else:
            filters = {}  # 不显示筛选器
        
        # 根据选中页面渲染对应内容
        page_map = {
            '单一信用限额': page1_single_credit,
            '特定信用限额': page2_specific_credit,
            '分类信用限额': page3_category_credit,
            '专业担保明细': page4_guarantee,
            '高风险类明细': page5_high_risk,
            '地域类明细': page6_regional,
            '高收益明细': page7_high_yield
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
