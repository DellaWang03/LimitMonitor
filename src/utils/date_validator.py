"""
日期验证器 - 确保Access数据库已更新到T-1
"""
import pandas as pd
from pathlib import Path
from datetime import datetime, date
from typing import Tuple, Optional, Any
from loguru import logger


class DateValidator:
    """日期验证器 - 确保Access数据库已更新到T-1（前一个交易日）"""
    
    def __init__(self, data_dir: Path, config: Any = None):
        """
        初始化日期验证器
        
        Args:
            data_dir: 数据源目录（config 为空时用于标准日期表路径）
            config: ConfigLoader，用于 get_data_file_path 路径 profile 切换
        """
        self.data_dir = Path(data_dir)
        self.config = config
        self._standard_dates = None
    
    def _date_table_path(self) -> Path:
        """标准日期表路径（按 profile）。"""
        if self.config is not None and hasattr(self.config, "get_data_file_path"):
            return self.config.get_data_file_path("标准日期表.xlsx")
        return self.data_dir / "标准日期表.xlsx"
    
    def get_standard_dates(self) -> pd.DataFrame:
        """
        读取标准日期表（交易日日历）
        
        Returns:
            包含'日期'和'日期类别'列的DataFrame，已按日期排序
        """
        if self._standard_dates is None:
            date_file = self._date_table_path()
            
            if not date_file.exists():
                raise FileNotFoundError(f"标准日期表不存在: {date_file}")
            
            df = pd.read_excel(date_file, sheet_name="标准日期表")
            df['日期'] = pd.to_datetime(df['日期'])
            df = df.sort_values('日期')
            self._standard_dates = df
            
            # 统计工作日数量（如果有日期类别列）
            if '日期类别' in df.columns:
                working_days_count = len(df[df['日期类别'] == '工作日'])
                logger.debug(f"加载标准日期表: {len(df)} 条记录，其中 {working_days_count} 个工作日")
            else:
                logger.debug(f"加载标准日期表: {len(df)} 条记录")
        
        return self._standard_dates
    
    def get_t_minus_1_date(self, as_of_date: Optional[date] = None) -> datetime:
        """
        获取T-1日期（前一个交易日）
        
        Args:
            as_of_date: 基准日期，默认为今天
        
        Returns:
            T-1交易日（datetime对象）
            
        Examples:
            今天是2026-01-23（周五），T-1 = 2026-01-22（周四）
            今天是2026-01-26（周一），T-1 = 2026-01-23（周五）
        """
        df_dates = self.get_standard_dates()
        
        if as_of_date is None:
            as_of_date = datetime.now().date()
        else:
            as_of_date = pd.to_datetime(as_of_date).date()
        
        # 检查是否有"日期类别"列
        if '日期类别' not in df_dates.columns:
            raise ValueError(
                f"标准日期表缺少'日期类别'列\n"
                f"请确认标准日期表.xlsx包含'日期'和'日期类别'两列"
            )
        
        # 先筛选出"工作日"类型的记录
        working_days = df_dates[df_dates['日期类别'] == '工作日'].copy()
        
        if len(working_days) == 0:
            raise ValueError(
                f"标准日期表中没有找到'工作日'类型的记录\n"
                f"请检查'日期类别'列的值是否正确（应为'工作日'或'节假日'）"
            )
        
        # 从工作日中找到<基准日期的最大日期（即前一个交易日）
        valid_dates = working_days[working_days['日期'].dt.date < as_of_date]
        
        if len(valid_dates) == 0:
            raise ValueError(
                f"标准日期表中没有找到 {as_of_date} 之前的工作日\n"
                f"请检查标准日期表是否已更新"
            )
        
        t_minus_1 = valid_dates['日期'].max()
        
        logger.debug(f"基准日期: {as_of_date}, T-1工作日: {t_minus_1.date()}")
        return t_minus_1
    
    def validate_access_database_freshness(
        self, 
        access_db_path: Path,
        expected_date: Optional[datetime] = None,
        strict_mode: bool = False
    ) -> Tuple[bool, str, Optional[datetime]]:
        """
        验证Access数据库是否已更新到T-1日期
        
        Args:
            access_db_path: Access数据库路径
            expected_date: 预期日期（T-1），默认自动获取
            strict_mode: 严格模式（数据不匹配时是否抛出异常）
        
        Returns:
            (是否通过, 详细信息, 实际日期)
            
        Raises:
            RuntimeError: 如果strict_mode=True且数据未更新
        """
        if expected_date is None:
            expected_date = self.get_t_minus_1_date()
        
        expected_date_str = expected_date.strftime('%Y-%m-%d')
        
        logger.info(f"\n{'='*70}")
        logger.info(f"Access数据库新鲜度验证")
        logger.info(f"数据库文件: {access_db_path.name}")
        logger.info(f"预期日期（T-1）: {expected_date_str}")
        logger.info(f"{'='*70}")
        
        try:
            # 读取Access数据库（与 stage0 一致：传入 export_dir/source_accdb_path 时先刷新再读 data_config_source，保证校验用最新数据）
            from ..common import AccessDatabaseReader
            export_dir = None
            source_accdb_path = None
            if self.config is not None:
                if hasattr(self.config, "get_data_config_source_dir"):
                    export_dir = self.config.get_data_config_source_dir()
                if hasattr(self.config, "get_data_file_path_without_override"):
                    source_accdb_path = self.config.get_data_file_path_without_override("风控部债券池.accdb")
            reader = AccessDatabaseReader(
                access_db_path,
                export_dir=export_dir,
                source_accdb_path=source_accdb_path,
                freshness_threshold_date=expected_date,
            )
            df = reader.read_table("风控部债券池")
            
            # 检查是否包含日期字段
            if '日期' not in df.columns:
                msg = "❌ Access数据库缺少'日期'字段，无法验证新鲜度"
                logger.error(msg)
                return False, msg, None
            
            # 转换日期并获取最大值（风控部债券池 CSV 为 mdb-export 格式：%m/%d/%y %H:%M:%S）
            df['日期'] = pd.to_datetime(df['日期'], format="%m/%d/%y %H:%M:%S", errors="coerce")
            actual_date = df['日期'].max()
            actual_date_str = actual_date.strftime('%Y-%m-%d')
            
            logger.info(f"Access中最大日期: {actual_date_str}")
            logger.info(f"数据记录数: {len(df)} 条")
            
            # 对比日期
            if actual_date.date() == expected_date.date():
                msg = f"✅ Access数据库已更新到T-1: {actual_date_str}"
                logger.info(msg)
                return True, msg, actual_date
            else:
                days_behind = (expected_date.date() - actual_date.date()).days
                msg = (
                    f"❌ Access数据库未更新！\n"
                    f"   预期日期（T-1）: {expected_date_str}\n"
                    f"   实际日期: {actual_date_str}\n"
                    f"   落后: {days_behind} 个日历日\n"
                    f"   ⚠️  请更新 {access_db_path.name} 文件后重新运行"
                )
                logger.error(msg)
                
                if strict_mode:
                    raise RuntimeError(msg)
                
                return False, msg, actual_date
                
        except Exception as e:
            msg = f"❌ 无法读取Access数据库: {e}"
            logger.error(msg)
            
            if strict_mode:
                raise RuntimeError(msg)
            
            return False, msg, None
    
    def get_business_date_info(self) -> dict:
        """
        获取完整的业务日期信息
        
        Returns:
            {
                'today': 今天（date）,
                't_minus_1': T-1日期（date）,
                'is_trading_day': 今天是否是交易日（bool）,
                't_minus_1_str': T-1日期字符串（str）
            }
        """
        df_dates = self.get_standard_dates()
        today = datetime.now().date()
        
        # 判断今天是否是工作日（交易日）
        if '日期类别' in df_dates.columns:
            # 筛选工作日
            working_days = df_dates[df_dates['日期类别'] == '工作日']
            is_trading_day = today in working_days['日期'].dt.date.values
        else:
            # 兼容：如果没有日期类别列，假设表中所有日期都是交易日
            logger.warning("标准日期表缺少'日期类别'列，假设所有日期均为工作日")
            is_trading_day = today in df_dates['日期'].dt.date.values
        
        # 获取T-1
        t_minus_1 = self.get_t_minus_1_date(today)
        
        return {
            'today': today,
            't_minus_1': t_minus_1.date(),
            'is_trading_day': is_trading_day,
            't_minus_1_str': t_minus_1.strftime('%Y-%m-%d')
        }
    
    def log_business_date_summary(self):
        """打印业务日期摘要信息"""
        date_info = self.get_business_date_info()
        
        logger.info(f"\n📅 业务日期信息:")
        logger.info(f"   今天: {date_info['today']}")
        logger.info(f"   T-1日期（前一个交易日）: {date_info['t_minus_1']}")
        logger.info(f"   今天是交易日: {'是' if date_info['is_trading_day'] else '否'}")
