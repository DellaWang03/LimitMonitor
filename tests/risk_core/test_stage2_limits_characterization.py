from __future__ import annotations

import pandas as pd
import pandas.testing as pdt

from src.risk_core.stage2_limits import Stage2RiskEngine
from src.stage2 import stage2_processor as stage2_module
from src.stage2.stage2_processor import SOURCE_ROW_ID_COL, Stage2Processor


PRODUCTION_STAGE2_CALCULATION_METHODS = {
    "query_total_credit_position",
    "query_single_region_total_position",
    "query_single_region_citybond_position",
    "query_high_risk_industry_position",
    "query_high_risk_industry_position_detail",
    "query_high_risk_province_position",
    "query_high_risk_province_position_detail",
    "query_credit_bond_detail_2",
    "query_high_risk_industry_detail",
    "query_high_risk_industry_detail_2",
    "query_high_risk_province_detail",
    "query_high_risk_province_detail_2",
    "query_region_concentration_detail",
    "query_high_yield_detail",
    "query_high_yield_capital",
}


def test_stage2_calculation_public_surface_is_frozen():
    assert PRODUCTION_STAGE2_CALCULATION_METHODS <= set(dir(Stage2Processor))
    assert PRODUCTION_STAGE2_CALCULATION_METHODS <= set(dir(Stage2RiskEngine))


def test_stage2_engine_matches_adapter_for_explicit_frame_inputs(
    monkeypatch, stage2_processor, credit_row, business_date
):
    credit = pd.DataFrame(
        [
            credit_row(
                资产代码="CITY.IB",
                省份="山西省",
                wind行业="煤炭",
                债券类别="城投债",
                是否城投债="是",
                **{"库存数量(万)_PR": 120.0},
            ),
            credit_row(
                资产代码="NORMAL.IB",
                省份="浙江省",
                wind行业="制造业",
                债券类别="产业债",
                是否城投债="否",
                **{"库存数量(万)_PR": 80.0},
            ),
        ]
    )
    merged = credit.copy()
    merged["行业类别"] = ["高风险行业", pd.NA]
    merged["省份类别"] = ["高风险省份", pd.NA]
    net_asset = pd.DataFrame([{"日期": business_date, "公司净资产(万)": 1000.0}])
    cache = {
        "债券持仓明细表_信用债": credit,
        "债券持仓明细表_信用债_合并风险限额相关": merged,
        "公司净资产_手工_每日": net_asset,
    }
    stage2_processor.cache.update(cache)
    monkeypatch.setattr(stage2_module.pd, "read_excel", lambda *a, **k: net_asset.copy())

    engine = Stage2RiskEngine(cache)
    for method_name in [
        "query_total_credit_position",
        "query_single_region_total_position",
        "query_single_region_citybond_position",
    ]:
        expected = getattr(stage2_processor, method_name)()
        actual = getattr(engine, method_name)()
        pdt.assert_frame_equal(actual, expected, check_exact=True)


def test_stage2_engine_detaches_mutable_inputs(credit_row, business_date):
    credit = pd.DataFrame([credit_row(**{"库存数量(万)_PR": 100.0})])
    engine = Stage2RiskEngine({"债券持仓明细表_信用债": credit})
    credit.loc[0, "库存数量(万)_PR"] = 999.0
    assert engine.query_total_credit_position()["信用债总持仓_PR"].tolist() == [100.0]


