"""
字段映射配置
根据实际 Excel 文件的列名进行映射
"""

# 债券持仓表字段映射
BOND_HOLDINGS_MAPPING = {
    '债券代码': '代码',
    '债券简称': '简称',
    '发行人名称': '发行人',
    '市值': '市值(元)',
    '持仓面额': '持仓面额(元)',
    '债券分类': '利率信用债划分',
    '债券类型': 'WIND一级市场',
    '是否城投债': '是否城投债',
    '是否高收益': '是否高收益',
}

# 风控部债券池字段映射
BOND_POOL_MAPPING = {
    '债券代码': '债券代码',
    '债券名称': '债券名称',
    '发行人名称': '发行人名称',
    '主体wind代码': '主体wind代码',
}

# 主体池字段映射
ISSUER_POOL_MAPPING = {
    '发行人wind代码': '发行人wind代码',
    '发行人名称': '发行人名称',
}

# 实控人映射字段
CONTROLLER_MAPPING = {
    '主体wind代码': '主体wind代码',
    '主体名称': '主体名称',
    '实际控制人': '调整后实际控制人',
}


def get_field_name(df, field_key: str, mapping: dict) -> str:
    """
    获取实际的字段名
    
    Args:
        df: DataFrame
        field_key: 标准字段名
        mapping: 字段映射字典
        
    Returns:
        实际字段名，如果不存在则返回 None
    """
    if field_key in mapping:
        actual_name = mapping[field_key]
        if actual_name in df.columns:
            return actual_name
    
    # 如果映射中的名称不存在，尝试直接使用标准名
    if field_key in df.columns:
        return field_key
        
    return None
