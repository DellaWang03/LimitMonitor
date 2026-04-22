"""
阶段0处理器
实现10个Power Query查询：
1. 调整实控人名单
2. 调整实控人_北京国有资本
3. 风控部债券池
4. 风控部债券池_主体
5. 风控部债券池_主体_虚拟添加
6. 风控部债券池_主体_虚拟添加_每日
7. 公司净资产_手工
8. 公司净资产_手工_每日
9. 债券池日期
10. 原始风控部债券池_主体
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, Any, Optional
from loguru import logger

from ..common import WindCodeResolver, AccessDatabaseReader
from ..utils import DateValidator


class Stage0Processor:
    """阶段0数据处理器"""
    
    def __init__(self, data_dir: Path, output_dir: Path, config: Any = None,
                 target_date: Optional[str] = None):
        """
        初始化阶段0处理器
        
        参数:
            data_dir: 原始数据目录（local 时使用；migration 时由 config 解析路径）
            output_dir: 输出目录
            config: ConfigLoader 或 None，用于 get_data_file_path 一键切换路径
            target_date: 目标日期（YYYY-MM-DD）。设置后 query_bond_pool 从 accdb 中
                取该日期的数据而非最新日期，用于补跑历史漏跑数据（T+N 补跑 T-1）。
        """
        self.data_dir = Path(data_dir)
        self.output_dir = Path(output_dir)
        self.config = config
        self.target_date = target_date
        
        # 创建输出目录
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 初始化Wind代码解析器（传入 config 以支持路径 profile 切换）
        mapping_file = self.output_dir / "issuer_wind_code_mapping.csv"
        self.wind_resolver = WindCodeResolver(
            data_dir=self.data_dir,
            mapping_file=mapping_file,
            use_wind_api=False,
            cache_new_codes=True,
            config=config
        )
        
        # 缓存中间结果
        self.cache = {}
        
        logger.info("阶段0处理器初始化完成")
        if self.target_date:
            logger.info(f"  🔁 目标日期模式: accdb 将取 {self.target_date} 的数据")
    
    def _data_file_path(self, file_name: str) -> Path:
        """按当前 profile 返回数据源文件路径；无 config 时使用 data_dir / file_name。"""
        if self.config is not None and hasattr(self.config, "get_data_file_path"):
            return self.config.get_data_file_path(file_name)
        return self.data_dir / file_name
    
    def process_all(self) -> Dict[str, pd.DataFrame]:
        """
        执行所有查询
        
        返回:
            字典，键为查询名称，值为DataFrame
        """
        logger.info("=" * 80)
        logger.info("开始执行阶段0查询")
        logger.info("=" * 80)
        
        results = {}
        
        # 按依赖顺序执行查询
        queries = [
            ('调整实控人_北京国有资本', self.query_beijing_guoyou),
            ('调整实控人名单', self.query_adjusted_controller),
            ('风控部债券池', self.query_bond_pool),
            ('原始风控部债券池_主体', self.query_original_issuer_pool),
            ('风控部债券池_主体_虚拟添加', self.query_virtual_issuer_addition),
            ('债券池日期', self.query_bond_pool_dates),
            ('风控部债券池_主体_虚拟添加_每日', self.query_virtual_issuer_daily),
            ('风控部债券池_主体', self.query_issuer_pool),
            ('公司净资产_手工', self.query_net_assets_manual),
            ('公司净资产_手工_每日', self.query_net_assets_daily),
        ]
        
        for query_name, query_func in queries:
            try:
                logger.info(f"\n执行查询: {query_name}")
                logger.info("-" * 80)
                
                df = query_func()
                results[query_name] = df
                
                # 缓存结果
                self.cache[query_name] = df
                
                # 保存到Excel
                output_file = self.output_dir / f"{query_name}.xlsx"
                
                # 检查文件是否已存在
                file_exists = output_file.exists()
                action = "覆盖" if file_exists else "新建"
                
                # 保存（会自动覆盖已存在的文件）
                df.to_excel(output_file, index=False, sheet_name=query_name)
                
                logger.info(f"✓ {query_name}: {len(df)} 行 × {len(df.columns)} 列")
                logger.info(f"  {action}: {output_file.name}")
                
            except Exception as e:
                logger.error(f"✗ 查询失败: {query_name}")
                logger.error(f"  错误: {e}", exc_info=True)
                results[query_name] = pd.DataFrame()
        
        # 批量解析缺失的Wind代码（使用Excel辅助）
        logger.info("\n" + "=" * 80)
        logger.info("检查缺失的Wind代码")
        logger.info("=" * 80)
        
        stats = self.wind_resolver.get_coverage_stats()
        if stats['missing_count'] > 0:
            logger.warning(f"⚠️  发现 {stats['missing_count']} 个缺失的Wind代码")
            
            # 尝试批量解析（Windows会自动使用Excel，macOS保存列表）
            try:
                resolved = self.wind_resolver.batch_resolve_missing()
                
                if resolved > 0:
                    logger.info(f"✓ Excel自动补充成功: {resolved} 个Wind代码")
                    
                    # 重新处理风控部债券池_主体（使用新的Wind代码）
                    logger.info("重新处理风控部债券池_主体...")
                    df_updated = self.query_issuer_pool()
                    results['风控部债券池_主体'] = df_updated
                    
                    output_file = self.output_dir / "风控部债券池_主体.xlsx"
                    df_updated.to_excel(output_file, index=False)
                    logger.info(f"✓ 已覆盖更新: {output_file.name}")
                    
            except Exception as e:
                logger.debug(f"批量解析过程信息: {e}")
        
        logger.info("\n" + "=" * 80)
        logger.info("阶段0处理完成")
        logger.info("=" * 80)
        
        return results
    
    def query_beijing_guoyou(self) -> pd.DataFrame:
        """
        查询2: 调整实控人_北京国有资本
        数据源: 德勤-主体评级列表.xlsx / 北京国有资本
        """
        file_path = self._data_file_path("德勤-主体评级列表.xlsx")
        
        df = pd.read_excel(file_path, sheet_name="北京国有资本")
        
        # 转换列类型
        df = df.astype({
            '主体名称': 'str',
            '统一社会信用代码': 'str',
            '主体wind代码': 'str',
            '调整后实际控制人': 'str'
        })
        
        # 清洗字符串列（去除首尾空格）
        df['主体名称'] = df['主体名称'].str.strip()
        df['调整后实际控制人'] = df['调整后实际控制人'].str.strip()
        
        logger.info(f"  读取北京国有资本调整表: {len(df)} 条记录")
        
        return df
    
    def query_adjusted_controller(self) -> pd.DataFrame:
        """
        查询1: 调整实控人名单
        数据源: 德勤-主体评级列表.xlsx / Sheet1
        逻辑: 合并北京国有资本调整表
        """
        file_path = self._data_file_path("德勤-主体评级列表.xlsx")
        
        # 读取Sheet1
        df = pd.read_excel(file_path, sheet_name="Sheet1")
        
        # 选择需要的列
        df = df[['主体名称', '社会信用代码', '主体wind代码', '调整后实际控制人']].copy()
        
        # 清洗字符串列（去除首尾空格）
        # 关键修复：主体wind代码标准化，去除交易所后缀和 .0
        df['主体名称'] = df['主体名称'].str.strip()
        
        # 标准化 主体wind代码
        df['主体wind代码'] = df['主体wind代码'].astype(str).str.strip()
        # 去除交易所后缀 (.SH, .SZ, .IB 等)
        df['主体wind代码'] = df['主体wind代码'].str.split('.').str[0]
        # 去除 .0 后缀
        df['主体wind代码'] = df['主体wind代码'].str.replace(r'\.0$', '', regex=True)
        
        # 调整后实际控制人：保留 NaN，仅清洗非空值
        df['调整后实际控制人'] = df['调整后实际控制人'].apply(
            lambda x: str(x).strip() if pd.notna(x) and str(x).strip() != '' and str(x).lower() != 'nan' else None
        )
        
        # 去重
        df = df.drop_duplicates()
        
        # 获取北京国有资本调整表
        df_beijing = self.cache.get('调整实控人_北京国有资本')
        if df_beijing is None:
            df_beijing = self.query_beijing_guoyou()
        
        # Left Join
        df = df.merge(
            df_beijing[['统一社会信用代码', '调整后实际控制人']],
            left_on='社会信用代码',
            right_on='统一社会信用代码',
            how='left',
            suffixes=('_原始', '_北京')
        )
        
        # 优先使用北京国有资本的调整
        df['调整后实际控制人'] = df['调整后实际控制人_北京'].combine_first(
            df['调整后实际控制人_原始']
        )
        
        # 删除临时列
        df = df.drop(columns=['调整后实际控制人_原始', '调整后实际控制人_北京', '统一社会信用代码'])
        
        # 筛选主体wind代码不为 "0" 或 "nan"
        df = df[df['主体wind代码'].notna()]
        df = df[~df['主体wind代码'].isin(['0', 'nan', 'None'])]
        
        logger.info(f"  调整实控人名单: {len(df)} 个主体")
        
        return df
    
    def query_bond_pool(self) -> pd.DataFrame:
        """
        查询3: 风控部债券池
        数据源: 风控部债券池.accdb / 风控部债券池表
        逻辑: 筛选最新日期 + 添加市场后缀
        """
        db_path = self._data_file_path("风控部债券池.accdb")
        export_dir = None
        source_accdb_path = None
        if self.config is not None:
            if hasattr(self.config, "get_data_config_source_dir"):
                export_dir = self.config.get_data_config_source_dir()
            if hasattr(self.config, "get_data_file_path_without_override"):
                source_accdb_path = self.config.get_data_file_path_without_override("风控部债券池.accdb")
        freshness_threshold_date = None
        if self.config is not None:
            try:
                validator = DateValidator(self.data_dir, config=self.config)
                freshness_threshold_date = validator.get_t_minus_1_date()
            except Exception as e:
                logger.warning(f"获取交易日T-1失败，回退到自然日昨天判断: {e}")
        reader = AccessDatabaseReader(
            db_path,
            export_dir=export_dir,
            source_accdb_path=source_accdb_path,
            freshness_threshold_date=freshness_threshold_date,
        )
        df = reader.read_table("风控部债券池")
        
        # 清洗发行人名称（去除首尾空格）
        if '发行人名称' in df.columns:
            df['发行人名称'] = df['发行人名称'].str.strip()
        
        # 转换日期类型（format='mixed' 避免混合格式时的推断警告）
        df['日期'] = pd.to_datetime(df['日期'], format='mixed')
        
        # 按目标日期或最新日期过滤
        if self.target_date:
            target_ts = pd.Timestamp(self.target_date)
            available_dates = sorted(df['日期'].unique())
            if target_ts not in df['日期'].values:
                available_str = [str(d.date()) for d in available_dates]
                raise ValueError(
                    f"accdb 中不存在目标日期 {self.target_date} 的数据。"
                    f"可用日期: {available_str}"
                )
            selected_date = target_ts
            logger.info(f"  目标日期: {selected_date.date()}, {len(df[df['日期'] == selected_date])} 条记录（共 {len(available_dates)} 个可用日期）")
        else:
            selected_date = df['日期'].max()
            logger.info(f"  最新日期: {selected_date.date()}, {len(df[df['日期'] == selected_date])} 条记录")
        
        df = df[df['日期'] == selected_date].copy()
        
        # 添加市场后缀到债券代码
        def add_market_suffix(row):
            code = str(row['债券代码'])
            market = str(row['市场名称'])
            
            if market == '银行间':
                return f"{code}.IB"
            elif market == '上交所':
                return f"{code}.SH"
            elif market == '深交所':
                return f"{code}.SZ"
            elif market == '其他':
                return f"{code}.BJ"
            else:
                return code
        
        df['代码'] = df.apply(add_market_suffix, axis=1)
        
        return df
    
    def query_original_issuer_pool(self) -> pd.DataFrame:
        """
        查询10: 原始风控部债券池_主体
        数据源: 风控部债券池
        逻辑: 提取唯一的发行人+主体池
        """
        df_bond_pool = self.cache.get('风控部债券池')
        if df_bond_pool is None:
            df_bond_pool = self.query_bond_pool()
        
        # 选择列并去重
        df = df_bond_pool[['日期', '发行人名称', '主体池']].copy()
        
        # 清洗发行人名称（去除首尾空格）
        df['发行人名称'] = df['发行人名称'].str.strip()
        
        df = df.drop_duplicates()
        
        logger.info(f"  原始主体池: {len(df)} 条记录")
        
        return df
    
    def query_virtual_issuer_addition(self) -> pd.DataFrame:
        """
        查询5: 风控部债券池_主体_虚拟添加
        数据源: sample data/风控部债券池_主体_虚拟添加.xlsx
        逻辑: 读取Excel文件，并执行anti-join筛选（与M代码一致）
        
        M代码逻辑（阶段0_query.md 第209-218行）:
        1. 与"原始风控部债券池_主体"左连接（键：发行人名称）
        2. 筛选连接结果为null的行（即不在原始池中的主体）
        """
        virtual_file = self._data_file_path("风控部债券池_主体_虚拟添加.xlsx")
        
        if not virtual_file.exists():
            logger.warning(f"  虚拟添加文件不存在: {virtual_file}")
            return pd.DataFrame(columns=['变动日期', '发行人名称', '主体池', '备注'])
        
        try:
            df = pd.read_excel(virtual_file)
            
            # 清洗发行人名称（去除首尾空格）
            if '发行人名称' in df.columns:
                df['发行人名称'] = df['发行人名称'].str.strip()
            
            original_count = len(df)
            logger.info(f"  虚拟添加主体（原始）: {original_count} 条记录")
            
            # === Anti-join: 排除已在原始池中的主体（与M代码一致）===
            # M代码第209-218行: 与原始风控部债券池_主体左连接，筛选连接结果为null的行
            df_original_pool = self.cache.get('原始风控部债券池_主体')
            if df_original_pool is None:
                df_original_pool = self.query_original_issuer_pool()
                self.cache['原始风控部债券池_主体'] = df_original_pool
            
            if len(df_original_pool) > 0:
                # 获取原始池中的唯一(发行人名称, 主体池)组合
                original_keys = df_original_pool[['发行人名称', '主体池']].drop_duplicates()
                
                # 与虚拟添加表左连接（键：发行人名称）
                df = df.merge(
                    original_keys[['发行人名称']].drop_duplicates().assign(in_original=1),
                    on='发行人名称',
                    how='left'
                )
                
                # 筛选不在原始池中的主体（in_original为null）
                df = df[df['in_original'].isna()].copy()
                df = df.drop(columns=['in_original'])
                
                filtered_count = len(df)
                logger.info(f"  Anti-join筛选后: {filtered_count} 条记录（排除了 {original_count - filtered_count} 条已在原始池中的主体）")
            else:
                logger.info(f"  原始池为空，保留所有虚拟添加主体")
            
            return df
        except Exception as e:
            logger.error(f"  读取虚拟添加文件失败: {e}")
            return pd.DataFrame(columns=['变动日期', '发行人名称', '主体池', '备注'])
    
    def query_bond_pool_dates(self) -> pd.DataFrame:
        """
        查询9: 债券池日期
        数据源: 风控部债券池
        逻辑: 提取唯一日期
        """
        df_bond_pool = self.cache.get('风控部债券池')
        if df_bond_pool is None:
            df_bond_pool = self.query_bond_pool()
        
        # 提取唯一日期
        df = df_bond_pool[['日期']].drop_duplicates()
        df = df.sort_values('日期')
        
        logger.info(f"  债券池日期: {len(df)} 个日期")
        
        return df
    
    def query_virtual_issuer_daily(self) -> pd.DataFrame:
        """
        查询6: 风控部债券池_主体_虚拟添加_每日
        数据源: 标准日期表 + 风控部债券池_主体_虚拟添加
        逻辑: 日期展开（累积逻辑 - 从变动日期开始，每个主体在后续所有日期都存在）
        
        M代码关键逻辑:
        1. Date.IsInCurrentYear([日期]) - 仅保留本年度日期
        2. 与"债券池日期"右连接 - 只保留债券池实际存在的日期
        """
        # 读取标准日期表
        date_file = self._data_file_path("标准日期表.xlsx")
        df_dates = pd.read_excel(date_file, sheet_name="标准日期表")
        df_dates['日期'] = pd.to_datetime(df_dates['日期'])
        df_dates = df_dates.sort_values('日期')
        
        # 【P1-3修复1】按M代码要求:仅保留本年度日期 (Date.IsInCurrentYear([日期]))
        # 补跑模式下使用目标日期所在年份，避免跨年补跑时过滤掉历史年份的日历行
        from datetime import datetime
        target_year = int(self.target_date[:4]) if self.target_date else datetime.now().year
        df_dates = df_dates[df_dates['日期'].dt.year == target_year].copy()
        logger.info(f"  标准日期表筛选年度({target_year}): {len(df_dates)} 天")
        
        # 获取虚拟添加数据
        df_virtual = self.cache.get('风控部债券池_主体_虚拟添加')
        if df_virtual is None:
            df_virtual = self.query_virtual_issuer_addition()
        
        if len(df_virtual) == 0:
            logger.warning("  虚拟添加数据为空，返回空DataFrame")
            return pd.DataFrame(columns=['日期', '发行人名称', '主体池'])
        
        # 转换变动日期为datetime（支持多种格式）
        df_virtual = df_virtual.copy()
        df_virtual['变动日期'] = pd.to_datetime(df_virtual['变动日期'], format='mixed', errors='coerce')
        
        # 展开逻辑：每个主体从其变动日期开始，在之后的所有日期都存在
        # M代码逻辑: 对每个日期，找出变动日期<=该日期的所有主体，取最新的记录
        results = []
        for _, row in df_virtual.iterrows():
            change_date = row['变动日期']
            # 只选择 >= 变动日期的日期
            valid_dates = df_dates[df_dates['日期'] >= change_date]
            
            if len(valid_dates) > 0:
                temp_df = valid_dates[['日期']].copy()
                temp_df['发行人名称'] = row['发行人名称']
                temp_df['主体池'] = row['主体池']
                results.append(temp_df)
        
        if len(results) == 0:
            logger.info(f"  虚拟添加每日展开(本年度): 0 条记录")
            return pd.DataFrame(columns=['日期', '发行人名称', '主体池'])
        
        df_expanded = pd.concat(results, ignore_index=True)
        logger.info(f"  虚拟添加每日展开(本年度): {len(df_expanded)} 条记录（{len(df_virtual)}个主体）")
        
        # 【P1-3修复2】按M代码要求:与"债券池日期"右连接，只保留债券池实际存在的日期
        # M代码: Table.NestedJoin(更改的类型, {"日期"}, 债券池日期, {"日期"}, "债券池日期", JoinKind.RightOuter)
        df_bond_pool_dates = self.cache.get('债券池日期')
        if df_bond_pool_dates is None:
            # 如果cache中没有，调用query_bond_pool_dates获取
            df_bond_pool_dates = self.query_bond_pool_dates()
            if df_bond_pool_dates is None or len(df_bond_pool_dates) == 0:
                logger.warning("  债券池日期未找到，返回展开结果（未与债券池日期对齐）")
                return df_expanded
        
        # 右连接：以债券池日期为准，只保留债券池中存在的日期
        df_bond_pool_dates = df_bond_pool_dates.copy()
        df_bond_pool_dates['日期'] = pd.to_datetime(df_bond_pool_dates['日期'])
        
        df_result = df_bond_pool_dates[['日期']].merge(
            df_expanded,
            on='日期',
            how='left'  # 相当于M代码的右连接（从债券池日期角度看是左连接）
        )
        
        # 去除日期存在但发行人名称为null的记录（说明该日期没有虚拟添加主体）
        rows_before = len(df_result)
        df_result = df_result[df_result['发行人名称'].notna()].copy()
        rows_after = len(df_result)
        
        logger.info(f"  与债券池日期对齐: {len(df_expanded)} -> {rows_after} 条记录 (仅保留债券池日期)")
        
        return df_result
    
    def query_issuer_pool(self) -> pd.DataFrame:
        """
        查询4: 风控部债券池_主体
        数据源: 原始风控部债券池_主体 + 风控部债券池_主体_虚拟添加_每日
        逻辑: 合并后去重并筛选主体池非空，最后补充发行人wind代码
        """
        # 获取原始主体池（已经是最新日期的数据）
        df_original = self.cache.get('原始风控部债券池_主体')
        if df_original is None:
            df_original = self.query_original_issuer_pool()
        
        # 获取虚拟添加_每日（与M代码一致）
        df_virtual_daily = self.cache.get('风控部债券池_主体_虚拟添加_每日')
        if df_virtual_daily is None:
            df_virtual_daily = self.query_virtual_issuer_daily()
        
        # 仅保留M代码使用的列，并去重
        df_original = df_original[['日期', '发行人名称', '主体池']].drop_duplicates()
        df_virtual_daily = df_virtual_daily[['日期', '发行人名称', '主体池']].drop_duplicates()
        
        # 合并并去重（M代码：Table.Combine + Table.Distinct）
        df = pd.concat([df_original, df_virtual_daily], ignore_index=True)
        df = df.drop_duplicates()
        
        # 筛选非空主体池
        df = df[df['主体池'].notna() & (df['主体池'] != '')]
        
        # 添加Wind代码
        logger.info(f"  查询 {len(df)} 个主体的Wind代码...")
        
        df['发行人wind代码'] = df['发行人名称'].apply(
            lambda x: self.wind_resolver.get_code(x, strict=False)
        )
        
        # 统计覆盖率
        covered = df['发行人wind代码'].notna().sum()
        total = len(df)
        logger.info(f"  Wind代码覆盖率: {covered}/{total} ({covered/total*100:.1f}%)")
        
        return df
    
    def query_net_assets_manual(self) -> pd.DataFrame:
        """
        查询7: 公司净资产_手工
        数据源: 净资产.xlsx
        """
        file_path = self._data_file_path("净资产.xlsx")
        
        df = pd.read_excel(file_path, sheet_name="净资产")
        
        # 选择需要的列并重命名
        df = df[['日期', '净资产（万元）']].copy()
        df.columns = ['变动日期', '公司净资产(万)']
        
        # 转换类型
        df['变动日期'] = pd.to_datetime(df['变动日期'])
        df['公司净资产(万)'] = pd.to_numeric(df['公司净资产(万)'], errors='coerce')
        
        logger.info(f"  公司净资产: {len(df)} 条记录")
        
        return df
    
    def query_net_assets_daily(self) -> pd.DataFrame:
        """
        查询8: 公司净资产_手工_每日
        数据源: 标准日期表 + 公司净资产_手工
        逻辑: 日期展开（取最近一次变动值）
        """
        # 读取标准日期表
        date_file = self._data_file_path("标准日期表.xlsx")
        df_dates = pd.read_excel(date_file, sheet_name="标准日期表")
        df_dates['日期'] = pd.to_datetime(df_dates['日期'])
        
        # 获取净资产手工数据
        df_assets = self.cache.get('公司净资产_手工')
        if df_assets is None:
            df_assets = self.query_net_assets_manual()
        
        # 展开到每一天（累积逻辑）
        result = []
        
        for _, date_row in df_dates.iterrows():
            current_date = date_row['日期']
            
            # 查找截至当前日期的最新净资产值
            historical = df_assets[df_assets['变动日期'] <= current_date]
            
            if len(historical) > 0:
                latest = historical.sort_values('变动日期').iloc[-1]
                result.append({
                    '日期': current_date,
                    '公司净资产(万)': latest['公司净资产(万)']
                })
        
        df_result = pd.DataFrame(result)
        
        logger.info(f"  公司净资产每日: {len(df_result)} 个日期")
        
        return df_result
