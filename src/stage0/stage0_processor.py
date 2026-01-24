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
from typing import Dict
from loguru import logger

from ..common import WindCodeResolver, AccessDatabaseReader


class Stage0Processor:
    """阶段0数据处理器"""
    
    def __init__(self, data_dir: Path, output_dir: Path, config: dict = None):
        """
        初始化阶段0处理器
        
        参数:
            data_dir: 原始数据目录
            output_dir: 输出目录
            config: 配置字典
        """
        self.data_dir = Path(data_dir)
        self.output_dir = Path(output_dir)
        self.config = config or {}
        
        # 创建输出目录
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 初始化Wind代码解析器（统一使用To_WindCode()策略）
        mapping_file = self.output_dir / "issuer_wind_code_mapping.csv"
        self.wind_resolver = WindCodeResolver(
            data_dir=self.data_dir,
            mapping_file=mapping_file,
            use_wind_api=False,  # 禁用Wind API，统一使用To_WindCode()
            cache_new_codes=True
        )
        
        # 缓存中间结果
        self.cache = {}
        
        logger.info("阶段0处理器初始化完成")
    
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
        file_path = self.data_dir / "德勤-主体评级列表.xlsx"
        
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
        file_path = self.data_dir / "德勤-主体评级列表.xlsx"
        
        # 读取Sheet1
        df = pd.read_excel(file_path, sheet_name="Sheet1")
        
        # 选择需要的列
        df = df[['主体名称', '社会信用代码', '主体wind代码', '调整后实际控制人']].copy()
        
        # 清洗字符串列（去除首尾空格）
        df['主体名称'] = df['主体名称'].str.strip()
        df['调整后实际控制人'] = df['调整后实际控制人'].str.strip()
        
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
        df['调整后实际控制人'] = df['调整后实际控制人_北京'].fillna(
            df['调整后实际控制人_原始']
        )
        
        # 删除临时列
        df = df.drop(columns=['调整后实际控制人_原始', '调整后实际控制人_北京', '统一社会信用代码'])
        
        # 转换类型
        df['调整后实际控制人'] = df['调整后实际控制人'].astype(str)
        
        logger.info(f"  调整实控人名单: {len(df)} 个主体")
        
        return df
    
    def query_bond_pool(self) -> pd.DataFrame:
        """
        查询3: 风控部债券池
        数据源: 风控部债券池.accdb / 风控部债券池表
        逻辑: 筛选最新日期 + 添加市场后缀
        """
        db_path = self.data_dir / "风控部债券池.accdb"
        
        # 读取Access数据库
        reader = AccessDatabaseReader(db_path)
        df = reader.read_table("风控部债券池")
        
        # 清洗发行人名称（去除首尾空格）
        if '发行人名称' in df.columns:
            df['发行人名称'] = df['发行人名称'].str.strip()
        
        # 转换日期类型
        df['日期'] = pd.to_datetime(df['日期'])
        
        # 筛选最新日期的数据
        latest_date = df['日期'].max()
        df = df[df['日期'] == latest_date].copy()
        
        logger.info(f"  最新日期: {latest_date.date()}, {len(df)} 条记录")
        
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
        逻辑: 直接读取Excel文件
        """
        virtual_file = self.data_dir / "风控部债券池_主体_虚拟添加.xlsx"
        
        if not virtual_file.exists():
            logger.warning(f"  虚拟添加文件不存在: {virtual_file}")
            return pd.DataFrame(columns=['变动日期', '发行人名称', '主体池', '备注'])
        
        try:
            df = pd.read_excel(virtual_file)
            
            # 清洗发行人名称（去除首尾空格）
            if '发行人名称' in df.columns:
                df['发行人名称'] = df['发行人名称'].str.strip()
            
            logger.info(f"  虚拟添加主体: {len(df)} 条记录")
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
        """
        # 读取标准日期表
        date_file = self.data_dir / "标准日期表.xlsx"
        df_dates = pd.read_excel(date_file, sheet_name="标准日期表")
        df_dates['日期'] = pd.to_datetime(df_dates['日期'])
        df_dates = df_dates.sort_values('日期')
        
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
        # 优化：只取标准日期表中 >= 最早变动日期 且 <= 最晚日期的范围
        min_change_date = df_virtual['变动日期'].min()
        max_date_in_table = df_dates['日期'].max()
        
        df_dates_filtered = df_dates[
            (df_dates['日期'] >= min_change_date) &
            (df_dates['日期'] <= max_date_in_table)
        ].copy()
        
        logger.info(f"  日期范围: {min_change_date.date()} 到 {max_date_in_table.date()}，共{len(df_dates_filtered)}天")
        
        # 使用向量化操作优化
        results = []
        for _, row in df_virtual.iterrows():
            change_date = row['变动日期']
            valid_dates = df_dates_filtered[df_dates_filtered['日期'] >= change_date]
            
            if len(valid_dates) > 0:
                temp_df = valid_dates[['日期']].copy()
                temp_df['发行人名称'] = row['发行人名称']
                temp_df['主体池'] = row['主体池']
                results.append(temp_df)
        
        if len(results) == 0:
            logger.info(f"  虚拟添加每日展开: 0 条记录")
            return pd.DataFrame(columns=['日期', '发行人名称', '主体池'])
        
        df_result = pd.concat(results, ignore_index=True)
        logger.info(f"  虚拟添加每日展开: {len(df_result)} 条记录（{len(df_virtual)}个主体）")
        
        return df_result
    
    def query_issuer_pool(self) -> pd.DataFrame:
        """
        查询4: 风控部债券池_主体
        数据源: 原始风控部债券池_主体（最新日期） + 虚拟添加（非每日）
        逻辑: 合并后添加Wind代码
        
        注意：这里只需要当前日期的主体池快照，不是每日展开
        """
        # 获取原始主体池（已经是最新日期的数据）
        df_original = self.cache.get('原始风控部债券池_主体')
        if df_original is None:
            df_original = self.query_original_issuer_pool()
        
        # 获取虚拟添加（非每日，只取需要添加的主体）
        df_virtual = self.cache.get('风控部债券池_主体_虚拟添加')
        if df_virtual is None:
            df_virtual = self.query_virtual_issuer_addition()
        
        # 如果有虚拟添加数据，需要转换为与原始数据相同的格式
        if len(df_virtual) > 0:
            # 获取原始数据的日期（应该是最新日期）
            latest_date = df_original['日期'].max() if len(df_original) > 0 else pd.Timestamp.now()
            
            # 将虚拟添加数据转换为相同格式
            df_virtual_formatted = df_virtual[['发行人名称', '主体池']].copy()
            df_virtual_formatted['日期'] = latest_date
            
            # 合并
            df = pd.concat([df_original, df_virtual_formatted], ignore_index=True)
        else:
            df = df_original.copy()
        
        # 去重（同一日期同一发行人只保留一条）
        df = df.drop_duplicates(subset=['日期', '发行人名称'], keep='first')
        
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
        file_path = self.data_dir / "净资产.xlsx"
        
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
        date_file = self.data_dir / "标准日期表.xlsx"
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
