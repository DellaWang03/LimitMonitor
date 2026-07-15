"""
阶段1处理器: 限额监控
负责处理债券持仓明细、计算限额、判断超限
"""

import pandas as pd
import numpy as np
from pathlib import Path
from loguru import logger
from typing import Dict
from .stage1_limit_detail import LimitDetailCalculator
from ..common import (
    SINGLE_BOND_GROUP_KEY_COL,
    SINGLE_BOND_GROUP_KEY_SOURCE_COL,
    ensure_single_bond_group_key,
    normalize_security_code_series,
)
from ..common.financial_tool_pool import (
    build_financial_tool_pool_sets,
    load_financial_tool_pool,
    normalize_tool_pool_code,
    row_in_financial_tool_pool,
)
from ..utils.limit_config_loader import load_limit_config
from ..risk_core.position_context import (
    attach_isin_to_results,
    build_credit_risk_context,
    collapse_credit_merged_to_source_rows,
    ensure_source_row_id,
    normalize_bond_position,
    normalize_credit_position,
    normalize_regulatory_position,
    validate_source_row_id,
)


SOURCE_ROW_ID_COL = '_源行号'


class Stage1Processor:
    """阶段1处理器"""
    
    def __init__(self, data_dir: Path, output_dir: Path, stage0_output_dir: Path, config=None):
        """
        初始化处理器
        
        Args:
            data_dir: 数据源目录（local 时使用；migration 时由 config 解析路径）
            output_dir: 输出目录
            stage0_output_dir: 阶段0输出目录
            config: ConfigLoader，用于 get_data_file_path 路径 profile 切换
        """
        self.data_dir = Path(data_dir)
        self.output_dir = Path(output_dir)
        self.stage0_output_dir = Path(stage0_output_dir)
        self.config = config
        self.cache = {}  # 查询结果缓存
        
        # 确保输出目录存在
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"阶段1处理器初始化")
        logger.info(f"  数据源: {self.data_dir}")
        logger.info(f"  输出目录: {self.output_dir}")
        logger.info(f"  阶段0输出: {self.stage0_output_dir}")
    
    def _data_file_path(self, file_name: str) -> Path:
        """按当前 profile 返回数据源文件路径。"""
        if self.config is not None and hasattr(self.config, "get_data_file_path"):
            return self.config.get_data_file_path(file_name)
        return self.data_dir / file_name

    def _coerce_numeric_columns(self, df: pd.DataFrame, columns) -> pd.DataFrame:
        """将指定列安全转换为数值，异常值转为 NaN。"""
        for col in columns:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        return df

    @staticmethod
    def _first_non_null(series: pd.Series):
        non_null = series.dropna()
        return non_null.iloc[0] if not non_null.empty else None

    def _build_penetration_high_yield_codes(self) -> set[str]:
        df_high_yield = self.cache.get('穿透高收益债券')
        if df_high_yield is None or df_high_yield.empty or '类型' not in df_high_yield.columns:
            return set()

        high_yield_rows = df_high_yield[
            df_high_yield['类型'].astype(str).str.strip() == '高收益'
        ]
        code_columns = [
            col
            for col in ('债券代码', '资产代码', '主证券代码', '主证券代码_标准', '代码')
            if col in high_yield_rows.columns
        ]
        codes: set[str] = set()
        for col in code_columns:
            codes.update(
                code
                for code in high_yield_rows[col].apply(normalize_tool_pool_code)
                if code
            )
        return codes

    def _filter_non_high_yield_credit_rows(self, df: pd.DataFrame) -> pd.DataFrame:
        """M-code 原本排除高收益的节点：仅替换为修正后的高收益识别规则。"""
        result = df.copy()
        high_yield_mask = pd.Series(False, index=result.index)

        if '是否属于高收益' in result.columns:
            high_yield_mask |= result['是否属于高收益'].astype(str).str.strip() == '是'

        if '内部证券账户名称' in result.columns:
            high_yield_mask |= result['内部证券账户名称'].astype(str).str.contains('高收益', na=False)

        penetration_codes = self._build_penetration_high_yield_codes()
        if penetration_codes:
            for col in ('资产代码', '资产代码_标准', '主证券代码', '主证券代码_标准'):
                if col in result.columns:
                    high_yield_mask |= result[col].apply(normalize_tool_pool_code).isin(penetration_codes)

        tool_pool_names, tool_pool_codes = build_financial_tool_pool_sets(
            self.cache.get('金融工具池设置')
        )
        if tool_pool_names or tool_pool_codes:
            high_yield_mask |= result.apply(
                row_in_financial_tool_pool,
                axis=1,
                tool_pool_names=tool_pool_names,
                tool_pool_codes=tool_pool_codes,
            )

        return result[~high_yield_mask].copy()

    def _ensure_source_row_id(self, df: pd.DataFrame, table_name: str) -> pd.DataFrame:
        """为信用债源持仓生成运行内唯一行号，用于保护真实重复持仓。"""
        return ensure_source_row_id(df, table_name)

    def _validate_source_row_id(self, df: pd.DataFrame, table_name: str) -> None:
        """校验信用债源行号存在且唯一。"""
        validate_source_row_id(df, table_name)

    def _collapse_credit_merged_to_source_rows(self, df: pd.DataFrame) -> pd.DataFrame:
        """把 merge 展开的同一源持仓收敛回一行，遇到非空字段冲突时中止。"""
        return collapse_credit_merged_to_source_rows(df)

    def _load_isin_mapping(self) -> pd.DataFrame:
        """读取资产代码到 ISIN 码映射。"""
        try:
            file_path = self._data_file_path("统计报表底稿2_债券SPPI.xlsx")
            if not Path(file_path).exists():
                logger.warning("未找到统计报表底稿2_债券SPPI.xlsx，跳过 ISIN 码补充")
                return pd.DataFrame(columns=['资产代码', 'ISIN码'])

            df = pd.read_excel(file_path, sheet_name="债券_含穿透持仓")
            source_cols = [col for col in ['资产代码', 'ISIN码'] if col in df.columns]
            if source_cols != ['资产代码', 'ISIN码']:
                logger.warning("SPPI 源表缺少资产代码/ISIN码列，跳过 ISIN 码补充")
                return pd.DataFrame(columns=['资产代码', 'ISIN码'])

            mapping_df = df[['资产代码', 'ISIN码']].copy()
            for col in ['资产代码', 'ISIN码']:
                mapping_df[col] = mapping_df[col].apply(self._clean_code_like_value)
            mapping_df = mapping_df[mapping_df['资产代码'].notna()].copy()
            mapping_df['_isin_non_null'] = mapping_df['ISIN码'].notna()
            mapping_df = mapping_df.sort_values(
                by=['资产代码', '_isin_non_null'],
                ascending=[True, False]
            )
            mapping_df = mapping_df.drop_duplicates(subset=['资产代码'], keep='first')
            mapping_df = mapping_df.drop(columns=['_isin_non_null'], errors='ignore')
            logger.info(f"  ISIN码映射加载完成: {len(mapping_df)} 行")
            return mapping_df
        except Exception as e:
            logger.warning(f"读取 ISIN 码映射失败，跳过补充: {e}")
            return pd.DataFrame(columns=['资产代码', 'ISIN码'])

    @staticmethod
    def _clean_code_like_value(value):
        """清洗代码/ISIN 类字段，统一空值。"""
        if pd.isna(value):
            return None
        text = str(value).strip()
        if text in {"", "nan", "None", "<NA>"}:
            return None
        return text

    @staticmethod
    def _clean_text_preserve_na(value):
        """清洗文本但保留空值，避免将 NaN 误转成字符串 'nan'。"""
        if pd.isna(value):
            return None
        text = str(value).strip()
        if text in {"", "nan", "None", "<NA>"}:
            return None
        return text

    def _attach_isin_to_results(self, results: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
        """为带资产代码的输出结果统一补充 ISIN 码。"""
        mapping_df = self._load_isin_mapping()
        return attach_isin_to_results(results, mapping_df)
    
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

        logger.info("\n执行查询: 金融工具池设置")
        df_tool_pool = self.query_financial_tool_pool()
        self.cache['金融工具池设置'] = df_tool_pool
        logger.info(f"✓ {len(df_tool_pool)} 行")
        
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

        logger.info("\n执行查询: 债券持仓明细表_全量债券监管集中度")
        df_regulatory_full = self.query_bond_position_regulatory_full()
        results['债券持仓明细表_全量债券监管集中度'] = df_regulatory_full
        self.cache['债券持仓明细表_全量债券监管集中度'] = df_regulatory_full
        logger.info(f"✓ {len(df_regulatory_full)} 行 × {len(df_regulatory_full.columns)} 列")
        
        # === 第3层：限额配置查询 ===
        logger.info("\n【第3层】限额配置查询")
        logger.info("=" * 80)

        # 从已缓存的信用债持仓中推断业务日期
        _df_credit_ref = self.cache.get('债券持仓明细表_信用债')
        if _df_credit_ref is None:
            raise ValueError("未找到信用债持仓缓存，无法推断 business_date")
        if '日期' not in _df_credit_ref.columns:
            raise KeyError("信用债持仓缓存缺少 '日期' 列，无法推断 business_date")
        _business_date_series = pd.to_datetime(_df_credit_ref['日期'], errors='coerce')
        _business_date = _business_date_series.max()
        if pd.isna(_business_date):
            raise ValueError("信用债持仓缓存的 '日期' 列无法解析出有效 business_date")
        self._business_date = pd.Timestamp(_business_date)
        logger.info(f"  业务日期: {self._business_date.date()}")

        logger.info("\n执行查询: 中债隐含评级AAA&AAA+")
        df_rating = self.query_bond_rating_aaa()
        results['中债隐含评级AAA&AAA+'] = df_rating
        self.cache['中债隐含评级AAA&AAA+'] = df_rating
        logger.info(f"✓ {len(df_rating)} 行")

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

        # 重要：单一担保人总持仓依赖“限额明细_特定主体/特定实控人”的剔除结果，
        # 必须在两张依赖表生成后再计算，否则会沿用不完整 cache，导致担保明细口径偏差。
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

        logger.info("\n执行查询: 限额明细_全量债券监管集中度")
        df_full_regulatory = limit_calculator.calculate_limit_detail_full_regulatory_concentration()
        results['限额明细_全量债券监管集中度'] = df_full_regulatory
        self.cache['限额明细_全量债券监管集中度'] = df_full_regulatory
        logger.info(f"✓ {len(df_full_regulatory)} 行")

        # 保存结果
        logger.info("\n" + "=" * 80)
        logger.info("保存输出文件")
        logger.info("=" * 80)

        results = self._attach_isin_to_results(results)
        self.cache.update(results)
        
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
        """读取底稿1后委托纯内核完成债券持仓标准化。"""
        file_path = self._data_file_path("统计报表底稿1_债券.xlsx")
        logger.info(f"  读取数据源: {file_path}")
        raw = pd.read_excel(file_path, sheet_name="债券持仓明细表")
        result = normalize_bond_position(raw)
        logger.info(f"  债券持仓明细表: {len(result)} 行, {len(result.columns)} 列")
        return result

    def query_bond_position_credit(self) -> pd.DataFrame:
        """读取底稿2后委托纯内核完成信用债持仓标准化。"""
        file_path = self._data_file_path("统计报表底稿2_债券SPPI.xlsx")
        logger.info(f"  读取数据源: {file_path}")
        raw = pd.read_excel(file_path, sheet_name="债券_含穿透持仓")
        result = normalize_credit_position(raw)
        logger.info(f"  信用债持仓标准化: {len(result)} 行")
        return result

    def query_bond_position_regulatory_full(self) -> pd.DataFrame:
        """读取底稿2后委托纯内核完成全量监管持仓标准化。"""
        file_path = self._data_file_path("统计报表底稿2_债券SPPI.xlsx")
        logger.info(f"  读取数据源: {file_path}")
        raw = pd.read_excel(file_path, sheet_name="债券_含穿透持仓")
        result = normalize_regulatory_position(raw)
        logger.info(f"  全量监管集中度底表（日期非空）: {len(result)} 行")
        return result

    def query_wind_bond_pool(self) -> pd.DataFrame:
        """
        查询: 风控部债券池
        数据源: 阶段0输出
        """
        file_path = self.stage0_output_dir / "风控部债券池.xlsx"
        
        df = pd.read_excel(file_path)

        # 清洗字符串列（保留空值，避免主体池 NaN 变成字符串 "nan"）
        for col in df.columns:
            if df[col].dtype == 'object' or pd.api.types.is_string_dtype(df[col]):
                df[col] = df[col].apply(self._clean_text_preserve_na)

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

        # 清洗字符串列（保留空值，避免主体池 NaN 变成字符串 "nan"）
        for col in df.columns:
            if df[col].dtype == 'object' or pd.api.types.is_string_dtype(df[col]):
                df[col] = df[col].apply(self._clean_text_preserve_na)

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
            if df[col].dtype == 'object' or pd.api.types.is_string_dtype(df[col]):
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
        file_path = self._data_file_path("发行人类型调整表.xlsx")

        df = pd.read_excel(file_path)

        # 清洗字符串列
        for col in df.columns:
            if df[col].dtype == 'object' or pd.api.types.is_string_dtype(df[col]):
                df[col] = df[col].astype(str).str.strip()

        logger.info(f"  发行人类型调整表: {len(df)} 行")
        
        return df
    
    def query_high_yield_penetration(self) -> pd.DataFrame:
        """
        查询: 穿透高收益债券
        数据源: 限额配置_当前.xlsx / 穿透高收益债券
        """
        business_date = getattr(self, '_business_date', None)
        df = load_limit_config(
            sheet_name="穿透高收益债券",
            business_date=business_date,
            config=self.config,
            inject_date=False,
        )

        # 清洗字符串列
        for col in df.columns:
            if df[col].dtype == 'object' or pd.api.types.is_string_dtype(df[col]):
                df[col] = df[col].astype(str).str.strip()

        logger.info(f"  穿透高收益债券: {len(df)} 行")

        return df

    def query_financial_tool_pool(self) -> pd.DataFrame:
        """
        查询: 金融工具池设置（可转债白名单）
        数据源: 金融工具池设置.xlsx
        """
        return load_financial_tool_pool(
            self._data_file_path("金融工具池设置.xlsx"),
            logger=logger,
        )
    
    def query_bond_rating_aaa(self) -> pd.DataFrame:
        """
        查询: 中债隐含评级AAA&AAA+
        数据源: 限额配置_当前.xlsx / 中债隐含评级表
        M代码逻辑: 筛选 评级 = "AAA" or "AAA+"
        """
        business_date = getattr(self, '_business_date', None)
        df = load_limit_config(
            sheet_name="中债隐含评级表",
            business_date=business_date,
            config=self.config,
            inject_date=True,
        )

        # 清洗字符串列
        for col in df.columns:
            if col != '日期' and (df[col].dtype == 'object' or pd.api.types.is_string_dtype(df[col])):
                df[col] = df[col].astype(str).str.strip()

        # 筛选AAA和AAA+
        if '中债隐含评级' in df.columns:
            df = df[df['中债隐含评级'].isin(['AAA', 'AAA+'])]

        logger.info(f"  中债隐含评级AAA&AAA+: {len(df)} 行")

        return df
    
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

        logger.info(f"  高风险行业表: {len(df)} 行")
        return df

    def query_high_risk_province(self) -> pd.DataFrame:
        """
        查询: 高风险省份表
        数据源: 限额配置_当前.xlsx
        """
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

        # 去重（按日期和省份名称）
        df = df.drop_duplicates(subset=['日期', '省份名称'], keep='first')

        logger.info(f"  高风险省份表: {len(df)} 行")
        return df
    
    def query_bond_position_credit_merged(self) -> pd.DataFrame:
        """委托纯内核构建信用债共享风险上下文。"""
        if self.cache.get("债券持仓明细表_信用债") is None:
            self.cache["债券持仓明细表_信用债"] = self.query_bond_position_credit()
        if self.cache.get("金融工具池设置") is None:
            self.cache["金融工具池设置"] = self.query_financial_tool_pool()

        frames = dict(self.cache)
        frames["高风险行业"] = self.query_high_risk_industry()
        frames["高风险省份"] = self.query_high_risk_province()
        result = build_credit_risk_context(frames)
        logger.info(f"  合并风险限额相关: {len(result)} 行 × {len(result.columns)} 列")
        return result

    def query_single_bond_concentration_limit(self) -> pd.DataFrame:
        """
        查询: 单一债券集中度限额
        数据源: 限额配置_当前.xlsx / 单一债券集中度限额
        """
        business_date = getattr(self, '_business_date', None)
        df = load_limit_config(
            sheet_name="单一债券集中度限额",
            business_date=business_date,
            config=self.config,
            inject_date=True,
        )

        for col in df.columns:
            if col != '日期' and (df[col].dtype == 'object' or pd.api.types.is_string_dtype(df[col])):
                df[col] = df[col].astype(str).str.strip()

        logger.info(f"  单一债券集中度限额: {len(df)} 行")

        return df

    def query_single_bond_scale_limit(self) -> pd.DataFrame:
        """
        查询: 单一债券规模限额
        数据源: 限额配置_当前.xlsx / 单一债券规模限额
        """
        business_date = getattr(self, '_business_date', None)
        df = load_limit_config(
            sheet_name="单一债券规模限额",
            business_date=business_date,
            config=self.config,
            inject_date=True,
        )

        for col in df.columns:
            if col != '日期' and (df[col].dtype == 'object' or pd.api.types.is_string_dtype(df[col])):
                df[col] = df[col].astype(str).str.strip()

        logger.info(f"  单一债券规模限额: {len(df)} 行")

        return df

    def query_special_single_bond_limit(self) -> pd.DataFrame:
        """
        查询: 特批单一债券限额
        数据源: 限额配置_当前.xlsx / 特批单一债券限额
        """
        business_date = getattr(self, '_business_date', None)
        df = load_limit_config(
            sheet_name="特批单一债券限额",
            business_date=business_date,
            config=self.config,
            inject_date=True,
        )

        for col in df.columns:
            if col != '日期' and (df[col].dtype == 'object' or pd.api.types.is_string_dtype(df[col])):
                df[col] = df[col].astype(str).str.strip()

        if '主证券代码' in df.columns:
            df['主证券代码_标准'] = normalize_security_code_series(df['主证券代码'])

        logger.info(f"  特批单一债券限额: {len(df)} 行")

        return df

    def query_single_issuer_scale_limit(self) -> pd.DataFrame:
        """
        查询: 单一主体规模限额
        数据源: 限额配置_当前.xlsx / 单一主体规模限额
        """
        business_date = getattr(self, '_business_date', None)
        df = load_limit_config(
            sheet_name="单一主体规模限额",
            business_date=business_date,
            config=self.config,
            inject_date=True,
        )

        for col in df.columns:
            if col != '日期' and (df[col].dtype == 'object' or pd.api.types.is_string_dtype(df[col])):
                df[col] = df[col].astype(str).str.strip()

        logger.info(f"  单一主体规模限额: {len(df)} 行")

        return df

    def query_single_controller_scale_limit(self) -> pd.DataFrame:
        """
        查询: 单一实控人规模限额
        数据源: 限额配置_当前.xlsx / 单一实控人规模限额
        """
        business_date = getattr(self, '_business_date', None)
        df = load_limit_config(
            sheet_name="单一实控人规模限额",
            business_date=business_date,
            config=self.config,
            inject_date=True,
        )

        for col in df.columns:
            if col != '日期' and (df[col].dtype == 'object' or pd.api.types.is_string_dtype(df[col])):
                df[col] = df[col].astype(str).str.strip()

        logger.info(f"  单一实控人规模限额: {len(df)} 行")

        return df

    def query_specific_issuer_limit(self) -> pd.DataFrame:
        """
        查询: 特定主体限额
        数据源: 限额配置_当前.xlsx / 特定主体限额
        """
        business_date = getattr(self, '_business_date', None)
        df = load_limit_config(
            sheet_name="特定主体限额",
            business_date=business_date,
            config=self.config,
            inject_date=True,
        )

        for col in df.columns:
            if col != '日期' and (df[col].dtype == 'object' or pd.api.types.is_string_dtype(df[col])):
                df[col] = df[col].astype(str).str.strip()

        logger.info(f"  特定主体限额: {len(df)} 行")

        return df

    def query_specific_controller_limit(self) -> pd.DataFrame:
        """
        查询: 特定实控人限额
        数据源: 限额配置_当前.xlsx / 特定实控人限额
        """
        business_date = getattr(self, '_business_date', None)
        df = load_limit_config(
            sheet_name="特定实控人限额",
            business_date=business_date,
            config=self.config,
            inject_date=True,
        )

        for col in df.columns:
            if col != '日期' and (df[col].dtype == 'object' or pd.api.types.is_string_dtype(df[col])):
                df[col] = df[col].astype(str).str.strip()

        logger.info(f"  特定实控人限额: {len(df)} 行")

        return df

    def query_single_guarantee_company_limit(self) -> pd.DataFrame:
        """
        查询: 单一担保公司规模限额
        数据源: 限额配置_当前.xlsx / 单一担保公司规模限额
        """
        business_date = getattr(self, '_business_date', None)
        df = load_limit_config(
            sheet_name="单一担保公司规模限额",
            business_date=business_date,
            config=self.config,
            inject_date=True,
        )

        for col in df.columns:
            if col != '日期' and (df[col].dtype == 'object' or pd.api.types.is_string_dtype(df[col])):
                df[col] = df[col].astype(str).str.strip()

        logger.info(f"  单一担保公司规模限额: {len(df)} 行")

        return df
    
    def query_single_bond_total_position(self) -> pd.DataFrame:
        """
        查询: 单一债券总持仓
        数据源: 债券持仓明细表_信用债
        M代码逻辑:
        1. 添加业务分类列
        2. 筛选非利率债
        3. 按日期、业务分类、单债归并键分组，计算总持仓和集中度
           归并键优先级：主证券代码_标准 -> ISIN码 -> 资产代码_标准 -> 资产名称 -> 行级缺省键
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

        if '主证券代码_标准' not in df.columns and '主证券代码' in df.columns:
            df['主证券代码_标准'] = normalize_security_code_series(df['主证券代码'])

        df = ensure_single_bond_group_key(df)

        if '主证券代码' in df.columns and '主证券代码_标准' in df.columns:
            df['_主证券代码_已标准化'] = df['主证券代码'] == df['主证券代码_标准']
            df = df.sort_values(
                ['日期', '业务分类', SINGLE_BOND_GROUP_KEY_COL, '_主证券代码_已标准化'],
                ascending=[True, True, True, False]
            )

        df = self._coerce_numeric_columns(
            df,
            ['库存数量(万)_PR', '债券余额(亿)']
        )
        
        # 分组计算
        aggregation_map = {
            '库存数量(万)_PR': 'sum',
            '债券余额(亿)': 'mean',
        }
        for col in [
            '主证券代码', '主证券代码_标准', '主证券名称',
            '资产代码', '资产代码_标准', '资产名称', 'ISIN码',
            SINGLE_BOND_GROUP_KEY_SOURCE_COL,
        ]:
            if col in df.columns:
                aggregation_map[col] = self._first_non_null

        result = df.groupby(
            ['日期', '业务分类', SINGLE_BOND_GROUP_KEY_COL],
            as_index=False
        ).agg(aggregation_map)
        
        result = result.rename(columns={'库存数量(万)_PR': '单一债券总持仓_PR'})
        
        # 计算单一债券集中度
        result['单一债券集中度'] = result['单一债券总持仓_PR'] / result['债券余额(亿)'] * 0.0001
        result['单一债券集中度'] = result['单一债券集中度'].replace([np.inf, -np.inf], None)
        
        # 删除债券余额列
        result = result.drop(columns=['债券余额(亿)'])

        result = result.drop(columns=['_主证券代码_已标准化'], errors='ignore')
        
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
        df = self._filter_non_high_yield_credit_rows(df)

        # 筛选：排除高收益和关注池
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
        
        df = self._filter_non_high_yield_credit_rows(df)
        
        # 筛选：排除高收益和关注池
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
        按M代码完整实现：特定主体/实控人排除、债券类型1分支、担保限额关联
        
        M代码关键逻辑（第173-292行）:
        1. 排除高收益和关注池
        2. 与"限额明细_特定主体"左连接（按资产代码+日期）
        3. 与"限额明细_特定实控人"左连接（按资产代码+日期）
        4. 筛选：指标名称 和 指标名称.1 均为null（排除特定主体/实控人）
        5. 使用债券类型1处理可转债/可交换债分支
        6. 两次合并单一主体规模限额（类别+担保准入），比较后取较大值
        7. 与单一担保公司规模限额三键关联（担保人wind代码+单一主体限额适用类别+日期）
        8. 筛选：单一担保公司规模限额不为null
        """
        df = self.cache.get('债券持仓明细表_信用债_合并风险限额相关')
        if df is None:
            df = self.query_bond_position_credit_merged()
        
        df = self._filter_non_high_yield_credit_rows(df)
        
        # 【P1-4修复1】筛选：排除高收益和关注池（M代码第179-183行）
        df = df[~df['内部证券账户名称'].str.contains('关注池', na=False)]
        
        # 步骤2: 只保留有担保人wind代码的记录
        df = df[df['担保人wind代码'].notna()]
        
        # 【P1-4修复2】与"限额明细_特定主体"左连接，使用资产代码+日期（M代码第185-190行）
        df_specific_issuer = self.cache.get('限额明细_特定主体')
        if df_specific_issuer is not None and len(df_specific_issuer) > 0:
            rows_before = len(df)
            df = df.merge(
                df_specific_issuer[['资产代码', '日期', '指标名称']],
                on=['资产代码', '日期'],
                how='left'
            )
            df = df.rename(columns={'指标名称': '特定主体指标名称'})
            logger.info(f"    合并特定主体限额: {rows_before} -> {len(df)} 行")
        else:
            df['特定主体指标名称'] = None
        
        # 【P1-4修复3】与"限额明细_特定实控人"左连接，使用资产代码+日期（M代码第192-197行）
        df_specific_controller = self.cache.get('限额明细_特定实控人')
        if df_specific_controller is not None and len(df_specific_controller) > 0:
            rows_before = len(df)
            df = df.merge(
                df_specific_controller[['资产代码', '日期', '指标名称']],
                on=['资产代码', '日期'],
                how='left',
                suffixes=('', '_ctrl')
            )
            df = df.rename(columns={'指标名称': '特定实控人指标名称'})
            logger.info(f"    合并特定实控人限额: {rows_before} -> {len(df)} 行")
        else:
            df['特定实控人指标名称'] = None
        
        # 【P1-4修复4】筛选：指标名称 和 指标名称.1 均为null（M代码第199-200行）
        # 即：排除所有特定主体和特定实控人的记录（不保留任何例外）
        rows_before = len(df)
        df = df[
            (df['特定主体指标名称'].isna()) &
            (df['特定实控人指标名称'].isna())
        ]
        rows_after = len(df)
        logger.info(f"    排除特定主体/实控人: {rows_before} -> {rows_after} 行 (排除{rows_before - rows_after}行)")
        
        # 删除临时列（M代码第202-203行）
        df = df.drop(columns=['特定主体指标名称', '特定实控人指标名称'], errors='ignore')
        
        # 【P1-4修复5】使用债券类型1处理可转债/可交换债（M代码第205-208行）
        def calc_custom_category(row):
            bond_type1 = row.get('债券类型1', '')
            if bond_type1 == '可转债':
                return '可转债'
            elif bond_type1 == '可交换债':
                return '可交换债'
            elif row.get('发行人类型') == '国企':
                return '国企'
            elif row.get('发行人类型') == '非国企':
                return '非国企'
            else:
                return None
        
        df['自定义'] = df.apply(calc_custom_category, axis=1)
        
        # 复制债券池列（M代码第210-211行）
        if '债券池' in df.columns:
            df['债券池_复制'] = df['债券池']
        
        # 合并自定义和债券池（M代码第213-215行）
        df['单一债券规模限额适用类别'] = df.apply(
            lambda row: f"{row.get('自定义', '')}/{row.get('债券池_复制', '')}"
            if pd.notna(row.get('自定义')) and pd.notna(row.get('债券池_复制'))
            else row.get('自定义', ''),
            axis=1
        )
        
        # 添加中债隐含评级前缀（M代码第220-221行）
        df['中债隐含评级_带前缀'] = df['中债隐含评级'].apply(
            lambda x: f"中债隐含评级{x}" if pd.notna(x) else None
        )
        
        # 【P1-4修复6】计算单一主体限额适用类别（M代码第223-226行）
        def calc_issuer_limit_category(row):
            # 优先使用中债隐含评级AAA/AAA+
            rating = row.get('中债隐含评级')
            if rating == 'AAA':
                return '中债隐含评级AAA'
            elif rating == 'AAA+':
                return '中债隐含评级AAA+'
            else:
                # 使用发行人类型和主体池拼接
                issuer_type = row.get('发行人类型', '')
                pool = row.get('主体池', '')
                if pd.notna(issuer_type) and pd.notna(pool):
                    return f"{issuer_type}/{pool}"
                elif pd.notna(issuer_type):
                    return issuer_type
                else:
                    return ''
        
        df['单一主体限额适用类别'] = df.apply(calc_issuer_limit_category, axis=1)
        
        # 第一次合并单一主体规模限额（M代码第232-237行）
        df_issuer_limit = self.cache.get('单一主体规模限额')
        if df_issuer_limit is not None:
            df = df.merge(
                df_issuer_limit[['日期', '指标名称', '指标值']].drop_duplicates(),
                left_on=['单一主体限额适用类别', '日期'],
                right_on=['指标名称', '日期'],
                how='left'
            )
            df = df.drop(columns=['指标名称'], errors='ignore')
            df = df.rename(columns={'指标值': '单一主体规模限额指标值1'})
        
        # 第二次合并单一主体规模限额（按担保公司是否准入）（M代码第239-245行）
        if df_issuer_limit is not None and '担保公司是否准入' in df.columns:
            df = df.merge(
                df_issuer_limit[['日期', '指标名称', '指标值']].drop_duplicates(),
                left_on=['担保公司是否准入', '日期'],
                right_on=['指标名称', '日期'],
                how='left'
            )
            df = df.drop(columns=['指标名称'], errors='ignore')
            df = df.rename(columns={'指标值': '指标值_担保'})

        # 与限额明细_债券持仓明细表_信用债1_2 保持同一套 M 代码实现，
        # 避免担保口径在“总持仓”和“限额明细”两条链路之间发生漂移。
        df = df.rename(columns={'单一主体限额适用类别': '单一主体限额适用类别1'})
        df['指标值_担保'] = df['指标值_担保'].fillna(0)
        df['单一主体规模限额指标值1'] = df['单一主体规模限额指标值1'].fillna(0)

        def select_issuer_limit_category(row):
            if pd.notna(row.get('指标值_担保')) and row.get('指标值_担保', 0) > row.get('单一主体规模限额指标值1', 0):
                return row.get('担保公司是否准入')

            return row['单一主体限额适用类别1']

        def select_issuer_limit_value(row):
            if pd.notna(row.get('指标值_担保')) and row.get('指标值_担保', 0) > row.get('单一主体规模限额指标值1', 0):
                return row.get('指标值_担保')

            return row.get('单一主体规模限额指标值1')

        # 【P1-4修复7】选择最终的单一主体限额适用类别（M代码第255-257行）
        df['单一主体限额适用类别'] = df.apply(select_issuer_limit_category, axis=1)

        # 选择最终的单一主体规模限额指标值（M代码第259-262行）
        df['单一主体规模限额指标值'] = df.apply(select_issuer_limit_value, axis=1)
        
        # 【P1-4修复8】关键步骤：与单一担保公司规模限额三键关联（M代码第268-274行）
        # 合并键：担保人wind代码 + 单一主体限额适用类别 + 日期
        # M代码：{"担保人wind代码", "单一主体限额适用类别", "日期"} <-> {"指标名称", "是否准入", "日期"}
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
            
            # 【P1-4修复9】筛选：只保留单一担保公司规模限额不为null的记录（M代码第276-277行）
            df = df[df['单一担保公司规模限额'].notna()]
            
            rows_after = len(df)
            logger.info(f"    关联单一担保公司规模限额并筛选: {rows_before} -> {rows_after} 行")
        
        # 添加业务分类（M代码第279-281行）
        df['业务分类'] = df['内部证券账户名称'].apply(
            lambda x: '做市业务' if x == '做市交易部做市业务' else '自营业务'
        )
        
        # 分组计算（M代码第283-285行）
        result = df.groupby(['日期', '业务分类', '担保人wind代码', '担保人'], as_index=False).agg({
            '库存数量(万)_PR': 'sum'
        })
        
        result = result.rename(columns={'库存数量(万)_PR': '单一担保人总持仓_PR'})
        
        logger.info(f"  单一担保人总持仓（按M代码完整实现）: {len(result)} 行")
        
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
