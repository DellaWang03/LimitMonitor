from __future__ import annotations

import pandas as pd
import pandas.testing as pdt
import pytest

from src.risk_core.contracts import (
    STAGE1_REQUIRED_FRAMES,
    STAGE2_REQUIRED_FRAMES,
    MissingKernelFramesError,
    ProductionKernelInput,
    ProductionKernelParameters,
)
from src.risk_core.kernel import ProductionRiskKernel


def _frames(names: tuple[str, ...]) -> dict[str, pd.DataFrame]:
    return {name: pd.DataFrame(columns=["日期", "值"]) for name in names}


def test_stage1_shell_fails_closed_on_missing_required_frame(business_date):
    frames = _frames(STAGE1_REQUIRED_FRAMES)
    missing = STAGE1_REQUIRED_FRAMES[-1]
    frames.pop(missing)
    inputs = ProductionKernelInput(
        business_date=business_date,
        frames=frames,
        parameters=ProductionKernelParameters(0.16),
    )
    with pytest.raises(MissingKernelFramesError, match=missing):
        ProductionRiskKernel().run_stage1(inputs)


def test_stage1_shell_is_deterministic_and_does_not_mutate_inputs(business_date):
    frames = _frames(STAGE1_REQUIRED_FRAMES)
    first_key = STAGE1_REQUIRED_FRAMES[0]
    frames[first_key] = pd.DataFrame({"日期": [business_date], "值": [1]})
    before = {name: frame.copy(deep=True) for name, frame in frames.items()}
    inputs = ProductionKernelInput(
        business_date=business_date,
        frames=frames,
        parameters=ProductionKernelParameters(0.16),
    )
    kernel = ProductionRiskKernel()

    assert kernel.run_stage1(inputs) == {}
    assert kernel.run_stage1(inputs) == {}
    for name, frame in frames.items():
        pdt.assert_frame_equal(frame, before[name], check_exact=True)


def test_stage2_shell_validates_frames_and_does_not_mutate_stage1_tables(business_date):
    frames = _frames(tuple(dict.fromkeys(STAGE1_REQUIRED_FRAMES + STAGE2_REQUIRED_FRAMES)))
    inputs = ProductionKernelInput(
        business_date=business_date,
        frames=frames,
        parameters=ProductionKernelParameters(0.16),
    )
    stage1_tables = {"阶段1结果": pd.DataFrame({"值": [1], "对象": [["a"]]})}
    before = stage1_tables["阶段1结果"].copy(deep=True)

    kernel = ProductionRiskKernel()
    assert kernel.run_stage2(inputs, stage1_tables) == {}
    pdt.assert_frame_equal(stage1_tables["阶段1结果"], before, check_exact=True)

    missing_frames = dict(frames)
    missing = STAGE2_REQUIRED_FRAMES[-1]
    missing_frames.pop(missing)
    incomplete = ProductionKernelInput(
        business_date=business_date,
        frames=missing_frames,
        parameters=ProductionKernelParameters(0.16),
    )
    with pytest.raises(MissingKernelFramesError, match=missing):
        kernel.run_stage2(incomplete, stage1_tables)
