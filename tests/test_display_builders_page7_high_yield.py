from __future__ import annotations

import pandas as pd

from src.visualization.display_builders import build_page7_high_yield_views


class DummyHighYieldLoader:
    def __init__(self, high_yield: pd.DataFrame, capital: pd.DataFrame) -> None:
        self._high_yield = high_yield
        self._capital = capital

    def load_stage2_high_yield(self) -> pd.DataFrame:
        return self._high_yield.copy()

    def load_stage2_high_yield_capital(self) -> pd.DataFrame:
        return self._capital.copy()

    def load_high_yield_annual_limit(self) -> float:
        return 10000.0


def test_high_yield_summaries_show_warning_at_or_above_80_percent_usage():
    date = pd.Timestamp("2026-06-22")
    high_yield = pd.DataFrame(
        [
            {
                "日期": date,
                "资产代码": "OVER.IB",
                "资产名称": "超限高收益债",
                "债务主体": "超限主体",
                "高收益单债归并键": "OVER.IB",
                "高收益单债总持仓(万)": 110.0,
                "高收益单债限额(万)": 100.0,
                "高收益单债剩余额度(万)": -10.0,
                "高收益单债是否超限": "否",
                "高收益主体总持仓(万)": 110.0,
                "高收益主体限额(万)": 100.0,
                "高收益主体剩余额度(万)": -10.0,
                "高收益主体是否超限": "否",
            },
            {
                "日期": date,
                "资产代码": "WARN.IB",
                "资产名称": "预警高收益债",
                "债务主体": "预警主体",
                "高收益单债归并键": "WARN.IB",
                "高收益单债总持仓(万)": 80.0,
                "高收益单债限额(万)": 100.0,
                "高收益单债剩余额度(万)": 20.0,
                "高收益单债是否超限": "否",
                "高收益主体总持仓(万)": 80.0,
                "高收益主体限额(万)": 100.0,
                "高收益主体剩余额度(万)": 20.0,
                "高收益主体是否超限": "否",
            },
            {
                "日期": date,
                "资产代码": "OK.IB",
                "资产名称": "正常高收益债",
                "债务主体": "正常主体",
                "高收益单债归并键": "OK.IB",
                "高收益单债总持仓(万)": 79.99,
                "高收益单债限额(万)": 100.0,
                "高收益单债剩余额度(万)": 20.01,
                "高收益单债是否超限": "否",
                "高收益主体总持仓(万)": 79.99,
                "高收益主体限额(万)": 100.0,
                "高收益主体剩余额度(万)": 20.01,
                "高收益主体是否超限": "否",
            },
        ]
    )
    capital = pd.DataFrame(
        [
            {
                "日期": date,
                "账户": "高收益账户",
                "简称": "高收益债",
                "代码": "HY.IB",
                "持仓面额(元)": 1000000.0,
                "全价成本(元)": 1000000.0,
                "年度限额(万)": 10000.0,
                "高收益年度总投资本金(万)": 100.0,
                "高收益年度限额剩余额度(万)": 9900.0,
                "高收益年度限额是否超限": "否",
            }
        ]
    )

    views = build_page7_high_yield_views(DummyHighYieldLoader(high_yield, capital))

    asset_status = dict(
        zip(
            views["tables"]["tab2_asset_summary"]["资产名称"],
            views["tables"]["tab2_asset_summary"]["是否超限"],
        )
    )
    issuer_status = dict(
        zip(
            views["tables"]["tab2_issuer_summary"]["债务主体"],
            views["tables"]["tab2_issuer_summary"]["是否超限"],
        )
    )
    assert asset_status == {
        "超限高收益债": "是",
        "预警高收益债": "预警",
        "正常高收益债": "否",
    }
    assert issuer_status == {
        "超限主体": "是",
        "预警主体": "预警",
        "正常主体": "否",
    }
