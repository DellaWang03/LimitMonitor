from __future__ import annotations

import pandas as pd
import pandas.testing as pdt

import src.stage1.stage1_processor as stage1_processor_module
from src.risk_core.stage1_limits import Stage1LimitEngine
from src.stage1.stage1_limit_detail import LimitDetailCalculator


PRODUCTION_LIMIT_METHODS = {
    "calculate_limit_detail_1_2",
    "calculate_limit_detail_single_bond",
    "calculate_limit_detail_single_issuer",
    "calculate_limit_detail_full_regulatory_concentration",
    "calculate_limit_detail_specific_issuer",
    "calculate_limit_detail_specific_controller",
    "calculate_limit_detail_single_controller",
    "calculate_limit_detail_single_controller_max",
    "calculate_limit_detail_single_guarantee",
    "calculate_limit_detail_1_1",
}


def test_stage1_limit_public_surface_is_frozen():
    assert PRODUCTION_LIMIT_METHODS <= set(dir(LimitDetailCalculator))
    assert PRODUCTION_LIMIT_METHODS <= set(dir(Stage1LimitEngine))


def test_stage1_adapter_resolves_regulatory_parameter_before_building_engine(
    stage1_processor, monkeypatch
):
    constructor_values: list[tuple[float | None, object]] = []
    stage_config = object()
    stage1_processor.config = stage_config

    class FakeCalculator:
        def __init__(
            self,
            cache,
            regulatory_concentration_limit=None,
            config=None,
        ):
            constructor_values.append((regulatory_concentration_limit, config))

        def _load_regulatory_concentration_limit(self):
            return 0.16

    monkeypatch.setattr(
        stage1_processor_module, "LimitDetailCalculator", FakeCalculator
    )

    calculator = stage1_processor._build_limit_calculator()

    assert isinstance(calculator, FakeCalculator)
    assert constructor_values == [
        (None, stage_config),
        (0.16, stage_config),
    ]
    assert stage1_processor._runtime_regulatory_concentration_limit == 0.16


def _one_row_1_2_cache(row: dict, business_date: pd.Timestamp, position: float) -> dict:
    merged = pd.DataFrame(
        [
            {
                **row,
                "是否属于高收益": "否",
                "发行人类型_调整": "国企",
                "债券池": None,
                "主体池": None,
                "中债隐含评级": None,
                "担保公司是否准入": None,
            }
        ]
    )
    return {
        "债券持仓明细表_信用债_合并风险限额相关": merged,
        "单一债券规模限额": pd.DataFrame(
            [{"日期": business_date, "指标名称": "国企/", "指标值": 15000.0}]
        ),
        "单一债券集中度限额": pd.DataFrame(
            [{"日期": business_date, "指标名称": "国企/", "指标值": 0.16}]
        ),
        "特批单一债券限额": pd.DataFrame(
            [
                {
                    "日期": business_date,
                    "主证券代码": row["主证券代码"],
                    "规模指标值": 20000.0,
                    "集中度指标值": 0.01,
                }
            ]
        ),
        "单一主体规模限额": pd.DataFrame(
            [{"日期": business_date, "指标名称": "国企", "指标值": 30000.0}]
        ),
        "单一债券总持仓": pd.DataFrame(
            [
                {
                    "日期": business_date,
                    "业务分类": "自营业务",
                    "单一债券归并键": f"主证券代码_标准::{row['主证券代码']}",
                    "单一债券总持仓_PR": position,
                    "单一债券集中度": position / row["债券余额(亿)"] * 0.0001,
                }
            ]
        ),
        "单一主体总持仓": pd.DataFrame(
            [
                {
                    "日期": business_date,
                    "业务分类": "自营业务",
                    "债务主体": row["债务主体"],
                    "单一主体总持仓_PR": position,
                }
            ]
        ),
        "限额明细_单一实控人_取最高额度": pd.DataFrame(
            [
                {
                    "日期": business_date,
                    "业务分类": "自营业务",
                    "实际控制人名称_修正": row["实际控制人名称_修正"],
                    "单一实控人限额适用类别": "国企",
                    "单一实控人规模限额指标值": 40000.0,
                    "单一实控人总持仓_PR": position,
                    "单一实控人规模剩余额度(万)": 40000.0 - position,
                    "单一实控人是否超限": "否",
                }
            ]
        ),
    }


