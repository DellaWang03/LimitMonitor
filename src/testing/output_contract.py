"""Frozen schema and row-identity contracts for production output artifacts."""

from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
import json
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

import numpy as np
from openpyxl import load_workbook
import pandas as pd

from .output_fingerprint import fingerprint_tree


class OutputContractError(RuntimeError):
    """The output contract is incomplete, inconsistent, or not sealed."""


_SCALAR_LOGICAL_DTYPES = frozenset(
    {
        "empty",
        "null",
        "string",
        "integer",
        "float",
        "boolean",
        "datetime",
        "date",
        "time",
        "timedelta",
        "decimal",
    }
)

_IDENTITY_COLUMNS = (
    "日期",
    "_源行号",
    "业务分类",
    "内部证券账户名称",
    "监管归并主键",
    "单一债券归并键",
    "高收益单债归并键",
    "证券代码",
    "资产代码",
    "资产代码_标准",
    "主证券代码",
    "主证券代码_标准",
    "债务主体wind代码",
    "债务主体",
    "实际控制人名称_修正",
    "实控人名称",
    "特定主体名称",
    "特定实控人名称",
    "担保人wind代码",
    "担保人",
    "授信担保公司名称",
    "指标名称",
    "限额名称",
    "指标维度",
    "指标类别",
    "发行人/债券类型",
    "内评类别",
    "行业类别",
    "行业名称",
    "wind行业",
    "省份类别",
    "省份名称",
    "省份",
    "账户",
    "代码",
    "简称",
    "债券代码",
    "主体名称",
    "主体wind代码",
    "发行人",
    "发行人名称",
)

_TIE_BREAKER_COLUMNS = (
    "wind代码",
    "ISIN码",
    "证券名称",
    "资产名称",
    "主证券名称",
    "发行人wind代码",
    "主体wind代码",
    "统一社会信用代码",
)


def _is_known_logical_dtype(value: str) -> bool:
    if value in _SCALAR_LOGICAL_DTYPES:
        return True
    if value.startswith("mixed[") and value.endswith("]"):
        members = tuple(item.strip() for item in value[6:-1].split(",") if item.strip())
        return bool(members) and all(item in _SCALAR_LOGICAL_DTYPES for item in members)
    return False


def logical_scalar_type(value: object) -> str:
    if value is None or value is pd.NA or value is pd.NaT:
        return "null"
    if isinstance(value, (float, np.floating)) and np.isnan(float(value)):
        return "null"
    if isinstance(value, (bool, np.bool_)):
        return "boolean"
    if isinstance(value, (int, np.integer)):
        return "integer"
    if isinstance(value, (float, np.floating)):
        return "float"
    if isinstance(value, (pd.Timestamp, np.datetime64, datetime)):
        return "datetime"
    if isinstance(value, date):
        return "date"
    if isinstance(value, time):
        return "time"
    if isinstance(value, (timedelta, np.timedelta64, pd.Timedelta)):
        return "timedelta"
    if isinstance(value, Decimal):
        return "decimal"
    if isinstance(value, str):
        return "string"
    return f"unsupported:{type(value).__name__}"


def infer_logical_dtype(values: Iterable[object]) -> str:
    members = sorted(
        {
            logical_scalar_type(value)
            for value in values
            if logical_scalar_type(value) != "null"
        }
    )
    if not members:
        return "empty"
    if len(members) == 1:
        return members[0]
    return f"mixed[{','.join(members)}]"


def _required_text(raw: Any, field_name: str) -> str:
    value = str(raw or "").strip()
    if not value:
        raise OutputContractError(f"{field_name} 不能为空")
    return value


def _string_tuple(
    raw: Any,
    field_name: str,
    *,
    allow_duplicates: bool = False,
) -> tuple[str, ...]:
    if not isinstance(raw, list):
        raise OutputContractError(f"{field_name} 必须是数组")
    values = tuple(str(value) for value in raw)
    if not allow_duplicates and len(values) != len(set(values)):
        raise OutputContractError(f"{field_name} 存在重复值")
    return values


