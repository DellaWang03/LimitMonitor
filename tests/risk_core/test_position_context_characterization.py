from __future__ import annotations

import pandas as pd
import pandas.testing as pdt
import pytest

from src.risk_core.position_context import (
    attach_isin_to_results,
    build_credit_risk_context,
    normalize_bond_position,
    normalize_credit_position,
    normalize_regulatory_position,
)
from src.stage1 import stage1_processor as stage1_module
from src.stage1.stage1_processor import SOURCE_ROW_ID_COL


def test_query_bond_position_freezes_selection_cleaning_and_code_normalization(
    monkeypatch, stage1_processor, business_date
):
    raw = pd.DataFrame(
        [
            {
                "日期": business_date,
                "金融资产会计属性": " 交易性金融资产 ",
                "部门": " 自营 ",
                "内部证券账户名称": " 自营部交易性 ",
                "资产代码": " 123456.0 ",
                "资产名称": " 债券A ",
                "库存数量(万)": "100",
                "库存数量(万)_空头为负": "-2",
                "债券分类2": " 信用债 ",
                "主证券代码": " 654321.0 ",
                "主证券名称": " 主债券A ",
                "库存数量(万)_PR": "98.5",
                "债券余额(亿)": "10",
                "债务主体wind代码": " F1000001.00 ",
                "担保人wind代码": " G1000001 ",
                "不应保留": "x",
            }
        ]
    )
    monkeypatch.setattr(stage1_module.pd, "read_excel", lambda *a, **k: raw.copy())

    result = stage1_processor.query_bond_position()
    pure_result = normalize_bond_position(raw)
    pdt.assert_frame_equal(pure_result, result, check_exact=True)

    assert result.columns.tolist() == [
        "日期",
        "金融资产会计属性",
        "部门",
        "内部证券账户名称",
        "资产代码",
        "资产名称",
        "库存数量(万)",
        "库存数量(万)_空头为负",
        "债券分类2",
        "主证券代码",
        "主证券名称",
        "库存数量(万)_PR",
        "债券余额(亿)",
        "债务主体wind代码",
        "担保人wind代码",
        "资产代码_标准",
        "主证券代码_标准",
    ]
    assert result.loc[0, "金融资产会计属性"] == "交易性金融资产"
    # Production security-code normalization preserves a numeric-looking ``.0``
    # string.  Wind issuer-code normalization is a separate merge-time rule.
    assert result.loc[0, "资产代码_标准"] == "123456.0"
    assert result.loc[0, "主证券代码_标准"] == "654321.0"
    assert result.loc[0, "库存数量(万)_PR"] == 98.5


def test_credit_and_regulatory_position_freeze_filter_asymmetry_and_source_identity(
    monkeypatch, stage1_processor, credit_row, business_date
):
    raw = pd.DataFrame(
        [
            credit_row(资产代码=" 123456.0 ", 主证券代码=" 123456.0 ", 省份="浙江"),
            credit_row(资产代码="RATE.IB", 主证券代码="RATE.IB", 债券分类2="利率债"),
            credit_row(
                资产代码="SUB.IB",
                主证券代码="SUB.IB",
                内部证券账户名称="代申购代缴款账户",
            ),
            credit_row(资产代码="BAD.IB", 主证券代码="BAD.IB", 日期="not-a-date"),
        ]
    )
    monkeypatch.setattr(stage1_module.pd, "read_excel", lambda *a, **k: raw.copy())

    credit = stage1_processor.query_bond_position_credit()
    regulatory = stage1_processor.query_bond_position_regulatory_full()
    pdt.assert_frame_equal(normalize_credit_position(raw), credit, check_exact=True)
    pdt.assert_frame_equal(normalize_regulatory_position(raw), regulatory, check_exact=True)

    assert credit["资产代码"].tolist() == ["123456.0"]
    assert credit["资产代码_标准"].tolist() == ["123456.0"]
    assert credit["省份"].tolist() == ["浙江省"]
    assert credit[SOURCE_ROW_ID_COL].tolist() == [1]
    assert credit.columns[-3:].tolist() == ["资产代码_标准", "主证券代码_标准", SOURCE_ROW_ID_COL]

    assert regulatory["资产代码"].tolist() == ["123456.0", "RATE.IB", "SUB.IB"]
    assert SOURCE_ROW_ID_COL not in regulatory.columns
    assert regulatory.loc[regulatory["资产代码"] == "RATE.IB", "债券分类2"].item() == "利率债"


