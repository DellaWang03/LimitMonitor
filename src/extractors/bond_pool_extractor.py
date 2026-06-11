"""
债券池数据提取器
提取阶段0的基础数据：风控部债券池、实控人名单、公司净资产等
"""

import pandas as pd
from pathlib import Path
from typing import Dict, Optional
from .excel_extractor import ExcelExtractor
from ..utils.logger import get_logger
from ..utils.config_loader import get_config


class BondPoolExtractor(ExcelExtractor):
    """债券池数据提取器（阶段0）"""
    
    def __init__(self):
        """初始化提取器"""
        super().__init__()
        self.config = get_config()
        
    def extract_stage0_data(self) -> Dict[str, pd.DataFrame]:
        """
        提取阶段0的所有基础数据
        
        Returns:
            {表名: DataFrame} 字典，包含:
            - 风控部债券池
            - 风控部债券池_主体
            - 调整实控人名单
            - 公司净资产_手工_每日
        """
        self.logger.info("=" * 60)
        self.logger.info("开始提取阶段0基础数据")
        self.logger.info("=" * 60)
        
        result = {}
        
        # 1. 读取风控部债券池文件
        bond_pool_path = self.config.get_data_source_path('bond_pool')
        bond_pool_sheets = self.get_sheet_names(bond_pool_path)
        
        self.logger.info(f"\n读取文件: {bond_pool_path.name}")
        self.logger.info(f"工作表: {bond_pool_sheets}")
        
        # 读取所有工作表
        for sheet_name in bond_pool_sheets:
            try:
                df = self.read_excel(bond_pool_path, sheet_name=sheet_name)
                df = self.clean_dataframe(df)
                result[sheet_name] = df
                
                self.logger.success(
                    f"✓ {sheet_name}: {len(df)} 行 × {len(df.columns)} 列"
                )
                
            except Exception as e:
                self.logger.error(f"✗ {sheet_name}: {e}")
                
        self.logger.info("=" * 60)
        self.logger.info(f"阶段0数据提取完成，共 {len(result)} 个数据表")
        self.logger.info("=" * 60)
        
        return result
    
    def get_bond_pool(self) -> pd.DataFrame:
        """
        获取风控部债券池数据
        
        Returns:
            风控部债券池 DataFrame
            主要字段: 债券代码, 债券简称, 发行人, 主体wind代码 等
        """
        bond_pool_path = self.config.get_data_source_path('bond_pool')
        df = self.read_excel(bond_pool_path, sheet_name='风控部债券池')
        df = self.clean_dataframe(df)
        
        # 数据类型转换（根据实际情况调整）
        # 这里先保持字符串，后续在转换器中处理
        
        return df
    
    def get_bond_pool_issuers(self) -> pd.DataFrame:
        """
        获取风控部债券池_主体数据
        
        Returns:
            主体信息 DataFrame
            主要字段: 发行人wind代码, 主体名称, 主体评级 等
        """
        bond_pool_path = self.config.get_data_source_path('bond_pool')
        df = self.read_excel(bond_pool_path, sheet_name='风控部债券池_主体')
        df = self.clean_dataframe(df)
        
        return df
    
    def get_controller_mapping(self) -> pd.DataFrame:
        """
        获取调整实控人名单
        
        Returns:
            实控人映射 DataFrame
            主要字段: 主体wind代码, 主体名称, 调整后实际控制人 等
        """
        bond_pool_path = self.config.get_data_source_path('bond_pool')
        df = self.read_excel(bond_pool_path, sheet_name='调整实控人名单')
        df = self.clean_dataframe(df)
        
        return df
    
    def get_net_assets(self) -> pd.DataFrame:
        """
        获取公司净资产数据
        
        Returns:
            净资产 DataFrame
            主要字段: 日期, 公司净资产(万) 等
        """
        bond_pool_path = self.config.get_data_source_path('bond_pool')
        df = self.read_excel(bond_pool_path, sheet_name='公司净资产_手工_每日')
        df = self.clean_dataframe(df)
        
        # 转换日期和金额字段
        if '日期' in df.columns:
            df['日期'] = pd.to_datetime(df['日期'], errors='coerce')
            
        if '公司净资产(万)' in df.columns:
            df['公司净资产(万)'] = pd.to_numeric(
                df['公司净资产(万)'], 
                errors='coerce'
            )
        
        return df
    
    def get_latest_net_assets(self) -> float:
        """
        获取最新的公司净资产（万元）
        
        Returns:
            最新净资产值
        """
        df = self.get_net_assets()
        
        if '日期' in df.columns and '公司净资产(万)' in df.columns:
            # 按日期排序，取最新值
            df = df.sort_values('日期', ascending=False)
            latest_value = df.iloc[0]['公司净资产(万)']
            latest_date = df.iloc[0]['日期']
            
            self.logger.info(
                f"最新净资产: {latest_value:,.0f} 万元 ({latest_date.date()})"
            )
            
            return float(latest_value)
        else:
            self.logger.warning("净资产数据字段不完整")
            return 0.0
    
    def extract_bond_holdings(self) -> pd.DataFrame:
        """
        提取债券持仓数据（从其他数据源）
        
        Returns:
            债券持仓 DataFrame
        """
        try:
            holdings_path = self.config.get_data_source_path('bond_holdings')
            df = self.read_excel(holdings_path)
            df = self.clean_dataframe(df)
            
            self.logger.info(
                f"债券持仓数据: {len(df)} 行 × {len(df.columns)} 列"
            )
            
            return df
            
        except Exception as e:
            self.logger.warning(f"读取债券持仓数据失败: {e}")
            return pd.DataFrame()


if __name__ == "__main__":
    # 测试债券池提取器
    from ..utils.logger import setup_logger
    
    # 初始化日志
    setup_logger(level="DEBUG")
    
    # 创建提取器
    extractor = BondPoolExtractor()
    
    # 测试提取阶段0数据
    try:
        stage0_data = extractor.extract_stage0_data()
        
        print("\n" + "=" * 60)
        print("阶段0数据提取结果:")
        print("=" * 60)
        
        for table_name, df in stage0_data.items():
            print(f"\n{table_name}:")
            print(f"  形状: {df.shape}")
            print(f"  列名: {df.columns.tolist()[:5]}...")  # 显示前5列
            
        # 测试获取最新净资产
        print("\n" + "=" * 60)
        latest_assets = extractor.get_latest_net_assets()
        print(f"最新公司净资产: {latest_assets:,.2f} 万元")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n测试失败: {e}")
        import traceback
        traceback.print_exc()
