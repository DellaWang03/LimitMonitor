"""
阶段0主程序
执行阶段0的10个查询，输出到data/current/stage0_output/
"""

import sys
import os
import json
from pathlib import Path
from datetime import datetime

# 添加src到路径
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.stage0 import Stage0Processor
from src.utils.logger import LoggerSetup
from src.utils import DateValidator


def main():
    """主函数"""
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
    logger.info(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 80)
    
    try:
        # 设置路径
        project_root = Path(__file__).parent
        data_dir = project_root / "sample data"
        output_dir = project_root / "data" / "current" / "stage0_output"
        current_dir = project_root / "data" / "current"
        
        logger.info(f"\n数据目录: {data_dir}")
        logger.info(f"输出目录: {output_dir}")
        
        # 检查数据目录
        if not data_dir.exists():
            logger.error(f"数据目录不存在: {data_dir}")
            return 1
        
        # 【新增】日期验证
        logger.info("\n" + "=" * 80)
        logger.info("数据新鲜度验证")
        logger.info("=" * 80)
        
        data_is_fresh = True
        actual_data_date = None
        expected_data_date = None
        
        try:
            date_validator = DateValidator(data_dir)
            
            # 显示业务日期信息
            date_validator.log_business_date_summary()
            
            # 验证Access数据库新鲜度
            access_db_path = data_dir / "风控部债券池.accdb"
            
            if access_db_path.exists():
                # 根据环境设置严格模式
                strict_mode = (ENV_MODE == 'production')
                
                is_fresh, message, actual_date = date_validator.validate_access_database_freshness(
                    access_db_path,
                    strict_mode=strict_mode
                )
                
                data_is_fresh = is_fresh
                if actual_date:
                    actual_data_date = actual_date.strftime('%Y-%m-%d')
                expected_data_date = date_validator.get_t_minus_1_date().strftime('%Y-%m-%d')
                
                if not is_fresh:
                    if ENV_MODE == 'production':
                        # 生产环境：strict_mode=True已抛出异常，不会到这里
                        logger.error("❌ 生产环境数据未更新，已停止处理")
                        return 1
                    else:
                        # 测试环境：警告但继续
                        logger.warning("\n" + "=" * 80)
                        logger.warning("⚠️  【测试模式】数据新鲜度检查未通过")
                        logger.warning(f"   Access数据日期: {actual_data_date}")
                        logger.warning(f"   预期日期（T-1）: {expected_data_date}")
                        logger.warning("   将继续处理并保存到 data/current/")
                        logger.warning("   ❌ 不会归档到 data/history/（数据不完整）")
                        logger.warning("=" * 80)
                        
                        # 设置环境变量标记（供后续阶段和归档脚本使用）
                        os.environ['DATA_INCOMPLETE'] = 'true'
                        os.environ['DATA_INCOMPLETE_REASON'] = 'access_db_outdated'
            else:
                logger.warning(f"⚠️  Access数据库不存在: {access_db_path}")
                logger.warning(f"   将使用fallback数据源（如果可用）")
                data_is_fresh = False
                os.environ['DATA_INCOMPLETE'] = 'true'
                os.environ['DATA_INCOMPLETE_REASON'] = 'access_db_missing'
        
        except Exception as e:
            if ENV_MODE == 'production':
                logger.error(f"❌ 生产环境日期验证失败: {e}")
                return 1
            else:
                logger.warning(f"⚠️  日期验证失败: {e}")
                logger.warning(f"   将继续处理，但无法确认数据新鲜度")
                data_is_fresh = False
                os.environ['DATA_INCOMPLETE'] = 'true'
                os.environ['DATA_INCOMPLETE_REASON'] = 'validation_failed'
        
        # 创建处理器
        processor = Stage0Processor(
            data_dir=data_dir,
            output_dir=output_dir
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
                
                try:
                    date_info = date_validator.get_business_date_info()
                    logger.info(f"预期日期（T-1）: {date_info['t_minus_1']}")
                    
                    if pool_date.date() == date_info['t_minus_1']:
                        logger.info("✅ 数据日期验证通过")
                    else:
                        logger.warning("⚠️  数据日期与T-1不匹配")
                except:
                    pass
        
        if '债券池日期' in results:
            df_dates = results['债券池日期']
            if '日期' in df_dates.columns and len(df_dates) > 0:
                date_count = len(df_dates)
                latest_date = pd.to_datetime(df_dates['日期']).max()
                logger.info(f"债券池日期表: 共{date_count}个日期，最新为 {latest_date.date()}")
        
        # 【新增】数据不完整时创建警告文件
        if not data_is_fresh and ENV_MODE == 'development':
            warning_file = current_dir / '.INCOMPLETE_DATA_WARNING'
            warning_data = {
                'warning': '数据不完整，仅供测试使用',
                'environment': 'development',
                'reason': os.getenv('DATA_INCOMPLETE_REASON', 'unknown'),
                'access_date': actual_data_date,
                'expected_date': expected_data_date,
                'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'message': '此数据不应归档到 history/ 目录，仅用于测试、校验和可视化'
            }
            
            try:
                current_dir.mkdir(parents=True, exist_ok=True)
                with open(warning_file, 'w', encoding='utf-8') as f:
                    json.dump(warning_data, f, indent=2, ensure_ascii=False)
                logger.warning(f"\n⚠️  已创建数据完整性警告文件: {warning_file.name}")
            except Exception as e:
                logger.warning(f"⚠️  无法创建警告文件: {e}")
        elif data_is_fresh:
            # 数据完整，删除可能存在的警告文件
            warning_file = current_dir / '.INCOMPLETE_DATA_WARNING'
            if warning_file.exists():
                try:
                    warning_file.unlink()
                    logger.info("✅ 已删除旧的数据完整性警告文件")
                except:
                    pass
        
        logger.info("\n" + "=" * 80)
        logger.info(f"结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("阶段0处理完成！")
        if not data_is_fresh and ENV_MODE == 'development':
            logger.warning("⚠️  数据不完整，请勿用于生产决策")
        logger.info("=" * 80)
        
        return 0
        
    except Exception as e:
        logger.error(f"\n处理失败: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
