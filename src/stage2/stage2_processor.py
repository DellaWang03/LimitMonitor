"""
阶段2处理器: 限额监控 - 高风险行业/省份、地域集中度、高收益债券
负责处理高风险监控、地域集中度、城投集中度、高收益债券等
"""

import json
import pandas as pd
import numpy as np
from pathlib import Path
from loguru import logger
from typing import Dict, Optional, Any
import zipfile
import xml.etree.ElementTree as ET
from ..common.financial_tool_pool import (
    build_financial_tool_pool_sets,
    load_financial_tool_pool,
    row_in_financial_tool_pool,
)
from ..common.security_code_normalizer import normalize_security_code_series
from ..utils.limit_config_loader import load_limit_config


SOURCE_ROW_ID_COL = '_源行号'
_EMPTY_TEXT_VALUES = {'', 'nan', 'none', 'nat', '<na>', 'null'}


def _clean_text_value(value: Any) -> str:
    if pd.isna(value):
        return ''
    text = str(value).strip()
    return '' if text.lower() in _EMPTY_TEXT_VALUES else text


def _first_non_empty(series: pd.Series) -> str:
    for value in series:
        text = _clean_text_value(value)
        if text:
            return text
    return ''


def _build_penetrate_isin_type_map_keep_last(df: pd.DataFrame) -> Dict[str, str]:
    """构造 ISIN -> 类型 映射；重复 ISIN 按配置表中靠后的记录覆盖。"""
    if df is None or df.empty:
        return {}

    isin_col = None
    if 'ISIN代码' in df.columns:
        isin_col = 'ISIN代码'
    elif 'ISIN码' in df.columns:
        isin_col = 'ISIN码'
    if isin_col is None or '类型' not in df.columns:
        return {}

    mapping = {}
    for _, row in df.iterrows():
        type_value = str(row.get('类型', '')).strip()
        raw_isin = row.get(isin_col)
        if pd.notna(raw_isin):
            isin = str(raw_isin).strip()
            if isin and isin.lower() not in ('nan', 'none', 'nat') and type_value:
                mapping[isin] = type_value
    return mapping


def _lookup_high_yield_limit(name: Any, default_limit: float, category_limits: Dict[str, float]) -> float:
    key = _clean_text_value(name)
    if key and key in category_limits:
        return float(category_limits[key])
    return float(default_limit)


