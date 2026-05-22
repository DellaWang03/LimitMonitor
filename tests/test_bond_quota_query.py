from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.visualization.bond_quota_query import query_bond_remaining_quota


class FakeLoader:
    def __init__(
        self,
        df_1_2: pd.DataFrame,
        df_2: pd.DataFrame,
        df_1_1: pd.DataFrame | None = None,
        df_full_reg: pd.DataFrame | None = None,
        df_hy: pd.DataFrame | None = None,
        df_hy_capital: pd.DataFrame | None = None,
        high_yield_annual_limit_wan: float | None = None,
        high_yield_limit_maps: dict | None = None,
    ):
        self._df_1_1 = df_1_1 if df_1_1 is not None else pd.DataFrame()
        self._df_1_2 = df_1_2
        self._df_2 = df_2
        self._df_full_reg = df_full_reg if df_full_reg is not None else pd.DataFrame()
        self._df_hy = df_hy if df_hy is not None else pd.DataFrame()
        self._df_hy_capital = df_hy_capital if df_hy_capital is not None else pd.DataFrame()
        self._high_yield_annual_limit_wan = high_yield_annual_limit_wan
        self._high_yield_limit_maps = high_yield_limit_maps

    def load_stage1_credit_1_1(self) -> pd.DataFrame:
        return self._df_1_1.copy()

    def load_stage1_credit_1_2(self) -> pd.DataFrame:
        return self._df_1_2.copy()

    def load_stage2_credit_2(self) -> pd.DataFrame:
        return self._df_2.copy()

    def load_stage1_full_regulatory_concentration(self) -> pd.DataFrame:
        return self._df_full_reg.copy()

    def load_stage2_high_yield(self) -> pd.DataFrame:
        return self._df_hy.copy()

    def load_stage2_high_yield_capital(self) -> pd.DataFrame:
        return self._df_hy_capital.copy()

    def load_high_yield_annual_limit(self) -> float:
        if self._high_yield_annual_limit_wan is None:
            raise FileNotFoundError("missing high yield annual limit")
        return self._high_yield_annual_limit_wan

    def load_high_yield_limit_maps(self) -> dict:
        if self._high_yield_limit_maps is None:
            raise FileNotFoundError("missing high yield limit maps")
        return self._high_yield_limit_maps


def test_query_bond_remaining_quota_returns_account_results_for_multiple_accounts():
    base_date = pd.Timestamp("2026-04-27")
    df_full_reg = pd.DataFrame(
        [
            {
                "日期": base_date,
                "资产代码": "240001",
                "资产名称": "测试债A",
                "监管集中度剩余额度(万)": 90.0,
                "监管集中度是否超限": "否",
                "是否可计算": "是",
            }
        ]
    )
    df_1_2 = pd.DataFrame(
        [
            {
                "日期": base_date,
                "资产代码": "240001",
                "代码": "240001",
                "资产名称": "测试债A",
                "债务主体": "主体甲",
                "内部证券账户名称": "账户A",
                "库存数量(万)_PR": 100.0,
                "单一债券规模剩余额度(万)": 80.0,
                "单一债券是否超限": "否",
                "单一主体规模剩余额度(万)": 60.0,
                "单一主体是否超限": "否",
            },
            {
                "日期": base_date,
                "资产代码": "240001",
                "代码": "240001",
                "资产名称": "测试债A",
                "债务主体": "主体甲",
                "内部证券账户名称": "账户B",
                "库存数量(万)_PR": 200.0,
                "单一债券规模剩余额度(万)": -5.0,
                "单一债券是否超限": "是",
                "单一主体规模剩余额度(万)": 30.0,
                "单一主体是否超限": "否",
            },
        ]
    )
    df_2 = pd.DataFrame(
        [
            {
                "日期": base_date,
                "资产代码": "240001",
                "内部证券账户名称": "账户A",
                "地域集中度剩余额度(万)": 55.0,
                "地域集中度是否超限": "否",
            },
            {
                "日期": base_date,
                "资产代码": "240001",
                "内部证券账户名称": "账户B",
                "地域集中度剩余额度(万)": 25.0,
                "地域集中度是否超限": "否",
            },
        ]
    )

    result = query_bond_remaining_quota(
        FakeLoader(df_1_2, df_2, df_full_reg=df_full_reg),
        "240001",
        target_date=date(2026, 4, 27),
    )

    assert result["matched_account_count"] == 2
    assert result["result_scope"] == "account"
    assert result["selected_account_name"] == "账户B"
    assert result["final_quota_wan"] == 0.0
    assert [item["account_name"] for item in result["account_results"]] == ["账户B", "账户A"]
    assert result["bond_info"]["内部证券账户名称"] == "账户B"
    assert result["common_bond_info"]["内部证券账户名称"] == "多账户"
    assert result["account_summary"][0]["是否存在超限维度"] == "是"