@dataclass(frozen=True)
class TableContract:
    name: str
    columns: tuple[str, ...]
    logical_dtypes: tuple[str, ...]
    stable_key_columns: tuple[str, ...]
    tie_breaker_columns: tuple[str, ...]
    duplicate_ordinal: bool

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "TableContract":
        if not isinstance(raw, dict):
            raise OutputContractError("table contract 必须是对象")
        name = _required_text(raw.get("name"), "table.name")
        columns = _string_tuple(raw.get("columns"), f"{name}.columns")
        logical_dtypes = _string_tuple(
            raw.get("logical_dtypes"),
            f"{name}.logical_dtypes",
            allow_duplicates=True,
        )
        if len(columns) != len(logical_dtypes):
            raise OutputContractError(
                f"{name}.logical_dtypes 数量必须与 columns 完全一致"
            )
        unknown = [value for value in logical_dtypes if not _is_known_logical_dtype(value)]
        if unknown:
            raise OutputContractError(f"{name} 存在未知逻辑类型: {unknown}")

        stable_keys = _string_tuple(
            raw.get("stable_key_columns"),
            f"{name}.stable_key_columns",
        )
        tie_breakers = _string_tuple(
            raw.get("tie_breaker_columns"),
            f"{name}.tie_breaker_columns",
        )
        if not stable_keys:
            raise OutputContractError(f"{name}.stable_key_columns 不能为空")
        missing_keys = [
            value
            for value in (*stable_keys, *tie_breakers)
            if value not in columns
        ]
        if missing_keys:
            raise OutputContractError(
                f"{name} 的键不存在于 columns: {missing_keys}"
            )
        overlap = set(stable_keys).intersection(tie_breakers)
        if overlap:
            raise OutputContractError(f"{name} 的稳定键和 tie-breaker 重复: {sorted(overlap)}")
        duplicate_ordinal = raw.get("duplicate_ordinal")
        if not isinstance(duplicate_ordinal, bool):
            raise OutputContractError(f"{name}.duplicate_ordinal 必须是布尔值")
        return cls(
            name=name,
            columns=columns,
            logical_dtypes=logical_dtypes,
            stable_key_columns=stable_keys,
            tie_breaker_columns=tie_breakers,
            duplicate_ordinal=duplicate_ordinal,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "columns": list(self.columns),
            "logical_dtypes": list(self.logical_dtypes),
            "stable_key_columns": list(self.stable_key_columns),
            "tie_breaker_columns": list(self.tie_breaker_columns),
            "duplicate_ordinal": self.duplicate_ordinal,
        }


@dataclass(frozen=True)
class ArtifactContract:
    relative_path: str
    kind: str
    sheets: tuple[TableContract, ...]
    table: TableContract | None

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ArtifactContract":
        if not isinstance(raw, dict):
            raise OutputContractError("artifact contract 必须是对象")
        relative_path = _required_text(raw.get("relative_path"), "relative_path")
        pure_path = PurePosixPath(relative_path)
        if pure_path.is_absolute() or ".." in pure_path.parts or len(pure_path.parts) < 2:
            raise OutputContractError(f"非法相对输出路径: {relative_path}")
        kind = _required_text(raw.get("kind"), f"{relative_path}.kind").lower()
        if kind not in {"xlsx", "csv"}:
            raise OutputContractError(f"不支持的输出类型: {kind}")

        if kind == "xlsx":
            raw_sheets = raw.get("sheets")
            if not isinstance(raw_sheets, list) or not raw_sheets:
                raise OutputContractError(f"{relative_path}.sheets 不能为空")
            sheets = tuple(TableContract.from_dict(item) for item in raw_sheets)
            names = [sheet.name for sheet in sheets]
            if len(names) != len(set(names)):
                raise OutputContractError(f"{relative_path} 存在重复 sheet")
            if raw.get("table") is not None:
                raise OutputContractError(f"{relative_path} 的 xlsx 不得设置 table")
            table = None
        else:
            sheets = ()
            if raw.get("table") is None:
                raise OutputContractError(f"{relative_path}.table 不能为空")
            table = TableContract.from_dict(raw["table"])
            if raw.get("sheets") not in (None, []):
                raise OutputContractError(f"{relative_path} 的 csv 不得设置 sheets")
        return cls(relative_path=relative_path, kind=kind, sheets=sheets, table=table)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "relative_path": self.relative_path,
            "kind": self.kind,
        }
        if self.kind == "xlsx":
            result["sheets"] = [sheet.to_dict() for sheet in self.sheets]
        else:
            assert self.table is not None
            result["table"] = self.table.to_dict()
        return result