def test_credit_risk_context_freezes_high_yield_pool_controller_and_risk_fallbacks(
    monkeypatch, stage1_processor, credit_row, business_date
):
    positions = pd.DataFrame(
        [
            credit_row(资产代码="ACCOUNT.IB", 内部证券账户名称="自营高收益账户"),
            credit_row(
                资产代码="PEN.IB",
                主证券代码="PEN.IB",
                债务主体="穿透主体",
                债务主体wind代码="F2000002.00",
                实际控制人名称="穿透原始实控人",
                实际控制人名称_修正=None,
                wind行业="煤炭",
                省份="山西",
            ),
            credit_row(
                资产代码="TOOL.IB",
                主证券代码="TOOL.IB",
                资产名称="工具池债",
                主证券名称="工具池债",
                债务主体="工具池主体",
                债务主体wind代码="F3000003.00",
                实际控制人名称="工具池原始实控人",
                实际控制人名称_修正="底稿修正实控人",
                担保人="担保公司",
                担保人wind代码="G3000003",
            ),
            credit_row(
                资产代码="NORMAL.IB",
                主证券代码="NORMAL.IB",
                债务主体="普通主体",
                债务主体wind代码="F4000004.00",
                实际控制人名称="普通原始实控人",
                实际控制人名称_修正="普通修正实控人",
            ),
        ]
    )
    stage1_processor.cache.update(
        {
            "债券持仓明细表_信用债": positions,
            "穿透高收益债券": pd.DataFrame([{"债券代码": "PEN.IB", "类型": "高收益"}]),
            "金融工具池设置": pd.DataFrame([{"代码": "TOOL", "简称": "工具池债"}]),
            "中债隐含评级AAA&AAA+": pd.DataFrame(
                [{"日期": business_date, "wind代码": "F4000004.00", "中债隐含评级": "AAA"}]
            ),
            "风控部债券池": pd.DataFrame(
                [
                    {"日期": business_date, "代码": "TOOL.IB", "债券池": "关注池", "主体池": "债券池回退"},
                    {"日期": business_date, "代码": "NORMAL.IB", "债券池": "核心池", "主体池": "债券池主体"},
                ]
            ),
            "风控部主体池": pd.DataFrame(
                [
                    {"日期": business_date, "发行人名称": "工具池主体", "主体wind代码": "F3000003", "主体池": "发行人池覆盖"},
                    {"日期": business_date, "发行人名称": "无关主体", "主体wind代码": "G3000003", "主体池": "担保池"},
                ]
            ),
            "发行人类型调整表": pd.DataFrame(
                [{"wind代码": "F4000004.00", "发行人类型": "非国企"}]
            ),
            "调整实控人名单": pd.DataFrame(
                [{"主体wind代码": "F3000003", "调整后实际控制人": "名单调整实控人"}]
            ),
            "单一担保公司规模限额": pd.DataFrame(
                [{"日期": business_date, "指标名称": "G3000003", "是否准入": "担保准入"}]
            ),
        }
    )
    monkeypatch.setattr(
        stage1_processor,
        "query_high_risk_industry",
        lambda: pd.DataFrame(
            [{"日期": business_date, "行业名称": "煤炭", "行业类别": "高风险行业"}]
        ),
    )
    monkeypatch.setattr(
        stage1_processor,
        "query_high_risk_province",
        lambda: pd.DataFrame(
            [{"日期": business_date, "省份名称": "山西省", "省份类别": "高风险省份"}]
        ),
    )

    result = stage1_processor.query_bond_position_credit_merged().set_index("资产代码")
    pure_frames = {
        **stage1_processor.cache,
        "高风险行业": stage1_processor.query_high_risk_industry(),
        "高风险省份": stage1_processor.query_high_risk_province(),
    }
    pure_result = build_credit_risk_context(pure_frames).set_index("资产代码")
    pdt.assert_frame_equal(pure_result, result, check_exact=True)

    assert result["是否属于高收益"].to_dict() == {
        "ACCOUNT.IB": "是",
        "PEN.IB": "是",
        "TOOL.IB": "是",
        "NORMAL.IB": "否",
    }
    assert result.loc["TOOL.IB", "主体池"] == "发行人池覆盖"
    assert result.loc["NORMAL.IB", "主体池"] == "债券池主体"
    assert result.loc["NORMAL.IB", "发行人类型_调整"] == "非国企"
    assert result.loc["TOOL.IB", "实际控制人名称_修正"] == "名单调整实控人"
    assert result.loc["PEN.IB", "实际控制人名称_修正"] == "穿透原始实控人"
    assert result.loc["TOOL.IB", "担保公司是否准入"] == "担保准入"
    assert result.loc["PEN.IB", "行业类别"] == "高风险行业"
    assert result.loc["PEN.IB", "省份类别"] == "高风险省份"
    assert result[SOURCE_ROW_ID_COL].tolist() == [1, 2, 3, 4]


