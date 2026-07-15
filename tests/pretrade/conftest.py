from __future__ import annotations

from collections.abc import Mapping

import pandas as pd
import pytest

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


@pytest.fixture
def source_manifest() -> dict[str, object]:
    return {
        "files": [{"name": "input.xlsx", "sha256": "a" * 64}],
        "static_issuer_mapping": {
            "sha256": "b" * 64,
            "row_count": 4,
            "validated_at": "2026-07-15T12:00:00+08:00",
        },
        "captured_at": "2026-07-15T12:00:00+08:00",
    }
