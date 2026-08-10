import json
from pathlib import Path

from openpyxl import Workbook
import pytest

from src.testing.output_contract import (
    OutputContract,
    OutputContractError,
    TableContract,
    _table_contract,
    snapshot_output_contract,
)
from src.testing.output_fingerprint import fingerprint_tree


def _write_evidence(tmp_path: Path, paths: tuple[str, ...]) -> Path:
    entries_by_stage: dict[str, list[dict[str, str]]] = {}
    for relative_path in paths:
        stage, artifact = relative_path.split("/", maxsplit=1)
        entries_by_stage.setdefault(stage, []).append(
            {
                "relative_path": artifact,
                "kind": Path(artifact).suffix.lstrip("."),
            }
        )
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        json.dumps(
            {
                "output_fingerprint": {"logical_sha256": "sealed-tree"},
                "stages": [
                    {
                        "stage": stage,
                        "logical_fingerprint": {"entries": entries},
                    }
                    for stage, entries in sorted(entries_by_stage.items())
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return evidence


def _xlsx_artifact(relative_path: str) -> dict:
    return {
        "relative_path": relative_path,
        "kind": "xlsx",
        "sheets": [
            {
                "name": "结果",
                "columns": ["日期", "代码", "剩余额度"],
                "logical_dtypes": ["datetime", "string", "float"],
                "stable_key_columns": ["日期", "代码"],
                "tie_breaker_columns": [],
                "duplicate_ordinal": False,
            }
        ],
    }


def _csv_artifact(relative_path: str) -> dict:
    return {
        "relative_path": relative_path,
        "kind": "csv",
        "table": {
            "name": "__csv__",
            "columns": ["发行人", "wind代码"],
            "logical_dtypes": ["string", "string"],
            "stable_key_columns": ["发行人"],
            "tie_breaker_columns": ["wind代码"],
            "duplicate_ordinal": True,
        },
    }


def _write_contract(tmp_path: Path, artifacts: list[dict]) -> Path:
    contract = tmp_path / "contract.json"
    contract.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "contract_id": "tiny-v1",
                "sealed_tree_logical_sha256": "sealed-tree",
                "artifacts": artifacts,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return contract


def test_contract_requires_exact_sealed_artifact_set(tmp_path: Path) -> None:
    evidence = _write_evidence(
        tmp_path,
        ("stage0/issuer_wind_code_mapping.csv", "stage1/限额明细_单一债券.xlsx"),
    )
    contract = _write_contract(
        tmp_path,
        [_xlsx_artifact("stage1/限额明细_单一债券.xlsx")],
    )

    with pytest.raises(OutputContractError, match="输出集合不完整"):
        OutputContract.load(contract, evidence_path=evidence)


def test_contract_rejects_extra_artifact(tmp_path: Path) -> None:
    evidence = _write_evidence(tmp_path, ("stage1/限额明细_单一债券.xlsx",))
    contract = _write_contract(
        tmp_path,
        [
            _xlsx_artifact("stage1/限额明细_单一债券.xlsx"),
            _csv_artifact("stage0/extra.csv"),
        ],
    )

    with pytest.raises(OutputContractError, match="输出集合不完整"):
        OutputContract.load(contract, evidence_path=evidence)


def test_contract_rejects_duplicate_artifact_entry(tmp_path: Path) -> None:
    evidence = _write_evidence(tmp_path, ("stage1/限额明细_单一债券.xlsx",))
    artifact = _xlsx_artifact("stage1/限额明细_单一债券.xlsx")
    contract = _write_contract(tmp_path, [artifact, artifact])

    with pytest.raises(OutputContractError, match="重复"):
        OutputContract.load(contract, evidence_path=evidence)


def test_table_contract_rejects_reordered_or_unknown_schema() -> None:
    with pytest.raises(OutputContractError, match="logical_dtypes"):
        TableContract.from_dict(
            {
                "name": "结果",
                "columns": ["日期", "代码"],
                "logical_dtypes": ["datetime"],
                "stable_key_columns": ["日期"],
                "tie_breaker_columns": [],
                "duplicate_ordinal": False,
            }
        )

    with pytest.raises(OutputContractError, match="未知逻辑类型"):
        TableContract.from_dict(
            {
                "name": "结果",
                "columns": ["日期"],
                "logical_dtypes": ["mystery"],
                "stable_key_columns": ["日期"],
                "tie_breaker_columns": [],
                "duplicate_ordinal": False,
            }
        )


def test_table_contract_rejects_key_outside_columns() -> None:
    with pytest.raises(OutputContractError, match="不存在于 columns"):
        TableContract.from_dict(
            {
                "name": "结果",
                "columns": ["日期", "代码"],
                "logical_dtypes": ["datetime", "string"],
                "stable_key_columns": ["日期", "账户"],
                "tie_breaker_columns": [],
                "duplicate_ordinal": False,
            }
        )


def test_contract_loads_xlsx_and_csv_separately(tmp_path: Path) -> None:
    paths = (
        "stage0/issuer_wind_code_mapping.csv",
        "stage1/限额明细_单一债券.xlsx",
    )
    evidence = _write_evidence(tmp_path, paths)
    contract = _write_contract(
        tmp_path,
        [_csv_artifact(paths[0]), _xlsx_artifact(paths[1])],
    )

    loaded = OutputContract.load(contract, evidence_path=evidence)

    assert loaded.artifact_paths == frozenset(paths)
    assert loaded.artifact(paths[0]).kind == "csv"
    assert loaded.artifact(paths[1]).sheets[0].name == "结果"


def test_snapshot_output_contract_records_actual_schema_and_duplicate_policy(
    tmp_path: Path,
) -> None:
    reference = tmp_path / "reference"
    (reference / "stage0").mkdir(parents=True)
    (reference / "stage1").mkdir()
    mapping = reference / "stage0/issuer_wind_code_mapping.csv"
    mapping.write_text(
        "发行人,wind代码\n甲公司,1001\n甲公司,1001\n",
        encoding="utf-8-sig",
    )
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "结果"
    sheet.append(["日期", "代码", "剩余额度"])
    sheet.append(["2026-07-10", "A", 1.5])
    workbook.save(reference / "stage1/限额明细_单一债券.xlsx")
    (reference / "runner-metadata.json").write_text("{}", encoding="utf-8")

    stage0_fp = fingerprint_tree(reference / "stage0")
    stage1_fp = fingerprint_tree(reference / "stage1")
    combined_fp = fingerprint_tree(reference)
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        json.dumps(
            {
                "output_fingerprint": {
                    "logical_sha256": combined_fp["logical_sha256"],
                },
                "stages": [
                    {"stage": "stage0", "logical_fingerprint": stage0_fp},
                    {"stage": "stage1", "logical_fingerprint": stage1_fp},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    contract = snapshot_output_contract(
        reference,
        evidence_path=evidence,
        contract_id="tiny-v1",
    )

    assert contract.artifact_paths == frozenset(
        {
            "stage0/issuer_wind_code_mapping.csv",
            "stage1/限额明细_单一债券.xlsx",
        }
    )
    csv_table = contract.artifact("stage0/issuer_wind_code_mapping.csv").table
    assert csv_table is not None
    assert csv_table.columns == ("发行人", "wind代码")
    assert csv_table.stable_key_columns == ("发行人",)
    assert csv_table.tie_breaker_columns == ("wind代码",)
    assert csv_table.duplicate_ordinal is True
    xlsx_table = contract.artifact("stage1/限额明细_单一债券.xlsx").sheets[0]
    assert xlsx_table.columns == ("日期", "代码", "剩余额度")
    assert xlsx_table.logical_dtypes == ("string", "string", "float")
    assert xlsx_table.stable_key_columns == ("日期", "代码")
    assert xlsx_table.duplicate_ordinal is False


def test_snapshot_output_contract_rejects_reference_content_drift(tmp_path: Path) -> None:
    reference = tmp_path / "reference"
    stage0 = reference / "stage0"
    stage0.mkdir(parents=True)
    mapping = stage0 / "issuer_wind_code_mapping.csv"
    mapping.write_text("发行人,wind代码\n甲公司,1001\n", encoding="utf-8-sig")
    stage0_fp = fingerprint_tree(stage0)
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        json.dumps(
            {
                "output_fingerprint": {"logical_sha256": "sealed-tree"},
                "stages": [
                    {"stage": "stage0", "logical_fingerprint": stage0_fp},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    mapping.write_text("发行人,wind代码\n甲公司,9999\n", encoding="utf-8-sig")

    with pytest.raises(OutputContractError, match="阶段逻辑指纹"):
        snapshot_output_contract(
            reference,
            evidence_path=evidence,
            contract_id="tiny-v1",
        )


def test_credit_detail_identity_prefers_frozen_source_row() -> None:
    columns = (
        "日期",
        "_源行号",
        "内部证券账户名称",
        "资产代码",
        "库存数量(万)_PR",
        "债务主体wind代码",
    )

    contract = _table_contract(
        "结果",
        columns,
        [("2026-07-10", 7, "自营", "BOND.IB", 100.0, "ISSUER")],
        "债券持仓明细表_信用债.xlsx",
    )

    assert contract.stable_key_columns == ("日期", "_源行号")
    assert contract.tie_breaker_columns == ()


def test_single_bond_group_identity_uses_production_grouping_key() -> None:
    columns = (
        "日期",
        "业务分类",
        "单一债券归并键",
        "主证券代码",
        "主证券代码_标准",
        "资产代码",
        "资产代码_标准",
        "单一债券总持仓_PR",
    )

    contract = _table_contract(
        "结果",
        columns,
        [("2026-07-10", "自营", "GROUP", "BOND", "BOND.IB", "A", "A.IB", 100.0)],
        "单一债券总持仓.xlsx",
    )

    assert contract.stable_key_columns == ("日期", "业务分类", "单一债券归并键")
    assert contract.tie_breaker_columns == (
        "主证券代码",
        "主证券代码_标准",
        "资产代码",
        "资产代码_标准",
    )


@pytest.mark.parametrize(
    ("artifact_name", "category_column"),
    [
        ("单一地域总持仓.xlsx", "省份"),
        ("高风险行业总持仓_2.xlsx", "wind行业"),
    ],
)
def test_category_aggregate_identity_includes_category(
    artifact_name: str,
    category_column: str,
) -> None:
    columns = ("日期", category_column, "总持仓_PR")

    contract = _table_contract(
        "结果",
        columns,
        [("2026-07-10", "河北", 100.0)],
        artifact_name,
    )

    assert contract.stable_key_columns == ("日期", category_column)


def test_identity_columns_never_repeat_the_same_business_key() -> None:
    columns = ("日期", "业务分类", "指标名称", "实控人名称", "指标值")

    contract = _table_contract(
        "结果",
        columns,
        [("2026-07-10", "自营", "特定实控人", "甲", 100.0)],
        "特定实控人限额.xlsx",
    )

    assert contract.stable_key_columns == ("日期", "业务分类", "实控人名称", "指标名称")
