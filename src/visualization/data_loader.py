"""
数据加载器 - 支持历史数据动态加载
负责加载Stage0/1/2的所有输出数据
"""
from pathlib import Path
import pandas as pd
import streamlit as st
from datetime import datetime, date
from typing import Dict, List, Optional
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DataLoader:
    """数据加载器 - 支持按日期加载历史数据"""
    
    def __init__(self, target_date: Optional[date] = None):
        """
        初始化数据加载器
        
        Args:
            target_date: 要加载的目标日期。如果为None，加载最新数据
        """
        # 使用Path自动处理Windows/Mac路径差异
        self.project_root = Path(__file__).parent.parent.parent
        self.target_date = target_date
        
        # 根据日期决定数据目录
        if target_date is None:
            # 加载最新数据（优先从current目录，兼容旧结构）
            current_stage0 = self.project_root / "data" / "current" / "stage0_output"
            current_stage1 = self.project_root / "data" / "current" / "stage1_output"
            current_stage2 = self.project_root / "data" / "current" / "stage2_output"
            
            # 兼容性处理：如果current不存在，使用旧的直接路径
            if current_stage0.exists() and current_stage1.exists() and current_stage2.exists():
                self.stage0_output_dir = current_stage0
                self.stage1_output_dir = current_stage1
                self.stage2_output_dir = current_stage2
            else:
                # 旧结构兼容
                self.stage0_output_dir = self.project_root / "data" / "stage0_output"
                self.stage1_output_dir = self.project_root / "data" / "stage1_output"
                self.stage2_output_dir = self.project_root / "data" / "stage2_output"
            
            self.data_source = "最新数据"
        else:
            # 加载历史数据（包含完整的Stage0/1/2快照）
            date_str = target_date.strftime('%Y-%m-%d')
            self.stage0_output_dir = self.project_root / "data" / "history" / date_str / "stage0_output"
            self.stage1_output_dir = self.project_root / "data" / "history" / date_str / "stage1_output"
            self.stage2_output_dir = self.project_root / "data" / "history" / date_str / "stage2_output"
            self.data_source = f"历史数据 ({date_str})"
        
        # 验证路径存在
        self._validate_directories()
        logger.info(f"数据加载器初始化: {self.data_source}")
    
    def _validate_directories(self):
        """验证数据目录是否存在"""
        if not self.stage0_output_dir.exists():
            raise FileNotFoundError(f"Stage0输出目录不存在: {self.stage0_output_dir}")
        if not self.stage1_output_dir.exists():
            raise FileNotFoundError(f"Stage1输出目录不存在: {self.stage1_output_dir}")
        if not self.stage2_output_dir.exists():
            raise FileNotFoundError(f"Stage2输出目录不存在: {self.stage2_output_dir}")
        logger.info(f"数据目录验证通过: {self.data_source}")
    
    @staticmethod
    def get_available_dates() -> List[date]:
        """
        获取所有可用的历史数据日期
        
        Returns:
            日期列表，从新到旧排序
        """
        project_root = Path(__file__).parent.parent.parent
        history_dir = project_root / "data" / "history"
        
        if not history_dir.exists():
            return []
        
        dates = []
        for date_folder in history_dir.iterdir():
            if date_folder.is_dir():
                try:
                    # 解析日期文件夹名称（格式：YYYY-MM-DD）
                    date_obj = datetime.strptime(date_folder.name, '%Y-%m-%d').date()
                    # 验证该日期的数据完整性（包含Stage0/1/2）
                    stage0_dir = date_folder / "stage0_output"
                    stage1_dir = date_folder / "stage1_output"
                    stage2_dir = date_folder / "stage2_output"
                    if stage0_dir.exists() and stage1_dir.exists() and stage2_dir.exists():
                        dates.append(date_obj)
                except ValueError:
                    logger.warning(f"忽略无效日期文件夹: {date_folder.name}")
        
        # 从新到旧排序
        dates.sort(reverse=True)
        return dates
    
    # ==================== Stage1 数据加载 ====================
    
    @st.cache_data(ttl=3600)
    def load_stage1_credit_1_1(_self) -> pd.DataFrame:
        """加载阶段1-债券持仓明细表_信用债1_1"""
        file_path = _self.stage1_output_dir / "限额明细_债券持仓明细表_信用债1_1.xlsx"
        logger.info(f"加载文件: {file_path.name}")
        df = pd.read_excel(file_path)
        if '日期' in df.columns:
            df['日期'] = pd.to_datetime(df['日期'], errors='coerce')
        return df
    
    @st.cache_data(ttl=3600)
    def load_stage1_credit_1_2(_self) -> pd.DataFrame:
        """加载阶段1-债券持仓明细表_信用债1_2"""
        file_path = _self.stage1_output_dir / "限额明细_债券持仓明细表_信用债1_2.xlsx"
        logger.info(f"加载文件: {file_path.name}")
        df = pd.read_excel(file_path)
        if '日期' in df.columns:
            df['日期'] = pd.to_datetime(df['日期'], errors='coerce')
        return df
    
    @st.cache_data(ttl=3600)
    def load_stage1_guarantee(_self) -> pd.DataFrame:
        """加载阶段1-单一担保人明细"""
        file_path = _self.stage1_output_dir / "限额明细_单一担保人.xlsx"
        logger.info(f"加载文件: {file_path.name}")
        df = pd.read_excel(file_path)
        if '日期' in df.columns:
            df['日期'] = pd.to_datetime(df['日期'], errors='coerce')
        return df
    
    @st.cache_data(ttl=3600)
    def load_stage1_merged(_self) -> pd.DataFrame:
        """加载阶段1-债券持仓明细表_信用债_合并风险限额相关"""
        file_path = _self.stage1_output_dir / "债券持仓明细表_信用债_合并风险限额相关.xlsx"
        logger.info(f"加载文件: {file_path.name}")
        df = pd.read_excel(file_path)
        if '日期' in df.columns:
            df['日期'] = pd.to_datetime(df['日期'], errors='coerce')
        return df
    
    # ==================== Stage2 数据加载 ====================
    
    @st.cache_data(ttl=3600)
    def load_stage2_credit_2(_self) -> pd.DataFrame:
        """加载阶段2-债券持仓明细表_信用债2（核心表）"""
        file_path = _self.stage2_output_dir / "限额明细_债券持仓明细表_信用债2.xlsx"
        logger.info(f"加载文件: {file_path.name}")
        df = pd.read_excel(file_path)
        if '日期' in df.columns:
            df['日期'] = pd.to_datetime(df['日期'], errors='coerce')
        return df
    
    @st.cache_data(ttl=3600)
    def load_stage2_high_risk_industry(_self) -> pd.DataFrame:
        """加载阶段2-高风险行业汇总"""
        file_path = _self.stage2_output_dir / "限额明细_高风险行业.xlsx"
        logger.info(f"加载文件: {file_path.name}")
        df = pd.read_excel(file_path)
        if '日期' in df.columns:
            df['日期'] = pd.to_datetime(df['日期'], errors='coerce')
        return df
    
    @st.cache_data(ttl=3600)
    def load_stage2_high_risk_province(_self) -> pd.DataFrame:
        """加载阶段2-高风险省份汇总"""
        file_path = _self.stage2_output_dir / "限额明细_高风险省份.xlsx"
        logger.info(f"加载文件: {file_path.name}")
        df = pd.read_excel(file_path)
        if '日期' in df.columns:
            df['日期'] = pd.to_datetime(df['日期'], errors='coerce')
        return df
    
    @st.cache_data(ttl=3600)
    def load_stage2_high_risk_province_detail(_self) -> pd.DataFrame:
        """加载阶段2-高风险省份明细（按省份汇总，包含做市业务）"""
        file_path = _self.stage2_output_dir / "高风险省份总持仓_2.xlsx"
        logger.info(f"加载文件: {file_path.name}")
        df = pd.read_excel(file_path)
        if '日期' in df.columns:
            df['日期'] = pd.to_datetime(df['日期'], errors='coerce')
        return df
    
    @st.cache_data(ttl=3600)
    def load_stage2_regional(_self) -> pd.DataFrame:
        """加载阶段2-地域集中度限额(含城投)"""
        file_path = _self.stage2_output_dir / "限额明细_地域集中度限额(含城投).xlsx"
        logger.info(f"加载文件: {file_path.name}")
        df = pd.read_excel(file_path)
        if '日期' in df.columns:
            df['日期'] = pd.to_datetime(df['日期'], errors='coerce')
        return df
    
    @st.cache_data(ttl=3600)
    def load_stage2_high_yield(_self) -> pd.DataFrame:
        """加载阶段2-高收益债券明细"""
        file_path = _self.stage2_output_dir / "限额明细_高收益.xlsx"
        logger.info(f"加载文件: {file_path.name}")
        df = pd.read_excel(file_path)
        if '日期' in df.columns:
            df['日期'] = pd.to_datetime(df['日期'], errors='coerce')
        return df
    
    @st.cache_data(ttl=3600)
    def load_stage2_high_yield_capital(_self) -> pd.DataFrame:
        """加载阶段2-高收益投资本金规模"""
        file_path = _self.stage2_output_dir / "限额明细_高收益_投资本金规模.xlsx"
        logger.info(f"加载文件: {file_path.name}")
        df = pd.read_excel(file_path)
        if '日期' in df.columns:
            df['日期'] = pd.to_datetime(df['日期'], errors='coerce')
        return df
    
    # ==================== 辅助方法 ====================
    
    def get_latest_date(self) -> datetime:
        """获取最新数据日期"""
        try:
            df = self.load_stage1_credit_1_1()
            return df['日期'].max()
        except Exception as e:
            logger.error(f"获取最新日期失败: {e}")
            return datetime.now()
    
    def get_available_accounts(self) -> List[str]:
        """获取所有可用账户列表（用于筛选器）"""
        try:
            df = self.load_stage1_credit_1_1()
            accounts = sorted(df['内部证券账户名称'].unique().tolist())
            return ['全部'] + accounts
        except Exception as e:
            logger.error(f"获取账户列表失败: {e}")
            return ['全部']
    
    def get_available_bond_types(self) -> List[str]:
        """获取所有债券类型列表（用于筛选器）"""
        try:
            df = self.load_stage1_credit_1_1()
            bond_types = sorted(df['债券分类2'].unique().tolist())
            return ['全部'] + bond_types
        except Exception as e:
            logger.error(f"获取债券类型失败: {e}")
            return ['全部']
    
    def get_summary_metrics(self) -> Dict[str, any]:
        """获取关键指标汇总"""
        try:
            df = self.load_stage2_credit_2()
            
            total_position = df['库存数量(万)_PR'].sum()
            overlimit_count = len(df[df['是否超限'] == '是'])
            total_count = len(df)
            
            return {
                'total_position': total_position,
                'total_position_formatted': f"{total_position:,.2f}",
                'overlimit_count': overlimit_count,
                'total_count': total_count,
                'overlimit_ratio': f"{overlimit_count/total_count*100:.1f}%" if total_count > 0 else "0%",
                'latest_date': self.get_latest_date().strftime("%Y年%m月%d日")
            }
        except Exception as e:
            logger.error(f"获取汇总指标失败: {e}")
            return {
                'total_position': 0,
                'total_position_formatted': "0",
                'overlimit_count': 0,
                'total_count': 0,
                'overlimit_ratio': "0%",
                'latest_date': datetime.now().strftime("%Y年%m月%d日")
            }
