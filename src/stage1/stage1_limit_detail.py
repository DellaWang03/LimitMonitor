"""
阶段1限额明细查询模块
由于限额明细查询非常复杂，单独提取到此模块
"""

import pandas as pd
import numpy as np
from loguru import logger
from typing import Dict


class LimitDetailCalculator:
    """限额明细计算器"""
    
    def __init__(self, cache: Dict[str, pd.DataFrame]):
        """
        初始化
        
        Args:
            cache: 缓存的查询结果字典
        """
        self.cache = cache
    
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
        
        # 1. 筛选非高收益
        df = df[df['是否属于高收益'] == '否']
        logger.info(f"    筛选非高收益: {len(df)} 行")
        
        # 2. 添加业务分类
        df['业务分类'] = df['内部证券账户名称'].apply(
            lambda x: '做市业务' if x == '做市交易部做市业务' else '自营业务'
        )
        
        # 2.1 关联限额明细_特定主体（获取指标名称）
        # 根据M-code第192-195行，需要在此处关联并筛选
        df_specific_issuer = self.cache.get('限额明细_特定主体')
        if df_specific_issuer is not None and len(df_specific_issuer) > 0:
            rows_before = len(df)
            df = df.merge(
                df_specific_issuer[['业务分类', '资产代码', '日期', '指标名称']],
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
        
        # 合并债券池
        if '债券池' in df.columns:
            df['单一债券规模限额适用类别_base'] = df.apply(
                lambda row: f"{row['单一债券规模限额适用类别_base']}/{row['债券池']}" 
                if pd.notna(row.get('债券池')) else row['单一债券规模限额适用类别_base'],
                axis=1
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
            df = df.merge(
                df_special[['日期', '主证券代码', '规模指标值', '集中度指标值']],
                left_on=['日期', '资产代码'],
                right_on=['日期', '主证券代码'],
                how='left',
                suffixes=('', '_特批')
            )
            # 如果特批限额存在，使用特批限额覆盖
            df['单一债券规模限额指标值'] = df.apply(
                lambda row: row['规模指标值'] if pd.notna(row.get('规模指标值')) 
                else row.get('单一债券规模限额指标值'),
                axis=1
            )
            df['单一债券集中度限额指标值'] = df.apply(
                lambda row: row['集中度指标值'] if pd.notna(row.get('集中度指标值')) 
                else row.get('单一债券集中度限额指标值'),
                axis=1
            )
            # 删除来自特批单一债券限额表的列（保留原始主证券代码列）
            df = df.drop(columns=['主证券代码_特批', '规模指标值', '集中度指标值'], errors='ignore')
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
            df = df.merge(
                df_bond_pos[['日期', '业务分类', '主证券代码', '单一债券总持仓_PR', '单一债券集中度']],
                on=['日期', '业务分类', '主证券代码'],
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
        # 9.5.1 单一实控人规模限额
        df_controller_limit = self.cache.get('单一实控人规模限额')
        if df_controller_limit is not None and '实际控制人名称_修正' in df.columns:
            # 计算单一实控人限额适用类别（与单一主体类似的逻辑）
            df['单一实控人限额适用类别'] = df['单一主体限额适用类别']
            
            df = df.merge(
                df_controller_limit[['日期', '指标名称', '指标值']],
                left_on=['日期', '单一实控人限额适用类别'],
                right_on=['日期', '指标名称'],
                how='left',
                suffixes=('', '_实控人限额')
            )
            df = df.drop(columns=['指标名称'], errors='ignore')
            df = df.rename(columns={'指标值': '单一实控人规模限额指标值'})
            logger.info(f"    关联单一实控人规模限额")
        
        # 9.5.2 单一实控人总持仓
        df_controller_pos = self.cache.get('单一实控人总持仓')
        if df_controller_pos is not None and '实际控制人名称_修正' in df.columns:
            df = df.merge(
                df_controller_pos[['日期', '业务分类', '实际控制人名称_修正', '单一实控人总持仓_PR']],
                on=['日期', '业务分类', '实际控制人名称_修正'],
                how='left',
                suffixes=('', '_实控人总持仓')
            )
            logger.info(f"    关联单一实控人总持仓")
        
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
        if '单一实控人规模限额指标值' in df.columns and '单一实控人总持仓_PR' in df.columns:
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
        
        if '单一实控人规模剩余额度(万)' in df.columns:
            df['单一实控人是否超限'] = df.apply(check_controller_over_limit, axis=1)
        
        # 12. 综合判断是否超限
        # 注意：单一实控人超限不计入综合判断，仅作为独立维度展示（与Excel参考文件逻辑一致）
        df['是否超限'] = df.apply(
            lambda row: '是' if '是' in [
                row.get('单一债券是否超限'),
                row.get('单一债券集中度是否超限'),
                row.get('单一主体是否超限'),
                row.get('单一担保人是否超限')
                # 不包含：单一实控人是否超限（单独作为一个维度展示）
            ] else '否',
            axis=1
        )
        
        # 13. 删除中间计算列
        columns_to_drop = ['单一债券规模限额适用类别_base', '调整后实际控制人']
        df = df.drop(columns=columns_to_drop, errors='ignore')
        
        logger.info(f"  限额明细计算完成: {len(df)} 行")
        
        return df
    
    def calculate_limit_detail_single_bond(self) -> pd.DataFrame:
        """
        查询: 限额明细_单一债券
        简化实现：基于债券持仓明细表，分组后与限额关联
        """
        df = self.cache.get('债券持仓明细表')
        if df is None:
            return pd.DataFrame()
        
        df = df.copy()
        
        # 排除高收益
        df = df[~df['内部证券账户名称'].str.contains('高收益', na=False)]
        
        # 筛选非利率债
        df = df[df['债券分类2'] != '利率债']
        
        # 分组计算单一债券总持仓
        result = df.groupby(['日期', '主证券代码', '主证券名称'], as_index=False).agg({
            '库存数量(万)_PR': 'sum',
            '债券余额(亿)': 'mean'
        })
        
        result = result.rename(columns={
            '库存数量(万)_PR': '单一债券总持仓_PR',
            '主证券代码': '证券代码',
            '主证券名称': '证券名称'
        })
        
        # 计算集中度
        result['单一债券集中度'] = result['单一债券总持仓_PR'] / result['债券余额(亿)'] * 0.0001
        result = result.drop(columns=['债券余额(亿)'], errors='ignore')
        
        # 排序
        result = result.sort_values('单一债券集中度', ascending=False, na_position='last')
        
        logger.info(f"  限额明细_单一债券: {len(result)} 行")
        
        return result
    
    def calculate_limit_detail_single_issuer(self) -> pd.DataFrame:
        """
        查询: 限额明细_单一主体
        简化实现：基于债券持仓明细表_信用债，分组计算
        """
        df = self.cache.get('债券持仓明细表_信用债')
        if df is None:
            return pd.DataFrame()
        
        df = df.copy()
        
        # 排除高收益
        df = df[~df['内部证券账户名称'].str.contains('高收益', na=False)]
        
        # 分组计算
        result = df.groupby(['日期', '债务主体wind代码', '债务主体'], as_index=False).agg({
            '库存数量(万)_PR': 'sum'
        })
        
        result = result.rename(columns={'库存数量(万)_PR': '单一主体总持仓_PR'})
        
        logger.info(f"  限额明细_单一主体: {len(result)} 行")
        
        return result
    
    def calculate_limit_detail_specific_issuer(self) -> pd.DataFrame:
        """
        查询: 限额明细_特定主体
        基于债券持仓明细表_信用债_合并风险限额相关，关联特定主体限额
        """
        df = self.cache.get('债券持仓明细表_信用债_合并风险限额相关')
        if df is None:
            return pd.DataFrame()
        
        df = df.copy()
        
        # 排除高收益和关注池
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
        基于债券持仓明细表_信用债_合并风险限额相关，关联特定实控人限额
        """
        df = self.cache.get('债券持仓明细表_信用债_合并风险限额相关')
        if df is None:
            return pd.DataFrame()
        
        df = df.copy()
        
        # 排除高收益和关注池
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
            
            # 筛选有特定实控人限额的记录
            df = df[(df['指标名称'].notna()) & (df['指标名称'] != '')]
            
            # 添加业务分类
            df['业务分类'] = df['内部证券账户名称'].apply(
                lambda x: '做市业务' if x == '做市交易部做市业务' else '自营业务'
            )
            
            # 分组计算
            # Excel M代码: {"日期", "业务分类","指标名称", "实控人名称", "债务主体", "资产代码", "资产名称"}
            result = df.groupby(['日期', '业务分类', '指标名称', '实际控制人名称_修正',
                                '债务主体', '资产代码', '资产名称'], as_index=False).agg({
                '库存数量(万)_PR': 'sum',
                '指标值': 'mean'
            })
            
            result = result.rename(columns={
                '指标值': '特定实控人限额指标值'
            })
            
            # 关联特定实控人总持仓
            df_total = self.cache.get('特定实控人总持仓')
            if df_total is not None:
                result = result.merge(
                    df_total[['日期', '业务分类', '特定实控人名称', '特定实控人总持仓']],
                    left_on=['日期', '业务分类', '指标名称'],
                    right_on=['日期', '业务分类', '特定实控人名称'],
                    how='left'
                )
                result = result.drop(columns=['特定实控人名称'], errors='ignore')
                
                # 计算剩余额度
                result['特定实控人限额剩余额度'] = result['特定实控人限额指标值'] - result['特定实控人总持仓']
                
                # 判断是否超限
                result['特定实控人限额是否超限'] = result['特定实控人限额剩余额度'].apply(
                    lambda x: '是' if pd.notna(x) and x < 0 else '否'
                )
            
            logger.info(f"  限额明细_特定实控人: {len(result)} 行")
            
            return result
        
        return pd.DataFrame()
    
    def calculate_limit_detail_single_controller(self) -> pd.DataFrame:
        """
        查询: 限额明细_单一实控人
        基于债券持仓明细表_信用债_合并风险限额相关，计算单一实控人限额
        """
        df = self.cache.get('债券持仓明细表_信用债_合并风险限额相关')
        if df is None:
            return pd.DataFrame()
        
        df = df.copy()
        
        # 排除高收益和关注池
        df = df[~df['内部证券账户名称'].str.contains('高收益', na=False)]
        df = df[~df['内部证券账户名称'].str.contains('关注池', na=False)]
        
        # 添加业务分类
        df['业务分类'] = df['内部证券账户名称'].apply(
            lambda x: '做市业务' if x == '做市交易部做市业务' else '自营业务'
        )
        
        # 计算单一实控人限额适用类别
        df['单一实控人限额适用类别'] = df.apply(
            lambda row: f"中债隐含评级{row['中债隐含评级']}" 
            if pd.notna(row.get('中债隐含评级')) and row['中债隐含评级'] in ['AAA', 'AAA+']
            else f"{row.get('发行人类型_调整', row.get('发行人类型', ''))}/{row.get('主体池', '')}",
            axis=1
        )
        
        # 关联单一实控人规模限额
        df_limit = self.cache.get('单一实控人规模限额')
        if df_limit is not None:
            df = df.merge(
                df_limit[['日期', '指标名称', '指标值']],
                left_on=['日期', '单一实控人限额适用类别'],
                right_on=['日期', '指标名称'],
                how='left'
            )
            df = df.drop(columns=['指标名称'], errors='ignore')
            df = df.rename(columns={'指标值': '单一实控人规模限额指标值'})
        
        # 关联单一实控人总持仓
        df_total = self.cache.get('单一实控人总持仓')
        if df_total is not None:
            df = df.merge(
                df_total[['日期', '业务分类', '实际控制人名称_修正', '单一实控人总持仓_PR']],
                on=['日期', '业务分类', '实际控制人名称_修正'],
                how='left'
            )
            
            # 计算剩余额度
            df['单一实控人规模剩余额度(万)'] = df['单一实控人规模限额指标值'] - df['单一实控人总持仓_PR']
            
            # 判断是否超限
            df['单一实控人是否超限'] = df['单一实控人规模剩余额度(万)'].apply(
                lambda x: '是' if pd.notna(x) and x < 0 else '否'
            )
        
        # 选择需要的列
        result_cols = ['日期', '业务分类', '实际控制人名称_修正', '资产代码', '资产名称',
                      '单一实控人限额适用类别', '单一实控人规模限额指标值', 
                      '单一实控人总持仓_PR', '单一实控人规模剩余额度(万)', '单一实控人是否超限']
        
        result = df[[col for col in result_cols if col in df.columns]].copy()
        
        # 筛选实控人不为空
        result = result[result['实际控制人名称_修正'].notna()]
        
        logger.info(f"  限额明细_单一实控人: {len(result)} 行")
        
        return result
    
    def calculate_limit_detail_single_controller_max(self) -> pd.DataFrame:
        """
        查询: 限额明细_单一实控人_取最高额度
        从单一实控人限额明细中，每个实控人取最高额度
        """
        df = self.calculate_limit_detail_single_controller()
        
        if len(df) == 0:
            return pd.DataFrame()
        
        # 按实控人分组，取最高额度
        result = df.groupby(['日期', '业务分类', '实际控制人名称_修正'], as_index=False).agg({
            '单一实控人限额适用类别': 'first',
            '单一实控人规模限额指标值': 'max',
            '单一实控人总持仓_PR': 'first',
            '单一实控人规模剩余额度(万)': 'max',
            '单一实控人是否超限': lambda x: '是' if '是' in x.values else '否'
        })
        
        logger.info(f"  限额明细_单一实控人_取最高额度: {len(result)} 行")
        
        return result
    
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
                
                # 删除旧的单一担保公司规模限额列，用指标值替代
                df_grouped = df_grouped.drop(columns=['单一担保公司规模限额'], errors='ignore')
                df_grouped = df_grouped.rename(columns={'指标值': '单一担保公司规模限额'})
        
        # 删除担保人wind代码和担保人列（按照M-code）
        df_grouped = df_grouped.drop(columns=['担保人wind代码', '担保人'], errors='ignore')
        
        # 重排序列（按照M-code的输出顺序）
        result_cols = ['日期', '业务分类', '授信担保公司名称', '单一担保公司规模限额', 
                      '单一担保人总持仓_PR', '单一担保公司规模剩余额度(万)']
        
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
        
        logger.info(f"  限额明细_债券持仓明细表_信用债1_1: {len(df)} 行")
        
        return df
