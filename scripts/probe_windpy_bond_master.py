#!/usr/bin/env python3
"""对一只债券执行一次、无持久化的 WindPy 字段能力探针。"""

from __future__ import annotations

import argparse
import json
from math import isnan
import sys
from typing import Any, Sequence

import pandas as pd


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bond-code", required=True)
    parser.add_argument("--field", action="append", default=[])
    parser.add_argument("--execute", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _build_parser().parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)

    bond_code = args.bond_code.strip()
    fields = [field.strip() if isinstance(field, str) else "" for field in args.field]
    if not bond_code:
        return _argument_error("--bond-code 不能为空")
    if any(not field for field in fields):
        return _argument_error("--field 不能为空")
    if not args.execute:
        _write_json(
            {"executed": False, "bond_code": bond_code, "fields": fields}
        )
        return 0
    if not fields:
        return _argument_error("--execute 时至少提供一个 --field")

    try:
        gateway = _import_wind()
    except Exception as exc:
        return _failure(bond_code, fields, f"WindPy 导入失败: {type(exc).__name__}")
    try:
        if _error_code(gateway.start()) != 0:
            return _failure(bond_code, fields, "WindPy 启动失败")
        response = gateway.wss(bond_code, ",".join(fields), usedf=True)
        error_code, record = _single_record(response)
    except Exception as exc:
        return _failure(bond_code, fields, f"Wind 请求失败: {type(exc).__name__}")
    if error_code != 0:
        return _failure(bond_code, fields, f"Wind 返回错误码: {error_code}")
    if record is None:
        return _failure(bond_code, fields, "Wind 主数据返回记录数不是 1")

    _write_json(
        {
            "executed": True,
            "bond_code": bond_code,
            "record_count": 1,
            "fields": [_field_capability(record, field) for field in fields],
        }
    )
    return 0


def _import_wind() -> Any:
    from WindPy import w  # type: ignore[import-not-found]

    return w


def _argument_error(message: str) -> int:
    print(message, file=sys.stderr)
    return 2


def _failure(bond_code: str, fields: list[str], error: str) -> int:
    _write_json(
        {
            "executed": True,
            "bond_code": bond_code,
            "fields": fields,
            "error": error,
        }
    )
    return 1


def _write_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _error_code(value: Any) -> int:
    raw = getattr(value, "ErrorCode", value)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return -1


def _single_record(response: Any) -> tuple[int, dict[str, Any] | None]:
    if not isinstance(response, tuple) or len(response) != 2:
        return -1, None
    error_code = _error_code(response[0])
    if error_code != 0:
        return error_code, None
    data = response[1]
    if not isinstance(data, pd.DataFrame) or len(data) != 1:
        return error_code, None
    return error_code, {str(key): value for key, value in data.iloc[0].to_dict().items()}


def _field_capability(record: dict[str, Any], field: str) -> dict[str, Any]:
    key = next((key for key in record if key.casefold() == field.casefold()), None)
    if key is None:
        return {
            "field": field,
            "available": False,
            "raw_type": None,
            "is_null": True,
        }
    value = record[key]
    return {
        "field": field,
        "available": True,
        "raw_type": type(value).__name__,
        "is_null": _is_null(value),
    }


def _is_null(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and isnan(value):
        return True
    try:
        marker = pd.isna(value)
    except (TypeError, ValueError):
        return False
    if hasattr(marker, "item"):
        marker = marker.item()
    return bool(marker) if isinstance(marker, bool) else False


if __name__ == "__main__":
    raise SystemExit(main())
