from __future__ import annotations

from collections.abc import Mapping

import pandas as pd

from .contracts import (
    STAGE1_REQUIRED_FRAMES,
    STAGE2_REQUIRED_FRAMES,
    ProductionKernelInput,
    _copy_frame,
)
from .position_context import (
    build_credit_risk_context,
    normalize_bond_position,
    normalize_credit_position,
    normalize_regulatory_position,
)


class ProductionRiskKernel:
    """Pure orchestration shell populated incrementally by extraction tasks."""

    def run_stage1(self, inputs: ProductionKernelInput) -> dict[str, pd.DataFrame]:
        if not isinstance(inputs, ProductionKernelInput):
            raise TypeError("inputs must be ProductionKernelInput")
        frames = inputs.require_frames(STAGE1_REQUIRED_FRAMES)
        bond_position = normalize_bond_position(frames["债券持仓明细表"])
        credit_position = normalize_credit_position(frames["债券持仓明细表_信用债"])
        regulatory_position = normalize_regulatory_position(
            frames["债券持仓明细表_全量债券监管集中度"]
        )
        context_frames = dict(frames)
        context_frames["债券持仓明细表_信用债"] = credit_position
        credit_context = build_credit_risk_context(context_frames)
        return {
            "债券持仓明细表": bond_position,
            "债券持仓明细表_信用债": credit_position,
            "债券持仓明细表_全量债券监管集中度": regulatory_position,
            "债券持仓明细表_信用债_合并风险限额相关": credit_context,
        }

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
