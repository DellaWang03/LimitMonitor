from __future__ import annotations

import pytest

from src.pretrade.master_derivations import (
    derive_bond_category,
    derive_classifications,
    derive_isin,
    derive_issuer_type,
)


@pytest.mark.parametrize(
    ("bond_type2", "expected"),
    [
        ("地方政府债", ("利率债", "利率债")),
        ("国债", ("利率债", "利率债")),
        ("政策银行债", ("利率债", "利率债")),
        ("政府支持机构债", ("利率债", "利率债")),
        ("可转债", ("信用债", "转债交债")),
        ("可交换债", ("信用债", "转债交债")),
        ("证监会主管ABS", ("信用债", "信用债")),
        ("资产支持证券", ("信用债", "信用债")),
    ],
)
def test_derive_classifications_matches_source_workbook(
    bond_type2: str, expected: tuple[str, str]
) -> None:
    assert derive_classifications(bond_type2) == expected


def test_derive_bond_category_keeps_source_ifs_precedence() -> None:
    assert derive_bond_category("利率债", "是", "房地产开发", "国企") == "利率债"
    assert derive_bond_category("信用债", "是", "房地产开发", "国企") == "城投债"
    assert derive_bond_category("信用债", "否", "房地产开发", "国企") == "地产债"
    assert derive_bond_category("信用债", "否", "公用事业", "国企") == "国企债"
    assert derive_bond_category("信用债", "否", "公用事业", "非国企") == "民企债"


def test_derive_issuer_type_matches_nature1_formula() -> None:
    assert derive_issuer_type("地方国有企业") == "国企"
    assert derive_issuer_type("民营企业") == "非国企"


@pytest.mark.parametrize(
    ("bond_code", "wind_isin", "expected"),
    [
        ("102480811.IB", "CND1000TEST", None),
        ("110073.SH", "CND1000TEST", None),
        ("159636.SZ", "CND1000TEST", None),
        ("UULB.SG", "SG0000000001", "SG0000000001"),
        ("UULB.SG", 0, None),
    ],
)
def test_derive_isin_preserves_domestic_blank_rule(
    bond_code: str, wind_isin: object, expected: str | None
) -> None:
    assert derive_isin(bond_code, wind_isin) == expected
