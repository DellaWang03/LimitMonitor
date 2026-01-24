"""
债券数据转换器
用于债券数据的筛选、清洗和转换
"""

import pandas as pd
from typing import List, Optional
from ..utils.logger import get_logger


class BondTransformer:
    """债券数据转换器"""
    
    def __init__(self):
        """初始化转换器"""
        self.logger = get_logger()
        
    def filter_credit_bonds(
        self,
        bond_holdings: pd.DataFrame,
        credit_bond_types: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """
        筛选信用债
        
        Args:
            bond_holdings: 债券持仓数据
            credit_bond_types: 信用债类型列表（如果为None，使用默认列表）
            
        Returns:
            信用债持仓数据
        """
        # 优先使用"利率信用债划分"字段
        if '利率信用债划分' in bond_holdings.columns:
            self.logger.info("使用'利率信用债划分'字段筛选信用债")
            credit_bonds = bond_holdings[
                bond_holdings['利率信用债划分'] == '信用债'
            ].copy()
            
            self.logger.info(
                f"筛选信用债: {len(bond_holdings)} → {len(credit_bonds)} 条"
            )
            return credit_bonds
        
        # 备选：使用债券类型字段
        if credit_bond_types is None:
            # 默认信用债类型（根据实际情况调整）
            credit_bond_types = [
                '企业债', '公司债', '中期票据', '短期融资券',
                '定向工具', '资产支持证券', '可转债', '可交换债'
            ]
        
        # 检查是否有债券类型字段
        type_field = None
        for field in ['WIND一级市场', '债券类型', '品种', '证券类型']:
            if field in bond_holdings.columns:
                type_field = field
                break
                
        if type_field is None:
            self.logger.warning("未找到债券类型字段，返回所有数据")
            return bond_holdings
            
        # 筛选信用债
        credit_bonds = bond_holdings[
            bond_holdings[type_field].isin(credit_bond_types)
        ].copy()
        
        self.logger.info(
            f"筛选信用债: {len(bond_holdings)} → {len(credit_bonds)} 条"
        )
        
        return credit_bonds
    
    def merge_with_bond_pool(
        self,
        bond_holdings: pd.DataFrame,
        bond_pool: pd.DataFrame,
        bond_pool_issuers: pd.DataFrame
    ) -> pd.DataFrame:
        """
        关联债券池和主体信息
        
        Args:
            bond_holdings: 债券持仓数据
            bond_pool: 风控部债券池
            bond_pool_issuers: 风控部债券池_主体
            
        Returns:
            关联后的数据
        """
        # 1. 与债券池关联（获取债券详细信息，特别是主体wind代码）
        result = bond_holdings.copy()
        
        # 确定关联字段 - 使用实际字段名
        bond_code_field = self._find_field(
            result.columns, ['代码', '主证券代码', '债券代码', '证券代码']
        )
        pool_code_field = self._find_field(
            bond_pool.columns, ['债券代码', '代码', '证券代码']
        )
        
        if bond_code_field and pool_code_field:
            self.logger.info(f"关联债券池: {bond_code_field} ← {pool_code_field}")
            
            # 只选择需要的列，避免重复
            pool_cols_to_merge = [pool_code_field, '主体wind代码', '发行人名称', '债券名称']
            pool_cols_to_merge = [col for col in pool_cols_to_merge if col in bond_pool.columns]
            
            result = result.merge(
                bond_pool[pool_cols_to_merge],
                left_on=bond_code_field,
                right_on=pool_code_field,
                how='left',
                suffixes=('', '_池')
            )
            
            self.logger.info(f"关联后数据: {len(result)} 行")
            
            # 检查主体wind代码匹配情况
            if '主体wind代码' in result.columns:
                matched = result['主体wind代码'].notna().sum()
                self.logger.info(f"成功匹配主体wind代码: {matched}/{len(result)} 条")
        else:
            self.logger.warning(f"未找到债券代码字段进行关联")
        
        # 2. 与主体池关联（获取主体详细信息）- 可选
        # 暂时跳过，因为我们已经从债券池获得了主要信息
        
        return result
    
    def add_new_old_cutoff_flag(
        self,
        bond_holdings: pd.DataFrame,
        cutoff_bonds: pd.DataFrame
    ) -> pd.DataFrame:
        """
        添加新老划断标记
        
        Args:
            bond_holdings: 债券持仓数据
            cutoff_bonds: 新老划断表（包含需要标记的债券代码）
            
        Returns:
            添加了新老划断标记的数据
        """
        result = bond_holdings.copy()
        
        # 查找债券代码字段
        bond_code_field = self._find_field(
            result.columns, ['主证券代码', '债券代码']
        )
        cutoff_code_field = self._find_field(
            cutoff_bonds.columns, ['主证券代码', '债券代码']
        )
        
        if bond_code_field and cutoff_code_field:
            # 创建新老划断标记
            cutoff_codes = set(cutoff_bonds[cutoff_code_field].unique())
            result['是否新老划断'] = result[bond_code_field].isin(cutoff_codes)
            
            count = result['是否新老划断'].sum()
            self.logger.info(f"新老划断标记: {count} 条")
        else:
            result['是否新老划断'] = False
            self.logger.warning("未找到债券代码字段，无法标记新老划断")
        
        return result
    
    def _find_field(self, columns: pd.Index, candidates: List[str]) -> Optional[str]:
        """
        在列中查找第一个匹配的字段名
        
        Args:
            columns: DataFrame 的列索引
            candidates: 候选字段名列表
            
        Returns:
            第一个找到的字段名，如果都不存在则返回 None
        """
        for candidate in candidates:
            if candidate in columns:
                return candidate
        return None
    
    def convert_amounts(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        转换金额字段到统一单位（万元）
        
        Args:
            df: DataFrame
            
        Returns:
            转换后的 DataFrame
        """
        result = df.copy()
        
        # 常见的金额字段
        amount_fields = {
            '债券余额(亿)': 10000,  # 亿 → 万
            '库存数量': 1,           # 已经是万元
            '持仓金额': 1,
            '市值': 1
        }
        
        for field, multiplier in amount_fields.items():
            if field in result.columns:
                try:
                    result[field] = pd.to_numeric(
                        result[field], 
                        errors='coerce'
                    ) * multiplier
                    
                    self.logger.debug(f"转换字段 {field} (×{multiplier})")
                    
                except Exception as e:
                    self.logger.warning(f"转换字段 {field} 失败: {e}")
        
        return result


if __name__ == "__main__":
    # 测试转换器
    from ..utils.logger import setup_logger
    from ..extractors.bond_pool_extractor import BondPoolExtractor
    
    # 初始化日志
    setup_logger(level="DEBUG")
    
    # 创建提取器和转换器
    extractor = BondPoolExtractor()
    transformer = BondTransformer()
    
    try:
        # 提取数据
        bond_pool = extractor.get_bond_pool()
        bond_pool_issuers = extractor.get_bond_pool_issuers()
        
        print(f"\n债券池: {len(bond_pool)} 条")
        print(f"主体池: {len(bond_pool_issuers)} 条")
        
        # 测试筛选信用债（如果有持仓数据）
        bond_holdings = extractor.extract_bond_holdings()
        if not bond_holdings.empty:
            credit_bonds = transformer.filter_credit_bonds(bond_holdings)
            print(f"\n信用债: {len(credit_bonds)} 条")
        
    except Exception as e:
        print(f"\n测试失败: {e}")
        import traceback
        traceback.print_exc()
