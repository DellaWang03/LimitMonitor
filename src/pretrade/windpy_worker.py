"""macOS 交易前 WindPy 的短生命周期进程入口。"""

from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from math import isfinite
import sys
from typing import Any, Mapping

from .windpy_master import (
    DEFAULT_WIND_FIELDS,
    _WINDPY_WORKER_RESULT_PREFIX,
    _import_windpy,
    _parse_wss_response,
    _start_gateway,
)


def _query(bond_code: str) -> dict[str, Any]:
    module = _import_windpy()
    gateway = getattr(module, "w", None) if module is not None else None
    if gateway is None:
        return {"error_code": 1, "rows": [], "reason": "WindPy 不可用"}

    try:
        if _start_gateway(gateway) != 0:
            return {"error_code": 1, "rows": [], "reason": "WindPy 启动失败"}
        response = gateway.wss(bond_code, DEFAULT_WIND_FIELDS, usedf=True)
    except Exception as exc:
        return {
            "error_code": 1,
            "rows": [],
            "reason": f"Wind 请求失败: {type(exc).__name__}",
        }

    error_code, rows = _parse_wss_response(response)
    return {
        "error_code": error_code,
        "rows": [_json_safe_mapping(row) for row in rows],
        "reason": None,
    }


def _json_safe_mapping(row: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): _json_safe(value) for key, value in row.items()}


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if isfinite(value) else None
    scalar = getattr(value, "item", None)
    if callable(scalar):
        try:
            return _json_safe(scalar())
        except (TypeError, ValueError):
            pass
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        try:
            return isoformat()
        except (TypeError, ValueError):
            pass
    return str(value)


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) != 1:
        payload = {
            "error_code": 1,
            "rows": [],
            "reason": "Wind 子进程参数无效",
        }
        exit_code = 2
    else:
        captured_stdout = io.StringIO()
        with redirect_stdout(captured_stdout):
            payload = _query(arguments[0])
        exit_code = 0

    print(
        _WINDPY_WORKER_RESULT_PREFIX
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        flush=True,
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
