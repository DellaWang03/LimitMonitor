"""
Excel 数据提取器
用于从 Excel 文件中读取数据
"""

import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional, Union
import openpyxl
from ..utils.logger import get_logger
from ..utils.config_loader import get_config


class ExcelExtractor:
    """Excel 数据提取器基类"""
    
    def __init__(self):
        """初始化提取器"""
        self.logger = get_logger()
        self.config = get_config()
        
    def read_excel(
        self,
        file_path: Union[str, Path],
        sheet_name: Optional[Union[str, int, List]] = 0,
        **kwargs
    ) -> Union[pd.DataFrame, Dict[str, pd.DataFrame]]:
        """
        读取 Excel 文件
        
        Args:
            file_path: 文件路径
            sheet_name: 工作表名称或索引，None 表示读取所有工作表
            **kwargs: 传递给 pandas.read_excel 的其他参数
            
        Returns:
            DataFrame 或 字典 (sheet_name -> DataFrame)
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
            
        self.logger.info(f"读取 Excel 文件: {file_path.name}")
        
        try:
            # 设置默认参数
            default_kwargs = {
                'engine': 'openpyxl',
                'dtype': str  # 先以字符串读取，避免类型推断错误
            }
            default_kwargs.update(kwargs)
            
            # 读取数据
            df = pd.read_excel(file_path, sheet_name=sheet_name, **default_kwargs)
            
            if isinstance(df, dict):
                self.logger.info(f"读取了 {len(df)} 个工作表")
                for sheet, data in df.items():
                    self.logger.debug(f"  - {sheet}: {len(data)} 行 × {len(data.columns)} 列")
            else:
                self.logger.info(f"读取数据: {len(df)} 行 × {len(df.columns)} 列")
                
            return df
            
        except Exception as e:
            self.logger.error(f"读取 Excel 文件失败: {e}")
            raise
            
    def get_sheet_names(self, file_path: Union[str, Path]) -> List[str]:
        """
        获取 Excel 文件中的所有工作表名称
        
        Args:
            file_path: 文件路径
            
        Returns:
            工作表名称列表
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
            
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        sheet_names = wb.sheetnames
        wb.close()
        
        return sheet_names
    
    def read_multiple_sheets(
        self,
        file_path: Union[str, Path],
        sheet_names: List[str],
        **kwargs
    ) -> Dict[str, pd.DataFrame]:
        """
        读取多个指定的工作表
        
        Args:
            file_path: 文件路径
            sheet_names: 工作表名称列表
            **kwargs: 传递给 read_excel 的其他参数
            
        Returns:
            {sheet_name: DataFrame} 字典
        """
        result = {}
        
        for sheet_name in sheet_names:
            try:
                df = self.read_excel(file_path, sheet_name=sheet_name, **kwargs)
                result[sheet_name] = df
            except Exception as e:
                self.logger.warning(f"读取工作表 {sheet_name} 失败: {e}")
                
        return result
    
    def clean_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        清理 DataFrame
        - 删除全空行/列
        - 去除列名首尾空格
        - 处理常见的数据问题
        
        Args:
            df: 原始 DataFrame
            
        Returns:
            清理后的 DataFrame
        """
        # 复制数据避免修改原始数据
        df = df.copy()
        
        # 删除全空行
        df = df.dropna(how='all')
        
        # 删除全空列
        df = df.dropna(axis=1, how='all')
        
        # 清理列名
        df.columns = df.columns.str.strip()
        
        # 重置索引
        df = df.reset_index(drop=True)
        
        return df
    
    def convert_datatypes(
        self,
        df: pd.DataFrame,
        column_types: Dict[str, str]
    ) -> pd.DataFrame:
        """
        转换列的数据类型
        
        Args:
            df: DataFrame
            column_types: {列名: 数据类型} 字典
                数据类型可以是: 'int', 'float', 'str', 'datetime', 'bool'
                
        Returns:
            转换后的 DataFrame
        """
        df = df.copy()
        
        for col, dtype in column_types.items():
            if col not in df.columns:
                self.logger.warning(f"列 {col} 不存在，跳过类型转换")
                continue
                
            try:
                if dtype == 'int':
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
                elif dtype == 'float':
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                elif dtype == 'str':
                    df[col] = df[col].astype(str)
                elif dtype == 'datetime':
                    df[col] = pd.to_datetime(df[col], errors='coerce')
                elif dtype == 'bool':
                    df[col] = df[col].astype(bool)
                else:
                    self.logger.warning(f"未知的数据类型: {dtype}")
                    
            except Exception as e:
                self.logger.error(f"转换列 {col} 到 {dtype} 失败: {e}")
                
        return df


if __name__ == "__main__":
    # 测试 Excel 提取器
    extractor = ExcelExtractor()
    
    # 测试读取文件
    try:
        config = get_config()
        bond_pool_path = config.get_data_source_path('bond_pool')
        
        # 获取工作表名称
        sheets = extractor.get_sheet_names(bond_pool_path)
        print(f"\n工作表: {sheets}")
        
        # 读取第一个工作表
        df = extractor.read_excel(bond_pool_path, sheet_name=sheets[0])
        df = extractor.clean_dataframe(df)
        
        print(f"\n数据预览:")
        print(df.head())
        print(f"\n形状: {df.shape}")
        print(f"列名: {df.columns.tolist()}")
        
    except Exception as e:
        print(f"测试失败: {e}")
