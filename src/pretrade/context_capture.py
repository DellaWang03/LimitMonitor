"""从同一次 Stage1/Stage2 运行缓存捕获共同内核输入。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

import pandas as pd

from src.risk_core import ProductionKernelInput, ProductionKernelParameters

from .input_contract import KERNEL_INPUT_DATASETS


FrameSource = Literal["stage1", "stage2"]

# 每个键只允许从本次运行中已经实际用于上线计算的缓存取得。
# Stage2 会从 Stage1 的导出 Excel 重读部分共享表；共同内核以 Stage1 的
# 同次内存输入为唯一来源，避免把 Excel 二进制浮点往返误差带入交易前快照。
FRAME_SOURCE: dict[str, FrameSource] = {
    "债券持仓明细表": "stage1",
    "债券持仓明细表_信用债": "stage1",
    "债券持仓明细表_全量债券监管集中度": "stage1",
    "穿透高收益债券": "stage1",
    "金融工具池设置": "stage1",
    "中债隐含评级AAA&AAA+": "stage1",
    "风控部债券池": "stage1",
    "风控部主体池": "stage1",
    "发行人类型调整表": "stage1",
    "调整实控人名单": "stage1",
    "高风险行业": "stage1",
    "高风险省份": "stage1",
    "单一债券集中度限额": "stage1",
    "单一债券规模限额": "stage1",
    "特批单一债券限额": "stage1",
    "单一主体规模限额": "stage1",
    "单一实控人规模限额": "stage1",
    "特定主体限额": "stage1",
    "特定实控人限额": "stage1",
    "单一担保公司规模限额": "stage1",
    "ISIN码映射": "stage1",
    "高风险限额": "stage2",
    "地域集中度限额(含城投)": "stage2",
    "债券持仓表_核算系统": "stage2",
    "穿透高收益_投资本金规模": "stage2",
    "公司净资产_手工_每日": "stage2",
    "高收益限额": "stage2",
}


class PretradeCaptureError(ValueError):
    """运行时缓存不能构成可重放的共同内核输入。"""


if tuple(FRAME_SOURCE) != KERNEL_INPUT_DATASETS:
    raise RuntimeError("FRAME_SOURCE 必须精确覆盖共同内核的 27 个输入")


def _cache_of(runtime: Any, stage_name: str) -> Mapping[str, pd.DataFrame]:
    cache = getattr(runtime, "cache", None)
    if not isinstance(cache, Mapping):
        raise PretradeCaptureError(f"{stage_name} 缺少运行缓存")
    return cache


def _require_frame(
    cache: Mapping[str, pd.DataFrame], *, dataset_code: str, stage_name: str
) -> pd.DataFrame:
    frame = cache.get(dataset_code)
    if frame is None:
        raise PretradeCaptureError(f"{stage_name} 缺少运行缓存: {dataset_code}")
    if not isinstance(frame, pd.DataFrame):
        raise PretradeCaptureError(f"{stage_name} 运行缓存不是 DataFrame: {dataset_code}")
    return frame


def _business_date_of(runtime: Any, stage_name: str) -> pd.Timestamp:
    value = getattr(runtime, "_business_date", None)
    if value is None:
        raise PretradeCaptureError(f"{stage_name} 缺少业务日期")
    try:
        business_date = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise PretradeCaptureError(f"{stage_name} 业务日期无法解析") from exc
    if pd.isna(business_date) or business_date.tz is not None:
        raise PretradeCaptureError(f"{stage_name} 业务日期无效")
    if business_date != business_date.normalize():
        raise PretradeCaptureError(f"{stage_name} 业务日期必须精确到日")
    return business_date


def capture_production_kernel_input(
    stage1: Any, stage2: Any
) -> ProductionKernelInput:
    """从同次 Stage1/Stage2 缓存建立脱离原缓存的共同内核输入。"""

    stage1_cache = _cache_of(stage1, "Stage1")
    stage2_cache = _cache_of(stage2, "Stage2")
    stage1_date = _business_date_of(stage1, "Stage1")
    stage2_date = _business_date_of(stage2, "Stage2")
    if stage1_date != stage2_date:
        raise PretradeCaptureError("Stage1 与 Stage2 业务日期不一致")

    regulatory_limit = getattr(stage1, "_runtime_regulatory_concentration_limit", None)
    if regulatory_limit is None:
        raise PretradeCaptureError("Stage1 未记录实际解析的监管集中度参数")
    try:
        parameters = ProductionKernelParameters(float(regulatory_limit))
    except (TypeError, ValueError) as exc:
        raise PretradeCaptureError("Stage1 监管集中度参数无效") from exc

    frames: dict[str, pd.DataFrame] = {}
    for dataset_code, source in FRAME_SOURCE.items():
        if source == "stage1":
            frames[dataset_code] = _require_frame(
                stage1_cache, dataset_code=dataset_code, stage_name="Stage1"
            )
        else:
            frames[dataset_code] = _require_frame(
                stage2_cache, dataset_code=dataset_code, stage_name="Stage2"
            )

    return ProductionKernelInput(
        business_date=stage1_date,
        frames=frames,
        parameters=parameters,
    )
