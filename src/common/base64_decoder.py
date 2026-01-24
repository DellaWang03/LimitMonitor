"""
Base64编码数据解码器
用于解码Power Query中的硬编码表格数据
"""

import base64
import zlib
import io
import pandas as pd
from loguru import logger


def decode_base64_table(base64_string: str) -> pd.DataFrame:
    """
    解码Power Query中Base64编码的表格数据
    
    参数:
        base64_string: Base64编码的字符串
        
    返回:
        解码后的DataFrame
    """
    try:
        # 1. Base64解码
        compressed_data = base64.b64decode(base64_string)
        
        # 2. zlib解压
        decompressed_data = zlib.decompress(compressed_data)
        
        # 3. 解析为字符串（通常是二进制格式的表格数据）
        # Power Query的编码格式比较复杂，这里需要根据实际情况调整
        
        logger.info(f"解码Base64数据: {len(decompressed_data)} 字节")
        
        # 尝试解析为JSON或其他格式
        # 这部分需要根据实际的M代码中的数据格式来实现
        # 暂时返回空DataFrame，待实际测试时完善
        
        logger.warning("Base64解码功能需要根据实际数据格式完善")
        return pd.DataFrame()
        
    except Exception as e:
        logger.error(f"Base64解码失败: {e}")
        raise


def parse_m_code_hardcoded_table(m_code_snippet: str) -> pd.DataFrame:
    """
    从M代码片段中解析硬编码的表格
    
    参数:
        m_code_snippet: 包含Table.FromRows的M代码片段
        
    返回:
        解析后的DataFrame
    """
    # 这个函数用于解析风控部债券池_主体_虚拟添加查询中的硬编码数据
    # 需要提取Base64字符串并解码
    
    logger.info("解析M代码中的硬编码表格")
    
    # 从M代码中提取Base64字符串
    # 示例: Binary.FromText("tV1p...", BinaryEncoding.Base64)
    import re
    
    pattern = r'Binary\.FromText\("([^"]+)",\s*BinaryEncoding\.Base64\)'
    match = re.search(pattern, m_code_snippet)
    
    if match:
        base64_str = match.group(1)
        return decode_base64_table(base64_str)
    else:
        logger.warning("未找到Base64编码数据")
        return pd.DataFrame()
