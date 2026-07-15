"""Compatibility adapter for the shared Stage1 production limit engine."""

from collections.abc import Mapping

import pandas as pd

from ..risk_core.stage1_limits import SOURCE_ROW_ID_COL, Stage1LimitEngine
from ..utils.config_loader import ConfigLoader
from ..utils.limit_config_loader import load_limit_config


class LimitDetailCalculator(Stage1LimitEngine):
    """Retain the production import path and legacy lazy configuration fallback."""

    def __init__(
        self,
        cache: Mapping[str, pd.DataFrame],
        regulatory_concentration_limit: float | None = None,
    ):
        super().__init__(
            cache,
            0.0
            if regulatory_concentration_limit is None
            else regulatory_concentration_limit,
        )
        # Legacy callers register dependent intermediate tables after construction.
        # Keep that adapter contract while the direct shared engine remains detached.
        self.cache = cache
        self._regulatory_concentration_limit_override = (
            regulatory_concentration_limit
        )

    def _load_regulatory_concentration_limit(self) -> float:
        if self._regulatory_concentration_limit_override is not None:
            return self._regulatory_concentration_limit

        config = ConfigLoader()
        df = load_limit_config(
            sheet_name="系统参数",
            config=config,
            inject_date=False,
        )
        if "参数名" not in df.columns or "值" not in df.columns:
            raise KeyError("系统参数 sheet 缺少 '参数名' 或 '值' 列")

        row_map = (
            df.assign(参数名=df["参数名"].astype(str).str.strip())
            .drop_duplicates(subset=["参数名"], keep="first")
            .set_index("参数名")["值"]
            .to_dict()
        )
        if "监管集中度限额" not in row_map:
            raise KeyError("系统参数 sheet 缺少 '监管集中度限额' 参数")

        value = row_map["监管集中度限额"]
        if pd.isna(value):
            raise ValueError("系统参数 sheet 中 '监管集中度限额' 为空")
        return float(value)
