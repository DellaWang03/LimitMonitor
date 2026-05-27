"""
测试阶段2处理 - 分步执行
"""

from pathlib import Path
from loguru import logger
from src.stage2 import Stage2Processor

def main():
    """主函数"""
    # 设置路径
    project_root = Path(__file__).parent
    data_dir = project_root / "sample data"
    stage0_output_dir = project_root / "data" / "stage0_output"
    stage1_output_dir = project_root / "data" / "stage1_output"
    stage2_output_dir = project_root / "data" / "stage2_output"
    
    # 配置日志
    logger.remove()
    logger.add(
        lambda msg: print(msg, end=''),
        format="{message}",
        level="INFO"
    )
    
    logger.info("=" * 100)
    logger.info(" " * 35 + "阶段2测试运行")
    logger.info("=" * 100)
    
    # 创建处理器
    processor = Stage2Processor(
        data_dir=data_dir,
        output_dir=stage2_output_dir,
        stage0_output_dir=stage0_output_dir,
        stage1_output_dir=stage1_output_dir
    )
    
    try:
        # 执行处理
        results = processor.process_all()
        
        logger.info("\n" + "=" * 100)
        logger.info("✅ 阶段2处理完成!")
        logger.info("=" * 100)
        logger.info(f"\n生成表格数: {len(results)}")
        
        for i, (name, df) in enumerate(results.items(), 1):
            logger.info(f"  {i:2d}. {name}: {len(df)} 行 × {len(df.columns)} 列")
        
        return results
        
    except Exception as e:
        logger.error(f"\n❌ 处理失败: {e}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()