@dataclass(frozen=True)
class OutputContract:
    schema_version: int
    contract_id: str
    sealed_tree_logical_sha256: str
    artifacts: tuple[ArtifactContract, ...]

    @property
    def artifact_paths(self) -> frozenset[str]:
        return frozenset(artifact.relative_path for artifact in self.artifacts)

    def artifact(self, relative_path: str) -> ArtifactContract:
        for artifact in self.artifacts:
            if artifact.relative_path == relative_path:
                return artifact
        raise KeyError(relative_path)

    @classmethod
    def load(
        cls,
        path: Path | str,
        *,
        evidence_path: Path | str,
    ) -> "OutputContract":
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
            evidence = json.loads(Path(evidence_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise OutputContractError("无法读取输出契约或封存证据") from exc

        if raw.get("schema_version") != 1:
            raise OutputContractError("输出契约 schema_version 必须为 1")
        artifacts = tuple(
            ArtifactContract.from_dict(item)
            for item in raw.get("artifacts", [])
        )
        paths = [artifact.relative_path for artifact in artifacts]
        if len(paths) != len(set(paths)):
            raise OutputContractError("输出契约存在重复 artifact 路径")

        expected_paths = _evidence_artifact_paths(evidence)
        actual_paths = frozenset(paths)
        if actual_paths != expected_paths:
            missing = sorted(expected_paths - actual_paths)
            extra = sorted(actual_paths - expected_paths)
            raise OutputContractError(
                f"输出集合不完整或包含额外项; missing={missing}, extra={extra}"
            )
        sealed_tree = _required_text(
            raw.get("sealed_tree_logical_sha256"),
            "sealed_tree_logical_sha256",
        )
        evidence_tree = str(
            evidence.get("output_fingerprint", {}).get("logical_sha256", "")
        )
        if sealed_tree != evidence_tree:
            raise OutputContractError("契约封存指纹与证据不一致")
        return cls(
            schema_version=1,
            contract_id=_required_text(raw.get("contract_id"), "contract_id"),
            sealed_tree_logical_sha256=sealed_tree,
            artifacts=artifacts,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "contract_id": self.contract_id,
            "sealed_tree_logical_sha256": self.sealed_tree_logical_sha256,
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
        }

    def write_json(self, path: Path | str) -> None:
        Path(path).write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, indent=2),
            encoding="utf-8",
        )


def snapshot_output_contract(
    reference_root: Path | str,
    *,
    evidence_path: Path | str,
    contract_id: str,
) -> OutputContract:
    root = Path(reference_root).resolve(strict=True)
    evidence = json.loads(Path(evidence_path).read_text(encoding="utf-8"))
    expected_paths = _evidence_artifact_paths(evidence)
    expected_stages = {PurePosixPath(path).parts[0] for path in expected_paths}
    actual_paths = frozenset(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
        and path.relative_to(root).parts[0] in expected_stages
    )
    if actual_paths != expected_paths:
        missing = sorted(expected_paths - actual_paths)
        extra = sorted(actual_paths - expected_paths)
        raise OutputContractError(
            f"金样输出集合与封存证据不一致; missing={missing}, extra={extra}"
        )

    for stage in evidence.get("stages", []):
        stage_name = _required_text(stage.get("stage"), "evidence.stage")
        sealed_stage_sha = _required_text(
            stage.get("logical_fingerprint", {}).get("logical_sha256"),
            f"evidence.{stage_name}.logical_fingerprint.logical_sha256",
        )
        actual_stage_sha = fingerprint_tree(root / stage_name)["logical_sha256"]
        if actual_stage_sha != sealed_stage_sha:
            raise OutputContractError(
                f"{stage_name} 阶段逻辑指纹与封存证据不一致"
            )

    artifacts: list[ArtifactContract] = []
    for relative_path in sorted(expected_paths):
        artifact_path = root / relative_path
        suffix = artifact_path.suffix.lower()
        if suffix == ".xlsx":
            sheets = _snapshot_xlsx(artifact_path)
            artifact = ArtifactContract(
                relative_path=relative_path,
                kind="xlsx",
                sheets=sheets,
                table=None,
            )
        elif suffix == ".csv":
            table = _snapshot_csv(artifact_path)
            artifact = ArtifactContract(
                relative_path=relative_path,
                kind="csv",
                sheets=(),
                table=table,
            )
        else:
            raise OutputContractError(f"金样包含不支持的输出类型: {relative_path}")
        artifacts.append(artifact)

    return OutputContract(
        schema_version=1,
        contract_id=_required_text(contract_id, "contract_id"),
        sealed_tree_logical_sha256=_required_text(
            evidence.get("output_fingerprint", {}).get("logical_sha256"),
            "evidence.output_fingerprint.logical_sha256",
        ),
        artifacts=tuple(artifacts),
    )