def test_query_bond_remaining_quota_includes_special_limit_dimensions_from_credit_1_1():
    base_date = pd.Timestamp("2026-04-27")
    df_full_reg = pd.DataFrame(
        [
            {
                "日期": base_date,
                "资产代码": "240001",
                "资产名称": "测试债A",
                "监管集中度剩余额度(万)": 14.0,
                "监管集中度是否超限": "否",
                "是否可计算": "是",
            }
        ]
    )
    df_1_1 = pd.DataFrame(
        [
            {
                "日期": base_date,
                "资产代码": "240001",
                "代码": "240001",
                "资产名称": "测试债A",
                "债务主体": "主体甲",
                "内部证券账户名称": "账户A",
                "库存数量(万)_PR": 100.0,
                "特定主体限额剩余额度": 18.0,
                "特定主体限额是否超限": "否",
                "特定实控人限额剩余额度": 12.0,
                "特定实控人限额是否超限": "否",
            }
        ]
    )
    df_1_2 = pd.DataFrame(
        [
            {
                "日期": base_date,
                "资产代码": "240001",
                "代码": "240001",
                "资产名称": "测试债A",
                "债务主体": "主体甲",
                "内部证券账户名称": "账户A",
                "库存数量(万)_PR": 100.0,
                "单一债券规模剩余额度(万)": 80.0,
                "单一债券是否超限": "否",
            }
        ]
    )
    df_2 = pd.DataFrame(
        [
            {
                "日期": base_date,
                "资产代码": "240001",
                "内部证券账户名称": "账户A",
                "地域集中度剩余额度(万)": 55.0,
                "地域集中度是否超限": "否",
            }
        ]
    )

    result = query_bond_remaining_quota(
        FakeLoader(df_1_2, df_2, df_1_1=df_1_1, df_full_reg=df_full_reg),
        "240001",
        target_date=date(2026, 4, 27),
    )

    dim_map = {item["维度名称"]: item for item in result["dimensions"]}
    assert dim_map["监管集中度"]["剩余额度(万)"] == 14.0
    assert dim_map["特定主体限额"]["剩余额度(万)"] == 18.0
    assert dim_map["特定主体限额"]["是否超限"] == "否"
    assert dim_map["特定实控人限额"]["剩余额度(万)"] == 12.0
    assert dim_map["特定实控人限额"]["是否超限"] == "否"
    assert "监管集中度" in result["public_dimensions"]
    assert result["final_quota_wan"] == 12.0


def test_query_bond_remaining_quota_can_find_bond_only_present_in_credit_1_1_or_credit_2():
    base_date = pd.Timestamp("2026-04-27")
    df_full_reg = pd.DataFrame(
        [
            {
                "日期": base_date,
                "资产代码": "240009",
                "资产名称": "特定限额债",
                "监管集中度剩余额度(万)": 25.0,
                "监管集中度是否超限": "否",
                "是否可计算": "是",
            },
            {
                "日期": base_date,
                "资产代码": "240010",
                "资产名称": "集中度债",
                "监管集中度剩余额度(万)": 30.0,
                "监管集中度是否超限": "否",
                "是否可计算": "是",
            },
        ]
    )
    df_1_1 = pd.DataFrame(
        [
            {
                "日期": base_date,
                "资产代码": "240009",
                "代码": "240009",
                "资产名称": "特定限额债",
                "债务主体": "主体乙",
                "内部证券账户名称": "账户A",
                "库存数量(万)_PR": 88.0,
                "特定主体限额剩余额度": 20.0,
                "特定主体限额是否超限": "否",
            }
        ]
    )
    df_2 = pd.DataFrame(
        [
            {
                "日期": base_date,
                "资产代码": "240010",
                "代码": "240010",
                "资产名称": "集中度债",
                "债务主体": "主体丙",
                "内部证券账户名称": "账户B",
                "库存数量(万)_PR": 66.0,
                "地域集中度剩余额度(万)": 15.0,
                "地域集中度是否超限": "否",
            }
        ]
    )

    result_special = query_bond_remaining_quota(
        FakeLoader(pd.DataFrame(), df_2, df_1_1=df_1_1, df_full_reg=df_full_reg),
        "240009",
        target_date=date(2026, 4, 27),
    )
    assert result_special["error"] is None
    assert result_special["bond_info"]["资产名称"] == "特定限额债"
    assert result_special["final_quota_wan"] == 20.0

    result_concentration = query_bond_remaining_quota(
        FakeLoader(pd.DataFrame(), df_2, df_1_1=df_1_1, df_full_reg=df_full_reg),
        "240010",
        target_date=date(2026, 4, 27),
    )
    dim_map = {item["维度名称"]: item for item in result_concentration["dimensions"]}
    assert result_concentration["error"] is None
    assert result_concentration["bond_info"]["资产名称"] == "集中度债"
    assert dim_map["地域集中度"]["剩余额度(万)"] == 15.0
    assert result_concentration["final_quota_wan"] == 15.0


