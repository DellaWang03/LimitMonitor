"""
运行阶段2: 高风险行业/省份、地域集中度、高收益债券监控
"""

import os
from pathlib import Path
from loguru import logger
from src.stage2 import Stage2Processor
from src.utils.config_loader import get_config


def main():
    """主函数"""
    # 读取环境模式
    ENV_MODE = os.getenv('LIMIT_MONITOR_ENV', 'development').lower()
    data_incomplete = os.getenv('DATA_INCOMPLETE', 'false').lower() == 'true'
    
    # 设置路径
    project_root = Path(__file__).parent
    
    # 从配置文件读取数据源目录
    config = get_config()
    data_dir = config.get_data_dir()
    
    stage0_output_dir = project_root / "data" / "current" / "stage0_output"
    stage1_output_dir = project_root / "data" / "current" / "stage1_output"
    stage2_output_dir = project_root / "data" / "current" / "stage2_output"
    
    # 配置日志
    logger.remove()
    logger.add(
        lambda msg: print(msg, end=''),
        format="{message}",
        level="INFO"
    )
    
    logger.info("=" * 100)
    logger.info(" " * 35 + "限额监控自动化 - 阶段2")
    logger.info("=" * 100)
    logger.info(f"运行模式: {'🔴 生产环境' if ENV_MODE == 'production' else '🟡 测试环境'}")
    if data_incomplete:
        logger.info("⚠️  数据完整性: 不完整（使用旧数据）\n")
    logger.info(f"\n数据源目录: {data_dir}")
    logger.info(f"阶段0输出: {stage0_output_dir}")
    logger.info(f"阶段1输出: {stage1_output_dir}")
    logger.info(f"阶段2输出: {stage2_output_dir}")
    logger.info("")
    
    # 创建处理器（传入 config 以支持路径 profile 一键切换）
    processor = Stage2Processor(
        data_dir=data_dir,
        output_dir=stage2_output_dir,
        stage0_output_dir=stage0_output_dir,
        stage1_output_dir=stage1_output_dir,
        config=config
    )
    
    # 执行处理
    try:
        results = processor.process_all()
        
        logger.info("\n" + "=" * 100)
        logger.info("✅ 阶段2处理完成!")
        if data_incomplete and ENV_MODE == 'development':
            logger.info("⚠️  数据不完整，请勿用于生产决策")
        logger.info("=" * 100)
        logger.info(f"\n生成表格数: {len(results)}")
        logger.info(f"输出目录: {stage2_output_dir}")
        logger.info("\n输出表格:")
        for i, (name, df) in enumerate(results.items(), 1):
            logger.info(f"  {i:2d}. {name}: {len(df)} 行 × {len(df.columns)} 列")
        
    except Exception as e:
        logger.error(f"\n❌ 处理失败: {e}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()
