"""
顶部筛选器组件
"""
import streamlit as st
from typing import Dict, Any


def render_top_filters(data_loader) -> Dict[str, Any]:
    """
    渲染顶部筛选器
    
    Returns:
        Dict: 筛选条件字典
    """
    st.markdown('<div class="filter-container">', unsafe_allow_html=True)
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        bond_types = data_loader.get_available_bond_types()
        selected_bond_type = st.selectbox(
            "债券分类",
            bond_types,
            index=0
        )
    
    with col2:
        accounts = data_loader.get_available_accounts()
        selected_account = st.selectbox(
            "内部证券账户/产品",
            accounts,
            index=0
        )
    
    with col3:
        search_code = st.text_input(
            "代码/名称/债务主体",
            placeholder="输入搜索关键词..."
        )
    
    with col4:
        quality_options = ["全部", "是", "否"]
        selected_quality = st.selectbox(
            "实质",
            quality_options,
            index=0
        )
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    return {
        'bond_type': selected_bond_type,
        'account': selected_account,
        'search_keyword': search_code,
        'quality': selected_quality
    }


def apply_filters(df, filters: Dict[str, Any]):
    """
    应用筛选条件到DataFrame
    
    Args:
        df: 原始DataFrame
        filters: 筛选条件字典（可以为空字典）
        
    Returns:
        pd.DataFrame: 筛选后的DataFrame
    """
    filtered_df = df.copy()
    
    # 如果filters为空，直接返回原数据
    if not filters:
        return filtered_df
    
    # 债券分类筛选
    if filters.get('bond_type') and filters['bond_type'] != '全部' and '债券分类2' in filtered_df.columns:
        filtered_df = filtered_df[filtered_df['债券分类2'] == filters['bond_type']]
    
    # 账户筛选
    if filters.get('account') and filters['account'] != '全部' and '内部证券账户名称' in filtered_df.columns:
        filtered_df = filtered_df[filtered_df['内部证券账户名称'] == filters['account']]
    
    # 搜索关键词筛选
    if filters.get('search_keyword'):
        keyword = filters['search_keyword'].lower()
        # 在多个列中搜索
        search_columns = ['资产代码', '资产名称', '债务主体']
        mask = False
        for col in search_columns:
            if col in filtered_df.columns:
                mask = mask | filtered_df[col].astype(str).str.lower().str.contains(keyword, na=False)
        if isinstance(mask, bool) and not mask:
            # 如果没有找到任何匹配的列，返回原数据
            pass
        else:
            filtered_df = filtered_df[mask]
    
    # 实质筛选
    if filters.get('quality') and filters['quality'] != '全部' and '是否超限' in filtered_df.columns:
        filtered_df = filtered_df[filtered_df['是否超限'] == filters['quality']]
    
    # 高风险行业是否超限筛选
    if filters.get('high_risk_industry') and filters['high_risk_industry'] != '全部' and '高风险行业是否超限' in filtered_df.columns:
        filtered_df = filtered_df[filtered_df['高风险行业是否超限'] == filters['high_risk_industry']]
    
    # 高风险省份是否超限筛选
    if filters.get('high_risk_province') and filters['high_risk_province'] != '全部' and '高风险省份是否超限' in filtered_df.columns:
        filtered_df = filtered_df[filtered_df['高风险省份是否超限'] == filters['high_risk_province']]
    
    # 地域集中度是否超限筛选
    if filters.get('regional_concentration') and filters['regional_concentration'] != '全部' and '地域集中度是否超限' in filtered_df.columns:
        filtered_df = filtered_df[filtered_df['地域集中度是否超限'] == filters['regional_concentration']]
    
    # 城投集中度是否超限筛选
    if filters.get('citybond_concentration') and filters['citybond_concentration'] != '全部' and '城投集中度是否超限' in filtered_df.columns:
        filtered_df = filtered_df[filtered_df['城投集中度是否超限'] == filters['citybond_concentration']]
    
    return filtered_df
