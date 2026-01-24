"""
Wind代码解析器 - 统一使用To_WindCode()策略
核心原则：与原始Excel保持100%一致

获取策略：
1. 映射表查询（包含历史所有To_WindCode()结果）
2. 记录缺失，批量使用Excel To_WindCode()函数补充
3. 禁用Wind API查询，确保数据源一致性

数据源：
- 德勤-主体评级列表.xlsx
- 统计报表底稿1_债券.xlsx
- Excel To_WindCode()函数（唯一补充来源）
"""

import pandas as pd
from pathlib import Path
from typing import Optional
from loguru import logger
import platform


class WindCodeResolver:
    """Wind主体代码解析器"""
    
    def __init__(
        self, 
        data_dir: Path,
        mapping_file: Optional[Path] = None,
        use_wind_api: bool = False,  # 强制禁用，保持与Excel一致
        use_excel_helper: bool = True,
        cache_new_codes: bool = True
    ):
        """
        初始化Wind代码解析器
        
        策略说明：
        - 统一使用To_WindCode()作为唯一数据源
        - 不使用Wind API，避免与Excel结果不一致
        - 所有新增Wind代码都通过Excel To_WindCode()函数获取
        
        参数:
            data_dir: 数据目录路径
            mapping_file: 映射表文件路径（如果为None则自动构建）
            use_wind_api: 已禁用，保持与原Excel一致性
            use_excel_helper: 是否使用Excel To_WindCode()函数
            cache_new_codes: 是否缓存查询到的新代码
        """
        self.data_dir = Path(data_dir)
        self.use_wind_api = False  # 强制禁用Wind API
        self.use_excel_helper = use_excel_helper
        self.cache_new_codes = cache_new_codes
        self.system = platform.system()
        
        # 加载或构建映射表
        if mapping_file and mapping_file.exists():
            logger.info(f"加载Wind代码映射表: {mapping_file}")
            self.mapping = pd.read_csv(mapping_file)
        else:
            logger.info("构建Wind代码映射表...")
            self.mapping = self._build_base_mapping()
            
            # 保存映射表
            if mapping_file:
                mapping_file.parent.mkdir(parents=True, exist_ok=True)
                self.mapping.to_csv(mapping_file, index=False, encoding='utf-8-sig')
                logger.info(f"映射表已保存: {mapping_file}")
        
        logger.info(f"映射表加载完成: {len(self.mapping)} 个主体")
        logger.info("策略: 仅使用To_WindCode()，与原Excel保持100%一致")
        
        # Wind API已禁用，确保数据源一致性
        self.wind_api = None
        
        # 初始化Excel辅助工具（macOS也可使用）
        self.excel_helper = None
        if use_excel_helper:
            try:
                from .wind_code_excel_helper import WindCodeExcelHelper
                self.excel_helper = WindCodeExcelHelper()
                logger.info(f"✓ Excel辅助工具已启用（{self.system} - To_WindCode函数）")
            except Exception as e:
                logger.warning(f"Excel辅助工具初始化失败: {e}")
        
        # 缓存映射文件路径（用于保存新增映射）
        self.mapping_file = mapping_file
        
        # 记录未找到的发行人（用于批量Excel查询）
        self.missing_issuers = []
        
    def _build_base_mapping(self) -> pd.DataFrame:
        """构建基础映射表（德勤列表 + 统计报表底稿）"""
        mappings = []
        
        # 1. 德勤-主体评级列表
        try:
            deloitte_file = self.data_dir / "德勤-主体评级列表.xlsx"
            logger.info(f"读取德勤列表: {deloitte_file}")
            
            df_deloitte = pd.read_excel(deloitte_file, sheet_name="Sheet1")
            mapping1 = df_deloitte[['主体名称', '主体wind代码']].copy()
            mapping1.columns = ['发行人', 'wind代码']
            
            # 清理数据
            mapping1 = mapping1[mapping1['wind代码'].notna()]
            mapping1 = mapping1[mapping1['wind代码'] != 0]
            mapping1 = mapping1.drop_duplicates(subset=['发行人'])
            
            mappings.append(mapping1)
            logger.info(f"  德勤列表: {len(mapping1)} 个主体")
            
        except Exception as e:
            logger.warning(f"无法读取德勤列表: {e}")
        
        # 2. 统计报表底稿
        try:
            report_file = self.data_dir / "统计报表底稿1_债券.xlsx"
            logger.info(f"读取统计报表底稿: {report_file}")
            
            df_report = pd.read_excel(report_file, sheet_name="债券持仓明细表")
            mapping2 = df_report[['债务主体', '债务主体wind代码']].copy()
            mapping2.columns = ['发行人', 'wind代码']
            
            # 清理数据
            mapping2 = mapping2[mapping2['wind代码'].notna()]
            mapping2 = mapping2[mapping2['wind代码'] != 0]
            mapping2 = mapping2.drop_duplicates(subset=['发行人'])
            
            mappings.append(mapping2)
            logger.info(f"  统计报表底稿: {len(mapping2)} 个主体")
            
        except Exception as e:
            logger.warning(f"无法读取统计报表底稿: {e}")
        
        # 合并映射表
        if mappings:
            combined = pd.concat(mappings, ignore_index=True)
            combined = combined.drop_duplicates(subset=['发行人'], keep='first')
            logger.info(f"合并后映射表: {len(combined)} 个主体")
            return combined
        else:
            logger.warning("未能构建任何映射表！")
            return pd.DataFrame(columns=['发行人', 'wind代码'])
    
    def _init_wind_api(self):
        """
        Wind API已禁用
        
        原因：为保证与原Excel的To_WindCode()函数100%一致，
        系统统一使用Excel To_WindCode()作为唯一数据源。
        """
        logger.info("Wind API已禁用，统一使用Excel To_WindCode()函数")
        self.wind_api = None
        self.use_wind_api = False
    
    def get_code(self, issuer_name: str, strict: bool = False) -> Optional[str]:
        """
        获取发行人的Wind代码（仅从映射表查询）
        
        策略：
        1. 从映射表查询（包含所有历史To_WindCode()结果）
        2. 未找到时记录到缺失列表，等待批量补充
        3. 不使用Wind API，确保与原Excel完全一致
        
        参数:
            issuer_name: 发行人名称
            strict: 严格模式，找不到代码时抛出异常
            
        返回:
            Wind代码字符串，或None（未找到时）
        """
        if not issuer_name or pd.isna(issuer_name):
            return None
        
        # 从映射表查询（唯一数据源）
        result = self.mapping[self.mapping['发行人'] == issuer_name]
        
        if len(result) > 0:
            return str(result.iloc[0]['wind代码'])
        
        # 未找到：记录到缺失列表，等待批量To_WindCode()补充
        if issuer_name not in self.missing_issuers:
            self.missing_issuers.append(issuer_name)
        
        # 未找到
        msg = f"未找到Wind代码: {issuer_name}"
        
        if strict:
            raise ValueError(msg)
        else:
            logger.warning(f"⚠️  {msg}")
            return None
    
    def _query_wind_api(self, issuer_name: str) -> Optional[str]:
        """
        Wind API查询已禁用
        
        为保证与原Excel完全一致，不再使用Wind API。
        所有Wind代码统一通过Excel To_WindCode()函数获取。
        """
        logger.debug(f"Wind API已禁用，请使用To_WindCode()函数: {issuer_name}")
        return None
    
    def _cache_code(self, issuer_name: str, wind_code: str):
        """缓存新的Wind代码到映射表"""
        # 添加到内存中的映射表
        new_row = pd.DataFrame([[issuer_name, wind_code]], columns=['发行人', 'wind代码'])
        self.mapping = pd.concat([self.mapping, new_row], ignore_index=True)
        
        # 保存到文件（如果指定了映射文件路径）
        if self.mapping_file:
            try:
                self.mapping.to_csv(self.mapping_file, index=False, encoding='utf-8-sig')
                logger.debug(f"缓存Wind代码: {issuer_name} → {wind_code}")
            except Exception as e:
                logger.warning(f"保存映射表失败: {e}")
    
    def get_codes_batch(self, issuer_names: list, strict: bool = False) -> pd.Series:
        """
        批量获取Wind代码
        
        参数:
            issuer_names: 发行人名称列表
            strict: 严格模式
            
        返回:
            pandas Series，索引为发行人名称，值为Wind代码
        """
        return pd.Series(issuer_names).apply(lambda x: self.get_code(x, strict=strict))
    
    def batch_resolve_missing(self) -> int:
        """
        批量解析缺失的Wind代码（使用Excel辅助）
        
        返回:
            成功获取的数量
        """
        if not self.missing_issuers:
            logger.info("没有缺失的Wind代码需要解析")
            return 0
        
        logger.info(f"批量解析缺失的Wind代码: {len(self.missing_issuers)} 个")
        
        # 使用Excel辅助工具（所有平台）
        if self.excel_helper:
            try:
                logger.info("使用Excel To_WindCode函数批量获取...")
                df_result = self.excel_helper.batch_get_wind_codes(self.missing_issuers)
                
                # 合并到映射表
                success_count = 0
                for _, row in df_result.iterrows():
                    if pd.notna(row['Wind代码']):
                        self._cache_code(row['发行人名称'], row['Wind代码'])
                        success_count += 1
                
                logger.info(f"✓ Excel批量获取成功: {success_count}/{len(self.missing_issuers)}")
                self.missing_issuers.clear()
                return success_count
                
            except Exception as e:
                logger.error(f"Excel批量获取失败: {e}")
                import traceback
                logger.debug(traceback.format_exc())
        
        # 保存缺失列表供后续处理（所有环境）
        if self.missing_issuers:
            missing_file = Path("temp/missing_wind_codes.txt")
            missing_file.parent.mkdir(exist_ok=True, parents=True)
            with open(missing_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(sorted(set(self.missing_issuers))))
            
            logger.warning(f"⚠️  {len(self.missing_issuers)} 个Wind代码未找到")
            logger.warning(f"   缺失列表已保存: {missing_file.absolute()}")
            
            if self.system != 'Windows':
                logger.info(f"   💡 Windows环境部署时将自动使用Excel获取")
        
        return 0
    
    def get_coverage_stats(self) -> dict:
        """获取映射表覆盖率统计"""
        return {
            'total_issuers': len(self.mapping),
            'wind_api_enabled': False,  # 已禁用，使用To_WindCode()
            'to_windcode_only': True,  # 统一使用To_WindCode()
            'excel_helper_enabled': self.excel_helper is not None,
            'cache_enabled': self.cache_new_codes,
            'missing_count': len(self.missing_issuers),
        }
