from __future__ import annotations

import pandas as pd

from src.visualization.display_builders import (
    export_legacy_page1_single_credit_table,
    export_legacy_page3_category_credit_table,
)


class DummyLoader:
    def __init__(
        self,
        *,
        stage1_credit_1_2: pd.DataFrame | None = None,
        stage2_credit_2: pd.DataFrame | None = None,
    ) -> None:
        self._stage1_credit_1_2 = stage1_credit_1_2
        self._stage2_credit_2 = stage2_credit_2

    def load_stage1_credit_1_2(self) -> pd.DataFrame:
        return self._stage1_credit_1_2.copy()

    def load_stage2_credit_2(self) -> pd.DataFrame:
        return self._stage2_credit_2.copy()


def test_legacy_page1_exports_concentration_amount_and_pbi_percent_format():
    row = {
        "日期": pd.Timestamp("2026-06-22"),
        "代码": "BOND.IB",
        "资产代码": "BOND.IB",
        "资产名称": "测试债",
        "内部证券账户名称": "自营部交易性",
        "债务主体": "测试主体",
        "库存数量(万)_PR": 100.0,
        "是否超限": "否",
        "是否新老划断": "新规",
        "部门": "自营",
        "单一债券是否超限": "否",
        "单一债券规模限额适用类别": "普通",
        "单一债券规模限额指标值": 5000.0,
        "单一债券总持仓_PR": 100.0,
        "单一债券规模剩余额度(万)": 4900.0,
        "单一债券集中度是否超限": "否",
        "单一债券集中度限额适用类别": "普通",
        "单一债券集中度限额指标值": 0.16,
        "债券余额(亿)": 35.0,
        "单一债券集中度总额度": 56000.0,
        "单一债券集中度": 0.0314,
        "单一债券集中度剩余额度(万)": 55900.0,
        "单一主体是否超限": "否",
        "单一主体限额适用类别": "普通",
        "单一主体规模限额指标值": 5000.0,
        "单一主体总持仓_PR": 100.0,
        "单一主体规模剩余额度(万)": 4900.0,
        "实际控制人名称_修正": "测试实控人",
        "单一实控人是否超限": "否",
        "单一实控人限额适用类别": "普通",
        "单一实控人规模限额指标值": 5000.0,
        "单一实控人总持仓_PR": 100.0,
        "单一实控人规模剩余额度(万)": 4900.0,
        "担保人": "测试担保",
        "单一担保人是否超限": "否",
        "单一担保公司规模限额": 5000.0,
        "单一担保人总持仓_PR": 100.0,
        "单一担保公司规模剩余额度(万)": 4900.0,
    }
    exported = export_legacy_page1_single_credit_table(
        DummyLoader(stage1_credit_1_2=pd.DataFrame([row]))
    )

    assert exported.loc[0, "债券余额(亿)"] == 35.0
    assert exported.loc[0, "单一债券集中度总额度"] == 56000.0
    assert exported.loc[0, "单一债券集中度限额"] == "16.00%"
    assert exported.loc[0, "单一债券集中度"] == "3.14%"


def test_legacy_page3_maps_stage2_field_names_and_pbi_percent_format():
    row = {
        "日期": pd.Timestamp("2026-06-22"),
        "代码": "BOND.IB",
        "资产代码": "BOND.IB",
        "资产名称": "测试债",
        "内部证券账户名称": "自营部交易性",
        "债务主体": "测试主体",
        "部门": "自营",
        "库存数量(万)_PR": 100.0,
        "是否超限": "否",
        "wind行业": "煤炭",
        "行业类别": "高风险行业",
        "高风险行业是否超限": "否",
        "高风险行业之和集中度限额指标值": 0.10,
        "高风险行业集中度": 0.0285,
        "高风险行业总持仓_PR": 300.0,
        "高风险行业集中度剩余额度(万)": 9700.0,
        "省份": "山西省",
        "省份类别": "高风险省份",
        "高风险省份是否超限": "否",
        "高风险省份之和集中度限额指标值": 0.10,
        "高风险省份集中度": 0.0751,
        "高风险省份总持仓_PR": 800.0,
        "高风险省份集中度剩余额度(万)": 9200.0,
        "地域集中度是否超限": "否",
        "指标值_地域集中度限额": 0.12,
        "地域集中度": 0.0171,
        "单一地域总持仓_PR": 900.0,
        "地域集中度剩余额度(万)": 11100.0,
        "是否城投债": "是",
        "城投集中度是否超限": "否",
        "指标值_城投集中度限额": 0.08,
        "城投地域集中度": 0.0157,
        "单一地域城投总持仓_PR": 700.0,
        "城投集中度剩余额度(万)": 7300.0,
    }
    exported = export_legacy_page3_category_credit_table(
        DummyLoader(stage2_credit_2=pd.DataFrame([row]))
    )

    assert exported.loc[0, "高风险行业之和集中度限额"] == "10.00%"
    assert exported.loc[0, "高风险行业集中度"] == "2.85%"
    assert exported.loc[0, "高风险省份之和集中度限额"] == "10.00%"
    assert exported.loc[0, "高风险省份集中度"] == "7.51%"
    assert exported.loc[0, "地域集中度限额"] == 0.12
    assert exported.loc[0, "地域集中度"] == "1.71%"
    assert exported.loc[0, "城投集中度限额指标值 "] == 0.08
    assert exported.loc[0, "城投地域集中度"] == "1.57%"
