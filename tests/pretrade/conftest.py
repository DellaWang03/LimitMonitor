from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256

import pandas as pd

from src.pretrade.config_workbook import (
    LIMIT_CONFIG_WORKBOOK_NAME,
    PretradeConfigWorkbook,
)
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


def make_config_workbook(
    payload: bytes = b"PK\x03\x04fixture-xlsx",
) -> PretradeConfigWorkbook:
    return PretradeConfigWorkbook(
        file_name=LIMIT_CONFIG_WORKBOOK_NAME,
        payload=payload,
        payload_hash=sha256(payload).hexdigest(),
    )
