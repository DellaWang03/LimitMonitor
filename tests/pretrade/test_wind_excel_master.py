from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from src.pretrade.wind_excel_master import ExcelWindMasterGateway


@dataclass
class FakeFormulaEvaluator:
    responses: dict[str, object]
    calls: list[dict[str, str]] = field(default_factory=list)

    def evaluate(self, formulas: dict[str, str]) -> dict[str, object]:
        self.calls.append(formulas)
        return {name: self.responses.get(formula) for name, formula in formulas.items()}


def test_initial_excel_formulas_match_source_workbook() -> None:
    evaluator = FakeFormulaEvaluator(
        {
            '=b_info_anchorbond("184072.SH")': "2180399.IB",
            '=b_issuer_windindustry("184072.SH",4)': "公用事业",
            '=s_info_province("184072.SH")': "浙江省",
            '=To_WindCode("测试发行人")': "F1000001.00",
            '=To_WindCode("测试担保人")': "F1000002.00",
        }
    )

    values = ExcelWindMasterGateway(evaluator).resolve_initial(
        "184072.SH", issuer_name="测试发行人", guarantor_name="测试担保人"
    )

    assert values.main_security_code == "2180399.IB"
    assert values.wind_industry == "公用事业"
    assert values.province == "浙江省"
    assert values.issuer_wind_code == "F1000001.00"
    assert values.guarantor_wind_code == "F1000002.00"
    assert evaluator.calls == [
        {
            "main_security_code": '=b_info_anchorbond("184072.SH")',
            "wind_industry": '=b_issuer_windindustry("184072.SH",4)',
            "province": '=s_info_province("184072.SH")',
            "issuer_wind_code": '=To_WindCode("测试发行人")',
            "guarantor_wind_code": '=To_WindCode("测试担保人")',
        }
    ]


def test_anchor_attributes_use_anchor_code_and_snapshot_business_date() -> None:
    evaluator = FakeFormulaEvaluator(
        {
            '=b_info_name("UULB.SG")': 0,
            '=b_info_outstandingbalance("UULB.SG","2026-07-10")': 0,
        }
    )

    values = ExcelWindMasterGateway(evaluator).resolve_anchor_attributes(
        "UULB.SG", pd.Timestamp("2026-07-10")
    )

    assert values.main_security_name == 0
    assert values.outstanding_balance_yi == 0
    assert evaluator.calls == [
        {
            "main_security_name": '=b_info_name("UULB.SG")',
            "outstanding_balance_yi": '=b_info_outstandingbalance("UULB.SG","2026-07-10")',
        }
    ]


def test_province_static_overrides_do_not_call_excel() -> None:
    evaluator = FakeFormulaEvaluator({})

    values = ExcelWindMasterGateway(evaluator).resolve_initial(
        "292680009.IB", issuer_name=None, guarantor_name=None
    )

    assert values.province == "海外"
    assert evaluator.calls == [
        {
            "main_security_code": '=b_info_anchorbond("292680009.IB")',
            "wind_industry": '=b_issuer_windindustry("292680009.IB",4)',
        }
    ]


def test_excel_zero_and_error_have_distinct_source_semantics() -> None:
    evaluator = FakeFormulaEvaluator(
        {
            '=b_info_anchorbond("X.IB")': 0,
            '=b_issuer_windindustry("X.IB",4)': "#N/A",
            '=s_info_province("X.IB")': 0,
            '=To_WindCode("担保人")': 0,
        }
    )

    values = ExcelWindMasterGateway(evaluator).resolve_initial(
        "X.IB", issuer_name=None, guarantor_name="担保人"
    )

    assert values.main_security_code == 0
    assert values.wind_industry is None
    assert values.province == 0
    assert values.guarantor_wind_code == 0
