"""
省份匹配诊断工具
用于检查省份名称不匹配问题
"""

import sys
from pathlib import Path
import pandas as pd

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.common import ProvinceNormalizer
from loguru import logger


def main():
    logger.info("=" * 80)
    logger.info("省份匹配诊断工具")
    logger.info("=" * 80)
    
    # 1. 检查配置表中的省份
    config_file = project_root / "sample data" / "限额监控_阶段0_指标设置.xlsx"
    df_config = pd.read_excel(config_file, sheet_name="高风险省份表")
    
    logger.info("\n[1] 配置表中的省份:")
    stats_config = ProvinceNormalizer.validate_dataframe(df_config, '省份名称')
    logger.info(f"  标准格式: {len(stats_config['standard'])} 个")
    logger.info(f"  非标准格式: {len(stats_config['non_standard'])} 个")
    if stats_config['non_standard']:
        for item in stats_config['non_standard']:
            logger.info(f"    - '{item['original']}' → '{item['standard']}'")
    if stats_config['unmapped']:
        logger.warning(f"  无法映射: {stats_config['unmapped']}")
    
    # 2. 检查债券持仓表中的省份
    bond_file = project_root / "data/current/stage1_output/限额明细_债券持仓明细表_信用债1_2.xlsx"
    if bond_file.exists():
        df_bond = pd.read_excel(bond_file)
        
        logger.info("\n[2] 债券持仓表中的省份:")
        stats_bond = ProvinceNormalizer.validate_dataframe(df_bond, '省份')
        logger.info(f"  标准格式: {len(stats_bond['standard'])} 个")
        logger.info(f"  非标准格式: {len(stats_bond['non_standard'])} 个")
        if stats_bond['non_standard']:
            for item in stats_bond['non_standard']:
                logger.info(f"    - '{item['original']}' → '{item['standard']}'")
        if stats_bond['unmapped']:
            logger.warning(f"  无法映射: {stats_bond['unmapped']}")
        
        # 3. 检查云南和贵州的具体情况
        logger.info("\n[3] 云南和贵州详细分析:")
        for province_keyword in ['云南', '贵州']:
            province_data = df_bond[df_bond['省份'].str.contains(province_keyword, na=False)]
            if len(province_data) > 0:
                logger.info(f"\n  {province_keyword}:")
                logger.info(f"    总记录数: {len(province_data)}")
                logger.info(f"    总持仓: {province_data['库存数量(万)_PR'].sum():.2f}")
                logger.info(f"    省份字段唯一值: {province_data['省份'].unique()}")
                
                # 按省份类别分组
                grouped = province_data.groupby('省份类别', dropna=False)['库存数量(万)_PR'].sum()
                for category, amount in grouped.items():
                    category_str = category if pd.notna(category) else 'NULL'
                    logger.info(f"      省份类别='{category_str}': {amount:.2f}")
    else:
        logger.warning(f"\n[2] 债券持仓表不存在: {bond_file}")
    
    logger.info("\n" + "=" * 80)
    logger.info("诊断完成")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
