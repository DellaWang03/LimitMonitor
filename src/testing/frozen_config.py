"""Config facade whose data paths are restricted to a validated manifest."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .frozen_manifest import ValidatedInputManifest


class FrozenConfigError(RuntimeError):
    """A caller attempted to escape frozen input or per-run output paths."""


class FrozenInputConfig:
    def __init__(
        self,
        base: Any,
        manifest: ValidatedInputManifest,
        pipeline_root: Path,
        access_export_dir: Path,
    ) -> None:
        self._base = base
        self._manifest = manifest
        self._allowed_names = manifest.names
        self._pipeline_root = self._resolve_directory(pipeline_root, "流水线根目录")
        self._access_export_dir = self._resolve_directory(
            access_export_dir,
            "Access 导出目录",
        )
        if (
            self._access_export_dir == self._pipeline_root
            or not self._access_export_dir.is_relative_to(self._pipeline_root)
        ):
            raise FrozenConfigError("Access 导出目录必须位于流水线根目录内")

    @staticmethod
    def _resolve_directory(path: Path | str, label: str) -> Path:
        raw = Path(path)
        if raw.is_symlink():
            raise FrozenConfigError(f"{label}不得为符号链接: {raw}")
        try:
            resolved = raw.resolve(strict=True)
        except OSError as exc:
            raise FrozenConfigError(f"{label}不存在: {raw}") from exc
        if not resolved.is_dir():
            raise FrozenConfigError(f"{label}不是目录: {resolved}")
        return resolved

    @property
    def manifest(self) -> ValidatedInputManifest:
        return self._manifest

    def get(self, key_path: str, default: Any = None) -> Any:
        return self._base.get(key_path, default)

    def get_limit(self, key_path: str, default: Any = None) -> Any:
        return self._base.get_limit(key_path, default)

    def load_settings(self) -> dict[str, Any]:
        return self._base.load_settings()

    def load_limits(self) -> dict[str, Any]:
        return self._base.load_limits()

    def get_active_profile(self) -> str:
        return "local"

    def get_data_dir(self) -> Path:
        return self._manifest.input_root

    def get_data_file_path(self, file_name: str) -> Path:
        if file_name not in self._allowed_names:
            raise FrozenConfigError(f"文件不在冻结清单中: {file_name}")
        raw = self._manifest.input_root / file_name
        if raw.is_symlink():
            raise FrozenConfigError(f"冻结输入文件变为符号链接: {file_name}")
        try:
            resolved = raw.resolve(strict=True)
        except OSError as exc:
            raise FrozenConfigError(f"冻结输入文件不存在: {file_name}") from exc
        if resolved.parent != self._manifest.input_root or not resolved.is_file():
            raise FrozenConfigError(f"冻结输入文件逃逸或类型无效: {file_name}")
        return resolved

    def get_data_file_path_without_override(self, file_name: str) -> Path:
        return self.get_data_file_path(file_name)

    def get_data_config_source_dir(self) -> Path:
        return self._access_export_dir
