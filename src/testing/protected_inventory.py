"""Byte-level, non-following inventories for paths that must not change."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import stat
from typing import Any


class InventoryError(RuntimeError):
    """A protected path could not be inventoried without ambiguity."""


_IGNORED_PLATFORM_METADATA = frozenset({".DS_Store"})


def inventory_tree(root: Path | str) -> dict[str, Any]:
    path = Path(root).absolute()
    try:
        root_stat = path.lstat()
    except FileNotFoundError:
        return {
            "root": str(path),
            "exists": False,
            "root_type": "missing",
            "entries": [],
        }
    except OSError as exc:
        raise InventoryError(f"无法读取受保护根路径: {path}") from exc

    root_type = _entry_type(root_stat.st_mode)
    result: dict[str, Any] = {
        "root": str(path),
        "exists": True,
        "root_type": root_type,
        "root_mode": _mode(root_stat.st_mode),
        "entries": [],
    }
    if root_type == "symlink":
        result["root_target"] = os.readlink(path)
        return result
    if root_type == "file":
        result["root_size"] = root_stat.st_size
        result["root_sha256"] = _sha256_file(path)
        return result
    if root_type != "directory":
        return result

    entries: list[dict[str, Any]] = []
    _inventory_directory(path, path, entries)
    entries.sort(key=lambda item: item["path"])
    result["entries"] = entries
    return result


def _inventory_directory(root: Path, directory: Path, target: list[dict[str, Any]]) -> None:
    try:
        children = sorted(os.scandir(directory), key=lambda item: item.name)
    except OSError as exc:
        raise InventoryError(f"无法遍历受保护目录: {directory}") from exc
    for child in children:
        if child.name in _IGNORED_PLATFORM_METADATA:
            continue
        path = Path(child.path)
        relative = path.relative_to(root).as_posix()
        try:
            metadata = child.stat(follow_symlinks=False)
        except OSError as exc:
            raise InventoryError(f"无法读取受保护条目: {relative}") from exc
        entry_type = _entry_type(metadata.st_mode)
        item: dict[str, Any] = {
            "path": relative,
            "type": entry_type,
            "mode": _mode(metadata.st_mode),
        }
        if entry_type == "symlink":
            item["target"] = os.readlink(path)
        elif entry_type == "file":
            item["size"] = metadata.st_size
            item["sha256"] = _sha256_file(path)
        elif entry_type == "directory":
            _inventory_directory(root, path, target)
        target.append(item)


def _entry_type(mode: int) -> str:
    if stat.S_ISLNK(mode):
        return "symlink"
    if stat.S_ISREG(mode):
        return "file"
    if stat.S_ISDIR(mode):
        return "directory"
    return "other"


def _mode(mode: int) -> str:
    return f"{stat.S_IMODE(mode):04o}"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    descriptor: int | None = None
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
        )
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise InventoryError(f"受保护条目哈希时不再是普通文件: {path}")
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = None
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise InventoryError(f"无法哈希受保护文件: {path}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
    return digest.hexdigest()
