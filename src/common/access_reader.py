"""
Access数据库读取器
支持在macOS和Windows上读取.accdb文件
"""

import subprocess
import pandas as pd
from pathlib import Path
from typing import Optional
from datetime import datetime, timedelta
import platform
from loguru import logger


class AccessDatabaseReader:
    """Access数据库读取器"""
    
    def __init__(
        self,
        db_path: Path,
        export_dir: Optional[Path] = None,
        source_accdb_path: Optional[Path] = None,
        freshness_threshold_date: Optional[datetime] = None,
    ):
        """
        初始化Access数据库读取器
        
        参数:
            db_path: Access数据库文件路径(.accdb)，用于同目录导出文件查找及 pyodbc
            export_dir: 仅用于风控部债券池：导出 CSV 的目录（如 data_config_source），先刷新再从此处读
            source_accdb_path: 仅用于风控部债券池：mdb-export 的 .accdb 路径（如 SMB 挂载路径）
        """
        self.db_path = Path(db_path)
        self.export_dir = Path(export_dir) if export_dir else None
        self.source_accdb_path = Path(source_accdb_path) if source_accdb_path else None
        self.freshness_threshold_date = freshness_threshold_date.date() if isinstance(freshness_threshold_date, datetime) else freshness_threshold_date
        
        if not self.export_dir and not self.db_path.exists():
            raise FileNotFoundError(f"Access数据库不存在: {db_path}")
        
        self.system = platform.system()
        logger.info(f"操作系统: {self.system}")
        
    def read_table(self, table_name: str, prefer_access: bool = None) -> pd.DataFrame:
        """
        读取Access表（智能环境检测，自动切换数据源）
        
        参数:
            table_name: 表名
            prefer_access: 是否优先使用Access（None=自动检测）
            
        返回:
            DataFrame
            
        智能策略：
            - Windows: 优先pyodbc读取Access（生产环境）
            - macOS: 优先导出文件/临时Excel（开发环境）
            - 所有平台: 自动fallback到可用数据源
        """
        logger.info(f"读取Access表: {table_name} from {self.db_path.name}")
        logger.info(f"  当前系统: {self.system}")
        
        # 自动判断是否优先使用Access
        if prefer_access is None:
            # Windows系统优先使用Access（生产环境）
            prefer_access = (self.system == 'Windows')
            logger.info(f"  优先数据源: {'Access数据库' if prefer_access else '导出文件/临时数据'}")
        
        # Windows环境 或 显式要求Access优先
        if prefer_access:
            # 策略1: pyodbc读取Access（生产环境标准方式）
            try:
                df = self._read_with_pyodbc(table_name)
                logger.info(f"✓ 从Access数据库读取成功: {len(df)} 行")
                return df
            except Exception as e:
                logger.warning(f"⚠️  pyodbc读取失败: {e}")
                logger.warning(f"   将尝试fallback到导出文件...")
        
        # 仅风控部债券池：若配置了 export_dir + source_accdb_path，先检查与 mdb-export 写入路径相同的 CSV 是否已为最新，是则跳过导出
        if (
            table_name == "风控部债券池"
            and self.export_dir
            and self.source_accdb_path
        ):
            # 与 _try_mdb_export 写入路径一致：export_dir / 风控部债券池.csv
            out_csv = self.export_dir / f"{table_name}.csv"
            need_export = True
            if out_csv.exists():
                max_date = self._csv_max_date(out_csv)
                threshold = self.freshness_threshold_date or (datetime.now().date() - timedelta(days=1))
                if max_date is not None:
                    if max_date.date() >= threshold:
                        need_export = False
                        logger.info(f"  CSV 已为最新日期 {max_date.date()}（≥T-1），跳过 mdb-export")
                    else:
                        logger.info(f"  CSV 最大日期 {max_date.date()} 早于 T-1 {threshold}，将重新导出")
                else:
                    # 解析失败时：若文件在 24 小时内修改过，视为刚导出，跳过
                    try:
                        mtime = out_csv.stat().st_mtime
                        age_seconds = datetime.now().timestamp() - mtime
                        if age_seconds <= 86400:  # 24h
                            need_export = False
                            logger.info(f"  CSV 为 24 小时内写入，跳过 mdb-export")
                        else:
                            logger.info(f"  无法解析 CSV 最大日期且文件超过 24h，将重新导出")
                    except OSError:
                        logger.info(f"  无法解析 CSV 最大日期，将重新导出")
            else:
                logger.info(f"  export_dir 下无 CSV，将执行 mdb-export")
            if need_export and self.system == "Darwin" and self.source_accdb_path.exists():
                self._try_mdb_export(table_name, self.source_accdb_path, self.export_dir)
            if out_csv.exists():
                df = pd.read_csv(out_csv)
                logger.info(f"✓ 从 export_dir 读取风控部债券池: {len(df)} 行")
                return df
        
        # 策略2: 检查是否有导出的Excel/CSV文件（开发环境或fallback）
        exported_files = [
            self.db_path.parent / f"{self.db_path.stem}_导出.xlsx",
            self.db_path.parent / f"{self.db_path.stem}_导出.csv",
            self.db_path.parent / f"{table_name}.xlsx",
            self.db_path.parent / f"{table_name}.csv",
        ]
        
        for export_file in exported_files:
            if export_file.exists():
                logger.info(f"✓ 发现导出文件: {export_file.name}")
                if export_file.suffix == '.xlsx':
                    df = pd.read_excel(export_file, sheet_name=0)
                else:
                    df = pd.read_csv(export_file)
                logger.info(f"  从导出文件读取成功: {len(df)} 行")
                
                if self.system != 'Windows':
                    logger.info(f"  💡 开发环境建议: Windows部署时将自动使用Access数据库")
                
                return df
        
        # 策略3: 临时使用阶段0的Excel（开发环境fallback）
        stage0_excel = self.db_path.parent / "阶段" / "限额监控_阶段0_风控债券池.xlsx"
        if stage0_excel.exists() and table_name == "风控部债券池":
            if self.system == 'Windows':
                logger.error(f"⚠️  生产环境(Windows)不应使用临时数据源！")
                logger.error(f"   请确保Access数据库可访问或提供导出文件")
            else:
                logger.warning(f"⚠️  开发环境: 使用临时数据源: {stage0_excel.name}")
                logger.info(f"   💡 Windows部署时将自动使用Access数据库")
            
            try:
                df = pd.read_excel(stage0_excel, sheet_name=table_name)
                logger.info(f"  从临时Excel读取成功: {len(df)} 行")
                return df
            except Exception as e:
                logger.warning(f"  读取临时Excel失败: {e}")
        
        # 策略4: 如果之前没尝试过pyodbc，现在尝试（非Windows环境）
        if not prefer_access:
            try:
                df = self._read_with_pyodbc(table_name)
                logger.info(f"✓ 从Access数据库读取成功: {len(df)} 行")
                return df
            except Exception as e:
                logger.warning(f"pyodbc读取失败: {e}")
        
        # 策略5: 尝试pandas_access（第三方库）
        try:
            return self._read_with_pandas_access(table_name)
        except Exception as e:
            logger.warning(f"pandas_access读取失败: {e}")
        
        # 所有策略都失败
        self._raise_access_error(table_name, stage0_excel)

    def _csv_max_date(self, csv_path: Path) -> Optional[pd.Timestamp]:
        """
        仅读 CSV 的「日期」列并返回最大日期，用于判断是否需重新从 .accdb 导出。
        与 mdb-export 写入的 CSV 路径一致时，日期格式通常为 MM/DD/YY HH:MM:SS。
        失败或缺少列时返回 None。
        """
        try:
            chunks = pd.read_csv(csv_path, usecols=["日期"], chunksize=100_000, encoding="utf-8")
            max_ts = None
            for ch in chunks:
                if ch.empty or "日期" not in ch.columns:
                    continue
                # mdb-export 导出格式多为 "01/26/25 00:00:00"，指定 format 避免推断并加速
                ser = pd.to_datetime(ch["日期"], format="%m/%d/%y %H:%M:%S", errors="coerce")
                if ser.isna().all():
                    ser = pd.to_datetime(ch["日期"], errors="coerce")
                m = ser.max()
                if pd.notna(m) and (max_ts is None or m > max_ts):
                    max_ts = m
            result = max_ts if isinstance(max_ts, pd.Timestamp) else None
            if result is None:
                logger.info("  无法从 CSV 解析出最大日期（列缺失或格式不符）")
            return result
        except Exception as e:
            logger.info(f"  读取 CSV 最大日期失败: {e}")
            return None

    def _try_mdb_export(self, table_name: str, accdb_path: Path, export_dir: Path) -> bool:
        """
        使用 mdb-export 将 Access 表导出为 CSV 到 export_dir（仅用于风控部债券池）。
        需要系统已安装 mdb-tools (brew install mdbtools)。返回 True 表示写入成功。
        """
        out_file = export_dir / f"{table_name}.csv"
        try:
            result = subprocess.run(
                ["mdb-export", str(accdb_path), table_name],
                capture_output=True,
                text=True,
                timeout=600,
            )
            if result.returncode != 0:
                logger.warning(f"mdb-export 失败: {result.stderr or result.stdout}")
                return False
            export_dir.mkdir(parents=True, exist_ok=True)
            out_file.write_text(result.stdout, encoding="utf-8")
            logger.info(f"✓ mdb-export 已写入: {out_file}")
            return True
        except FileNotFoundError:
            logger.warning("未找到 mdb-export，请安装: brew install mdbtools")
            return False
        except subprocess.TimeoutExpired:
            logger.warning("mdb-export 超时")
            return False
        except Exception as e:
            logger.warning(f"mdb-export 异常: {e}")
            return False

    def _raise_access_error(self, table_name: str, stage0_excel: Path):
        """抛出详细的错误信息"""
        if self.system == 'Windows':
            # Windows环境错误（生产环境）
            error_msg = (
                f"❌ Windows生产环境：无法读取Access数据库表 '{table_name}'\n\n"
                f"【必需操作】\n"
                f"1. 安装Microsoft Access Database Engine:\n"
                f"   下载: https://www.microsoft.com/en-us/download/details.aspx?id=54920\n\n"
                f"2. 确认Access数据库路径正确:\n"
                f"   {self.db_path}\n\n"
                f"3. 或提供导出的Excel文件:\n"
                f"   保存为: {self.db_path.parent}/{self.db_path.stem}_导出.xlsx\n"
            )
        else:
            # macOS环境错误（开发环境）
            error_msg = (
                f"❌ macOS开发环境：无法读取Access数据库表 '{table_name}'\n\n"
                f"【开发环境解决方案】\n\n"
                f"方案1：使用导出文件（推荐）\n"
                f"  在Windows上导出Access表为Excel:\n"
                f"  保存为: {self.db_path.parent}/{self.db_path.stem}_导出.xlsx\n\n"
                f"方案2：使用临时数据（快速测试）\n"
                f"  确保存在: {stage0_excel}\n\n"
                f"方案3：使用mdb-tools\n"
                f"  brew install mdb-tools\n"
                f"  mdb-export '{self.db_path}' '{table_name}' > output.csv\n\n"
                f"💡 注意: Windows部署时会自动使用pyodbc读取Access数据库\n"
            )
        
        raise RuntimeError(error_msg)
    
    def _read_with_pyodbc(self, table_name: str) -> pd.DataFrame:
        """使用pyodbc读取"""
        import pyodbc
        
        # 构建连接字符串
        if self.system == 'Windows':
            driver = '{Microsoft Access Driver (*.mdb, *.accdb)}'
        else:
            # macOS可能需要配置ODBC驱动
            driver = '{Microsoft Access Driver (*.mdb, *.accdb)}'
        
        conn_str = f'DRIVER={driver};DBQ={self.db_path};'
        
        logger.debug(f"连接字符串: {conn_str}")
        
        # 连接并查询
        conn = pyodbc.connect(conn_str)
        
        try:
            df = pd.read_sql(f"SELECT * FROM [{table_name}]", conn)
            logger.info(f"✓ 读取成功: {len(df)} 行")
            return df
        finally:
            conn.close()
    
    def _read_with_pandas_access(self, table_name: str) -> pd.DataFrame:
        """使用pandas_access读取（第三方库）"""
        import pandas_access as mdb
        
        df = mdb.read_table(str(self.db_path), table_name)
        logger.info(f"✓ 读取成功: {len(df)} 行")
        return df
    
    def list_tables(self) -> list:
        """列出数据库中的所有表"""
        try:
            import pyodbc
            
            if self.system == 'Windows':
                driver = '{Microsoft Access Driver (*.mdb, *.accdb)}'
            else:
                driver = '{Microsoft Access Driver (*.mdb, *.accdb)}'
            
            conn_str = f'DRIVER={driver};DBQ={self.db_path};'
            conn = pyodbc.connect(conn_str)
            
            try:
                cursor = conn.cursor()
                tables = [row.table_name for row in cursor.tables(tableType='TABLE')]
                logger.info(f"数据库中的表: {tables}")
                return tables
            finally:
                conn.close()
                
        except Exception as e:
            logger.warning(f"无法列出表: {e}")
            return []
