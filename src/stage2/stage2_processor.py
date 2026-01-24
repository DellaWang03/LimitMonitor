"""
阶段2处理器: 限额监控 - 高风险行业/省份、地域集中度、高收益债券
负责处理高风险监控、地域集中度、城投集中度、高收益债券等
"""

import pandas as pd
import numpy as np
from pathlib import Path
from loguru import logger
from typing import Dict, Optional
import zipfile
import xml.etree.ElementTree as ET


class Stage2Processor:
    """阶段2处理器"""
    
    def __init__(self, data_dir: Path, output_dir: Path, stage0_output_dir: Path, stage1_output_dir: Path):
        """
        初始化处理器
        
        Args:
            data_dir: 数据源目录
            output_dir: 输出目录
            stage0_output_dir: 阶段0输出目录
            stage1_output_dir: 阶段1输出目录
        """
        self.data_dir = Path(data_dir)
        self.output_dir = Path(output_dir)
        self.stage0_output_dir = Path(stage0_output_dir)
        self.stage1_output_dir = Path(stage1_output_dir)
        self.cache = {}  # 查询结果缓存
        
        # 确保输出目录存在
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"阶段2处理器初始化")
        logger.info(f"  数据源: {self.data_dir}")
        logger.info(f"  输出目录: {self.output_dir}")
        logger.info(f"  阶段0输出: {self.stage0_output_dir}")
        logger.info(f"  阶段1输出: {self.stage1_output_dir}")
    
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
        数据源: 限额监控_阶段0_指标设置.xlsx
        """
        file_path = self.data_dir / "限额监控_阶段0_指标设置.xlsx"
        df = pd.read_excel(file_path, sheet_name="高风险行业表")
        
        # 数据清洗
        df['日期'] = pd.to_datetime(df['日期'])
        df['行业名称'] = df['行业名称'].astype(str).str.strip()
        df['行业类别'] = df['行业类别'].astype(str).str.strip()
        
        # 去重（按日期和行业名称）
        df = df.drop_duplicates(subset=['日期', '行业名称'], keep='first')
        
        logger.info(f"  高风险行业表: {len(df)} 行, {df['行业名称'].nunique()} 个唯一行业")
        return df
    
    def query_high_risk_province(self) -> pd.DataFrame:
        """
        查询: 高风险省份表
        数据源: 限额监控_阶段0_指标设置.xlsx
        """
        from ..common import ProvinceNormalizer  # 导入省份标准化工具
        
        file_path = self.data_dir / "限额监控_阶段0_指标设置.xlsx"
        df = pd.read_excel(file_path, sheet_name="高风险省份表")
        
        # 数据清洗
        df['日期'] = pd.to_datetime(df['日期'])
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
        数据源: 限额监控_阶段0_指标设置.xlsx
        """
        file_path = self.data_dir / "限额监控_阶段0_指标设置.xlsx"
        df = pd.read_excel(file_path, sheet_name="高风险集中度限额")
        
        # 数据清洗
        df['日期'] = pd.to_datetime(df['日期'])
        
        logger.info(f"  高风险集中度限额: {len(df)} 行")
        return df
    
    def query_region_concentration_limit(self) -> pd.DataFrame:
        """
        查询: 地域集中度限额(含城投)
        数据源: 限额监控_阶段0_指标设置.xlsx -> 单一省份限额
        """
        file_path = self.data_dir / "限额监控_阶段0_指标设置.xlsx"
        df = pd.read_excel(file_path, sheet_name="单一省份限额")
        
        # 数据清洗
        df['日期'] = pd.to_datetime(df['日期'])
        df['指标名称'] = df['指标名称'].astype(str).str.strip()
        
        logger.info(f"  地域集中度限额: {len(df)} 行, {df['指标名称'].nunique()} 个省份/地区")
        return df
    
    def query_isin_mapping(self) -> pd.DataFrame:
        """
        查询: ISIN码映射表
        数据源: 统计报表底稿2_债券SPPI.xlsx → 债券_含穿透持仓
        """
        file_path = self.data_dir / "统计报表底稿2_债券SPPI.xlsx"
        df = pd.read_excel(file_path, sheet_name="债券_含穿透持仓")
        
        # 只保留资产代码和ISIN码，并去重
        df_isin = df[['资产代码', 'ISIN码']].drop_duplicates(subset=['资产代码'], keep='first')
        
        logger.info(f"  ISIN码映射表: {len(df_isin)} 行, ISIN码非空 {df_isin['ISIN码'].notna().sum()} 个")
        return df_isin
    
    def _parse_damaged_excel(self, file_path: Path) -> pd.DataFrame:
        """
        手动解析损坏的Excel文件（样式表损坏但数据完好）
        通过解析ZIP内的XML文件来提取数据
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
                
                # 2. 读取第一个工作表数据
                with zip_ref.open('xl/worksheets/sheet1.xml') as f:
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
                        return df
                    
        except Exception as e:
            logger.error(f"手动解析Excel失败: {e}")
        
        return pd.DataFrame()
    
    def query_financial_tool_pool(self) -> pd.DataFrame:
        """
        查询: 金融工具池设置（可转债白名单）
        数据源: 金融工具池设置.xlsx
        注意：该文件样式表损坏，使用手动XML解析
        """
        file_path = self.data_dir / "金融工具池设置.xlsx"
        
        try:
            # 先尝试用pandas正常读取
            xls = pd.ExcelFile(file_path)
            sheet_name = xls.sheet_names[0] if xls.sheet_names else None
            if sheet_name:
                df = pd.read_excel(file_path, sheet_name=sheet_name)
                if '代码' in df.columns and '简称' in df.columns:
                    # 只保留代码和简称
                    df = df[['代码', '简称']].copy()
                    logger.info(f"  金融工具池设置: {len(df)} 行")
                    return df
        except Exception as e:
            # pandas读取失败，尝试手动解析XML
            logger.warning(f"  pandas读取失败，尝试手动解析XML: {str(e)[:50]}")
            df = self._parse_damaged_excel(file_path)
            
            if not df.empty and '代码' in df.columns and '简称' in df.columns:
                # 只保留代码和简称
                df = df[['代码', '简称']].copy()
                # 数据清洗
                df['代码'] = df['代码'].astype(str).str.strip()
                df['简称'] = df['简称'].astype(str).str.strip()
                # 去除空值
                df = df[df['代码'].notna() & (df['代码'] != '') & (df['代码'] != 'nan')]
                logger.info(f"  金融工具池设置（手动解析）: {len(df)} 行")
                return df
            else:
                logger.warning(f"  手动解析失败或数据格式不正确")
        
        # 返回空DataFrame
        return pd.DataFrame({'代码': [], '简称': []})
    
    def query_penetrate_high_yield(self) -> pd.DataFrame:
        """
        查询: 穿透高收益债券表
        数据源: 限额监控_阶段0_指标设置.xlsx
        """
        file_path = self.data_dir / "限额监控_阶段0_指标设置.xlsx"
        df = pd.read_excel(file_path, sheet_name="穿透高收益债券")
        
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
        
        logger.info(f"  债券持仓明细表_信用债_合并风险限额相关: {len(df)} 行")
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
        
        logger.info(f"    Stage1信用债: {len(df)} 行（保留原始重复记录）")
        
        # 2. 筛选账户（排除特定账户）
        # 注意：与原Excel保持一致，排除"做市交易部做市业务"账户
        # 高风险省份汇总表使用Stage1数据（包含做市业务），明细表排除做市业务
        df = df[
            ~df['内部证券账户名称'].str.contains('代申购代缴款', na=False) &
            (df['内部证券账户名称'] != '做市交易部做市业务')
        ].copy()
        logger.info(f"    筛选后: {len(df)} 行")
        
        # 3. 关联Stage1合并风险限额相关的计算字段（通过业务key关联）
        df_stage1_merged = self.cache.get('债券持仓明细表_信用债_合并风险限额相关')
        if df_stage1_merged is not None:
            # 准备关联key
            merge_cols = ['日期', '资产代码', '内部证券账户名称', '库存数量(万)_PR']
            
            # 选择Stage1合并后的计算字段
            stage1_calc_cols = merge_cols + [
                '行业类别', '省份类别', '主体池', '债券池', '是否属于高收益',
                '中债隐含评级', '实际控制人名称_修正', '调整后实际控制人', '担保公司是否准入'
            ]
            existing_stage1_cols = [col for col in stage1_calc_cols if col in df_stage1_merged.columns]
            
            df = df.merge(
                df_stage1_merged[existing_stage1_cols],
                on=merge_cols,
                how='left',
                suffixes=('', '_s1calc')
            )
            
            # 用Stage1的计算字段覆盖原有字段
            for col in stage1_calc_cols:
                if col not in merge_cols and f'{col}_s1calc' in df.columns:
                    df[col] = df[f'{col}_s1calc']
                    df = df.drop(columns=[f'{col}_s1calc'])
            
            logger.info(f"    ✓ 关联Stage1计算字段")
        
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
        if all(col in df.columns for col in ['公司净资产(万)', '指标值_地域集中度限额', '单一地域总持仓_PR']):
            df['地域集中度剩余额度(万)'] = (
                df['公司净资产(万)'] * 1.2 * df['指标值_地域集中度限额'] - df['单一地域总持仓_PR']
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
        
        # 高风险省份集中度剩余额度（分母 = 公司净资产 * 1.2）
        if all(col in df.columns for col in ['公司净资产(万)', '高风险省份之和集中度限额指标值', '高风险省份总持仓_PR']):
            df['高风险省份集中度剩余额度(万)'] = (
                df['公司净资产(万)'] * 1.2 * df['高风险省份之和集中度限额指标值'] - df['高风险省份总持仓_PR']
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
        
        # 删除临时业务日期列
        df = df.drop(columns=['业务日期'], errors='ignore')
        
        # 重新排列列顺序（包含日期.1字段）
        output_cols = [
            '指标名称', '指标值_地域集中度限额', '日期', '单一地域总持仓_PR', '地域集中度',
            '单一地域总持仓上限', '单一地域总持仓剩余额度',
            '指标值_城投集中度限额', '日期.1', '公司净资产(万)', 
            '单一地域城投总持仓_PR', '城投地域集中度',
            '单一地域城投总持仓上限', '单一地域城投持仓剩余额度'
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
        主要通过账户名称识别（包含"高收益"、"可转债量化策略"等）
        """
        df_credit = self.cache.get('债券持仓明细表_信用债')
        if df_credit is None:
            return pd.DataFrame()
        
        df = df_credit.copy()
        
        # 添加是否高收益标识
        # Excel规则：
        # 1. 账户包含"高收益" → 全部纳入
        # 2. 账户包含"可转债量化策略" → 必须在金融工具池设置白名单中
        # 3. 账户包含"自营部交易性" + 在穿透高收益债券表中 → 纳入（外币高收益债）
        
        # 获取穿透高收益债券表
        df_penetrate = self.cache.get('穿透高收益债券')
        penetrate_codes = set()
        if df_penetrate is not None and '债券代码' in df_penetrate.columns:
            penetrate_codes = set(df_penetrate['债券代码'].dropna().astype(str).str.strip().unique())
        
        # 获取金融工具池设置（可转债白名单）
        df_tool_pool = self.cache.get('金融工具池设置')
        tool_pool_codes = set()
        if df_tool_pool is not None and '代码' in df_tool_pool.columns:
            # 金融工具池中的代码不带交易所后缀，需要保存原始代码
            tool_pool_codes = set(df_tool_pool['代码'].dropna().astype(str).str.strip().unique())
            logger.info(f"    ✓ 金融工具池白名单: {len(tool_pool_codes)} 个债券")
        
        def is_high_yield(row):
            account = str(row.get('内部证券账户名称', ''))
            code = str(row.get('资产代码', '')).strip()
            
            # 去掉交易所后缀进行匹配（如 123080.SZ → 123080）
            code_base = code.split('.')[0] if '.' in code else code
            
            # 规则1：账户包含"高收益" → 全部纳入
            if '高收益' in account:
                return '是'
            
            # 规则2：账户包含"可转债量化策略" → 必须在金融工具池白名单中
            if '可转债量化策略' in account:
                if code_base in tool_pool_codes:
                    return '是'
                else:
                    return '否'
            
            # 规则3：自营部交易性账户 + 在穿透表中
            if '自营部交易性' in account and code in penetrate_codes:
                return '是'
            
            return '否'
        
        df['是否高收益'] = df.apply(is_high_yield, axis=1)
        
        # 筛选高收益债券
        df = df[df['是否高收益'] == '是'].copy()
        
        # 选择输出列
        output_cols = ['日期', '内部证券账户名称', '资产代码', '资产名称', '库存数量(万)_PR', '债务主体']
        existing_cols = [col for col in output_cols if col in df.columns]
        df = df[existing_cols]
        
        logger.info(f"  限额明细_高收益: {len(df)} 行")
        return df
    
    def query_high_yield_capital(self) -> pd.DataFrame:
        """
        限额明细_高收益_投资本金规模
        
        逻辑：从"限额明细_高收益"获取高收益债券列表，然后从SPPI表获取对应的本币成本
        """
        # 获取高收益债券列表（已在query_high_yield_detail中筛选好）
        df_high_yield = self.cache.get('限额明细_高收益')
        if df_high_yield is None or len(df_high_yield) == 0:
            logger.warning("    ⚠️  未找到限额明细_高收益数据")
            return pd.DataFrame()
        
        # 读取SPPI表（包含本币成本信息）
        df_sppi = pd.read_excel(self.data_dir / "统计报表底稿2_债券SPPI.xlsx", sheet_name="债券_含穿透持仓")
        
        # 确保日期字段
        if '日期' in df_sppi.columns:
            df_sppi['日期'] = pd.to_datetime(df_sppi['日期'])
        if '日期' in df_high_yield.columns:
            df_high_yield['日期'] = pd.to_datetime(df_high_yield['日期'])
        
        # 创建匹配键：日期 + 账户 + 资产代码
        df_high_yield_copy = df_high_yield.copy()
        df_high_yield_copy['匹配键'] = (
            df_high_yield_copy['日期'].astype(str) + '|' + 
            df_high_yield_copy['内部证券账户名称'].astype(str) + '|' + 
            df_high_yield_copy['资产代码'].astype(str)
        )
        
        df_sppi['匹配键'] = (
            df_sppi['日期'].astype(str) + '|' + 
            df_sppi['内部证券账户名称'].astype(str) + '|' + 
            df_sppi['资产代码'].astype(str)
        )
        
        # 从SPPI表中获取匹配的记录（获取本币成本）
        df = df_sppi[df_sppi['匹配键'].isin(df_high_yield_copy['匹配键'])].copy()
        
        if len(df) == 0:
            logger.warning("    ⚠️  SPPI表中未找到匹配数据")
            return pd.DataFrame()
        
        # 重命名列
        df = df.rename(columns={
            '内部证券账户名称': '账户',
            '资产名称': '简称',
            '资产代码': '代码'
        })
        
        # 去除代码后缀（与Excel保持一致）
        df['代码'] = df['代码'].astype(str).str.split('.').str[0]
        
        # 计算持仓面额
        df['持仓面额(元)'] = df['库存数量(万)'] * 10000
        
        # 计算全价成本
        # Excel M代码说重命名"本币成本"为"全价成本"，但SPPI表中"本币成本"大多为空
        # 实际上Excel数据显示需要用成本净价计算：全价成本 = 库存数量(万) * 10000 * 成本净价(元)_初始 / 100
        if '成本净价(元)_初始' in df.columns:
            df['全价成本(元)'] = df['库存数量(万)'] * 10000 * df['成本净价(元)_初始'] / 100
            # 对于有本币成本值的记录，用本币成本覆盖
            if '本币成本' in df.columns:
                df['全价成本(元)'] = df['全价成本(元)'].fillna(df['本币成本'])
                df.loc[df['本币成本'].notna(), '全价成本(元)'] = df.loc[df['本币成本'].notna(), '本币成本']
        else:
            df = df.rename(columns={'本币成本': '全价成本(元)'})
        
        # 选择输出列
        output_cols = ['日期', '账户', '简称', '代码', '持仓面额(元)', '全价成本(元)', 'ISIN码']
        existing_cols = [col for col in output_cols if col in df.columns]
        df = df[existing_cols]
        
        logger.info(f"  限额明细_高收益_投资本金规模: {len(df)} 行")
        return df
