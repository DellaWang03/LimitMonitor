"""Exact table, row, and field comparison for frozen pipeline outputs."""

from __future__ import annotations

from collections import Counter, defaultdict
import csv
from dataclasses import asdict, dataclass, field
import json
import hashlib
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from openpyxl import load_workbook
import pandas as pd

from .output_contract import (
    OutputContract,
    TableContract,
    infer_logical_dtype,
)
from .output_fingerprint import canonical_scalar, fingerprint_tree


@dataclass(frozen=True)
class FieldDifference:
    row_key: tuple[str, ...]
    column: str
    reference: str
    candidate: str
    float_serialization_only: bool


@dataclass(frozen=True)
class FrameDiffReport:
    passed: bool
    schema_differences: int = 0
    added_rows: int = 0
    deleted_rows: int = 0
    field_differences: int = 0
    float_serialization_differences: int = 0
    row_order_differences: int = 0
    details: tuple[FieldDifference, ...] = ()

    @property
    def total_differences(self) -> int:
        return (
            self.schema_differences
            + self.added_rows
            + self.deleted_rows
            + self.field_differences
            + self.row_order_differences
        )


@dataclass(frozen=True)
class TableDiffReport:
    relative_path: str
    table_name: str
    report: FrameDiffReport


@dataclass(frozen=True)
class OutputTreeDiffReport:
    passed: bool
    artifact_differences: int
    sheet_differences: int
    logical_fingerprint_differences: int
    table_reports: tuple[TableDiffReport, ...] = field(default_factory=tuple)
    reference_logical_sha256: str | None = None
    candidate_logical_sha256: str | None = None

    @property
    def schema_differences(self) -> int:
        return sum(item.report.schema_differences for item in self.table_reports)

    @property
    def added_rows(self) -> int:
        return sum(item.report.added_rows for item in self.table_reports)

    @property
    def deleted_rows(self) -> int:
        return sum(item.report.deleted_rows for item in self.table_reports)

    @property
    def field_differences(self) -> int:
        return sum(item.report.field_differences for item in self.table_reports)

    @property
    def float_serialization_differences(self) -> int:
        return sum(
            item.report.float_serialization_differences
            for item in self.table_reports
        )

    @property
    def row_order_differences(self) -> int:
        return sum(item.report.row_order_differences for item in self.table_reports)

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result.update(
            {
                "schema_differences": self.schema_differences,
                "added_rows": self.added_rows,
                "deleted_rows": self.deleted_rows,
                "field_differences": self.field_differences,
                "float_serialization_differences": self.float_serialization_differences,
                "row_order_differences": self.row_order_differences,
            }
        )
        return result

    def write_json(self, path: Path | str) -> None:
        Path(path).write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, indent=2),
            encoding="utf-8",
        )


def compare_frame(
    reference: pd.DataFrame,
    candidate: pd.DataFrame,
    contract: TableContract,
) -> FrameDiffReport:
    schema_differences = 0
    expected_columns = list(contract.columns)
    if list(reference.columns) != expected_columns:
        schema_differences += 1
    if list(candidate.columns) != expected_columns:
        schema_differences += 1

    common_columns = [
        column
        for column in contract.columns
        if column in reference.columns and column in candidate.columns
    ]
    for index, column in enumerate(contract.columns):
        expected_dtype = contract.logical_dtypes[index]
        if column in reference.columns:
            if infer_logical_dtype(reference[column].tolist()) != expected_dtype:
                schema_differences += 1
        if column in candidate.columns:
            if infer_logical_dtype(candidate[column].tolist()) != expected_dtype:
                schema_differences += 1

    required_keys = (*contract.stable_key_columns, *contract.tie_breaker_columns)
    if any(column not in common_columns for column in required_keys):
        return FrameDiffReport(passed=False, schema_differences=schema_differences + 1)

    reference_rows = _indexed_rows(reference, contract)
    candidate_rows = _indexed_rows(candidate, contract)
    reference_keys = set(reference_rows)
    candidate_keys = set(candidate_rows)
    added_keys = candidate_keys - reference_keys
    deleted_keys = reference_keys - candidate_keys

    details: list[FieldDifference] = []
    float_differences = 0
    for row_key in sorted(reference_keys & candidate_keys):
        reference_row = reference_rows[row_key]
        candidate_row = candidate_rows[row_key]
        for column in common_columns:
            reference_value = reference_row[column]
            candidate_value = candidate_row[column]
            reference_canonical = canonical_scalar(reference_value)
            candidate_canonical = canonical_scalar(candidate_value)
            if reference_canonical == candidate_canonical:
                continue
            float_only = isinstance(reference_value, (float, np.floating)) and isinstance(
                candidate_value,
                (float, np.floating),
            )
            if float_only:
                float_differences += 1
            details.append(
                FieldDifference(
                    row_key=row_key,
                    column=column,
                    reference=reference_canonical,
                    candidate=candidate_canonical,
                    float_serialization_only=float_only,
                )
            )

    reference_signatures = _row_signatures(reference, common_columns)
    candidate_signatures = _row_signatures(candidate, common_columns)
    order_differences = int(
        Counter(reference_signatures) == Counter(candidate_signatures)
        and reference_signatures != candidate_signatures
    )
    total = (
        schema_differences
        + len(added_keys)
        + len(deleted_keys)
        + len(details)
        + order_differences
    )
    return FrameDiffReport(
        passed=total == 0,
        schema_differences=schema_differences,
        added_rows=len(added_keys),
        deleted_rows=len(deleted_keys),
        field_differences=len(details),
        float_serialization_differences=float_differences,
        row_order_differences=order_differences,
        details=tuple(details),
    )


