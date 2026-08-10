from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
import pandas as pd

from src.testing.output_contract import ArtifactContract, OutputContract, TableContract
from src.testing.output_diff import compare_frame, compare_output_trees


def _contract(
    columns: tuple[str, ...] = ("代码", "剩余额度"),
    dtypes: tuple[str, ...] = ("string", "float"),
    *,
    stable_keys: tuple[str, ...] = ("代码",),
    duplicate_ordinal: bool = False,
) -> TableContract:
    return TableContract(
        name="结果",
        columns=columns,
        logical_dtypes=dtypes,
        stable_key_columns=stable_keys,
        tie_breaker_columns=(),
        duplicate_ordinal=duplicate_ordinal,
    )


def _write_xlsx(path: Path, rows: list[list[object]], *, sheet_name: str = "结果") -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = sheet_name
    for row in rows:
        sheet.append(row)
    workbook.save(path)


def test_compare_frame_accepts_exact_copy() -> None:
    reference = pd.DataFrame({"代码": ["A"], "剩余额度": [0.3]})
    candidate = reference.copy(deep=True)

    report = compare_frame(reference, candidate, _contract())

    assert report.passed is True
    assert report.total_differences == 0


def test_float_serialization_difference_is_reported_but_fails() -> None:
    reference = pd.DataFrame({"代码": ["A"], "剩余额度": [0.3]})
    candidate = pd.DataFrame({"代码": ["A"], "剩余额度": [0.30000000000000004]})

    report = compare_frame(reference, candidate, _contract())

    assert report.passed is False
    assert report.float_serialization_differences == 1
    assert report.field_differences == 1


def test_compare_frame_reports_added_and_deleted_rows() -> None:
    reference = pd.DataFrame({"代码": ["A", "B"], "剩余额度": [1.0, 2.0]})
    candidate = pd.DataFrame({"代码": ["A", "C"], "剩余额度": [1.0, 3.0]})

    report = compare_frame(reference, candidate, _contract())

    assert report.passed is False
    assert report.added_rows == 1
    assert report.deleted_rows == 1
    assert report.field_differences == 0


def test_compare_frame_reports_order_only_difference() -> None:
    reference = pd.DataFrame({"代码": ["A", "B"], "剩余额度": [1.0, 2.0]})
    candidate = reference.iloc[::-1].reset_index(drop=True)

    report = compare_frame(reference, candidate, _contract())

    assert report.passed is False
    assert report.row_order_differences == 1
    assert report.added_rows == 0
    assert report.deleted_rows == 0
    assert report.field_differences == 0


def test_compare_frame_preserves_duplicate_row_count() -> None:
    reference = pd.DataFrame({"代码": ["A", "A"], "剩余额度": [1.0, 1.0]})
    candidate = pd.DataFrame({"代码": ["A"], "剩余额度": [1.0]})

    report = compare_frame(
        reference,
        candidate,
        _contract(duplicate_ordinal=True),
    )

    assert report.passed is False
    assert report.deleted_rows == 1


def test_compare_frame_reports_schema_and_semantic_type_drift() -> None:
    reference = pd.DataFrame(
        {"日期": [datetime(2026, 7, 10)], "代码": ["A"], "剩余额度": [1]}
    )
    candidate = pd.DataFrame(
        {"日期": ["2026-07-10"], "代码": ["A"], "剩余额度": [1.0]}
    )
    contract = _contract(
        columns=("日期", "代码", "剩余额度"),
        dtypes=("datetime", "string", "integer"),
        stable_keys=("代码",),
    )

    report = compare_frame(reference, candidate, contract)

    assert report.passed is False
    assert report.schema_differences >= 2
    assert report.field_differences >= 2


def test_compare_output_trees_reports_file_sheet_and_cell_differences(tmp_path: Path) -> None:
    reference = tmp_path / "reference"
    candidate = tmp_path / "candidate"
    (reference / "stage1").mkdir(parents=True)
    (candidate / "stage1").mkdir(parents=True)
    _write_xlsx(reference / "stage1/result.xlsx", [["代码", "剩余额度"], ["A", 1.0]])
    _write_xlsx(candidate / "stage1/result.xlsx", [["代码", "剩余额度"], ["A", 2.0]])
    (reference / "runner-metadata.json").write_text("reference", encoding="utf-8")
    (candidate / "runner-metadata.json").write_text("candidate", encoding="utf-8")

    table = _contract()
    output_contract = OutputContract(
        schema_version=1,
        contract_id="tiny-v1",
        sealed_tree_logical_sha256="not-used-in-unit-test",
        artifacts=(
            ArtifactContract(
                relative_path="stage1/result.xlsx",
                kind="xlsx",
                sheets=(table,),
                table=None,
            ),
        ),
    )

    report = compare_output_trees(reference, candidate, output_contract)

    assert report.passed is False
    assert report.artifact_differences == 0
    assert report.sheet_differences == 0
    assert report.field_differences == 1
    assert report.table_reports[0].relative_path == "stage1/result.xlsx"


def test_compare_output_trees_reports_missing_artifact(tmp_path: Path) -> None:
    reference = tmp_path / "reference"
    candidate = tmp_path / "candidate"
    (reference / "stage1").mkdir(parents=True)
    candidate.mkdir()
    _write_xlsx(reference / "stage1/result.xlsx", [["代码", "剩余额度"], ["A", 1.0]])
    table = _contract()
    output_contract = OutputContract(
        schema_version=1,
        contract_id="tiny-v1",
        sealed_tree_logical_sha256="not-used-in-unit-test",
        artifacts=(
            ArtifactContract(
                relative_path="stage1/result.xlsx",
                kind="xlsx",
                sheets=(table,),
                table=None,
            ),
        ),
    )

    report = compare_output_trees(reference, candidate, output_contract)

    assert report.passed is False
    assert report.artifact_differences == 1