def test_source_row_collapse_accepts_identical_expansion_but_rejects_conflict(
    stage1_processor,
):
    identical = pd.DataFrame(
        [
            {SOURCE_ROW_ID_COL: 1, "资产代码": "A.IB", "标签": None},
            {SOURCE_ROW_ID_COL: 1, "资产代码": "A.IB", "标签": ""},
        ]
    )
    collapsed = stage1_processor._collapse_credit_merged_to_source_rows(identical)
    assert len(collapsed) == 1
    assert collapsed[SOURCE_ROW_ID_COL].tolist() == [1]

    conflict = pd.DataFrame(
        [
            {SOURCE_ROW_ID_COL: 1, "资产代码": "A.IB"},
            {SOURCE_ROW_ID_COL: 1, "资产代码": "B.IB"},
        ]
    )
    with pytest.raises(ValueError, match="冲突展开"):
        stage1_processor._collapse_credit_merged_to_source_rows(conflict)


@pytest.mark.parametrize("bad_ids", [[1, 1], [1, None]])
def test_source_row_validation_is_fail_closed(stage1_processor, bad_ids):
    frame = pd.DataFrame({SOURCE_ROW_ID_COL: bad_ids})
    with pytest.raises(ValueError):
        stage1_processor._validate_source_row_id(frame, "信用债")


def test_attach_isin_to_results_preserves_existing_value_and_detaches_inputs():
    source = pd.DataFrame(
        [
            {"资产代码": " A.IB ", "ISIN码": "EXISTING"},
            {"资产代码": "B.IB", "ISIN码": None},
        ]
    )
    untouched = pd.DataFrame({"值": [1]})
    mapping = pd.DataFrame(
        [
            {"资产代码": "A.IB", "ISIN码": "MAPPED-A"},
            {"资产代码": "B.IB", "ISIN码": "MAPPED-B"},
        ]
    )

    result = attach_isin_to_results({"明细": source, "汇总": untouched}, mapping)

    assert result["明细"]["资产代码"].tolist() == ["A.IB", "B.IB"]
    assert result["明细"]["ISIN码"].tolist() == ["EXISTING", "MAPPED-B"]
    pdt.assert_frame_equal(result["汇总"], untouched, check_exact=True)
    result["明细"].loc[0, "ISIN码"] = "CHANGED"
    assert source.loc[0, "ISIN码"] == "EXISTING"
    assert mapping.loc[0, "ISIN码"] == "MAPPED-A"