def test_1_2_freezes_special_scale_only_and_strict_zero_negative_boundary(
    credit_row, business_date
):
    base_row = credit_row(**{"库存数量(万)_PR": 20000.0, "债券余额(亿)": 20.0})
    zero = LimitDetailCalculator(
        _one_row_1_2_cache(base_row, business_date, 20000.0),
        regulatory_concentration_limit=0.16,
    ).calculate_limit_detail_1_2().iloc[0]

    assert zero["单一债券规模限额指标值"] == 20000.0
    assert zero["单一债券规模剩余额度(万)"] == 0.0
    assert zero["单一债券是否超限"] == "否"
    # The configured special concentration value 0.01 is intentionally inactive.
    assert zero["单一债券集中度限额指标值"] == 0.16

    negative_position = 20000.0000001
    negative_row = credit_row(
        **{"库存数量(万)_PR": negative_position, "债券余额(亿)": 20.0}
    )
    negative = LimitDetailCalculator(
        _one_row_1_2_cache(negative_row, business_date, negative_position),
        regulatory_concentration_limit=0.16,
    ).calculate_limit_detail_1_2().iloc[0]
    assert negative["单一债券规模剩余额度(万)"] < 0
    assert negative["单一债券是否超限"] == "是"


def test_shared_limit_engine_matches_adapter_and_detaches_input_cache(
    credit_row, business_date
):
    row = credit_row(**{"库存数量(万)_PR": 100.0, "债券余额(亿)": 20.0})
    cache = _one_row_1_2_cache(row, business_date, 100.0)
    before = {name: frame.copy(deep=True) for name, frame in cache.items()}

    engine = Stage1LimitEngine(cache, regulatory_concentration_limit=0.16)
    adapter = LimitDetailCalculator(cache, regulatory_concentration_limit=0.16)
    pdt.assert_frame_equal(
        engine.calculate_limit_detail_1_2(),
        adapter.calculate_limit_detail_1_2(),
        check_exact=True,
    )

    for name, frame in cache.items():
        pdt.assert_frame_equal(frame, before[name], check_exact=True)
        frame.drop(index=frame.index, inplace=True)

    pdt.assert_frame_equal(
        engine.calculate_limit_detail_1_2(),
        LimitDetailCalculator(before, regulatory_concentration_limit=0.16)
        .calculate_limit_detail_1_2(),
        check_exact=True,
    )


def test_1_2_excludes_general_special_issuer_but_keeps_exact_xixian_exception(
    credit_row, business_date
):
    row = credit_row(**{"库存数量(万)_PR": 100.0, "债券余额(亿)": 20.0})

    general_cache = _one_row_1_2_cache(row, business_date, 100.0)
    general_cache["限额明细_特定主体"] = pd.DataFrame(
        [
            {
                "日期": business_date,
                "业务分类": "自营业务",
                "资产代码": row["资产代码"],
                "指标名称": "普通主体特批",
                "特定主体限额指标值": 25000.0,
            }
        ]
    )
    assert LimitDetailCalculator(
        general_cache, regulatory_concentration_limit=0.16
    ).calculate_limit_detail_1_2().empty

    xixian_cache = _one_row_1_2_cache(row, business_date, 100.0)
    xixian_cache["限额明细_特定主体"] = pd.DataFrame(
        [
            {
                "日期": business_date,
                "业务分类": "自营业务",
                "资产代码": row["资产代码"],
                "指标名称": "陕西西咸新区发展集团有限公司",
                "特定主体限额指标值": 25000.0,
            }
        ]
    )
    xixian = LimitDetailCalculator(
        xixian_cache, regulatory_concentration_limit=0.16
    ).calculate_limit_detail_1_2().iloc[0]
    assert xixian["单一主体限额适用类别"] == "陕西西咸新区发展集团有限公司"
    assert xixian["单一主体规模限额指标值"] == 25000.0


