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
        "地域集中度限额(含城投)": [
            "日期", "指标名称", "指标值_地域集中度限额", "指标值_城投集中度限额"
        ],
        "ISIN码映射": ["资产代码", "ISIN码"],
        "债券持仓表_核算系统": [
            "日期", "账户", "简称", "代码", "持仓面额(元)", "全价成本(元)"
        ],
        "穿透高收益_投资本金规模": [
            "日期", "账户", "简称", "代码", "持仓面额(元)", "全价成本(元)"
        ],
        "公司净资产_手工_每日": ["日期", "公司净资产(万)"],
        "高收益限额": ["指标", "限额(万)"],
        "特定主体限额": ["日期", "主体wind代码", "指标名称", "指标值"],
        "特定实控人限额": ["日期", "实控人名称", "指标名称", "指标值"],
        "单一债券集中度限额": ["日期", "指标名称", "指标值"],
        "单一债券规模限额": ["日期", "指标名称", "指标值"],
        "特批单一债券限额": [
            "日期", "主证券代码", "主证券代码_标准", "规模指标值", "集中度指标值"
        ],
        "单一主体规模限额": ["日期", "指标名称", "指标值"],
        "单一实控人规模限额": ["日期", "指标名称", "指标值"],
        "单一担保公司规模限额": [
            "日期", "指标名称", "是否准入", "指标值", "统一社会信用代码", "授信担保公司名称"
        ],
    }
    frames = {name: pd.DataFrame(columns=schemas.get(name, ["日期", "值"])) for name in names}
    if "特定实控人限额" in frames:
        # Empty merged production context materializes the controller fallback as float64.
        frames["特定实控人限额"]["实控人名称"] = pd.Series(dtype="float64")
    if "单一担保公司规模限额" in frames:
        frames["单一担保公司规模限额"]["是否准入"] = pd.Series(dtype="float64")
    for name in (
        "单一债券集中度限额",
        "单一债券规模限额",
        "单一主体规模限额",
        "单一实控人规模限额",
    ):
        if name in frames:
            frames[name]["指标名称"] = pd.Series(dtype="float64")
    for name in ("高风险行业", "高风险省份"):
        if name in frames:
            frames[name]["指标值"] = pd.Series(dtype="float64")
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
        "风控部债券池",
        "风控部主体池",
        "调整实控人名单",
        "发行人类型调整表",
        "穿透高收益债券",
        "债券持仓明细表",
        "债券持仓明细表_信用债",
        "债券持仓明细表_全量债券监管集中度",
        "中债隐含评级AAA&AAA+",
        "单一债券规模限额",
        "单一债券集中度限额",
        "特批单一债券限额",
        "单一主体规模限额",
        "单一实控人规模限额",
        "特定主体限额",
        "特定实控人限额",
        "单一担保公司规模限额",
        "债券持仓明细表_信用债_合并风险限额相关",
        "单一债券总持仓",
        "单一主体总持仓",
        "特定主体总持仓",
        "单一实控人总持仓",
        "特定实控人总持仓",
        "限额明细_特定主体",
        "限额明细_特定实控人",
        "单一担保人总持仓",
        "单一担保人总持仓_不剔除",
        "限额明细_债券持仓明细表_信用债1_2",
        "限额明细_单一债券",
        "限额明细_单一主体",
        "限额明细_单一实控人",
        "限额明细_单一实控人_取最高额度",
        "限额明细_单一担保人",
        "限额明细_债券持仓明细表_信用债1_1",
        "限额明细_全量债券监管集中度",
    ]
    for name in first:
        pdt.assert_frame_equal(first[name], second[name], check_exact=True)
    for name, frame in frames.items():
        pdt.assert_frame_equal(frame, before[name], check_exact=True)


def test_stage2_shell_validates_frames_and_does_not_mutate_stage1_tables(business_date):
    frames = _frames(tuple(dict.fromkeys(STAGE1_REQUIRED_FRAMES + STAGE2_REQUIRED_FRAMES)))
    frames["高收益限额"] = pd.DataFrame(
        [
            {"指标": "年度高收益债券投资本金规模", "限额(万)": 100.0},
            {"指标": "单一债券票面规模", "限额(万)": 100.0},
            {"指标": "单一主体票面规模", "限额(万)": 200.0},
        ]
    )
    inputs = ProductionKernelInput(
        business_date=business_date,
        frames=frames,
        parameters=ProductionKernelParameters(0.16),
    )
    credit = frames["债券持仓明细表_信用债"].copy()
    credit["_源行号"] = pd.Series(dtype="int64")
    merged = credit.copy()
    merged["行业类别"] = pd.Series(dtype="object")
    merged["省份类别"] = pd.Series(dtype="object")
    stage1_tables = {
        "债券持仓明细表_信用债": credit,
        "债券持仓明细表_信用债_合并风险限额相关": merged,
        "阶段1结果": pd.DataFrame({"值": [1], "对象": [["a"]]}),
    }
    before = stage1_tables["阶段1结果"].copy(deep=True)

    kernel = ProductionRiskKernel()
    first = kernel.run_stage2(inputs, stage1_tables)
    second = kernel.run_stage2(inputs, stage1_tables)
    assert list(first) == [
        "高风险行业",
        "高风险省份",
        "高风险限额",
        "地域集中度限额(含城投)",
        "金融工具池设置",
        "债券持仓明细表_信用债",
        "债券持仓明细表_信用债_合并风险限额相关",
        "信用债总持仓",
        "单一地域总持仓",
        "单一地域城投总持仓",
        "高风险行业总持仓",
        "高风险行业总持仓_2",
        "高风险省份总持仓",
        "高风险省份总持仓_2",
        "限额明细_债券持仓明细表_信用债2",
        "限额明细_高风险行业",
        "限额明细_高风险行业_2",
        "限额明细_高风险省份",
        "限额明细_高风险省份2",
        "限额明细_地域集中度限额(含城投)",
        "限额明细_高收益",
        "限额明细_高收益_投资本金规模",
    ]
    for name in first:
        pdt.assert_frame_equal(first[name], second[name], check_exact=True)
    pdt.assert_frame_equal(stage1_tables["阶段1结果"], before, check_exact=True)

    colliding_stage1_tables = dict(stage1_tables)
    colliding_stage1_tables["高收益限额"] = pd.DataFrame({"恶意覆盖": [1]})
    collision_result = kernel.run_stage2(inputs, colliding_stage1_tables)
    for name in first:
        pdt.assert_frame_equal(first[name], collision_result[name], check_exact=True)

    missing_handoff = dict(stage1_tables)
    missing_handoff.pop("债券持仓明细表_信用债_合并风险限额相关")
    with pytest.raises(
        MissingKernelFramesError,
        match="债券持仓明细表_信用债_合并风险限额相关",
    ):
        kernel.run_stage2(inputs, missing_handoff)

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