def test_query_bond_remaining_quota_supports_full_regulatory_only_bond():
    base_date = pd.Timestamp("2026-04-27")
    df_full_reg = pd.DataFrame(
        [
            {
                "日期": base_date,
                "资产代码": "999001",
                "代码": "999001",
                "资产名称": "利率债A",
                "债务主体": "财政部",
                "内部证券账户名称": "账户甲、账户乙",
                "单债总持仓_PR": 500.0,
                "监管集中度剩余额度(万)": 120.0,
                "监管集中度是否超限": "否",
                "是否可计算": "是",
            }
        ]
    )

    result = query_bond_remaining_quota(
        FakeLoader(pd.DataFrame(), pd.DataFrame(), df_full_reg=df_full_reg),
        "999001",
        target_date=date(2026, 4, 27),
    )

    dim_map = {item["维度名称"]: item for item in result["dimensions"]}
    assert result["error"] is None
    assert result["result_scope"] == "bond"
    assert result["matched_account_count"] == 0
    assert result["bond_level_result"] is not None
    assert result["bond_info"]["资产名称"] == "利率债A"
    assert result["bond_info"]["内部证券账户名称"] == "不区分账户"
    assert dim_map["监管集中度"]["剩余额度(万)"] == 120.0
    assert result["final_quota_wan"] == 120.0


def test_query_bond_remaining_quota_maps_alias_asset_code_to_regulatory_entity():
    base_date = pd.Timestamp("2026-04-27")
    df_full_reg = pd.DataFrame(
        [
            {
                "日期": base_date,
                "资产代码": "2080278.IB",
                "代码": "2080278.IB",
                "资产名称": "20邹城利民债",
                "债务主体": "邹城市利民建设发展集团有限公司",
                "主证券代码_标准": "2080278.IB",
                "监管集中度剩余额度(万)": 3070.0,
                "监管集中度是否超限": "否",
                "是否可计算": "是",
            }
        ]
    )
    df_1_2 = pd.DataFrame(
        [
            {
                "日期": base_date,
                "资产代码": "152592.SH",
                "代码": "152592.SH",
                "资产名称": "20利民债",
                "债务主体": "邹城市利民建设发展集团有限公司",
                "内部证券账户名称": "账户A",
                "主证券代码_标准": "2080278.IB",
                "库存数量(万)_PR": 80.0,
                "单一债券规模剩余额度(万)": 5000.0,
                "单一债券是否超限": "否",
            }
        ]
    )
    df_2 = pd.DataFrame(
        [
            {
                "日期": base_date,
                "资产代码": "152592.SH",
                "代码": "152592.SH",
                "资产名称": "20利民债",
                "债务主体": "邹城市利民建设发展集团有限公司",
                "内部证券账户名称": "账户A",
                "主证券代码": "2080278.ib",
                "地域集中度剩余额度(万)": 4000.0,
                "地域集中度是否超限": "否",
            }
        ]
    )

    result = query_bond_remaining_quota(
        FakeLoader(df_1_2, df_2, df_full_reg=df_full_reg),
        "152592.SH",
        target_date=date(2026, 4, 27),
    )

    dim_map = {item["维度名称"]: item for item in result["dimensions"]}
    assert result["error"] is None
    assert result["result_scope"] == "account"
    assert "监管集中度" in result["public_dimensions"]
    assert dim_map["监管集中度"]["剩余额度(万)"] == 3070.0
    assert result["final_quota_wan"] == 3070.0


