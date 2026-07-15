import hashlib
import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from scripts import run_kernel_candidate as runner
from src.pipeline.execution import BaselineRunResult, StageRunResult, TableRunSummary
from src.testing.current_issuer_resolver import validate_current_issuer_resolver
from src.testing.output_diff import OutputTreeDiffReport
from src.testing.test_environment import UnsafeTestEnvironment


def _stage(name: str, table_count: int, root: Path) -> StageRunResult:
    output = root / name
    output.mkdir()
    return StageRunResult(
        stage=name,
        output_dir=output,
        tables=tuple(
            TableRunSummary(name=f"table-{index}", row_count=1, column_count=1)
            for index in range(table_count)
        ),
    )


def _diff(*, passed: bool) -> OutputTreeDiffReport:
    return OutputTreeDiffReport(
        passed=passed,
        artifact_differences=0 if passed else 1,
        sheet_differences=0,
        logical_fingerprint_differences=0,
    )


def test_cli_exposes_no_manifest_mapping_database_wind_or_archive_override() -> None:
    parser = runner._build_parser()
    destinations = {action.dest for action in parser._actions}

    assert {"input_root", "allow_output_root", "output", "reference"} <= destinations
    assert destinations.isdisjoint(
        {
            "manifest",
            "issuer_mapping_file",
            "zero_result_source",
            "database_url",
            "wind",
            "archive",
            "current",
        }
    )


def test_source_diff_accepts_only_planned_kernel_extraction_paths() -> None:
    entries = runner._validate_source_diff_entries(
        (
            ("A", "src/risk_core/kernel.py"),
            ("M", "src/stage1/stage1_processor.py"),
            ("M", "src/stage1/stage1_limit_detail.py"),
            ("M", "src/stage2/stage2_processor.py"),
        )
    )

    assert [entry["path"] for entry in entries] == [
        "src/risk_core/kernel.py",
        "src/stage1/stage1_limit_detail.py",
        "src/stage1/stage1_processor.py",
        "src/stage2/stage2_processor.py",
    ]


@pytest.mark.parametrize(
    "entry",
    [
        ("M", "src/stage0/stage0_processor.py"),
        ("M", "src/common/business_rules.py"),
        ("M", "src/utils/config_loader.py"),
        ("M", "config/settings.yaml"),
        ("M", "scripts/daily_archive.py"),
        ("D", "src/risk_core/kernel.py"),
        ("R100", "src/stage1/stage1_processor.py"),
    ],
)
def test_source_diff_rejects_every_path_or_status_outside_plan(
    entry: tuple[str, str],
) -> None:
    with pytest.raises(UnsafeTestEnvironment, match="允许范围"):
        runner._validate_source_diff_entries((entry,))


def test_pipeline_result_requires_exact_stage_order_and_counts(tmp_path: Path) -> None:
    result = BaselineRunResult(
        business_date=date(2026, 7, 10),
        stages=(
            _stage("stage0", 10, tmp_path),
            _stage("stage1", 35, tmp_path),
            _stage("stage2", 22, tmp_path),
        ),
    )

    runner._validate_stage_result(result)


def test_pipeline_result_rejects_reordered_or_incomplete_stages(tmp_path: Path) -> None:
    result = BaselineRunResult(
        business_date=date(2026, 7, 10),
        stages=(
            _stage("stage0", 10, tmp_path),
            _stage("stage2", 22, tmp_path),
            _stage("stage1", 34, tmp_path),
        ),
    )

    with pytest.raises(UnsafeTestEnvironment, match="Stage0→1→2"):
        runner._validate_stage_result(result)


