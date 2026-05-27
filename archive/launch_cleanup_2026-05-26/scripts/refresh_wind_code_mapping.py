"""
Wind代码映射表刷新工具

功能：
1. 读取所有缺失的Wind代码
2. 使用Excel To_WindCode()函数批量补充
3. 更新映射表

使用场景：
- 初次部署时，补充完整映射表
- 定期（如每月）更新映射表
- 发现大量缺失Wind代码时

运行方式：
    python scripts/refresh_wind_code_mapping.py
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.common.wind_code_resolver import WindCodeResolver
from loguru import logger


def main():
    """主函数"""
    logger.info("=" * 80)
    logger.info("Wind代码映射表刷新工具")
    logger.info("=" * 80)
    
    # 初始化resolver
    data_dir = project_root / "sample data"
    output_dir = project_root / "data" / "current" / "stage0_output"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    mapping_file = output_dir / "issuer_wind_code_mapping.csv"
    
    resolver = WindCodeResolver(
        data_dir=data_dir,
        mapping_file=mapping_file,
        use_wind_api=False,
        use_excel_helper=True,
        cache_new_codes=True
    )
    
    logger.info(f"\n当前映射表状态: {len(resolver.mapping)} 个主体")
    
    # 检查是否有缺失列表
    missing_file = project_root / "temp" / "missing_wind_codes.txt"
    
    if missing_file.exists():
        logger.info(f"\n发现缺失列表: {missing_file}")
        
        # 读取缺失列表
        with open(missing_file, 'r', encoding='utf-8') as f:
            missing_issuers = [line.strip() for line in f if line.strip()]
        
        logger.info(f"需要补充: {len(missing_issuers)} 个Wind代码")
        
        # 设置缺失列表
        resolver.missing_issuers = missing_issuers
        
        # 批量解析
        logger.info("\n开始批量获取Wind代码...")
        success_count = resolver.batch_resolve_missing()
        
        if success_count > 0:
            logger.info(f"\n✓ 成功补充 {success_count} 个Wind代码")
            logger.info(f"✓ 映射表已更新: {mapping_file}")
            logger.info(f"✓ 当前映射表: {len(resolver.mapping)} 个主体")
        else:
            logger.warning("\n⚠️  未成功获取新的Wind代码")
            logger.info("请检查：")
            logger.info("  1. Excel是否已安装")
            logger.info("  2. Wind终端是否已启动")
            logger.info("  3. To_WindCode()函数是否可用")
    else:
        logger.info("\n✓ 没有缺失的Wind代码需要补充")
        logger.info("  映射表已完整")
    
    # 显示统计信息
    stats = resolver.get_coverage_stats()
    logger.info("\n" + "=" * 80)
    logger.info("映射表统计信息")
    logger.info("=" * 80)
    logger.info(f"总主体数: {stats['total_issuers']}")
    logger.info(f"数据源策略: 仅使用To_WindCode()")
    logger.info(f"Excel辅助: {'已启用' if stats['excel_helper_enabled'] else '未启用'}")
    logger.info(f"缓存功能: {'已启用' if stats['cache_enabled'] else '未启用'}")
    logger.info(f"当前缺失: {stats['missing_count']} 个")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