def test_query_bond_remaining_quota_maps_isin_only_entity_for_regulatory_constraint():
    base_date = pd.Timestamp("2026-04-27")
    df_full_reg = pd.DataFrame(
        [
            {
                "日期": base_date,
                "资产代码": "REP001",
                "代码": "REP001",
                "资产名称": "离岸债代表码",
                "债务主体": "主体离岸",
                "ISIN码": "XS1234567890",
                "监管集中度剩余额度(万)": 40.0,
                "监管集中度是否超限": "否",
                "是否可计算": "是",
            }
        ]
    )
    df_1_2 = pd.DataFrame(
        [
            {
                "日期": base_date,
                "资产代码": "85053.HK",
                "代码": "85053.HK",
                "资产名称": "离岸债A",
                "债务主体": "主体离岸",
                "内部证券账户名称": "账户A",
                "ISIN码": "XS1234567890",
                "库存数量(万)_PR": 10.0,
                "单一债券规模剩余额度(万)": 80.0,
                "单一债券是否超限": "否",
            }
        ]
    )
    df_2 = pd.DataFrame(
        [
            {
                "日期": base_date,
                "资产代码": "85053.HK",
                "代码": "85053.HK",
                "资产名称": "离岸债A",
                "债务主体": "主体离岸",
                "内部证券账户名称": "账户A",
                "ISIN码": "XS1234567890",
                "地域集中度剩余额度(万)": 60.0,
                "地域集中度是否超限": "否",
            }
        ]
    )

    result = query_bond_remaining_quota(
        FakeLoader(df_1_2, df_2, df_full_reg=df_full_reg),
        "85053.HK",
        target_date=date(2026, 4, 27),
    )

    dim_map = {item["维度名称"]: item for item in result["dimensions"]}
    assert result["error"] is None
    assert "监管集中度" in result["public_dimensions"]
    assert dim_map["监管集中度"]["剩余额度(万)"] == 40.0
    assert result["final_quota_wan"] == 40.0


def test_query_bond_remaining_quota_includes_high_yield_specific_limits():
    base_date = pd.Timestamp("2026-04-27")
    df_full_reg = pd.DataFrame(
        [
            {
                "日期": base_date,
                "资产代码": "HY001",
                "资产名称": "高收益债A",
                "监管集中度剩余额度(万)": 600.0,
                "监管集中度是否超限": "否",
                "是否可计算": "是",
            }
        ]
    )
    df_hy = pd.DataFrame(
        [
            {
                "日期": base_date,
                "资产代码": "HY001",
                "代码": "HY001",
                "资产名称": "高收益债A",
                "债务主体": "主体高收",
                "内部证券账户名称": "高收益账户",
                "库存数量(万)_PR": 300.0,
            },
            {
                "日期": base_date,
                "资产代码": "HY002",
                "代码": "HY002",
                "资产名称": "高收益债B",
                "债务主体": "主体高收",
                "内部证券账户名称": "高收益账户",
                "库存数量(万)_PR": 250.0,
            },
        ]
    )
    df_hy_capital = pd.DataFrame(
        [
            {
                "日期": base_date,
                "账户": "高收益账户",
                "简称": "高收益债A",
                "代码": "HY001",
                "全价成本(元)": 4000000.0,
            }
        ]
    )
    result = query_bond_remaining_quota(
        FakeLoader(
            pd.DataFrame(),
            pd.DataFrame(),
            df_full_reg=df_full_reg,
            df_hy=df_hy,
            df_hy_capital=df_hy_capital,
            high_yield_annual_limit_wan=500.0,
            high_yield_limit_maps={
                "bond_limits": {"__default__": 1000.0, "高收益债A": 350.0},
                "entity_limits": {"__default__": 1200.0, "主体高收": 800.0},
            },
        ),
        "HY001",
        target_date=date(2026, 4, 27),
    )

    dim_map = {item["维度名称"]: item for item in result["dimensions"]}
    assert result["error"] is None
    assert "高收益年度限额" in result["public_dimensions"]
    assert dim_map["高收益年度限额"]["剩余额度(万)"] == 100.0
    assert dim_map["高收益单债限额"]["剩余额度(万)"] == 50.0
    assert dim_map["高收益主体限额"]["剩余额度(万)"] == 250.0
    assert dim_map["监管集中度"]["剩余额度(万)"] == 600.0
    assert result["final_quota_wan"] == 50.0


