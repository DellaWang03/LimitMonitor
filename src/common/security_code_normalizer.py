"""
证券代码标准化工具
"""

import pandas as pd


def normalize_security_code_series(series: pd.Series) -> pd.Series:
    """标准化证券代码，仅用于分组和匹配键。"""
    normalized = series.apply(
        lambda value: None if pd.isna(value) else str(value).strip()
    )
    normalized = normalized.replace({'': None, 'nan': None, 'None': None})
    return normalized.apply(
        lambda value: value.upper() if isinstance(value, str) else value
    )
