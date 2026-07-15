from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from math import isfinite
from numbers import Real
from types import MappingProxyType

import pandas as pd


STAGE1_REQUIRED_FRAMES: tuple[str, ...] = (
    "债券持仓明细表",
    "债券持仓明细表_信用债",
    "债券持仓明细表_全量债券监管集中度",
    "穿透高收益债券",
    "金融工具池设置",
    "中债隐含评级AAA&AAA+",
    "风控部债券池",
    "风控部主体池",
    "发行人类型调整表",
    "调整实控人名单",
    "高风险行业",
    "高风险省份",
    "单一债券集中度限额",
    "单一债券规模限额",
    "特批单一债券限额",
    "单一主体规模限额",
    "单一实控人规模限额",
    "特定主体限额",
    "特定实控人限额",
    "单一担保公司规模限额",
)


STAGE2_REQUIRED_FRAMES: tuple[str, ...] = (
    "债券持仓明细表_信用债",
    "债券持仓明细表_信用债_合并风险限额相关",
    "高风险行业",
    "高风险省份",
    "地域集中度限额(含城投)",
    "ISIN码映射",
    "金融工具池设置",
    "穿透高收益债券",
    "债券持仓表_核算系统",
    "穿透高收益_投资本金规模",
    "公司净资产_手工_每日",
    "高收益限额",
)


class MissingKernelFramesError(KeyError):
    """Raised when a required dataset key is absent from the kernel input."""


def _copy_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Copy a frame and mutable Python objects stored in object cells."""
    copied = frame.copy(deep=True)
    for column in copied.columns:
        if pd.api.types.is_object_dtype(copied[column].dtype):
            copied[column] = copied[column].map(deepcopy, na_action="ignore")
    return copied


def _freeze_frames(
    frames: Mapping[str, pd.DataFrame],
    *,
    field_name: str,
) -> Mapping[str, pd.DataFrame]:
    if not isinstance(frames, Mapping):
        raise TypeError(f"{field_name} must be a mapping of pandas DataFrame values")

    frozen: dict[str, pd.DataFrame] = {}
    for name, frame in frames.items():
        if not isinstance(name, str) or not name:
            raise TypeError(f"{field_name} keys must be non-empty strings")
        if not isinstance(frame, pd.DataFrame):
            raise TypeError(f"{field_name}[{name!r}] must be a pandas DataFrame")
        frozen[name] = _copy_frame(frame)
    return MappingProxyType(frozen)


def _detached_frames(frames: Mapping[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    return {name: _copy_frame(frame) for name, frame in frames.items()}


@dataclass(frozen=True)
class ProductionKernelParameters:
    regulatory_concentration_limit: float

    def __post_init__(self) -> None:
        value = self.regulatory_concentration_limit
        if isinstance(value, bool) or not isinstance(value, Real):
            raise TypeError("regulatory_concentration_limit must be numeric and finite")
        numeric = float(value)
        if not isfinite(numeric):
            raise ValueError("regulatory_concentration_limit must be finite")
        object.__setattr__(self, "regulatory_concentration_limit", numeric)


@dataclass(frozen=True)
class ProductionKernelInput:
    business_date: pd.Timestamp
    frames: Mapping[str, pd.DataFrame]
    parameters: ProductionKernelParameters

    def __post_init__(self) -> None:
        business_date = self.business_date
        if not isinstance(business_date, pd.Timestamp):
            raise TypeError("business_date must be a pandas Timestamp")
        if pd.isna(business_date):
            raise ValueError("business_date must not be NaT")
        if business_date.tz is not None:
            raise ValueError("business_date must be timezone-naive")
        if business_date != business_date.normalize():
            raise ValueError("business_date must contain a date without a time component")
        if not isinstance(self.parameters, ProductionKernelParameters):
            raise TypeError("parameters must be ProductionKernelParameters")
        object.__setattr__(self, "frames", _freeze_frames(self.frames, field_name="frames"))

    def detached_frames(self) -> dict[str, pd.DataFrame]:
        return _detached_frames(self.frames)

    def require_frames(self, required: Sequence[str]) -> dict[str, pd.DataFrame]:
        missing = [name for name in required if name not in self.frames]
        if missing:
            raise MissingKernelFramesError(f"共同内核缺少必需输入表: {missing}")
        return {name: _copy_frame(self.frames[name]) for name in required}


@dataclass(frozen=True)
class ProductionKernelResult:
    stage1_tables: Mapping[str, pd.DataFrame]
    stage2_tables: Mapping[str, pd.DataFrame]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "stage1_tables",
            _freeze_frames(self.stage1_tables, field_name="stage1_tables"),
        )
        object.__setattr__(
            self,
            "stage2_tables",
            _freeze_frames(self.stage2_tables, field_name="stage2_tables"),
        )

    def detached_stage1_tables(self) -> dict[str, pd.DataFrame]:
        return _detached_frames(self.stage1_tables)

    def detached_stage2_tables(self) -> dict[str, pd.DataFrame]:
        return _detached_frames(self.stage2_tables)
