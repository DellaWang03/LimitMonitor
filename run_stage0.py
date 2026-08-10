"""
阶段0主程序
执行阶段0的10个查询，输出到data/current/stage0_output/

历史补跑模式（--target-date）:
  在 T+N 需要补跑 T-1 数据时使用。此时统计报表底稿 Excel 通常尚未更新仍是 T-1
  的数据，但 风控部债券池.accdb 已更新到更新日期。通过指定 --target-date，让
  Stage0 从 accdb 中取该指定日期的记录，而非默认的最新日期。
  Stage1/Stage2 正常运行后，用 scripts/daily_archive.py --archive-date <date> 归档即可。
"""

import sys
import os
import argparse
from pathlib import Path
from datetime import datetime

# 添加src到路径
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.stage0 import Stage0Processor
from src.utils.logger import LoggerSetup
from src.utils import DateValidator
from src.utils.config_loader import get_config


def validate_current_inputs(config, target_date: str | None, environment: str) -> dict[str, str | bool | None]:
    """验证日常运行的必需输入，不以 T-1 新鲜度阻断完整数据归档。

    Access 最新日期相对 T-1 的偏差只用于运行日志；业务日期、文件存在性和
    日期解析仍是必需条件，不能被“最新可用”策略掩盖。
    """

    data_dir = config.get_data_dir()
    if not data_dir.exists():
        raise FileNotFoundError(f"数据目录不存在: {data_dir}")

    if target_date is not None:
        datetime.strptime(target_date, "%Y-%m-%d")

    date_validator = DateValidator(data_dir, config=config)
    date_validator.log_business_date_summary()
    access_db_path = config.get_data_file_path("风控部债券池.accdb")
    if not access_db_path.exists():
        raise FileNotFoundError(f"Access 数据库不存在: {access_db_path}")

    expected_date = date_validator.get_t_minus_1_date().strftime("%Y-%m-%d")
    if target_date is not None:
        return {
            "actual_date": None,
            "expected_t_minus_1_date": expected_date,
            "is_t_minus_1": None,
            "target_date": target_date,
        }

    is_fresh, message, actual_date = date_validator.validate_access_database_freshness(
        access_db_path,
        strict_mode=False,
    )
    actual_date_text = actual_date.strftime("%Y-%m-%d") if actual_date else None
    if not is_fresh:
        print(
            "⚠️  Access 数据日期与 T-1 不一致，但完整性校验继续："
            f"实际={actual_date_text}，预期={expected_date}，说明={message}"
        )
    return {
        "actual_date": actual_date_text,
        "expected_t_minus_1_date": expected_date,
        "is_t_minus_1": is_fresh,
        "target_date": None,
    }


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="阶段0：数据提取")
    parser.add_argument(
        "--target-date",
        metavar="YYYY-MM-DD",
        help=(
            "目标日期（补跑模式）：从 风控部债券池.accdb 中取该日期的记录而非最新日期。"
            "用于 T+N 补跑 T-1 数据，此时 Excel 底稿仍是 T-1 数据，但 accdb 已更新。"
        ),
    )
    args = parser.parse_args()
    target_date: str | None = args.target_date

    # 读取环境模式
    ENV_MODE = os.getenv('LIMIT_MONITOR_ENV', 'development').lower()
    
    # 设置日志
    log_dir = Path(__file__).parent / "logs"
    logger_setup = LoggerSetup(
        log_dir=log_dir,
        level="INFO"
    )
    logger = logger_setup.get_logger()
    
    logger.info("=" * 80)
    logger.info("限额监控系统 - 阶段0数据处理")
    logger.info(f"运行模式: {'🔴 生产环境' if ENV_MODE == 'production' else '🟡 测试环境'}")
    if target_date:
        logger.info(f"🔁 补跑模式: 目标日期 = {target_date}")
    logger.info(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 80)
    
    try:
        # 设置路径
        project_root = Path(__file__).parent
        
        # 从配置文件读取数据源目录
        config = get_config()
        data_dir = config.get_data_dir()
        
        output_dir = project_root / "data" / "current" / "stage0_output"
        
        profile = config.get_active_profile()
        logger.info(f"\n路径 profile: {profile} (一键切换: 修改 config/settings.yaml 中 data_sources.active_profile 或设置环境变量 LIMIT_MONITOR_PROFILE)")
        logger.info(f"数据目录: {data_dir}")
        logger.info(f"输出目录: {output_dir}")
        # 日期验证：T-1 偏差仅记录 warning；缺文件或不可解析日期仍立即失败。
        logger.info("\n" + "=" * 80)
        if target_date:
            logger.info(f"数据日期校验（补跑模式 - 目标日期: {target_date}）")
        else:
            logger.info("数据完整性与新鲜度记录")
        logger.info("=" * 80)
        validation = validate_current_inputs(config, target_date, ENV_MODE)
        if target_date:
            logger.info(f"⏭️  补跑模式：目标日期={target_date}")
        else:
            logger.info(
                "Access 数据日期："
                f"实际={validation['actual_date']}，"
                f"预期 T-1={validation['expected_t_minus_1_date']}，"
                f"是否一致={validation['is_t_minus_1']}"
            )
        
        # 创建处理器（传入 config 以支持路径 profile 一键切换）
        processor = Stage0Processor(
            data_dir=data_dir,
            output_dir=output_dir,
            config=config,
            target_date=target_date,
        )
        
        # 执行所有查询
        results = processor.process_all()
        
        # 汇总报告
        logger.info("\n" + "=" * 80)
        logger.info("阶段0处理结果汇总")
        logger.info("=" * 80)
        
        for query_name, df in results.items():
            if len(df) > 0:
                logger.info(f"✓ {query_name}: {len(df)} 行")
            else:
                logger.warning(f"⚠️  {query_name}: 无数据")
        
        # 【新增】数据日期总结
        logger.info("\n" + "=" * 80)
        logger.info("数据日期总结")
        logger.info("=" * 80)
        
        import pandas as pd
        
        if '风控部债券池' in results:
            df_pool = results['风控部债券池']
            if '日期' in df_pool.columns and len(df_pool) > 0:
                pool_date = pd.to_datetime(df_pool['日期']).max()
                logger.info(f"风控部债券池日期: {pool_date.date()}")
                
                if target_date:
                    # 补跑模式：与目标日期对比，而非 T-1
                    import pandas as _pd
                    expected_ts = _pd.Timestamp(target_date)
                    if pool_date.date() == expected_ts.date():
                        logger.info(f"✅ 数据日期与目标日期一致（{target_date}）")
                    else:
                        logger.error(f"❌ 数据日期 {pool_date.date()} 与目标日期 {target_date} 不一致，请检查 accdb 是否含该日期数据")
        
        if '债券池日期' in results:
            df_dates = results['债券池日期']
            if '日期' in df_dates.columns and len(df_dates) > 0:
                date_count = len(df_dates)
                latest_date = pd.to_datetime(df_dates['日期']).max()
                logger.info(f"债券池日期表: 共{date_count}个日期，最新为 {latest_date.date()}")
        
        logger.info("\n" + "=" * 80)
        logger.info(f"结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("阶段0处理完成！")
        logger.info("=" * 80)
        
        return 0
        
    except Exception as e:
        logger.error(f"\n处理失败: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