def test_stage2_totals_and_summary_details_freeze_denominators_and_aggregations(
    monkeypatch, stage2_processor, credit_row, business_date
):
    credit = pd.DataFrame(
        [
            credit_row(
                资产代码="CITY.IB",
                省份="山西省",
                wind行业="煤炭",
                债券类别="城投债",
                是否城投债="是",
                **{"库存数量(万)_PR": 120.0},
            ),
            credit_row(
                资产代码="NORMAL.IB",
                省份="浙江省",
                wind行业="制造业",
                债券类别="产业债",
                是否城投债="否",
                **{"库存数量(万)_PR": 80.0},
            ),
        ]
    )
    merged = credit.copy()
    merged["行业类别"] = ["高风险行业", pd.NA]
    merged["省份类别"] = ["高风险省份", pd.NA]
    stage2_processor.cache.update(
        {
            "债券持仓明细表_信用债": credit,
            "债券持仓明细表_信用债_合并风险限额相关": merged,
        }
    )
    net_asset = pd.DataFrame([{"日期": business_date, "公司净资产(万)": 1000.0}])
    monkeypatch.setattr(stage2_module.pd, "read_excel", lambda *a, **k: net_asset.copy())

    total = stage2_processor.query_total_credit_position()
    stage2_processor.cache["信用债总持仓"] = total
    region = stage2_processor.query_single_region_total_position()
    city = stage2_processor.query_single_region_citybond_position()
    industry = stage2_processor.query_high_risk_industry_position()
    industry_2 = stage2_processor.query_high_risk_industry_position_detail()
    province = stage2_processor.query_high_risk_province_position()
    province_2 = stage2_processor.query_high_risk_province_position_detail()

    assert total["信用债总持仓_PR"].tolist() == [200.0]
    assert region.set_index("省份").loc["山西省", "地域集中度"] == 120.0 / 1200.0
    assert city["城投地域集中度"].tolist() == [0.12]
    assert industry["高风险行业总持仓_PR"].tolist() == [120.0]
    assert industry["高风险行业集中度"].tolist() == [0.6]
    assert industry_2[["wind行业", "高风险行业总持仓_PR"]].to_dict("records") == [
        {"wind行业": "煤炭", "高风险行业总持仓_PR": 120.0}
    ]
    assert province["高风险省份集中度"].tolist() == [0.1]
    assert province_2[["省份", "高风险省份总持仓_PR"]].to_dict("records") == [
        {"省份": "山西省", "高风险省份总持仓_PR": 120.0}
    ]

    stage2_processor.cache.update(
        {
            "高风险行业": pd.DataFrame(
                [
                    {
                        "日期": business_date,
                        "行业名称": "煤炭",
                        "行业类别": "高风险行业",
                        "指标值": 0.6,
                    }
                ]
            ),
            "高风险行业总持仓": industry,
            "高风险行业总持仓_2": industry_2,
            "高风险省份": pd.DataFrame(
                [
                    {
                        "日期": business_date,
                        "省份名称": "山西省",
                        "省份类别": "高风险省份",
                        "指标值": 0.1,
                    }
                ]
            ),
            "高风险省份总持仓": province,
            "高风险省份总持仓_2": province_2,
            "地域集中度限额(含城投)": pd.DataFrame(
                [
                    {
                        "日期": business_date,
                        "指标名称": "山西省",
                        "指标值_地域集中度限额": 0.1,
                        "指标值_城投集中度限额": 0.12,
                    }
                ]
            ),
            "单一地域总持仓": region,
            "单一地域城投总持仓": city,
        }
    )
    assert stage2_processor.query_high_risk_industry_detail()["剩余额度"].tolist() == [0.0]
    assert stage2_processor.query_high_risk_industry_detail_2()["行业名称"].tolist() == ["煤炭"]
    assert stage2_processor.query_high_risk_province_detail()["剩余额度"].tolist() == [0.0]
    assert stage2_processor.query_high_risk_province_detail_2()["省份名称"].tolist() == ["山西省"]
    region_detail = stage2_processor.query_region_concentration_detail()
    assert region_detail["单一地域总持仓剩余额度"].tolist() == [0.0]
    assert region_detail["单一地域城投持仓剩余额度"].tolist() == [0.0]
    assert region_detail["地域集中度是否超限"].tolist() == ["否"]
    assert region_detail["城投集中度是否超限"].tolist() == ["否"]