def test_single_bond_and_single_issuer_views_bind_to_1_2_and_keep_zero_non_exceeded(
    credit_row, business_date
):
    row = credit_row(**{"库存数量(万)_PR": 100.0})
    limit_detail = pd.DataFrame(
        [
            {
                "日期": business_date,
                "主证券代码": row["主证券代码"],
                "主证券代码_标准": row["主证券代码"],
                "债务主体wind代码": row["债务主体wind代码"],
                "单一债券规模限额适用类别": "国企/",
                "单一债券规模限额指标值": 100.0,
                "单一债券规模剩余额度(万)": 0.0,
                "单一债券是否超限": "否",
                "单一债券集中度限额适用类别": "国企/",
                "单一债券集中度限额指标值": 0.16,
                "单一债券集中度剩余额度(万)": 15900.0,
                "单一债券集中度是否超限": "否",
                "单一主体是否超限": "否",
                "单一主体限额适用类别": "国企",
                "单一主体规模限额指标值": 100.0,
                "单一主体规模剩余额度(万)": 0.0,
            }
        ]
    )
    calculator = LimitDetailCalculator(
        {
            "债券持仓明细表": pd.DataFrame([row]),
            "债券持仓明细表_信用债": pd.DataFrame([row]),
            "债券持仓明细表_信用债_合并风险限额相关": pd.DataFrame(
                [{**row, "是否属于高收益": "否"}]
            ),
            "限额明细_债券持仓明细表_信用债1_2": limit_detail,
        },
        regulatory_concentration_limit=0.16,
    )

    bond = calculator.calculate_limit_detail_single_bond().iloc[0]
    issuer = calculator.calculate_limit_detail_single_issuer().iloc[0]
    assert bond["证券代码"] == row["主证券代码"]
    assert bond["单一债券规模剩余额度(万)"] == 0.0
    assert bond["单一债券是否超限"] == "否"
    assert issuer["单一主体总持仓_PR"] == 100.0
    assert issuer["单一主体规模剩余额度(万)"] == 0.0


def test_full_regulatory_freezes_missing_reason_and_exact_boundary(
    credit_row, business_date
):
    rows = pd.DataFrame(
        [
            credit_row(
                资产代码="ZERO.IB",
                主证券代码="ZERO.IB",
                ISIN码="CNZERO",
                **{"库存数量(万)_PR": 1600.0, "债券余额(亿)": 1.0},
            ),
            credit_row(
                资产代码="NEG.IB",
                主证券代码="NEG.IB",
                ISIN码="CNNEG",
                **{"库存数量(万)_PR": 1600.0000001, "债券余额(亿)": 1.0},
            ),
            credit_row(
                资产代码="MISSING.IB",
                主证券代码=None,
                ISIN码=None,
                **{"库存数量(万)_PR": 10.0, "债券余额(亿)": None},
            ),
        ]
    )
    result = LimitDetailCalculator(
        {"债券持仓明细表_全量债券监管集中度": rows},
        regulatory_concentration_limit=0.16,
    ).calculate_limit_detail_full_regulatory_concentration()
    by_asset = result.set_index("资产代码")

    assert by_asset.loc["ZERO.IB", "监管集中度剩余额度(万)"] == 0.0
    assert by_asset.loc["ZERO.IB", "监管集中度是否超限"] == "否"
    assert by_asset.loc["NEG.IB", "监管集中度剩余额度(万)"] < 0
    assert by_asset.loc["NEG.IB", "监管集中度是否超限"] == "是"
    assert by_asset.loc["MISSING.IB", "是否可计算"] == "否"
    assert by_asset.loc["MISSING.IB", "不可计算原因"] == "缺归并主键、缺债券余额"


