from __future__ import annotations

import pandas as pd
import pandas.testing as pdt

from src.risk_core.stage1_aggregates import (
    calculate_single_bond_total_position,
    calculate_single_controller_total_position,
    calculate_single_guarantee_total_position,
    calculate_single_guarantee_total_position_unfiltered,
    calculate_single_issuer_total_position,
    calculate_specific_controller_total_position,
    calculate_specific_issuer_total_position,
    filter_non_high_yield_credit_rows,
)
from src.stage1.stage1_processor import Stage1Processor


PRODUCTION_AGGREGATE_METHODS = {
    "query_single_bond_total_position",
    "query_single_issuer_total_position",
    "query_specific_issuer_total_position",
    "query_single_controller_total_position",
    "query_specific_controller_total_position",
    "query_single_guarantee_total_position",
    "query_single_guarantee_total_position_unfiltered",
}


def test_stage1_aggregate_public_surface_is_frozen():
    assert PRODUCTION_AGGREGATE_METHODS <= set(dir(Stage1Processor))


def test_bond_issuer_and_controller_totals_freeze_business_partition_and_denominators(
    stage1_processor, credit_row
):
    credit = pd.DataFrame(
        [
            credit_row(),
            credit_row(内部证券账户名称="做市交易部做市业务", **{"库存数量(万)_PR": 40.0}),
            credit_row(内部证券账户名称="自营部交易性2", **{"库存数量(万)_PR": 60.0}),
        ]
    )
    merged = credit.copy()
    merged["是否属于高收益"] = "否"
    stage1_processor.cache.update(
        {
            "债券持仓明细表_信用债": credit,
            "债券持仓明细表_信用债_合并风险限额相关": merged,
        }
    )

    bonds = stage1_processor.query_single_bond_total_position()
    issuers = stage1_processor.query_single_issuer_total_position()
    controllers = stage1_processor.query_single_controller_total_position()

    bond_positions = bonds.set_index("业务分类")["单一债券总持仓_PR"].to_dict()
    issuer_positions = issuers.set_index("业务分类")["单一主体总持仓_PR"].to_dict()
    controller_positions = controllers.set_index("业务分类")["单一实控人总持仓_PR"].to_dict()
    assert bond_positions == {"做市业务": 40.0, "自营业务": 160.0}
    assert issuer_positions == {"做市业务": 40.0, "自营业务": 160.0}
    assert controller_positions == {"做市业务": 40.0, "自营业务": 160.0}
    # 160 / 10亿元 * 0.0001 is the production concentration formula.
    assert bonds.loc[bonds["业务分类"] == "自营业务", "单一债券集中度"].item() == 0.0016
    pdt.assert_frame_equal(calculate_single_bond_total_position(credit), bonds, check_exact=True)
    pdt.assert_frame_equal(calculate_single_issuer_total_position(credit), issuers, check_exact=True)
    pdt.assert_frame_equal(
        calculate_single_controller_total_position(merged), controllers, check_exact=True
    )


def test_specific_totals_exclude_high_yield_and_attention_pool_asymmetrically(
    stage1_processor, credit_row, business_date
):
    rows = pd.DataFrame(
        [
            credit_row(资产代码="KEEP.IB", **{"库存数量(万)_PR": 30.0}),
            credit_row(
                资产代码="FOCUS.IB",
                内部证券账户名称="关注池账户",
                **{"库存数量(万)_PR": 40.0},
            ),
            credit_row(
                资产代码="HY.IB",
                内部证券账户名称="高收益账户",
                **{"库存数量(万)_PR": 50.0},
            ),
        ]
    )
    merged = rows.copy()
    merged["是否属于高收益"] = ["否", "否", "是"]
    stage1_processor.cache.update(
        {
            "债券持仓明细表_信用债": rows,
            "债券持仓明细表_信用债_合并风险限额相关": merged,
            "穿透高收益债券": pd.DataFrame(columns=["债券代码", "类型"]),
            "金融工具池设置": pd.DataFrame(columns=["代码", "简称"]),
            "特定主体限额": pd.DataFrame(
                [
                    {
                        "日期": business_date,
                        "主体wind代码": "F1000001.00",
                        "指标名称": "普通主体特批",
                        "指标值": 1000.0,
                    }
                ]
            ),
            "特定实控人限额": pd.DataFrame(
                [
                    {
                        "日期": business_date,
                        "实控人名称": "修正实控人",
                        "指标名称": "实控人特批",
                        "指标值": 2000.0,
                    }
                ]
            ),
        }
    )

    issuer = stage1_processor.query_specific_issuer_total_position()
    controller = stage1_processor.query_specific_controller_total_position()

    assert issuer[["特定主体名称", "特定主体总持仓"]].to_dict("records") == [
        {"特定主体名称": "普通主体特批", "特定主体总持仓": 30.0}
    ]
    assert controller[["特定实控人名称", "特定实控人总持仓"]].to_dict("records") == [
        {"特定实控人名称": "修正实控人", "特定实控人总持仓": 30.0}
    ]
    pdt.assert_frame_equal(
        filter_non_high_yield_credit_rows(
            merged,
            stage1_processor.cache["穿透高收益债券"],
            stage1_processor.cache["金融工具池设置"],
        ),
        rows.iloc[[0, 1]].assign(**{"是否属于高收益": ["否", "否"]}),
        check_exact=True,
    )
    pdt.assert_frame_equal(
        calculate_specific_issuer_total_position(
            rows,
            stage1_processor.cache["特定主体限额"],
            stage1_processor.cache["穿透高收益债券"],
            stage1_processor.cache["金融工具池设置"],
        ),
        issuer,
        check_exact=True,
    )
    pdt.assert_frame_equal(
        calculate_specific_controller_total_position(
            merged,
            stage1_processor.cache["特定实控人限额"],
            stage1_processor.cache["穿透高收益债券"],
            stage1_processor.cache["金融工具池设置"],
        ),
        controller,
        check_exact=True,
    )
    # Ordinary issuer/controller totals retain both focus-pool and high-yield rows.
    assert stage1_processor.query_single_issuer_total_position()["单一主体总持仓_PR"].item() == 120.0
    assert stage1_processor.query_single_controller_total_position()["单一实控人总持仓_PR"].item() == 120.0


