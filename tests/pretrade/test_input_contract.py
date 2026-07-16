from __future__ import annotations

import pandas as pd
import pytest

from src.risk_core import STAGE1_REQUIRED_FRAMES, STAGE2_REQUIRED_FRAMES
from src.pretrade.input_contract import (
    KERNEL_INPUT_DATASETS,
    PretradeInputContractError,
    PretradeSnapshotRequest,
)

from .conftest import make_all_kernel_frames, make_kernel_input


def test_kernel_input_dataset_registry_is_the_exact_27_frame_union() -> None:
    assert KERNEL_INPUT_DATASETS == tuple(
        dict.fromkeys(STAGE1_REQUIRED_FRAMES + STAGE2_REQUIRED_FRAMES)
    )
    assert len(KERNEL_INPUT_DATASETS) == 27


def test_snapshot_request_contains_only_validated_kernel_input() -> None:
    request = PretradeSnapshotRequest.from_kernel_input(make_kernel_input())

    assert request.kernel_input.business_date == pd.Timestamp("2026-07-10")
    assert not hasattr(request, "usage")
    assert not hasattr(request, "input_hash")
    assert not hasattr(request, "source_manifest")


def test_snapshot_request_rejects_missing_dataset() -> None:
    frames = make_all_kernel_frames()
    frames.pop(KERNEL_INPUT_DATASETS[-1])

    with pytest.raises(PretradeInputContractError, match="缺少共同内核输入"):
        PretradeSnapshotRequest.from_kernel_input(make_kernel_input(frames))


def test_snapshot_request_rejects_extra_dataset() -> None:
    frames = make_all_kernel_frames()
    frames["展示长表"] = pd.DataFrame({"值": [1]})

    with pytest.raises(PretradeInputContractError, match="未注册输入"):
        PretradeSnapshotRequest.from_kernel_input(make_kernel_input(frames))