def compare_output_trees(
    reference_root: Path | str,
    candidate_root: Path | str,
    contract: OutputContract,
) -> OutputTreeDiffReport:
    reference_root = Path(reference_root).resolve(strict=True)
    candidate_root = Path(candidate_root).resolve(strict=True)
    expected_paths = contract.artifact_paths
    expected_stages = {
        Path(relative_path).parts[0]
        for relative_path in expected_paths
    }
    reference_paths = _artifact_paths(reference_root, expected_stages)
    candidate_paths = _artifact_paths(candidate_root, expected_stages)
    artifact_differences = len(expected_paths.symmetric_difference(reference_paths))
    artifact_differences += len(expected_paths.symmetric_difference(candidate_paths))

    sheet_differences = 0
    table_reports: list[TableDiffReport] = []
    for artifact in contract.artifacts:
        if artifact.relative_path not in reference_paths:
            continue
        if artifact.relative_path not in candidate_paths:
            continue
        reference_path = reference_root / artifact.relative_path
        candidate_path = candidate_root / artifact.relative_path
        if artifact.kind == "xlsx":
            reference_tables, reference_sheets = _load_xlsx_tables(reference_path)
            candidate_tables, candidate_sheets = _load_xlsx_tables(candidate_path)
            expected_sheets = {sheet.name for sheet in artifact.sheets}
            sheet_differences += len(expected_sheets.symmetric_difference(reference_sheets))
            sheet_differences += len(expected_sheets.symmetric_difference(candidate_sheets))
            for table_contract in artifact.sheets:
                if table_contract.name not in reference_tables:
                    continue
                if table_contract.name not in candidate_tables:
                    continue
                table_reports.append(
                    TableDiffReport(
                        relative_path=artifact.relative_path,
                        table_name=table_contract.name,
                        report=compare_frame(
                            reference_tables[table_contract.name],
                            candidate_tables[table_contract.name],
                            table_contract,
                        ),
                    )
                )
        else:
            assert artifact.table is not None
            table_reports.append(
                TableDiffReport(
                    relative_path=artifact.relative_path,
                    table_name=artifact.table.name,
                    report=compare_frame(
                        _load_csv_table(reference_path),
                        _load_csv_table(candidate_path),
                        artifact.table,
                    ),
                )
            )

    reference_fingerprint = _aggregate_stage_fingerprint(
        reference_root,
        expected_stages,
    )
    candidate_fingerprint = _aggregate_stage_fingerprint(
        candidate_root,
        expected_stages,
    )
    logical_fingerprint_differences = int(
        reference_fingerprint != candidate_fingerprint
    )
    passed = (
        artifact_differences == 0
        and sheet_differences == 0
        and logical_fingerprint_differences == 0
        and all(item.report.passed for item in table_reports)
    )
    return OutputTreeDiffReport(
        passed=passed,
        artifact_differences=artifact_differences,
        sheet_differences=sheet_differences,
        logical_fingerprint_differences=logical_fingerprint_differences,
        table_reports=tuple(table_reports),
        reference_logical_sha256=reference_fingerprint,
        candidate_logical_sha256=candidate_fingerprint,
    )


def _indexed_rows(
    frame: pd.DataFrame,
    contract: TableContract,
) -> dict[tuple[str, ...], dict[str, object]]:
    key_columns = (*contract.stable_key_columns, *contract.tie_breaker_columns)
    ordinals: defaultdict[tuple[str, ...], int] = defaultdict(int)
    indexed: dict[tuple[str, ...], dict[str, object]] = {}
    for row in frame.to_dict(orient="records"):
        base_key = tuple(canonical_scalar(row[column]) for column in key_columns)
        ordinal = ordinals[base_key]
        ordinals[base_key] += 1
        if ordinal and not contract.duplicate_ordinal:
            key = (*base_key, f"unexpected-duplicate:{ordinal}")
        elif contract.duplicate_ordinal:
            key = (*base_key, f"ordinal:{ordinal}")
        else:
            key = base_key
        indexed[key] = row
    return indexed


def _row_signatures(frame: pd.DataFrame, columns: Iterable[str]) -> list[tuple[str, ...]]:
    return [
        tuple(canonical_scalar(row[column]) for column in columns)
        for row in frame.to_dict(orient="records")
    ]


def _artifact_paths(root: Path, stage_names: set[str]) -> frozenset[str]:
    return frozenset(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
        and path.relative_to(root).parts[0] in stage_names
    )


def _aggregate_stage_fingerprint(root: Path, stage_names: set[str]) -> str:
    aggregate_items = [
        {
            "stage": stage,
            "logical_sha256": (
                fingerprint_tree(root / stage)["logical_sha256"]
                if (root / stage).is_dir()
                else "__missing_stage__"
            ),
        }
        for stage in sorted(stage_names)
    ]
    encoded = json.dumps(
        aggregate_items,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _load_xlsx_tables(path: Path) -> tuple[dict[str, pd.DataFrame], set[str]]:
    workbook = load_workbook(path, read_only=True, data_only=False, keep_links=False)
    tables: dict[str, pd.DataFrame] = {}
    try:
        for sheet in workbook.worksheets:
            rows = [tuple(row) for row in sheet.iter_rows(values_only=True)]
            if not rows:
                tables[sheet.title] = pd.DataFrame()
                continue
            columns = tuple("" if value is None else str(value) for value in rows[0])
            data = [list(row) for row in rows[1:]]
            tables[sheet.title] = pd.DataFrame(data, columns=columns, dtype=object)
        return tables, set(tables)
    finally:
        workbook.close()


def _load_csv_table(path: Path) -> pd.DataFrame:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows[1:], columns=rows[0], dtype=object)
