from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pandas.testing as pdt
import pytest

from src.pretrade.context_capture import (
    FRAME_SOURCE,
    PretradeCaptureError,
    capture_production_kernel_input,
)
from src.pretrade.input_contract import KERNEL_INPUT_DATASETS


def _frame(dataset_code: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "数据集": pd.Series([dataset_code], dtype="string"),
            "数值": pd.Series([len(dataset_code)], dtype="Int64"),
        }
    )


def _runtime_pair() -> tuple[SimpleNamespace, SimpleNamespace]:
    stage1_cache: dict[str, pd.DataFrame] = {}
    stage2_cache: dict[str, pd.DataFrame] = {}
    for dataset_code, source in FRAME_SOURCE.items():
        if source == "stage1":
            stage1_cache[dataset_code] = _frame(dataset_code)
        elif source == "stage2":
            stage2_cache[dataset_code] = _frame(dataset_code)
        else:
            stage1_cache[dataset_code] = _frame(dataset_code)
            stage2_cache[dataset_code] = stage1_cache[dataset_code].copy(deep=True)

    return (
        SimpleNamespace(
            cache=stage1_cache,
            _business_date=pd.Timestamp("2026-07-10"),
            _runtime_regulatory_concentration_limit=0.16,
        ),
        SimpleNamespace(
            cache=stage2_cache,
            _business_date=pd.Timestamp("2026-07-10"),
        ),
    )


def test_capture_uses_exact_27_runtime_inputs_and_detaches_frames() -> None:
    stage1, stage2 = _runtime_pair()

    captured = capture_production_kernel_input(stage1, stage2)

    assert tuple(captured.frames) == KERNEL_INPUT_DATASETS
    assert captured.business_date == pd.Timestamp("2026-07-10")
    assert captured.parameters.regulatory_concentration_limit == 0.16
    for dataset_code, source in FRAME_SOURCE.items():
        expected_cache = stage1.cache if source != "stage2" else stage2.cache
        pdt.assert_frame_equal(captured.frames[dataset_code], expected_cache[dataset_code])

    stage1.cache["债券持仓明细表"].loc[0, "数值"] = 999
    assert captured.frames["债券持仓明细表"].loc[0, "数值"] != 999


def test_capture_rejects_missing_runtime_frame() -> None:
    stage1, stage2 = _runtime_pair()
    stage2.cache.pop("高收益限额")

    with pytest.raises(PretradeCaptureError, match="缺少运行缓存"):
        capture_production_kernel_input(stage1, stage2)


def test_capture_refuses_different_overlap_values() -> None:
    stage1, stage2 = _runtime_pair()
    stage2.cache["金融工具池设置"] = pd.DataFrame({"代码": ["different"]})

    with pytest.raises(PretradeCaptureError, match="同次运行重叠输入不一致"):
        capture_production_kernel_input(stage1, stage2)


def test_capture_refuses_mismatched_business_date() -> None:
    stage1, stage2 = _runtime_pair()
    stage2._business_date = pd.Timestamp("2026-07-09")

    with pytest.raises(PretradeCaptureError, match="业务日期不一致"):
        capture_production_kernel_input(stage1, stage2)


def test_capture_requires_stage1_resolved_regulatory_limit() -> None:
    stage1, stage2 = _runtime_pair()
    del stage1._runtime_regulatory_concentration_limit

    with pytest.raises(PretradeCaptureError, match="监管集中度参数"):
        capture_production_kernel_input(stage1, stage2)
