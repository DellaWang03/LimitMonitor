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
    load_financial_tool_pool,
)
from ..common.security_code_normalizer import normalize_security_code_series
from ..risk_core.high_yield_capital_sources import (
    select_penetration_high_yield_capital_rows,
)
from ..risk_core.stage2_limits import Stage2RiskEngine
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
        df = select_penetration_high_yield_capital_rows(df_src, df_penetrate)
        if df.empty:
            needed = [
                '日期', 'ISIN码', '资产代码', '资产名称',
                '内部证券账户名称', '库存数量(万)_PR', '本币成本',
            ]
            missing = [column for column in needed if column not in df_src.columns]
            if missing:
                logger.warning(f"  穿透高收益_投资本金规模: 缺少列 {missing}")
            elif 'ISIN代码' not in df_penetrate.columns and 'ISIN码' not in df_penetrate.columns:
                logger.warning("  穿透高收益_投资本金规模: 穿透表无 ISIN 列")
        
        logger.info(f"  穿透高收益_投资本金规模: {len(df)} 行")
        return df
    
    # ========================================================================
    # 总持仓计算方法（待实现）
    # ========================================================================

    _NET_ASSET_METHODS = {
        'query_single_region_total_position',
        'query_single_region_citybond_position',
        'query_high_risk_province_position',
        'query_credit_bond_detail_2',
    }
    _HIGH_YIELD_CONFIG_METHODS = {
        'query_high_yield_detail',
        'query_high_yield_capital',
    }

    def _stage2_calculation_frames(self, method_name: str) -> Dict[str, pd.DataFrame]:
        """Resolve adapter-owned I/O before entering the pure Stage2 engine."""
        if method_name in self._NET_ASSET_METHODS and '公司净资产_手工_每日' not in self.cache:
            df_net_asset = pd.read_excel(
                self.stage0_output_dir / "公司净资产_手工_每日.xlsx"
            )
            df_net_asset['日期'] = pd.to_datetime(df_net_asset['日期'])
            self.cache['公司净资产_手工_每日'] = df_net_asset

        if method_name == 'query_credit_bond_detail_2':
            if '债券持仓明细表_信用债' not in self.cache:
                self.cache['债券持仓明细表_信用债'] = self.query_bond_position_credit()
            if '债券持仓明细表_信用债_合并风险限额相关' not in self.cache:
                self.cache[
                    '债券持仓明细表_信用债_合并风险限额相关'
                ] = self.query_bond_position_credit_merged()

        if (
            method_name in self._HIGH_YIELD_CONFIG_METHODS
            and '高收益限额' not in self.cache
        ):
            self.cache['高收益限额'] = load_limit_config(
                sheet_name="高收益限额",
                config=self.config,
                inject_date=False,
            )

        if (
            method_name == 'query_high_yield_capital'
            and '穿透高收益_投资本金规模' not in self.cache
        ):
            self.cache[
                '穿透高收益_投资本金规模'
            ] = self.query_penetrate_high_yield_capital()

        return dict(self.cache)

    def _run_stage2_calculation(self, method_name: str) -> pd.DataFrame:
        engine = Stage2RiskEngine(self._stage2_calculation_frames(method_name))
        return getattr(engine, method_name)()

    def query_total_credit_position(self) -> pd.DataFrame:
        return self._run_stage2_calculation('query_total_credit_position')

    def query_single_region_total_position(self) -> pd.DataFrame:
        return self._run_stage2_calculation('query_single_region_total_position')

    def query_single_region_citybond_position(self) -> pd.DataFrame:
        return self._run_stage2_calculation('query_single_region_citybond_position')

    def query_high_risk_industry_position(self) -> pd.DataFrame:
        return self._run_stage2_calculation('query_high_risk_industry_position')

    def query_high_risk_industry_position_detail(self) -> pd.DataFrame:
        return self._run_stage2_calculation('query_high_risk_industry_position_detail')

    def query_high_risk_province_position(self) -> pd.DataFrame:
        return self._run_stage2_calculation('query_high_risk_province_position')

    def query_high_risk_province_position_detail(self) -> pd.DataFrame:
        return self._run_stage2_calculation('query_high_risk_province_position_detail')

    def query_credit_bond_detail_2(self) -> pd.DataFrame:
        return self._run_stage2_calculation('query_credit_bond_detail_2')

    def query_high_risk_industry_detail(self) -> pd.DataFrame:
        return self._run_stage2_calculation('query_high_risk_industry_detail')

    def query_high_risk_industry_detail_2(self) -> pd.DataFrame:
        return self._run_stage2_calculation('query_high_risk_industry_detail_2')

    def query_high_risk_province_detail(self) -> pd.DataFrame:
        return self._run_stage2_calculation('query_high_risk_province_detail')

    def query_high_risk_province_detail_2(self) -> pd.DataFrame:
        return self._run_stage2_calculation('query_high_risk_province_detail_2')

    def query_region_concentration_detail(self) -> pd.DataFrame:
        return self._run_stage2_calculation('query_region_concentration_detail')

    def query_high_yield_detail(self) -> pd.DataFrame:
        return self._run_stage2_calculation('query_high_yield_detail')

    def query_high_yield_capital(self) -> pd.DataFrame:
        return self._run_stage2_calculation('query_high_yield_capital')
