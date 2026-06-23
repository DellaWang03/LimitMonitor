from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.stage1.stage1_limit_detail import LimitDetailCalculator
from src.stage1.stage1_processor import Stage1Processor


def _minimal_credit_row(**overrides):
    row = {
        "日期": pd.Timestamp("2026-05-20"),
        "金融资产会计属性": "交易性",
        "部门": "多资产投资部",
        "内部证券账户名称": "普通账户",
        "资产代码": "113680.SH",
        "资产名称": "测试转债",
        "债券分类2": "转债交债",
        "债券类型1": "可转债",
        "主证券代码": "113680.SH",
        "主证券名称": "测试转债",
        "库存数量(万)_PR": 100.0,
        "债券余额(亿)": 10.0,
        "发行人类型": "国企",
        "债务主体": "测试主体",
        "债务主体wind代码": "ISSUER1",
        "实际控制人名称_修正": "测试实控人",
        "担保人": None,
        "担保人wind代码": None,
        "是否城投债": "否",
        "债券类别": "产业债",
        "wind行业": "制造业",
        "省份": "浙江省",
        "合并辅助列": "",
    }
    row.update(overrides)
    return row


def test_stage1_marks_financial_tool_pool_code_as_high_yield(monkeypatch, tmp_path):
    processor = Stage1Processor(tmp_path, tmp_path, tmp_path)
    monkeypatch.setattr(
        processor,
        "query_high_risk_industry",
        lambda: pd.DataFrame(columns=["日期", "行业名称", "行业类别"]),
    )
    monkeypatch.setattr(
        processor,
        "query_high_risk_province",
        lambda: pd.DataFrame(columns=["日期", "省份名称", "省份类别"]),
    )

    processor.cache["债券持仓明细表_信用债"] = pd.DataFrame(
        [
            _minimal_credit_row(
                资产代码="113680.SH",
                资产名称="非工具池简称",
                主证券代码="113680.SH",
                主证券名称="非工具池简称",
            )
        ]
    )
    processor.cache["穿透高收益债券"] = pd.DataFrame(columns=["债券代码", "类型"])
    processor.cache["金融工具池设置"] = pd.DataFrame(
        [{"代码": "113680", "简称": "丽岛转债"}]
    )

    result = processor.query_bond_position_credit_merged()

    assert result.loc[0, "是否属于高收益"] == "是"


def test_stage1_credit_merge_loads_financial_tool_pool_when_cache_missing(monkeypatch, tmp_path):
    processor = Stage1Processor(tmp_path, tmp_path, tmp_path)
    monkeypatch.setattr(
        processor,
        "query_high_risk_industry",
        lambda: pd.DataFrame(columns=["日期", "行业名称", "行业类别"]),
    )
    monkeypatch.setattr(
        processor,
        "query_high_risk_province",
        lambda: pd.DataFrame(columns=["日期", "省份名称", "省份类别"]),
    )
    monkeypatch.setattr(
        processor,
        "query_financial_tool_pool",
        lambda: pd.DataFrame([{"代码": "113680", "简称": "丽岛转债"}]),
    )

    processor.cache["债券持仓明细表_信用债"] = pd.DataFrame(
        [
            _minimal_credit_row(
                资产代码="113680.SH",
                资产名称="非工具池简称",
                主证券代码="113680.SH",
                主证券名称="非工具池简称",
            )
        ]
    )
    processor.cache["穿透高收益债券"] = pd.DataFrame(columns=["债券代码", "类型"])

    result = processor.query_bond_position_credit_merged()

    assert result.loc[0, "是否属于高收益"] == "是"
    assert "金融工具池设置" in processor.cache


def test_stage1_single_bond_total_position_keeps_high_yield_rows_per_m_code(tmp_path):
    processor = Stage1Processor(tmp_path, tmp_path, tmp_path)
    credit_rows = pd.DataFrame(
        [
            _minimal_credit_row(**{"库存数量(万)_PR": 80.0}),
            _minimal_credit_row(
                **{"内部证券账户名称": "普通账户2", "库存数量(万)_PR": 20.0}
            ),
        ]
    )
    merged_rows = credit_rows.copy()
    merged_rows["是否属于高收益"] = ["是", "否"]

    processor.cache["债券持仓明细表_信用债"] = credit_rows
    processor.cache["债券持仓明细表_信用债_合并风险限额相关"] = merged_rows

    result = processor.query_single_bond_total_position()

    assert result["单一债券总持仓_PR"].iloc[0] == 100.0


