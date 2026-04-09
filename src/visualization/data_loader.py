"""
数据加载器 - 支持历史数据动态加载
负责加载Stage0/1/2的所有输出数据
"""
from pathlib import Path
import json
import pandas as pd
import streamlit as st
from datetime import datetime, date
from typing import Any, Dict, List, Optional
import logging
from functools import lru_cache
from src.utils.config_loader import ConfigLoader

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
        self.archive_root: Optional[Path] = None
        
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
            self.archive_root = self.project_root / "data" / "history" / date_str
            self.stage0_output_dir = self.archive_root / "stage0_output"
            self.stage1_output_dir = self.archive_root / "stage1_output"
            self.stage2_output_dir = self.archive_root / "stage2_output"
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
    
    @staticmethod
    def get_data_date_for_archive(archive_date: date) -> Optional[str]:
        """
        读取某次历史归档中记录的数据日期（data_date.txt），用于下拉展示「归档日 (数据日期: xxx)」。
        旧归档无此文件时返回 None。
        """
        project_root = Path(__file__).parent.parent.parent
        meta_file = (
            project_root
            / "data"
            / "history"
            / archive_date.strftime("%Y-%m-%d")
            / "data_date.txt"
        )
        if not meta_file.exists():
            return None
        try:
            return meta_file.read_text(encoding="utf-8").strip() or None
        except Exception:
            return None
    
    # ==================== 可视化层本地缓存（避免 Streamlit 缓存提示框） ====================
    # 使用文件路径 + mtime 作为缓存键，文件变更后自动失效。
    @staticmethod
    @lru_cache(maxsize=128)
    def _load_excel_cached(file_path_str: str, mtime_ns: int) -> pd.DataFrame:
        df = pd.read_excel(file_path_str)
        if '日期' in df.columns:
            df['日期'] = pd.to_datetime(df['日期'], errors='coerce')
        return df

    @staticmethod
    def _load_excel_with_date(file_path_str: str) -> pd.DataFrame:
        file_path = Path(file_path_str)
        mtime_ns = file_path.stat().st_mtime_ns if file_path.exists() else 0
        return DataLoader._load_excel_cached(file_path_str, mtime_ns).copy()

    @staticmethod
    @lru_cache(maxsize=64)
    def _load_json_cached(file_path_str: str, mtime_ns: int) -> Dict[str, Any]:
        with open(file_path_str, 'r', encoding='utf-8') as f:
            return json.load(f)

    @staticmethod
    def _load_json_file(file_path_str: str) -> Dict[str, Any]:
        file_path = Path(file_path_str)
        mtime_ns = file_path.stat().st_mtime_ns if file_path.exists() else 0
        return dict(DataLoader._load_json_cached(file_path_str, mtime_ns))

    @staticmethod
    def clear_local_caches():
        """清理可视化层本地缓存。"""
        DataLoader._load_excel_cached.cache_clear()
        DataLoader._load_json_cached.cache_clear()

    def _load_history_snapshot(self, file_name: str) -> Optional[Dict[str, Any]]:
        """历史模式下读取归档根目录的快照文件。"""
        if self.archive_root is None:
            return None
        file_path = self.archive_root / file_name
        if not file_path.exists():
            return None
        try:
            return DataLoader._load_json_file(str(file_path))
        except Exception as e:
            logger.warning(f"读取历史快照失败 {file_path.name}: {e}")
            return None

    @staticmethod
    def _clean_code_like_value(value: Any) -> Optional[str]:
        """清洗代码/ISIN类字段，统一空值。"""
        if pd.isna(value):
            return None
        text = str(value).strip()
        if text in {"", "nan", "None", "<NA>"}:
            return None
        return text

    def _attach_display_code(self, df: pd.DataFrame) -> pd.DataFrame:
        """为展示数据补充 ISIN 优先、资产代码兜底的代码列。"""
        if '资产代码' not in df.columns and '证券代码' in df.columns:
            df = df.copy()
            df['资产代码'] = df['证券代码']

        if '资产代码' not in df.columns:
            return df

        result = df.copy()
        result['资产代码'] = result['资产代码'].apply(self._clean_code_like_value)
        if 'ISIN码' in result.columns:
            result['ISIN码'] = result['ISIN码'].apply(self._clean_code_like_value)

        if 'ISIN码' in result.columns:
            result['代码'] = result['ISIN码'].combine_first(result['资产代码'])
        else:
            result['代码'] = result['资产代码']

        return result
    
    # ==================== Stage1 数据加载 ====================
    
    def load_stage1_credit_1_1(self) -> pd.DataFrame:
        """加载阶段1-债券持仓明细表_信用债1_1"""
        file_path = self.stage1_output_dir / "限额明细_债券持仓明细表_信用债1_1.xlsx"
        logger.info(f"加载文件: {file_path.name}")
        df = DataLoader._load_excel_with_date(str(file_path))
        return self._attach_display_code(df)
    
    def load_stage1_credit_1_2(self) -> pd.DataFrame:
        """加载阶段1-债券持仓明细表_信用债1_2"""
        file_path = self.stage1_output_dir / "限额明细_债券持仓明细表_信用债1_2.xlsx"
        logger.info(f"加载文件: {file_path.name}")
        df = DataLoader._load_excel_with_date(str(file_path))
        return self._attach_display_code(df)

    def load_stage1_single_bond(self) -> pd.DataFrame:
        """加载阶段1-单一债券明细"""
        file_path = self.stage1_output_dir / "限额明细_单一债券.xlsx"
        logger.info(f"加载文件: {file_path.name}")
        df = DataLoader._load_excel_with_date(str(file_path))
        return self._attach_display_code(df)

    def load_stage1_full_regulatory_concentration(self) -> pd.DataFrame:
        """加载阶段1-全量债券监管集中度明细"""
        file_path = self.stage1_output_dir / "限额明细_全量债券监管集中度.xlsx"
        logger.info(f"加载文件: {file_path.name}")
        df = DataLoader._load_excel_with_date(str(file_path))
        return self._attach_display_code(df)
    
    def load_stage1_guarantee(self) -> pd.DataFrame:
        """加载阶段1-单一担保人明细"""
        file_path = self.stage1_output_dir / "限额明细_单一担保人.xlsx"
        logger.info(f"加载文件: {file_path.name}")
        return DataLoader._load_excel_with_date(str(file_path))
    
    def load_stage1_merged(self) -> pd.DataFrame:
        """加载阶段1-债券持仓明细表_信用债_合并风险限额相关"""
        file_path = self.stage1_output_dir / "债券持仓明细表_信用债_合并风险限额相关.xlsx"
        logger.info(f"加载文件: {file_path.name}")
        return DataLoader._load_excel_with_date(str(file_path))
    
    # ==================== Stage2 数据加载 ====================
    
    def load_stage2_credit_2(self) -> pd.DataFrame:
        """加载阶段2-债券持仓明细表_信用债2（核心表）"""
        file_path = self.stage2_output_dir / "限额明细_债券持仓明细表_信用债2.xlsx"
        logger.info(f"加载文件: {file_path.name}")
        df = DataLoader._load_excel_with_date(str(file_path))
        return self._attach_display_code(df)
    
    def load_stage2_high_risk_industry(self) -> pd.DataFrame:
        """加载阶段2-高风险行业汇总"""
        file_path = self.stage2_output_dir / "限额明细_高风险行业.xlsx"
        logger.info(f"加载文件: {file_path.name}")
        return DataLoader._load_excel_with_date(str(file_path))
    
    def load_stage2_high_risk_province(self) -> pd.DataFrame:
        """加载阶段2-高风险省份汇总"""
        file_path = self.stage2_output_dir / "限额明细_高风险省份.xlsx"
        logger.info(f"加载文件: {file_path.name}")
        return DataLoader._load_excel_with_date(str(file_path))
    
    def load_stage2_high_risk_province_detail(self) -> pd.DataFrame:
        """加载阶段2-高风险省份明细（按省份汇总，包含做市业务）"""
        file_path = self.stage2_output_dir / "高风险省份总持仓_2.xlsx"
        logger.info(f"加载文件: {file_path.name}")
        return DataLoader._load_excel_with_date(str(file_path))
    
    def load_stage2_regional(self) -> pd.DataFrame:
        """加载阶段2-地域集中度限额(含城投)"""
        file_path = self.stage2_output_dir / "限额明细_地域集中度限额(含城投).xlsx"
        logger.info(f"加载文件: {file_path.name}")
        return DataLoader._load_excel_with_date(str(file_path))
    
    def load_stage2_high_yield(self) -> pd.DataFrame:
        """加载阶段2-高收益债券明细"""
        file_path = self.stage2_output_dir / "限额明细_高收益.xlsx"
        logger.info(f"加载文件: {file_path.name}")
        df = DataLoader._load_excel_with_date(str(file_path))
        return self._attach_display_code(df)
    
    def load_stage2_high_yield_capital(self) -> pd.DataFrame:
        """加载阶段2-高收益投资本金规模"""
        file_path = self.stage2_output_dir / "限额明细_高收益_投资本金规模.xlsx"
        logger.info(f"加载文件: {file_path.name}")
        return DataLoader._load_excel_with_date(str(file_path))

    def load_high_yield_annual_limit(self) -> int:
        """
        从「限额监控_阶段0_指标设置.xlsx / 高收益限额」读取年度高收益债券投资本金规模限额（万元）。
        若文件不可达则返回 100000（10 亿）兜底。
        """
        FALLBACK = 100000
        snapshot = self._load_history_snapshot("high_yield_limit_snapshot.json")
        if snapshot is not None:
            try:
                return int(snapshot.get("annual_limit_wan", FALLBACK))
            except (TypeError, ValueError):
                logger.warning("历史高收益限额快照格式异常，改用实时配置兜底")

        try:
            config = ConfigLoader()
            file_path = config.get_data_file_path("限额监控_阶段0_指标设置.xlsx")
            df = pd.read_excel(str(file_path), sheet_name="高收益限额")
            row = df[df['指标'].astype(str).str.strip() == '年度高收益债券投资本金规模']
            if row.empty:
                logger.warning("高收益限额：未找到「年度高收益债券投资本金规模」行，使用兜底值")
                return FALLBACK
            return int(row.iloc[0]['限额(万)'])
        except Exception as e:
            logger.warning(f"读取高收益限额配置失败，使用兜底值 {FALLBACK} 万元：{e}")
            return FALLBACK

    def load_alert_thresholds(self) -> Dict[str, float]:
        """
        加载页面展示用告警阈值。
        历史模式优先读取归档快照，避免颜色/文案口径被当前 settings.yaml 污染。
        """
        snapshot = self._load_history_snapshot("alert_thresholds_snapshot.json")
        if snapshot is not None:
            try:
                return {
                    'warning': float(snapshot.get('warning', 0.80)),
                    'overlimit': float(snapshot.get('overlimit', 1.00)),
                }
            except (TypeError, ValueError):
                logger.warning("历史告警阈值快照格式异常，改用当前配置兜底")

        try:
            config = ConfigLoader()
            return {
                'warning': float(config.get("alerts.thresholds.warning", 0.80)),
                'overlimit': float(config.get("alerts.thresholds.overlimit", 1.00)),
            }
        except Exception as e:
            logger.warning(f"读取告警阈值失败，使用默认阈值：{e}")
            return {
                'warning': 0.80,
                'overlimit': 1.00,
            }

    def load_regulatory_concentration_limit(self) -> float:
        """
        加载监管集中度限额。
        历史模式优先读取归档根目录快照，找不到时回退到项目默认 JSON 配置。
        """
        FALLBACK = 0.16
        snapshot = self._load_history_snapshot("regulatory_concentration_limit_snapshot.json")
        if snapshot is not None:
            try:
                return float(snapshot.get("regulatory_concentration_limit", FALLBACK))
            except (TypeError, ValueError):
                logger.warning("历史监管集中度限额快照格式异常，改用默认配置兜底")

        file_path = self.project_root / "data" / "regulatory_concentration_limit.json"
        if file_path.exists():
            try:
                config = DataLoader._load_json_file(str(file_path))
                return float(config.get("regulatory_concentration_limit", FALLBACK))
            except (TypeError, ValueError, json.JSONDecodeError) as e:
                logger.warning(f"读取监管集中度限额配置失败，使用默认值 {FALLBACK}: {e}")

        return FALLBACK

    # ==================== 辅助方法 ====================
    
    def get_latest_date(self) -> datetime:
        """获取最新数据日期"""
        try:
            df = self.load_stage1_credit_1_1()
            return df['日期'].max()
        except Exception as e:
            logger.error(f"获取最新日期失败: {e}")
            return datetime.now()
    
    def get_available_accounts(self, page_name: Optional[str] = None) -> List[str]:
        """根据当前页面数据源获取账户列表（用于筛选器）"""
        try:
            if page_name == '单一信用限额':
                df = self.load_stage1_credit_1_2()
            elif page_name == '分类信用限额':
                df = self.load_stage2_credit_2()
            else:
                df = self.load_stage1_credit_1_1()

            accounts = sorted(
                df['内部证券账户名称']
                .dropna()
                .astype(str)
                .unique()
                .tolist()
            )
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
