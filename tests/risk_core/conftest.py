from __future__ import annotations

from collections.abc import Callable

import pandas as pd
import pytest

from src.stage1.stage1_limit_detail import LimitDetailCalculator
from src.stage1.stage1_processor import Stage1Processor
from src.stage2.stage2_processor import Stage2Processor


@pytest.fixture
def business_date() -> pd.Timestamp:
    return pd.Timestamp("2026-05-20")


@pytest.fixture
def credit_row(business_date: pd.Timestamp) -> Callable[..., dict]:
    """Return a factory using the exact production column labels."""

    def factory(**overrides) -> dict:
        row = {
            "日期": business_date,
            "金融资产会计属性": "交易性金融资产",
            "部门": "自营",
            "内部证券账户名称": "自营部交易性",
            "资产代码": "123456.IB",
            "ISIN码": "CN0000000001",
            "资产名称": "普通信用债",
            "债券分类2": "信用债",
            "债券类型1": "一般企业债",
            "主证券代码": "123456.IB",
            "主证券名称": "普通信用债",
            "库存数量(万)_PR": 100.0,
            "债券余额(亿)": 10.0,
            "发行人类型": "国企",
            "债务主体": "普通主体",
            "债务主体wind代码": "F1000001.00",
            "实际控制人名称": "原始实控人",
            "实际控制人名称_修正": "修正实控人",
            "担保人": None,
            "担保人wind代码": None,
            "是否城投债": "否",
            "债券类别": "产业债",
            "wind行业": "制造业",
            "省份": "浙江",
            "合并辅助列": "",
        }
        row.update(overrides)
        return row

    return factory


@pytest.fixture
def stage1_processor(tmp_path) -> Stage1Processor:
    return Stage1Processor(
        data_dir=tmp_path / "data",
        output_dir=tmp_path / "stage1",
        stage0_output_dir=tmp_path / "stage0",
    )


@pytest.fixture
def stage2_processor(tmp_path) -> Stage2Processor:
    return Stage2Processor(
        data_dir=tmp_path / "data",
        output_dir=tmp_path / "stage2",
        stage0_output_dir=tmp_path / "stage0",
        stage1_output_dir=tmp_path / "stage1",
    )


@pytest.fixture
def limit_calculator() -> Callable[[dict[str, pd.DataFrame]], LimitDetailCalculator]:
    def factory(cache: dict[str, pd.DataFrame]) -> LimitDetailCalculator:
        return LimitDetailCalculator(cache, regulatory_concentration_limit=0.16)

    return factory
