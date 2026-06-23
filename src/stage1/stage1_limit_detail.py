"""
阶段1限额明细查询模块
由于限额明细查询非常复杂，单独提取到此模块
"""

import pandas as pd
import numpy as np
from loguru import logger
from typing import Dict
from ..common import (
    SINGLE_BOND_GROUP_KEY_COL,
    ensure_single_bond_group_key,
    normalize_security_code_series,
)
from ..common.financial_tool_pool import (
    build_financial_tool_pool_sets,
    normalize_tool_pool_code,
    row_in_financial_tool_pool,
)
from ..utils.config_loader import ConfigLoader
from ..utils.limit_config_loader import load_limit_config


SOURCE_ROW_ID_COL = '_源行号'


class LimitDetailCalculator:
    """限额明细计算器"""
    
    def __init__(self, cache: Dict[str, pd.DataFrame],
                 regulatory_concentration_limit: float | None = None):
        """
        初始化

        Args:
            cache: 缓存的查询结果字典
            regulatory_concentration_limit: 监管集中度限额（如 0.16 表示 16%）。
                显式传入时直接使用，优先于磁盘配置文件；用于历史归档回放时确保使用
                归档当日的限额值而非当前配置文件的值（由 daily_archive.py 传入）。
        """
        self.cache = cache
        self._regulatory_concentration_limit_override = regulatory_concentration_limit

    def _load_regulatory_concentration_limit(self) -> float:
        """读取监管集中度默认限额配置。实例级 override 优先于 Excel 配置文件。"""
        if self._regulatory_concentration_limit_override is not None:
            return self._regulatory_concentration_limit_override
        config = ConfigLoader()
        df = load_limit_config(
            sheet_name="系统参数",
            config=config,
            inject_date=False,
        )
        if "参数名" not in df.columns or "值" not in df.columns:
            raise KeyError("系统参数 sheet 缺少 '参数名' 或 '值' 列")

        row_map = (
            df.assign(参数名=df["参数名"].astype(str).str.strip())
            .drop_duplicates(subset=["参数名"], keep="first")
            .set_index("参数名")["值"]
            .to_dict()
        )
        if "监管集中度限额" not in row_map:
            raise KeyError("系统参数 sheet 缺少 '监管集中度限额' 参数")

        value = row_map["监管集中度限额"]
        if pd.isna(value):
            raise ValueError("系统参数 sheet 中 '监管集中度限额' 为空")
        return float(value)

    @staticmethod
    def _first_non_null(series: pd.Series):
        """返回序列中的首个非空值。"""
        non_null = series.dropna()
        if len(non_null) == 0:
            return None
        return non_null.iloc[0]

    @staticmethod
    def _normalize_match_series(series: pd.Series, column_name: str) -> pd.Series:
        """用于跨表兜底匹配的轻量标准化。"""
        if column_name == '日期':
            parsed = pd.to_datetime(series, errors='coerce')
            raw = series.astype('string').str.strip().fillna('')
            return parsed.dt.strftime('%Y-%m-%d').fillna(raw)
        if '代码' in column_name:
            return series.apply(normalize_tool_pool_code)
        return series.apply(lambda x: '' if pd.isna(x) else str(x).strip())

    @classmethod
    def _row_key_series(cls, df: pd.DataFrame, columns: list[str]) -> pd.Series:
        key_parts = [
            cls._normalize_match_series(df[col], col).astype(str)
            for col in columns
        ]
        return pd.concat(key_parts, axis=1).agg('\x1f'.join, axis=1)

    def _build_penetration_high_yield_codes(self) -> set[str]:
        df_high_yield = self.cache.get('穿透高收益债券')
        if df_high_yield is None or df_high_yield.empty:
            return set()
        if '类型' not in df_high_yield.columns:
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

    def _merged_high_yield_mask(self, result: pd.DataFrame) -> pd.Series:
        """原始持仓表没有高收益标记时，用合并信用债表做行级兜底。"""
        mask = pd.Series(False, index=result.index)
        merged = self.cache.get('债券持仓明细表_信用债_合并风险限额相关')
        if merged is None or merged.empty or '是否属于高收益' not in merged.columns:
            return mask

        merged_flag = merged['是否属于高收益'].astype(str).str.strip()
        if not (merged_flag == '是').any():
            return mask

        high_yield_rows = merged[merged_flag == '是'].copy()
        exact_candidates = [
            SOURCE_ROW_ID_COL,
            '日期',
            '内部证券账户名称',
            '资产代码',
            '资产名称',
            '主证券代码',
            '主证券名称',
            '库存数量(万)_PR',
        ]
        exact_cols = [
            col
            for col in exact_candidates
            if col in result.columns and col in high_yield_rows.columns
        ]
        if exact_cols:
            high_yield_keys = set(self._row_key_series(high_yield_rows, exact_cols))
            mask |= self._row_key_series(result, exact_cols).isin(high_yield_keys)

        code_cols = [
            col
            for col in ('资产代码', '资产代码_标准', '主证券代码', '主证券代码_标准')
            if col in merged.columns
        ]
        if not code_cols:
            return mask

        merged_code_records = []
        merged_accounts = (
            merged['内部证券账户名称'].astype(str)
            if '内部证券账户名称' in merged.columns
            else pd.Series('', index=merged.index)
        )
        for idx, row in merged.iterrows():
            row_codes = {
                normalize_tool_pool_code(row.get(col))
                for col in code_cols
            }
            row_codes.discard('')
            for code in row_codes:
                merged_code_records.append(
                    {
                        'code': code,
                        'is_high_yield': merged_flag.loc[idx] == '是',
                        'is_account_high_yield': '高收益' in merged_accounts.loc[idx],
                    }
                )

        if not merged_code_records:
            return mask

        code_status = pd.DataFrame(merged_code_records)
        all_high_yield_by_code = code_status.groupby('code')['is_high_yield'].all()
        has_non_account_reason_by_code = (
            code_status[code_status['is_high_yield']]
            .groupby('code')['is_account_high_yield']
            .apply(lambda s: (~s).any())
        )
        code_level_high_yield = {
            code
            for code, all_high_yield in all_high_yield_by_code.items()
            if all_high_yield and has_non_account_reason_by_code.get(code, False)
        }
        if not code_level_high_yield:
            return mask

        result_code_cols = [
            col
            for col in ('资产代码', '资产代码_标准', '主证券代码', '主证券代码_标准')
            if col in result.columns
        ]
        for col in result_code_cols:
            mask |= result[col].apply(normalize_tool_pool_code).isin(code_level_high_yield)
        return mask

    def _filter_non_high_yield_rows(self, df: pd.DataFrame) -> pd.DataFrame:
        """普通信用债限额口径：排除账户、穿透配置、金融工具池识别出的高收益。"""
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

        if '是否属于高收益' not in result.columns:
            high_yield_mask |= self._merged_high_yield_mask(result)

        return result[~high_yield_mask].copy()
    
    def calculate_limit_detail_1_2(self) -> pd.DataFrame:
        """
        查询: 限额明细_债券持仓明细表_信用债1_2
        这是最核心的限额明细查询，包含所有超限判断逻辑
        
        M代码逻辑:
        1. 过滤高收益
        2. 添加业务分类
        3. 关联特定主体/实控人限额
        4. 计算单一债券限额适用类别
        5. 关联各类限额配置
        6. 关联各类总持仓
        7. 计算剩余额度
        8. 判断是否超限
        """
        df = self.cache.get('债券持仓明细表_信用债_合并风险限额相关')
        if df is None:
            logger.error("债券持仓明细表_信用债_合并风险限额相关未找到")
            return pd.DataFrame()
        
        df = df.copy()
        
        logger.info(f"  开始计算限额明细...")

        if '主证券代码_标准' not in df.columns and '主证券代码' in df.columns:
            df['主证券代码_标准'] = normalize_security_code_series(df['主证券代码'])
        df = ensure_single_bond_group_key(df)
        
        # 1. 筛选非高收益
        df = df[df['是否属于高收益'] == '否']
        logger.info(f"    筛选非高收益: {len(df)} 行")
        
        # 2. 添加业务分类
        df['业务分类'] = df['内部证券账户名称'].apply(
            lambda x: '做市业务' if x == '做市交易部做市业务' else '自营业务'
        )
        
        # 2.1 关联限额明细_特定主体（获取指标名称 + 特定主体限额指标值）
        # M-code: 合并的查询7 同时展开 {指标名称, 特定主体限额指标值}，必须在步骤8之前完成
        df_specific_issuer = self.cache.get('限额明细_特定主体')
        if df_specific_issuer is not None and len(df_specific_issuer) > 0:
            rows_before = len(df)
            cols_to_merge = ['业务分类', '资产代码', '日期', '指标名称']
            if '特定主体限额指标值' in df_specific_issuer.columns:
                cols_to_merge.append('特定主体限额指标值')
            df = df.merge(
                df_specific_issuer[cols_to_merge],
                on=['业务分类', '资产代码', '日期'],
                how='left'
            )
            # 重命名为特定主体指标名称
            df = df.rename(columns={'指标名称': '特定主体指标名称'})
            
            # 关键筛选：只保留特定主体指标名称为null或"陕西西咸新区发展集团有限公司"的记录
            # 这是Excel M-code第195行的筛选逻辑
            df = df[
                (df['特定主体指标名称'].isna()) | 
                (df['特定主体指标名称'] == '陕西西咸新区发展集团有限公司')
            ]
            
            rows_after = len(df)
            logger.info(f"    关联并筛选特定主体: {rows_before} -> {rows_after} 行 (排除了非陕西西咸新区的特定主体)")
        
        # 3. 计算单一债券规模限额适用类别
        def get_bond_limit_category(row):
            if row['债券分类2'] == '转债交债':
                return row.get('债券类型1', '')
            elif row.get('发行人类型_调整'):
                return row['发行人类型_调整']
            elif row.get('发行人类型'):
                return row['发行人类型']
            return ''
        
        df['单一债券规模限额适用类别_base'] = df.apply(get_bond_limit_category, axis=1)
        
        # 合并债券池（与 M 代码 Table.CombineColumns 一致：无条件用 "/" 连接，债券池为空时视为空串，结果带尾斜杠如 "国企/"）
        def _apply_bond_pool(row):
            base = row['单一债券规模限额适用类别_base']
            if pd.isna(base) or base == '':
                return base
            pool = row.get('债券池', '')
            if pd.isna(pool) or pool == '':
                pool = ''
            return f"{base}/{pool}"
        
        if '债券池' in df.columns:
            df['单一债券规模限额适用类别_base'] = df.apply(_apply_bond_pool, axis=1)
        else:
            df['单一债券规模限额适用类别_base'] = df['单一债券规模限额适用类别_base'].apply(
                lambda x: f"{x}/" if pd.notna(x) and x != '' else x
            )
        
        # 处理中债隐含评级
        df['单一债券规模限额适用类别'] = df.apply(
            lambda row: f"中债隐含评级{row['中债隐含评级']}" 
            if pd.notna(row.get('中债隐含评级')) and row['中债隐含评级'] in ['AAA', 'AAA+']
            else row['单一债券规模限额适用类别_base'],
            axis=1
        )
        
        df['单一债券集中度限额适用类别'] = df['单一债券规模限额适用类别']
        
        # 4. 关联单一债券规模限额
        df_bond_scale = self.cache.get('单一债券规模限额')
        if df_bond_scale is not None:
            df = df.merge(
                df_bond_scale[['日期', '指标名称', '指标值']],
                left_on=['日期', '单一债券规模限额适用类别'],
                right_on=['日期', '指标名称'],
                how='left'
            )
            df = df.drop(columns=['指标名称'], errors='ignore')
            df = df.rename(columns={'指标值': '单一债券规模限额指标值'})
            logger.info(f"    关联单一债券规模限额")
        
        # 5. 关联单一债券集中度限额
        df_bond_conc = self.cache.get('单一债券集中度限额')
        if df_bond_conc is not None:
            df = df.merge(
                df_bond_conc[['日期', '指标名称', '指标值']],
                left_on=['日期', '单一债券集中度限额适用类别'],
                right_on=['日期', '指标名称'],
                how='left'
            )
            df = df.drop(columns=['指标名称'], errors='ignore')
            df = df.rename(columns={'指标值': '单一债券集中度限额指标值'})
            logger.info(f"    关联单一债券集中度限额")
        
        # 6. 关联特批单一债券限额（优先级更高）
        df_special = self.cache.get('特批单一债券限额')
        if df_special is not None:
            df_special = df_special.copy()
            if '主证券代码_标准' not in df_special.columns and '主证券代码' in df_special.columns:
                df_special['主证券代码_标准'] = normalize_security_code_series(df_special['主证券代码'])
            df = df.merge(
                df_special[['日期', '主证券代码_标准', '规模指标值', '集中度指标值']],
                on=['日期', '主证券代码_标准'],
                how='left',
                suffixes=('', '_特批')
            )
            # 如果特批限额存在，使用特批限额覆盖
            df['单一债券规模限额指标值'] = df.apply(
                lambda row: row['规模指标值'] if pd.notna(row.get('规模指标值')) 
                else row.get('单一债券规模限额指标值'),
                axis=1
            )
            df = df.drop(columns=['规模指标值', '集中度指标值'], errors='ignore')
            logger.info(f"    关联特批单一债券限额")
        
        # 7. 计算单一主体限额适用类别（第一版）
        def calc_issuer_limit_category_1(row):
            # 优先使用中债隐含评级
            if pd.notna(row.get('中债隐含评级')) and row['中债隐含评级'] in ['AAA', 'AAA+']:
                return f"中债隐含评级{row['中债隐含评级']}"
            
            # 获取发行人类型
            issuer_type = row.get('发行人类型_调整', row.get('发行人类型', ''))
            
            # 只有当主体池不为空时才拼接
            pool = row.get('主体池')
            if pd.notna(pool) and pool != '':
                return f"{issuer_type}/{pool}"
            else:
                return issuer_type
        
        df['单一主体限额适用类别1'] = df.apply(calc_issuer_limit_category_1, axis=1)
        
        # 8. 关联单一主体规模限额（第一次：按单一主体限额适用类别1）
        df_issuer_limit = self.cache.get('单一主体规模限额')
        if df_issuer_limit is not None:
            df = df.merge(
                df_issuer_limit[['日期', '指标名称', '指标值']],
                left_on=['日期', '单一主体限额适用类别1'],
                right_on=['日期', '指标名称'],
                how='left',
                suffixes=('', '_merge1')
            )
            df = df.drop(columns=['指标名称'], errors='ignore')
            df = df.rename(columns={'指标值': '单一主体规模限额指标值1'})
            logger.info(f"    关联单一主体规模限额（第一次）")
        
        # 8.1 关联单一主体规模限额（第二次：按担保公司是否准入）
        if df_issuer_limit is not None and '担保公司是否准入' in df.columns:
            df = df.merge(
                df_issuer_limit[['日期', '指标名称', '指标值']],
                left_on=['日期', '担保公司是否准入'],
                right_on=['日期', '指标名称'],
                how='left',
                suffixes=('', '_merge2')
            )
            df = df.drop(columns=['指标名称'], errors='ignore')
            df = df.rename(columns={'指标值': '指标值_担保'})
            
            # 将null替换为0以便比较
            df['指标值_担保'] = df['指标值_担保'].fillna(0)
            df['单一主体规模限额指标值1'] = df['单一主体规模限额指标值1'].fillna(0)
            
            logger.info(f"    关联单一主体规模限额（第二次：按担保）")
        
        # 8.2 根据M-code第231行逻辑，选择单一主体限额适用类别
        # 完整逻辑：
        # if [特定主体指标名称] <> null then [特定主体指标名称]
        # else if Text.Contains([合并辅助列], "穿透") then [单一主体限额适用类别1]
        # else if [指标值] > [单一主体规模限额指标值1] then [担保公司是否准入]
        # else [单一主体限额适用类别1]
        def select_issuer_limit_category(row):
            # 1. 如果有特定主体指标名称，优先使用
            if pd.notna(row.get('特定主体指标名称')):
                return row['特定主体指标名称']
            
            # 2. 如果合并辅助列包含"穿透"，使用基础类别1（不进行担保比较）
            if pd.notna(row.get('合并辅助列')) and '穿透' in str(row.get('合并辅助列', '')):
                return row['单一主体限额适用类别1']
            
            # 3. 如果担保的指标值 > 基础指标值1，使用担保
            if pd.notna(row.get('指标值_担保')) and row.get('指标值_担保', 0) > row.get('单一主体规模限额指标值1', 0):
                return row.get('担保公司是否准入')
            
            # 4. 否则使用基础类别1
            return row['单一主体限额适用类别1']
        
        df['单一主体限额适用类别'] = df.apply(select_issuer_limit_category, axis=1)
        
        # 8.3 同样的逻辑选择指标值（但特定主体指标值和穿透的处理需要与特定主体限额指标值关联）
        def select_issuer_limit_value(row):
            # 1. 如果有特定主体指标名称，使用特定主体限额指标值
            if pd.notna(row.get('特定主体指标名称')) and pd.notna(row.get('特定主体限额指标值')):
                return row['特定主体限额指标值']
            
            # 2. 如果合并辅助列包含"穿透"，使用基础指标值1
            if pd.notna(row.get('合并辅助列')) and '穿透' in str(row.get('合并辅助列', '')):
                return row.get('单一主体规模限额指标值1')
            
            # 3. 如果担保的指标值 > 基础指标值1，使用担保指标值
            if pd.notna(row.get('指标值_担保')) and row.get('指标值_担保', 0) > row.get('单一主体规模限额指标值1', 0):
                return row.get('指标值_担保')
            
            # 4. 否则使用基础指标值1
            return row.get('单一主体规模限额指标值1')
        
        df['单一主体规模限额指标值'] = df.apply(select_issuer_limit_value, axis=1)
        
        # 清理中间列
        df = df.drop(columns=['单一主体限额适用类别1', '单一主体规模限额指标值1', '指标值_担保'], errors='ignore')
        
        logger.info(f"    计算单一主体限额适用类别完成")
        
        # 9. 关联各类总持仓
        # 9.1 单一债券总持仓
        df_bond_pos = self.cache.get('单一债券总持仓')
        if df_bond_pos is not None:
            df_bond_pos = df_bond_pos.copy()
            if SINGLE_BOND_GROUP_KEY_COL not in df_bond_pos.columns:
                df_bond_pos = ensure_single_bond_group_key(df_bond_pos)
            df = df.merge(
                df_bond_pos[
                    [
                        '日期', '业务分类', SINGLE_BOND_GROUP_KEY_COL,
                        '单一债券总持仓_PR', '单一债券集中度'
                    ]
                ],
                on=['日期', '业务分类', SINGLE_BOND_GROUP_KEY_COL],
                how='left'
            )
            logger.info(f"    关联单一债券总持仓")
        
        # 9.2 单一主体总持仓
        df_issuer_pos = self.cache.get('单一主体总持仓')
        if df_issuer_pos is not None:
            df = df.merge(
                df_issuer_pos[['日期', '业务分类', '债务主体', '单一主体总持仓_PR']],
                left_on=['日期', '业务分类', '债务主体'],
                right_on=['日期', '业务分类', '债务主体'],
                how='left'
            )
            logger.info(f"    关联单一主体总持仓")
        
        # 9.3 单一担保公司规模限额（根据M-code：通过单一主体限额适用类别、日期、担保人wind代码三列联合匹配）
        df_guarantee_limit = self.cache.get('单一担保公司规模限额')
        if df_guarantee_limit is not None and '担保人wind代码' in df.columns:
            # 验证行数，记录merge前的行数
            rows_before = len(df)
            
            df = df.merge(
                df_guarantee_limit[['是否准入', '日期', '指标名称', '指标值']],
                left_on=['单一主体限额适用类别', '日期', '担保人wind代码'],
                right_on=['是否准入', '日期', '指标名称'],
                how='left',
                suffixes=('', '_担保限额')
            )
            
            rows_after = len(df)
            if rows_after > rows_before * 1.1:  # 如果增长超过10%，警告可能的笛卡尔积
                logger.warning(f"    ⚠️ merge后行数从{rows_before}增至{rows_after}，可能存在问题")
            
            df = df.drop(columns=['是否准入', '指标名称'], errors='ignore')
            df = df.rename(columns={'指标值': '单一担保公司规模限额'}, errors='ignore')
            logger.info(f"    关联单一担保公司规模限额: {rows_before} -> {rows_after} 行")
        
        # 9.4 单一担保人总持仓（通过日期、业务分类、担保人wind代码三列联合匹配）
        df_guarantee_pos = self.cache.get('单一担保人总持仓')
        if df_guarantee_pos is not None and '担保人wind代码' in df.columns:
            rows_before = len(df)
            
            # 关键修复：去重，避免笛卡尔积（保留第一条记录）
            df_guarantee_pos_unique = df_guarantee_pos.drop_duplicates(
                subset=['日期', '业务分类', '担保人wind代码'], 
                keep='first'
            )
            
            df = df.merge(
                df_guarantee_pos_unique[['日期', '业务分类', '担保人wind代码', '单一担保人总持仓_PR']],
                on=['日期', '业务分类', '担保人wind代码'],
                how='left',
                suffixes=('', '_担保总持仓')
            )
            
            rows_after = len(df)
            if rows_after > rows_before * 1.1:
                logger.warning(f"    ⚠️ merge后行数从{rows_before}增至{rows_after}，可能存在问题")
            
            logger.info(f"    关联单一担保人总持仓: {rows_before} -> {rows_after} 行")
        
        # 9.5 关联单一实控人相关数据
        # page1/tab4 展示使用 1_2，因此这里应优先回挂“取最高额度”后的最终口径，
        # 以确保特定实控人特批、担保额度比较等覆盖逻辑真实反映到页面字段。
        df_controller_final = self.cache.get('限额明细_单一实控人_取最高额度')
        if df_controller_final is None or len(df_controller_final) == 0:
            df_controller_final = self.calculate_limit_detail_single_controller_max()
            if isinstance(df_controller_final, pd.DataFrame) and len(df_controller_final) > 0:
                self.cache['限额明细_单一实控人_取最高额度'] = df_controller_final

        if df_controller_final is not None and len(df_controller_final) > 0 and '实际控制人名称_修正' in df.columns:
            rows_before = len(df)
            df_controller_final = df_controller_final.drop_duplicates(
                subset=['日期', '业务分类', '实际控制人名称_修正'],
                keep='first'
            )
            df = df.merge(
                df_controller_final[
                    [
                        '日期', '业务分类', '实际控制人名称_修正',
                        '单一实控人限额适用类别', '单一实控人规模限额指标值',
                        '单一实控人总持仓_PR', '单一实控人规模剩余额度(万)',
                        '单一实控人是否超限'
                    ]
                ],
                on=['日期', '业务分类', '实际控制人名称_修正'],
                how='left',
                suffixes=('', '_实控人最终口径')
            )
            logger.info(f"    关联单一实控人最终口径: {rows_before} -> {len(df)} 行")
        else:
            logger.warning("    未找到单一实控人最终口径结果，1_2中的实控人字段可能无法体现特批优先覆盖")

        # M代码 Table.ReplaceValue(…, null, "否", …, {"单一实控人是否超限"})
        # Left Join 后匹配不到实控人限额的行（ETF、境外债等）值为 null，统一补"否"
        if '单一实控人是否超限' in df.columns:
            df['单一实控人是否超限'] = df['单一实控人是否超限'].fillna('否')

        # 9.6 从限额明细_特定主体获取特定主体限额指标值
        df_specific_issuer_detail = self.cache.get('限额明细_特定主体')
        if df_specific_issuer_detail is not None and len(df_specific_issuer_detail) > 0:
            df = df.merge(
                df_specific_issuer_detail[['业务分类', '资产代码', '日期', '特定主体限额指标值']],
                on=['业务分类', '资产代码', '日期'],
                how='left',
                suffixes=('', '_特定主体详情')
            )
            logger.info(f"    关联特定主体限额指标值")
        
        # 9.7 从限额明细_特定实控人获取特定实控人限额指标值
        df_specific_controller_detail = self.cache.get('限额明细_特定实控人')
        if df_specific_controller_detail is not None and len(df_specific_controller_detail) > 0:
            df = df.merge(
                df_specific_controller_detail[['业务分类', '资产代码', '日期', '特定实控人限额指标值']],
                on=['业务分类', '资产代码', '日期'],
                how='left',
                suffixes=('', '_特定实控人详情')
            )
            logger.info(f"    关联特定实控人限额指标值")
        
        # 10. 计算单一债券集中度总额度（根据M-code第222行）
        if '单一债券集中度限额指标值' in df.columns and '债券余额(亿)' in df.columns:
            df['单一债券集中度总额度'] = df['单一债券集中度限额指标值'] * df['债券余额(亿)'] * 10000
            logger.info(f"    计算单一债券集中度总额度")
        
        # 11. 计算剩余额度
        df['单一债券规模剩余额度(万)'] = df['单一债券规模限额指标值'] - df['单一债券总持仓_PR']
        
        if '单一债券集中度限额指标值' in df.columns and '债券余额(亿)' in df.columns:
            df['单一债券集中度剩余额度(万)'] = (
                df['债券余额(亿)'] * (df['单一债券集中度限额指标值'] - df['单一债券集中度']) * 10000
            )
        
        df['单一主体规模剩余额度(万)'] = df['单一主体规模限额指标值'] - df['单一主体总持仓_PR']
        
        # 计算单一实控人规模剩余额度
        # 优先保留“取最高额度”回挂的最终结果；仅在缺失时兜底重算。
        if '单一实控人规模剩余额度(万)' not in df.columns and '单一实控人规模限额指标值' in df.columns and '单一实控人总持仓_PR' in df.columns:
            df['单一实控人规模剩余额度(万)'] = df['单一实控人规模限额指标值'] - df['单一实控人总持仓_PR']
        
        # 计算单一担保公司规模剩余额度
        if '单一担保公司规模限额' in df.columns and '单一担保人总持仓_PR' in df.columns:
            df['单一担保公司规模剩余额度(万)'] = df['单一担保公司规模限额'] - df['单一担保人总持仓_PR']
        
        # 11. 判断是否超限
        def check_bond_over_limit(row):
            if row.get('是否属于高收益') == '是':
                return '否'
            if '穿透' in str(row.get('合并辅助列', '')):
                return '否'
            if pd.isna(row.get('单一债券规模剩余额度(万)')):
                return '否'
            return '是' if row['单一债券规模剩余额度(万)'] < 0 else '否'
        
        def check_bond_concentration_over_limit(row):
            if row.get('是否属于高收益') == '是':
                return '否'
            if '穿透' in str(row.get('合并辅助列', '')):
                return '否'
            if pd.isna(row.get('单一债券集中度剩余额度(万)')):
                return '否'
            return '是' if row['单一债券集中度剩余额度(万)'] < 0 else '否'
        
        def check_issuer_over_limit(row):
            if row.get('是否属于高收益') == '是':
                return '否'
            if pd.isna(row.get('单一主体规模剩余额度(万)')):
                return '否'
            return '是' if row['单一主体规模剩余额度(万)'] < 0 else '否'
        
        df['单一债券是否超限'] = df.apply(check_bond_over_limit, axis=1)
        df['单一债券集中度是否超限'] = df.apply(check_bond_concentration_over_limit, axis=1)
        df['单一主体是否超限'] = df.apply(check_issuer_over_limit, axis=1)
        
        # 判断单一担保人是否超限
        def check_guarantee_over_limit(row):
            if pd.isna(row.get('单一担保公司规模剩余额度(万)')):
                return '否'
            return '是' if row['单一担保公司规模剩余额度(万)'] < 0 else '否'
        
        if '单一担保公司规模剩余额度(万)' in df.columns:
            df['单一担保人是否超限'] = df.apply(check_guarantee_over_limit, axis=1)
        
        # 判断单一实控人是否超限
        def check_controller_over_limit(row):
            if pd.isna(row.get('单一实控人规模剩余额度(万)')):
                return '否'
            return '是' if row['单一实控人规模剩余额度(万)'] < 0 else '否'
        
        if '单一实控人是否超限' not in df.columns and '单一实控人规模剩余额度(万)' in df.columns:
            df['单一实控人是否超限'] = df.apply(check_controller_over_limit, axis=1)
        
        # 12. 综合判断是否超限
        # 综合口径按 5 个维度汇总：债券规模、债券集中度、主体、实控人、担保人
        df['是否超限'] = df.apply(
            lambda row: '是' if '是' in [
                row.get('单一债券是否超限'),
                row.get('单一债券集中度是否超限'),
                row.get('单一主体是否超限'),
                row.get('单一实控人是否超限'),
                row.get('单一担保人是否超限')
            ] else '否',
            axis=1
        )
        
        # 13. 删除中间计算列
        columns_to_drop = ['单一债券规模限额适用类别_base', '调整后实际控制人', SOURCE_ROW_ID_COL]
        df = df.drop(columns=columns_to_drop, errors='ignore')
        
        logger.info(f"  限额明细计算完成: {len(df)} 行")
        
        return df
    
    def calculate_limit_detail_single_bond(self) -> pd.DataFrame:
        """
        查询: 限额明细_单一债券
        按M代码完整实现：分组后与限额明细1_2合并，展开限额字段
        
        M代码关键逻辑（第729-806行）:
        1. 源=债券持仓明细表，按修正后的高收益口径排除高收益后筛选非利率债
        2. 分组：日期+主证券代码+主证券名称
        3. 与"限额明细_债券持仓明细表_信用债1_2"按(日期+主证券代码)左连接
        4. 展开限额相关列（单一债券规模/集中度限额、超限判断）
        5. 去重，筛选单一债券规模限额适用类别不为null
        """
        # 与 Excel M-code 一致：单一债券明细从原始“债券持仓明细表”取数；
        # 高收益剔除由统一过滤器按修正后的识别口径补足。
        df = self.cache.get('债券持仓明细表')
        if df is None:
            return pd.DataFrame()
        
        df = df.copy()

        if '主证券代码_标准' not in df.columns and '主证券代码' in df.columns:
            df['主证券代码_标准'] = normalize_security_code_series(df['主证券代码'])
        
        # 【P1-5修复1】排除高收益（M代码第735-736行）
        df = self._filter_non_high_yield_rows(df)
        
        # 筛选非利率债（M代码第738-739行）
        df = df[df['债券分类2'] != '利率债']
        
        # 【P1-5修复2】分组计算单一债券总持仓和集中度（M代码第741-745行）
        if '主证券代码' in df.columns and '主证券代码_标准' in df.columns:
            df['_主证券代码_已标准化'] = df['主证券代码'] == df['主证券代码_标准']
            df = df.sort_values(
                ['日期', '主证券代码_标准', '_主证券代码_已标准化'],
                ascending=[True, True, False]
            )

        for col in ['库存数量(万)_PR', '债券余额(亿)']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        aggregation_map = {
            '主证券代码': 'first',
            '库存数量(万)_PR': 'sum',
            '债券余额(亿)': 'mean'
        }
        for optional_col in ['资产代码', '资产名称', '债务主体', '债券分类2']:
            if optional_col in df.columns:
                aggregation_map[optional_col] = 'first'

        result = df.groupby(['日期', '主证券代码_标准', '主证券名称'], as_index=False).agg(aggregation_map)
        
        result = result.rename(columns={
            '库存数量(万)_PR': '单一债券总持仓_PR'
        })
        
        # 计算集中度（M代码第744-745行）
        result['单一债券集中度'] = result['单一债券总持仓_PR'] / result['债券余额(亿)'] * 0.0001

        # 替换错误值为null（M代码第750-751行）
        result['单一债券集中度'] = result['单一债券集中度'].replace([float('inf'), -float('inf')], None)

        # 监管集中度：单债整体口径，不区分内部证券账户，限额来自系统参数 sheet
        regulatory_limit = self._load_regulatory_concentration_limit()
        result['监管集中度限额指标值'] = regulatory_limit
        result['监管集中度'] = result['单一债券集中度']
        result['监管集中度总额度'] = result['监管集中度限额指标值'] * result['债券余额(亿)'] * 10000
        result['监管集中度剩余额度(万)'] = (
            result['债券余额(亿)'] * (result['监管集中度限额指标值'] - result['监管集中度']) * 10000
        )
        result['监管集中度是否超限'] = result['监管集中度剩余额度(万)'].apply(
            lambda x: '是' if pd.notna(x) and x < 0 else '否'
        )
        result['是否超限'] = result['监管集中度是否超限']
        
        # 排序（M代码第753-754行）
        result = result.sort_values('单一债券集中度', ascending=False, na_position='last')
        
        # 【P1-5修复3】与"限额明细_债券持仓明细表_信用债1_2"合并（M代码第756-769行）
        df_limit_detail = self.cache.get('限额明细_债券持仓明细表_信用债1_2')
        if df_limit_detail is not None:
            df_limit_detail = df_limit_detail.copy()
            if '主证券代码_标准' not in df_limit_detail.columns and '主证券代码' in df_limit_detail.columns:
                df_limit_detail['主证券代码_标准'] = normalize_security_code_series(df_limit_detail['主证券代码'])
            result = result.merge(
                df_limit_detail[[
                    '日期', '主证券代码_标准',
                    '单一债券规模限额适用类别', '单一债券规模限额指标值',
                    '单一债券规模剩余额度(万)', '单一债券是否超限',
                    '单一债券集中度限额适用类别', '单一债券集中度限额指标值',
                    '单一债券集中度剩余额度(万)', '单一债券集中度是否超限'
                ]],
                on=['日期', '主证券代码_标准'],
                how='left'
            )
            logger.info(f"    与限额明细1_2合并: 展开限额字段")
        
        # 替换null为空字符串（M代码第775-776行）
        if '单一债券集中度是否超限' in result.columns:
            result['单一债券集中度是否超限'] = result['单一债券集中度是否超限'].fillna('')
        
        # 【P1-5修复4】去重（M代码第778行）
        result = result.drop_duplicates()
        
        # 重命名列（M代码第780-781行）
        result = result.rename(columns={
            '主证券代码_标准': '证券代码',
            '主证券代码': '证券代码_原始',
            '主证券名称': '证券名称'
        })
        
        # 保留债券余额(亿)供监管集中度展示使用
        result = result.drop(columns=['_主证券代码_已标准化'], errors='ignore')
        
        # 【P1-5修复5】筛选：单一债券规模限额适用类别不为null（M代码第801-802行）
        if '单一债券规模限额适用类别' in result.columns:
            result = result[result['单一债券规模限额适用类别'].notna()]
        
        logger.info(f"  限额明细_单一债券（按M代码完整实现）: {len(result)} 行")
        
        return result
    
    def calculate_limit_detail_single_issuer(self) -> pd.DataFrame:
        """
        查询: 限额明细_单一主体
        按M代码完整实现：分组后与限额明细1_2合并，展开限额字段
        
        M代码关键逻辑（第808-847行）:
        1. 源=债券持仓明细表_信用债，排除高收益
        2. 分组：日期+债务主体wind代码+债务主体
        3. 与"限额明细_债券持仓明细表_信用债1_2"按(日期+债务主体wind代码)左连接
        4. 展开限额相关列（单一主体限额、超限判断）
        5. 去重
        """
        df = self.cache.get('债券持仓明细表_信用债')
        if df is None:
            return pd.DataFrame()
        
        # 【P1-5修复1】排除高收益（M代码第814-815行）
        df = self._filter_non_high_yield_rows(df)
        
        # 【P1-5修复2】分组计算（M代码第817-819行）
        result = df.groupby(['日期', '债务主体wind代码', '债务主体'], as_index=False).agg({
            '库存数量(万)_PR': 'sum'
        })
        
        result = result.rename(columns={'库存数量(万)_PR': '单一主体总持仓_PR'})
        
        # 【P1-5修复3】与"限额明细_债券持仓明细表_信用债1_2"合并（M代码第825-835行）
        df_limit_detail = self.cache.get('限额明细_债券持仓明细表_信用债1_2')
        if df_limit_detail is not None:
            result = result.merge(
                df_limit_detail[[
                    '日期', '债务主体wind代码',
                    '单一主体是否超限', '单一主体限额适用类别',
                    '单一主体规模限额指标值', '单一主体规模剩余额度(万)'
                ]],
                on=['日期', '债务主体wind代码'],
                how='left'
            )
            logger.info(f"    与限额明细1_2合并: 展开限额字段")
        
        # 【P1-5修复4】去重（M代码第837-838行）
        result = result.drop_duplicates()
        
        logger.info(f"  限额明细_单一主体（按M代码完整实现）: {len(result)} 行")
        
        return result

    def calculate_limit_detail_full_regulatory_concentration(self) -> pd.DataFrame:
        """
        查询: 限额明细_全量债券监管集中度

        口径：
        1. 基于 SPPI 全量债券表
        2. 不做高收益/利率债等业务剔除
        3. 单债归并优先级：主证券代码_标准 -> ISIN码 -> 缺归并主键（保留展示）
        4. 债券余额缺失时保留展示，但标记不可计算
        """
        df = self.cache.get('债券持仓明细表_全量债券监管集中度')
        if df is None or df.empty:
            return pd.DataFrame()

        df = df.copy()

        for col in ['库存数量(万)_PR', '债券余额(亿)']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        if '主证券代码_标准' not in df.columns and '主证券代码' in df.columns:
            df['主证券代码_标准'] = normalize_security_code_series(df['主证券代码'])

        if 'ISIN码' in df.columns:
            df['ISIN码'] = df['ISIN码'].apply(
                lambda x: None if pd.isna(x) or str(x).strip() in ['', 'nan', 'None', '<NA>'] else str(x).strip()
            )

        if '主证券代码_标准' in df.columns:
            df['主证券代码_标准'] = df['主证券代码_标准'].apply(
                lambda x: None if pd.isna(x) or str(x).strip() in ['', 'nan', 'None', '<NA>'] else str(x).strip()
            )

        df['归并主键来源'] = np.select(
            [
                df.get('主证券代码_标准', pd.Series(index=df.index)).notna(),
                df.get('ISIN码', pd.Series(index=df.index)).notna(),
            ],
            ['主证券代码_标准', 'ISIN码'],
            default='缺归并主键'
        )

        df['监管归并主键'] = np.where(
            df['归并主键来源'] == '主证券代码_标准',
            df['主证券代码_标准'],
            np.where(
                df['归并主键来源'] == 'ISIN码',
                df['ISIN码'],
                None
            )
        )

        missing_key_mask = df['监管归并主键'].isna()
        df.loc[missing_key_mask, '监管归并主键'] = df.loc[missing_key_mask].index.map(lambda idx: f"MISSING_KEY::{idx}")

        aggregation_map = {'库存数量(万)_PR': 'sum'}
        first_cols = [
            '主证券代码_标准', 'ISIN码', '资产代码', '资产名称', '主证券代码', '主证券名称', '债务主体',
            '债券分类2', '债券类型1', '金融资产会计属性', '部门', '发行人类型', '是否城投债',
            '债券类别', 'wind行业', '省份', '债务主体wind代码', '担保人', '担保人wind代码',
            '实际控制人名称_修正', '实际控制人名称', '归并主键来源'
        ]
        for col in first_cols:
            if col in df.columns:
                aggregation_map[col] = self._first_non_null

        if '债券余额(亿)' in df.columns:
            aggregation_map['债券余额(亿)'] = self._first_non_null
        if '内部证券账户名称' in df.columns:
            aggregation_map['内部证券账户名称'] = lambda s: "、".join(sorted({str(v).strip() for v in s.dropna() if str(v).strip()}))

        result = df.groupby(['日期', '监管归并主键'], as_index=False).agg(aggregation_map)
        result = result.rename(columns={'库存数量(万)_PR': '单债总持仓_PR'})

        if '内部证券账户名称' in df.columns:
            account_count_df = (
                df.groupby(['日期', '监管归并主键'])['内部证券账户名称']
                .apply(lambda s: s.dropna().astype(str).str.strip().replace('', np.nan).dropna().nunique())
                .reset_index(name='内部证券账户覆盖数')
            )
            result = result.merge(account_count_df, on=['日期', '监管归并主键'], how='left')

        limit_value = self._load_regulatory_concentration_limit()
        result['监管集中度限额指标值'] = limit_value

        def build_reason(row):
            reasons = []
            if row.get('归并主键来源') == '缺归并主键':
                reasons.append('缺归并主键')
            balance = row.get('债券余额(亿)')
            if pd.isna(balance) or balance <= 0:
                reasons.append('缺债券余额')
            return '、'.join(reasons) if reasons else None

        result['不可计算原因'] = result.apply(build_reason, axis=1)
        result['是否可计算'] = result['不可计算原因'].isna().map({True: '是', False: '否'})

        computable_mask = result['是否可计算'] == '是'
        result['监管集中度'] = np.nan
        result['监管集中度总额度'] = np.nan
        result['监管集中度剩余额度(万)'] = np.nan
        result.loc[computable_mask, '监管集中度'] = (
            result.loc[computable_mask, '单债总持仓_PR'] /
            result.loc[computable_mask, '债券余额(亿)'] * 0.0001
        )
        result.loc[computable_mask, '监管集中度总额度'] = (
            result.loc[computable_mask, '监管集中度限额指标值'] *
            result.loc[computable_mask, '债券余额(亿)'] * 10000
        )
        result.loc[computable_mask, '监管集中度剩余额度(万)'] = (
            result.loc[computable_mask, '债券余额(亿)'] *
            (result.loc[computable_mask, '监管集中度限额指标值'] - result.loc[computable_mask, '监管集中度']) *
            10000
        )

        result['监管集中度是否超限'] = ''
        result.loc[computable_mask, '监管集中度是否超限'] = result.loc[
            computable_mask, '监管集中度剩余额度(万)'
        ].apply(lambda x: '是' if pd.notna(x) and x < 0 else '否')
        result['是否超限'] = result['监管集中度是否超限']

        sort_cols = ['日期']
        if '监管集中度' in result.columns:
            result = result.sort_values(['日期', '监管集中度'], ascending=[False, False], na_position='last')

        logger.info(f"  限额明细_全量债券监管集中度: {len(result)} 行")
        return result
    
    def calculate_limit_detail_specific_issuer(self) -> pd.DataFrame:
        """
        查询: 限额明细_特定主体
        基于债券持仓明细表_信用债_合并风险限额相关，关联特定主体限额
        """
        df = self.cache.get('债券持仓明细表_信用债_合并风险限额相关')
        if df is None:
            return pd.DataFrame()
        
        # 排除高收益和关注池
        df = self._filter_non_high_yield_rows(df)
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
            
            # 筛选有特定主体限额的记录
            df = df[df['指标名称'].notna()]
            
            # 添加业务分类
            df['业务分类'] = df['内部证券账户名称'].apply(
                lambda x: '做市业务' if x == '做市交易部做市业务' else '自营业务'
            )
            
            # 分组计算
            result = df.groupby(['日期', '业务分类', '指标名称', '债务主体wind代码', 
                                '债务主体', '资产代码', '资产名称'], as_index=False).agg({
                '库存数量(万)_PR': 'sum',
                '指标值': 'mean'
            })
            
            result = result.rename(columns={
                '库存数量(万)_PR': '库存数量(万)_PR',
                '指标值': '特定主体限额指标值'
            })
            
            # 关联特定主体总持仓
            df_total = self.cache.get('特定主体总持仓')
            if df_total is not None:
                result = result.merge(
                    df_total[['日期', '业务分类', '特定主体名称', '特定主体总持仓']],
                    left_on=['日期', '业务分类', '指标名称'],
                    right_on=['日期', '业务分类', '特定主体名称'],
                    how='left'
                )
                result = result.drop(columns=['特定主体名称'], errors='ignore')
                
                # 计算剩余额度
                result['特定主体限额剩余额度'] = result['特定主体限额指标值'] - result['特定主体总持仓']
                
                # 判断是否超限
                result['特定主体限额是否超限'] = result['特定主体限额剩余额度'].apply(
                    lambda x: '是' if pd.notna(x) and x < 0 else '否'
                )
            
            logger.info(f"  限额明细_特定主体: {len(result)} 行")
            
            return result
        
        return pd.DataFrame()
    
    def calculate_limit_detail_specific_controller(self) -> pd.DataFrame:
        """
        查询: 限额明细_特定实控人
        按M代码完整实现：仅排除高收益（不排除关注池）
        
        M代码关键逻辑（第907-958行）:
        1. 源=债券持仓明细表_信用债_合并风险限额相关
        2. 仅排除高收益（不排除关注池）
        3. 与特定实控人限额合并
        4. 筛选：指标名称不为null且不为空字符串
        5. 分组键包含：日期、业务分类、指标名称、实控人名称、债务主体、资产代码、资产名称
        """
        df = self.cache.get('债券持仓明细表_信用债_合并风险限额相关')
        if df is None:
            return pd.DataFrame()

        # 【P1-5修复】仅排除高收益（M代码第913-914行，未排除关注池）
        df = self._filter_non_high_yield_rows(df)
        
        # 与特定实控人限额关联（M代码第916-922行）
        df_limit = self.cache.get('特定实控人限额')
        if df_limit is not None:
            df = df.merge(
                df_limit[['实控人名称', '日期', '指标名称', '指标值']],
                left_on=['实际控制人名称_修正', '日期'],
                right_on=['实控人名称', '日期'],
                how='left'
            )
            
            # 筛选有特定实控人限额的记录（M代码第924-925行）
            df = df[(df['指标名称'].notna()) & (df['指标名称'] != '')]
            
            # 添加业务分类（M代码第927-929行）
            df['业务分类'] = df['内部证券账户名称'].apply(
                lambda x: '做市业务' if x == '做市交易部做市业务' else '自营业务'
            )
            
            # 分组计算（M代码第931-934行）
            # 注意：M代码分组键使用"实控人名称"（即从特定实控人限额表来的列）
            result = df.groupby(['日期', '业务分类', '指标名称', '实控人名称',
                                '债务主体', '资产代码', '资产名称'], as_index=False).agg({
                '库存数量(万)_PR': 'sum',
                '指标值': 'mean'
            })
            
            result = result.rename(columns={
                '指标值': '特定实控人限额指标值'
            })
            
            # 关联特定实控人总持仓（M代码第936-941行）
            df_total = self.cache.get('特定实控人总持仓')
            if df_total is not None:
                result = result.merge(
                    df_total[['日期', '业务分类', '特定实控人名称', '特定实控人总持仓']],
                    left_on=['日期', '业务分类', '实控人名称'],
                    right_on=['日期', '业务分类', '特定实控人名称'],
                    how='left'
                )
                result = result.drop(columns=['特定实控人名称'], errors='ignore')
                
                # 计算剩余额度（M代码第943-945行）
                result['特定实控人限额剩余额度'] = result['特定实控人限额指标值'] - result['特定实控人总持仓']
                
                # 判断是否超限（M代码第947-948行）
                result['特定实控人限额是否超限'] = result['特定实控人限额剩余额度'].apply(
                    lambda x: '是' if pd.notna(x) and x < 0 else '否'
                )
            
            logger.info(f"  限额明细_特定实控人（按M代码完整实现）: {len(result)} 行")
            
            return result
        
        return pd.DataFrame()
    
    def calculate_limit_detail_single_controller(self) -> pd.DataFrame:
        """
        查询: 限额明细_单一实控人
        按M代码实现：实控人维度汇总后关联1_2限额字段
        """
        df = self.cache.get('债券持仓明细表_信用债_合并风险限额相关')
        if df is None:
            return pd.DataFrame()

        # M-code 仅排除高收益；这里仅替换为修正后的高收益识别口径。
        df = self._filter_non_high_yield_rows(df)

        if df.empty:
            return pd.DataFrame()

        df = df.copy()
        df['库存数量(万)_PR'] = pd.to_numeric(df['库存数量(万)_PR'], errors='coerce')

        result = df.groupby(['日期', '实际控制人名称_修正'], as_index=False).agg({
            '库存数量(万)_PR': 'sum'
        })
        result = result.rename(columns={'库存数量(万)_PR': '单一实控人总持仓_PR'})
        result = result[result['实际控制人名称_修正'].notna()]

        df_limit_detail = self.cache.get('限额明细_债券持仓明细表_信用债1_2')
        if df_limit_detail is not None and len(df_limit_detail) > 0:
            limit_cols = [
                '日期',
                '实际控制人名称_修正',
                '单一实控人规模限额指标值',
                '单一实控人规模剩余额度(万)',
            ]
            category_col = None
            for candidate in ['单一主体/实控人限额适用类别', '单一实控人限额适用类别']:
                if candidate in df_limit_detail.columns:
                    category_col = candidate
                    limit_cols.append(candidate)
                    break

            limit_cols = [col for col in limit_cols if col in df_limit_detail.columns]
            result = result.merge(
                df_limit_detail[limit_cols],
                on=['日期', '实际控制人名称_修正'],
                how='left'
            )
            result = result.drop_duplicates()

            agg_dict = {'单一实控人总持仓_PR': 'mean'}
            if '单一实控人规模限额指标值' in result.columns:
                agg_dict['单一实控人规模限额指标值'] = 'max'
            if '单一实控人规模剩余额度(万)' in result.columns:
                agg_dict['单一实控人规模剩余额度(万)'] = 'max'

            result = (
                result.sort_values(['实际控制人名称_修正'])
                .groupby(['日期', '实际控制人名称_修正'], as_index=False)
                .agg(agg_dict)
            )

        logger.info(f"  限额明细_单一实控人: {len(result)} 行")

        return result
    
    def calculate_limit_detail_single_controller_max(self) -> pd.DataFrame:
        """
        查询: 限额明细_单一实控人_取最高额度
        按M代码完整实现：排序后分组取index=0，确保类别/指标值/总持仓来自同一行
        
        M代码关键逻辑:
        1. 仅排除高收益（不排除关注池）
        2. 处理转债交债分支 -> 可转换债、可交换债
        3. 两次合并单一实控人规模限额（类别+担保准入），比较后取较大值
        4. 合并特定实控人限额，优先使用特批
        5. 排序：日期降序、实控人升序、限额指标值降序
        6. 分组取index=0（每组第一条，即最高额度对应行）
        7. 过滤：实控人名称 != "0" 且 != ""
        """
        # 【P1-2修复1】从债券持仓明细表_信用债_合并风险限额相关开始，仅排除高收益
        df = self.cache.get('债券持仓明细表_信用债_合并风险限额相关')
        if df is None:
            logger.error("债券持仓明细表_信用债_合并风险限额相关未找到")
            return pd.DataFrame()
        
        df = df.copy()
        
        # 筛选：仅排除高收益（M代码第966-967行）
        df = self._filter_non_high_yield_rows(df)
        logger.info(f"  筛选非高收益: {len(df)} 行")
        
        # 【P1-2修复2】补全转债交债分支
        # M代码第969-972行：if [债券分类2] = "转债交债" then "可转换债、可交换债"
        def get_custom_category(row):
            if row.get('债券分类2') == '转债交债':
                return '可转换债、可交换债'
            elif row.get('发行人类型_调整') == '国企':
                return '国企'
            elif row.get('发行人类型_调整') == '非国企':
                return '非国企'
            else:
                return None
        
        df['自定义'] = df.apply(get_custom_category, axis=1)
        
        # 复制债券池列（M代码第974-975行）
        if '债券池' in df.columns:
            df['债券池_复制'] = df['债券池']
        
        # 【P1-2修复3】计算单一实控人限额适用类别（M代码第977-980行）
        def calc_controller_limit_category(row):
            if row.get('中债隐含评级') == 'AAA':
                return '中债隐含评级AAA'
            elif row.get('中债隐含评级') == 'AAA+':
                return '中债隐含评级AAA+'
            else:
                # 使用发行人类型_调整和主体池拼接
                issuer_type = row.get('发行人类型_调整', '')
                pool = row.get('主体池', '')
                if pd.notna(issuer_type) and pd.notna(pool):
                    return f"{issuer_type}/{pool}"
                elif pd.notna(issuer_type):
                    return issuer_type
                else:
                    return ''
        
        df['单一实控人限额适用类别'] = df.apply(calc_controller_limit_category, axis=1)
        
        # 【P1-2修复4】第一次合并：按单一实控人限额适用类别（M代码第985-990行）
        df_controller_limit = self.cache.get('单一实控人规模限额')
        if df_controller_limit is not None:
            df = df.merge(
                df_controller_limit[['日期', '指标名称', '指标值']],
                left_on=['单一实控人限额适用类别', '日期'],
                right_on=['指标名称', '日期'],
                how='left'
            )
            df = df.drop(columns=['指标名称'], errors='ignore')
            df = df.rename(columns={'指标值': '单一实控人规模限额指标值1'})
        
        # 【P1-2修复5】第二次合并：按担保公司是否准入（M代码第992-997行）
        if df_controller_limit is not None and '担保公司是否准入' in df.columns:
            df = df.merge(
                df_controller_limit[['日期', '指标名称', '指标值']],
                left_on=['担保公司是否准入', '日期'],
                right_on=['指标名称', '日期'],
                how='left'
            )
            df = df.drop(columns=['指标名称'], errors='ignore')
            df = df.rename(columns={'指标值': '指标值_担保'})
            
            # 替换null为0（M代码第999-1000行）
            df['指标值_担保'] = df['指标值_担保'].fillna(0)
            df['单一实控人规模限额指标值1'] = df['单一实控人规模限额指标值1'].fillna(0)
        
        # 重命名列（M代码第1002-1005行）
        df = df.rename(columns={
            '单一实控人规模限额指标值1': '单一实控人规模限额指标值1_renamed',
            '单一实控人限额适用类别': '单一实控人限额适用类别1'
        })
        
        # 【P1-2修复6】合并特定实控人限额（M代码第1007-1017行）
        df_specific_controller = self.cache.get('特定实控人限额')
        if df_specific_controller is not None:
            df = df.merge(
                df_specific_controller[['日期', '实控人名称', '指标名称', '指标值']],
                left_on=['日期', '实际控制人名称_修正'],
                right_on=['日期', '实控人名称'],
                how='left'
            )
            df = df.drop(columns=['实控人名称'], errors='ignore')
            df = df.rename(columns={
                '指标名称': '特批实控人指标名称',
                '指标值': '特批实控人指标值'
            })
        
        # 【P1-2修复7】条件列：选择最终的单一实控人限额适用类别（M代码第1019-1022行）
        # if [特批实控人指标名称] <> null then [特批实控人指标名称]
        # else if [指标值] > [单一实控人规模限额指标值1] then [担保公司是否准入]
        # else [单一实控人限额适用类别1]
        def select_final_category(row):
            if pd.notna(row.get('特批实控人指标名称')):
                return row['特批实控人指标名称']
            elif row.get('指标值_担保', 0) > row.get('单一实控人规模限额指标值1_renamed', 0):
                return row.get('担保公司是否准入', '')
            else:
                return row.get('单一实控人限额适用类别1', '')
        
        df['单一实控人限额适用类别'] = df.apply(select_final_category, axis=1)
        
        # 【P1-2修复8】条件列：选择最终的单一实控人规模限额指标值（M代码第1024-1028行）
        def select_final_value(row):
            if pd.notna(row.get('特批实控人指标值')):
                return row['特批实控人指标值']
            elif row.get('指标值_担保', 0) > row.get('单一实控人规模限额指标值1_renamed', 0):
                return row.get('指标值_担保', 0)
            else:
                return row.get('单一实控人规模限额指标值1_renamed', 0)
        
        df['单一实控人规模限额指标值'] = df.apply(select_final_value, axis=1)
        
        # 添加业务分类（M代码第1030-1032行）
        df['业务分类'] = df['内部证券账户名称'].apply(
            lambda x: '做市业务' if x == '做市交易部做市业务' else '自营业务'
        )
        
        # 选择需要的列（M代码第1034-1036行）
        df = df[['日期', '实际控制人名称_修正', '单一实控人限额适用类别', 
                '单一实控人规模限额指标值', '业务分类']].copy()
        
        # 筛选：实控人名称不为null（M代码第1038-1039行）
        df = df[df['实际控制人名称_修正'].notna()]
        
        # 【P1-2修复9】合并单一实控人总持仓（M代码第1041-1048行）
        df_controller_pos = self.cache.get('单一实控人总持仓')
        if df_controller_pos is not None:
            df = df.merge(
                df_controller_pos[['日期', '业务分类', '实际控制人名称_修正', '单一实控人总持仓_PR']],
                on=['日期', '业务分类', '实际控制人名称_修正'],
                how='left'
            )
        
        # 【P1-2修复10】排序（M代码第1054-1056行）
        # 关键：按日期降序、实控人升序、单一实控人规模限额指标值降序
        df = df.sort_values(
            by=['日期', '实际控制人名称_修正', '单一实控人规模限额指标值'],
            ascending=[False, True, False]
        ).reset_index(drop=True)
        
        logger.info(f"  排序完成: 日期降序、实控人升序、限额指标值降序")
        
        # 【P1-2修复11】分组并添加索引（M代码第1058-1069行）
        # 分组键：日期、业务分类、实际控制人名称_修正
        # 每组添加索引（0, 1, 2...），然后只保留索引=0的记录
        df['分组索引'] = df.groupby(['日期', '业务分类', '实际控制人名称_修正']).cumcount()
        
        # 筛选：只保留分组索引=0的记录（M代码第1076-1077行）
        df = df[df['分组索引'] == 0].copy()
        
        logger.info(f"  分组取index=0: {len(df)} 行（每个实控人保留最高额度对应行）")
        
        # 计算剩余额度（M代码第1079-1081行）
        df['单一实控人规模剩余额度(万)'] = df['单一实控人规模限额指标值'] - df['单一实控人总持仓_PR']
        
        # 判断是否超限（M代码第1083-1084行）
        df['单一实控人是否超限'] = df['单一实控人规模剩余额度(万)'].apply(
            lambda x: '是' if pd.notna(x) and x < 0 else '否'
        )
        
        # 【P1-2修复12】过滤：实控人名称不为"0"且不为空字符串（M代码第1090-1096行）
        df = df[
            (df['实际控制人名称_修正'] != '0') &
            (df['实际控制人名称_修正'] != '') &
            (df['实际控制人名称_修正'].notna())
        ]
        
        # 删除分组索引列（M代码第1093行）
        df = df.drop(columns=['分组索引'], errors='ignore')
        
        logger.info(f"  限额明细_单一实控人_取最高额度（按M代码完整实现）: {len(df)} 行")
        
        return df
    
    def calculate_limit_detail_single_guarantee(self) -> pd.DataFrame:
        """
        查询: 限额明细_单一担保人
        基于限额明细_债券持仓明细表_信用债1_2，按担保人分组聚合
        M代码逻辑：
        1. 筛选单一主体限额适用类别包含"担保"的记录
        2. 按日期、业务分类、担保人wind代码、担保人分组
        3. 对限额和持仓取平均值
        4. 合并单一担保公司规模限额表获取授信担保公司名称
        5. 重新计算剩余额度
        """
        # 源数据：限额明细_债券持仓明细表_信用债1_2
        df = self.cache.get('限额明细_债券持仓明细表_信用债1_2')
        if df is None:
            return pd.DataFrame()
        
        df = df.copy()
        
        # 步骤1: 筛选单一主体限额适用类别包含"担保"
        # 这一步与Excel M代码一致：Table.SelectRows(源, each Text.Contains([单一主体限额适用类别], "担保"))
        if '单一主体限额适用类别' in df.columns:
            df = df[df['单一主体限额适用类别'].str.contains('担保', na=False)]
        else:
            logger.warning("  ⚠️ 缺少'单一主体限额适用类别'列，无法筛选")
            return pd.DataFrame()
        
        # 步骤2: 按日期、业务分类、担保人wind代码、担保人分组，取平均值
        # Excel M代码：Table.Group(..., {{"单一担保人总持仓_PR", each List.Average([单一担保人总持仓_PR])...
        # 注意：直接使用merge进来的"单一担保人总持仓_PR"，不重新计算
        group_cols = ['日期', '业务分类', '担保人wind代码', '担保人']
        agg_dict = {
            '单一担保公司规模限额': 'mean',
            '单一担保人总持仓_PR': 'mean',
            '单一担保公司规模剩余额度(万)': 'mean'
        }
        
        # 只保留存在的列
        agg_dict = {k: v for k, v in agg_dict.items() if k in df.columns}
        
        if not agg_dict:
            logger.warning("  ⚠️ 缺少必要的聚合列")
            return pd.DataFrame()
        
        df_grouped = df.groupby(group_cols, as_index=False).agg(agg_dict)
        
        # 筛选：单一担保公司规模限额不为空
        if '单一担保公司规模限额' in df_grouped.columns:
            df_grouped = df_grouped[df_grouped['单一担保公司规模限额'].notna()]
        
        # 步骤4: 合并单一担保公司规模限额表，获取"授信担保公司名称"
        df_guarantee_limit = self.cache.get('单一担保公司规模限额')
        if df_guarantee_limit is not None and '担保人wind代码' in df_grouped.columns:
            df_grouped = df_grouped.merge(
                df_guarantee_limit[['日期', '指标名称', '授信担保公司名称', '指标值']],
                left_on=['日期', '担保人wind代码'],
                right_on=['日期', '指标名称'],
                how='left',
                suffixes=('', '_limit')
            )
            df_grouped = df_grouped.drop(columns=['指标名称'], errors='ignore')
            
            # 步骤5: 重新计算剩余额度（使用指标值 - 单一担保人总持仓_PR）
            if '指标值' in df_grouped.columns and '单一担保人总持仓_PR' in df_grouped.columns:
                # 填充null为0
                df_grouped['单一担保人总持仓_PR'] = df_grouped['单一担保人总持仓_PR'].fillna(0)
                
                # 重新计算剩余额度
                df_grouped['单一担保公司规模剩余额度(万)'] = (
                    df_grouped['指标值'] - df_grouped['单一担保人总持仓_PR']
                )
                df_grouped['单一担保人是否超限'] = df_grouped['单一担保公司规模剩余额度(万)'].apply(
                    lambda x: '是' if pd.notna(x) and x < 0 else '否'
                )
                
                # 删除旧的单一担保公司规模限额列，用指标值替代
                df_grouped = df_grouped.drop(columns=['单一担保公司规模限额'], errors='ignore')
                df_grouped = df_grouped.rename(columns={'指标值': '单一担保公司规模限额'})
        
        # 删除担保人wind代码和担保人列（按照M-code）
        df_grouped = df_grouped.drop(columns=['担保人wind代码', '担保人'], errors='ignore')
        
        # 重排序列（按照M-code的输出顺序）
        result_cols = ['日期', '业务分类', '授信担保公司名称', '单一担保公司规模限额', 
                      '单一担保人总持仓_PR', '单一担保公司规模剩余额度(万)', '单一担保人是否超限']
        
        # 只保留存在的列
        result_cols = [col for col in result_cols if col in df_grouped.columns]
        result = df_grouped[result_cols].copy()
        
        logger.info(f"  限额明细_单一担保人: {len(result)} 行")
        
        return result
    
    def calculate_limit_detail_1_1(self) -> pd.DataFrame:
        """
        查询: 限额明细_债券持仓明细表_信用债1_1
        与1_2类似，但主要关联特定主体和特定实控人限额明细
        """
        df = self.cache.get('债券持仓明细表_信用债_合并风险限额相关')
        if df is None:
            return pd.DataFrame()

        # M-code 1_1 直接使用合并表，不在此处排除高收益行。
        df = df.copy()
        
        # 添加业务分类
        df['业务分类'] = df['内部证券账户名称'].apply(
            lambda x: '做市业务' if x == '做市交易部做市业务' else '自营业务'
        )
        
        # 关联特定主体限额明细
        df_specific_issuer = self.cache.get('限额明细_特定主体')
        if df_specific_issuer is not None and len(df_specific_issuer) > 0:
            df = df.merge(
                df_specific_issuer[['业务分类', '资产代码', '日期', '指标名称', 
                                   '特定主体限额指标值', '特定主体总持仓',
                                   '特定主体限额剩余额度', '特定主体限额是否超限']],
                on=['业务分类', '资产代码', '日期'],
                how='left'
            )
            df = df.rename(columns={'指标名称': '特定主体限额名称'})
        
        # 关联特定实控人限额明细
        df_specific_controller = self.cache.get('限额明细_特定实控人')
        if df_specific_controller is not None and len(df_specific_controller) > 0:
            df = df.merge(
                df_specific_controller[['业务分类', '资产代码', '日期', '指标名称',
                                       '特定实控人限额指标值', '特定实控人总持仓',
                                       '特定实控人限额剩余额度', '特定实控人限额是否超限']],
                on=['业务分类', '资产代码', '日期'],
                how='left',
                suffixes=('', '_ctrl')
            )
            df = df.rename(columns={'指标名称': '特定实控人限额名称'})
        
        # 筛选：至少有一个特定限额
        df = df[(df.get('特定实控人限额名称', pd.Series()).notna()) | 
                (df.get('特定主体限额名称', pd.Series()).notna())]
        
        # 综合判断是否超限
        df['是否超限'] = df.apply(
            lambda row: '是' if '是' in [
                row.get('特定主体限额是否超限'),
                row.get('特定实控人限额是否超限')
            ] else '否',
            axis=1
        )
        
        # 替换空值
        for col in ['特定主体限额是否超限', '特定实控人限额是否超限']:
            if col in df.columns:
                df[col] = df[col].fillna('否')
        
        # 【修复】Excel M代码逻辑：同一债券的多个持仓记录需要合并
        # 问题：原始数据中同一债券（同一日期、业务分类、资产代码、账户）可能有多条记录
        # Excel使用Table.Distinct去重，Python需要按业务key分组sum库存数量
        rows_before = len(df)
        
        # 定义分组键：包含所有业务主键和特定限额名称
        # 这样确保同一债券+同一限额配置只有一行
        group_cols = [
            '日期', '业务分类', '资产代码', '资产名称', '债务主体', 
            '债务主体wind代码', '内部证券账户名称'
        ]
        
        # 添加特定限额相关列到分组键（如果存在）
        for col in ['特定主体限额名称', '特定实控人限额名称']:
            if col in df.columns:
                group_cols.append(col)
        
        # 确保分组列存在
        group_cols = [col for col in group_cols if col in df.columns]
        
        # 定义聚合规则
        agg_dict = {}
        for col in df.columns:
            if col not in group_cols:
                if col == '库存数量(万)_PR':
                    agg_dict[col] = 'sum'  # 库存数量求和
                elif col in ['特定主体限额指标值', '特定主体总持仓', '特定主体限额剩余额度',
                           '特定实控人限额指标值', '特定实控人总持仓', '特定实控人限额剩余额度']:
                    agg_dict[col] = 'first'  # 限额相关字段取第一个（都是相同的）
                elif df[col].dtype in ['float64', 'int64']:
                    agg_dict[col] = 'first'  # 其他数值列取第一个
                else:
                    agg_dict[col] = 'first'  # 文本列取第一个
        
        if group_cols and agg_dict:
            df = df.groupby(group_cols, as_index=False, dropna=False).agg(agg_dict)
            rows_after = len(df)
            if rows_before > rows_after:
                logger.info(f"    合并同一债券的多条记录: {rows_before} -> {rows_after} 行 (合并了 {rows_before - rows_after} 条)")

        df = df.drop(columns=[SOURCE_ROW_ID_COL], errors='ignore')
        
        logger.info(f"  限额明细_债券持仓明细表_信用债1_1: {len(df)} 行")
        
        return df
