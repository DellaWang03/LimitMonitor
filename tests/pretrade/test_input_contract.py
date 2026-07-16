from __future__ import annotations

import pandas as pd
import pytest

from src.risk_core import STAGE1_REQUIRED_FRAMES, STAGE2_REQUIRED_FRAMES
from src.pretrade.input_contract import (
    KERNEL_INPUT_DATASETS,
    PretradeInputContractError,
    PretradeSnapshotRequest,
)

from .conftest import make_all_kernel_frames, make_config_workbook, make_kernel_input


def test_kernel_input_dataset_registry_is_the_exact_27_frame_union() -> None:
    assert KERNEL_INPUT_DATASETS == tuple(
        dict.fromkeys(STAGE1_REQUIRED_FRAMES + STAGE2_REQUIRED_FRAMES)
    )
    assert len(KERNEL_INPUT_DATASETS) == 27


def test_snapshot_request_contains_validated_kernel_input_and_config_workbook() -> None:
    workbook = make_config_workbook()
    request = PretradeSnapshotRequest.from_kernel_input(make_kernel_input(), workbook)

    assert request.kernel_input.business_date == pd.Timestamp("2026-07-10")
    assert request.config_workbook == workbook
    assert not hasattr(request, "usage")
    assert not hasattr(request, "input_hash")
    assert not hasattr(request, "source_manifest")


def test_snapshot_request_rejects_missing_dataset() -> None:
    frames = make_all_kernel_frames()
    frames.pop(KERNEL_INPUT_DATASETS[-1])

    with pytest.raises(PretradeInputContractError, match="缺少共同内核输入"):
        PretradeSnapshotRequest.from_kernel_input(
            make_kernel_input(frames), make_config_workbook()
        )


def test_snapshot_request_rejects_extra_dataset() -> None:
    frames = make_all_kernel_frames()
    frames["展示长表"] = pd.DataFrame({"值": [1]})

    with pytest.raises(PretradeInputContractError, match="未注册输入"):
        PretradeSnapshotRequest.from_kernel_input(
            make_kernel_input(frames), make_config_workbook()
        )


def test_snapshot_request_requires_config_workbook() -> None:
    with pytest.raises(TypeError, match="config_workbook"):
        PretradeSnapshotRequest.from_kernel_input(make_kernel_input(), None)
