"""Shared helpers exposed lazily so pure consumers do not load I/O adapters."""

from importlib import import_module
from typing import Any


_LAZY_IMPORTS = {
    "WindCodeResolver": (".wind_code_resolver", "WindCodeResolver"),
    "AccessDatabaseReader": (".access_reader", "AccessDatabaseReader"),
    "WindCodeExcelHelper": (".wind_code_excel_helper", "WindCodeExcelHelper"),
    "LoggerSetup": (".logger_setup", "LoggerSetup"),
    "ProvinceNormalizer": (".province_normalizer", "ProvinceNormalizer"),
    "normalize_security_code_series": (
        ".security_code_normalizer",
        "normalize_security_code_series",
    ),
    "SINGLE_BOND_GROUP_KEY_COL": (
        ".bond_grouping",
        "SINGLE_BOND_GROUP_KEY_COL",
    ),
    "SINGLE_BOND_GROUP_KEY_SOURCE_COL": (
        ".bond_grouping",
        "SINGLE_BOND_GROUP_KEY_SOURCE_COL",
    ),
    "ensure_single_bond_group_key": (
        ".bond_grouping",
        "ensure_single_bond_group_key",
    ),
}


def __getattr__(name: str) -> Any:
    try:
        module_name, attribute_name = _LAZY_IMPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
    value = getattr(import_module(module_name, __name__), attribute_name)
    globals()[name] = value
    return value

__all__ = [
    'WindCodeResolver',
    'AccessDatabaseReader',
    'WindCodeExcelHelper',
    'LoggerSetup',
    'ProvinceNormalizer',
    'normalize_security_code_series',
    'SINGLE_BOND_GROUP_KEY_COL',
    'SINGLE_BOND_GROUP_KEY_SOURCE_COL',
    'ensure_single_bond_group_key',
]
