from datetime import date, datetime, time, timedelta
from decimal import Decimal
import json
from pathlib import Path
import zipfile

import numpy as np
from openpyxl import Workbook
import pandas as pd
import pytest

from src.testing.output_fingerprint import (
    FingerprintError,
    canonical_scalar,
    fingerprint_file,
    fingerprint_tree,
)


def _write_workbook(path: Path, value=1) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "结果"
    sheet["B2"] = value
    sheet["C3"] = date(2026, 7, 10)
    workbook.save(path)


def _rewrite_zip_timestamps(path: Path) -> None:
    replacement = path.with_suffix(".rewritten")
    with zipfile.ZipFile(path, "r") as source, zipfile.ZipFile(
        replacement,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as target:
        for item in source.infolist():
            info = zipfile.ZipInfo(item.filename, date_time=(2025, 1, 2, 3, 4, 6))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = item.external_attr
            target.writestr(info, source.read(item.filename))
    replacement.replace(path)


def test_canonical_scalar_preserves_semantic_type() -> None:
    assert canonical_scalar(None) == "null"
    assert canonical_scalar(pd.NA) == "null"
    assert canonical_scalar(pd.NaT) == "null"
    assert canonical_scalar(float("nan")) == "null"
    assert canonical_scalar(pd.Timestamp("2026-07-10 09:30")) == (
        "timestamp:2026-07-10T09:30:00"
    )
    assert canonical_scalar(np.datetime64("2026-07-10")) == (
        "numpy-datetime64:2026-07-10T00:00:00"
    )
    assert canonical_scalar(datetime(2026, 7, 10, 9, 30)) == (
        "datetime:2026-07-10T09:30:00"
    )
    assert canonical_scalar(date(2026, 7, 10)) == "date:2026-07-10"
    assert canonical_scalar(time(9, 30)) == "time:09:30:00"
    assert canonical_scalar(timedelta(days=1, seconds=2)) == "timedelta:86402"
    assert canonical_scalar(Decimal("1.00")) == "decimal:1"
    assert canonical_scalar(True) == "bool:true"
    assert canonical_scalar(np.int64(1)) == "int:1"
    assert canonical_scalar(1) == "int:1"
    assert canonical_scalar(1.0) == "float:1"
    assert canonical_scalar(-0.0) == "float:0"
    assert canonical_scalar("1") == "string:1"


@pytest.mark.parametrize("value", [float("inf"), float("-inf"), object()])
def test_canonical_scalar_rejects_unsupported_or_non_finite(value) -> None:
    with pytest.raises(FingerprintError):
        canonical_scalar(value)


def test_xlsx_logical_hash_ignores_zip_metadata(tmp_path: Path) -> None:
    left = tmp_path / "left.xlsx"
    right = tmp_path / "right.xlsx"
    _write_workbook(left)
    right.write_bytes(left.read_bytes())
    _rewrite_zip_timestamps(right)

    left_fp = fingerprint_file(left, relative_to=tmp_path)
    right_fp = fingerprint_file(right, relative_to=tmp_path)

    assert left_fp["logical_sha256"] == right_fp["logical_sha256"]
    assert left_fp["physical_sha256"] != right_fp["physical_sha256"]


def test_xlsx_logical_hash_changes_with_value_or_type(tmp_path: Path) -> None:
    integer = tmp_path / "integer.xlsx"
    floating = tmp_path / "floating.xlsx"
    changed = tmp_path / "changed.xlsx"
    _write_workbook(integer, 1)
    _write_workbook(floating, 1.0)
    _write_workbook(changed, 2)

    hashes = {
        fingerprint_file(path, relative_to=tmp_path)["logical_sha256"]
        for path in (integer, floating, changed)
    }

    assert len(hashes) >= 2
    assert fingerprint_file(integer, relative_to=tmp_path)["logical_sha256"] != (
        fingerprint_file(changed, relative_to=tmp_path)["logical_sha256"]
    )


def test_csv_logical_hash_tolerates_utf8_bom(tmp_path: Path) -> None:
    plain = tmp_path / "plain.csv"
    bom = tmp_path / "bom.csv"
    plain.write_text("a,b\n1,2\n", encoding="utf-8")
    bom.write_text("a,b\n1,2\n", encoding="utf-8-sig")

    assert fingerprint_file(plain, relative_to=tmp_path)["logical_sha256"] == (
        fingerprint_file(bom, relative_to=tmp_path)["logical_sha256"]
    )


def test_tree_hash_excludes_physical_xlsx_metadata(tmp_path: Path) -> None:
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    _write_workbook(left / "a.xlsx")
    (right / "a.xlsx").write_bytes((left / "a.xlsx").read_bytes())
    _rewrite_zip_timestamps(right / "a.xlsx")

    left_fp = fingerprint_tree(left)
    right_fp = fingerprint_tree(right)

    assert left_fp["logical_sha256"] == right_fp["logical_sha256"]
    assert left_fp["entries"][0]["physical_sha256"] != (
        right_fp["entries"][0]["physical_sha256"]
    )


def test_tree_hash_changes_with_relative_path(tmp_path: Path) -> None:
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    (left / "a.bin").write_bytes(b"same")
    (right / "b.bin").write_bytes(b"same")

    assert fingerprint_tree(left)["logical_sha256"] != fingerprint_tree(right)[
        "logical_sha256"
    ]


def test_tree_rejects_symlinks(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "target").write_bytes(b"x")
    (root / "link").symlink_to(root / "target")

    with pytest.raises(FingerprintError, match="符号链接"):
        fingerprint_tree(root)


def test_fingerprint_is_json_serializable(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "a.bin").write_bytes(b"x")

    json.dumps(fingerprint_tree(root), ensure_ascii=False, sort_keys=True)
