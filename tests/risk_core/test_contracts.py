from __future__ import annotations

from math import inf, nan

import pandas as pd
import pytest

from src.risk_core.contracts import (
    MissingKernelFramesError,
    ProductionKernelInput,
    ProductionKernelParameters,
    ProductionKernelResult,
)


@pytest.mark.parametrize(
    "value",
    [
        pd.NaT,
        "2026-05-20",
        pd.Timestamp("2026-05-20 12:00:00"),
        pd.Timestamp("2026-05-20", tz="Asia/Shanghai"),
    ],
)
def test_kernel_input_rejects_invalid_business_date(value):
    with pytest.raises((TypeError, ValueError), match="business_date"):
        ProductionKernelInput(
            business_date=value,
            frames={},
            parameters=ProductionKernelParameters(0.16),
        )


@pytest.mark.parametrize("value", [nan, inf, -inf])
def test_kernel_parameters_reject_non_finite_regulatory_limit(value):
    with pytest.raises(ValueError, match="finite"):
        ProductionKernelParameters(regulatory_concentration_limit=value)


def test_kernel_parameters_preserve_explicit_zero():
    parameters = ProductionKernelParameters(regulatory_concentration_limit=0.0)
    assert parameters.regulatory_concentration_limit == 0.0


def test_missing_frame_and_legal_empty_frame_are_distinct(business_date):
    inputs = ProductionKernelInput(
        business_date=business_date,
        frames={"合法空表": pd.DataFrame(columns=["日期", "指标值"])},
        parameters=ProductionKernelParameters(0.16),
    )

    present = inputs.require_frames(("合法空表",))
    assert present["合法空表"].empty
    assert present["合法空表"].columns.tolist() == ["日期", "指标值"]

    with pytest.raises(MissingKernelFramesError, match="缺失表"):
        inputs.require_frames(("合法空表", "缺失表"))


def test_input_frames_are_deeply_detached_and_mapping_is_read_only(business_date):
    source = pd.DataFrame({"值": [1], "对象": [["a"]]})
    inputs = ProductionKernelInput(
        business_date=business_date,
        frames={"输入": source},
        parameters=ProductionKernelParameters(0.16),
    )

    source.loc[0, "值"] = 99
    source.loc[0, "对象"].append("caller")
    first = inputs.detached_frames()
    assert first["输入"].loc[0, "值"] == 1
    assert first["输入"].loc[0, "对象"] == ["a"]

    first["输入"].loc[0, "值"] = 88
    first["输入"].loc[0, "对象"].append("detached")
    second = inputs.detached_frames()
    assert second["输入"].loc[0, "值"] == 1
    assert second["输入"].loc[0, "对象"] == ["a"]
    with pytest.raises(TypeError):
        inputs.frames["新增"] = pd.DataFrame()


def test_result_tables_are_deeply_detached_and_mapping_is_read_only():
    stage1 = pd.DataFrame({"值": [1], "对象": [["a"]]})
    stage2 = pd.DataFrame({"值": [2]})
    result = ProductionKernelResult(
        stage1_tables={"阶段1": stage1},
        stage2_tables={"阶段2": stage2},
    )

    stage1.loc[0, "值"] = 9
    stage1.loc[0, "对象"].append("caller")
    detached = result.detached_stage1_tables()
    assert detached["阶段1"].loc[0, "值"] == 1
    assert detached["阶段1"].loc[0, "对象"] == ["a"]
    with pytest.raises(TypeError):
        result.stage1_tables["新增"] = pd.DataFrame()


def test_contract_rejects_non_dataframe_frame(business_date):
    with pytest.raises(TypeError, match="DataFrame"):
        ProductionKernelInput(
            business_date=business_date,
            frames={"错误": []},
            parameters=ProductionKernelParameters(0.16),
        )
