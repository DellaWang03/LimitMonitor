"""
日志工具
基于 loguru 的日志配置
"""

import sys
from pathlib import Path
from loguru import logger
from datetime import datetime


class LoggerSetup:
    """日志设置"""
    
    def __init__(self, log_dir: str = None, level: str = "INFO"):
        """
        初始化日志
        
        Args:
            log_dir: 日志目录
            level: 日志级别
        """
        if log_dir is None:
            # 默认日志目录
            current_file = Path(__file__)
            project_root = current_file.parent.parent.parent
            self.log_dir = project_root / "logs"
        else:
            self.log_dir = Path(log_dir)
            
        # 确保日志目录存在
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        self.level = level
        self._setup_logger()
        
    def _setup_logger(self):
        """配置日志器"""
        # 移除默认的 handler
        logger.remove()
        
        # 添加控制台输出
        logger.add(
            sys.stderr,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
                   "<level>{level: <8}</level> | "
                   "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
                   "<level>{message}</level>",
            level=self.level,
            colorize=True
        )
        
        # 添加文件输出 - 所有日志
        log_file = self.log_dir / f"limit_monitor_{datetime.now():%Y%m%d}.log"
        logger.add(
            log_file,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
            level="DEBUG",
            rotation="10 MB",
            retention="30 days",
            encoding="utf-8"
        )
        
        # 添加错误日志文件
        error_log_file = self.log_dir / f"error_{datetime.now():%Y%m%d}.log"
        logger.add(
            error_log_file,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
            level="ERROR",
            rotation="10 MB",
            retention="90 days",
            encoding="utf-8"
        )
        
    @staticmethod
    def get_logger():
        """获取日志器实例"""
        return logger


# 全局日志实例
_logger_instance = None


def setup_logger(log_dir: str = None, level: str = "INFO"):
    """
    设置全局日志
    
    Args:
        log_dir: 日志目录
        level: 日志级别
    """
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = LoggerSetup(log_dir, level)
    return _logger_instance.get_logger()


def get_logger():
    """获取日志器（如果未初始化则自动初始化）"""
    global _logger_instance
    if _logger_instance is None:
        setup_logger()
    return logger


if __name__ == "__main__":
    # 测试日志
    log = setup_logger(level="DEBUG")
    
    log.debug("这是一条 DEBUG 日志")
    log.info("这是一条 INFO 日志")
    log.warning("这是一条 WARNING 日志")
    log.error("这是一条 ERROR 日志")
    
    try:
        1 / 0
    except Exception as e:
        log.exception("捕获异常:")
        
    log.success("日志测试完成！")
