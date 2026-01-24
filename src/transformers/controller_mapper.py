"""
实控人映射器
用于将主体穿透映射到实际控制人
"""

import pandas as pd
from typing import Dict, Optional
from ..utils.logger import get_logger


class ControllerMapper:
    """实控人映射器"""
    
    def __init__(self):
        """初始化映射器"""
        self.logger = get_logger()
        
    def map_to_controller(
        self,
        bond_holdings: pd.DataFrame,
        controller_mapping: pd.DataFrame
    ) -> pd.DataFrame:
        """
        将债券持仓穿透映射到实际控制人
        
        Args:
            bond_holdings: 债券持仓数据（需包含主体wind代码）
            controller_mapping: 实控人映射表
            
        Returns:
            添加了实控人字段的数据
        """
        result = bond_holdings.copy()
        
        # 查找主体代码字段 - 使用实际字段名
        issuer_code_field = self._find_field(
            result.columns,
            ['主体wind代码', '债务主体wind代码', '发行人wind代码']
        )
        
        mapping_code_field = self._find_field(
            controller_mapping.columns,
            ['主体wind代码', '主体代码']
        )
        
        if not issuer_code_field:
            self.logger.error(f"未找到主体代码字段，无法进行实控人映射")
            self.logger.error(f"可用字段: {result.columns.tolist()[:10]}...")
            return result
            
        if not mapping_code_field:
            self.logger.error(f"实控人映射表中未找到主体代码字段")
            return result
            
        # 进行左连接
        self.logger.info(f"实控人映射: {issuer_code_field} ← {mapping_code_field}")
        
        # 准备映射表的列
        mapping_cols = [mapping_code_field]
        if '主体名称' in controller_mapping.columns:
            mapping_cols.append('主体名称')
        if '调整后实际控制人' in controller_mapping.columns:
            mapping_cols.append('调整后实际控制人')
            
        result = result.merge(
            controller_mapping[mapping_cols],
            left_on=issuer_code_field,
            right_on=mapping_code_field,
            how='left',
            suffixes=('', '_实控人')
        )
        
        # 统计映射情况
        if '调整后实际控制人' in result.columns:
            mapped = result['调整后实际控制人'].notna().sum()
            total = len(result)
            
            self.logger.info(
                f"实控人映射完成: {mapped}/{total} "
                f"({mapped/total*100:.1f}% 映射成功)"
            )
            
            # 对于未映射的，使用发行人名称作为实控人
            unmapped_mask = result['调整后实际控制人'].isna()
            
            # 查找发行人名称字段
            issuer_name_field = self._find_field(
                result.columns,
                ['发行人名称', '发行人名称_池', '发行人', '债务主体', '主体名称']
            )
            
            if issuer_name_field and unmapped_mask.sum() > 0:
                result.loc[unmapped_mask, '调整后实际控制人'] = \
                    result.loc[unmapped_mask, issuer_name_field]
                    
                self.logger.info(
                    f"对于未映射的 {unmapped_mask.sum()} 条，使用发行人名称作为实控人"
                )
        
        return result
    
    def handle_beijing_state_capital(
        self,
        data: pd.DataFrame
    ) -> pd.DataFrame:
        """
        处理北京国有资本的特殊情况
        
        根据业务规则，北京国有资本可能需要单独计算
        
        Args:
            data: 包含实控人字段的数据
            
        Returns:
            添加了北京国资标记的数据
        """
        result = data.copy()
        
        if '调整后实际控制人' not in result.columns:
            self.logger.warning("未找到实控人字段，跳过北京国资处理")
            return result
            
        # 标记北京国有资本
        beijing_keywords = ['北京国有资本', '北京市国资']
        
        result['是否北京国资'] = result['调整后实际控制人'].apply(
            lambda x: any(keyword in str(x) for keyword in beijing_keywords)
            if pd.notna(x) else False
        )
        
        count = result['是否北京国资'].sum()
        if count > 0:
            self.logger.info(f"识别北京国有资本: {count} 条")
        
        return result
    
    def _find_field(self, columns: pd.Index, candidates: list) -> Optional[str]:
        """查找第一个匹配的字段名"""
        for candidate in candidates:
            if candidate in columns:
                return candidate
        return None


if __name__ == "__main__":
    # 测试实控人映射器
    from ..utils.logger import setup_logger
    from ..extractors.bond_pool_extractor import BondPoolExtractor
    
    setup_logger(level="DEBUG")
    
    extractor = BondPoolExtractor()
    mapper = ControllerMapper()
    
    try:
        # 提取数据
        controller_mapping = extractor.get_controller_mapping()
        bond_holdings = extractor.extract_bond_holdings()
        
        if not bond_holdings.empty:
            # 测试映射
            result = mapper.map_to_controller(bond_holdings, controller_mapping)
            result = mapper.handle_beijing_state_capital(result)
            
            print(f"\n映射结果: {len(result)} 条")
            print(f"列: {result.columns.tolist()}")
            
            if '调整后实际控制人' in result.columns:
                unique_controllers = result['调整后实际控制人'].nunique()
                print(f"唯一实控人数: {unique_controllers}")
                
    except Exception as e:
        print(f"\n测试失败: {e}")
        import traceback
        traceback.print_exc()
