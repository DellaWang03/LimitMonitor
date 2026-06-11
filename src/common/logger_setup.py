"""
日志配置模块
"""

from loguru import logger
import sys


class LoggerSetup:
    """日志设置类"""
    
    def __init__(self, level="INFO"):
        """
        初始化日志设置
        
        Args:
            level: 日志级别 (DEBUG, INFO, WARNING, ERROR)
        """
        self.level = level
    
    def setup(self):
        """配置日志"""
        # 移除默认的handler
        logger.remove()
        
        # 添加新的handler，输出到stdout
        logger.add(
            sys.stdout,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
            level=self.level,
            colorize=True
        )
        
        logger.info(f"日志系统已初始化，级别: {self.level}")
