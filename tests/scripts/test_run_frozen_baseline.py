import hashlib
import json
import os
from datetime import date
from pathlib import Path
import subprocess
from unittest.mock import Mock

import pytest

from scripts import run_frozen_baseline as runner
from src.pipeline.execution import (
    BaselineRunResult,
    StageRunResult,
    TableRunSummary,
)
from src.pipeline.paths import PipelinePaths
from src.testing.test_environment import UnsafeTestEnvironment


def _write_tiny_manifest(tmp_path: Path) -> tuple[Path, Path]:
    source = tmp_path / "source"
    source.mkdir()
    payload = b"input"
    (source / "input.xlsx").write_bytes(payload)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "manifest_id": "tiny-v1",
                "expected_business_date": "2026-07-10",
                "files": [
                    {
                        "name": "input.xlsx",
                        "size": len(payload),
                        "sha256": hashlib.sha256(payload).hexdigest(),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return source, manifest


def _parent_args(
    source: Path,
    manifest: Path,
    allow: Path,
    project_root: Path,
) -> list[str]:
    return [
        "--input-root",
        str(source),
        "--manifest",
        str(manifest),
        "--allow-output-root",
        str(allow),
        "--output-name",
        "run-1",
        "--project-root",
        str(project_root),
        "--protected-root",
        str(project_root / "data/current"),
    ]


def test_parent_launches_only_the_sandboxed_child(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, manifest = _write_tiny_manifest(tmp_path)
    allow = tmp_path / "allow"
    allow.mkdir()
    project_root = Path(__file__).resolve().parents[2]
    monkeypatch.setenv("ENV", "test")
    monkeypatch.setenv("LIMIT_MONITOR_PROFILE", "local")
    monkeypatch.setattr(runner, "_git_is_clean", lambda root: True)
    completed = subprocess.CompletedProcess(args=[], returncode=0)
    run = Mock(return_value=completed)
    monkeypatch.setattr(runner.subprocess, "run", run)

    assert runner.main(_parent_args(source, manifest, allow, project_root)) == 0

    argv = run.call_args.args[0]
    output_root = (allow / "run-1").resolve()
    assert argv[:3] == [
        "/usr/bin/sandbox-exec",
        "-D",
        f"OUTPUT_ROOT={output_root}",
    ]
    assert argv[3:5] == ["-f", str(runner.SANDBOX_PROFILE)]
    assert "/opt/homebrew/bin/python3" in argv
    assert "--sandboxed-child" in argv
    assert "--database-url" not in argv
    assert "--archive" not in argv
    assert "--wind" not in argv
    child_env = run.call_args.kwargs["env"]
    assert child_env == {
        "ENV": "test",
        "GIT_OPTIONAL_LOCKS": "0",
        "HOME": str(output_root / "home"),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "LIMIT_MONITOR_PROFILE": "local",
        "PATH": "/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUNBUFFERED": "1",
        "TMPDIR": str(output_root / "tmp"),
    }
    PipelinePaths.load_existing(output_root)


def test_parent_propagates_nonzero_sandbox_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, manifest = _write_tiny_manifest(tmp_path)
    allow = tmp_path / "allow"
    allow.mkdir()
    project_root = Path(__file__).resolve().parents[2]
    monkeypatch.setenv("ENV", "test")
    monkeypatch.setenv("LIMIT_MONITOR_PROFILE", "local")
    monkeypatch.setattr(runner, "_git_is_clean", lambda root: True)
    monkeypatch.setattr(
        runner.subprocess,
        "run",
        Mock(return_value=subprocess.CompletedProcess(args=[], returncode=23)),
    )

    assert runner.main(_parent_args(source, manifest, allow, project_root)) == 23


def test_parent_rejects_dirty_worktree_before_creating_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, manifest = _write_tiny_manifest(tmp_path)
    allow = tmp_path / "allow"
    allow.mkdir()
    project_root = Path(__file__).resolve().parents[2]
    monkeypatch.setenv("ENV", "test")
    monkeypatch.setenv("LIMIT_MONITOR_PROFILE", "local")
    monkeypatch.setattr(runner, "_git_is_clean", lambda root: False)

    assert runner.main(_parent_args(source, manifest, allow, project_root)) == 2
    assert not (allow / "run-1").exists()


def test_live_probe_rejects_direct_unsandboxed_execution(tmp_path: Path) -> None:
    allow = tmp_path / "allow"
    output = allow / "run"
    allow.mkdir()
    output.mkdir()

    with pytest.raises(UnsafeTestEnvironment, match="输出外写入"):
        runner._run_sandbox_probes(output_root=output, allow_output_root=allow)
    assert not any(path.name.startswith(".outside-write-probe-") for path in allow.iterdir())


def test_atomic_json_replaces_complete_document(tmp_path: Path) -> None:
    target = tmp_path / "evidence.json"
    runner._atomic_write_json(target, {"status": "success", "value": "中文"})

    assert json.loads(target.read_text(encoding="utf-8")) == {
        "status": "success",
        "value": "中文",
    }
    assert list(tmp_path.glob("*.tmp")) == []


def test_stage_evidence_contains_no_absolute_output_path(tmp_path: Path) -> None:
    stage_dir = tmp_path / "stage0"
    stage_dir.mkdir()
    (stage_dir / "result.bin").write_bytes(b"result")
    result = BaselineRunResult(
        business_date=date(2026, 7, 10),
        stages=(
            StageRunResult(
                stage="stage0",
                output_dir=stage_dir,
                tables=(TableRunSummary("result", 1, 2),),
            ),
        ),
    )

    stages, fingerprint = runner._fingerprint_run(result)
    serialized = json.dumps({"stages": stages, "fingerprint": fingerprint})

    assert str(tmp_path) not in serialized
    assert stages[0]["table_count"] == 1