class Stage2Processor:
    """阶段2处理器"""
    
    def __init__(self, data_dir: Path, output_dir: Path, stage0_output_dir: Path, stage1_output_dir: Path, config: Any = None):
        """
        初始化处理器
        
        Args:
            data_dir: 数据源目录（local 时使用；migration 时由 config 解析路径）
            output_dir: 输出目录
            stage0_output_dir: 阶段0输出目录
            stage1_output_dir: 阶段1输出目录
            config: ConfigLoader，用于 get_data_file_path 路径 profile 切换
        """
        self.data_dir = Path(data_dir)
        self.output_dir = Path(output_dir)
        self.stage0_output_dir = Path(stage0_output_dir)
        self.stage1_output_dir = Path(stage1_output_dir)
        self.config = config
        self.cache = {}  # 查询结果缓存
        
        # 确保输出目录存在
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"阶段2处理器初始化")
        logger.info(f"  数据源: {self.data_dir}")
        logger.info(f"  输出目录: {self.output_dir}")
        logger.info(f"  阶段0输出: {self.stage0_output_dir}")
        logger.info(f"  阶段1输出: {self.stage1_output_dir}")
    
    def _data_file_path(self, file_name: str) -> Path:
        """按当前 profile 返回数据源文件路径。"""
        if self.config is not None and hasattr(self.config, "get_data_file_path"):
            return self.config.get_data_file_path(file_name)
        return self.data_dir / file_name

    def _validate_source_row_id(self, df: pd.DataFrame, table_name: str) -> None:
        """校验 Stage1 中间表带有唯一源行号，避免 Stage2 旧键 join 展开。"""
        if SOURCE_ROW_ID_COL not in df.columns:
            raise KeyError(
                f"{table_name} 缺少 {SOURCE_ROW_ID_COL}，请先重跑 Stage1 后再运行 Stage2"
            )
        if df[SOURCE_ROW_ID_COL].isna().any():
            raise ValueError(f"{table_name} 的 {SOURCE_ROW_ID_COL} 存在空值")
        duplicated = df[df[SOURCE_ROW_ID_COL].duplicated(keep=False)]
        if not duplicated.empty:
            sample_ids = duplicated[SOURCE_ROW_ID_COL].drop_duplicates().head(5).tolist()
            raise ValueError(f"{table_name} 的 {SOURCE_ROW_ID_COL} 不唯一，示例: {sample_ids}")
    
    def process_all(self) -> Dict[str, pd.DataFrame]:
        """
        执行所有阶段2查询
        
        Returns:
            查询结果字典
        """
        results = {}

        logger.info("\n" + "=" * 80)
        logger.info("开始处理阶段2")
        logger.info("=" * 80)

        # 从 Stage1 输出推断业务日期
        ref_file = self.stage1_output_dir / "限额明细_债券持仓明细表_信用债1_2.xlsx"
        if not ref_file.exists():
            raise FileNotFoundError(f"未找到Stage1输出，无法推断 business_date: {ref_file}")

        df_ref = pd.read_excel(ref_file, usecols=['日期'])
        business_date_series = pd.to_datetime(df_ref['日期'], errors='coerce')
        business_date = business_date_series.max()
        if pd.isna(business_date):
            raise ValueError(f"Stage1输出中的 '日期' 列无法解析出有效 business_date: {ref_file}")
        self._business_date = pd.Timestamp(business_date)
        logger.info(f"业务日期（来自Stage1输出）: {self._business_date.date()}")

        # === 第1层：加载配置和阶段1数据 ===
        logger.info("\n【第1层】加载配置和基础数据")
        logger.info("=" * 80)

        # 1.1 加载高风险配置
        logger.info("\n执行查询: 高风险行业")
        df_high_risk_industry = self.query_high_risk_industry()
        results['高风险行业'] = df_high_risk_industry
        self.cache['高风险行业'] = df_high_risk_industry
        logger.info(f"✓ {len(df_high_risk_industry)} 行")
        
        logger.info("\n执行查询: 高风险省份")
        df_high_risk_province = self.query_high_risk_province()
        results['高风险省份'] = df_high_risk_province
        self.cache['高风险省份'] = df_high_risk_province
        logger.info(f"✓ {len(df_high_risk_province)} 行")
        
        logger.info("\n执行查询: 高风险集中度限额")
        df_high_risk_limit = self.query_high_risk_concentration_limit()
        results['高风险限额'] = df_high_risk_limit
        self.cache['高风险限额'] = df_high_risk_limit
        logger.info(f"✓ {len(df_high_risk_limit)} 行")
        
        logger.info("\n执行查询: 地域集中度限额(含城投)")
        df_region_limit = self.query_region_concentration_limit()
        results['地域集中度限额(含城投)'] = df_region_limit
        self.cache['地域集中度限额(含城投)'] = df_region_limit
        logger.info(f"✓ {len(df_region_limit)} 行")
        
        logger.info("\n执行查询: 金融工具池设置")
        df_tool_pool = self.query_financial_tool_pool()
        results['金融工具池设置'] = df_tool_pool
        self.cache['金融工具池设置'] = df_tool_pool
        logger.info(f"✓ {len(df_tool_pool)} 行")
        
        logger.info("\n执行查询: ISIN码映射表")
        df_isin = self.query_isin_mapping()
        self.cache['ISIN码映射'] = df_isin
        logger.info(f"✓ {len(df_isin)} 行")
        
        logger.info("\n执行查询: 穿透高收益债券表")
        df_penetrate = self.query_penetrate_high_yield()
        self.cache['穿透高收益债券'] = df_penetrate
        logger.info(f"✓ {len(df_penetrate)} 行")
        
        # 1.2 加载阶段1数据
        logger.info("\n执行查询: 债券持仓明细表_信用债（引用阶段1）")
        df_credit = self.query_bond_position_credit()
        results['债券持仓明细表_信用债'] = df_credit
        self.cache['债券持仓明细表_信用债'] = df_credit
        logger.info(f"✓ {len(df_credit)} 行")
        
        logger.info("\n执行查询: 债券持仓明细表_信用债_合并风险限额相关（引用阶段1）")
        df_credit_merged = self.query_bond_position_credit_merged()
        results['债券持仓明细表_信用债_合并风险限额相关'] = df_credit_merged
        self.cache['债券持仓明细表_信用债_合并风险限额相关'] = df_credit_merged
        logger.info(f"✓ {len(df_credit_merged)} 行")
        
        logger.info("\n执行查询: 债券持仓表_核算系统（与M一致：限额/债券持仓表.xlsx）")
        df_accounting = self.query_bond_position_accounting()
        self.cache['债券持仓表_核算系统'] = df_accounting
        logger.info(f"✓ {len(df_accounting)} 行")
        
        # === 第2层：计算各类总持仓 ===
        logger.info("\n【第2层】计算各类总持仓")
        logger.info("=" * 80)
        
        logger.info("\n执行查询: 信用债总持仓")
        df_total_credit = self.query_total_credit_position()
        results['信用债总持仓'] = df_total_credit
        self.cache['信用债总持仓'] = df_total_credit
        logger.info(f"✓ {len(df_total_credit)} 行")
        
        logger.info("\n执行查询: 单一地域总持仓")
        df_region_pos = self.query_single_region_total_position()
        results['单一地域总持仓'] = df_region_pos
        self.cache['单一地域总持仓'] = df_region_pos
        logger.info(f"✓ {len(df_region_pos)} 行")
        
        logger.info("\n执行查询: 单一地域城投总持仓")
        df_citybond_pos = self.query_single_region_citybond_position()
        results['单一地域城投总持仓'] = df_citybond_pos
        self.cache['单一地域城投总持仓'] = df_citybond_pos
        logger.info(f"✓ {len(df_citybond_pos)} 行")
        
        logger.info("\n执行查询: 高风险行业总持仓")
        df_high_industry_pos = self.query_high_risk_industry_position()
        results['高风险行业总持仓'] = df_high_industry_pos
        self.cache['高风险行业总持仓'] = df_high_industry_pos
        logger.info(f"✓ {len(df_high_industry_pos)} 行")
        
        logger.info("\n执行查询: 高风险行业总持仓_2")
        df_high_industry_pos_2 = self.query_high_risk_industry_position_detail()
        results['高风险行业总持仓_2'] = df_high_industry_pos_2
        self.cache['高风险行业总持仓_2'] = df_high_industry_pos_2
        logger.info(f"✓ {len(df_high_industry_pos_2)} 行")
        
        logger.info("\n执行查询: 高风险省份总持仓")
        df_high_province_pos = self.query_high_risk_province_position()
        results['高风险省份总持仓'] = df_high_province_pos
        self.cache['高风险省份总持仓'] = df_high_province_pos
        logger.info(f"✓ {len(df_high_province_pos)} 行")
        
        logger.info("\n执行查询: 高风险省份总持仓_2")
        df_high_province_pos_2 = self.query_high_risk_province_position_detail()
        results['高风险省份总持仓_2'] = df_high_province_pos_2
        self.cache['高风险省份总持仓_2'] = df_high_province_pos_2
        logger.info(f"✓ {len(df_high_province_pos_2)} 行")
        
        # === 第3层：生成输出表 ===
        logger.info("\n【第3层】生成输出表")
        logger.info("=" * 80)
        
        logger.info("\n执行查询: 限额明细_债券持仓明细表_信用债2")
        df_credit_detail_2 = self.query_credit_bond_detail_2()
        results['限额明细_债券持仓明细表_信用债2'] = df_credit_detail_2
        self.cache['限额明细_债券持仓明细表_信用债2'] = df_credit_detail_2
        logger.info(f"✓ {len(df_credit_detail_2)} 行")
        
        logger.info("\n执行查询: 限额明细_高风险行业")
        df_high_industry_detail = self.query_high_risk_industry_detail()
        results['限额明细_高风险行业'] = df_high_industry_detail
        self.cache['限额明细_高风险行业'] = df_high_industry_detail
        logger.info(f"✓ {len(df_high_industry_detail)} 行")
        
        logger.info("\n执行查询: 限额明细_高风险行业_2")
        df_high_industry_detail_2 = self.query_high_risk_industry_detail_2()
        results['限额明细_高风险行业_2'] = df_high_industry_detail_2
        self.cache['限额明细_高风险行业_2'] = df_high_industry_detail_2
        logger.info(f"✓ {len(df_high_industry_detail_2)} 行")
        
        logger.info("\n执行查询: 限额明细_高风险省份")
        df_high_province_detail = self.query_high_risk_province_detail()
        results['限额明细_高风险省份'] = df_high_province_detail
        self.cache['限额明细_高风险省份'] = df_high_province_detail
        logger.info(f"✓ {len(df_high_province_detail)} 行")
        
        logger.info("\n执行查询: 限额明细_高风险省份2")
        df_high_province_detail_2 = self.query_high_risk_province_detail_2()
        results['限额明细_高风险省份2'] = df_high_province_detail_2
        self.cache['限额明细_高风险省份2'] = df_high_province_detail_2
        logger.info(f"✓ {len(df_high_province_detail_2)} 行")
        
        logger.info("\n执行查询: 限额明细_地域集中度限额(含城投)")
        df_region_detail = self.query_region_concentration_detail()
        results['限额明细_地域集中度限额(含城投)'] = df_region_detail
        self.cache['限额明细_地域集中度限额(含城投)'] = df_region_detail
        logger.info(f"✓ {len(df_region_detail)} 行")
        
        logger.info("\n执行查询: 限额明细_高收益")
        df_high_yield = self.query_high_yield_detail()
        results['限额明细_高收益'] = df_high_yield
        self.cache['限额明细_高收益'] = df_high_yield
        logger.info(f"✓ {len(df_high_yield)} 行")
        
        logger.info("\n执行查询: 限额明细_高收益_投资本金规模")
        df_high_yield_capital = self.query_high_yield_capital()
        results['限额明细_高收益_投资本金规模'] = df_high_yield_capital
        self.cache['限额明细_高收益_投资本金规模'] = df_high_yield_capital
        logger.info(f"✓ {len(df_high_yield_capital)} 行")
        
        # === 输出所有表格 ===
        logger.info("\n【输出】保存所有查询结果")
        logger.info("=" * 80)
        
        for name, df in results.items():
            output_path = self.output_dir / f"{name}.xlsx"
            
            # 检查文件是否已存在
            file_exists = output_path.exists()
            action = "覆盖" if file_exists else "新建"
            
            # 保存（会自动覆盖已存在的文件）
            df.to_excel(output_path, index=False)
            logger.info(f"  ✓ {action}: {name} ({len(df)} 行)")
        
        logger.info("\n" + "=" * 80)
        logger.info("阶段2处理完成")
        logger.info("=" * 80)
        logger.info(f"  输出目录: {self.output_dir}")
        logger.info(f"  输出表格数: {len(results)}")
        
        return results
    
    # ========================================================================
    # 配置加载方法
    # ========================================================================
    
    def query_high_risk_industry(self) -> pd.DataFrame:
        """
        查询: 高风险行业表
        数据源: 限额配置_当前.xlsx
        """
        business_date = getattr(self, '_business_date', None)
        df = load_limit_config(
            sheet_name="高风险行业表",
            business_date=business_date,
            config=self.config,
            inject_date=True,
        )

        # 数据清洗
        df['行业名称'] = df['行业名称'].astype(str).str.strip()
        df['行业类别'] = df['行业类别'].astype(str).str.strip()

        # 去重（按日期和行业名称）
        df = df.drop_duplicates(subset=['日期', '行业名称'], keep='first')

        logger.info(f"  高风险行业表: {len(df)} 行, {df['行业名称'].nunique()} 个唯一行业")
        return df

    def query_high_risk_province(self) -> pd.DataFrame:
        """
        查询: 高风险省份表
        数据源: 限额配置_当前.xlsx
        """
        from ..common import ProvinceNormalizer

        business_date = getattr(self, '_business_date', None)
        df = load_limit_config(
            sheet_name="高风险省份表",
            business_date=business_date,
            config=self.config,
            inject_date=True,
        )

        # 数据清洗
        df['省份名称'] = df['省份名称'].astype(str).str.strip()
        df['省份类别'] = df['省份类别'].astype(str).str.strip()

        # 应用省份标准化（直接覆盖原字段）
        df = ProvinceNormalizer.add_normalized_column(
            df,
            source_column='省份名称',
            target_column='省份名称'
        )

        # 去重（按日期和省份名称）
        df = df.drop_duplicates(subset=['日期', '省份名称'], keep='first')

        logger.info(f"  高风险省份表: {len(df)} 行, {df['省份名称'].nunique()} 个唯一省份")
        return df

    def query_high_risk_concentration_limit(self) -> pd.DataFrame:
        """
        查询: 高风险集中度限额
        数据源: 限额配置_当前.xlsx
        """
        business_date = getattr(self, '_business_date', None)
        df = load_limit_config(
            sheet_name="高风险集中度限额",
            business_date=business_date,
            config=self.config,
            inject_date=True,
        )

        logger.info(f"  高风险集中度限额: {len(df)} 行")
        return df

    def query_region_concentration_limit(self) -> pd.DataFrame:
        """
        查询: 地域集中度限额(含城投)
        数据源: 限额配置_当前.xlsx -> 单一省份限额
        """
        from ..common import ProvinceNormalizer

        business_date = getattr(self, '_business_date', None)
        df = load_limit_config(
            sheet_name="单一省份限额",
            business_date=business_date,
            config=self.config,
            inject_date=True,
        )

        # 数据清洗
        df['指标名称'] = df['指标名称'].astype(str).str.strip()

        # 标准化省份名称，与持仓数据（上海市/北京市…）保持一致
        # 直辖市在配置表中以短格式存储（上海/北京/天津/重庆），必须转为长格式才能正确 join
        df = ProvinceNormalizer.add_normalized_column(
            df,
            source_column='指标名称',
            target_column='指标名称',
        )

        logger.info(f"  地域集中度限额: {len(df)} 行, {df['指标名称'].nunique()} 个省份/地区")
        return df
    
    def query_isin_mapping(self) -> pd.DataFrame:
        """
        查询: ISIN码映射表
        数据源: 统计报表底稿2_债券SPPI.xlsx → 债券_含穿透持仓
        """
        file_path = self._data_file_path("统计报表底稿2_债券SPPI.xlsx")
        df = pd.read_excel(file_path, sheet_name="债券_含穿透持仓")
        
        # 只保留资产代码和ISIN码，并去重
        df_isin = df[['资产代码', 'ISIN码']].drop_duplicates(subset=['资产代码'], keep='first')
        
        logger.info(f"  ISIN码映射表: {len(df_isin)} 行, ISIN码非空 {df_isin['ISIN码'].notna().sum()} 个")
        return df_isin
    
    def _parse_damaged_excel(self, file_path: Path) -> pd.DataFrame:
        """
        手动解析损坏的Excel文件（样式表损坏但数据完好）
        通过解析ZIP内的XML文件来提取数据
        动态检测工作表名称（sheet0.xml、sheet1.xml等）
        """
        try:
            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                # 1. 读取共享字符串表
                with zip_ref.open('xl/sharedStrings.xml') as f:
                    tree = ET.parse(f)
                    root = tree.getroot()
                    ns = {'main': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
                    strings = []
                    for si in root.findall('.//main:si', ns):
                        t = si.find('.//main:t', ns)
                        if t is not None and t.text:
                            strings.append(t.text)
                
                # 2. 动态查找第一个工作表
                worksheet_files = [name for name in zip_ref.namelist() 
                                  if name.startswith('xl/worksheets/sheet') and name.endswith('.xml')]
                
                if not worksheet_files:
                    logger.error(f"手动解析Excel失败: 未找到工作表文件")
                    return pd.DataFrame()
                
                # 按名称排序，使用第一个工作表
                worksheet_files.sort()
                sheet_path = worksheet_files[0]
                logger.info(f"    使用工作表: {sheet_path}")
                
                # 3. 读取工作表数据
                with zip_ref.open(sheet_path) as f:
                    tree = ET.parse(f)
                    root = tree.getroot()
                    rows = root.findall('.//main:row', ns)
                    
                    data = []
                    for row in rows:
                        cells = row.findall('.//main:c', ns)
                        row_data = []
                        for cell in cells:
                            cell_type = cell.get('t', 'n')
                            v = cell.find('.//main:v', ns)
                            if v is not None and v.text:
                                if cell_type == 's':  # 字符串类型，从共享字符串表查找
                                    idx = int(v.text)
                                    if idx < len(strings):
                                        row_data.append(strings[idx])
                                else:
                                    row_data.append(v.text)
                            else:
                                row_data.append(None)
                        if row_data:  # 跳过空行
                            data.append(row_data)
                    
                    if len(data) > 0:
                        # 第一行作为列名
                        df = pd.DataFrame(data[1:], columns=data[0])
                        logger.info(f"    手动解析成功: {len(df)} 行, {len(df.columns)} 列")
                        return df
                    
        except Exception as e:
            logger.error(f"手动解析Excel失败: {e}")
        
        return pd.DataFrame()
    
    def query_financial_tool_pool(self) -> pd.DataFrame:
        """
        查询: 金融工具池设置（可转债白名单）
        数据源: 金融工具池设置.xlsx
        注意：该文件样式表损坏，使用手动XML解析
        
        重要：与PBI M-code保持一致
        - 只筛选"品种" = "可转债"的记录
        - 保留"代码"和"简称"列（同时支持代码匹配和简称匹配，提高兼容性）
        """
        file_path = self._data_file_path("金融工具池设置.xlsx")
        return load_financial_tool_pool(file_path, logger=logger)
    
    def query_penetrate_high_yield(self) -> pd.DataFrame:
        """
        查询: 穿透高收益债券表
        数据源: 限额配置_当前.xlsx
        """
        df = load_limit_config(
            sheet_name="穿透高收益债券",
            business_date=None,
            config=self.config,
            inject_date=False,
        )

        logger.info(f"  穿透高收益债券表: {len(df)} 行")
        return df
    
    def query_bond_position_credit(self) -> pd.DataFrame:
        """
        查询: 债券持仓明细表_信用债（引用阶段1）
        """
        file_path = self.stage1_output_dir / "债券持仓明细表_信用债.xlsx"
        df = pd.read_excel(file_path)
        
        # 日期转换
        if '日期' in df.columns:
            df['日期'] = pd.to_datetime(df['日期'])
        self._validate_source_row_id(df, '债券持仓明细表_信用债')
        
        logger.info(f"  债券持仓明细表_信用债: {len(df)} 行")
        return df
    
    def query_bond_position_credit_merged(self) -> pd.DataFrame:
        """
        查询: 债券持仓明细表_信用债_合并风险限额相关（引用阶段1）
        """
        file_path = self.stage1_output_dir / "债券持仓明细表_信用债_合并风险限额相关.xlsx"
        df = pd.read_excel(file_path)
        
        # 日期转换
        if '日期' in df.columns:
            df['日期'] = pd.to_datetime(df['日期'])
        self._validate_source_row_id(df, '债券持仓明细表_信用债_合并风险限额相关')
        
        logger.info(f"  债券持仓明细表_信用债_合并风险限额相关: {len(df)} 行")
        return df
    
    def query_bond_position_accounting(self) -> pd.DataFrame:
        """
        查询: 债券持仓表_核算系统
        与 M 代码严格一致：读限额/债券持仓表.xlsx（与 M 的核算系统表同源），按核算日期筛选。
        M 代码: 阶段2_query.md 第1077-1138行
        """
        df_credit = self.cache.get('债券持仓明细表_信用债')
        if df_credit is None or len(df_credit) == 0:
            logger.warning("  债券持仓表_核算系统: 依赖债券持仓明细表_信用债，请先加载")
            return pd.DataFrame()
        
        # 核算日期 = 债券持仓明细表_信用债 的唯一日期（M: 核算日期）
        accounting_dates = df_credit[['日期']].drop_duplicates()
        accounting_dates = accounting_dates.dropna(subset=['日期'])
        if len(accounting_dates) == 0:
            logger.warning("  债券持仓表_核算系统: 核算日期为空")
            return pd.DataFrame()
        
        file_path = self._data_file_path("债券持仓表.xlsx")
        if not file_path.exists():
            logger.warning(f"  债券持仓表_核算系统: 文件不存在 {file_path}")
            return pd.DataFrame()
        
        xls = pd.ExcelFile(file_path)
        sheet_name = "债券持仓表"
        if sheet_name not in xls.sheet_names:
            sheet_name = xls.sheet_names[0] if xls.sheet_names else None
        if sheet_name is None:
            logger.warning("  债券持仓表_核算系统: 无可用 Sheet")
            return pd.DataFrame()
        
        df = pd.read_excel(file_path, sheet_name=sheet_name)
        if '日期' not in df.columns:
            logger.warning("  债券持仓表_核算系统: 缺少列 日期")
            return pd.DataFrame()
        
        df['日期'] = pd.to_datetime(df['日期'], errors='coerce')
        accounting_dates['日期'] = pd.to_datetime(accounting_dates['日期'])
        
        # 与核算日期左连接，只保留核算日期存在的行（M: 筛选 核算日期.日期 <> null）
        df = df.merge(
            accounting_dates.rename(columns={'日期': '核算日期.日期'}),
            left_on='日期',
            right_on='核算日期.日期',
            how='inner'
        )
        df = df.drop(columns=['核算日期.日期'], errors='ignore')
        
        logger.info(f"  债券持仓表_核算系统: {len(df)} 行（数据源: {file_path.name}）")
        return df
    
    def query_penetrate_high_yield_capital(self) -> pd.DataFrame:
        """
        穿透高收益_投资本金规模
        M 代码: 阶段2_query.md 第632-659行
        源 = 债券持仓明细表（M 中即统计报表底稿2_债券SPPI 债券_含穿透持仓），
        与穿透高收益债券按 ISIN码 Inner Join，选列并重命名。
        """
        df_penetrate = self.cache.get('穿透高收益债券')
        if df_penetrate is None or len(df_penetrate) == 0:
            logger.warning("  穿透高收益_投资本金规模: 依赖穿透高收益债券")
            return pd.DataFrame()
        
        file_path = self._data_file_path("统计报表底稿2_债券SPPI.xlsx")
        if not file_path.exists():
            logger.warning(f"  穿透高收益_投资本金规模: 文件不存在 {file_path}")
            return pd.DataFrame()
        
        df_src = pd.read_excel(file_path, sheet_name="债券_含穿透持仓")
        if '日期' in df_src.columns:
            df_src['日期'] = pd.to_datetime(df_src['日期'], errors='coerce')
        
        need_cols = ['日期', 'ISIN码', '资产代码', '资产名称', '内部证券账户名称', '库存数量(万)_PR', '本币成本']
        missing = [c for c in need_cols if c not in df_src.columns]
        if missing:
            logger.warning(f"  穿透高收益_投资本金规模: 缺少列 {missing}")
            return pd.DataFrame()
        
        df_src = df_src[need_cols].copy()
        df_src = df_src.dropna(subset=['ISIN码'])
        
        isin_col_penetrate = 'ISIN代码' if 'ISIN代码' in df_penetrate.columns else 'ISIN码'
        if isin_col_penetrate not in df_penetrate.columns:
            logger.warning("  穿透高收益_投资本金规模: 穿透表无 ISIN 列")
            return pd.DataFrame()
        
        penetrate_isin = df_penetrate[[isin_col_penetrate]].drop_duplicates(keep='last')
        penetrate_isin = penetrate_isin.dropna(subset=[isin_col_penetrate])
        penetrate_isin.columns = ['ISIN码']
        
        df = df_src.merge(penetrate_isin, on='ISIN码', how='inner')
        df = df.rename(columns={
            '内部证券账户名称': '账户',
            '资产名称': '简称',
            '资产代码': '代码'
        })
        df['持仓面额(元)'] = df['库存数量(万)_PR'] * 10000
        df = df.drop(columns=['库存数量(万)_PR'], errors='ignore')
        df = df.rename(columns={'本币成本': '全价成本(元)'})
        
        out_cols = ['日期', '账户', '简称', '代码', '持仓面额(元)', '全价成本(元)']
        df = df[[c for c in out_cols if c in df.columns]]
        
        logger.info(f"  穿透高收益_投资本金规模: {len(df)} 行")
        return df
    
    # ========================================================================
    # 总持仓计算方法（待实现）
    # ========================================================================
    
    def query_total_credit_position(self) -> pd.DataFrame:
        """
        信用债总持仓
        M-code: 按日期分组，对库存数量求和
        """
        df = self.cache.get('债券持仓明细表_信用债')
        if df is None:
            raise ValueError("债券持仓明细表_信用债未找到")
        
        # 按日期分组，求和
        result = df.groupby('日期').agg({
            '库存数量(万)_PR': 'sum'
        }).reset_index()
        
        result = result.rename(columns={'库存数量(万)_PR': '信用债总持仓_PR'})
        
        logger.info(f"  信用债总持仓: {len(result)} 行")
        return result
    
    def query_single_region_total_position(self) -> pd.DataFrame:
        """
        单一地域总持仓
        M-code: 按日期、省份分组，对库存数量求和
        """
        df = self.cache.get('债券持仓明细表_信用债')
        if df is None:
            raise ValueError("债券持仓明细表_信用债未找到")
        
        # 按日期、省份分组，求和
        result = df.groupby(['日期', '省份']).agg({
            '库存数量(万)_PR': 'sum'
        }).reset_index()
        
        result = result.rename(columns={'库存数量(万)_PR': '单一地域总持仓_PR'})
        
        # 关联公司净资产（用于后续计算集中度）
        df_net_asset = pd.read_excel(
            self.stage0_output_dir / "公司净资产_手工_每日.xlsx"
        )
        df_net_asset['日期'] = pd.to_datetime(df_net_asset['日期'])
        
        result = result.merge(
            df_net_asset[['日期', '公司净资产(万)']],
            on='日期',
            how='left'
        )
        
        # 计算地域集中度
        result['地域集中度'] = result['单一地域总持仓_PR'] / (result['公司净资产(万)'] * 1.2)
        
        logger.info(f"  单一地域总持仓: {len(result)} 行")
        return result
    
    def query_single_region_citybond_position(self) -> pd.DataFrame:
        """
        单一地域城投总持仓
        M-code: 筛选城投债，按日期、省份分组，对库存数量求和
        """
        df = self.cache.get('债券持仓明细表_信用债')
        if df is None:
            raise ValueError("债券持仓明细表_信用债未找到")
        
        # 筛选城投债
        df_citybond = df[df['债券类别'] == '城投债'].copy()
        
        # 按日期、省份分组，求和
        result = df_citybond.groupby(['日期', '省份']).agg({
            '库存数量(万)_PR': 'sum'
        }).reset_index()
        
        result = result.rename(columns={'库存数量(万)_PR': '单一地域城投总持仓_PR'})
        
        # 关联公司净资产
        df_net_asset = pd.read_excel(
            self.stage0_output_dir / "公司净资产_手工_每日.xlsx"
        )
        df_net_asset['日期'] = pd.to_datetime(df_net_asset['日期'])
        
        result = result.merge(
            df_net_asset[['日期', '公司净资产(万)']],
            on='日期',
            how='left'
        )
        
        # 计算城投地域集中度
        result['城投地域集中度'] = result['单一地域城投总持仓_PR'] / result['公司净资产(万)']
        
        logger.info(f"  单一地域城投总持仓: {len(result)} 行")
        return result
    
    def query_high_risk_industry_position(self) -> pd.DataFrame:
        """
        高风险行业总持仓
        M-code: 筛选高风险行业，按日期、行业类别分组，对库存数量求和
        """
        df = self.cache.get('债券持仓明细表_信用债_合并风险限额相关')
        if df is None:
            raise ValueError("债券持仓明细表_信用债_合并风险限额相关未找到")
        
        # 筛选高风险行业
        df_high_risk = df[df['行业类别'] == '高风险行业'].copy()
        
        # 按日期、行业类别分组，求和
        result = df_high_risk.groupby(['日期', '行业类别']).agg({
            '库存数量(万)_PR': 'sum'
        }).reset_index()
        
        result = result.rename(columns={'库存数量(万)_PR': '高风险行业总持仓_PR'})
        
        # 关联信用债总持仓
        df_total_credit = self.cache.get('信用债总持仓')
        if df_total_credit is not None:
            result = result.merge(
                df_total_credit,
                on='日期',
                how='left'
            )
        
        # 计算高风险行业集中度
        if '信用债总持仓_PR' in result.columns:
            result['高风险行业集中度'] = result['高风险行业总持仓_PR'] / result['信用债总持仓_PR']
        
        logger.info(f"  高风险行业总持仓: {len(result)} 行")
        return result
    
    def query_high_risk_industry_position_detail(self) -> pd.DataFrame:
        """
        高风险行业总持仓_2（明细）
        M-code: 筛选高风险行业，按日期、wind行业分组，对库存数量求和
        """
        df = self.cache.get('债券持仓明细表_信用债_合并风险限额相关')
        if df is None:
            raise ValueError("债券持仓明细表_信用债_合并风险限额相关未找到")
        
        # 筛选高风险行业
        df_high_risk = df[df['行业类别'] == '高风险行业'].copy()
        
        # 按日期、wind行业分组，求和
        result = df_high_risk.groupby(['日期', 'wind行业']).agg({
            '库存数量(万)_PR': 'sum'
        }).reset_index()
        
        result = result.rename(columns={'库存数量(万)_PR': '高风险行业总持仓_PR'})
        
        logger.info(f"  高风险行业总持仓_2: {len(result)} 行")
        return result
    
    def query_high_risk_province_position(self) -> pd.DataFrame:
        """
        高风险省份总持仓
        M-code: 筛选高风险省份，按日期、省份类别分组，对库存数量求和
        """
        df = self.cache.get('债券持仓明细表_信用债_合并风险限额相关')
        if df is None:
            raise ValueError("债券持仓明细表_信用债_合并风险限额相关未找到")
        
        # 筛选高风险省份
        df_high_risk = df[df['省份类别'] == '高风险省份'].copy()
        
        # 按日期、省份类别分组，求和
        result = df_high_risk.groupby(['日期', '省份类别']).agg({
            '库存数量(万)_PR': 'sum'
        }).reset_index()
        
        result = result.rename(columns={'库存数量(万)_PR': '高风险省份总持仓_PR'})
        
        # 关联公司净资产
        df_net_asset = pd.read_excel(
            self.stage0_output_dir / "公司净资产_手工_每日.xlsx"
        )
        df_net_asset['日期'] = pd.to_datetime(df_net_asset['日期'])
        
        result = result.merge(
            df_net_asset[['日期', '公司净资产(万)']],
            on='日期',
            how='left'
        )
        
        # 计算高风险省份集中度（分母 = 公司净资产 * 1.2）
        result['高风险省份集中度'] = result['高风险省份总持仓_PR'] / (result['公司净资产(万)'] * 1.2)
        
        logger.info(f"  高风险省份总持仓: {len(result)} 行")
        return result
    
    def query_high_risk_province_position_detail(self) -> pd.DataFrame:
        """
        高风险省份总持仓_2（明细）
        M-code: 筛选高风险省份，按日期、省份分组，对库存数量求和
        """
        df = self.cache.get('债券持仓明细表_信用债_合并风险限额相关')
        if df is None:
            raise ValueError("债券持仓明细表_信用债_合并风险限额相关未找到")
        
        # 筛选高风险省份
        df_high_risk = df[df['省份类别'] == '高风险省份'].copy()
        
        # 按日期、省份分组，求和
        result = df_high_risk.groupby(['日期', '省份']).agg({
            '库存数量(万)_PR': 'sum'
        }).reset_index()
        
        result = result.rename(columns={'库存数量(万)_PR': '高风险省份总持仓_PR'})
        
        logger.info(f"  高风险省份总持仓_2: {len(result)} 行")
        return result
    
    # ========================================================================
    # 输出表生成方法（待实现）
    # ========================================================================
    
    def query_credit_bond_detail_2(self) -> pd.DataFrame:
        """
        限额明细_债券持仓明细表_信用债2
        M-code: 核心明细表，包含地域集中度、城投集中度、高风险行业/省份集中度、超限判断
        注意：使用Stage1的债券持仓明细表_信用债（保留原始重复记录），以匹配Excel逻辑
        """
        logger.info(f"  开始生成信用债2明细表...")
        
        # 1. 读取Stage1的债券持仓明细表_信用债（保留原始重复记录）
        df = pd.read_excel(self.stage1_output_dir / "债券持仓明细表_信用债.xlsx")
        
        # 确保日期字段
        if '日期' in df.columns:
            df['日期'] = pd.to_datetime(df['日期'])
        self._validate_source_row_id(df, '债券持仓明细表_信用债')
        
        logger.info(f"    Stage1信用债: {len(df)} 行（保留原始重复记录）")
        
        # 2. 筛选账户（排除特定账户）
        # 注意：与原Excel保持一致，排除"做市交易部做市业务"账户
        # 高风险省份汇总表使用Stage1数据（包含做市业务），明细表排除做市业务
        df = df[
            ~df['内部证券账户名称'].str.contains('代申购代缴款', na=False) &
            (df['内部证券账户名称'] != '做市交易部做市业务')
        ].copy()
        logger.info(f"    筛选后: {len(df)} 行")
        
        # 3. 关联Stage1合并风险限额相关的计算字段（通过源行号关联）
        df_stage1_merged = self.cache.get('债券持仓明细表_信用债_合并风险限额相关')
        if df_stage1_merged is None:
            df_stage1_merged = self.query_bond_position_credit_merged()
        if df_stage1_merged is not None:
            self._validate_source_row_id(df_stage1_merged, '债券持仓明细表_信用债_合并风险限额相关')
            rows_before_calc_merge = len(df)

            # 用原业务字段做血缘一致性校验，实际关联只依赖源行号。
            lineage_check_cols = ['日期', '资产代码', '内部证券账户名称', '库存数量(万)_PR']

            # 选择Stage1合并后的计算字段
            stage1_calc_cols = [SOURCE_ROW_ID_COL] + lineage_check_cols + [
                '行业类别', '省份类别', '主体池', '债券池', '是否属于高收益',
                '中债隐含评级', '实际控制人名称_修正', '调整后实际控制人', '担保公司是否准入'
            ]
            existing_stage1_cols = [col for col in stage1_calc_cols if col in df_stage1_merged.columns]
            
            df = df.merge(
                df_stage1_merged[existing_stage1_cols],
                on=SOURCE_ROW_ID_COL,
                how='left',
                suffixes=('', '_s1calc'),
                validate='many_to_one',
                indicator='_stage1_calc_merge'
            )

            if len(df) != rows_before_calc_merge:
                raise ValueError(
                    "Stage2 关联Stage1计算字段后行数变化: "
                    f"{rows_before_calc_merge} -> {len(df)}"
                )

            missing_stage1_calc = (df['_stage1_calc_merge'] == 'left_only').sum()
            if missing_stage1_calc:
                raise ValueError(
                    f"Stage2 有 {missing_stage1_calc} 行信用债未匹配到合并风险限额相关源行"
                )
            df = df.drop(columns=['_stage1_calc_merge'])

            mismatches = []
            for col in lineage_check_cols:
                calc_col = f'{col}_s1calc'
                if calc_col not in df.columns:
                    continue
                if col == '日期':
                    left = pd.to_datetime(df[col], errors='coerce')
                    right = pd.to_datetime(df[calc_col], errors='coerce')
                    mismatch = ~((left == right) | (left.isna() & right.isna()))
                elif col == '库存数量(万)_PR':
                    left = pd.to_numeric(df[col], errors='coerce')
                    right = pd.to_numeric(df[calc_col], errors='coerce')
                    close = pd.Series(
                        np.isclose(left.fillna(0), right.fillna(0), rtol=0, atol=1e-6),
                        index=df.index
                    )
                    mismatch = ~((left.notna() & right.notna() & close) | (left.isna() & right.isna()))
                else:
                    left = df[col].astype(str).str.strip().replace({'nan': '', 'None': '', '<NA>': ''})
                    right = df[calc_col].astype(str).str.strip().replace({'nan': '', 'None': '', '<NA>': ''})
                    mismatch = left != right
                if mismatch.any():
                    mismatches.append(f"{col}: {int(mismatch.sum())} 行")
                df = df.drop(columns=[calc_col])
            if mismatches:
                raise ValueError(f"Stage2 源行号血缘校验失败: {mismatches}")
            
            # 用Stage1的计算字段覆盖原有字段
            for col in stage1_calc_cols:
                if col not in [SOURCE_ROW_ID_COL] + lineage_check_cols and f'{col}_s1calc' in df.columns:
                    df[col] = df[f'{col}_s1calc']
                    df = df.drop(columns=[f'{col}_s1calc'])
            
            logger.info(f"    ✓ 按{SOURCE_ROW_ID_COL}关联Stage1计算字段")
        
        # 2. 关联高风险行业配置（获取指标值）
        df_high_industry = self.cache.get('高风险行业')
        if df_high_industry is not None:
            df = df.merge(
                df_high_industry[['日期', '行业名称', '指标值']],
                left_on=['日期', 'wind行业'],
                right_on=['日期', '行业名称'],
                how='left'
            )
            df = df.drop(columns=['行业名称'], errors='ignore')
            df = df.rename(columns={'指标值': '高风险行业之和集中度限额指标值'})
        
        # 3. 关联高风险省份配置（获取指标值）
        df_high_province = self.cache.get('高风险省份')
        if df_high_province is not None:
            df = df.merge(
                df_high_province[['日期', '省份名称', '指标值']],
                left_on=['日期', '省份'],
                right_on=['日期', '省份名称'],
                how='left'
            )
            df = df.drop(columns=['省份名称'], errors='ignore')
            df = df.rename(columns={'指标值': '高风险省份之和集中度限额指标值'})
        
        # 4. 关联地域集中度限额
        df_region_limit = self.cache.get('地域集中度限额(含城投)')
        if df_region_limit is not None:
            df = df.merge(
                df_region_limit[['日期', '指标名称', '指标值_地域集中度限额', '指标值_城投集中度限额']],
                left_on=['日期', '省份'],
                right_on=['日期', '指标名称'],
                how='left'
            )
            df = df.drop(columns=['指标名称'], errors='ignore')
            # 重命名城投集中度限额
            df = df.rename(columns={'指标值_城投集中度限额': '指标值_城投集中度限额2'})
            
            # 根据是否城投债设置城投集中度限额
            df['指标值_城投集中度限额'] = df.apply(
                lambda row: row.get('指标值_城投集中度限额2') if row.get('是否城投债') == '是' else None,
                axis=1
            )
            df = df.drop(columns=['指标值_城投集中度限额2'], errors='ignore')
        
        # 5. 关联单一地域总持仓
        df_region_pos = self.cache.get('单一地域总持仓')
        if df_region_pos is not None:
            df = df.merge(
                df_region_pos[['日期', '省份', '单一地域总持仓_PR', '地域集中度']],
                on=['日期', '省份'],
                how='left'
            )
        
        # 6. 关联单一地域城投总持仓（只对城投债赋值）
        df_citybond_pos = self.cache.get('单一地域城投总持仓')
        if df_citybond_pos is not None:
            # 先关联所有记录
            df = df.merge(
                df_citybond_pos[['日期', '省份', '单一地域城投总持仓_PR', '城投地域集中度']],
                on=['日期', '省份'],
                how='left'
            )
            
            # 只对"债券类别"=='城投债'的记录保留城投地域集中度，其他设为NaN
            # 注意：只用"债券类别"判断，不使用"是否城投债"
            is_citybond = (df['债券类别'] == '城投债')
            df.loc[~is_citybond, '城投地域集中度'] = None
            df.loc[~is_citybond, '单一地域城投总持仓_PR'] = None
        
        # 7. 关联信用债总持仓
        df_total_credit = self.cache.get('信用债总持仓')
        if df_total_credit is not None:
            df = df.merge(
                df_total_credit,
                on='日期',
                how='left'
            )
        
        # 8. 关联公司净资产
        df_net_asset = pd.read_excel(
            self.stage0_output_dir / "公司净资产_手工_每日.xlsx"
        )
        df_net_asset['日期'] = pd.to_datetime(df_net_asset['日期'])
        df = df.merge(
            df_net_asset[['日期', '公司净资产(万)']],
            on='日期',
            how='left'
        )
        
        # 9. 关联高风险行业总持仓和集中度
        df_high_industry_pos = self.cache.get('高风险行业总持仓')
        if df_high_industry_pos is not None:
            df = df.merge(
                df_high_industry_pos[['日期', '高风险行业总持仓_PR', '高风险行业集中度']],
                on='日期',
                how='left'
            )
        
        # 10. 关联高风险省份总持仓和集中度
        df_high_province_pos = self.cache.get('高风险省份总持仓')
        if df_high_province_pos is not None:
            df = df.merge(
                df_high_province_pos[['日期', '高风险省份总持仓_PR', '高风险省份集中度']],
                on='日期',
                how='left'
            )
        
        # 11. 计算剩余额度
        # 地域集中度剩余额度
        # M 代码: (指标值_地域集中度限额 - 地域集中度) * 信用债总持仓_PR
        if all(col in df.columns for col in ['地域集中度', '指标值_地域集中度限额', '信用债总持仓_PR']):
            df['地域集中度剩余额度(万)'] = (
                (df['指标值_地域集中度限额'] - df['地域集中度']) * df['信用债总持仓_PR']
            )
        
        # 城投集中度剩余额度
        if all(col in df.columns for col in ['公司净资产(万)', '指标值_城投集中度限额', '单一地域城投总持仓_PR']):
            df['城投集中度剩余额度(万)'] = (
                df['公司净资产(万)'] * df['指标值_城投集中度限额'] - df['单一地域城投总持仓_PR']
            )
        
        # 高风险行业集中度剩余额度
        if all(col in df.columns for col in ['信用债总持仓_PR', '高风险行业之和集中度限额指标值', '高风险行业总持仓_PR']):
            df['高风险行业集中度剩余额度(万)'] = (
                df['信用债总持仓_PR'] * df['高风险行业之和集中度限额指标值'] - df['高风险行业总持仓_PR']
            )
        
        # 高风险省份集中度剩余额度
        # M 代码: (高风险省份之和集中度限额指标值 - 高风险省份集中度) * 信用债总持仓_PR
        if all(col in df.columns for col in ['高风险省份集中度', '高风险省份之和集中度限额指标值', '信用债总持仓_PR']):
            df['高风险省份集中度剩余额度(万)'] = (
                (df['高风险省份之和集中度限额指标值'] - df['高风险省份集中度']) * df['信用债总持仓_PR']
            )
        
        # 12. 判断是否超限
        df['高风险行业是否超限'] = df.apply(
            lambda row: '是' if pd.notna(row.get('高风险行业集中度剩余额度(万)')) and 
                                row.get('高风险行业集中度剩余额度(万)') < 0 else '否',
            axis=1
        )
        
        df['高风险省份是否超限'] = df.apply(
            lambda row: '是' if pd.notna(row.get('高风险省份集中度剩余额度(万)')) and 
                                row.get('高风险省份集中度剩余额度(万)') < 0 else '否',
            axis=1
        )
        
        df['地域集中度是否超限'] = df.apply(
            lambda row: '是' if pd.notna(row.get('地域集中度剩余额度(万)')) and 
                                row.get('地域集中度剩余额度(万)') < 0 else '否',
            axis=1
        )
        
        df['城投集中度是否超限'] = df.apply(
            lambda row: '是' if pd.notna(row.get('城投集中度剩余额度(万)')) and 
                                row.get('城投集中度剩余额度(万)') < 0 else '否',
            axis=1
        )
        
        # 综合判断是否超限
        df['是否超限'] = df.apply(
            lambda row: '是' if '是' in [
                row.get('高风险行业是否超限'),
                row.get('高风险省份是否超限'),
                row.get('地域集中度是否超限'),
                row.get('城投集中度是否超限')
            ] else '否',
            axis=1
        )
        
        # 12. 添加ISIN码（从SPPI表关联）
        df_isin = self.cache.get('ISIN码映射')
        if df_isin is not None and 'ISIN码' not in df.columns:
            df = df.merge(
                df_isin,
                on='资产代码',
                how='left'
            )
            logger.info(f"    ✓ 关联ISIN码: {df['ISIN码'].notna().sum()} 个非空")
        
        # 13. 选择输出列（根据Excel参考，字段名已与参考文件完全一致）
        output_cols = [
            '日期', 'ISIN码', '金融资产会计属性', '部门', '内部证券账户名称',
            '资产代码', '资产名称', '债券分类2', '债券类型1', '主证券代码', '主证券名称',
            '库存数量(万)_PR', '债券余额(亿)', '发行人类型', '债务主体', '债务主体wind代码',
            '调整后实际控制人', '担保人', '担保人wind代码', '是否城投债', '债券类别',
            'wind行业', '省份', '行业类别', '省份类别',
            '高风险行业之和集中度限额指标值', '高风险省份之和集中度限额指标值',
            '指标值_地域集中度限额', '指标值_城投集中度限额',
            '单一地域总持仓_PR', '地域集中度', '单一地域城投总持仓_PR', '城投地域集中度',
            '信用债总持仓_PR', '公司净资产(万)',
            '高风险行业总持仓_PR', '高风险行业集中度',
            '高风险省份总持仓_PR', '高风险省份集中度',
            '地域集中度剩余额度(万)', '城投集中度剩余额度(万)',
            '高风险行业集中度剩余额度(万)', '高风险省份集中度剩余额度(万)',
            '高风险行业是否超限', '高风险省份是否超限',
            '地域集中度是否超限', '城投集中度是否超限', '是否超限'
        ]
        
        # 只选择存在的列
        existing_cols = [col for col in output_cols if col in df.columns]
        df = df[existing_cols]
        
        # 14. 浮点数精度处理（修复与Excel的浮点数比较差异）
        numeric_cols = [
            '库存数量(万)_PR', '债券余额(亿)', '单一地域总持仓_PR', 
            '地域集中度', '单一地域城投总持仓_PR', '城投地域集中度',
            '信用债总持仓_PR', '公司净资产(万)',
            '高风险行业总持仓_PR', '高风险行业集中度',
            '高风险省份总持仓_PR', '高风险省份集中度',
            '地域集中度剩余额度(万)', '城投集中度剩余额度(万)',
            '高风险行业集中度剩余额度(万)', '高风险省份集中度剩余额度(万)',
            '高风险行业之和集中度限额指标值', '高风险省份之和集中度限额指标值',
            '指标值_地域集中度限额', '指标值_城投集中度限额'
        ]
        
        for col in numeric_cols:
            if col in df.columns:
                df[col] = df[col].round(4)  # 保留4位小数，与Excel一致
        
        logger.info(f"  信用债2明细表: {len(df)} 行 × {len(df.columns)} 列")
        return df
    
    def query_high_risk_industry_detail(self) -> pd.DataFrame:
        """
        限额明细_高风险行业（汇总表）
        M-code: 高风险行业的集中度、限额、剩余额度汇总
        """
        df_high_risk = self.cache.get('高风险行业')
        df_high_industry_pos = self.cache.get('高风险行业总持仓')
        
        if df_high_risk is None or df_high_industry_pos is None:
            return pd.DataFrame()
        
        # 从总持仓表获取最新日期
        latest_date = df_high_industry_pos['日期'].max()
        df_pos = df_high_industry_pos[df_high_industry_pos['日期'] == latest_date].copy()
        
        # 从配置表获取对应日期的指标值
        df = df_high_risk[['行业类别', '指标值', '日期']].drop_duplicates()
        
        # 关联总持仓数据
        df = df.merge(
            df_pos[['日期', '高风险行业总持仓_PR', '信用债总持仓_PR', '高风险行业集中度']],
            on='日期',
            how='inner'
        )
        
        # 如果inner join为空，使用配置表最新日期的指标值
        if len(df) == 0:
            df_config_latest = df_high_risk[df_high_risk['日期'] == df_high_risk['日期'].max()][['行业类别', '指标值']].drop_duplicates()
            df = df_pos.merge(df_config_latest, on='行业类别', how='left')
        
        # 计算限额和剩余额度
        df['高风险行业总持仓限额(万)'] = df['信用债总持仓_PR'] * df['指标值']
        df['高风险行业总持仓剩余额度(万)'] = df['高风险行业总持仓限额(万)'] - df['高风险行业总持仓_PR']
        
        # 添加"集中度"和"剩余额度"字段（与Power BI截图字段名一致）
        df['集中度'] = df['高风险行业集中度']
        df['剩余额度'] = df['高风险行业总持仓剩余额度(万)']
        
        logger.info(f"  限额明细_高风险行业: {len(df)} 行")
        return df
    
    def query_high_risk_industry_detail_2(self) -> pd.DataFrame:
        """
        限额明细_高风险行业_2（明细表）
        M-code: 按行业名称分组的持仓明细
        """
        df_high_risk = self.cache.get('高风险行业')
        df_high_industry_pos_2 = self.cache.get('高风险行业总持仓_2')
        
        if df_high_risk is None or df_high_industry_pos_2 is None:
            return pd.DataFrame()
        
        # 关联
        df = df_high_risk.merge(
            df_high_industry_pos_2,
            left_on=['行业名称', '日期'],
            right_on=['wind行业', '日期'],
            how='inner'
        )
        
        # 选择输出列
        df = df[['日期', 'wind行业', '行业类别', '高风险行业总持仓_PR']]
        df = df.rename(columns={'wind行业': '行业名称'})
        
        # 排序
        df = df.sort_values(['日期', '高风险行业总持仓_PR'], ascending=[True, False])
        
        logger.info(f"  限额明细_高风险行业_2: {len(df)} 行")
        return df
    
    def query_high_risk_province_detail(self) -> pd.DataFrame:
        """
        限额明细_高风险省份（汇总表）
        M-code: 高风险省份的集中度、限额、剩余额度汇总
        """
        df_high_risk = self.cache.get('高风险省份')
        df_high_province_pos = self.cache.get('高风险省份总持仓')
        
        if df_high_risk is None or df_high_province_pos is None:
            return pd.DataFrame()
        
        # 从总持仓表获取最新日期
        latest_date = df_high_province_pos['日期'].max()
        df_pos = df_high_province_pos[df_high_province_pos['日期'] == latest_date].copy()
        
        # 从配置表获取对应日期的指标值
        df = df_high_risk[['省份类别', '指标值', '日期']].drop_duplicates()
        
        # 关联总持仓数据
        df = df.merge(
            df_pos[['日期', '高风险省份总持仓_PR', '公司净资产(万)', '高风险省份集中度']],
            on='日期',
            how='inner'
        )
        
        # 如果inner join为空，使用配置表最新日期的指标值
        if len(df) == 0:
            df_config_latest = df_high_risk[df_high_risk['日期'] == df_high_risk['日期'].max()][['省份类别', '指标值']].drop_duplicates()
            df = df_pos.merge(df_config_latest, on='省份类别', how='left')
        
        # 重新排列列顺序
        output_cols = ['日期', '省份类别', '指标值', '高风险省份总持仓_PR', '公司净资产(万)', 
                       '高风险省份集中度']
        existing_cols = [col for col in output_cols if col in df.columns]
        df = df[existing_cols]
        
        # 计算限额和剩余额度（修正：分母=公司净资产*1.2）
        df['高风险省份总持仓限额(万)'] = df['公司净资产(万)'] * 1.2 * df['指标值']
        df['高风险省份总持仓剩余额度(万)'] = df['高风险省份总持仓限额(万)'] - df['高风险省份总持仓_PR']
        
        # 添加"集中度"和"剩余额度"字段（与Power BI截图字段名一致）
        df['集中度'] = df['高风险省份集中度']
        df['剩余额度'] = df['高风险省份总持仓剩余额度(万)']
        
        logger.info(f"  限额明细_高风险省份: {len(df)} 行")
        return df
    
    def query_high_risk_province_detail_2(self) -> pd.DataFrame:
        """
        限额明细_高风险省份2（明细表）
        M-code: 按省份名称分组的持仓明细
        """
        df_high_risk = self.cache.get('高风险省份')
        df_high_province_pos_2 = self.cache.get('高风险省份总持仓_2')
        
        if df_high_risk is None or df_high_province_pos_2 is None:
            return pd.DataFrame()
        
        # 关联
        df = df_high_risk.merge(
            df_high_province_pos_2,
            left_on=['省份名称', '日期'],
            right_on=['省份', '日期'],
            how='inner'
        )
        
        # 选择输出列
        df = df[['日期', '省份', '高风险省份总持仓_PR']]
        df = df.rename(columns={'省份': '省份名称'})
        
        # 排序
        df = df.sort_values(['日期', '高风险省份总持仓_PR'], ascending=[True, False])
        
        logger.info(f"  限额明细_高风险省份2: {len(df)} 行")
        return df
    
    def query_region_concentration_detail(self) -> pd.DataFrame:
        """
        限额明细_地域集中度限额(含城投)
        M-code: 地域集中度和城投集中度的综合明细表
        """
        df_region_limit = self.cache.get('地域集中度限额(含城投)')
        df_region_pos = self.cache.get('单一地域总持仓')
        df_citybond_pos = self.cache.get('单一地域城投总持仓')
        
        if df_region_limit is None or df_region_pos is None:
            return pd.DataFrame()
        
        # 使用单一地域总持仓的最新日期（实际业务日期）
        latest_date = df_region_pos['日期'].max()
        
        # 从地域集中度限额中选择<=该日期的最新配置
        df_limit_valid = df_region_limit[df_region_limit['日期'] <= latest_date]
        if len(df_limit_valid) == 0:
            # 如果没有历史配置，使用配置表中最早的配置
            logger.warning(f"  ⚠️ 未找到{latest_date}之前的地域限额配置，使用最早配置")
            df_limit_valid = df_region_limit
        
        limit_date = df_limit_valid['日期'].max()
        df = df_limit_valid[df_limit_valid['日期'] == limit_date].copy()
        
        # 关联单一地域总持仓（使用left join保留配置表中的所有省份）
        # 只选择业务最新日期的持仓数据
        df_region_pos_latest = df_region_pos[df_region_pos['日期'] == latest_date].copy()
        
        # 添加业务日期列用于后续关联
        df['业务日期'] = latest_date
        
        df = df.merge(
            df_region_pos_latest[['日期', '省份', '单一地域总持仓_PR', '公司净资产(万)', '地域集中度']],
            left_on=['业务日期', '指标名称'],
            right_on=['日期', '省份'],
            how='left',  # Left join保留配置表中的所有省份
            suffixes=('', '_持仓')
        )
        
        # 重命名日期列：配置日期保留为"日期"，业务日期用于计算
        if '日期_持仓' in df.columns:
            df = df.drop(columns=['日期_持仓'])
        df = df.drop(columns=['省份'], errors='ignore')
        
        # 对于没有实际持仓的省份，填充0
        df['单一地域总持仓_PR'] = df['单一地域总持仓_PR'].fillna(0)
        df['地域集中度'] = df['地域集中度'].fillna(0)
        
        # 计算单一地域总持仓上限和剩余额度
        df['单一地域总持仓上限'] = df['公司净资产(万)'] * 1.2 * df['指标值_地域集中度限额']
        df['单一地域总持仓剩余额度'] = df['单一地域总持仓上限'] - df['单一地域总持仓_PR']
        df['地域集中度是否超限'] = df['单一地域总持仓剩余额度'].apply(
            lambda x: '是' if pd.notna(x) and x < 0 else '否'
        )
        
        # 关联单一地域城投总持仓（保留日期.1字段）
        if df_citybond_pos is not None:
            # 只选择业务最新日期的城投持仓数据
            df_citybond_latest = df_citybond_pos[df_citybond_pos['日期'] == latest_date].copy()
            # 重命名城投数据的日期列为日期.1
            df_citybond_latest = df_citybond_latest.rename(columns={'日期': '日期.1'})
            
            df = df.merge(
                df_citybond_latest[['日期.1', '省份', '单一地域城投总持仓_PR', '城投地域集中度']],
                left_on=['业务日期', '指标名称'],
                right_on=['日期.1', '省份'],
                how='left'
            )
            df = df.drop(columns=['省份'], errors='ignore')
            # 日期.1字段已保留
            
            # 对于没有城投债持仓的省份，填充0
            df['单一地域城投总持仓_PR'] = df['单一地域城投总持仓_PR'].fillna(0)
            df['城投地域集中度'] = df['城投地域集中度'].fillna(0)
        
        # 计算单一地域城投总持仓上限和剩余额度
        df['单一地域城投总持仓上限'] = df['公司净资产(万)'] * df['指标值_城投集中度限额']
        df['单一地域城投持仓剩余额度'] = df['单一地域城投总持仓上限'] - df['单一地域城投总持仓_PR']
        df['城投集中度是否超限'] = df['单一地域城投持仓剩余额度'].apply(
            lambda x: '是' if pd.notna(x) and x < 0 else '否'
        )
        
        # 删除临时业务日期列
        df = df.drop(columns=['业务日期'], errors='ignore')
        
        # 重新排列列顺序（包含日期.1字段）
        output_cols = [
            '指标名称', '指标值_地域集中度限额', '日期', '单一地域总持仓_PR', '地域集中度',
            '单一地域总持仓上限', '单一地域总持仓剩余额度', '地域集中度是否超限',
            '指标值_城投集中度限额', '日期.1', '公司净资产(万)', 
            '单一地域城投总持仓_PR', '城投地域集中度',
            '单一地域城投总持仓上限', '单一地域城投持仓剩余额度', '城投集中度是否超限'
        ]
        existing_cols = [col for col in output_cols if col in df.columns]
        df = df[existing_cols]
        
        # 排序
        df = df.sort_values(['日期', '单一地域总持仓_PR'], ascending=[True, False])
        
        logger.info(f"  限额明细_地域集中度限额(含城投): {len(df)} 行")
        return df
    
    def query_high_yield_detail(self) -> pd.DataFrame:
        """
        限额明细_高收益
        M-code: 高收益债券持仓明细
        
        高收益识别规则：
        1. 优先级最高：资产代码/主证券代码/资产名称/主证券名称命中金融工具池 → 纳入（可转债白名单）
        2. 账户包含"高收益" → 全部纳入
        3. 穿透高收益债券表中"类型"="高收益" → 纳入（通过ISIN码匹配，对所有债券生效）
        """
        df_credit = self.cache.get('债券持仓明细表_信用债')
        if df_credit is None:
            return pd.DataFrame()
        
        df = df_credit.copy()
        
        # ===== 准备匹配数据 =====
        
        # 1. 获取金融工具池设置（可转债白名单，代码或简称命中即纳入）
        df_tool_pool = self.cache.get('金融工具池设置')
        tool_pool_names, tool_pool_codes = build_financial_tool_pool_sets(df_tool_pool)
        logger.info(
            f"    ✓ 金融工具池白名单（可转债代码/简称）: "
            f"{len(tool_pool_codes)}/{len(tool_pool_names)} 个"
        )
        
        # 2. 获取穿透高收益债券表，构建ISIN码→类型的映射；重复 ISIN 保留后面的配置
        df_penetrate = self.cache.get('穿透高收益债券')
        penetrate_isin_dict = _build_penetrate_isin_type_map_keep_last(df_penetrate)
        if df_penetrate is not None and '类型' not in df_penetrate.columns:
            logger.warning(f"    ⚠️  穿透高收益债券表缺少'类型'列")
        logger.info(f"    ✓ 穿透高收益债券表（ISIN→类型映射）: {len(penetrate_isin_dict)} 个")
        
        # ===== 高收益识别逻辑（增强版：同时支持简称和代码匹配）=====
        
        # 用于调试：记录每个规则匹配的数量
        match_stats = {
            'rule1_tool_pool': 0,  # 代码或简称在白名单
            'rule2_account': 0,  # 账户包含"高收益"
            'rule3_isin': 0   # ISIN码匹配穿透表
        }
        
        def is_high_yield(row):
            account = str(row.get('内部证券账户名称', ''))

            # 规则1（优先级最高）：代码或简称在金融工具池白名单中
            # 对应 PBI M-code: if [高收益量化可转债] <> null then "是"
            if row_in_financial_tool_pool(row, tool_pool_names, tool_pool_codes):
                match_stats['rule1_tool_pool'] += 1
                return '是'

            # 规则2：账户名称包含"高收益"
            # 对应 PBI M-code: else if Text.Contains([内部证券账户名称], "高收益") then "是"
            if '高收益' in account:
                match_stats['rule2_account'] += 1
                return '是'

            # 规则3：穿透高收益债券表中"类型"="高收益"
            # 对应 PBI M-code: else if [穿透债券类型] = "高收益" then "是"
            # 严格过滤 NaN ISIN，对齐 M 代码 NestedJoin 语义（NaN 不匹配任何行）
            raw_isin = row.get('ISIN码')
            if pd.notna(raw_isin):
                isin = str(raw_isin).strip()
                if isin and isin.lower() not in ('nan', 'none', 'nat'):
                    if penetrate_isin_dict.get(isin) == '高收益':
                        match_stats['rule3_isin'] += 1
                        return '是'

            # 所有条件不满足，返回"否"
            return '否'
        
        df['是否高收益'] = df.apply(is_high_yield, axis=1)
        
        # 统计识别结果（调试用）
        high_yield_count = (df['是否高收益'] == '是').sum()
        logger.info(f"    ✓ 识别为高收益的债券: {high_yield_count} 条")
        logger.info(f"      规则1-金融工具池代码/简称匹配: {match_stats['rule1_tool_pool']} 条")
        logger.info(f"      规则2-账户高收益: {match_stats['rule2_account']} 条")
        logger.info(f"      规则3-ISIN穿透表: {match_stats['rule3_isin']} 条")
        
        # 筛选高收益债券
        df = df[df['是否高收益'] == '是'].copy()
        
        # 打印一些样本用于调试
        if len(df) > 0 and '资产名称' in df.columns:
            sample_names = df['资产名称'].head(10).tolist()
            logger.info(f"    前10个高收益债券: {sample_names}")
        
        # 单债口径统一按主证券代码归并，缺失时兜底 ISIN，再兜底资产代码。
        if '主证券代码_标准' not in df.columns:
            if '主证券代码' in df.columns:
                df['主证券代码_标准'] = normalize_security_code_series(df['主证券代码'])
            else:
                df['主证券代码_标准'] = pd.NA
        if 'ISIN码' not in df.columns:
            df['ISIN码'] = pd.NA
        if '主证券代码' not in df.columns:
            df['主证券代码'] = pd.NA

        def build_high_yield_entity(row):
            main_code = _clean_text_value(row.get('主证券代码_标准'))
            if main_code:
                return pd.Series([main_code.upper(), '主证券代码'])
            isin = _clean_text_value(row.get('ISIN码'))
            if isin:
                return pd.Series([isin.upper(), 'ISIN'])
            asset_code = _clean_text_value(row.get('资产代码'))
            return pd.Series([asset_code, '资产代码' if asset_code else '缺失'])

        if df.empty:
            df['高收益单债归并键'] = pd.Series(dtype='object')
            df['高收益单债归并键来源'] = pd.Series(dtype='object')
        else:
            entity_keys = df.apply(build_high_yield_entity, axis=1)
            df['高收益单债归并键'] = entity_keys[0]
            df['高收益单债归并键来源'] = entity_keys[1]

        # 选择输出列
        output_cols = [
            '日期', '内部证券账户名称', '资产代码', '资产名称',
            '主证券代码', '主证券代码_标准', 'ISIN码',
            '库存数量(万)_PR', '债务主体',
            '高收益单债归并键', '高收益单债归并键来源',
        ]
        existing_cols = [col for col in output_cols if col in df.columns]
        df = df[existing_cols]

        # 附加高收益限额配置阈值列（参照高风险行业写法，从配置 sheet 直接赋值）
        _hy_cfg = load_limit_config(sheet_name="高收益限额", config=self.config, inject_date=False)
        _cfg_map = dict(zip(_hy_cfg['指标'], _hy_cfg['限额(万)']))
        _SCALAR_KEYS = {'年度高收益债券投资本金规模', '单一债券票面规模', '单一主体票面规模'}
        _single_bond_limit = float(_cfg_map['单一债券票面规模'])
        _single_entity_limit = float(_cfg_map['单一主体票面规模'])
        df['单一债券限额(万)'] = _single_bond_limit
        df['单一主体限额(万)'] = _single_entity_limit
        _category_limits = {k: float(v) for k, v in _cfg_map.items() if k not in _SCALAR_KEYS}
        df['按类别限额JSON'] = json.dumps(_category_limits, ensure_ascii=False)

        # 显式沉淀高收益单债 / 主体剩余额度，供 page7/page8 与审计归档复用。
        if not df.empty:
            if '库存数量(万)_PR' not in df.columns:
                df['库存数量(万)_PR'] = 0.0
            if '资产名称' not in df.columns:
                df['资产名称'] = ''
            if '债务主体' not in df.columns:
                df['债务主体'] = ''
            df['_高收益库存数值'] = pd.to_numeric(df.get('库存数量(万)_PR'), errors='coerce').fillna(0)

            bond_group_keys = [c for c in ['日期', '高收益单债归并键'] if c in df.columns]
            if bond_group_keys:
                df['高收益单债总持仓(万)'] = (
                    df.groupby(bond_group_keys, dropna=False)['_高收益库存数值'].transform('sum')
                )
                df['_高收益单债限额名称'] = (
                    df.groupby(bond_group_keys, dropna=False)['资产名称'].transform(_first_non_empty)
                )
            else:
                df['高收益单债总持仓(万)'] = df['_高收益库存数值'].sum()
                df['_高收益单债限额名称'] = _first_non_empty(df.get('资产名称', pd.Series(dtype='object')))

            df['高收益单债限额(万)'] = df['_高收益单债限额名称'].apply(
                lambda x: _lookup_high_yield_limit(x, _single_bond_limit, _category_limits)
            )
            df['高收益单债剩余额度(万)'] = df['高收益单债限额(万)'] - df['高收益单债总持仓(万)']
            df['高收益单债是否超限'] = df['高收益单债剩余额度(万)'].apply(
                lambda x: '是' if pd.notna(x) and x < 0 else '否'
            )

            issuer_group_keys = [c for c in ['日期', '债务主体'] if c in df.columns]
            if issuer_group_keys:
                df['高收益主体总持仓(万)'] = (
                    df.groupby(issuer_group_keys, dropna=False)['_高收益库存数值'].transform('sum')
                )
            else:
                df['高收益主体总持仓(万)'] = df['_高收益库存数值'].sum()

            df['高收益主体限额(万)'] = df.get('债务主体', pd.Series(dtype='object')).apply(
                lambda x: _lookup_high_yield_limit(x, _single_entity_limit, _category_limits)
            )
            df['高收益主体剩余额度(万)'] = df['高收益主体限额(万)'] - df['高收益主体总持仓(万)']
            df['高收益主体是否超限'] = df['高收益主体剩余额度(万)'].apply(
                lambda x: '是' if pd.notna(x) and x < 0 else '否'
            )
            df = df.drop(columns=['_高收益库存数值', '_高收益单债限额名称'], errors='ignore')
        else:
            for col in [
                '高收益单债总持仓(万)', '高收益单债限额(万)', '高收益单债剩余额度(万)', '高收益单债是否超限',
                '高收益主体总持仓(万)', '高收益主体限额(万)', '高收益主体剩余额度(万)', '高收益主体是否超限',
            ]:
                df[col] = pd.Series(dtype='float64' if col.endswith('(万)') else 'object')

        logger.info(f"  限额明细_高收益: {len(df)} 行")
        return df
    
    def query_high_yield_capital(self) -> pd.DataFrame:
        """
        限额明细_高收益_投资本金规模
        M 代码: 阶段2_query.md 第573-609行
        源 = 债券持仓表_核算系统，按代码或简称匹配金融工具池设置，筛选（账户含"高收益" or 可转债），
        选列后与 穿透高收益_投资本金规模 追加合并。
        """
        df_src = self.cache.get('债券持仓表_核算系统')
        if df_src is None or len(df_src) == 0:
            logger.warning("    ⚠️  未找到债券持仓表_核算系统，请确保已加载")
            return pd.DataFrame()
        
        df_src = df_src.copy()
        if '日期' in df_src.columns:
            df_src['日期'] = pd.to_datetime(df_src['日期'], errors='coerce')
        
        # 列名与 M 一致：账户、简称、代码、持仓面额(元)、全价成本(元)（核算系统表已有）
        if '账户' not in df_src.columns and '内部证券账户名称' in df_src.columns:
            df_src['账户'] = df_src['内部证券账户名称']
        if '简称' not in df_src.columns and '资产名称' in df_src.columns:
            df_src['简称'] = df_src['资产名称']
        if '代码' not in df_src.columns and '资产代码' in df_src.columns:
            df_src['代码'] = df_src['资产代码'].astype(str).str.split('.').str[0]
        if '代码' in df_src.columns and df_src['代码'].dtype != object:
            df_src['代码'] = df_src['代码'].astype(str).str.split('.').str[0]
        need_src = ['日期', '账户', '简称', '代码', '持仓面额(元)', '全价成本(元)']
        missing_src = [c for c in need_src if c not in df_src.columns]
        if missing_src:
            logger.warning(f"    债券持仓表_核算系统缺少列: {missing_src}")
            return pd.DataFrame()
        
        tool_pool_names, tool_pool_codes = build_financial_tool_pool_sets(
            self.cache.get('金融工具池设置')
        )
        if tool_pool_names or tool_pool_codes:
            df_src['高收益量化可转债'] = df_src.apply(
                lambda row: (
                    row.get('简称')
                    if row_in_financial_tool_pool(row, tool_pool_names, tool_pool_codes)
                    else pd.NA
                ),
                axis=1,
            )
        else:
            df_src['高收益量化可转债'] = pd.NA
        
        # 筛选：账户包含"高收益" or 高收益量化可转债 <> null（M: Table.SelectRows）
        account_contains = df_src['账户'].astype(str).str.contains('高收益', na=False)
        has_convertible = df_src['高收益量化可转债'].notna()
        df_src = df_src[account_contains | has_convertible].copy()
        df_src = df_src[need_src]
        
        part_accounting = df_src.drop_duplicates()
        
        part_penetrate = self.query_penetrate_high_yield_capital()
        
        out_cols = ['日期', '账户', '简称', '代码', '持仓面额(元)', '全价成本(元)']
        part_accounting = part_accounting[[c for c in out_cols if c in part_accounting.columns]]
        if len(part_penetrate) > 0:
            part_penetrate = part_penetrate[[c for c in out_cols if c in part_penetrate.columns]]
            df = pd.concat([part_accounting, part_penetrate], ignore_index=True)
        else:
            df = part_accounting
        
        if '代码' in df.columns:
            df['代码'] = df['代码'].astype(str).str.split('.').str[0]

        # 附加高收益年度限额配置阈值列
        _hy_cfg = load_limit_config(sheet_name="高收益限额", config=self.config, inject_date=False)
        _cfg_map = dict(zip(_hy_cfg['指标'], _hy_cfg['限额(万)']))
        _annual_limit = float(_cfg_map['年度高收益债券投资本金规模'])
        df['年度限额(万)'] = _annual_limit

        # 显式沉淀年度高收益限额结果，避免 page7/page8 展示层重复计算。
        if not df.empty:
            if '全价成本(元)' not in df.columns:
                df['全价成本(元)'] = 0.0
            df['_高收益全价成本数值'] = pd.to_numeric(df['全价成本(元)'], errors='coerce').fillna(0)
            if '日期' in df.columns:
                df['高收益年度总投资本金(万)'] = (
                    df.groupby(['日期'], dropna=False)['_高收益全价成本数值'].transform('sum') / 10000
                )
            else:
                df['高收益年度总投资本金(万)'] = df['_高收益全价成本数值'].sum() / 10000
            df['高收益年度限额剩余额度(万)'] = df['年度限额(万)'] - df['高收益年度总投资本金(万)']
            df['高收益年度限额是否超限'] = df['高收益年度限额剩余额度(万)'].apply(
                lambda x: '是' if pd.notna(x) and x < 0 else '否'
            )
            df = df.drop(columns=['_高收益全价成本数值'], errors='ignore')
        else:
            df['高收益年度总投资本金(万)'] = pd.Series(dtype='float64')
            df['高收益年度限额剩余额度(万)'] = pd.Series(dtype='float64')
            df['高收益年度限额是否超限'] = pd.Series(dtype='object')

        logger.info(f"  限额明细_高收益_投资本金规模: {len(df)} 行（核算系统 {len(part_accounting)} + 穿透 {len(part_penetrate)}）")
        return df