def _credit_detail_cache(row: dict, business_date: pd.Timestamp, industry_position: float) -> dict:
    return {
        "债券持仓明细表_信用债_合并风险限额相关": pd.DataFrame(
            [
                {
                    SOURCE_ROW_ID_COL: 1,
                    "日期": business_date,
                    "资产代码": row["资产代码"],
                    "内部证券账户名称": row["内部证券账户名称"],
                    "库存数量(万)_PR": row["库存数量(万)_PR"],
                    "行业类别": "高风险行业",
                    "省份类别": "高风险省份",
                    "是否属于高收益": "否",
                }
            ]
        ),
        "高风险行业": pd.DataFrame(
            [{"日期": business_date, "行业名称": "煤炭", "指标值": 0.1}]
        ),
        "高风险省份": pd.DataFrame(
            [{"日期": business_date, "省份名称": "山西省", "指标值": 0.1}]
        ),
        "地域集中度限额(含城投)": pd.DataFrame(
            [
                {
                    "日期": business_date,
                    "指标名称": "山西省",
                    "指标值_地域集中度限额": 0.1,
                    "指标值_城投集中度限额": 0.1,
                }
            ]
        ),
        "单一地域总持仓": pd.DataFrame(
            [{"日期": business_date, "省份": "山西省", "单一地域总持仓_PR": 100.0, "地域集中度": 0.1}]
        ),
        "单一地域城投总持仓": pd.DataFrame(
            [{"日期": business_date, "省份": "山西省", "单一地域城投总持仓_PR": 100.0, "城投地域集中度": 0.1}]
        ),
        "信用债总持仓": pd.DataFrame(
            [{"日期": business_date, "信用债总持仓_PR": 1000.0}]
        ),
        "高风险行业总持仓": pd.DataFrame(
            [
                {
                    "日期": business_date,
                    "行业类别": "高风险行业",
                    "高风险行业总持仓_PR": industry_position,
                    "高风险行业集中度": industry_position / 1000.0,
                }
            ]
        ),
        "高风险省份总持仓": pd.DataFrame(
            [
                {
                    "日期": business_date,
                    "省份类别": "高风险省份",
                    "高风险省份总持仓_PR": 100.0,
                    "高风险省份集中度": 0.1,
                }
            ]
        ),
    }


def test_credit_detail_2_freezes_source_identity_formulas_and_strict_boundary(
    monkeypatch, stage2_processor, credit_row, business_date
):
    row = credit_row(
        资产代码="RISK.IB",
        主证券代码="RISK.IB",
        wind行业="煤炭",
        省份="山西省",
        债券类别="城投债",
        是否城投债="是",
        **{"库存数量(万)_PR": 100.0},
    )
    source = pd.DataFrame([{SOURCE_ROW_ID_COL: 1, **row}])
    net_asset = pd.DataFrame([{"日期": business_date, "公司净资产(万)": 1000.0}])

    def fake_read_excel(path, *args, **kwargs):
        return source.copy() if "债券持仓明细表_信用债" in str(path) else net_asset.copy()

    monkeypatch.setattr(stage2_module.pd, "read_excel", fake_read_excel)
    stage2_processor.cache.update(_credit_detail_cache(row, business_date, 100.0))
    zero = stage2_processor.query_credit_bond_detail_2().iloc[0]
    assert zero["地域集中度剩余额度(万)"] == 0.0
    assert zero["城投集中度剩余额度(万)"] == 0.0
    assert zero["高风险行业集中度剩余额度(万)"] == 0.0
    assert zero["高风险省份集中度剩余额度(万)"] == 0.0
    assert zero["是否超限"] == "否"

    stage2_processor.cache.update(_credit_detail_cache(row, business_date, 100.0001))
    negative = stage2_processor.query_credit_bond_detail_2().iloc[0]
    assert negative["高风险行业集中度剩余额度(万)"] == -0.0001
    assert negative["高风险行业是否超限"] == "是"
    assert negative["是否超限"] == "是"


def _high_yield_config() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"指标": "年度高收益债券投资本金规模", "限额(万)": 100.0},
            {"指标": "单一债券票面规模", "限额(万)": 100.0},
            {"指标": "单一主体票面规模", "限额(万)": 200.0},
        ]
    )


