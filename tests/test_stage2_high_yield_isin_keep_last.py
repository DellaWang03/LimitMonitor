from __future__ import annotations

import pandas as pd

from src.stage2 import stage2_processor
from src.stage2.stage2_processor import (
    SOURCE_ROW_ID_COL,
    Stage2Processor,
    _build_penetrate_isin_type_map_keep_last,
)


def test_stage2_penetrate_high_yield_load_preserves_source_rows(monkeypatch, tmp_path):
    def fake_load_limit_config(*, sheet_name, **kwargs):
        assert sheet_name == "穿透高收益债券"
        return pd.DataFrame(
            [
                {
                    "债券代码": "OLD.MOX",
                    "ISIN代码": "XS0000000001",
                    "名称": "旧名称",
                    "类型": "高收益",
                },
                {
                    "债券代码": "NEW.MOX",
                    "ISIN代码": "XS0000000001",
                    "名称": "新名称",
                    "类型": "非高收益",
                },
            ]
        )

    monkeypatch.setattr(stage2_processor, "load_limit_config", fake_load_limit_config)

    processor = Stage2Processor(
        data_dir=tmp_path,
        output_dir=tmp_path / "out",
        stage0_output_dir=tmp_path / "stage0",
        stage1_output_dir=tmp_path / "stage1",
    )

    result = processor.query_penetrate_high_yield()

    assert len(result) == 2
    assert result["债券代码"].tolist() == ["OLD.MOX", "NEW.MOX"]


def test_stage2_penetrate_isin_type_map_keeps_last_duplicate_isin():
    mapping = _build_penetrate_isin_type_map_keep_last(
        pd.DataFrame(
            [
                {
                    "债券代码": "OLD.MOX",
                    "ISIN代码": "XS0000000001",
                    "名称": "旧名称",
                    "类型": "高收益",
                },
                {
                    "债券代码": "NEW.MOX",
                    "ISIN代码": "XS0000000001",
                    "名称": "新名称",
                    "类型": "非高收益",
                },
            ]
        )
    )

    assert mapping == {"XS0000000001": "非高收益"}