def test_guarantee_total_freezes_three_key_match_and_special_attention_exclusions(
    stage1_processor, credit_row, business_date
):
    merged = pd.DataFrame(
        [
            credit_row(
                资产代码="KEEP.IB",
                担保人="担保公司A",
                担保人wind代码="G1",
                **{"库存数量(万)_PR": 70.0},
            ),
            credit_row(
                资产代码="FOCUS.IB",
                内部证券账户名称="关注池账户",
                担保人="担保公司A",
                担保人wind代码="G1",
                **{"库存数量(万)_PR": 20.0},
            ),
            credit_row(
                资产代码="SPECIAL.IB",
                担保人="担保公司A",
                担保人wind代码="G1",
                **{"库存数量(万)_PR": 30.0},
            ),
        ]
    )
    merged["是否属于高收益"] = "否"
    merged["债券池"] = "核心池"
    merged["主体池"] = "核心池"
    merged["中债隐含评级"] = None
    merged["担保公司是否准入"] = "担保准入"
    stage1_processor.cache.update(
        {
            "债券持仓明细表_信用债_合并风险限额相关": merged,
            "限额明细_特定主体": pd.DataFrame(
                [{"日期": business_date, "资产代码": "SPECIAL.IB", "指标名称": "主体特批"}]
            ),
            "限额明细_特定实控人": pd.DataFrame(columns=["日期", "资产代码", "指标名称"]),
            "单一主体规模限额": pd.DataFrame(
                [
                    {"日期": business_date, "指标名称": "国企/核心池", "指标值": 1000.0},
                    {"日期": business_date, "指标名称": "担保准入", "指标值": 2000.0},
                ]
            ),
            "单一担保公司规模限额": pd.DataFrame(
                [
                    {
                        "日期": business_date,
                        "指标名称": "G1",
                        "是否准入": "担保准入",
                        "指标值": 5000.0,
                        "统一社会信用代码": "91300000",
                        "授信担保公司名称": "担保公司A",
                    }
                ]
            ),
        }
    )

    filtered = stage1_processor.query_single_guarantee_total_position()
    unfiltered = stage1_processor.query_single_guarantee_total_position_unfiltered()

    assert filtered["单一担保人总持仓_PR"].tolist() == [70.0]
    assert unfiltered["单一担保人总持仓_PR"].tolist() == [120.0]
    pdt.assert_frame_equal(
        calculate_single_guarantee_total_position(
            merged,
            stage1_processor.cache["限额明细_特定主体"],
            stage1_processor.cache["限额明细_特定实控人"],
            stage1_processor.cache["单一主体规模限额"],
            stage1_processor.cache["单一担保公司规模限额"],
            pd.DataFrame(columns=["债券代码", "类型"]),
            pd.DataFrame(columns=["代码", "简称"]),
        ),
        filtered,
        check_exact=True,
    )
    pdt.assert_frame_equal(
        calculate_single_guarantee_total_position_unfiltered(
            stage1_processor.cache["单一担保公司规模限额"], merged
        ),
        unfiltered,
        check_exact=True,
    )


def test_specific_aggregate_missing_config_is_a_legal_empty_table(
    stage1_processor, credit_row
):
    stage1_processor.cache["债券持仓明细表_信用债"] = pd.DataFrame([credit_row()])
    assert stage1_processor.query_specific_issuer_total_position().empty
    assert calculate_specific_issuer_total_position(
        stage1_processor.cache["债券持仓明细表_信用债"],
        None,
        None,
        None,
    ).empty
