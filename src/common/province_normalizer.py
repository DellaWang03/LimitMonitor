"""
省份名称标准化工具
解决省份字段在不同数据源中的格式不一致问题
"""

import pandas as pd
from typing import Union, List
from loguru import logger


class ProvinceNormalizer:
    """省份名称标准化器"""
    
    # 标准省份名称映射表（包含所有可能的变体）
    PROVINCE_MAPPING = {
        # 直辖市
        '北京': '北京市',
        '上海': '上海市',
        '天津': '天津市',
        '重庆': '重庆市',
        
        # 省份（23个）
        '河北': '河北省',
        '山西': '山西省',
        '辽宁': '辽宁省',
        '吉林': '吉林省',
        '黑龙江': '黑龙江省',
        '江苏': '江苏省',
        '浙江': '浙江省',
        '安徽': '安徽省',
        '福建': '福建省',
        '江西': '江西省',
        '山东': '山东省',
        '河南': '河南省',
        '湖北': '湖北省',
        '湖南': '湖南省',
        '广东': '广东省',
        '海南': '海南省',
        '四川': '四川省',
        '贵州': '贵州省',
        '云南': '云南省',
        '陕西': '陕西省',
        '甘肃': '甘肃省',
        '青海': '青海省',
        '台湾': '台湾省',
        
        # 自治区（5个）
        '内蒙古': '内蒙古自治区',
        '内蒙': '内蒙古自治区',
        '广西': '广西壮族自治区',
        '西藏': '西藏自治区',
        '宁夏': '宁夏回族自治区',
        '新疆': '新疆维吾尔自治区',
        
        # 特别行政区（2个）
        '香港': '香港特别行政区',
        '澳门': '澳门特别行政区',
        
        # 特殊值（非省份但合法）
        '海外': '海外',
        '境外': '境外',
    }
    
    # 所有标准省份名称（用于反向查找）
    STANDARD_PROVINCES = set(PROVINCE_MAPPING.values())
    
    @classmethod
    def normalize(cls, province_name: Union[str, pd.Series]) -> Union[str, pd.Series]:
        """
        标准化省份名称
        
        参数:
            province_name: 省份名称（字符串或Series）
        
        返回:
            标准化后的省份名称
        
        示例:
            >>> normalize('云南')
            '云南省'
            >>> normalize('内蒙')
            '内蒙古自治区'
        """
        if isinstance(province_name, pd.Series):
            return province_name.apply(cls._normalize_single)
        else:
            return cls._normalize_single(province_name)
    
    @classmethod
    def _normalize_single(cls, name: str) -> str:
        """标准化单个省份名称"""
        if pd.isna(name):
            return name
        
        # 清理首尾空格和特殊字符
        name = str(name).strip()
        
        # 如果已经是标准格式，直接返回
        if name in cls.STANDARD_PROVINCES:
            return name
        
        # 尝试从映射表中查找
        if name in cls.PROVINCE_MAPPING:
            return cls.PROVINCE_MAPPING[name]
        
        # 尝试模糊匹配（去除常见后缀）
        name_base = name
        for suffix in ['省', '市', '自治区', '特别行政区', '壮族', '回族', '维吾尔']:
            name_base = name_base.replace(suffix, '')
        
        if name_base in cls.PROVINCE_MAPPING:
            return cls.PROVINCE_MAPPING[name_base]
        
        # 无法标准化，返回原值并记录警告
        logger.warning(f"⚠️  无法标准化省份名称: {name}")
        return name
    
    @classmethod
    def validate_dataframe(cls, df: pd.DataFrame, column: str = '省份') -> dict:
        """
        验证DataFrame中省份字段的标准化情况
        
        参数:
            df: 待验证的DataFrame
            column: 省份字段名
        
        返回:
            统计信息字典
        """
        if column not in df.columns:
            return {'error': f'列 {column} 不存在'}
        
        unique_provinces = df[column].dropna().unique()
        
        stats = {
            'total_unique': len(unique_provinces),
            'standard': [],
            'non_standard': [],
            'unmapped': []
        }
        
        for prov in unique_provinces:
            prov_clean = str(prov).strip()
            if prov_clean in cls.STANDARD_PROVINCES:
                stats['standard'].append(prov_clean)
            elif prov_clean in cls.PROVINCE_MAPPING:
                stats['non_standard'].append({
                    'original': prov_clean,
                    'standard': cls.PROVINCE_MAPPING[prov_clean]
                })
            else:
                stats['unmapped'].append(prov_clean)
        
        return stats
    
    @classmethod
    def add_normalized_column(cls, df: pd.DataFrame, 
                             source_column: str = '省份',
                             target_column: str = '省份_标准') -> pd.DataFrame:
        """
        在DataFrame中添加标准化后的省份列
        
        参数:
            df: 原始DataFrame
            source_column: 源省份列名
            target_column: 目标标准列名
        
        返回:
            添加了标准列的DataFrame
        """
        if source_column not in df.columns:
            logger.warning(f"列 {source_column} 不存在，跳过标准化")
            return df
        
        df[target_column] = cls.normalize(df[source_column])
        
        # 统计标准化效果
        changed = (df[source_column] != df[target_column]).sum()
        if changed > 0:
            logger.info(f"✓ 省份标准化: {changed}/{len(df)} 条记录被标准化")
        
        return df