def test_high_yield_detail_freezes_three_paths_keep_last_and_strict_boundary(
    monkeypatch, stage2_processor, credit_row, business_date
):
    monkeypatch.setattr(stage2_module, "load_limit_config", lambda **kwargs: _high_yield_config())
    rows = pd.DataFrame(
        [
            credit_row(
                资产代码="TOOL.IB",
                主证券代码="TOOL.IB",
                资产名称="工具池债",
                主证券名称="工具池债",
                ISIN码="CNTOOL",
                债务主体="主体A",
                **{"库存数量(万)_PR": 100.0},
            ),
            credit_row(
                资产代码="ACCOUNT.IB",
                主证券代码="ACCOUNT.IB",
                内部证券账户名称="高收益账户",
                ISIN码="CNACCOUNT",
                债务主体="主体B",
                **{"库存数量(万)_PR": 10.0},
            ),
            credit_row(
                资产代码="PEN.IB",
                主证券代码="PEN.IB",
                ISIN码="CNPEN",
                债务主体="主体C",
                **{"库存数量(万)_PR": 10.0},
            ),
            credit_row(
                资产代码="ORD.IB",
                主证券代码="ORD.IB",
                ISIN码="CNORD",
                债务主体="主体D",
                **{"库存数量(万)_PR": 10.0},
            ),
        ]
    )
    stage2_processor.cache.update(
        {
            "债券持仓明细表_信用债": rows,
            "金融工具池设置": pd.DataFrame([{"代码": "TOOL", "简称": "工具池债"}]),
            "穿透高收益债券": pd.DataFrame(
                [
                    {"ISIN代码": "CNPEN", "类型": "非高收益"},
                    {"ISIN代码": "CNPEN", "类型": "高收益"},
                ]
            ),
        }
    )
    result = stage2_processor.query_high_yield_detail().set_index("资产代码")
    assert result.index.tolist() == ["TOOL.IB", "ACCOUNT.IB", "PEN.IB"]
    assert result.loc["TOOL.IB", "高收益单债剩余额度(万)"] == 0.0
    assert result.loc["TOOL.IB", "高收益单债是否超限"] == "否"

    stage2_processor.cache["债券持仓明细表_信用债"].loc[0, "库存数量(万)_PR"] = 100.0000001
    negative = stage2_processor.query_high_yield_detail().set_index("资产代码")
    assert negative.loc["TOOL.IB", "高收益单债剩余额度(万)"] < 0
    assert negative.loc["TOOL.IB", "高收益单债是否超限"] == "是"


def test_high_yield_capital_uses_full_price_cost_by_business_date(
    monkeypatch, stage2_processor, business_date
):
    monkeypatch.setattr(stage2_module, "load_limit_config", lambda **kwargs: _high_yield_config())
    monkeypatch.setattr(stage2_processor, "query_penetrate_high_yield_capital", lambda: pd.DataFrame())
    stage2_processor.cache.update(
        {
            "债券持仓表_核算系统": pd.DataFrame(
                [
                    {
                        "日期": business_date,
                        "账户": "高收益账户",
                        "简称": "债券A",
                        "代码": "A.IB",
                        "持仓面额(元)": 500000.0,
                        "全价成本(元)": 600000.0,
                    },
                    {
                        "日期": business_date,
                        "账户": "高收益账户",
                        "简称": "债券B",
                        "代码": "B.IB",
                        "持仓面额(元)": 800000.0,
                        "全价成本(元)": 400000.0,
                    },
                ]
            ),
            "金融工具池设置": pd.DataFrame(columns=["代码", "简称"]),
        }
    )
    zero = stage2_processor.query_high_yield_capital()
    assert zero["高收益年度总投资本金(万)"].tolist() == [100.0, 100.0]
    assert zero["高收益年度限额剩余额度(万)"].tolist() == [0.0, 0.0]
    assert zero["高收益年度限额是否超限"].tolist() == ["否", "否"]
    # Face value is deliberately different; the annual rule uses full-price cost.
    assert zero["持仓面额(元)"].sum() == 1300000.0

    stage2_processor.cache["债券持仓表_核算系统"].loc[1, "全价成本(元)"] += 0.001
    negative = stage2_processor.query_high_yield_capital()
    assert negative["高收益年度限额剩余额度(万)"].iloc[0] < 0
    assert negative["高收益年度限额是否超限"].tolist() == ["是", "是"]
