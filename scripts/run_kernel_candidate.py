#!/opt/homebrew/bin/python3
"""Run a production-kernel candidate against the sealed frozen baseline."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Sequence


RUNNER_PATH = Path(__file__).resolve()
PROJECT_ROOT = RUNNER_PATH.parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import run_frozen_baseline as baseline
from src.pipeline.execution import BaselineRunRequest, BaselineRunResult, run_frozen_pipeline
from src.pipeline.paths import PipelinePaths
from src.testing.current_issuer_resolver import (
    ValidatedCurrentIssuerResolver,
    stage_current_issuer_resolver,
    validate_current_issuer_resolver,
)
from src.testing.frozen_config import FrozenInputConfig
from src.testing.frozen_manifest import FrozenInputManifest
from src.testing.legacy_local_compat import (
    cleanup_legacy_local_limit_config,
    stage_legacy_local_limit_config,
)
from src.testing.output_contract import OutputContract
from src.testing.output_diff import OutputTreeDiffReport, compare_output_trees
from src.testing.output_fingerprint import fingerprint_tree
from src.testing.protected_inventory import inventory_tree
from src.testing.safe_paths import create_unique_test_output
from src.testing.test_environment import UnsafeTestEnvironment, assert_test_environment
from src.utils.config_loader import ConfigLoader


BASELINE_COMMIT = baseline.BASELINE_COMMIT
PYTHON_EXECUTABLE = baseline.PYTHON_EXECUTABLE
SANDBOX_EXECUTABLE = baseline.SANDBOX_EXECUTABLE
SANDBOX_PROFILE = baseline.SANDBOX_PROFILE
FROZEN_MANIFEST = PROJECT_ROOT / "config/test_manifests/data_source_0123-20260710-v1.json"
OUTPUT_CONTRACT = PROJECT_ROOT / "config/test_manifests/pretrade-output-contract-v1.json"
SEALED_EVIDENCE = PROJECT_ROOT / "docs/evidence/pretrade-baseline-20260710.json"
EXPECTED_STAGE_COUNTS = (("stage0", 10), ("stage1", 35), ("stage2", 22))
SOURCE_AUDIT_SCOPE = (*baseline.PRODUCTION_SCOPE, "src/risk_core")
_ALLOWED_EXACT_SOURCE_PATHS = frozenset(
    {
        "src/common/__init__.py",
        "src/common/access_reader.py",
        "src/common/financial_tool_pool.py",
        "src/common/financial_tool_pool_rules.py",
        "src/common/macos_wind_excel.py",
        "src/common/wind_code_excel_helper.py",
        "src/stage0/stage0_processor.py",
        "src/stage1/stage1_processor.py",
        "src/stage1/stage1_limit_detail.py",
        "src/stage2/stage2_processor.py",
    }
)


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.sandboxed_child:
            return _run_sandboxed_child(args)
        return _run_parent(args)
    except Exception as exc:
        print(f"kernel-candidate error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", required=True)
    parser.add_argument("--allow-output-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--sandboxed-child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--output-root", help=argparse.SUPPRESS)
    parser.add_argument("--sandbox-profile-sha256", help=argparse.SUPPRESS)
    parser.add_argument("--git-executable", help=argparse.SUPPRESS)
    parser.add_argument("--git-executable-sha256", help=argparse.SUPPRESS)
    parser.add_argument("--compatibility-limit-config", help=argparse.SUPPRESS)
    parser.add_argument("--compatibility-limit-config-sha256", help=argparse.SUPPRESS)
    return parser


def _run_parent(args: argparse.Namespace) -> int:
    assert_test_environment(os.environ.get("ENV"), os.environ.get("LIMIT_MONITOR_PROFILE"))
    project_root = baseline._resolve_directory(PROJECT_ROOT, "项目根目录")
    if not baseline._git_is_clean(project_root):
        raise UnsafeTestEnvironment("候选运行要求干净工作树")

    manifest_path = baseline._resolve_file(FROZEN_MANIFEST, "冻结清单")
    manifest = FrozenInputManifest.load(manifest_path).validate(Path(args.input_root))
    reference = baseline._resolve_directory(Path(args.reference), "冻结参考输出")
    evidence = _load_json(SEALED_EVIDENCE, "封存证据")
    OutputContract.load(OUTPUT_CONTRACT, evidence_path=SEALED_EVIDENCE)
    _validate_reference_against_evidence(reference, evidence)
    resolver = _reference_resolver(reference)
    _validate_resolver_against_evidence(resolver, evidence)

    allow_root = baseline._resolve_directory(Path(args.allow_output_root), "输出白名单根")
    requested_output = Path(args.output)
    if not requested_output.is_absolute():
        raise UnsafeTestEnvironment("候选输出路径必须是绝对路径")
    output_root = create_unique_test_output(
        allow_root=allow_root,
        requested=requested_output,
        project_root=project_root,
        input_root=manifest.input_root,
        forbidden_roots=(reference,),
    )
    paths = PipelinePaths.create(output_root)

    profile = baseline._resolve_file(SANDBOX_PROFILE, "macOS 沙箱策略")
    if not SANDBOX_EXECUTABLE.is_file():
        raise UnsafeTestEnvironment(f"缺少 macOS sandbox-exec: {SANDBOX_EXECUTABLE}")
    if not PYTHON_EXECUTABLE.is_file():
        raise UnsafeTestEnvironment(f"缺少冻结 Python: {PYTHON_EXECUTABLE}")
    profile_sha = baseline._sha256_file(profile)
    git_executable = baseline._resolve_real_git()
    git_sha = baseline._sha256_file(git_executable)
    compatibility = stage_legacy_local_limit_config(manifest, project_root)

    child_argv = [
        str(SANDBOX_EXECUTABLE),
        "-D",
        f"OUTPUT_ROOT={output_root}",
        "-f",
        str(profile),
        str(PYTHON_EXECUTABLE),
        str(RUNNER_PATH),
        "--sandboxed-child",
        "--input-root",
        str(manifest.input_root),
        "--allow-output-root",
        str(allow_root),
        "--output",
        str(output_root),
        "--output-root",
        str(output_root),
        "--reference",
        str(reference),
        "--sandbox-profile-sha256",
        profile_sha,
        "--git-executable",
        str(git_executable),
        "--git-executable-sha256",
        git_sha,
        "--compatibility-limit-config",
        str(compatibility.path),
        "--compatibility-limit-config-sha256",
        compatibility.sha256,
    ]
    try:
        completed = subprocess.run(
            child_argv,
            cwd=project_root,
            env=_candidate_child_environment(paths),
            check=False,
        )
    finally:
        cleanup_legacy_local_limit_config(compatibility)
    return completed.returncode


def _candidate_child_environment(paths: PipelinePaths) -> dict[str, str]:
    environment = baseline._child_environment(paths)
    environment["LIMIT_MONITOR_FROZEN_WIND_RESULT"] = "1"
    return environment


def _run_sandboxed_child(args: argparse.Namespace) -> int:
    baseline._require_args(
        args,
        "input_root",
        "allow_output_root",
        "output",
        "output_root",
        "reference",
        "sandbox_profile_sha256",
        "git_executable",
        "git_executable_sha256",
        "compatibility_limit_config",
        "compatibility_limit_config_sha256",
    )
    output_root = Path(args.output_root).absolute()
    completed_guards: list[str] = []
    try:
        assert_test_environment(os.environ.get("ENV"), os.environ.get("LIMIT_MONITOR_PROFILE"))
        completed_guards.append("test_environment")
        project_root = baseline._resolve_directory(PROJECT_ROOT, "项目根目录")
        paths = PipelinePaths.load_existing(output_root)
        output_root, allow_root = baseline._validate_output_containment(
            paths.root,
            Path(args.allow_output_root),
        )
        if Path(args.output).absolute() != output_root:
            raise UnsafeTestEnvironment("候选输出参数不一致")
        completed_guards.append("prepared_output")

        profile = baseline._validate_profile(
            SANDBOX_PROFILE,
            args.sandbox_profile_sha256,
        )
        git_executable = baseline._validate_binary(
            Path(args.git_executable),
            "Git",
            args.git_executable_sha256,
        )
        compatibility = baseline._validate_legacy_local_compatibility(
            Path(args.compatibility_limit_config),
            args.compatibility_limit_config_sha256,
            project_root,
        )
        completed_guards.append("fixed_runtime")

        if not baseline._git_is_clean(project_root, git_executable):
            raise UnsafeTestEnvironment("沙箱候选进程要求干净工作树")
        if not baseline._git_baseline_is_ancestor(project_root, git_executable):
            raise UnsafeTestEnvironment("当前候选提交不包含冻结上线基线")
        candidate_sha = baseline._git_head(project_root, git_executable)
        source_diff = _source_diff_evidence(project_root, git_executable, candidate_sha)
        completed_guards.append("source_allowlist")

        probes = baseline._run_sandbox_probes(
            output_root=output_root,
            allow_output_root=allow_root,
        )
        completed_guards.append("sandbox_probes")

        manifest_path = baseline._resolve_file(FROZEN_MANIFEST, "冻结清单")
        manifest = FrozenInputManifest.load(manifest_path).validate(Path(args.input_root))
        reference = baseline._resolve_directory(Path(args.reference), "冻结参考输出")
        evidence = _load_json(SEALED_EVIDENCE, "封存证据")
        contract = OutputContract.load(OUTPUT_CONTRACT, evidence_path=SEALED_EVIDENCE)
        _validate_reference_against_evidence(reference, evidence)
        resolver = _reference_resolver(reference)
        _validate_resolver_against_evidence(resolver, evidence)
        completed_guards.append("frozen_authorities")

        protected_paths = baseline._unique_protected_paths(
            (
                manifest.input_root,
                reference,
                project_root / "data",
                compatibility,
            )
        )
        protected_before = {
            str(path): inventory_tree(path)
            for path in protected_paths
        }
        completed_guards.append("protected_before")

        config = FrozenInputConfig(
            base=ConfigLoader(config_dir=str(project_root / "config")),
            manifest=manifest,
            pipeline_root=paths.root,
            access_export_dir=paths.access_export,
        )
        stage_current_issuer_resolver(resolver, paths)
        os.chdir(paths.tmp)
        run_result = run_frozen_pipeline(
            BaselineRunRequest(
                manifest=manifest,
                config=config,
                paths=paths,
                business_date=manifest.expected_business_date,
            )
        )
        _validate_stage_result(run_result)
        completed_guards.append("pipeline_stage_order")

        stage_evidence, output_fingerprint = baseline._fingerprint_run(run_result)
        report = compare_output_trees(reference, paths.root, contract)
        _write_diff_report(paths.root / "output_diff.json", report)
        completed_guards.append("exact_output_diff")

        protected_after = {
            str(path): inventory_tree(path)
            for path in protected_paths
        }
        if not baseline._git_is_clean(project_root, git_executable):
            raise UnsafeTestEnvironment("候选运行后工作树不再干净")
        _validate_success_gate(
            report=report,
            actual_fingerprint=output_fingerprint["logical_sha256"],
            expected_fingerprint=contract.sealed_tree_logical_sha256,
            protected_before=protected_before,
            protected_after=protected_after,
        )
        completed_guards.append("success_gate")

        success = _build_success_evidence(
            manifest=baseline._manifest_evidence(manifest),
            resolver=baseline._current_issuer_resolver_evidence(resolver),
            candidate_sha=candidate_sha,
            source_diff=source_diff,
            stage_evidence=stage_evidence,
            output_fingerprint=output_fingerprint,
            report=report,
            protected_before=protected_before,
            protected_after=protected_after,
            runtime=baseline._runtime_evidence(git_executable),
            code={
                "settings_sha256": baseline._sha256_file(project_root / "config/settings.yaml"),
                "runner_sha256": baseline._sha256_file(RUNNER_PATH),
                "sandbox_profile_sha256": baseline._sha256_file(profile),
                "manifest_sha256": baseline._sha256_file(manifest_path),
                "contract_sha256": baseline._sha256_file(OUTPUT_CONTRACT),
                "sealed_evidence_sha256": baseline._sha256_file(SEALED_EVIDENCE),
            },
            sandbox_probes=probes,
        )
        _write_success_evidence(
            paths.root / "candidate_evidence.json",
            success,
            report=report,
        )
        return 0
    except Exception as exc:
        failure = {
            "schema_version": 1,
            "status": "failure",
            "exception_class": type(exc).__name__,
            "message": str(exc),
            "completed_guards": completed_guards,
        }
        try:
            baseline._atomic_write_json(output_root / "candidate_failure.json", failure)
        except Exception as write_exc:
            print(f"无法写入候选失败证据: {write_exc}", file=sys.stderr)
        print(f"sandboxed candidate failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


def _reference_resolver(reference: Path) -> ValidatedCurrentIssuerResolver:
    return validate_current_issuer_resolver(
        reference / "stage0/issuer_wind_code_mapping.csv",
        reference / "stage0/风控部债券池_主体.xlsx",
    )


def _validate_resolver_against_evidence(
    resolver: ValidatedCurrentIssuerResolver,
    evidence: dict[str, Any],
) -> None:
    sealed = evidence.get("current_issuer_resolver", {})
    mapping = sealed.get("mapping", {})
    actual_mapping = (
        resolver.mapping_sha256,
        resolver.mapping_size,
        resolver.mapping_row_count,
    )
    expected_mapping = (
        mapping.get("sha256"),
        mapping.get("size"),
        mapping.get("row_count"),
    )
    if actual_mapping != expected_mapping:
        raise UnsafeTestEnvironment("静态主体映射与封存证据不一致")

    zero_source = sealed.get("zero_result_source", {})
    actual_zero = (
        len(resolver.zero_results),
        tuple(name for name, _ in resolver.zero_results),
    )
    expected_zero = (
        zero_source.get("zero_result_count"),
        tuple(zero_source.get("issuer_names", [])),
    )
    if actual_zero != expected_zero:
        raise UnsafeTestEnvironment("显式零代码来源与封存证据不一致")


def _validate_reference_against_evidence(
    reference: Path,
    evidence: dict[str, Any],
) -> None:
    aggregate: list[dict[str, str]] = []
    for sealed_stage in evidence.get("stages", []):
        stage_name = str(sealed_stage.get("stage", ""))
        expected = str(
            sealed_stage.get("logical_fingerprint", {}).get("logical_sha256", "")
        )
        actual = fingerprint_tree(reference / stage_name)["logical_sha256"]
        if not stage_name or actual != expected:
            raise UnsafeTestEnvironment(f"冻结参考 {stage_name or '未知阶段'} 指纹不一致")
        aggregate.append({"stage": stage_name, "logical_sha256": actual})
    encoded = json.dumps(
        aggregate,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    actual_tree = hashlib.sha256(encoded).hexdigest()
    expected_tree = str(evidence.get("output_fingerprint", {}).get("logical_sha256", ""))
    if actual_tree != expected_tree:
        raise UnsafeTestEnvironment("冻结参考汇总指纹与封存证据不一致")


def _validate_source_diff_entries(
    entries: Sequence[tuple[str, str]],
) -> list[dict[str, str]]:
    validated: list[dict[str, str]] = []
    for status, path in entries:
        allowed_path = path.startswith("src/risk_core/") or path in _ALLOWED_EXACT_SOURCE_PATHS
        if status not in {"A", "M"} or not allowed_path:
            raise UnsafeTestEnvironment(
                f"生产源码差异超出计划允许范围: {status} {path}"
            )
        validated.append({"status": status, "path": path})
    return sorted(validated, key=lambda item: (item["path"], item["status"]))


def _source_diff_evidence(
    project_root: Path,
    git_executable: Path,
    candidate_sha: str,
) -> dict[str, Any]:
    name_status = baseline._git_command(
        project_root,
        ("diff", "--name-status", BASELINE_COMMIT, "HEAD", "--", *SOURCE_AUDIT_SCOPE),
        git_executable,
    )
    if name_status.returncode != 0:
        raise UnsafeTestEnvironment(f"候选源码清单 diff 失败: {name_status.stderr}")
    parsed: list[tuple[str, str]] = []
    for line in name_status.stdout.splitlines():
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) != 2:
            raise UnsafeTestEnvironment(f"候选源码差异格式超出允许范围: {line}")
        parsed.append((parts[0], parts[1]))
    changed_files = _validate_source_diff_entries(tuple(parsed))

    patch = baseline._git_command(
        project_root,
        ("diff", "--binary", BASELINE_COMMIT, "HEAD", "--", *SOURCE_AUDIT_SCOPE),
        git_executable,
    )
    if patch.returncode != 0:
        raise UnsafeTestEnvironment(f"候选源码 patch diff 失败: {patch.stderr}")
    return {
        "baseline": BASELINE_COMMIT,
        "candidate": candidate_sha,
        "changed_files": changed_files,
        "patch_sha256": hashlib.sha256(patch.stdout.encode("utf-8")).hexdigest(),
    }


def _validate_stage_result(result: BaselineRunResult) -> None:
    actual = tuple((stage.stage, len(stage.tables)) for stage in result.stages)
    if actual != EXPECTED_STAGE_COUNTS:
        raise UnsafeTestEnvironment(
            f"候选流水线必须严格按 Stage0→1→2 且表数为 10/35/22; actual={actual}"
        )


def _validate_success_gate(
    *,
    report: OutputTreeDiffReport,
    actual_fingerprint: str,
    expected_fingerprint: str,
    protected_before: dict[str, Any],
    protected_after: dict[str, Any],
) -> None:
    if not report.passed:
        raise UnsafeTestEnvironment("候选输出未通过生产输出零差异门")
    if actual_fingerprint != expected_fingerprint:
        raise UnsafeTestEnvironment("候选输出未命中封存指纹")
    if protected_before != protected_after:
        raise UnsafeTestEnvironment("受保护输入、参考、数据库或归档目录发生变化")


def _build_success_evidence(
    *,
    manifest: dict[str, Any],
    resolver: dict[str, Any],
    candidate_sha: str,
    source_diff: dict[str, Any],
    stage_evidence: list[dict[str, Any]],
    output_fingerprint: dict[str, Any],
    report: OutputTreeDiffReport,
    protected_before: dict[str, Any],
    protected_after: dict[str, Any],
    runtime: dict[str, Any],
    code: dict[str, Any],
    sandbox_probes: dict[str, str],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "success",
        "authority": {
            "manifest": manifest,
            "static_issuer_resolver": resolver,
        },
        "git": {
            "baseline": BASELINE_COMMIT,
            "candidate": candidate_sha,
            "source_diff": source_diff,
        },
        "runtime": runtime,
        "code": code,
        "sandbox_probes": sandbox_probes,
        "io_exclusions": {
            "database": True,
            "wind": True,
            "archive_write": True,
            "current_data_input": True,
        },
        "protected_before": protected_before,
        "protected_after": protected_after,
        "protected_unchanged": protected_before == protected_after,
        "stages": stage_evidence,
        "output_fingerprint": output_fingerprint,
        "diff": report.to_dict(),
    }


def _write_success_evidence(
    path: Path,
    payload: dict[str, Any],
    *,
    report: OutputTreeDiffReport,
) -> None:
    if not report.passed or payload.get("status") != "success":
        raise UnsafeTestEnvironment("禁止为失败结果写入成功证据")
    baseline._atomic_write_json(path, payload)


def _write_diff_report(path: Path, report: OutputTreeDiffReport) -> None:
    baseline._atomic_write_json(path, report.to_dict())


def _load_json(path: Path, label: str) -> dict[str, Any]:
    resolved = baseline._resolve_file(path, label)
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise UnsafeTestEnvironment(f"无法读取{label}: {exc}") from exc
    if not isinstance(payload, dict):
        raise UnsafeTestEnvironment(f"{label}必须是 JSON 对象")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
