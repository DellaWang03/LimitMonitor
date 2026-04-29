"""
限额配置加载模块
从截面格式的 限额配置_当前.xlsx 读取指定 Sheet，并可选注入业务日期列。
"""
from pathlib import Path
from typing import Optional, Union

import pandas as pd
from loguru import logger

# 项目根目录（相对本文件向上两级）
_PROJECT_ROOT = Path(__file__).parent.parent.parent
_FALLBACK_PATH = _PROJECT_ROOT / "data_source_0123" / "限额配置_当前.xlsx"

_FILE_NAME = "限额配置_当前.xlsx"
_EXCEL_ENGINE = "openpyxl"


def load_limit_config(
    sheet_name: str,
    business_date=None,
    config=None,
    inject_date: bool = True,
) -> pd.DataFrame:
    """
    从 限额配置_当前.xlsx 读取指定 Sheet 的截面配置。

    参数：
        sheet_name:    Sheet 名称
        business_date: 业务日期（str "YYYY-MM-DD" 或 pd.Timestamp）
        config:        ConfigLoader 实例，用于路径 profile 切换
        inject_date:   True 时注入 '日期' 列 = pd.Timestamp(business_date)，
                       保持下游 merge(on=[..., '日期']) 兼容；
                       False 时直接返回原表（用于穿透高收益债券等无需日期 join 的 Sheet）

    路径解析：
        通过 config.get_data_file_path("限额配置_当前.xlsx") 获取；
        无 config 时 fallback 到项目根目录下的 data_source_0123/限额配置_当前.xlsx
    """
    # 1. 解析文件路径
    if config is not None and hasattr(config, "get_data_file_path"):
        file_path = config.get_data_file_path(_FILE_NAME)
    else:
        file_path = _FALLBACK_PATH

    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(
            f"限额配置文件不存在: {file_path}\n"
            f"请先准备好最新的 限额配置_当前.xlsx。"
        )

    # 2. 读取 Sheet
    df = pd.read_excel(file_path, sheet_name=sheet_name, engine=_EXCEL_ENGINE)
    logger.debug(f"load_limit_config: {sheet_name} 读取 {len(df)} 行 from {file_path.name}")

    # 3. 注入日期列
    if inject_date:
        if business_date is None:
            raise ValueError(
                f"load_limit_config: inject_date=True 时必须提供 business_date (sheet={sheet_name})"
            )
        ts = pd.Timestamp(business_date)
        df.insert(0, "日期", ts)
        logger.debug(f"load_limit_config: 注入 '日期' = {ts.date()} 到 {sheet_name}")

    return df