def test_stage1_single_bond_total_position_uses_fallback_bond_key_when_main_code_missing(tmp_path):
    processor = Stage1Processor(tmp_path, tmp_path, tmp_path)
    processor.cache["债券持仓明细表_信用债"] = pd.DataFrame(
        [
            _minimal_credit_row(
                **{
                    "资产代码": "5354.HK",
                    "资产名称": "ZBTECH 6.95 12/13/27",
                    "主证券代码": None,
                    "主证券名称": None,
                    "ISIN码": "XS1234567890",
                    "库存数量(万)_PR": 100.0,
                    "债券余额(亿)": 10.0,
                }
            ),
            _minimal_credit_row(
                **{
                    "内部证券账户名称": "普通账户2",
                    "资产代码": "ALT5354.HK",
                    "资产名称": "ZBTECH 6.95 12/13/27",
                    "主证券代码": None,
                    "主证券名称": None,
                    "ISIN码": "XS1234567890",
                    "库存数量(万)_PR": 50.0,
                    "债券余额(亿)": 10.0,
                }
            ),
            _minimal_credit_row(
                **{
                    "资产代码": "MOXTB23122.MOX",
                    "资产名称": "CDSNFE 7.9 12/22/26",
                    "主证券代码": None,
                    "主证券名称": None,
                    "ISIN码": None,
                    "库存数量(万)_PR": 30.0,
                    "债券余额(亿)": 5.0,
                }
            ),
            _minimal_credit_row(
                **{
                    "内部证券账户名称": "普通账户2",
                    "资产代码": "MOXTB23122.MOX",
                    "资产名称": "CDSNFE 7.9 12/22/26",
                    "主证券代码": None,
                    "主证券名称": None,
                    "ISIN码": None,
                    "库存数量(万)_PR": 20.0,
                    "债券余额(亿)": 5.0,
                }
            ),
        ]
    )

    result = processor.query_single_bond_total_position()
    position_by_key = result.set_index("单一债券归并键")["单一债券总持仓_PR"].to_dict()

    assert position_by_key["ISIN码::XS1234567890"] == 150.0
    assert position_by_key["资产代码_标准::MOXTB23122.MOX"] == 50.0


def test_stage1_single_issuer_total_position_keeps_high_yield_rows_per_m_code(tmp_path):
    processor = Stage1Processor(tmp_path, tmp_path, tmp_path)
    credit_rows = pd.DataFrame(
        [
            _minimal_credit_row(**{"库存数量(万)_PR": 80.0}),
            _minimal_credit_row(
                **{"内部证券账户名称": "普通账户2", "库存数量(万)_PR": 20.0}
            ),
        ]
    )
    merged_rows = credit_rows.copy()
    merged_rows["是否属于高收益"] = ["是", "否"]

    processor.cache["债券持仓明细表_信用债"] = credit_rows
    processor.cache["债券持仓明细表_信用债_合并风险限额相关"] = merged_rows

    result = processor.query_single_issuer_total_position()

    assert result["单一主体总持仓_PR"].iloc[0] == 100.0


def test_stage1_single_controller_total_position_keeps_high_yield_rows_per_m_code(tmp_path):
    processor = Stage1Processor(tmp_path, tmp_path, tmp_path)
    merged_rows = pd.DataFrame(
        [
            _minimal_credit_row(**{"库存数量(万)_PR": 80.0, "是否属于高收益": "是"}),
            _minimal_credit_row(
                **{
                    "内部证券账户名称": "普通账户2",
                    "库存数量(万)_PR": 20.0,
                    "是否属于高收益": "否",
                }
            ),
        ]
    )

    processor.cache["债券持仓明细表_信用债_合并风险限额相关"] = merged_rows

    result = processor.query_single_controller_total_position()

    assert result["单一实控人总持仓_PR"].iloc[0] == 100.0


