#!/opt/homebrew/bin/python3
"""Run the deployed pipeline against frozen input inside a macOS sandbox."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import errno
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import socket
import subprocess
import sys
from typing import Any, Sequence
import uuid


RUNNER_PATH = Path(__file__).resolve()
PROJECT_ROOT = RUNNER_PATH.parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.pipeline.execution import BaselineRunRequest, BaselineRunResult, run_frozen_pipeline
from src.pipeline.paths import PipelinePaths
from src.testing.frozen_config import FrozenInputConfig
from src.testing.frozen_manifest import FrozenInputManifest, ValidatedInputManifest
from src.testing.output_fingerprint import fingerprint_tree
from src.testing.protected_inventory import inventory_tree
from src.testing.safe_paths import create_unique_test_output
from src.testing.test_environment import UnsafeTestEnvironment, assert_test_environment
from src.utils.config_loader import ConfigLoader


BASELINE_COMMIT = "579af695fb8727dec8249f66d07a8b0e723da137"
PYTHON_EXECUTABLE = Path("/opt/homebrew/bin/python3")
SANDBOX_EXECUTABLE = Path("/usr/bin/sandbox-exec")
DEFAULT_GIT_EXECUTABLE = Path("/usr/bin/git")
SANDBOX_PROFILE = PROJECT_ROOT / "config/test_manifests/frozen-baseline-macos.sb"
PRODUCTION_SCOPE = (
    "src/stage0",
    "src/stage1",
    "src/stage2",
    "src/common",
    "src/utils",
    "config/settings.yaml",
    "scripts/daily_archive.py",
)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        if args.sandbox_probe_only:
            return _run_probe_only(args)
        if args.sandboxed_child:
            return _run_sandboxed_child(args)
        return _run_parent(args)
    except Exception as exc:
        print(f"frozen-baseline error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root")
    parser.add_argument("--manifest")
    parser.add_argument("--allow-output-root", required=True)
    parser.add_argument("--output-name")
    parser.add_argument("--project-root")
    parser.add_argument("--protected-root", action="append", default=[])
    parser.add_argument("--sandboxed-child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--sandbox-probe-only", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--output-root", help=argparse.SUPPRESS)
    parser.add_argument("--sandbox-profile", help=argparse.SUPPRESS)
    parser.add_argument("--sandbox-profile-sha256", help=argparse.SUPPRESS)
    parser.add_argument("--git-executable", help=argparse.SUPPRESS)
    parser.add_argument("--git-executable-sha256", help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def _run_parent(args: argparse.Namespace) -> int:
    _require_args(
        args,
        "input_root",
        "manifest",
        "output_name",
        "project_root",
    )
    assert_test_environment(os.environ.get("ENV"), os.environ.get("LIMIT_MONITOR_PROFILE"))
    project_root = _resolve_directory(Path(args.project_root), "项目根目录")
    if not _git_is_clean(project_root):
        raise UnsafeTestEnvironment("基线运行要求干净工作树")

    manifest_path = _resolve_file(Path(args.manifest), "冻结清单")
    validated = FrozenInputManifest.load(manifest_path).validate(Path(args.input_root))
    allow_output_root = _resolve_directory(Path(args.allow_output_root), "输出白名单根")
    output_root = create_unique_test_output(
        allow_root=allow_output_root,
        requested=allow_output_root / args.output_name,
        project_root=project_root,
        input_root=validated.input_root,
    )
    paths = PipelinePaths.create(output_root)

    profile = _resolve_file(SANDBOX_PROFILE, "macOS 沙箱策略")
    if not SANDBOX_EXECUTABLE.is_file():
        raise UnsafeTestEnvironment(f"缺少 macOS sandbox-exec: {SANDBOX_EXECUTABLE}")
    if not PYTHON_EXECUTABLE.is_file():
        raise UnsafeTestEnvironment(f"缺少冻结 Python: {PYTHON_EXECUTABLE}")
    profile_sha = _sha256_file(profile)
    git_executable = _resolve_real_git()
    git_sha = _sha256_file(git_executable)

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
        str(validated.input_root),
        "--manifest",
        str(manifest_path),
        "--allow-output-root",
        str(allow_output_root),
        "--output-name",
        args.output_name,
        "--output-root",
        str(output_root),
        "--project-root",
        str(project_root),
        "--sandbox-profile",
        str(profile),
        "--sandbox-profile-sha256",
        profile_sha,
        "--git-executable",
        str(git_executable),
        "--git-executable-sha256",
        git_sha,
    ]
    for protected in args.protected_root:
        child_argv.extend(("--protected-root", str(Path(protected).absolute())))

    completed = subprocess.run(
        child_argv,
        cwd=project_root,
        env=_child_environment(paths),
        check=False,
    )
    return completed.returncode


def _run_probe_only(args: argparse.Namespace) -> int:
    _require_args(args, "output_root", "sandbox_profile", "sandbox_profile_sha256")
    assert_test_environment(os.environ.get("ENV"), os.environ.get("LIMIT_MONITOR_PROFILE"))
    output_root, allow_root = _validate_output_containment(
        Path(args.output_root),
        Path(args.allow_output_root),
    )
    _validate_profile(Path(args.sandbox_profile), args.sandbox_profile_sha256)
    _run_sandbox_probes(output_root=output_root, allow_output_root=allow_root)
    return 0


def _run_sandboxed_child(args: argparse.Namespace) -> int:
    _require_args(
        args,
        "input_root",
        "manifest",
        "output_root",
        "project_root",
        "sandbox_profile",
        "sandbox_profile_sha256",
        "git_executable",
        "git_executable_sha256",
    )
    output_root = Path(args.output_root).absolute()
    completed_guards: list[str] = []
    try:
        assert_test_environment(os.environ.get("ENV"), os.environ.get("LIMIT_MONITOR_PROFILE"))
        completed_guards.append("test_environment")
        project_root = _resolve_directory(Path(args.project_root), "项目根目录")
        paths = PipelinePaths.load_existing(output_root)
        output_root, allow_root = _validate_output_containment(
            paths.root,
            Path(args.allow_output_root),
        )
        completed_guards.append("prepared_output")
        profile = _validate_profile(
            Path(args.sandbox_profile),
            args.sandbox_profile_sha256,
        )
        completed_guards.append("sandbox_profile")
        git_executable = _validate_binary(
            Path(args.git_executable),
            "Git",
            args.git_executable_sha256,
        )
        completed_guards.append("git_binary")

        git_head = _git_head(project_root, git_executable)
        clean_before = _git_is_clean(project_root, git_executable)
        if not clean_before:
            raise UnsafeTestEnvironment("沙箱子进程要求干净工作树")
        baseline_is_ancestor = _git_baseline_is_ancestor(project_root, git_executable)
        if not baseline_is_ancestor:
            raise UnsafeTestEnvironment("当前提交不包含冻结上线基线")
        production_diff_empty = _git_production_scope_diff_empty(
            project_root,
            git_executable,
        )
        if not production_diff_empty:
            raise UnsafeTestEnvironment("生产计算范围相对上线基线存在差异")
        completed_guards.append("git_baseline")

        probes = _run_sandbox_probes(
            output_root=output_root,
            allow_output_root=allow_root,
        )
        completed_guards.append("sandbox_probes")
        manifest_path = _resolve_file(Path(args.manifest), "冻结清单")
        manifest = FrozenInputManifest.load(manifest_path).validate(Path(args.input_root))
        completed_guards.append("manifest")

        protected_paths = _unique_protected_paths(
            [manifest.input_root, *(Path(path) for path in args.protected_root)]
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
        os.chdir(paths.tmp)
        run_result = run_frozen_pipeline(
            BaselineRunRequest(
                manifest=manifest,
                config=config,
                paths=paths,
                business_date=manifest.expected_business_date,
            )
        )
        completed_guards.append("pipeline")

        stage_evidence, output_fingerprint = _fingerprint_run(run_result)
        protected_after = {
            str(path): inventory_tree(path)
            for path in protected_paths
        }
        protected_unchanged = protected_before == protected_after
        if not protected_unchanged:
            raise UnsafeTestEnvironment("受保护目录在基线运行期间发生变化")
        if not _git_is_clean(project_root, git_executable):
            raise UnsafeTestEnvironment("基线运行后工作树不再干净")
        completed_guards.append("protected_after")

        evidence = {
            "schema_version": 1,
            "status": "success",
            "manifest": _manifest_evidence(manifest),
            "git": {
                "head": git_head,
                "baseline": BASELINE_COMMIT,
                "baseline_is_ancestor": baseline_is_ancestor,
                "worktree_clean_before": clean_before,
                "worktree_clean_after": True,
            },
            "runtime": _runtime_evidence(git_executable),
            "code": {
                "settings_sha256": _sha256_file(project_root / "config/settings.yaml"),
                "runner_sha256": _sha256_file(RUNNER_PATH),
                "sandbox_profile_sha256": _sha256_file(profile),
                "production_scope_diff_is_empty": production_diff_empty,
            },
            "sandbox_probes": probes,
            "protected_before": protected_before,
            "protected_after": protected_after,
            "protected_unchanged": protected_unchanged,
            "stages": stage_evidence,
            "output_fingerprint": output_fingerprint,
        }
        _atomic_write_json(paths.root / "baseline_evidence.json", evidence)
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
            _atomic_write_json(output_root / "baseline_failure.json", failure)
        except Exception as write_exc:
            print(f"无法写入失败证据: {write_exc}", file=sys.stderr)
        print(f"sandboxed baseline failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


def _run_sandbox_probes(*, output_root: Path, allow_output_root: Path) -> dict[str, str]:
    token = f"{os.getpid()}-{uuid.uuid4().hex}"
    inside = output_root / f".inside-write-probe-{token}"
    inside.write_text("inside", encoding="utf-8")
    inside.unlink()

    outside = allow_output_root / f".outside-write-probe-{token}"
    try:
        outside.write_text("outside", encoding="utf-8")
    except OSError as exc:
        if exc.errno not in {errno.EPERM, errno.EACCES}:
            raise UnsafeTestEnvironment(f"输出外写入探针异常: {exc}") from exc
    else:
        try:
            outside.unlink()
        finally:
            raise UnsafeTestEnvironment("输出外写入未被沙箱拒绝")

    network = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        network.bind(("127.0.0.1", 0))
    except OSError as exc:
        if exc.errno not in {errno.EPERM, errno.EACCES}:
            raise UnsafeTestEnvironment(f"网络探针异常: {exc}") from exc
    else:
        raise UnsafeTestEnvironment("loopback bind 未被沙箱拒绝")
    finally:
        network.close()

    _mdb_export_info()
    return {
        "inside_write": "allowed",
        "outside_write": "denied",
        "loopback_bind": "denied",
    }


def _child_environment(paths: PipelinePaths) -> dict[str, str]:
    return {
        "ENV": "test",
        "GIT_OPTIONAL_LOCKS": "0",
        "HOME": str(paths.home),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "LIMIT_MONITOR_PROFILE": "local",
        "PATH": "/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUNBUFFERED": "1",
        "TMPDIR": str(paths.tmp),
    }


def _fingerprint_run(
    result: BaselineRunResult,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    stages: list[dict[str, Any]] = []
    aggregate_items: list[dict[str, str]] = []
    for stage in result.stages:
        fingerprint = fingerprint_tree(stage.output_dir)
        stages.append(
            {
                "stage": stage.stage,
                "table_count": len(stage.tables),
                "tables": [asdict(table) for table in stage.tables],
                "logical_fingerprint": fingerprint,
            }
        )
        aggregate_items.append(
            {"stage": stage.stage, "logical_sha256": fingerprint["logical_sha256"]}
        )
    encoded = json.dumps(
        aggregate_items,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return stages, {
        "schema_version": 1,
        "logical_sha256": hashlib.sha256(encoded).hexdigest(),
        "stages": aggregate_items,
    }


def _manifest_evidence(manifest: ValidatedInputManifest) -> dict[str, Any]:
    return {
        "id": manifest.manifest_id,
        "business_date": manifest.expected_business_date.isoformat(),
        "files": [asdict(file) for file in manifest.files],
    }


def _runtime_evidence(git_executable: Path) -> dict[str, Any]:
    if Path(sys.executable).resolve() != PYTHON_EXECUTABLE.resolve():
        raise UnsafeTestEnvironment(
            f"Python 可执行文件不符合冻结要求: {sys.executable}"
        )
    dependencies = {
        name: importlib.metadata.version(name)
        for name in ("pandas", "openpyxl", "numpy", "PyYAML", "loguru")
    }
    return {
        "python_executable": str(PYTHON_EXECUTABLE),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "environment": "test",
        "profile": "local",
        "dependencies": dependencies,
        "mdb_export": _mdb_export_info(),
        "git": _git_info(git_executable),
    }


def _mdb_export_info() -> dict[str, Any]:
    binary = shutil.which("mdb-export")
    if not binary:
        raise UnsafeTestEnvironment("PATH 中未找到 mdb-export")
    path = _resolve_file(Path(binary), "mdb-export", allow_symlink=True)
    completed = subprocess.run(
        [str(path), "--version"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if completed.returncode != 0:
        raise UnsafeTestEnvironment(
            f"mdb-export --version 失败: {completed.stderr or completed.stdout}"
        )
    version = (completed.stdout or completed.stderr).strip()
    return {
        "path": str(path),
        "version": version,
        "binary_sha256": _sha256_file(path),
    }


def _validate_output_containment(output: Path, allow: Path) -> tuple[Path, Path]:
    output_root = _resolve_directory(output, "唯一输出根")
    allow_root = _resolve_directory(allow, "输出白名单根")
    if output_root == allow_root or not output_root.is_relative_to(allow_root):
        raise UnsafeTestEnvironment("唯一输出根不在白名单根内")
    return output_root, allow_root


def _validate_profile(path: Path, expected_sha: str) -> Path:
    profile = _resolve_file(path, "macOS 沙箱策略")
    actual_sha = _sha256_file(profile)
    if actual_sha != expected_sha:
        raise UnsafeTestEnvironment(
            f"沙箱策略哈希不一致: expected={expected_sha}; actual={actual_sha}"
        )
    return profile


def _validate_binary(path: Path, label: str, expected_sha: str) -> Path:
    binary = _resolve_file(path, label, allow_symlink=True)
    actual_sha = _sha256_file(binary)
    if actual_sha != expected_sha:
        raise UnsafeTestEnvironment(
            f"{label} 二进制哈希不一致: expected={expected_sha}; actual={actual_sha}"
        )
    return binary


def _resolve_directory(path: Path, label: str) -> Path:
    if path.is_symlink():
        raise UnsafeTestEnvironment(f"{label}不得为符号链接: {path}")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise UnsafeTestEnvironment(f"{label}不存在: {path}") from exc
    if not resolved.is_dir():
        raise UnsafeTestEnvironment(f"{label}不是目录: {resolved}")
    return resolved


def _resolve_file(path: Path, label: str, *, allow_symlink: bool = False) -> Path:
    if path.is_symlink() and not allow_symlink:
        raise UnsafeTestEnvironment(f"{label}不得为符号链接: {path}")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise UnsafeTestEnvironment(f"{label}不存在: {path}") from exc
    if not resolved.is_file():
        raise UnsafeTestEnvironment(f"{label}不是文件: {resolved}")
    return resolved


def _unique_protected_paths(paths: Sequence[Path]) -> tuple[Path, ...]:
    unique: dict[str, Path] = {}
    for path in paths:
        absolute = path.absolute()
        unique[str(absolute)] = absolute
    return tuple(unique[key] for key in sorted(unique))


def _require_args(args: argparse.Namespace, *names: str) -> None:
    missing = [name for name in names if not getattr(args, name, None)]
    if missing:
        raise UnsafeTestEnvironment(f"缺少参数: {', '.join(missing)}")


def _git_command(
    project_root: Path,
    arguments: Sequence[str],
    git_executable: Path = DEFAULT_GIT_EXECUTABLE,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            str(git_executable),
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.untrackedCache=false",
            *arguments,
        ],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
        env={
            "GIT_OPTIONAL_LOCKS": "0",
            "HOME": os.environ.get("HOME", str(project_root)),
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        },
    )


def _git_is_clean(
    project_root: Path,
    git_executable: Path = DEFAULT_GIT_EXECUTABLE,
) -> bool:
    completed = _git_command(
        project_root,
        ("status", "--porcelain=v1", "--untracked-files=all", "--no-ahead-behind"),
        git_executable,
    )
    if completed.returncode != 0:
        raise UnsafeTestEnvironment(f"git status 失败: {completed.stderr}")
    return not completed.stdout


def _git_head(project_root: Path, git_executable: Path) -> str:
    completed = _git_command(project_root, ("rev-parse", "HEAD"), git_executable)
    if completed.returncode != 0:
        raise UnsafeTestEnvironment(f"git rev-parse 失败: {completed.stderr}")
    return completed.stdout.strip()


def _git_baseline_is_ancestor(project_root: Path, git_executable: Path) -> bool:
    completed = _git_command(
        project_root,
        ("merge-base", "--is-ancestor", BASELINE_COMMIT, "HEAD"),
        git_executable,
    )
    if completed.returncode not in {0, 1}:
        raise UnsafeTestEnvironment(f"git merge-base 失败: {completed.stderr}")
    return completed.returncode == 0


def _git_production_scope_diff_empty(project_root: Path, git_executable: Path) -> bool:
    completed = _git_command(
        project_root,
        ("diff", "--exit-code", BASELINE_COMMIT, "--", *PRODUCTION_SCOPE),
        git_executable,
    )
    if completed.returncode not in {0, 1}:
        raise UnsafeTestEnvironment(f"git diff 失败: {completed.stderr}")
    return completed.returncode == 0


def _resolve_real_git() -> Path:
    completed = subprocess.run(
        ["/usr/bin/xcrun", "--find", "git"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0 or not completed.stdout.strip():
        raise UnsafeTestEnvironment(f"无法解析真实 Git: {completed.stderr}")
    return _resolve_file(Path(completed.stdout.strip()), "真实 Git")


def _git_info(git_executable: Path) -> dict[str, str]:
    completed = subprocess.run(
        [str(git_executable), "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise UnsafeTestEnvironment(f"git --version 失败: {completed.stderr}")
    return {
        "path": str(git_executable),
        "version": completed.stdout.strip(),
        "binary_sha256": _sha256_file(git_executable),
    }


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    if path.parent.is_symlink() or not path.parent.is_dir():
        raise UnsafeTestEnvironment(f"证据父目录无效: {path.parent}")
    temporary = path.parent / f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary.exists():
            temporary.unlink()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
