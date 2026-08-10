"""Load and verify an immutable, exact input-directory manifest."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import json
from pathlib import Path
import re


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_TOP_LEVEL_KEYS = {"manifest_id", "expected_business_date", "files"}
_FILE_KEYS = {"name", "size", "sha256"}


class ManifestValidationError(RuntimeError):
    """The manifest or the directory it describes is not exactly valid."""


@dataclass(frozen=True)
class FrozenFile:
    name: str
    size: int
    sha256: str


@dataclass(frozen=True)
class ValidatedInputManifest:
    manifest_id: str
    expected_business_date: date
    input_root: Path
    files: tuple[FrozenFile, ...]

    @property
    def names(self) -> frozenset[str]:
        return frozenset(file.name for file in self.files)


@dataclass(frozen=True)
class FrozenInputManifest:
    manifest_id: str
    expected_business_date: date
    files: tuple[FrozenFile, ...]

    @classmethod
    def load(cls, path: Path | str) -> "FrozenInputManifest":
        manifest_path = Path(path)
        if manifest_path.is_symlink():
            raise ManifestValidationError(f"清单文件不得为符号链接: {manifest_path}")
        try:
            resolved_path = manifest_path.resolve(strict=True)
        except OSError as exc:
            raise ManifestValidationError(f"清单文件不存在: {manifest_path}") from exc
        if not resolved_path.is_file():
            raise ManifestValidationError(f"清单路径不是普通文件: {resolved_path}")

        try:
            payload = json.loads(resolved_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ManifestValidationError(f"清单 JSON 无法读取: {resolved_path}") from exc

        if not isinstance(payload, dict):
            raise ManifestValidationError("清单顶层必须是对象")
        unknown = set(payload) - _TOP_LEVEL_KEYS
        missing = _TOP_LEVEL_KEYS - set(payload)
        if missing:
            raise ManifestValidationError(f"清单缺少字段: {', '.join(sorted(missing))}")
        if unknown:
            raise ManifestValidationError(f"清单包含未知字段: {', '.join(sorted(unknown))}")

        manifest_id = payload["manifest_id"]
        if not isinstance(manifest_id, str) or not manifest_id.strip():
            raise ManifestValidationError("manifest_id 必须是非空字符串")

        raw_date = payload["expected_business_date"]
        if not isinstance(raw_date, str) or not _DATE_RE.fullmatch(raw_date):
            raise ManifestValidationError("expected_business_date 必须为 YYYY-MM-DD")
        try:
            business_date = date.fromisoformat(raw_date)
        except ValueError as exc:
            raise ManifestValidationError("expected_business_date 不是有效日期") from exc

        raw_files = payload["files"]
        if not isinstance(raw_files, list) or not raw_files:
            raise ManifestValidationError("files 必须是非空数组")

        files: list[FrozenFile] = []
        names: set[str] = set()
        for index, item in enumerate(raw_files):
            if not isinstance(item, dict) or set(item) != _FILE_KEYS:
                raise ManifestValidationError(f"files[{index}] 必须只含 name、size、sha256")
            name = item["name"]
            if (
                not isinstance(name, str)
                or name in {"", ".", ".."}
                or "/" in name
                or "\\" in name
                or Path(name).is_absolute()
            ):
                raise ManifestValidationError(f"files[{index}].name 必须是直接子文件名")
            if name in names:
                raise ManifestValidationError(f"清单文件名重复: {name}")
            names.add(name)

            size = item["size"]
            if isinstance(size, bool) or not isinstance(size, int) or size < 0:
                raise ManifestValidationError(f"files[{index}].size 必须是非负整数")
            sha256 = item["sha256"]
            if not isinstance(sha256, str) or not _SHA256_RE.fullmatch(sha256):
                raise ManifestValidationError(f"files[{index}].sha256 格式无效")
            files.append(FrozenFile(name=name, size=size, sha256=sha256))

        return cls(
            manifest_id=manifest_id.strip(),
            expected_business_date=business_date,
            files=tuple(files),
        )

    def validate(self, input_root: Path | str) -> ValidatedInputManifest:
        raw_root = Path(input_root)
        if raw_root.is_symlink():
            raise ManifestValidationError(f"输入根目录不得为符号链接: {raw_root}")
        try:
            root = raw_root.resolve(strict=True)
        except OSError as exc:
            raise ManifestValidationError(f"输入根目录不存在: {raw_root}") from exc
        if not root.is_dir():
            raise ManifestValidationError(f"输入根路径不是目录: {root}")

        entries = tuple(root.iterdir())
        actual_names = {entry.name for entry in entries}
        expected_names = {file.name for file in self.files}
        if actual_names != expected_names:
            missing = sorted(expected_names - actual_names)
            unexpected = sorted(actual_names - expected_names)
            raise ManifestValidationError(
                f"目录文件集合与清单不一致; 缺少={missing}; 多余={unexpected}"
            )

        by_name = {file.name: file for file in self.files}
        for entry in entries:
            expected = by_name[entry.name]
            if entry.is_symlink():
                raise ManifestValidationError(f"输入文件不得为符号链接: {entry.name}")
            try:
                resolved = entry.resolve(strict=True)
            except OSError as exc:
                raise ManifestValidationError(f"输入文件无法解析: {entry.name}") from exc
            if resolved.parent != root:
                raise ManifestValidationError(f"输入文件 realpath 逃逸根目录: {entry.name}")
            if not resolved.is_file():
                raise ManifestValidationError(f"输入项不是普通文件: {entry.name}")
            actual_size = resolved.stat().st_size
            if actual_size != expected.size:
                raise ManifestValidationError(
                    f"输入文件大小不一致: {entry.name}; expected={expected.size}; actual={actual_size}"
                )
            actual_sha = _sha256_file(resolved)
            if actual_sha != expected.sha256:
                raise ManifestValidationError(
                    f"输入文件 SHA-256 不一致: {entry.name}; "
                    f"expected={expected.sha256}; actual={actual_sha}"
                )

        return ValidatedInputManifest(
            manifest_id=self.manifest_id,
            expected_business_date=self.expected_business_date,
            input_root=root,
            files=self.files,
        )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