def test_stage1_specific_issuer_total_position_uses_credit_source_and_enhanced_high_yield_filter(tmp_path):
    processor = Stage1Processor(tmp_path, tmp_path, tmp_path)
    credit_rows = pd.DataFrame(
        [
            _minimal_credit_row(**{"库存数量(万)_PR": 80.0}),
            _minimal_credit_row(
                **{"内部证券账户名称": "普通账户2", "库存数量(万)_PR": 20.0}
            ),
            _minimal_credit_row(
                **{
                    "内部证券账户名称": "普通账户3",
                    "资产代码": "113681.SH",
                    "资产名称": "测试债2",
                    "主证券代码": "113681.SH",
                    "主证券名称": "测试债2",
                    "库存数量(万)_PR": 30.0,
                    "债务主体wind代码": "ISSUER2",
                    "债务主体": "测试主体2",
                }
            ),
        ]
    )
    merged_rows = credit_rows.iloc[:2].copy()
    merged_rows["是否属于高收益"] = ["是", "否"]

    processor.cache["债券持仓明细表_信用债"] = credit_rows
    processor.cache["债券持仓明细表_信用债_合并风险限额相关"] = merged_rows
    processor.cache["穿透高收益债券"] = pd.DataFrame(
        [{"债券代码": "113680.SH", "类型": "高收益"}]
    )
    processor.cache["金融工具池设置"] = pd.DataFrame(columns=["代码", "简称"])
    processor.cache["特定主体限额"] = pd.DataFrame(
        [
            {
                "日期": pd.Timestamp("2026-05-20"),
                "主体wind代码": "ISSUER1",
                "指标名称": "测试主体",
                "指标值": 1000.0,
            },
            {
                "日期": pd.Timestamp("2026-05-20"),
                "主体wind代码": "ISSUER2",
                "指标名称": "测试主体2",
                "指标值": 1000.0,
            },
        ]
    )

    result = processor.query_specific_issuer_total_position()
    position_by_name = result.set_index("特定主体名称")["特定主体总持仓"].to_dict()

    assert "测试主体" not in position_by_name
    assert position_by_name["测试主体2"] == 30.0


def test_single_bond_detail_excludes_financial_tool_pool_high_yield_rows():
    base_date = pd.Timestamp("2026-05-20")
    credit_rows = pd.DataFrame(
        [
            _minimal_credit_row(**{"库存数量(万)_PR": 80.0}),
            _minimal_credit_row(
                **{"内部证券账户名称": "普通账户2", "库存数量(万)_PR": 20.0}
            ),
        ]
    )
    merged_rows = credit_rows.copy()
    merged_rows["是否属于高收益"] = ["是", "否"]
    limit_detail = pd.DataFrame(
        [
            {
                "日期": base_date,
                "主证券代码_标准": "113680.SH",
                "单一债券规模限额适用类别": "可转债/关注池",
                "单一债券规模限额指标值": 1000.0,
                "单一债券规模剩余额度(万)": 980.0,
                "单一债券是否超限": "否",
                "单一债券集中度限额适用类别": "可转债/关注池",
                "单一债券集中度限额指标值": 0.16,
                "单一债券集中度剩余额度(万)": 1580.0,
                "单一债券集中度是否超限": "否",
            }
        ]
    )
    calculator = LimitDetailCalculator(
        {
            "债券持仓明细表": credit_rows,
            "债券持仓明细表_信用债_合并风险限额相关": merged_rows,
            "限额明细_债券持仓明细表_信用债1_2": limit_detail,
        },
        regulatory_concentration_limit=0.16,
    )

    result = calculator.calculate_limit_detail_single_bond()

    assert result["单一债券总持仓_PR"].iloc[0] == 20.0


