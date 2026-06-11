"""
发行人映射器
用于主体级别的数据映射
"""

import pandas as pd
from ..utils.logger import get_logger


class IssuerMapper:
    """发行人映射器"""
    
    def __init__(self):
        """初始化映射器"""
        self.logger = get_logger()
        
    def map_issuer_info(
        self,
        bond_holdings: pd.DataFrame,
        bond_pool_issuers: pd.DataFrame
    ) -> pd.DataFrame:
        """
        映射发行人详细信息
        
        Args:
            bond_holdings: 债券持仓数据
            bond_pool_issuers: 主体池数据
            
        Returns:
            添加了发行人信息的数据
        """
        result = bond_holdings.merge(
            bond_pool_issuers,
            left_on='债务主体wind代码',
            right_on='发行人wind代码',
            how='left',
            suffixes=('', '_主体池')
        )
        
        self.logger.info(f"发行人信息映射完成: {len(result)} 条")
        
        return result
