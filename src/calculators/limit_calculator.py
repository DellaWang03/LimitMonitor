"""
限额计算器
实现7大限额维度的计算逻辑
"""

import pandas as pd
from typing import Dict, Tuple
from ..utils.logger import get_logger
from ..utils.config_loader import get_config


class LimitCalculator:
    """限额计算器"""
    
    def __init__(self, net_assets: float = None):
        """
        初始化计算器
        
        Args:
            net_assets: 公司净资产（万元），用于计算集中度
        """
        self.logger = get_logger()
        self.config = get_config()
        self.net_assets = net_assets
        
        # 加载限额配置参数
        self.limits = self.config.load_limits()
        
        # 提取关键参数（提供默认值以确保向后兼容）
        self.guarantor_limit = self.limits.get('single_guarantor', {}).get('scale_limit', 40000)
        self.regional_ratio = self.limits.get('regional_concentration', {}).get('total_limit_ratio', 0.20)
        self.chengtou_ratio = self.limits.get('regional_concentration', {}).get('chengtou_limit_ratio', 0.10)
        self.high_risk_industry_ratio = self.limits.get('high_risk_industry', {}).get('total_limit_ratio', 0.10)
        self.high_risk_province_ratio = self.limits.get('high_risk_province', {}).get('total_limit_ratio', 0.10)
        
        self.logger.info(f"加载限额配置: 担保人={self.guarantor_limit}万, 地域={self.regional_ratio*100}%, 城投={self.chengtou_ratio*100}%, 高风险行业={self.high_risk_industry_ratio*100}%, 高风险省份={self.high_risk_province_ratio*100}%")
        
    def calculate_single_bond_limits(
        self,
        credit_bonds: pd.DataFrame
    ) -> pd.DataFrame:
        """
        计算单一债券持仓和限额
        
        Args:
            credit_bonds: 信用债持仓数据
            
        Returns:
            单一债券限额明细
            包含字段: 主证券代码, 单一债券持仓, 单一债券限额, 是否超限 等
        """
        self.logger.info("=" * 60)
        self.logger.info("计算单一债券限额")
        self.logger.info("=" * 60)
        
        # 按债券代码汇总 - 使用实际字段名
        bond_code_field = self._find_field(
            credit_bonds.columns,
            ['代码', '主证券代码', '债券代码']
        )
        
        if not bond_code_field:
            self.logger.error("未找到债券代码字段")
            self.logger.error(f"可用字段: {credit_bonds.columns.tolist()[:10]}...")
            return pd.DataFrame()
        
        # 查找金额字段
        amount_field = self._find_field(
            credit_bonds.columns,
            ['市值(元)', '持仓面额(元)', '债券余额(亿)']
        )
        
        if not amount_field:
            self.logger.error("未找到金额字段")
            return pd.DataFrame()
            
        # 先转换金额字段为数值类型（如果是字符串）
        credit_bonds_copy = credit_bonds.copy()
        credit_bonds_copy[amount_field] = pd.to_numeric(
            credit_bonds_copy[amount_field], 
            errors='coerce'
        )
        
        # 汇总持仓
        agg_dict = {amount_field: 'sum'}
        
        # 添加债券名称
        name_field = self._find_field(credit_bonds.columns, ['简称', '债券名称', '证券名称'])
        if name_field:
            agg_dict[name_field] = 'first'
            
        result = credit_bonds_copy.groupby(bond_code_field).agg(agg_dict).reset_index()
        
        # 转换金额单位到万元
        if amount_field == '市值(元)' or amount_field == '持仓面额(元)':
            result[amount_field] = result[amount_field] / 10000  # 元 → 万元
        elif amount_field == '债券余额(亿)':
            result[amount_field] = result[amount_field] * 10000  # 亿 → 万元
        
        # 重命名
        rename_dict = {
            bond_code_field: '债券代码',
            amount_field: '单一债券持仓(万)'
        }
        if name_field:
            rename_dict[name_field] = '债券简称'
        result = result.rename(columns=rename_dict)
        
        # TODO: 从配置或数据库中获取单一债券限额
        # 这里先使用占位值
        result['单一债券规模限额(万)'] = 50000  # 示例值
        
        # 计算是否超限
        result['单一债券是否超限'] = result['单一债券持仓(万)'] > result['单一债券规模限额(万)']
        
        # 计算超限金额
        result['超限金额(万)'] = (
            result['单一债券持仓(万)'] - result['单一债券规模限额(万)']
        ).clip(lower=0)
        
        # 计算使用率
        result['限额使用率(%)'] = (
            result['单一债券持仓(万)'] / result['单一债券规模限额(万)'] * 100
        ).round(2)
        
        self.logger.info(f"单一债券总数: {len(result)}")
        self.logger.info(f"超限债券数: {result['单一债券是否超限'].sum()}")
        
        return result
    
    def calculate_single_issuer_limits(
        self,
        credit_bonds: pd.DataFrame
    ) -> pd.DataFrame:
        """
        计算单一主体持仓和限额
        
        Args:
            credit_bonds: 信用债持仓数据（已关联主体信息）
            
        Returns:
            单一主体限额明细
        """
        self.logger.info("=" * 60)
        self.logger.info("计算单一主体限额")
        self.logger.info("=" * 60)
        
        # 按主体代码汇总 - 使用实际字段名
        issuer_code_field = self._find_field(
            credit_bonds.columns,
            ['主体wind代码', '债务主体wind代码', '发行人wind代码']
        )
        
        if not issuer_code_field:
            self.logger.error("未找到主体代码字段")
            self.logger.error(f"可用字段: {credit_bonds.columns.tolist()[:10]}...")
            return pd.DataFrame()
        
        # 查找金额字段
        amount_field = self._find_field(
            credit_bonds.columns,
            ['市值(元)', '持仓面额(元)', '债券余额(亿)']
        )
        
        if not amount_field:
            self.logger.error("未找到金额字段")
            return pd.DataFrame()
        
        # 先转换金额字段为数值类型
        credit_bonds_copy = credit_bonds.copy()
        credit_bonds_copy[amount_field] = pd.to_numeric(
            credit_bonds_copy[amount_field], 
            errors='coerce'
        )
            
        # 汇总
        agg_dict = {amount_field: 'sum'}
        
        # 添加主体名称
        name_field = self._find_field(
            credit_bonds.columns, 
            ['发行人名称', '发行人名称_池', '发行人', '债务主体', '主体名称']
        )
        if name_field:
            agg_dict[name_field] = 'first'
            
        result = credit_bonds_copy.groupby(issuer_code_field).agg(agg_dict).reset_index()
        
        # 转换金额单位到万元
        if amount_field == '市值(元)' or amount_field == '持仓面额(元)':
            result[amount_field] = result[amount_field] / 10000
        elif amount_field == '债券余额(亿)':
            result[amount_field] = result[amount_field] * 10000
        
        # 重命名
        rename_dict = {
            issuer_code_field: '主体wind代码',
            amount_field: '单一主体持仓(万)'
        }
        if name_field:
            rename_dict[name_field] = '主体名称'
        result = result.rename(columns=rename_dict)
        
        # TODO: 从配置获取限额
        result['单一主体规模限额(万)'] = 100000  # 示例值
        
        # 计算超限
        result['单一主体是否超限'] = result['单一主体持仓(万)'] > result['单一主体规模限额(万)']
        
        # 计算超限金额
        result['超限金额(万)'] = (
            result['单一主体持仓(万)'] - result['单一主体规模限额(万)']
        ).clip(lower=0)
        
        # 计算使用率
        result['限额使用率(%)'] = (
            result['单一主体持仓(万)'] / result['单一主体规模限额(万)'] * 100
        ).round(2)
        
        self.logger.info(f"主体总数: {len(result)}")
        self.logger.info(f"超限主体数: {result['单一主体是否超限'].sum()}")
        
        return result
    
    def calculate_single_controller_limits(
        self,
        credit_bonds: pd.DataFrame
    ) -> pd.DataFrame:
        """
        计算单一实控人持仓和限额
        
        Args:
            credit_bonds: 信用债持仓数据（已穿透到实控人）
            
        Returns:
            单一实控人限额明细
        """
        self.logger.info("=" * 60)
        self.logger.info("计算单一实控人限额")
        self.logger.info("=" * 60)
        
        if '调整后实际控制人' not in credit_bonds.columns:
            self.logger.error("未找到实控人字段，请先进行实控人映射")
            self.logger.error(f"可用字段: {credit_bonds.columns.tolist()[:10]}...")
            return pd.DataFrame()
        
        # 查找金额字段
        amount_field = self._find_field(
            credit_bonds.columns,
            ['市值(元)', '持仓面额(元)', '债券余额(亿)']
        )
        
        if not amount_field:
            self.logger.error("未找到金额字段")
            return pd.DataFrame()
        
        # 先转换金额字段为数值类型
        credit_bonds_copy = credit_bonds.copy()
        credit_bonds_copy[amount_field] = pd.to_numeric(
            credit_bonds_copy[amount_field], 
            errors='coerce'
        )
            
        # 按实控人汇总
        result = credit_bonds_copy.groupby('调整后实际控制人').agg({
            amount_field: 'sum'
        }).reset_index()
        
        # 转换金额单位到万元
        if amount_field == '市值(元)' or amount_field == '持仓面额(元)':
            result[amount_field] = result[amount_field] / 10000
        elif amount_field == '债券余额(亿)':
            result[amount_field] = result[amount_field] * 10000
        
        # 重命名
        result = result.rename(columns={
            amount_field: '单一实控人持仓(万)'
        })
        
        # TODO: 从配置获取限额
        result['单一实控人规模限额(万)'] = 150000  # 示例值
        
        # 计算超限
        result['单一实控人是否超限'] = result['单一实控人持仓(万)'] > result['单一实控人规模限额(万)']
        
        # 计算超限金额
        result['超限金额(万)'] = (
            result['单一实控人持仓(万)'] - result['单一实控人规模限额(万)']
        ).clip(lower=0)
        
        # 计算使用率
        result['限额使用率(%)'] = (
            result['单一实控人持仓(万)'] / result['单一实控人规模限额(万)'] * 100
        ).round(2)
        
        # 按持仓金额降序排序
        result = result.sort_values('单一实控人持仓(万)', ascending=False)
        
        self.logger.info(f"实控人总数: {len(result)}")
        self.logger.info(f"超限实控人数: {result['单一实控人是否超限'].sum()}")
        
        return result
    
    def calculate_regional_concentration(
        self,
        credit_bonds: pd.DataFrame
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        计算地域集中度限额
        
        Args:
            credit_bonds: 信用债持仓数据（需包含省份字段）
            
        Returns:
            (单一地域总持仓明细, 单一地域城投持仓明细)
        """
        self.logger.info("=" * 60)
        self.logger.info("计算地域集中度限额")
        self.logger.info("=" * 60)
        
        if '省份' not in credit_bonds.columns:
            self.logger.warning("未找到省份字段")
            return pd.DataFrame(), pd.DataFrame()
            
        # 1. 单一地域总持仓
        total_by_region = credit_bonds.groupby('省份').agg({
            '债券余额(亿)': 'sum'
        }).reset_index()
        
        total_by_region.columns = ['省份', '单一地域总持仓(万)']
        
        # 计算限额（公司净资产 × 地域集中度比例，从YAML读取）
        if self.net_assets:
            total_by_region['单一地域总持仓限额(万)'] = self.net_assets * self.regional_ratio
            total_by_region['集中度(%)'] = (
                total_by_region['单一地域总持仓(万)'] / self.net_assets * 100
            )
            total_by_region['是否超限'] = total_by_region['集中度(%)'] > (self.regional_ratio * 100)
            
        self.logger.info(f"涉及省份数: {len(total_by_region)}")
        
        # 2. 单一地域城投持仓（需要识别城投债）
        # TODO: 添加城投债识别逻辑
        chengtou_by_region = pd.DataFrame()
        
        return total_by_region, chengtou_by_region
    
    def calculate_high_risk_industry(
        self,
        credit_bonds: pd.DataFrame,
        high_risk_industries: list = None
    ) -> pd.DataFrame:
        """
        计算高风险行业限额
        
        Args:
            credit_bonds: 信用债持仓数据（需包含行业字段）
            high_risk_industries: 高风险行业列表
            
        Returns:
            高风险行业限额明细
        """
        self.logger.info("=" * 60)
        self.logger.info("计算高风险行业限额")
        self.logger.info("=" * 60)
        
        # TODO: 实现高风险行业计算
        return pd.DataFrame()
    
    def _find_field(self, columns: pd.Index, candidates: list) -> str:
        """查找第一个匹配的字段名"""
        for candidate in candidates:
            if candidate in columns:
                return candidate
        return None


if __name__ == "__main__":
    # 测试计算器
    from ..utils.logger import setup_logger
    from ..extractors.bond_pool_extractor import BondPoolExtractor
    from ..transformers.bond_transformer import BondTransformer
    from ..transformers.controller_mapper import ControllerMapper
    
    setup_logger(level="DEBUG")
    
    # 准备数据
    extractor = BondPoolExtractor()
    transformer = BondTransformer()
    controller_mapper = ControllerMapper()
    
    try:
        # 获取净资产
        net_assets = extractor.get_latest_net_assets()
        
        # 创建计算器
        calculator = LimitCalculator(net_assets=net_assets)
        
        # 模拟数据测试
        test_data = pd.DataFrame({
            '主证券代码': ['112590776', '112590776', '112590777'],
            '债券余额(亿)': [10000, 5000, 20000],
            '债务主体wind代码': ['1000001', '1000001', '1000002'],
            '债务主体': ['测试主体A', '测试主体A', '测试主体B'],
            '调整后实际控制人': ['实控人A', '实控人A', '实控人B'],
            '省份': ['北京', '北京', '上海']
        })
        
        # 测试计算
        bond_limits = calculator.calculate_single_bond_limits(test_data)
        print("\n单一债券限额:")
        print(bond_limits)
        
        issuer_limits = calculator.calculate_single_issuer_limits(test_data)
        print("\n单一主体限额:")
        print(issuer_limits)
        
        controller_limits = calculator.calculate_single_controller_limits(test_data)
        print("\n单一实控人限额:")
        print(controller_limits)
        
    except Exception as e:
        print(f"\n测试失败: {e}")
        import traceback
        traceback.print_exc()
