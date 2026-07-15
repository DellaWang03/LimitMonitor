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


def test_snapshot_request_rejects_missing_dataset(source_manifest) -> None:
    frames = make_all_kernel_frames()
    frames.pop(KERNEL_INPUT_DATASETS[-1])

    with pytest.raises(PretradeInputContractError, match="缺少共同内核输入"):
        PretradeSnapshotRequest.from_kernel_input(
            make_kernel_input(frames),
            usage="DEV",
            source_manifest=source_manifest,
        )


def test_snapshot_request_rejects_extra_dataset(source_manifest) -> None:
    frames = make_all_kernel_frames()
    frames["展示长表"] = pd.DataFrame({"值": [1]})

    with pytest.raises(PretradeInputContractError, match="未注册输入"):
        PretradeSnapshotRequest.from_kernel_input(
            make_kernel_input(frames),
            usage="DEV",
            source_manifest=source_manifest,
        )


def test_snapshot_request_hash_is_independent_of_frame_mapping_order(source_manifest) -> None:
    frames = make_all_kernel_frames()
    reversed_frames = dict(reversed(list(frames.items())))

    original = PretradeSnapshotRequest.from_kernel_input(
        make_kernel_input(frames), usage="DEV", source_manifest=source_manifest
    )
    reordered = PretradeSnapshotRequest.from_kernel_input(
        make_kernel_input(reversed_frames), usage="DEV", source_manifest=source_manifest
    )

    assert original.input_hash == reordered.input_hash


def test_snapshot_request_hash_changes_when_input_data_changes(source_manifest) -> None:
    original_frames = make_all_kernel_frames()
    changed_frames = make_all_kernel_frames()
    changed_frames[KERNEL_INPUT_DATASETS[0]].loc[0, "值"] = 999

    original = PretradeSnapshotRequest.from_kernel_input(
        make_kernel_input(original_frames), usage="DEV", source_manifest=source_manifest
    )
    changed = PretradeSnapshotRequest.from_kernel_input(
        make_kernel_input(changed_frames), usage="DEV", source_manifest=source_manifest
    )

    assert original.input_hash != changed.input_hash


def test_snapshot_request_rejects_invalid_usage(source_manifest) -> None:
    with pytest.raises(PretradeInputContractError, match="usage"):
        PretradeSnapshotRequest.from_kernel_input(
            make_kernel_input(), usage="TEST", source_manifest=source_manifest
        )