def test_query_bond_remaining_quota_prefers_persisted_high_yield_results():
    base_date = pd.Timestamp("2026-04-27")
    df_hy = pd.DataFrame(
        [
            {
                "日期": base_date,
                "资产代码": "HY003",
                "代码": "HY003",
                "资产名称": "高收益债C",
                "债务主体": "主体高收C",
                "内部证券账户名称": "高收益账户",
                "库存数量(万)_PR": 120.0,
                "高收益单债剩余额度(万)": 25.0,
                "高收益单债是否超限": "否",
                "高收益主体剩余额度(万)": 40.0,
                "高收益主体是否超限": "否",
            }
        ]
    )
    df_hy_capital = pd.DataFrame(
        [
            {
                "日期": base_date,
                "账户": "高收益账户",
                "简称": "高收益债C",
                "代码": "HY003",
                "高收益年度限额剩余额度(万)": 80.0,
                "高收益年度限额是否超限": "否",
            }
        ]
    )

    result = query_bond_remaining_quota(
        FakeLoader(
            pd.DataFrame(),
            pd.DataFrame(),
            df_hy=df_hy,
            df_hy_capital=df_hy_capital,
        ),
        "HY003",
        target_date=date(2026, 4, 27),
    )

    dim_map = {item["维度名称"]: item for item in result["dimensions"]}
    assert result["error"] is None
    assert dim_map["高收益年度限额"]["剩余额度(万)"] == 80.0
    assert dim_map["高收益单债限额"]["剩余额度(万)"] == 25.0
    assert dim_map["高收益主体限额"]["剩余额度(万)"] == 40.0
    assert result["final_quota_wan"] == 25.0


def test_query_bond_remaining_quota_reports_ambiguous_name_matches():
    base_date = pd.Timestamp("2026-04-27")
    df_1_2 = pd.DataFrame(
        [
            {
                "日期": base_date,
                "资产代码": "240001",
                "代码": "240001",
                "资产名称": "测试债",
                "债务主体": "主体甲",
                "内部证券账户名称": "账户A",
                "库存数量(万)_PR": 100.0,
            },
            {
                "日期": base_date,
                "资产代码": "240002",
                "代码": "240002",
                "资产名称": "测试债增强版",
                "债务主体": "主体乙",
                "内部证券账户名称": "账户B",
                "库存数量(万)_PR": 100.0,
            },
        ]
    )

    result = query_bond_remaining_quota(
        FakeLoader(df_1_2, pd.DataFrame()),
        "测试",
        target_date=date(2026, 4, 27),
    )

    assert result["error"] is None
    assert "匹配到多只债券" in result["message"]
    assert len(result["candidates"]) == 2


def test_query_bond_remaining_quota_fails_loudly_when_core_source_unavailable():
    base_date = pd.Timestamp("2026-04-27")

    class BrokenLoader(FakeLoader):
        def load_stage2_credit_2(self) -> pd.DataFrame:  # type: ignore[override]
            raise RuntimeError("stage2_credit_2 unavailable")

    df_1_2 = pd.DataFrame(
        [
            {
                "日期": base_date,
                "资产代码": "240001",
                "代码": "240001",
                "资产名称": "测试债A",
                "债务主体": "主体甲",
                "内部证券账户名称": "账户A",
                "库存数量(万)_PR": 100.0,
            }
        ]
    )
    df_full_reg = pd.DataFrame(
        [
            {
                "日期": base_date,
                "资产代码": "240001",
                "资产名称": "测试债A",
                "监管集中度剩余额度(万)": 90.0,
                "监管集中度是否超限": "否",
                "是否可计算": "是",
            }
        ]
    )

    result = query_bond_remaining_quota(
        BrokenLoader(df_1_2, pd.DataFrame(), df_full_reg=df_full_reg),
        "240001",
        target_date=date(2026, 4, 27),
    )

    assert "关键数据源加载失败" in result["error"]
    assert any("信用债2加载失败" in item for item in result["data_health"]["errors"])
