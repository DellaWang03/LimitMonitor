"""Recreate the deployed local config path for an isolated worktree run."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import stat

from .frozen_manifest import ValidatedInputManifest


_FILE_NAME = "限额配置_当前.xlsx"
_LOCAL_DIRECTORY = "data_source_0123"


class LegacyLocalCompatibilityError(RuntimeError):
    """The deployed local path cannot be staged or removed without ambiguity."""


@dataclass(frozen=True)
class StagedLegacyLocalLimitConfig:
    path: Path
    directory: Path
    size: int
    sha256: str


def stage_legacy_local_limit_config(
    manifest: ValidatedInputManifest,
    project_root: Path | str,
) -> StagedLegacyLocalLimitConfig:
    """Stage the one ignored local file read by a nested production ConfigLoader."""

    project = _resolve_directory(Path(project_root), "项目根目录")
    expected = next((file for file in manifest.files if file.name == _FILE_NAME), None)
    if expected is None:
        raise LegacyLocalCompatibilityError(f"冻结清单缺少 {_FILE_NAME}")
    source = manifest.input_root / _FILE_NAME
    if source.is_symlink() or not source.is_file():
        raise LegacyLocalCompatibilityError(f"冻结限额配置不是普通文件: {source}")

    directory = project / _LOCAL_DIRECTORY
    target = directory / _FILE_NAME
    if directory.exists() or directory.is_symlink():
        raise LegacyLocalCompatibilityError(f"本地兼容目录已存在: {directory}")
    try:
        directory.mkdir(mode=0o700, parents=False, exist_ok=False)
        _copy_verified(
            source,
            target,
            expected_size=expected.size,
            expected_sha256=expected.sha256,
        )
    except Exception:
        try:
            if target.is_file() and not target.is_symlink():
                target.unlink()
            directory.rmdir()
        except OSError:
            pass
        raise
    return StagedLegacyLocalLimitConfig(
        path=target,
        directory=directory,
        size=expected.size,
        sha256=expected.sha256,
    )


def cleanup_legacy_local_limit_config(
    staged: StagedLegacyLocalLimitConfig,
) -> None:
    """Remove only the unchanged compatibility file and its otherwise-empty directory."""

    directory = staged.directory
    target = staged.path
    if directory.is_symlink() or not directory.is_dir():
        raise LegacyLocalCompatibilityError(
            f"本地兼容目录在清理前发生变化: {directory}"
        )
    entries = tuple(directory.iterdir())
    if entries != (target,):
        raise LegacyLocalCompatibilityError(
            f"本地兼容目录在清理前发生变化: {[entry.name for entry in entries]}"
        )
    if target.is_symlink() or not target.is_file():
        raise LegacyLocalCompatibilityError(
            f"本地兼容限额配置在清理前发生变化: {target}"
        )
    if target.stat().st_size != staged.size or _sha256_file(target) != staged.sha256:
        raise LegacyLocalCompatibilityError(
            f"本地兼容限额配置在运行期间发生变化: {target}"
        )
    target.unlink()
    directory.rmdir()


def _resolve_directory(path: Path, label: str) -> Path:
    if path.is_symlink():
        raise LegacyLocalCompatibilityError(f"{label}不得为符号链接: {path}")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise LegacyLocalCompatibilityError(f"{label}不存在: {path}") from exc
    if not resolved.is_dir():
        raise LegacyLocalCompatibilityError(f"{label}不是目录: {resolved}")
    return resolved


def _copy_verified(
    source: Path,
    target: Path,
    *,
    expected_size: int,
    expected_sha256: str,
) -> None:
    source_fd: int | None = None
    target_fd: int | None = None
    digest = hashlib.sha256()
    total = 0
    try:
        source_fd = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        metadata = os.fstat(source_fd)
        if not stat.S_ISREG(metadata.st_mode):
            raise LegacyLocalCompatibilityError(f"冻结限额配置不再是普通文件: {source}")
        target_fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        while True:
            chunk = os.read(source_fd, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            total += len(chunk)
            view = memoryview(chunk)
            while view:
                written = os.write(target_fd, view)
                view = view[written:]
        os.fsync(target_fd)
    except FileExistsError as exc:
        raise LegacyLocalCompatibilityError(f"本地兼容目标已存在: {target}") from exc
    except OSError as exc:
        raise LegacyLocalCompatibilityError(f"复制本地兼容限额配置失败: {exc}") from exc
    finally:
        if source_fd is not None:
            os.close(source_fd)
        if target_fd is not None:
            os.close(target_fd)
    if total != expected_size or digest.hexdigest() != expected_sha256:
        try:
            target.unlink()
        except OSError:
            pass
        raise LegacyLocalCompatibilityError("复制期间冻结限额配置发生变化")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    descriptor: int | None = None
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise LegacyLocalCompatibilityError(f"哈希目标不是普通文件: {path}")
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = None
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise LegacyLocalCompatibilityError(f"无法哈希本地兼容文件: {path}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
    return digest.hexdigest()
