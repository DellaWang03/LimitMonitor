"""
顶部筛选器组件
"""
import streamlit as st
from typing import Dict, Any


def _normalize_account_filter(account_filter) -> list[str]:
    """将账户筛选统一为账户名称列表；空列表表示全部账户。"""
    if not account_filter or account_filter == '全部':
        return []
    if isinstance(account_filter, (list, tuple, set)):
        return [
            str(item)
            for item in account_filter
            if item and item != '全部'
        ]
    return [str(account_filter)]


def render_top_filters(data_loader, page_name: str) -> Dict[str, Any]:
    """
    渲染顶部筛选器
    
    Returns:
        Dict: 筛选条件字典
    """
    # 债券分类和账户列表在同一数据源+页面下不会改变，缓存到 session_state 避免每次 rerun 重复
    # 计算 .copy() + unique() + sorted()。刷新按钮会清除这些缓存键（见 sidebar.py）。
    _lists_key = f"_filter_lists_{data_loader.data_source}_{page_name}"
    if _lists_key not in st.session_state:
        if hasattr(data_loader, "get_filter_options"):
            st.session_state[_lists_key] = data_loader.get_filter_options(
                page_name=page_name
            )
        else:
            st.session_state[_lists_key] = {
                'bond_types': data_loader.get_available_bond_types(page_name=page_name),
                'accounts': data_loader.get_available_accounts(page_name=page_name),
            }
    bond_types = st.session_state[_lists_key]['bond_types']
    accounts = st.session_state[_lists_key]['accounts']

    if page_name == "高收益明细":
        col1, col2 = st.columns([1.4, 2.6])
        with col1:
            account_options = [account for account in accounts if account != '全部']
            selected_account = st.multiselect(
                "内部证券账户",
                account_options,
                default=[],
                placeholder="全部账户",
                key=f"{page_name}_account_multiselect",
            )
        with col2:
            search_code = st.text_input(
                "关键词搜索",
                placeholder="输入账户、代码、简称、资产名称或债务主体",
                key=f"{page_name}_search_keyword",
            )
        return {
            'bond_type': '全部',
            'account': selected_account,
            'search_keyword': search_code,
            'quality': '全部',
            'quality_field': '是否超限'
        }

    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        selected_bond_type = st.selectbox(
            "债券分类",
            bond_types,
            index=0
        )
    
    with col2:
        account_options = [account for account in accounts if account != '全部']
        selected_account = st.multiselect(
            "内部证券账户",
            account_options,
            default=[],
            placeholder="全部账户",
            key=f"{page_name}_account_multiselect",
        )
    
    with col3:
        search_code = st.text_input(
            "关键词搜索",
            placeholder="输入代码、名称、主体、实控人或担保人"
        )
    
    with col4:
        quality_options = ["全部", "是", "否"]
        selected_quality = st.selectbox(
            "综合超限",
            quality_options,
            index=0
        )

    return {
        'bond_type': selected_bond_type,
        'account': selected_account,
        'search_keyword': search_code,
        'quality': selected_quality,
        'quality_field': '是否超限'
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
    selected_accounts = _normalize_account_filter(filters.get('account'))
    if selected_accounts and '内部证券账户名称' in filtered_df.columns:
        filtered_df = filtered_df[
            filtered_df['内部证券账户名称'].astype(str).isin(selected_accounts)
        ]
    
    # 搜索关键词筛选
    if filters.get('search_keyword'):
        keyword = filters['search_keyword'].lower()
        # 在多个列中搜索
        search_columns = [
            '代码',
            'ISIN码',
            '资产代码',
            '资产名称',
            '证券名称',
            '债务主体',
            '实际控制人名称_修正',
            '调整后实际控制人',
            '担保人'
        ]
        mask = False
        for col in search_columns:
            if col in filtered_df.columns:
                mask = mask | filtered_df[col].astype(str).str.lower().str.contains(keyword, na=False)
        if isinstance(mask, bool) and not mask:
            # 如果没有找到任何匹配的列，返回原数据
            pass
        else:
            filtered_df = filtered_df[mask]
    
    # 综合超限筛选
    quality_field = filters.get('quality_field')
    if filters.get('quality') and filters['quality'] != '全部' and quality_field and quality_field in filtered_df.columns:
        filtered_df = filtered_df[filtered_df[quality_field] == filters['quality']]

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
