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
    schemas = {
        "债券持仓明细表": [
            "日期", "金融资产会计属性", "部门", "内部证券账户名称", "资产代码", "资产名称",
            "库存数量(万)", "库存数量(万)_空头为负", "债券分类2", "主证券代码", "主证券名称",
            "库存数量(万)_PR", "债券余额(亿)", "债务主体wind代码", "担保人wind代码",
        ],
        "债券持仓明细表_信用债": [
            "日期", "金融资产会计属性", "部门", "内部证券账户名称", "资产代码", "ISIN码",
            "资产名称", "债券分类2", "债券类型1", "主证券代码", "主证券名称", "库存数量(万)_PR",
            "债券余额(亿)", "发行人类型", "债务主体", "债务主体wind代码", "实际控制人名称",
            "实际控制人名称_修正", "担保人", "担保人wind代码", "是否城投债", "债券类别",
            "wind行业", "省份", "合并辅助列",
        ],
        "债券持仓明细表_全量债券监管集中度": [
            "日期", "金融资产会计属性", "部门", "内部证券账户名称", "资产代码", "ISIN码",
            "资产名称", "债券分类2", "债券类型1", "主证券代码", "主证券名称", "库存数量(万)_PR",
            "债券余额(亿)", "发行人类型", "债务主体", "债务主体wind代码", "实际控制人名称",
            "实际控制人名称_修正", "担保人", "担保人wind代码", "是否城投债", "债券类别",
            "wind行业", "省份",
        ],
        "穿透高收益债券": ["债券代码", "类型"],
        "金融工具池设置": ["代码", "简称"],
        "中债隐含评级AAA&AAA+": ["wind代码", "日期", "中债隐含评级"],
        "风控部债券池": ["代码", "日期", "债券池", "主体池"],
        "风控部主体池": ["日期", "发行人名称", "主体wind代码", "主体池"],
        "发行人类型调整表": ["wind代码", "发行人类型"],
        "调整实控人名单": ["主体wind代码", "调整后实际控制人"],
        "高风险行业": ["日期", "行业名称", "行业类别"],
        "高风险省份": ["日期", "省份名称", "省份类别"],
        "单一担保公司规模限额": ["日期", "指标名称", "是否准入"],
    }
    frames = {name: pd.DataFrame(columns=schemas.get(name, ["日期", "值"])) for name in names}
    for frame in frames.values():
        if "日期" in frame.columns:
            frame["日期"] = pd.to_datetime(frame["日期"])
    return frames


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
    before = {name: frame.copy(deep=True) for name, frame in frames.items()}
    inputs = ProductionKernelInput(
        business_date=business_date,
        frames=frames,
        parameters=ProductionKernelParameters(0.16),
    )
    kernel = ProductionRiskKernel()

    first = kernel.run_stage1(inputs)
    second = kernel.run_stage1(inputs)
    assert list(first) == [
        "债券持仓明细表",
        "债券持仓明细表_信用债",
        "债券持仓明细表_全量债券监管集中度",
        "债券持仓明细表_信用债_合并风险限额相关",
    ]
    for name in first:
        pdt.assert_frame_equal(first[name], second[name], check_exact=True)
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