def _snapshot_xlsx(path: Path) -> tuple[TableContract, ...]:
    workbook = load_workbook(path, read_only=True, data_only=False, keep_links=False)
    tables: list[TableContract] = []
    try:
        for sheet in workbook.worksheets:
            rows = [tuple(row) for row in sheet.iter_rows(values_only=True)]
            if not rows:
                raise OutputContractError(f"工作表没有表头: {path.name}/{sheet.title}")
            columns = tuple("" if value is None else str(value) for value in rows[0])
            if not columns or any(not column for column in columns):
                raise OutputContractError(f"工作表表头为空: {path.name}/{sheet.title}")
            data_rows = rows[1:]
            tables.append(_table_contract(sheet.title, columns, data_rows, path.name))
        return tuple(tables)
    finally:
        workbook.close()


def _snapshot_csv(path: Path) -> TableContract:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    if not rows:
        raise OutputContractError(f"CSV 没有表头: {path.name}")
    columns = tuple(rows[0])
    return _table_contract("__csv__", columns, rows[1:], path.name)


def _table_contract(
    table_name: str,
    columns: tuple[str, ...],
    rows: Iterable[Iterable[object]],
    artifact_name: str,
) -> TableContract:
    materialized_rows = [tuple(row) for row in rows]
    if any(len(row) != len(columns) for row in materialized_rows):
        raise OutputContractError(f"表格行宽与表头不一致: {artifact_name}/{table_name}")
    logical_dtypes = tuple(
        infer_logical_dtype(row[index] for row in materialized_rows)
        for index in range(len(columns))
    )
    stable_keys, tie_breakers = _identity_columns(artifact_name, columns)
    key_indexes = tuple(columns.index(column) for column in (*stable_keys, *tie_breakers))
    key_counts = Counter(
        tuple(str(row[index]) for index in key_indexes)
        for row in materialized_rows
    )
    duplicate_ordinal = any(count > 1 for count in key_counts.values())
    return TableContract(
        name=table_name,
        columns=columns,
        logical_dtypes=logical_dtypes,
        stable_key_columns=stable_keys,
        tie_breaker_columns=tie_breakers,
        duplicate_ordinal=duplicate_ordinal,
    )


def _identity_columns(
    artifact_name: str,
    columns: tuple[str, ...],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if artifact_name == "issuer_wind_code_mapping.csv" and "发行人" in columns:
        return ("发行人",), (("wind代码",) if "wind代码" in columns else ())

    if (
        artifact_name.startswith("债券持仓明细表_信用债")
        and "_源行号" in columns
    ):
        stable = tuple(column for column in ("日期", "_源行号") if column in columns)
        return stable, ()

    if artifact_name == "单一债券总持仓.xlsx" and "单一债券归并键" in columns:
        stable = tuple(
            column
            for column in ("日期", "业务分类", "单一债券归并键")
            if column in columns
        )
        ties = tuple(
            column
            for column in (
                "主证券代码",
                "主证券代码_标准",
                "资产代码",
                "资产代码_标准",
            )
            if column in columns
        )
        return stable, ties

    stable = tuple(column for column in _IDENTITY_COLUMNS if column in columns)
    if not stable:
        stable = (columns[0],)
    ties = tuple(
        column
        for column in _TIE_BREAKER_COLUMNS
        if column in columns and column not in stable
    )
    return stable, ties


def _evidence_artifact_paths(evidence: dict[str, Any]) -> frozenset[str]:
    paths: set[str] = set()
    for stage in evidence.get("stages", []):
        stage_name = _required_text(stage.get("stage"), "evidence.stage")
        for entry in stage.get("logical_fingerprint", {}).get("entries", []):
            kind = entry.get("kind")
            if kind == "directory":
                continue
            relative = _required_text(entry.get("relative_path"), "evidence.relative_path")
            combined = PurePosixPath(stage_name, relative).as_posix()
            if combined in paths:
                raise OutputContractError(f"封存证据存在重复输出: {combined}")
            paths.add(combined)
    if not paths:
        raise OutputContractError("封存证据未包含输出文件")
    return frozenset(paths)