def test_specific_issuer_keeps_multiple_constraints_and_zero_is_not_exceeded(
    credit_row, business_date
):
    row = credit_row(**{"库存数量(万)_PR": 100.0})
    result = LimitDetailCalculator(
        {
            "债券持仓明细表_信用债_合并风险限额相关": pd.DataFrame(
                [{**row, "是否属于高收益": "否"}]
            ),
            "特定主体限额": pd.DataFrame(
                [
                    {
                        "日期": business_date,
                        "主体wind代码": row["债务主体wind代码"],
                        "指标名称": "约束A",
                        "指标值": 100.0,
                    },
                    {
                        "日期": business_date,
                        "主体wind代码": row["债务主体wind代码"],
                        "指标名称": "约束B",
                        "指标值": 99.0,
                    },
                ]
            ),
            "特定主体总持仓": pd.DataFrame(
                [
                    {
                        "日期": business_date,
                        "业务分类": "自营业务",
                        "特定主体名称": "约束A",
                        "特定主体总持仓": 100.0,
                    },
                    {
                        "日期": business_date,
                        "业务分类": "自营业务",
                        "特定主体名称": "约束B",
                        "特定主体总持仓": 100.0,
                    },
                ]
            ),
        },
        regulatory_concentration_limit=0.16,
    ).calculate_limit_detail_specific_issuer()
    status = result.set_index("指标名称")["特定主体限额是否超限"].to_dict()
    remaining = result.set_index("指标名称")["特定主体限额剩余额度"].to_dict()
    assert status == {"约束A": "否", "约束B": "是"}
    assert remaining == {"约束A": 0.0, "约束B": -1.0}


def test_specific_controller_keeps_attention_pool_while_specific_issuer_drops_it(
    credit_row, business_date
):
    row = credit_row(内部证券账户名称="关注池账户", **{"库存数量(万)_PR": 100.0})
    base = {
        "债券持仓明细表_信用债_合并风险限额相关": pd.DataFrame(
            [{**row, "是否属于高收益": "否"}]
        ),
        "特定主体限额": pd.DataFrame(
            [
                {
                    "日期": business_date,
                    "主体wind代码": row["债务主体wind代码"],
                    "指标名称": "主体特批",
                    "指标值": 100.0,
                }
            ]
        ),
        "特定实控人限额": pd.DataFrame(
            [
                {
                    "日期": business_date,
                    "实控人名称": row["实际控制人名称_修正"],
                    "指标名称": "实控人特批",
                    "指标值": 100.0,
                }
            ]
        ),
        "特定实控人总持仓": pd.DataFrame(
            [
                {
                    "日期": business_date,
                    "业务分类": "自营业务",
                    "特定实控人名称": row["实际控制人名称_修正"],
                    "特定实控人总持仓": 100.0,
                }
            ]
        ),
    }
    calculator = LimitDetailCalculator(base, regulatory_concentration_limit=0.16)
    assert calculator.calculate_limit_detail_specific_issuer().empty
    controller = calculator.calculate_limit_detail_specific_controller().iloc[0]
    assert controller["特定实控人限额剩余额度"] == 0.0
    assert controller["特定实控人限额是否超限"] == "否"


