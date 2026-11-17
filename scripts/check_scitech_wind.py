#!/usr/bin/env python3
"""独立、只读的科创债 WindPy 核验脚本（仅依赖标准库和本机 WindPy）。

运行：python check_scitech_wind.py
预览：python check_scitech_wind.py --dry-run
指定 WindPy：python check_scitech_wind.py --windpy-path "D:\\Wind\\Wind.NET.Client\\WindNET"

不导入本项目业务模块，不读取持仓文件，不写数据库，不修改 Wind 安装或配置。
只查询证券代码和字段；不上传持仓金额。结果保存在脚本旁的 wind_scitech_reports。
截图中的 Excel 字段和去掉前缀的候选 WSS 字段分别探测，绝不静默替换字段。
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import importlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys


PREFIX = "SCITECH_WIND_EVENT="
REFERENCE_CODES = (
    "132026.SH", "137198.SH", "137206.SH", "137207.SH", "117249.SZ",
    "117236.SZ", "137201.SH", "117219.SZ", "117252.SZ", "102480811.IB",
    "102684208.IB", "102690088.IB", "520419.SZ", "245067.SH", "246294.SH",
    "246232.SH", "246233.SH", "244776.SH", "281082.SH", "283625.SH", "821032.BJ",
)
CONTROL_CODE = "010706.SH"  # 07国债06，非科创债对照；并非用户持仓金额。
ALL_CODES = REFERENCE_CODES + (CONTROL_CODE,)
DEFAULT_FIELDS = ("b_info_scitechbondornot", "scitechbondornot")


def safe_value(value):
    if isinstance(value, dict):
        return {str(key): safe_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [safe_value(item) for item in value]
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if hasattr(value, "item"):
        return safe_value(value.item())
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def emit(step, **payload):
    print(PREFIX + json.dumps(safe_value({"step": step, **payload}), ensure_ascii=False,
                              allow_nan=False), flush=True)


def parse_response(response, requested_field):
    """读取 Wind 原生 WindData，保留字段、证券代码、原始值及类型。"""
    error_code = getattr(response, "ErrorCode", None)
    fields = list(getattr(response, "Fields", None) or [])
    codes = list(getattr(response, "Codes", None) or [])
    data = getattr(response, "Data", None)
    result = {
        "requested_field": requested_field, "error_code": error_code,
        "returned_fields": fields, "returned_codes": codes,
        "raw_data": safe_value(data), "records": [], "shape_error": None,
    }
    if error_code != 0:
        return result
    if (len(fields) != 1 or not isinstance(data, (list, tuple)) or len(data) != 1
            or not isinstance(data[0], (list, tuple)) or len(data[0]) != len(codes)):
        result["shape_error"] = "单字段 WSS 返回结构不完整或维度不匹配"
        return result
    result["records"] = [
        {"code": str(code).strip().upper(), "returned_field": str(fields[0]),
         "raw_value": safe_value(value), "raw_type": type(value).__name__,
         "is_missing": safe_value(value) is None or str(value).strip() == ""}
        for code, value in zip(codes, data[0])
    ]
    return result


def normalized_flag(value):
    """仅用于对照诊断；不将空值、未知值或错误当作“否”。"""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return True if value == 1 else False if value == 0 else None
    text = str(value).strip().upper()
    if text in {"是", "Y", "YES", "TRUE", "1"}:
        return True
    if text in {"否", "N", "NO", "FALSE", "0"}:
        return False
    return None


def summarize_query(query):
    records = query["records"]
    counts = Counter(r["code"] for r in records)
    complete_codes = set(counts) == set(ALL_CODES) and all(n == 1 for n in counts.values())
    complete = (query["error_code"] == 0 and query["shape_error"] is None
                and complete_codes and all(not r["is_missing"] for r in records))
    comparisons = []
    for row in records:
        expected = False if row["code"] == CONTROL_CODE else True if row["code"] in REFERENCE_CODES else None
        actual = normalized_flag(row["raw_value"])
        comparisons.append({"code": row["code"], "raw_value": row["raw_value"],
                            "expected_from_reference": expected,
                            "normalized_for_comparison": actual,
                            "matches_reference": expected is not None and actual is expected})
    return {
        "field": query["requested_field"], "error_code": query["error_code"],
        "complete": complete,
        "sample_check_passed": complete and all(r["matches_reference"] for r in comparisons),
        "missing_codes": sorted(set(ALL_CODES) - set(counts)),
        "raw_value_counts": dict(Counter(json.dumps(r["raw_value"], ensure_ascii=False) for r in records)),
        "comparisons": comparisons,
    }


def load_wind(path):
    # 用户明确传入的路径优先；否则使用已安装模块，再尝试官方 macOS 路径。
    if path:
        directory = Path(path).expanduser().resolve()
        if not directory.is_dir():
            raise ValueError("--windpy-path 应为包含 WindPy.py 的文件夹")
        sys.path.insert(0, str(directory))
    try:
        return importlib.import_module("WindPy")
    except ModuleNotFoundError as exc:
        if exc.name != "WindPy" or path:
            raise
        mac_path = Path("/Applications/Wind API.app/Contents/python")
        if not mac_path.is_dir():
            raise
        sys.path.insert(0, str(mac_path))
        return importlib.import_module("WindPy")


def worker(args):
    try:
        emit("environment", python=sys.version, platform=sys.platform)
        emit("import_start")
        module = load_wind(args.windpy_path)
        wind = module.w
        emit("import_done", module_path=getattr(module, "__file__", None))
        connected = bool(wind.isconnected())
        emit("connection", connected=connected)
        if not connected:
            emit("start_begin", wait_seconds=20)
            started = wind.start(waitTime=20)
            error = getattr(started, "ErrorCode", started)
            emit("start_result", error_code=error)
            if error != 0:
                emit("failed", reason="Wind 启动失败，请检查登录、网络及 API 权限")
                return 1
        for field in ["sec_name", *args.fields]:
            emit("query_begin", field=field, code_count=len(ALL_CODES))
            try:
                # 使用原生 WindData，避免额外依赖 pandas，也保留原始值类型。
                response = wind.wss(",".join(ALL_CODES), field)
                emit("query_result", **parse_response(response, field))
            except Exception as exc:
                emit("query_exception", field=field, error_type=type(exc).__name__, reason=str(exc))
        emit("finished")
        return 0
    except Exception as exc:
        emit("failed", error_type=type(exc).__name__, reason=str(exc))
        return 1


def parser():
    result = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    result.add_argument("--field", action="append", dest="fields", help="替换默认字段；可重复指定")
    result.add_argument("--windpy-path", help="包含 WindPy.py 的本地文件夹（通常不需要）")
    result.add_argument("--timeout", type=int, default=90, help="子进程总超时秒数，默认 90")
    result.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parent / "wind_scitech_reports")
    result.add_argument("--dry-run", action="store_true", help="仅显示查询计划，不导入 WindPy、不写文件")
    result.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    return result


def main(argv=None):
    cli = parser()
    args = cli.parse_args(argv)
    args.fields = list(dict.fromkeys(field.strip() for field in (args.fields or DEFAULT_FIELDS)))
    if args.timeout <= 0 or any(not f or "," in f or ";" in f for f in args.fields):
        cli.error("超时必须大于零；每个 --field 只能指定一个非空字段")
    if args.dry_run:
        print(json.dumps({"executed": False, "codes": ALL_CODES,
                          "fields": ["sec_name", *args.fields],
                          "timeout_seconds": args.timeout}, ensure_ascii=False, indent=2))
        return 0
    if args.worker:
        return worker(args)

    stamp = datetime.now(timezone(timedelta(hours=8))).strftime("%Y%m%d_%H%M%S_%f")
    output = args.output_dir.expanduser().resolve() / stamp
    output.mkdir(parents=True, exist_ok=False)
    log_path = output / "wind_probe.log"
    report_path = output / "wind_probe_report.json"
    command = [sys.executable, "-u", str(Path(__file__).resolve()), "--worker"]
    for field in args.fields:
        command.extend(["--field", field])
    if args.windpy_path:
        command.extend(["--windpy-path", args.windpy_path])
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    print("开始只读核验：21 只清单债券 + 1 只国债对照。请确保 Wind 已登录。", flush=True)
    print("分别探测截图字段与候选 WSS 字段，结果不会修改生产配置。", flush=True)
    print(f"最长等待 {args.timeout} 秒；进度日志：{log_path}", flush=True)
    timed_out = False
    interrupted = False
    launch_error = None
    exit_code = None
    with log_path.open("w", encoding="utf-8") as log:
        try:
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, env=env)
            try:
                exit_code = process.wait(timeout=args.timeout)
            except (subprocess.TimeoutExpired, KeyboardInterrupt) as exc:
                timed_out = isinstance(exc, subprocess.TimeoutExpired)
                interrupted = not timed_out
                process.kill()  # 只终止本脚本的子进程，不关闭用户 Wind 终端。
                exit_code = process.wait()
        except OSError as exc:
            launch_error = str(exc)
    events = []
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith(PREFIX):
            try:
                events.append(json.loads(line[len(PREFIX):]))
            except ValueError:
                continue
    summaries = [summarize_query(event) for event in events
                 if event["step"] == "query_result" and event["requested_field"] in args.fields]
    passed_fields = [s["field"] for s in summaries if s["sample_check_passed"]]
    complete_run = exit_code == 0 and any(e["step"] == "finished" for e in events)
    ok = complete_run and bool(passed_fields)
    report = {
        "checked_at_beijing": stamp, "codes": ALL_CODES, "fields": args.fields,
        "scope": "当前 Wind 属性查询；不验证历史属性，不修改持仓、数据库或生产配置",
        "reference_note": "21只债券为用户提供的参考名单；010706.SH为国债对照。名单不一致须复核，不能直接改持仓。",
        "field_note": "b_info_scitechbondornot来自Excel截图；scitechbondornot仅为待验证WSS候选，分别记录。",
        "exit_code": exit_code, "timed_out": timed_out, "interrupted": interrupted,
        "launch_error": launch_error, "last_step": events[-1]["step"] if events else None,
        "sample_check_passed": ok, "passed_fields": passed_fields,
        "summaries": summaries, "events": events,
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    for summary in summaries:
        status = "样本检查通过" if summary["sample_check_passed"] else "需要核对"
        print(f"{summary['field']}: 错误码={summary['error_code']}，完整={summary['complete']}，{status}")
    if timed_out:
        print(f"核验超时，最后阶段：{report['last_step']}。已保存部分结果。")
    elif not ok:
        print("尚未通过字段样本检查，请查看报告中的错误码、空值或名单差异。")
    else:
        print("通过样本检查的字段：" + ", ".join(passed_fields))
    print(f"请回传报告：{report_path}")
    print(f"如启动失败或超时，同时回传日志：{log_path}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