def test_limit_detail_1_2_merges_single_bond_position_by_fallback_bond_key():
    base_date = pd.Timestamp("2026-05-20")
    merged_rows = pd.DataFrame(
        [
            _minimal_credit_row(
                **{
                    "日期": base_date,
                    "资产代码": "5354.HK",
                    "资产名称": "ZBTECH 6.95 12/13/27",
                    "主证券代码": None,
                    "主证券名称": None,
                    "ISIN码": None,
                    "库存数量(万)_PR": 2383.5,
                    "债券余额(亿)": None,
                    "是否属于高收益": "否",
                    "发行人类型_调整": "国企",
                    "债券池": None,
                    "主体池": None,
                    "主体池_担保": None,
                    "担保公司是否准入": None,
                }
            )
        ]
    )
    single_bond_position = pd.DataFrame(
        [
            {
                "日期": base_date,
                "业务分类": "自营业务",
                "单一债券归并键": "资产代码_标准::5354.HK",
                "单一债券归并键来源": "资产代码_标准",
                "单一债券总持仓_PR": 2383.5,
                "单一债券集中度": None,
            }
        ]
    )
    calculator = LimitDetailCalculator(
        {
            "债券持仓明细表_信用债_合并风险限额相关": merged_rows,
            "单一债券规模限额": pd.DataFrame(
                [{"日期": base_date, "指标名称": "国企/", "指标值": 0.0}]
            ),
            "单一债券集中度限额": pd.DataFrame(
                [{"日期": base_date, "指标名称": "国企/", "指标值": 0.0}]
            ),
            "单一主体规模限额": pd.DataFrame(
                [{"日期": base_date, "指标名称": "国企", "指标值": 10000.0}]
            ),
            "单一债券总持仓": single_bond_position,
            "单一主体总持仓": pd.DataFrame(
                [
                    {
                        "日期": base_date,
                        "业务分类": "自营业务",
                        "债务主体": "测试主体",
                        "单一主体总持仓_PR": 2383.5,
                    }
                ]
            ),
            "限额明细_单一实控人_取最高额度": pd.DataFrame(
                [
                    {
                        "日期": base_date,
                        "业务分类": "自营业务",
                        "实际控制人名称_修正": "测试实控人",
                        "单一实控人限额适用类别": "国企",
                        "单一实控人规模限额指标值": 10000.0,
                        "单一实控人总持仓_PR": 2383.5,
                        "单一实控人规模剩余额度(万)": 7616.5,
                        "单一实控人是否超限": "否",
                    }
                ]
            ),
        }
    )

    result = calculator.calculate_limit_detail_1_2()

    assert result["单一债券总持仓_PR"].iloc[0] == 2383.5


def test_single_bond_detail_keeps_original_position_rows_not_in_credit_merged():
    base_date = pd.Timestamp("2026-05-20")
    original_rows = pd.DataFrame(
        [
            _minimal_credit_row(**{"库存数量(万)_PR": 80.0}),
            _minimal_credit_row(
                **{"内部证券账户名称": "普通账户2", "库存数量(万)_PR": 20.0}
            ),
            _minimal_credit_row(
                **{
                    "内部证券账户名称": "普通账户3",
                    "资产代码": "113681.SH",
                    "资产名称": "测试债2",
                    "主证券代码": "113681.SH",
                    "主证券名称": "测试债2",
                    "库存数量(万)_PR": 30.0,
                }
            ),
        ]
    )
    merged_rows = original_rows.iloc[:2].copy()
    merged_rows["是否属于高收益"] = ["是", "否"]
    limit_detail = pd.DataFrame(
        [
            {
                "日期": base_date,
                "主证券代码_标准": "113680.SH",
                "单一债券规模限额适用类别": "可转债/关注池",
                "单一债券规模限额指标值": 1000.0,
                "单一债券规模剩余额度(万)": 980.0,
                "单一债券是否超限": "否",
                "单一债券集中度限额适用类别": "可转债/关注池",
                "单一债券集中度限额指标值": 0.16,
                "单一债券集中度剩余额度(万)": 1580.0,
                "单一债券集中度是否超限": "否",
            },
            {
                "日期": base_date,
                "主证券代码_标准": "113681.SH",
                "单一债券规模限额适用类别": "普通信用债/关注池",
                "单一债券规模限额指标值": 1000.0,
                "单一债券规模剩余额度(万)": 970.0,
                "单一债券是否超限": "否",
                "单一债券集中度限额适用类别": "普通信用债/关注池",
                "单一债券集中度限额指标值": 0.16,
                "单一债券集中度剩余额度(万)": 1570.0,
                "单一债券集中度是否超限": "否",
            },
        ]
    )
    calculator = LimitDetailCalculator(
        {
            "债券持仓明细表": original_rows,
            "债券持仓明细表_信用债_合并风险限额相关": merged_rows,
            "限额明细_债券持仓明细表_信用债1_2": limit_detail,
        },
        regulatory_concentration_limit=0.16,
    )

    result = calculator.calculate_limit_detail_single_bond()
    quantity_by_code = result.set_index("证券代码")["单一债券总持仓_PR"].to_dict()

    assert quantity_by_code["113680.SH"] == 20.0
    assert quantity_by_code["113681.SH"] == 30.0