def test_static_resolver_must_equal_sealed_mapping_and_zero_source(tmp_path: Path) -> None:
    mapping = tmp_path / "issuer_wind_code_mapping.csv"
    mapping.write_text("发行人,wind代码\n甲公司,1001\n", encoding="utf-8-sig")
    zero_source = tmp_path / "风控部债券池_主体.xlsx"
    pd.DataFrame(
        {"发行人名称": ["无代码公司"], "发行人wind代码": [0]}
    ).to_excel(zero_source, index=False)
    resolver = validate_current_issuer_resolver(mapping, zero_source)
    evidence = {
        "current_issuer_resolver": {
            "mapping": {
                "sha256": hashlib.sha256(mapping.read_bytes()).hexdigest(),
                "size": mapping.stat().st_size,
                "row_count": 1,
            },
            "zero_result_source": {
                "sha256": hashlib.sha256(zero_source.read_bytes()).hexdigest(),
                "size": zero_source.stat().st_size,
                "zero_result_count": 1,
            },
        }
    }

    runner._validate_resolver_against_evidence(resolver, evidence)
    evidence["current_issuer_resolver"]["mapping"]["sha256"] = "wrong"
    with pytest.raises(UnsafeTestEnvironment, match="静态主体映射"):
        runner._validate_resolver_against_evidence(resolver, evidence)


def test_success_gate_requires_zero_diff_sealed_fingerprint_and_inventory() -> None:
    protected = {"input": {"sha256": "same"}}
    runner._validate_success_gate(
        report=_diff(passed=True),
        actual_fingerprint="sealed",
        expected_fingerprint="sealed",
        protected_before=protected,
        protected_after=protected,
    )

    with pytest.raises(UnsafeTestEnvironment, match="零差异"):
        runner._validate_success_gate(
            report=_diff(passed=False),
            actual_fingerprint="sealed",
            expected_fingerprint="sealed",
            protected_before=protected,
            protected_after=protected,
        )
    with pytest.raises(UnsafeTestEnvironment, match="封存指纹"):
        runner._validate_success_gate(
            report=_diff(passed=True),
            actual_fingerprint="candidate",
            expected_fingerprint="sealed",
            protected_before=protected,
            protected_after=protected,
        )
    with pytest.raises(UnsafeTestEnvironment, match="受保护"):
        runner._validate_success_gate(
            report=_diff(passed=True),
            actual_fingerprint="sealed",
            expected_fingerprint="sealed",
            protected_before=protected,
            protected_after={"input": {"sha256": "changed"}},
        )


def test_success_evidence_records_candidate_sha_source_diff_and_zero_summary() -> None:
    source_diff = {
        "baseline": runner.BASELINE_COMMIT,
        "candidate": "candidate-sha",
        "changed_files": [{"status": "M", "path": "src/stage1/stage1_processor.py"}],
        "patch_sha256": "patch-sha",
    }

    evidence = runner._build_success_evidence(
        manifest={"id": "frozen"},
        resolver={"mapping": {"sha256": "mapping"}},
        candidate_sha="candidate-sha",
        source_diff=source_diff,
        stage_evidence=[{"stage": "stage0"}],
        output_fingerprint={"logical_sha256": "sealed"},
        report=_diff(passed=True),
        protected_before={"input": {}},
        protected_after={"input": {}},
        runtime={"environment": "test"},
        code={"runner_sha256": "runner"},
        sandbox_probes={"outside_write": "denied"},
    )

    assert evidence["status"] == "success"
    assert evidence["git"]["candidate"] == "candidate-sha"
    assert evidence["git"]["source_diff"] == source_diff
    assert evidence["diff"]["passed"] is True
    assert evidence["diff"]["artifact_differences"] == 0
    assert evidence["protected_unchanged"] is True


def test_success_evidence_is_never_written_for_failed_diff(tmp_path: Path) -> None:
    target = tmp_path / "candidate_evidence.json"

    with pytest.raises(UnsafeTestEnvironment, match="失败结果"):
        runner._write_success_evidence(target, {"status": "success"}, report=_diff(passed=False))

    assert not target.exists()


def test_diff_report_is_written_before_failure_decision(tmp_path: Path) -> None:
    target = tmp_path / "output_diff.json"
    report = _diff(passed=False)

    runner._write_diff_report(target, report)

    saved = json.loads(target.read_text(encoding="utf-8"))
    assert saved["passed"] is False
    assert saved["artifact_differences"] == 1