def test_controller_highest_rule_and_single_controller_view(
    credit_row, business_date
):
    rows = pd.DataFrame(
        [
            credit_row(
                资产代码="LOW.IB",
                发行人类型_调整="国企",
                **{"库存数量(万)_PR": 50.0},
            ),
            credit_row(
                资产代码="HIGH.IB",
                发行人类型_调整="非国企",
                **{"库存数量(万)_PR": 100.0},
            ),
        ]
    )
    rows["是否属于高收益"] = "否"
    rows["主体池"] = "核心池"
    rows["中债隐含评级"] = None
    rows["担保公司是否准入"] = None
    cache = {
        "债券持仓明细表_信用债_合并风险限额相关": rows,
        "单一实控人规模限额": pd.DataFrame(
            [
                {"日期": business_date, "指标名称": "国企/核心池", "指标值": 100.0},
                {"日期": business_date, "指标名称": "非国企/核心池", "指标值": 200.0},
            ]
        ),
        "特定实控人限额": pd.DataFrame(
            columns=["日期", "实控人名称", "指标名称", "指标值"]
        ),
        "单一实控人总持仓": pd.DataFrame(
            [
                {
                    "日期": business_date,
                    "业务分类": "自营业务",
                    "实际控制人名称_修正": "修正实控人",
                    "单一实控人总持仓_PR": 150.0,
                }
            ]
        ),
    }
    calculator = LimitDetailCalculator(cache, regulatory_concentration_limit=0.16)
    highest = calculator.calculate_limit_detail_single_controller_max()
    assert highest["单一实控人规模限额指标值"].tolist() == [200.0]
    assert highest["单一实控人规模剩余额度(万)"].tolist() == [50.0]

    cache["限额明细_债券持仓明细表_信用债1_2"] = highest.rename(
        columns={"单一实控人限额适用类别": "单一主体/实控人限额适用类别"}
    )
    single = calculator.calculate_limit_detail_single_controller()
    assert single["单一实控人总持仓_PR"].tolist() == [150.0]
    assert single["单一实控人规模限额指标值"].tolist() == [200.0]


def test_guarantee_detail_uses_persisted_total_and_three_key_limit(
    business_date
):
    result = LimitDetailCalculator(
        {
            "限额明细_债券持仓明细表_信用债1_2": pd.DataFrame(
                [
                    {
                        "日期": business_date,
                        "业务分类": "自营业务",
                        "担保人wind代码": "G1",
                        "担保人": "担保公司A",
                        "单一主体限额适用类别": "担保准入",
                        "单一担保公司规模限额": 100.0,
                        "单一担保人总持仓_PR": 100.0,
                        "单一担保公司规模剩余额度(万)": 0.0,
                    }
                ]
            ),
            "单一担保公司规模限额": pd.DataFrame(
                [
                    {
                        "日期": business_date,
                        "指标名称": "G1",
                        "授信担保公司名称": "担保公司A",
                        "指标值": 100.0,
                    }
                ]
            ),
        },
        regulatory_concentration_limit=0.16,
    ).calculate_limit_detail_single_guarantee().iloc[0]
    assert result["单一担保公司规模剩余额度(万)"] == 0.0
    assert result["单一担保人是否超限"] == "否"


def test_1_1_keeps_special_limit_rows_and_combines_duplicate_positions(
    credit_row, business_date
):
    rows = pd.DataFrame(
        [
            credit_row(**{"库存数量(万)_PR": 40.0}),
            credit_row(**{"库存数量(万)_PR": 60.0}),
        ]
    )
    rows["是否属于高收益"] = "是"
    specific = pd.DataFrame(
        [
            {
                "日期": business_date,
                "业务分类": "自营业务",
                "资产代码": "123456.IB",
                "指标名称": "普通主体特批",
                "特定主体限额指标值": 100.0,
                "特定主体总持仓": 100.0,
                "特定主体限额剩余额度": 0.0,
                "特定主体限额是否超限": "否",
            }
        ]
    )
    result = LimitDetailCalculator(
        {
            "债券持仓明细表_信用债_合并风险限额相关": rows,
            "限额明细_特定主体": specific,
            "限额明细_特定实控人": pd.DataFrame(
                [
                    {
                        "日期": business_date,
                        "业务分类": "自营业务",
                        "资产代码": "OTHER.IB",
                        "指标名称": "其他实控人特批",
                        "特定实控人限额指标值": 999.0,
                        "特定实控人总持仓": 1.0,
                        "特定实控人限额剩余额度": 998.0,
                        "特定实控人限额是否超限": "否",
                    }
                ]
            ),
        },
        regulatory_concentration_limit=0.16,
    ).calculate_limit_detail_1_1()
    assert result["库存数量(万)_PR"].tolist() == [100.0]
    assert result["特定主体限额名称"].tolist() == ["普通主体特批"]
    assert result["是否超限"].tolist() == ["否"]