def test_single_issuer_detail_uses_credit_source_and_enhanced_high_yield_filter():
    base_date = pd.Timestamp("2026-05-20")
    credit_rows = pd.DataFrame(
        [
            _minimal_credit_row(**{"库存数量(万)_PR": 80.0}),
            _minimal_credit_row(
                **{"内部证券账户名称": "普通账户2", "库存数量(万)_PR": 20.0}
            ),
            _minimal_credit_row(
                **{
                    "内部证券账户名称": "普通账户3",
                    "资产代码": "113681.SH",
                    "资产名称": "测试债2",
                    "主证券代码": "113681.SH",
                    "主证券名称": "测试债2",
                    "库存数量(万)_PR": 30.0,
                    "债务主体wind代码": "ISSUER2",
                    "债务主体": "测试主体2",
                }
            ),
        ]
    )
    merged_rows = credit_rows.iloc[:2].copy()
    merged_rows["是否属于高收益"] = ["是", "否"]
    limit_detail = pd.DataFrame(
        [
            {
                "日期": base_date,
                "债务主体wind代码": "ISSUER1",
                "单一主体是否超限": "否",
                "单一主体限额适用类别": "可转债/关注池",
                "单一主体规模限额指标值": 1000.0,
                "单一主体规模剩余额度(万)": 980.0,
            },
            {
                "日期": base_date,
                "债务主体wind代码": "ISSUER2",
                "单一主体是否超限": "否",
                "单一主体限额适用类别": "普通信用债/关注池",
                "单一主体规模限额指标值": 1000.0,
                "单一主体规模剩余额度(万)": 970.0,
            },
        ]
    )
    calculator = LimitDetailCalculator(
        {
            "债券持仓明细表_信用债": credit_rows,
            "债券持仓明细表_信用债_合并风险限额相关": merged_rows,
            "穿透高收益债券": pd.DataFrame(
                [{"债券代码": "113680.SH", "类型": "高收益"}]
            ),
            "限额明细_债券持仓明细表_信用债1_2": limit_detail,
        }
    )

    result = calculator.calculate_limit_detail_single_issuer()
    position_by_issuer = result.set_index("债务主体wind代码")["单一主体总持仓_PR"].to_dict()

    assert "ISSUER1" not in position_by_issuer
    assert position_by_issuer["ISSUER2"] == 30.0


def test_limit_detail_1_1_keeps_high_yield_rows_per_m_code():
    base_date = pd.Timestamp("2026-05-20")
    merged_rows = pd.DataFrame(
        [_minimal_credit_row(**{"是否属于高收益": "是", "库存数量(万)_PR": 80.0})]
    )
    specific_issuer_detail = pd.DataFrame(
        [
            {
                "日期": base_date,
                "业务分类": "自营业务",
                "资产代码": "113680.SH",
                "指标名称": "测试主体限额",
                "特定主体限额指标值": 1000.0,
                "特定主体总持仓": 80.0,
                "特定主体限额剩余额度": 920.0,
                "特定主体限额是否超限": "否",
            }
        ]
    )
    specific_controller_detail = pd.DataFrame(
        [
            {
                "日期": base_date,
                "业务分类": "自营业务",
                "资产代码": "999999.SH",
                "指标名称": "其他实控人限额",
                "特定实控人限额指标值": 1000.0,
                "特定实控人总持仓": 10.0,
                "特定实控人限额剩余额度": 990.0,
                "特定实控人限额是否超限": "否",
            }
        ]
    )
    calculator = LimitDetailCalculator(
        {
            "债券持仓明细表_信用债_合并风险限额相关": merged_rows,
            "限额明细_特定主体": specific_issuer_detail,
            "限额明细_特定实控人": specific_controller_detail,
        }
    )

    result = calculator.calculate_limit_detail_1_1()

    assert result["资产代码"].tolist() == ["113680.SH"]
    assert result["特定主体限额名称"].iloc[0] == "测试主体限额"


