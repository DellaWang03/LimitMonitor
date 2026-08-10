"""Create a new test-output directory without crossing protected roots."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable


class UnsafeTestPath(RuntimeError):
    """A requested test path is missing, shared, overlapping or redirected."""


def _existing_directory(path: Path, label: str) -> Path:
    if path.is_symlink():
        raise UnsafeTestPath(f"{label}不得为符号链接: {path}")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise UnsafeTestPath(f"{label}不存在: {path}") from exc
    if not resolved.is_dir():
        raise UnsafeTestPath(f"{label}不是目录: {resolved}")
    return resolved


def _overlaps(left: Path, right: Path) -> bool:
    return left == right or left.is_relative_to(right) or right.is_relative_to(left)


def create_unique_test_output(
    *,
    allow_root: Path | str,
    requested: Path | str,
    project_root: Path | str,
    input_root: Path | str,
    forbidden_roots: Iterable[Path | str] = (),
) -> Path:
    """Create exactly one mode-0700 output directory and return its realpath."""

    allow = _existing_directory(Path(allow_root), "输出白名单根")
    project = _existing_directory(Path(project_root), "项目根目录")
    source = _existing_directory(Path(input_root), "输入目录")

    forbidden: list[Path] = [project, project / "data", Path("/Volumes")]
    for raw in forbidden_roots:
        path = Path(raw)
        try:
            forbidden.append(path.resolve(strict=True))
        except OSError:
            forbidden.append(path.resolve(strict=False))

    for root in forbidden:
        if allow == root or allow.is_relative_to(root):
            raise UnsafeTestPath(f"输出白名单根位于禁止目录: {root}")

    requested_path = Path(requested)
    if os.path.lexists(requested_path):
        raise UnsafeTestPath(f"输出路径已存在: {requested_path}")
    if requested_path.name in {"", ".", ".."}:
        raise UnsafeTestPath(f"输出路径名称无效: {requested_path}")
    if requested_path.parent.is_symlink():
        raise UnsafeTestPath(f"输出父目录不得为符号链接: {requested_path.parent}")
    try:
        parent = requested_path.parent.resolve(strict=True)
    except OSError as exc:
        raise UnsafeTestPath(f"输出父目录不存在: {requested_path.parent}") from exc

    candidate = parent / requested_path.name
    if candidate == allow or not candidate.is_relative_to(allow):
        raise UnsafeTestPath(f"输出路径逃逸白名单根: {candidate}")
    if _overlaps(candidate, source):
        raise UnsafeTestPath(f"输出路径与输入目录重叠: {candidate}")

    candidate.mkdir(mode=0o700, parents=False, exist_ok=False)
    try:
        resolved = candidate.resolve(strict=True)
        if resolved != candidate or not resolved.is_relative_to(allow):
            raise UnsafeTestPath(f"创建后的输出路径逃逸白名单根: {resolved}")
        if _overlaps(resolved, source):
            raise UnsafeTestPath(f"创建后的输出路径与输入目录重叠: {resolved}")
        if resolved.stat().st_mode & 0o777 != 0o700:
            os.chmod(resolved, 0o700)
        return resolved
    except Exception:
        try:
            candidate.rmdir()
        except OSError:
            pass
        raise
