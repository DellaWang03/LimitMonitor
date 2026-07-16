from __future__ import annotations

from collections.abc import Mapping

import pandas as pd

from src.risk_core import (
    STAGE1_REQUIRED_FRAMES,
    STAGE2_REQUIRED_FRAMES,
    ProductionKernelInput,
    ProductionKernelParameters,
)


KERNEL_DATASET_CODES = tuple(
    dict.fromkeys(STAGE1_REQUIRED_FRAMES + STAGE2_REQUIRED_FRAMES)
)


def make_all_kernel_frames() -> dict[str, pd.DataFrame]:
    return {
        name: pd.DataFrame({"数据集": [name], "值": [index]})
        for index, name in enumerate(KERNEL_DATASET_CODES)
    }


def make_kernel_input(
    frames: Mapping[str, pd.DataFrame] | None = None,
    *,
    business_date: str = "2026-07-10",
    regulatory_limit: float = 0.16,
) -> ProductionKernelInput:
    return ProductionKernelInput(
        business_date=pd.Timestamp(business_date),
        frames=make_all_kernel_frames() if frames is None else frames,
        parameters=ProductionKernelParameters(regulatory_limit),
    )