def test_single_controller_detail_keeps_focus_pool_and_uses_1_2_per_m_code():
    base_date = pd.Timestamp("2026-05-20")
    merged_rows = pd.DataFrame(
        [
            _minimal_credit_row(
                **{
                    "内部证券账户名称": "关注池账户",
                    "实际控制人名称_修正": "测试实控人A",
                    "资产代码": "113682.SH",
                    "资产名称": "关注池债",
                    "主证券代码": "113682.SH",
                    "主证券名称": "关注池债",
                    "库存数量(万)_PR": 20.0,
                    "是否属于高收益": "否",
                }
            ),
            _minimal_credit_row(
                **{
                    "内部证券账户名称": "高收益账户",
                    "实际控制人名称_修正": "测试实控人A",
                    "资产代码": "113683.SH",
                    "资产名称": "高收益债",
                    "主证券代码": "113683.SH",
                    "主证券名称": "高收益债",
                    "库存数量(万)_PR": 300.0,
                    "是否属于高收益": "是",
                }
            ),
        ]
    )
    limit_detail_1_2 = pd.DataFrame(
        [
            {
                "日期": base_date,
                "实际控制人名称_修正": "测试实控人A",
                "单一主体/实控人限额适用类别": "实控人类别低",
                "单一实控人规模限额指标值": 1000.0,
                "单一实控人规模剩余额度(万)": 980.0,
            },
            {
                "日期": base_date,
                "实际控制人名称_修正": "测试实控人A",
                "单一主体/实控人限额适用类别": "实控人类别高",
                "单一实控人规模限额指标值": 2000.0,
                "单一实控人规模剩余额度(万)": 1980.0,
            },
        ]
    )
    calculator = LimitDetailCalculator(
        {
            "债券持仓明细表_信用债_合并风险限额相关": merged_rows,
            "限额明细_债券持仓明细表_信用债1_2": limit_detail_1_2,
        }
    )

    result = calculator.calculate_limit_detail_single_controller()

    assert len(result) == 1
    row = result.iloc[0]
    assert row["实际控制人名称_修正"] == "测试实控人A"
    assert row["单一实控人总持仓_PR"] == 20.0
    assert row["单一实控人规模限额指标值"] == 2000.0
    assert row["单一实控人规模剩余额度(万)"] == 1980.0
    assert "资产代码" not in result.columns


def test_specific_controller_limit_uses_controller_name_for_total_position():
    base_date = pd.Timestamp("2026-05-20")
    cache = {
        "债券持仓明细表_信用债_合并风险限额相关": pd.DataFrame(
            [
                {
                    "日期": base_date,
                    "内部证券账户名称": "普通账户",
                    "实际控制人名称_修正": "山西省国有资本运营有限公司",
                    "债务主体": "主体A",
                    "资产代码": "102382403.IB",
                    "资产名称": "23华阳新材MTN012",
                    "库存数量(万)_PR": 100.0,
                }
            ]
        ),
        "特定实控人限额": pd.DataFrame(
            [
                {
                    "日期": base_date,
                    "实控人名称": "山西省国有资本运营有限公司",
                    "指标名称": "山西国运系列",
                    "指标值": 90000.0,
                }
            ]
        ),
        "特定实控人总持仓": pd.DataFrame(
            [
                {
                    "日期": base_date,
                    "业务分类": "自营业务",
                    "特定实控人名称": "山西省国有资本运营有限公司",
                    "特定实控人总持仓": 4200.0,
                }
            ]
        ),
    }
    calculator = LimitDetailCalculator(cache)

    result = calculator.calculate_limit_detail_specific_controller()

    assert result["特定实控人总持仓"].iloc[0] == 4200.0
    assert result["特定实控人限额剩余额度"].iloc[0] == 85800.0
