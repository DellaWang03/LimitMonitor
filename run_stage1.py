"""
阶段1运行脚本
"""

import os
from pathlib import Path
from datetime import datetime
from loguru import logger
from src.stage1 import Stage1Processor
from src.common.logger_setup import LoggerSetup


def main():
    """主函数"""
    # 读取环境模式
    ENV_MODE = os.getenv('LIMIT_MONITOR_ENV', 'development').lower()
    data_incomplete = os.getenv('DATA_INCOMPLETE', 'false').lower() == 'true'
    
    # 初始化日志
    log_setup = LoggerSetup(level="INFO")
    log_setup.setup()
    
    # 设置路径
    base_dir = Path(__file__).parent
    data_dir = base_dir / "sample data"
    output_dir = base_dir / "data" / "current" / "stage1_output"
    stage0_output_dir = base_dir / "data" / "current" / "stage0_output"
    
    logger.info("=" * 80)
    logger.info("阶段1: 限额监控数据处理")
    logger.info(f"运行模式: {'🔴 生产环境' if ENV_MODE == 'production' else '🟡 测试环境'}")
    if data_incomplete:
        logger.warning("⚠️  数据完整性: 不完整（使用旧数据）")
    logger.info("=" * 80)
    logger.info(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        # 创建处理器
        processor = Stage1Processor(
            data_dir=data_dir,
            output_dir=output_dir,
            stage0_output_dir=stage0_output_dir
        )
        
        # 执行处理
        results = processor.process_all()
        
        # 输出结果汇总
        logger.info("\n" + "=" * 80)
        logger.info("阶段1处理结果汇总")
        logger.info("=" * 80)
        
        for name, df in results.items():
            logger.info(f"✓ {name}: {len(df)} 行")
        
        logger.info("\n" + "=" * 80)
        logger.info(f"结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("阶段1处理完成！")
        if data_incomplete and ENV_MODE == 'development':
            logger.warning("⚠️  数据不完整，请勿用于生产决策")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.exception(f"阶段1处理失败: {e}")
        raise


if __name__ == "__main__":
    main()
