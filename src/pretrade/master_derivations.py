"""复现债券持仓底稿中不依赖限额计算的确定性主数据公式。"""

from __future__ import annotations

from typing import Any


_RATE_BOND_TYPES = frozenset({"地方政府债", "国债", "政策银行债", "政府支持机构债"})
_CONVERTIBLE_BOND_TYPES = frozenset({"可交换债", "可转债"})
_REAL_ESTATE_INDUSTRIES = frozenset(
    {"房地产开发", "房地产经营公司", "房地产服务", "多样化房地产活动"}
)
_DOMESTIC_MARKETS = frozenset({"IB", "SH", "SZ"})


def derive_classifications(bond_type2: str) -> tuple[str, str]:
    """返回底稿“债券分类”和“债券分类2”的同一组公式结果。"""

    base_classification = "利率债" if bond_type2 in _RATE_BOND_TYPES else "信用债"
    if base_classification == "利率债":
        return base_classification, "利率债"
    if bond_type2 in _CONVERTIBLE_BOND_TYPES:
        return base_classification, "转债交债"
    return base_classification, "信用债"


def derive_issuer_type(nature1: str) -> str:
    """复现 IF(FIND(\"国有企业\", Nature1), \"国企\", \"非国企\")。"""

    return "国企" if "国有企业" in nature1 else "非国企"


def derive_bond_category(
    base_classification: str,
    is_city_investment_bond: str,
    wind_industry: str,
    issuer_type: str,
) -> str:
    """按上线 IFS 的原始顺序产生“债券类别”。"""

    if base_classification == "利率债":
        return "利率债"
    if is_city_investment_bond == "是":
        return "城投债"
    if wind_industry in _REAL_ESTATE_INDUSTRIES:
        return "地产债"
    if issuer_type == "国企":
        return "国企债"
    return "民企债"


def derive_isin(bond_code: str, wind_isin: Any) -> str | None:
    """底稿只为境外债保留 ISIN，境内债明确留空。"""

    normalized_code = str(bond_code).strip().upper()
    market = normalized_code.rsplit(".", maxsplit=1)[-1] if "." in normalized_code else ""
    if market in _DOMESTIC_MARKETS:
        return None
    normalized_isin = _optional_text(wind_isin)
    return normalized_isin if normalized_isin != "0" else None


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text and text.lower() not in {"nan", "none", "null", "nat"} else None
