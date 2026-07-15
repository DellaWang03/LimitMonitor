from __future__ import annotations

from collections.abc import Mapping

import pandas as pd

from .contracts import (
    STAGE1_REQUIRED_FRAMES,
    STAGE2_REQUIRED_FRAMES,
    ProductionKernelInput,
    _copy_frame,
)


class ProductionRiskKernel:
    """Pure orchestration shell populated incrementally by extraction tasks."""

    def run_stage1(self, inputs: ProductionKernelInput) -> dict[str, pd.DataFrame]:
        if not isinstance(inputs, ProductionKernelInput):
            raise TypeError("inputs must be ProductionKernelInput")
        inputs.require_frames(STAGE1_REQUIRED_FRAMES)
        return {}

    def run_stage2(
        self,
        inputs: ProductionKernelInput,
        stage1_tables: Mapping[str, pd.DataFrame],
    ) -> dict[str, pd.DataFrame]:
        if not isinstance(inputs, ProductionKernelInput):
            raise TypeError("inputs must be ProductionKernelInput")
        inputs.require_frames(STAGE2_REQUIRED_FRAMES)
        if not isinstance(stage1_tables, Mapping):
            raise TypeError("stage1_tables must be a mapping of pandas DataFrame values")
        for name, frame in stage1_tables.items():
            if not isinstance(name, str) or not isinstance(frame, pd.DataFrame):
                raise TypeError("stage1_tables must map string keys to pandas DataFrame values")
            _copy_frame(frame)
        return {}
