"""Deterministic logical fingerprints for pipeline output artifacts."""

from __future__ import annotations

import csv
from datetime import date, datetime, time, timedelta
from decimal import Decimal
import hashlib
import math
import os
from pathlib import Path
from typing import Any

import numpy as np
from openpyxl import load_workbook
import pandas as pd


class FingerprintError(RuntimeError):
    """An artifact cannot be represented by the frozen fingerprint schema."""


def canonical_scalar(value: object) -> str:
    """Return a type-tagged, deterministic scalar representation."""

    if value is None or value is pd.NA or value is pd.NaT:
        return "null"
    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            return "null"
        return f"timestamp:{value.isoformat()}"
    if isinstance(value, np.datetime64):
        if np.isnat(value):
            return "null"
        return f"numpy-datetime64:{pd.Timestamp(value).isoformat()}"
    if isinstance(value, datetime):
        return f"datetime:{value.isoformat()}"
    if isinstance(value, date):
        return f"date:{value.isoformat()}"
    if isinstance(value, time):
        return f"time:{value.isoformat()}"
    if isinstance(value, timedelta):
        microseconds = (
            value.days * 86_400_000_000
            + value.seconds * 1_000_000
            + value.microseconds
        )
        if microseconds % 1_000_000 == 0:
            return f"timedelta:{microseconds // 1_000_000}"
        return f"timedelta:{Decimal(microseconds) / Decimal(1_000_000)}"
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise FingerprintError(f"Decimal 不是有限数值: {value}")
        return f"decimal:{value.normalize()}"
    if isinstance(value, (bool, np.bool_)):
        return f"bool:{str(bool(value)).lower()}"
    if isinstance(value, (int, np.integer)):
        return f"int:{int(value)}"
    if isinstance(value, (float, np.floating)):
        number = float(value)
        if math.isnan(number):
            return "null"
        if not math.isfinite(number):
            raise FingerprintError(f"浮点数不是有限数值: {number}")
        if number == 0:
            number = 0.0
        return f"float:{format(number, '.17g')}"
    if isinstance(value, str):
        return f"string:{value}"
    raise FingerprintError(f"不支持的标量类型: {type(value).__name__}")


def fingerprint_file(path: Path | str, *, relative_to: Path | str) -> dict[str, Any]:
    raw = Path(path)
    root = Path(relative_to)
    if raw.is_symlink():
        raise FingerprintError(f"输出文件不得为符号链接: {raw}")
    try:
        resolved = raw.resolve(strict=True)
        resolved_root = root.resolve(strict=True)
    except OSError as exc:
        raise FingerprintError(f"输出文件或相对根不存在: {raw}") from exc
    if not resolved.is_file() or not resolved.is_relative_to(resolved_root):
        raise FingerprintError(f"输出路径不是根目录内普通文件: {resolved}")

    physical_sha = _sha256_file(resolved)
    suffix = resolved.suffix.lower()
    if suffix == ".xlsx":
        kind = "xlsx"
        logical_sha = _xlsx_logical_sha256(resolved)
    elif suffix == ".csv":
        kind = "csv"
        logical_sha = _csv_logical_sha256(resolved)
    else:
        kind = "binary"
        logical_sha = physical_sha

    return {
        "relative_path": resolved.relative_to(resolved_root).as_posix(),
        "kind": kind,
        "logical_sha256": logical_sha,
        "physical_sha256": physical_sha,
        "physical_size": resolved.stat().st_size,
    }


def fingerprint_tree(root: Path | str) -> dict[str, Any]:
    raw_root = Path(root)
    if raw_root.is_symlink():
        raise FingerprintError(f"输出树根不得为符号链接: {raw_root}")
    try:
        resolved_root = raw_root.resolve(strict=True)
    except OSError as exc:
        raise FingerprintError(f"输出树根不存在: {raw_root}") from exc
    if not resolved_root.is_dir():
        raise FingerprintError(f"输出树根不是目录: {resolved_root}")

    entries: list[dict[str, Any]] = []
    _collect_fingerprint_entries(resolved_root, resolved_root, entries)
    entries.sort(key=lambda item: item["relative_path"])

    digest = hashlib.sha256()
    _feed_text(digest, "tree:v1")
    for entry in entries:
        _feed_text(digest, entry["relative_path"])
        _feed_text(digest, entry["kind"])
        _feed_text(digest, entry["logical_sha256"])
    return {"schema_version": 1, "logical_sha256": digest.hexdigest(), "entries": entries}


def _collect_fingerprint_entries(root: Path, directory: Path, target: list[dict[str, Any]]) -> None:
    try:
        entries = sorted(os.scandir(directory), key=lambda item: item.name)
    except OSError as exc:
        raise FingerprintError(f"无法遍历输出目录: {directory}") from exc
    for entry in entries:
        path = Path(entry.path)
        relative = path.relative_to(root).as_posix()
        if entry.is_symlink():
            raise FingerprintError(f"输出树包含符号链接: {relative}")
        if entry.is_dir(follow_symlinks=False):
            logical_sha = hashlib.sha256(b"directory:v1").hexdigest()
            target.append(
                {
                    "relative_path": relative,
                    "kind": "directory",
                    "logical_sha256": logical_sha,
                    "physical_sha256": None,
                    "physical_size": None,
                }
            )
            _collect_fingerprint_entries(root, path, target)
        elif entry.is_file(follow_symlinks=False):
            target.append(fingerprint_file(path, relative_to=root))
        else:
            raise FingerprintError(f"输出树包含不支持的条目: {relative}")


def _xlsx_logical_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    _feed_text(digest, "workbook:v1")
    try:
        workbook = load_workbook(path, read_only=True, data_only=False, keep_links=False)
        for sheet_index, sheet in enumerate(workbook.worksheets):
            _feed_text(digest, f"sheet:{sheet_index}:{sheet.title}")
            for row in sheet.iter_rows():
                for cell in row:
                    if cell.value is None:
                        continue
                    _feed_text(digest, f"cell:{cell.coordinate}")
                    _feed_text(digest, canonical_scalar(cell.value))
            _feed_text(digest, "end-sheet")
        _feed_text(digest, "end-workbook")
        workbook.close()
    except FingerprintError:
        raise
    except Exception as exc:
        raise FingerprintError(f"无法读取 XLSX 逻辑内容: {path}") from exc
    return digest.hexdigest()


def _csv_logical_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    _feed_text(digest, "csv:v1")
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.reader(handle):
                _feed_text(digest, "row")
                for field in row:
                    _feed_text(digest, field)
                _feed_text(digest, "end-row")
    except (OSError, UnicodeError, csv.Error) as exc:
        raise FingerprintError(f"无法读取 CSV 逻辑内容: {path}") from exc
    return digest.hexdigest()


def _feed_text(digest: Any, value: str) -> None:
    encoded = value.encode("utf-8")
    digest.update(len(encoded).to_bytes(8, byteorder="big", signed=False))
    digest.update(encoded)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
