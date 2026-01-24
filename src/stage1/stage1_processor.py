"""
阶段1处理器: 限额监控
负责处理债券持仓明细、计算限额、判断超限
"""

import pandas as pd
import numpy as np
from pathlib import Path
from loguru import logger
from typing import Dict, Optional
from .stage1_limit_detail import LimitDetailCalculator


class Stage1Processor:
    """阶段1处理器"""
    
    def __init__(self, data_dir: Path, output_dir: Path, stage0_output_dir: Path):
        """
        初始化处理器
        
        Args:
            data_dir: 数据源目录
            output_dir: 输出目录
            stage0_output_dir: 阶段0输出目录
        """
        self.data_dir = Path(data_dir)
        self.output_dir = Path(output_dir)
        self.stage0_output_dir = Path(stage0_output_dir)
        self.cache = {}  # 查询结果缓存
        
        # 确保输出目录存在
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"阶段1处理器初始化")
        logger.info(f"  数据源: {self.data_dir}")
        logger.info(f"  输出目录: {self.output_dir}")
        logger.info(f"  阶段0输出: {self.stage0_output_dir}")
    
    def process_all(self) -> Dict[str, pd.DataFrame]:
        """
        执行所有阶段1查询
        
        Returns:
            查询结果字典
        """
        results = {}
        
        logger.info("\n" + "=" * 80)
        logger.info("开始处理阶段1")
        logger.info("=" * 80)
        
        # === 第1层：基础查询（从阶段0或数据源读取）===
        logger.info("\n【第1层】基础查询")
        logger.info("=" * 80)
        
        # 1.1 阶段0输出（直接引用）
        logger.info("\n执行查询: 风控部债券池（引用阶段0）")
        df_bond_pool = self.query_wind_bond_pool()
        results['风控部债券池'] = df_bond_pool
        self.cache['风控部债券池'] = df_bond_pool
        logger.info(f"✓ {len(df_bond_pool)} 行")
        
        logger.info("\n执行查询: 风控部主体池（引用阶段0）")
        df_issuer_pool = self.query_wind_issuer_pool()
        results['风控部主体池'] = df_issuer_pool
        self.cache['风控部主体池'] = df_issuer_pool
        logger.info(f"✓ {len(df_issuer_pool)} 行")
        
        logger.info("\n执行查询: 调整实控人名单（引用阶段0）")
        df_controller = self.query_adjusted_controller()
        results['调整实控人名单'] = df_controller
        self.cache['调整实控人名单'] = df_controller
        logger.info(f"✓ {len(df_controller)} 行")
        
        # 1.2 辅助查询
        logger.info("\n执行查询: 发行人类型调整表")
        df_issuer_type = self.query_issuer_type_adjustment()
        results['发行人类型调整表'] = df_issuer_type
        self.cache['发行人类型调整表'] = df_issuer_type
        logger.info(f"✓ {len(df_issuer_type)} 行")
        
        logger.info("\n执行查询: 穿透高收益债券")
        df_high_yield = self.query_high_yield_penetration()
        results['穿透高收益债券'] = df_high_yield
        self.cache['穿透高收益债券'] = df_high_yield
        logger.info(f"✓ {len(df_high_yield)} 行")
        
        logger.info("\n执行查询: 中债隐含评级AAA&AAA+")
        df_rating = self.query_bond_rating_aaa()
        results['中债隐含评级AAA&AAA+'] = df_rating
        self.cache['中债隐含评级AAA&AAA+'] = df_rating
        logger.info(f"✓ {len(df_rating)} 行")
        
        logger.info("\n执行查询: 新老划断")
        df_new_old_cutoff = self.query_new_old_cutoff()
        results['新老划断'] = df_new_old_cutoff
        self.cache['新老划断'] = df_new_old_cutoff
        logger.info(f"✓ {len(df_new_old_cutoff)} 行")
        
        # === 第2层：信用债查询 ===
        logger.info("\n【第2层】信用债查询")
        logger.info("=" * 80)
        
        logger.info("\n执行查询: 债券持仓明细表")
        df_position = self.query_bond_position()
        results['债券持仓明细表'] = df_position
        self.cache['债券持仓明细表'] = df_position
        logger.info(f"✓ {len(df_position)} 行 × {len(df_position.columns)} 列")
        
        logger.info("\n执行查询: 债券持仓明细表_信用债")
        df_credit = self.query_bond_position_credit()
        results['债券持仓明细表_信用债'] = df_credit
        self.cache['债券持仓明细表_信用债'] = df_credit
        logger.info(f"✓ {len(df_credit)} 行 × {len(df_credit.columns)} 列")
        
        # === 第3层：限额配置查询 ===
        logger.info("\n【第3层】限额配置查询")
        logger.info("=" * 80)
        
        # 读取各类限额配置
        limit_queries = [
            ('单一债券规模限额', self.query_single_bond_scale_limit),
            ('单一债券集中度限额', self.query_single_bond_concentration_limit),
            ('特批单一债券限额', self.query_special_single_bond_limit),
            ('单一主体规模限额', self.query_single_issuer_scale_limit),
            ('单一实控人规模限额', self.query_single_controller_scale_limit),
            ('特定主体限额', self.query_specific_issuer_limit),
            ('特定实控人限额', self.query_specific_controller_limit),
            ('单一担保公司规模限额', self.query_single_guarantee_company_limit),
        ]
        
        for name, func in limit_queries:
            logger.info(f"\n执行查询: {name}")
            df = func()
            results[name] = df
            self.cache[name] = df
            logger.info(f"✓ {len(df)} 行")
        
        # === 第4层：合并风险限额相关字段 ===
        logger.info("\n【第4层】合并风险限额相关")
        logger.info("=" * 80)
        
        logger.info("\n执行查询: 债券持仓明细表_信用债_合并风险限额相关")
        df_credit_merged = self.query_bond_position_credit_merged()
        results['债券持仓明细表_信用债_合并风险限额相关'] = df_credit_merged
        self.cache['债券持仓明细表_信用债_合并风险限额相关'] = df_credit_merged
        logger.info(f"✓ {len(df_credit_merged)} 行 × {len(df_credit_merged.columns)} 列")
        
        # === 第5层：总持仓计算 ===
        logger.info("\n【第5层】总持仓计算")
        logger.info("=" * 80)
        
        logger.info("\n执行查询: 单一债券总持仓")
        df_bond_pos = self.query_single_bond_total_position()
        results['单一债券总持仓'] = df_bond_pos
        self.cache['单一债券总持仓'] = df_bond_pos
        logger.info(f"✓ {len(df_bond_pos)} 行")
        
        logger.info("\n执行查询: 单一主体总持仓")
        df_issuer_pos = self.query_single_issuer_total_position()
        results['单一主体总持仓'] = df_issuer_pos
        self.cache['单一主体总持仓'] = df_issuer_pos
        logger.info(f"✓ {len(df_issuer_pos)} 行")
        
        logger.info("\n执行查询: 特定主体总持仓")
        df_specific_issuer = self.query_specific_issuer_total_position()
        results['特定主体总持仓'] = df_specific_issuer
        self.cache['特定主体总持仓'] = df_specific_issuer
        logger.info(f"✓ {len(df_specific_issuer)} 行")
        
        logger.info("\n执行查询: 单一实控人总持仓")
        df_controller = self.query_single_controller_total_position()
        results['单一实控人总持仓'] = df_controller
        self.cache['单一实控人总持仓'] = df_controller
        logger.info(f"✓ {len(df_controller)} 行")
        
        logger.info("\n执行查询: 特定实控人总持仓")
        df_specific_controller = self.query_specific_controller_total_position()
        results['特定实控人总持仓'] = df_specific_controller
        self.cache['特定实控人总持仓'] = df_specific_controller
        logger.info(f"✓ {len(df_specific_controller)} 行")
        
        logger.info("\n执行查询: 单一担保人总持仓")
        df_guarantee = self.query_single_guarantee_total_position()
        results['单一担保人总持仓'] = df_guarantee
        self.cache['单一担保人总持仓'] = df_guarantee
        logger.info(f"✓ {len(df_guarantee)} 行")
        
        logger.info("\n执行查询: 单一担保人总持仓_不剔除")
        df_guarantee_all = self.query_single_guarantee_total_position_unfiltered()
        results['单一担保人总持仓_不剔除'] = df_guarantee_all
        self.cache['单一担保人总持仓_不剔除'] = df_guarantee_all
        logger.info(f"✓ {len(df_guarantee_all)} 行")
        
        # === 第6层：限额明细查询 ===
        logger.info("\n【第6层】限额明细查询")
        logger.info("=" * 80)
        
        # 创建限额明细计算器
        limit_calculator = LimitDetailCalculator(self.cache)
        
        # 重要：先计算限额明细_特定主体和_特定实控人，因为限额明细1_2需要用它们来筛选和关联
        logger.info("\n执行查询: 限额明细_特定主体")
        df_specific_issuer_limit = limit_calculator.calculate_limit_detail_specific_issuer()
        results['限额明细_特定主体'] = df_specific_issuer_limit
        self.cache['限额明细_特定主体'] = df_specific_issuer_limit
        logger.info(f"✓ {len(df_specific_issuer_limit)} 行")
        
        logger.info("\n执行查询: 限额明细_特定实控人")
        df_specific_controller_limit = limit_calculator.calculate_limit_detail_specific_controller()
        results['限额明细_特定实控人'] = df_specific_controller_limit
        self.cache['限额明细_特定实控人'] = df_specific_controller_limit
        logger.info(f"✓ {len(df_specific_controller_limit)} 行")
        
        logger.info("\n执行查询: 限额明细_债券持仓明细表_信用债1_2")
        df_limit_detail = limit_calculator.calculate_limit_detail_1_2()
        results['限额明细_债券持仓明细表_信用债1_2'] = df_limit_detail
        self.cache['限额明细_债券持仓明细表_信用债1_2'] = df_limit_detail
        logger.info(f"✓ {len(df_limit_detail)} 行")
        
        logger.info("\n执行查询: 限额明细_单一债券")
        df_bond_limit = limit_calculator.calculate_limit_detail_single_bond()
        results['限额明细_单一债券'] = df_bond_limit
        self.cache['限额明细_单一债券'] = df_bond_limit
        logger.info(f"✓ {len(df_bond_limit)} 行")
        
        logger.info("\n执行查询: 限额明细_单一主体")
        df_issuer_limit = limit_calculator.calculate_limit_detail_single_issuer()
        results['限额明细_单一主体'] = df_issuer_limit
        self.cache['限额明细_单一主体'] = df_issuer_limit
        logger.info(f"✓ {len(df_issuer_limit)} 行")
        
        logger.info("\n执行查询: 限额明细_单一实控人")
        df_controller_limit = limit_calculator.calculate_limit_detail_single_controller()
        results['限额明细_单一实控人'] = df_controller_limit
        self.cache['限额明细_单一实控人'] = df_controller_limit
        logger.info(f"✓ {len(df_controller_limit)} 行")
        
        logger.info("\n执行查询: 限额明细_单一实控人_取最高额度")
        df_controller_max = limit_calculator.calculate_limit_detail_single_controller_max()
        results['限额明细_单一实控人_取最高额度'] = df_controller_max
        self.cache['限额明细_单一实控人_取最高额度'] = df_controller_max
        logger.info(f"✓ {len(df_controller_max)} 行")
        
        logger.info("\n执行查询: 限额明细_单一担保人")
        df_guarantee_limit = limit_calculator.calculate_limit_detail_single_guarantee()
        results['限额明细_单一担保人'] = df_guarantee_limit
        self.cache['限额明细_单一担保人'] = df_guarantee_limit
        logger.info(f"✓ {len(df_guarantee_limit)} 行")
        
        logger.info("\n执行查询: 限额明细_债券持仓明细表_信用债1_1")
        df_limit_1_1 = limit_calculator.calculate_limit_detail_1_1()
        results['限额明细_债券持仓明细表_信用债1_1'] = df_limit_1_1
        self.cache['限额明细_债券持仓明细表_信用债1_1'] = df_limit_1_1
        logger.info(f"✓ {len(df_limit_1_1)} 行")
        
        # 保存结果
        logger.info("\n" + "=" * 80)
        logger.info("保存输出文件")
        logger.info("=" * 80)
        
        for name, df in results.items():
            output_file = self.output_dir / f"{name}.xlsx"
            
            # 检查文件是否已存在
            file_exists = output_file.exists()
            action = "覆盖" if file_exists else "新建"
            
            # 保存（会自动覆盖已存在的文件）
            df.to_excel(output_file, index=False)
            logger.info(f"  ✓ {action}: {name}.xlsx")
        
        logger.info("\n" + "=" * 80)
        logger.info("阶段1处理完成")
        logger.info("=" * 80)
        
        return results
    
    def query_bond_position(self) -> pd.DataFrame:
        """
        查询: 债券持仓明细表
        数据源: 统计报表底稿1_债券.xlsx / 债券持仓明细表
        M代码逻辑: 只选择部分列
        """
        file_path = self.data_dir / "统计报表底稿1_债券.xlsx"
        
        logger.info(f"  读取数据源: {file_path}")
        df = pd.read_excel(file_path, sheet_name="债券持仓明细表")
        
        # 清洗字符串列
        for col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].astype(str).str.strip()
        
        # 转换日期列
        if '日期' in df.columns:
            df['日期'] = pd.to_datetime(df['日期'])
        
        # 根据M代码选择需要的列
        selected_cols = ['日期', '金融资产会计属性', '部门', '内部证券账户名称', '资产代码', '资产名称',
                        '库存数量(万)', '库存数量(万)_空头为负', '债券分类2', '主证券代码', '主证券名称', 
                        '库存数量(万)_PR', '债券余额(亿)', '债务主体wind代码', '担保人wind代码']
        
        # 只保留存在的列
        existing_cols = [col for col in selected_cols if col in df.columns]
        df = df[existing_cols]
        
        logger.info(f"  债券持仓明细表: {len(df)} 行, {len(df.columns)} 列")
        
        return df
    
    def query_bond_position_credit(self) -> pd.DataFrame:
        """
        查询: 债券持仓明细表_信用债
        数据源: 统计报表底稿2_债券SPPI.xlsx / 债券_含穿透持仓
        M代码逻辑: 
        1. 读取债券_含穿透持仓
        2. 选择需要的列
        3. 筛选: 债券分类2 <> "利率债"
        4. 筛选: 不包含"代申购代缴款"
        5. 筛选: 日期非空
        """
        file_path = self.data_dir / "统计报表底稿2_债券SPPI.xlsx"
        
        logger.info(f"  读取数据源: {file_path}")
        df = pd.read_excel(file_path, sheet_name="债券_含穿透持仓")
        
        # 清洗字符串列
        for col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].astype(str).str.strip()
        
        # 转换日期列
        if '日期' in df.columns:
            df['日期'] = pd.to_datetime(df['日期'], errors='coerce')
        
        logger.info(f"  原始数据: {len(df)} 行")
        
        # 根据M代码选择需要的列（这里只列出关键的23列）
        selected_cols = ['日期', '金融资产会计属性', '部门', '内部证券账户名称', '资产代码', '资产名称', 
                        '债券分类2', '债券类型1', '主证券代码', '主证券名称', '库存数量(万)_PR', '债券余额(亿)',
                        '发行人类型', '债务主体', '债务主体wind代码', '实际控制人名称_修正', '担保人', '担保人wind代码',
                        '是否城投债', '债券类别', 'wind行业', '省份', '合并辅助列']
        
        # 保留存在的列
        existing_cols = [col for col in selected_cols if col in df.columns]
        df = df[existing_cols]
        
        # 筛选: 债券分类2 <> "利率债"
        df = df[df['债券分类2'] != '利率债']
        logger.info(f"  筛选非利率债: {len(df)} 行")
        
        # 筛选: 不包含"代申购代缴款"
        if '内部证券账户名称' in df.columns:
            df = df[~df['内部证券账户名称'].str.contains('代申购代缴款', na=False)]
            logger.info(f"  排除代申购代缴款: {len(df)} 行")
        
        # 筛选: 日期非空
        df = df[df['日期'].notna()]
        logger.info(f"  筛选日期非空: {len(df)} 行")
        
        return df
    
    def query_wind_bond_pool(self) -> pd.DataFrame:
        """
        查询: 风控部债券池
        数据源: 阶段0输出
        """
        file_path = self.stage0_output_dir / "风控部债券池.xlsx"
        
        df = pd.read_excel(file_path)
        
        # 清洗字符串列
        for col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].astype(str).str.strip()
        
        logger.info(f"  风控部债券池: {len(df)} 行")
        
        return df
    
    def query_wind_issuer_pool(self) -> pd.DataFrame:
        """
        查询: 风控部主体池
        数据源: 阶段0输出
        M代码逻辑: 重命名"发行人wind代码"为"主体wind代码"
        """
        file_path = self.stage0_output_dir / "风控部债券池_主体.xlsx"
        
        df = pd.read_excel(file_path)
        
        # 清洗字符串列
        for col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].astype(str).str.strip()
        
        # 重命名列
        df = df.rename(columns={'发行人wind代码': '主体wind代码'})
        
        logger.info(f"  风控部主体池: {len(df)} 行")
        
        return df
    
    def query_adjusted_controller(self) -> pd.DataFrame:
        """
        查询: 调整实控人名单
        数据源: 阶段0输出
        M代码逻辑: 筛选 主体wind代码 <> "0"
        """
        file_path = self.stage0_output_dir / "调整实控人名单.xlsx"
        
        df = pd.read_excel(file_path)
        
        # 清洗字符串列
        for col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].astype(str).str.strip()
        
        # 去重
        df = df.drop_duplicates()
        
        # 筛选: 主体wind代码 <> "0"
        df = df[df['主体wind代码'] != '0']
        
        logger.info(f"  调整实控人名单: {len(df)} 行")
        
        return df
    
    def query_issuer_type_adjustment(self) -> pd.DataFrame:
        """
        查询: 发行人类型调整表
        数据源: 发行人类型调整表.xlsx（用户提供，替代Base64解码）
        """
        file_path = self.data_dir / "发行人类型调整表.xlsx"
        
        df = pd.read_excel(file_path)
        
        # 清洗字符串列
        for col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].astype(str).str.strip()
        
        logger.info(f"  发行人类型调整表: {len(df)} 行")
        
        return df
    
    def query_high_yield_penetration(self) -> pd.DataFrame:
        """
        查询: 穿透高收益债券
        数据源: 限额监控_阶段0_指标设置.xlsx / 穿透高收益债券
        """
        file_path = self.data_dir / "限额监控_阶段0_指标设置.xlsx"
        
        df = pd.read_excel(file_path, sheet_name="穿透高收益债券")
        
        # 清洗字符串列
        for col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].astype(str).str.strip()
        
        logger.info(f"  穿透高收益债券: {len(df)} 行")
        
        return df
    
    def query_bond_rating_aaa(self) -> pd.DataFrame:
        """
        查询: 中债隐含评级AAA&AAA+
        数据源: 限额监控_阶段0_指标设置.xlsx / 中债隐含评级表
        M代码逻辑: 筛选 评级 = "AAA" or "AAA+"
        """
        file_path = self.data_dir / "限额监控_阶段0_指标设置.xlsx"
        
        df = pd.read_excel(file_path, sheet_name="中债隐含评级表")
        
        # 清洗字符串列
        for col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].astype(str).str.strip()
        
        # 筛选AAA和AAA+
        if '中债隐含评级' in df.columns:
            df = df[df['中债隐含评级'].isin(['AAA', 'AAA+'])]
        
        logger.info(f"  中债隐含评级AAA&AAA+: {len(df)} 行")
        
        return df
    
    def query_new_old_cutoff(self) -> pd.DataFrame:
        """
        查询: 新老划断
        数据源: sample data/新老划断.xlsx
        用途: 标记特定债券的新老划断属性，用于限额计算时的特殊处理
        """
        file_path = self.data_dir / "新老划断.xlsx"
        
        df = pd.read_excel(file_path, sheet_name="新老划断")
        
        # 清洗字符串列
        for col in df.select_dtypes(include=['object']).columns:
            df[col] = df[col].str.strip()
        
        # 选择关键列（保留所有字段以完全复现Excel）
        columns_to_keep = ['主证券代码', '代码', '债券分类', '证券简称', '备注', '列1', '债务主体']
        df = df[columns_to_keep]
        
        logger.info(f"  新老划断: {len(df)} 行")
        
        return df
    
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
        
        logger.info(f"  高风险行业表: {len(df)} 行")
        return df
    
    def query_high_risk_province(self) -> pd.DataFrame:
        """
        查询: 高风险省份表
        数据源: 限额监控_阶段0_指标设置.xlsx
        """
        file_path = self.data_dir / "限额监控_阶段0_指标设置.xlsx"
        df = pd.read_excel(file_path, sheet_name="高风险省份表")
        
        # 数据清洗
        df['日期'] = pd.to_datetime(df['日期'])
        df['省份名称'] = df['省份名称'].astype(str).str.strip()
        df['省份类别'] = df['省份类别'].astype(str).str.strip()
        
        # 去重（按日期和省份名称）
        df = df.drop_duplicates(subset=['日期', '省份名称'], keep='first')
        
        logger.info(f"  高风险省份表: {len(df)} 行")
        return df
    
    def query_bond_position_credit_merged(self) -> pd.DataFrame:
        """
        查询: 债券持仓明细表_信用债_合并风险限额相关
        数据源: 债券持仓明细表_信用债
        M代码逻辑: 复杂的多表关联，添加风险限额相关字段
        """
        # 获取信用债数据
        df = self.cache.get('债券持仓明细表_信用债')
        if df is None:
            df = self.query_bond_position_credit()
        
        df = df.copy()
        
        logger.info(f"  开始合并风险限额字段...")
        
        # 1. 合并穿透高收益债券
        df_high_yield = self.cache.get('穿透高收益债券')
        if df_high_yield is not None and '债券代码' in df_high_yield.columns:
            df = df.merge(
                df_high_yield[['债券代码', '类型']],
                left_on='资产代码',
                right_on='债券代码',
                how='left'
            )
            df = df.drop(columns=['债券代码'], errors='ignore')
            
            # 添加"是否属于高收益"列
            df['是否属于高收益'] = df.apply(
                lambda row: '是' if ('高收益' in str(row.get('内部证券账户名称', '')) or 
                                    row.get('类型') == '高收益') else '否',
                axis=1
            )
            df = df.drop(columns=['类型'], errors='ignore')
            logger.info(f"    ✓ 合并穿透高收益债券")
        
        # 2. 合并中债隐含评级
        df_rating = self.cache.get('中债隐含评级AAA&AAA+')
        if df_rating is not None and 'wind代码' in df_rating.columns and '日期' in df_rating.columns:
            df = df.merge(
                df_rating[['wind代码', '日期', '中债隐含评级']],
                left_on=['债务主体wind代码', '日期'],
                right_on=['wind代码', '日期'],
                how='left'
            )
            df = df.drop(columns=['wind代码'], errors='ignore')
            logger.info(f"    ✓ 合并中债隐含评级")
        
        # 3. 合并风控部债券池（获取债券池、主体池）
        df_bond_pool = self.cache.get('风控部债券池')
        if df_bond_pool is not None:
            df = df.merge(
                df_bond_pool[['代码', '日期', '债券池', '主体池']],
                left_on=['资产代码', '日期'],
                right_on=['代码', '日期'],
                how='left',
                suffixes=('', '.0')
            )
            df = df.drop(columns=['代码'], errors='ignore')
            logger.info(f"    ✓ 合并风控部债券池")
        
        # 4. 合并风控部主体池（通过债务主体获取主体池）
        df_issuer_pool = self.cache.get('风控部主体池')
        if df_issuer_pool is not None:
            df = df.merge(
                df_issuer_pool[['日期', '发行人名称', '主体池']],
                left_on=['日期', '债务主体'],
                right_on=['日期', '发行人名称'],
                how='left',
                suffixes=('', '.1')
            )
            df = df.drop(columns=['发行人名称'], errors='ignore')
            
            # 去重
            df = df.drop_duplicates()
            
            # 处理主体池：如果主体池.1不为空，使用主体池.1，否则使用主体池
            if '主体池.0' in df.columns:
                df = df.rename(columns={'主体池': '主体池.0'})
            
            if '主体池.1' in df.columns:
                df['主体池'] = df['主体池.1'].fillna(df.get('主体池.0', ''))
                df = df.drop(columns=['主体池.0', '主体池.1'], errors='ignore')
            
            logger.info(f"    ✓ 合并风控部主体池")
        
        # 5. 合并担保人主体池
        if df_issuer_pool is not None and '担保人wind代码' in df.columns:
            # 关键修复：过滤掉主体wind代码为NaN的记录，避免NaN键笛卡尔积
            df_issuer_pool_valid = df_issuer_pool[
                df_issuer_pool['主体wind代码'].notna()
            ].copy()
            
            df = df.merge(
                df_issuer_pool_valid[['日期', '主体wind代码', '主体池']],
                left_on=['日期', '担保人wind代码'],
                right_on=['日期', '主体wind代码'],
                how='left',
                suffixes=('', '_担保')
            )
            df = df.drop(columns=['主体wind代码'], errors='ignore')
            logger.info(f"    ✓ 合并担保人主体池")
        
        # 6. 替换空值为null
        for col in ['债券池', '主体池', '主体池_担保']:
            if col in df.columns:
                df[col] = df[col].replace('', None)
        
        # 再次去重
        df = df.drop_duplicates()
        
        # 7. 合并发行人类型调整表
        df_issuer_type = self.cache.get('发行人类型调整表')
        if df_issuer_type is not None:
            df = df.merge(
                df_issuer_type[['wind代码', '发行人类型']],
                left_on='债务主体wind代码',
                right_on='wind代码',
                how='left',
                suffixes=('', '.1')
            )
            df = df.drop(columns=['wind代码'], errors='ignore')
            
            # 处理发行人类型：如果调整表有值，使用调整表的值
            if '发行人类型.1' in df.columns:
                df['发行人类型_调整'] = df['发行人类型.1'].fillna(df.get('发行人类型', ''))
                df = df.drop(columns=['发行人类型.1'], errors='ignore')
            
            logger.info(f"    ✓ 合并发行人类型调整表")
        
        # 8. 合并调整实控人名单
        df_controller = self.cache.get('调整实控人名单')
        if df_controller is not None and '主体wind代码' in df_controller.columns:
            df = df.merge(
                df_controller[['主体wind代码', '调整后实际控制人']],
                left_on='债务主体wind代码',
                right_on='主体wind代码',
                how='left'
            )
            df = df.drop(columns=['主体wind代码'], errors='ignore')
            logger.info(f"    ✓ 合并调整实控人名单")
        
        # 8.4 合并单一担保公司规模限额（获取"是否准入"字段）
        df_guarantee_limit = self.cache.get('单一担保公司规模限额')
        if df_guarantee_limit is not None and '担保人wind代码' in df.columns:
            df = df.merge(
                df_guarantee_limit[['日期', '指标名称', '是否准入']],
                left_on=['日期', '担保人wind代码'],
                right_on=['日期', '指标名称'],
                how='left',
                suffixes=('', '_担保限额')
            )
            df = df.drop(columns=['指标名称'], errors='ignore')
            logger.info(f"    ✓ 合并单一担保公司规模限额")
        
        # 8.5 合并新老划断
        df_new_old_cutoff = self.cache.get('新老划断')
        if df_new_old_cutoff is not None:
            df = df.merge(
                df_new_old_cutoff[['主证券代码', '备注']],
                left_on='资产代码',
                right_on='主证券代码',
                how='left',
                suffixes=('', '_新老划断')
            )
            # 删除来自新老划断表的主证券代码列
            df = df.drop(columns=['主证券代码_新老划断'], errors='ignore')
            df = df.rename(columns={'备注': '是否新老划断'}, errors='ignore')
            
            # 未匹配的默认为"否"
            if '是否新老划断' in df.columns:
                df['是否新老划断'] = df['是否新老划断'].fillna('否')
            
            logger.info(f"    ✓ 合并新老划断")
        
        # 9. 处理实际控制人名称_修正
        if '调整后实际控制人' in df.columns:
            df['实际控制人名称_修正'] = df['调整后实际控制人'].fillna(df.get('实际控制人名称_修正', ''))
        
        # 10. 替换空字符串为null
        null_cols = ['担保人wind代码', '中债隐含评级', '债券池', '主体池', '主体池_担保', '实际控制人名称_修正']
        for col in null_cols:
            if col in df.columns:
                df[col] = df[col].replace('', None)
        
        # 11. 添加担保公司是否准入列
        # 根据Excel M代码逻辑：
        # if [是否准入] <> null then [是否准入]  
        # else if [担保人] <> "0" then "担保" 
        # else null
        if '担保人' in df.columns:
            df['担保公司是否准入'] = df.apply(
                lambda row: (
                    row.get('是否准入') if pd.notna(row.get('是否准入')) 
                    else ('担保' if pd.notna(row.get('担保人')) and str(row.get('担保人')) != '0' 
                    else None)
                ),
                axis=1
            )
            # 删除中间列"是否准入"
            df = df.drop(columns=['是否准入'], errors='ignore')
        
        # 12. 添加合并列（可选，但为了完全复现Excel逻辑）
        if '资产代码' in df.columns and '资产名称' in df.columns and '债务主体' in df.columns:
            df['代码/名称/债务主体'] = df['资产代码'].astype(str) + '/' + \
                                      df['资产名称'].astype(str) + '/' + \
                                      df['债务主体'].astype(str)
        
        # 13. 按业务key去重，保留第一条（与Excel逻辑一致）
        # 说明：merge操作可能产生笛卡尔积导致业务key相同但辅助字段不同的重复记录
        # 按业务逻辑，同一日期、资产、账户、数量应视为同一笔交易，保留第一条
        key_cols = ['日期', '资产代码', '内部证券账户名称', '库存数量(万)_PR']
        df = df.drop_duplicates(subset=key_cols, keep='first')
        
        # 14. 关联高风险行业表（添加"行业类别"字段）
        # 根据阶段2 M-code：通过wind行业字段关联
        df_high_risk_industry = self.query_high_risk_industry()
        if df_high_risk_industry is not None and 'wind行业' in df.columns:
            # 确保wind行业字段为字符串类型
            df['wind行业'] = df['wind行业'].astype(str).str.strip()
            
            df = df.merge(
                df_high_risk_industry[['日期', '行业名称', '行业类别']],
                left_on=['日期', 'wind行业'],
                right_on=['日期', '行业名称'],
                how='left'
            )
            df = df.drop(columns=['行业名称'], errors='ignore')
            logger.info(f"    ✓ 合并高风险行业表")
        
        # 15. 关联高风险省份表（添加"省份类别"字段）
        # 根据阶段2 M-code：通过省份字段关联
        from ..common import ProvinceNormalizer  # 导入省份标准化工具
        
        df_high_risk_province = self.query_high_risk_province()
        if df_high_risk_province is not None and '省份' in df.columns:
            # 确保省份字段为字符串类型
            df['省份'] = df['省份'].astype(str).str.strip()
            
            # ===== 新增：省份标准化 =====
            # 1. 标准化债券持仓表中的省份字段
            df = ProvinceNormalizer.add_normalized_column(
                df, 
                source_column='省份', 
                target_column='省份_标准'
            )
            
            # 2. 标准化配置表中的省份名称字段
            df_high_risk_province = ProvinceNormalizer.add_normalized_column(
                df_high_risk_province,
                source_column='省份名称',
                target_column='省份名称_标准'
            )
            
            # 3. 使用标准化后的字段进行merge
            df = df.merge(
                df_high_risk_province[['日期', '省份名称_标准', '省份类别']],
                left_on=['日期', '省份_标准'],
                right_on=['日期', '省份名称_标准'],
                how='left'
            )
            
            # 4. 清理临时列
            df = df.drop(columns=['省份_标准', '省份名称_标准'], errors='ignore')
            
            # 5. 验证合并效果（修正逻辑）
            # 只验证配置表中定义的高风险省份是否都被正确匹配
            high_risk_provinces = set(df_high_risk_province['省份名称'].unique())
            
            # 统计各高风险省份的匹配情况
            matched_high_risk = df[df['省份类别'] == '高风险省份']['省份'].unique()
            all_provinces_in_data = df['省份'].unique()
            
            # 找出配置表中定义的高风险省份，在数据中存在但未被标记的
            unmatched_high_risk = []
            for province in high_risk_provinces:
                # 检查这个高风险省份是否在数据中存在
                if province in all_provinces_in_data:
                    # 如果存在，检查是否被正确标记
                    province_records = df[df['省份'] == province]
                    marked_count = province_records[province_records['省份类别'] == '高风险省份'].shape[0]
                    total_count = province_records.shape[0]
                    
                    if marked_count < total_count:
                        unmatched_high_risk.append(f"{province}({marked_count}/{total_count})")
            
            # 记录高风险省份标记情况
            high_risk_count = df[df['省份类别'] == '高风险省份'].shape[0]
            logger.info(f"    ✓ 合并高风险省份表 (高风险省份记录: {high_risk_count}条)")
            
            # 只有当配置的高风险省份未被完全匹配时才警告
            if unmatched_high_risk:
                logger.warning(f"    ⚠️  以下高风险省份部分记录未被标记: {unmatched_high_risk}")
            else:
                logger.info(f"    ✓ 所有高风险省份记录已正确标记")
        
        logger.info(f"  合并风险限额相关: {len(df)} 行 × {len(df.columns)} 列")
        if '行业类别' in df.columns:
            logger.info(f"    高风险行业记录数: {df['行业类别'].notna().sum()}")
        if '省份类别' in df.columns:
            logger.info(f"    高风险省份记录数: {df['省份类别'].notna().sum()}")
        
        return df
    
    def query_single_bond_concentration_limit(self) -> pd.DataFrame:
        """
        查询: 单一债券集中度限额
        数据源: 限额监控_阶段0_指标设置.xlsx / 单一债券集中度限额
        """
        file_path = self.data_dir / "限额监控_阶段0_指标设置.xlsx"
        
        df = pd.read_excel(file_path, sheet_name="单一债券集中度限额")
        
        # 清洗和转换类型
        for col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].astype(str).str.strip()
        
        if '日期' in df.columns:
            df['日期'] = pd.to_datetime(df['日期'])
        
        logger.info(f"  单一债券集中度限额: {len(df)} 行")
        
        return df
    
    def query_single_bond_scale_limit(self) -> pd.DataFrame:
        """
        查询: 单一债券规模限额
        数据源: 限额监控_阶段0_指标设置.xlsx / 单一债券规模限额
        """
        file_path = self.data_dir / "限额监控_阶段0_指标设置.xlsx"
        
        df = pd.read_excel(file_path, sheet_name="单一债券规模限额")
        
        # 清洗和转换类型
        for col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].astype(str).str.strip()
        
        if '日期' in df.columns:
            df['日期'] = pd.to_datetime(df['日期'])
        
        logger.info(f"  单一债券规模限额: {len(df)} 行")
        
        return df
    
    def query_special_single_bond_limit(self) -> pd.DataFrame:
        """
        查询: 特批单一债券限额
        数据源: 限额监控_阶段0_指标设置.xlsx / 特批单一债券限额
        """
        file_path = self.data_dir / "限额监控_阶段0_指标设置.xlsx"
        
        df = pd.read_excel(file_path, sheet_name="特批单一债券限额")
        
        # 清洗和转换类型
        for col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].astype(str).str.strip()
        
        if '日期' in df.columns:
            df['日期'] = pd.to_datetime(df['日期'])
        
        logger.info(f"  特批单一债券限额: {len(df)} 行")
        
        return df
    
    def query_single_issuer_scale_limit(self) -> pd.DataFrame:
        """
        查询: 单一主体规模限额
        数据源: 限额监控_阶段0_指标设置.xlsx / 单一主体规模限额
        """
        file_path = self.data_dir / "限额监控_阶段0_指标设置.xlsx"
        
        df = pd.read_excel(file_path, sheet_name="单一主体规模限额")
        
        # 清洗和转换类型
        for col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].astype(str).str.strip()
        
        if '日期' in df.columns:
            df['日期'] = pd.to_datetime(df['日期'])
        
        logger.info(f"  单一主体规模限额: {len(df)} 行")
        
        return df
    
    def query_single_controller_scale_limit(self) -> pd.DataFrame:
        """
        查询: 单一实控人规模限额
        数据源: 限额监控_阶段0_指标设置.xlsx / 单一实控人规模限额
        """
        file_path = self.data_dir / "限额监控_阶段0_指标设置.xlsx"
        
        df = pd.read_excel(file_path, sheet_name="单一实控人规模限额")
        
        # 清洗和转换类型
        for col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].astype(str).str.strip()
        
        if '日期' in df.columns:
            df['日期'] = pd.to_datetime(df['日期'])
        
        logger.info(f"  单一实控人规模限额: {len(df)} 行")
        
        return df
    
    def query_specific_issuer_limit(self) -> pd.DataFrame:
        """
        查询: 特定主体限额
        数据源: 限额监控_阶段0_指标设置.xlsx / 特定主体限额
        """
        file_path = self.data_dir / "限额监控_阶段0_指标设置.xlsx"
        
        df = pd.read_excel(file_path, sheet_name="特定主体限额")
        
        # 清洗和转换类型
        for col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].astype(str).str.strip()
        
        if '日期' in df.columns:
            df['日期'] = pd.to_datetime(df['日期'])
        
        logger.info(f"  特定主体限额: {len(df)} 行")
        
        return df
    
    def query_specific_controller_limit(self) -> pd.DataFrame:
        """
        查询: 特定实控人限额
        数据源: 限额监控_阶段0_指标设置.xlsx / 特定实控人限额
        """
        file_path = self.data_dir / "限额监控_阶段0_指标设置.xlsx"
        
        df = pd.read_excel(file_path, sheet_name="特定实控人限额")
        
        # 清洗和转换类型
        for col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].astype(str).str.strip()
        
        if '日期' in df.columns:
            df['日期'] = pd.to_datetime(df['日期'])
        
        logger.info(f"  特定实控人限额: {len(df)} 行")
        
        return df
    
    def query_single_guarantee_company_limit(self) -> pd.DataFrame:
        """
        查询: 单一担保公司规模限额
        数据源: 限额监控_阶段0_指标设置.xlsx / 单一担保公司规模限额
        """
        file_path = self.data_dir / "限额监控_阶段0_指标设置.xlsx"
        
        df = pd.read_excel(file_path, sheet_name="单一担保公司规模限额")
        
        # 清洗和转换类型
        for col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].astype(str).str.strip()
        
        if '日期' in df.columns:
            df['日期'] = pd.to_datetime(df['日期'])
        
        logger.info(f"  单一担保公司规模限额: {len(df)} 行")
        
        return df
    
    def query_single_bond_total_position(self) -> pd.DataFrame:
        """
        查询: 单一债券总持仓
        数据源: 债券持仓明细表_信用债
        M代码逻辑:
        1. 添加业务分类列
        2. 筛选非利率债
        3. 按日期、业务分类、主证券代码分组，计算总持仓和集中度
        """
        df = self.cache.get('债券持仓明细表_信用债')
        if df is None:
            df = self.query_bond_position_credit()
        
        df = df.copy()
        
        # 添加业务分类
        df['业务分类'] = df['内部证券账户名称'].apply(
            lambda x: '做市业务' if x == '做市交易部做市业务' else '自营业务'
        )
        
        # 筛选非利率债
        df = df[df['债券分类2'] != '利率债']
        
        # 分组计算
        result = df.groupby(['日期', '业务分类', '主证券代码', '主证券名称'], as_index=False).agg({
            '库存数量(万)_PR': 'sum',
            '债券余额(亿)': 'mean'
        })
        
        result = result.rename(columns={'库存数量(万)_PR': '单一债券总持仓_PR'})
        
        # 计算单一债券集中度
        result['单一债券集中度'] = result['单一债券总持仓_PR'] / result['债券余额(亿)'] * 0.0001
        result['单一债券集中度'] = result['单一债券集中度'].replace([np.inf, -np.inf], None)
        
        # 删除债券余额列
        result = result.drop(columns=['债券余额(亿)'])
        
        # 排序
        result = result.sort_values('单一债券集中度', ascending=False)
        
        logger.info(f"  单一债券总持仓: {len(result)} 行")
        
        return result
    
    def query_single_issuer_total_position(self) -> pd.DataFrame:
        """
        查询: 单一主体总持仓
        数据源: 债券持仓明细表_信用债
        M代码逻辑: 按日期、业务分类、债务主体分组
        """
        df = self.cache.get('债券持仓明细表_信用债')
        if df is None:
            df = self.query_bond_position_credit()
        
        df = df.copy()
        
        # 添加业务分类
        df['业务分类'] = df['内部证券账户名称'].apply(
            lambda x: '做市业务' if x == '做市交易部做市业务' else '自营业务'
        )
        
        # 分组计算
        result = df.groupby(['日期', '业务分类', '债务主体wind代码', '债务主体'], as_index=False).agg({
            '库存数量(万)_PR': 'sum'
        })
        
        result = result.rename(columns={'库存数量(万)_PR': '单一主体总持仓_PR'})
        
        logger.info(f"  单一主体总持仓: {len(result)} 行")
        
        return result
    
    def query_specific_issuer_total_position(self) -> pd.DataFrame:
        """
        查询: 特定主体总持仓
        数据源: 债券持仓明细表_信用债
        M代码逻辑: 排除高收益和关注池，与特定主体限额关联后分组
        """
        df = self.cache.get('债券持仓明细表_信用债')
        if df is None:
            df = self.query_bond_position_credit()
        
        df = df.copy()
        
        # 筛选：排除高收益和关注池
        df = df[~df['内部证券账户名称'].str.contains('高收益', na=False)]
        df = df[~df['内部证券账户名称'].str.contains('关注池', na=False)]
        
        # 与特定主体限额关联
        df_limit = self.cache.get('特定主体限额')
        if df_limit is not None:
            df = df.merge(
                df_limit[['主体wind代码', '日期', '指标名称', '指标值']],
                left_on=['债务主体wind代码', '日期'],
                right_on=['主体wind代码', '日期'],
                how='left'
            )
            df = df.drop(columns=['主体wind代码'], errors='ignore')
            df = df.rename(columns={'指标名称': '限额名称'})
            
            # 筛选：限额名称不为空
            df = df[df['限额名称'].notna()]
            
            # 添加业务分类
            df['业务分类'] = df['内部证券账户名称'].apply(
                lambda x: '做市业务' if x == '做市交易部做市业务' else '自营业务'
            )
            
            # 分组计算
            result = df.groupby(['日期', '业务分类', '限额名称'], as_index=False).agg({
                '库存数量(万)_PR': 'sum'
            })
            
            result = result.rename(columns={
                '限额名称': '特定主体名称',
                '库存数量(万)_PR': '特定主体总持仓'
            })
            
            logger.info(f"  特定主体总持仓: {len(result)} 行")
            
            return result
        else:
            logger.warning(f"  特定主体限额未找到，返回空DataFrame")
            return pd.DataFrame()
    
    def query_single_controller_total_position(self) -> pd.DataFrame:
        """
        查询: 单一实控人总持仓
        数据源: 债券持仓明细表_信用债_合并风险限额相关
        M代码逻辑: 按实际控制人分组
        """
        df = self.cache.get('债券持仓明细表_信用债_合并风险限额相关')
        if df is None:
            df = self.query_bond_position_credit_merged()
        
        df = df.copy()
        
        # 添加业务分类
        df['业务分类'] = df['内部证券账户名称'].apply(
            lambda x: '做市业务' if x == '做市交易部做市业务' else '自营业务'
        )
        
        # 分组计算
        result = df.groupby(['日期', '业务分类', '实际控制人名称_修正'], as_index=False).agg({
            '库存数量(万)_PR': 'sum'
        })
        
        result = result.rename(columns={'库存数量(万)_PR': '单一实控人总持仓_PR'})
        
        # 筛选：实际控制人不为空
        result = result[result['实际控制人名称_修正'].notna()]
        
        logger.info(f"  单一实控人总持仓: {len(result)} 行")
        
        return result
    
    def query_specific_controller_total_position(self) -> pd.DataFrame:
        """
        查询: 特定实控人总持仓
        数据源: 债券持仓明细表_信用债_合并风险限额相关
        M代码逻辑: 排除高收益和关注池，与特定实控人限额关联后分组
        """
        df = self.cache.get('债券持仓明细表_信用债_合并风险限额相关')
        if df is None:
            df = self.query_bond_position_credit_merged()
        
        df = df.copy()
        
        # 筛选：排除高收益和关注池
        df = df[~df['内部证券账户名称'].str.contains('高收益', na=False)]
        df = df[~df['内部证券账户名称'].str.contains('关注池', na=False)]
        
        # 与特定实控人限额关联
        df_limit = self.cache.get('特定实控人限额')
        if df_limit is not None:
            df = df.merge(
                df_limit[['实控人名称', '日期', '指标名称', '指标值']],
                left_on=['实际控制人名称_修正', '日期'],
                right_on=['实控人名称', '日期'],
                how='left'
            )
            
            # 筛选：指标名称不为空
            df = df[(df['指标名称'].notna()) & (df['指标名称'] != '')]
            
            # 添加业务分类
            df['业务分类'] = df['内部证券账户名称'].apply(
                lambda x: '做市业务' if x == '做市交易部做市业务' else '自营业务'
            )
            
            # 分组计算
            result = df.groupby(['日期', '业务分类', '实控人名称'], as_index=False).agg({
                '库存数量(万)_PR': 'sum'
            })
            
            result = result.rename(columns={
                '实控人名称': '特定实控人名称',
                '库存数量(万)_PR': '特定实控人总持仓'
            })
            
            logger.info(f"  特定实控人总持仓: {len(result)} 行")
            
            return result
        else:
            logger.warning(f"  特定实控人限额未找到，返回空DataFrame")
            return pd.DataFrame()
    
    def query_single_guarantee_total_position(self) -> pd.DataFrame:
        """
        查询: 单一担保人总持仓
        数据源: 债券持仓明细表_信用债_合并风险限额相关
        M代码逻辑: 完整实现Excel Power Query的复杂担保人筛选和限额判断逻辑
        """
        df = self.cache.get('债券持仓明细表_信用债_合并风险限额相关')
        if df is None:
            df = self.query_bond_position_credit_merged()
        
        df = df.copy()
        
        # 步骤1: 筛选：排除高收益和关注池
        df = df[~df['内部证券账户名称'].str.contains('高收益', na=False)]
        df = df[~df['内部证券账户名称'].str.contains('关注池', na=False)]
        
        # 步骤2: 只保留有担保人wind代码的记录
        df = df[df['担保人wind代码'].notna()]
        
        # 步骤3: merge特定主体限额，筛选([指标名称] = null) and ([指标名称.1] = null)
        df_specific_issuer_limit = self.cache.get('特定主体限额')
        if df_specific_issuer_limit is not None and len(df_specific_issuer_limit) > 0:
            rows_before = len(df)
            df = df.merge(
                df_specific_issuer_limit[['主体wind代码', '日期', '指标名称']],
                left_on=['债务主体wind代码', '日期'],
                right_on=['主体wind代码', '日期'],
                how='left'
            )
            df = df.drop(columns=['主体wind代码'], errors='ignore')
            df = df.rename(columns={'指标名称': '特定主体指标名称'})
            df = df[
                (df['特定主体指标名称'].isna()) | 
                (df['特定主体指标名称'] == '陕西西咸新区发展集团有限公司')
            ]
            rows_after = len(df)
            logger.info(f"    排除特定主体: {rows_before} -> {rows_after} 行")
        
        # 步骤4: 生成"单一主体限额适用类别"（初始值）
        # Excel: if [中债隐含评级] = "AAA" then "中债隐含评级AAA" else if ... else Text.Combine({[发行人类型], [主体池]}, "/")
        df['单一主体限额适用类别_1'] = df.apply(
            lambda row: (
                '中债隐含评级AAA' if row.get('中债隐含评级') == 'AAA' else
                '中债隐含评级AAA+' if row.get('中债隐含评级') == 'AAA+' else
                f"{row.get('发行人类型', '')}/{row.get('主体池', '')}"
            ),
            axis=1
        )
        
        # 步骤5: 第一次merge"单一主体规模限额"（使用"单一主体限额适用类别"）
        df_issuer_limit = self.cache.get('单一主体规模限额')
        if df_issuer_limit is not None:
            df = df.merge(
                df_issuer_limit[['日期', '指标名称', '指标值']].drop_duplicates(),
                left_on=['日期', '单一主体限额适用类别_1'],
                right_on=['日期', '指标名称'],
                how='left'
            )
            df = df.drop(columns=['指标名称'], errors='ignore')
            df = df.rename(columns={'指标值': '单一主体规模限额指标值_1'})
        
        # 步骤6: 第二次merge"单一主体规模限额"（使用"担保公司是否准入"）
        if df_issuer_limit is not None and '担保公司是否准入' in df.columns:
            df = df.merge(
                df_issuer_limit[['日期', '指标名称', '指标值']].drop_duplicates(),
                left_on=['日期', '担保公司是否准入'],
                right_on=['日期', '指标名称'],
                how='left'
            )
            df = df.drop(columns=['指标名称'], errors='ignore')
            df = df.rename(columns={'指标值': '担保公司限额指标值'})
            
            # 步骤7: 替换null为0
            df['担保公司限额指标值'] = df['担保公司限额指标值'].fillna(0)
            df['单一主体规模限额指标值_1'] = df['单一主体规模限额指标值_1'].fillna(0)
            
            # 步骤8: 条件列 - 比较两个限额，选择较大的作为最终的"单一主体限额适用类别"
            # Excel: if [指标值] > [单一主体规模限额指标值1] then [担保公司是否准入] else [单一主体限额适用类别1]
            df['单一主体限额适用类别'] = df.apply(
                lambda row: (
                    row.get('担保公司是否准入') 
                    if row.get('担保公司限额指标值', 0) > row.get('单一主体规模限额指标值_1', 0) 
                    else row.get('单一主体限额适用类别_1')
                ),
                axis=1
            )
            
            logger.info(f"    应用担保限额逻辑: 优先使用更高的限额配置")
        else:
            df['单一主体限额适用类别'] = df['单一主体限额适用类别_1']
        
        # 步骤9: 关键步骤 - merge"单一担保公司规模限额"（使用最终的"单一主体限额适用类别"）
        df_guarantee_limit = self.cache.get('单一担保公司规模限额')
        if df_guarantee_limit is not None:
            rows_before = len(df)
            
            df = df.merge(
                df_guarantee_limit[['日期', '指标名称', '是否准入', '指标值']].drop_duplicates(),
                left_on=['日期', '担保人wind代码', '单一主体限额适用类别'],
                right_on=['日期', '指标名称', '是否准入'],
                how='left'
            )
            df = df.rename(columns={'指标值': '单一担保公司规模限额'})
            
            # 筛选：只保留成功匹配到担保限额的记录
            df = df[df['单一担保公司规模限额'].notna()]
            
            rows_after = len(df)
            if rows_before > rows_after:
                logger.info(f"    筛选有担保限额配置: {rows_before} -> {rows_after} 行 (排除{rows_before - rows_after}行)")
        
        # 步骤10: 添加业务分类
        df['业务分类'] = df['内部证券账户名称'].apply(
            lambda x: '做市业务' if x == '做市交易部做市业务' else '自营业务'
        )
        
        # 步骤11: 分组计算
        result = df.groupby(['日期', '业务分类', '担保人wind代码', '担保人'], as_index=False).agg({
            '库存数量(万)_PR': 'sum'
        })
        
        result = result.rename(columns={'库存数量(万)_PR': '单一担保人总持仓_PR'})
        
        logger.info(f"  单一担保人总持仓: {len(result)} 行")
        
        return result
    
    def query_single_guarantee_total_position_unfiltered(self) -> pd.DataFrame:
        """
        查询: 单一担保人总持仓_不剔除
        数据源: 单一担保公司规模限额 + 债券持仓明细表_信用债_合并风险限额相关
        M代码逻辑: 不排除任何记录，全部统计
        """
        df_limit = self.cache.get('单一担保公司规模限额')
        df_position = self.cache.get('债券持仓明细表_信用债_合并风险限额相关')
        
        if df_limit is None or df_position is None:
            logger.warning(f"  单一担保公司规模限额或债券持仓未找到")
            return pd.DataFrame()
        
        # 从限额表获取担保公司列表
        df_guarantors = df_limit[['日期', '指标名称', '统一社会信用代码', '授信担保公司名称']].copy()
        df_guarantors = df_guarantors.drop_duplicates()
        
        # 与持仓关联（右连接，保留所有持仓）
        df = df_guarantors.merge(
            df_position[['日期', '担保人wind代码', '库存数量(万)_PR']],
            left_on=['日期', '指标名称'],
            right_on=['日期', '担保人wind代码'],
            how='right'
        )
        
        # 分组计算
        result = df.groupby(['日期', '指标名称', '授信担保公司名称'], as_index=False).agg({
            '库存数量(万)_PR': 'sum'
        })
        
        result = result.rename(columns={'库存数量(万)_PR': '单一担保人总持仓_PR'})
        
        logger.info(f"  单一担保人总持仓_不剔除: {len(result)} 行")
        
        return result