def test_stage2_high_risk_position_totals_only_apply_to_matching_category(tmp_path):
    stage0_dir = tmp_path / "stage0"
    stage1_dir = tmp_path / "stage1"
    output_dir = tmp_path / "out"
    stage0_dir.mkdir()
    stage1_dir.mkdir()

    date = pd.Timestamp("2026-06-22")
    base_rows = [
        {
            SOURCE_ROW_ID_COL: 1,
            "日期": date,
            "ISIN码": "CNSAFE",
            "金融资产会计属性": "交易性金融资产",
            "部门": "自营",
            "内部证券账户名称": "自营部交易性",
            "资产代码": "SAFE.IB",
            "资产名称": "普通债",
            "债券分类2": "信用债",
            "债券类型1": "一般企业债",
            "主证券代码": "SAFE.IB",
            "主证券名称": "普通债",
            "库存数量(万)_PR": 100.0,
            "债券余额(亿)": 10.0,
            "发行人类型": "产业",
            "债务主体": "普通主体",
            "债务主体wind代码": "SAFE",
            "调整后实际控制人": "普通实控人",
            "担保人": "",
            "担保人wind代码": "",
            "是否城投债": "是",
            "债券类别": "城投债",
            "wind行业": "综合",
            "省份": "北京市",
        },
        {
            SOURCE_ROW_ID_COL: 2,
            "日期": date,
            "ISIN码": "CNRISK",
            "金融资产会计属性": "交易性金融资产",
            "部门": "自营",
            "内部证券账户名称": "自营部交易性",
            "资产代码": "RISK.IB",
            "资产名称": "高风险债",
            "债券分类2": "信用债",
            "债券类型1": "一般企业债",
            "主证券代码": "RISK.IB",
            "主证券名称": "高风险债",
            "库存数量(万)_PR": 200.0,
            "债券余额(亿)": 20.0,
            "发行人类型": "产业",
            "债务主体": "高风险主体",
            "债务主体wind代码": "RISK",
            "调整后实际控制人": "高风险实控人",
            "担保人": "",
            "担保人wind代码": "",
            "是否城投债": "是",
            "债券类别": "城投债",
            "wind行业": "煤炭",
            "省份": "山西省",
        },
    ]
    pd.DataFrame(base_rows).to_excel(
        stage1_dir / "债券持仓明细表_信用债.xlsx",
        index=False,
    )
    pd.DataFrame({"日期": [date], "公司净资产(万)": [100000.0]}).to_excel(
        stage0_dir / "公司净资产_手工_每日.xlsx",
        index=False,
    )

    processor = Stage2Processor(
        data_dir=tmp_path,
        output_dir=output_dir,
        stage0_output_dir=stage0_dir,
        stage1_output_dir=stage1_dir,
    )
    processor.cache["债券持仓明细表_信用债_合并风险限额相关"] = pd.DataFrame(
        [
            {
                SOURCE_ROW_ID_COL: 1,
                "日期": date,
                "资产代码": "SAFE.IB",
                "内部证券账户名称": "自营部交易性",
                "库存数量(万)_PR": 100.0,
                "行业类别": pd.NA,
                "省份类别": pd.NA,
            },
            {
                SOURCE_ROW_ID_COL: 2,
                "日期": date,
                "资产代码": "RISK.IB",
                "内部证券账户名称": "自营部交易性",
                "库存数量(万)_PR": 200.0,
                "行业类别": "高风险行业",
                "省份类别": "高风险省份",
            },
        ]
    )
    processor.cache["高风险行业"] = pd.DataFrame(
        [{"日期": date, "行业名称": "煤炭", "行业类别": "高风险行业", "指标值": 0.10}]
    )
    processor.cache["高风险省份"] = pd.DataFrame(
        [{"日期": date, "省份名称": "山西省", "省份类别": "高风险省份", "指标值": 0.10}]
    )
    processor.cache["地域集中度限额(含城投)"] = pd.DataFrame(
        [
            {"日期": date, "指标名称": "北京市", "指标值_地域集中度限额": 0.12, "指标值_城投集中度限额": 0.08},
            {"日期": date, "指标名称": "山西省", "指标值_地域集中度限额": 0.12, "指标值_城投集中度限额": 0.08},
        ]
    )
    processor.cache["单一地域总持仓"] = pd.DataFrame(
        [
            {"日期": date, "省份": "北京市", "单一地域总持仓_PR": 100.0, "地域集中度": 0.01},
            {"日期": date, "省份": "山西省", "单一地域总持仓_PR": 200.0, "地域集中度": 0.02},
        ]
    )
    processor.cache["单一地域城投总持仓"] = pd.DataFrame(
        [
            {"日期": date, "省份": "北京市", "单一地域城投总持仓_PR": 100.0, "城投地域集中度": 0.01},
            {"日期": date, "省份": "山西省", "单一地域城投总持仓_PR": 200.0, "城投地域集中度": 0.02},
        ]
    )
    processor.cache["信用债总持仓"] = pd.DataFrame(
        [{"日期": date, "信用债总持仓_PR": 300.0}]
    )
    processor.cache["高风险行业总持仓"] = pd.DataFrame(
        [
            {
                "日期": date,
                "行业类别": "高风险行业",
                "高风险行业总持仓_PR": 200.0,
                "高风险行业集中度": 200.0 / 300.0,
            }
        ]
    )
    processor.cache["高风险省份总持仓"] = pd.DataFrame(
        [
            {
                "日期": date,
                "省份类别": "高风险省份",
                "高风险省份总持仓_PR": 200.0,
                "高风险省份集中度": 200.0 / 300.0,
            }
        ]
    )

    result = processor.query_credit_bond_detail_2()

    safe_row = result.loc[result["资产代码"] == "SAFE.IB"].iloc[0]
    risk_row = result.loc[result["资产代码"] == "RISK.IB"].iloc[0]
    assert pd.isna(safe_row["高风险行业总持仓_PR"])
    assert pd.isna(safe_row["高风险省份总持仓_PR"])
    assert risk_row["高风险行业总持仓_PR"] == 200.0
    assert risk_row["高风险省份总持仓_PR"] == 200.0
