import hashlib
import json
from pathlib import Path

import pytest

from src.testing.frozen_manifest import (
    FrozenInputManifest,
    ManifestValidationError,
)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _write_manifest(
    path: Path,
    files: list[dict[str, object]],
    *,
    manifest_id: str = "fixture-v1",
    business_date: str = "2026-07-10",
) -> Path:
    path.write_text(
        json.dumps(
            {
                "manifest_id": manifest_id,
                "expected_business_date": business_date,
                "files": files,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def _entry(name: str, payload: bytes) -> dict[str, object]:
    return {"name": name, "size": len(payload), "sha256": _sha256(payload)}


def test_validate_returns_resolved_immutable_metadata(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    payload = b"frozen"
    (source / "a.xlsx").write_bytes(payload)
    manifest_path = _write_manifest(tmp_path / "manifest.json", [_entry("a.xlsx", payload)])

    validated = FrozenInputManifest.load(manifest_path).validate(source)

    assert validated.manifest_id == "fixture-v1"
    assert validated.expected_business_date.isoformat() == "2026-07-10"
    assert validated.input_root == source.resolve()
    assert validated.files[0].name == "a.xlsx"
    with pytest.raises(AttributeError):
        validated.manifest_id = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    "payload, message",
    [
        ({"expected_business_date": "2026-07-10", "files": []}, "manifest_id"),
        ({"manifest_id": "v1", "files": []}, "expected_business_date"),
        (
            {"manifest_id": "v1", "expected_business_date": "07/10/2026", "files": []},
            "expected_business_date",
        ),
    ],
)
def test_load_rejects_missing_or_invalid_identity(
    tmp_path: Path,
    payload: dict[str, object],
    message: str,
) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ManifestValidationError, match=message):
        FrozenInputManifest.load(manifest)


@pytest.mark.parametrize("name", ["../a.xlsx", "nested/a.xlsx", "/tmp/a.xlsx", "", "."])
def test_load_rejects_non_direct_file_names(tmp_path: Path, name: str) -> None:
    manifest = _write_manifest(tmp_path / "manifest.json", [_entry(name, b"x")])

    with pytest.raises(ManifestValidationError, match="直接子文件"):
        FrozenInputManifest.load(manifest)


def test_load_rejects_duplicate_names(tmp_path: Path) -> None:
    manifest = _write_manifest(
        tmp_path / "manifest.json",
        [_entry("a.xlsx", b"a"), _entry("a.xlsx", b"b")],
    )

    with pytest.raises(ManifestValidationError, match="重复"):
        FrozenInputManifest.load(manifest)


def test_validate_requires_exact_directory_entries(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "a.xlsx").write_bytes(b"a")
    (source / "unexpected.xlsx").write_bytes(b"extra")
    manifest = _write_manifest(tmp_path / "manifest.json", [_entry("a.xlsx", b"a")])

    with pytest.raises(ManifestValidationError, match="目录文件集合"):
        FrozenInputManifest.load(manifest).validate(source)


def test_validate_rejects_symlinked_manifest_file(tmp_path: Path) -> None:
    source = tmp_path / "source"
    outside = tmp_path / "outside.xlsx"
    source.mkdir()
    outside.write_bytes(b"outside")
    (source / "a.xlsx").symlink_to(outside)
    manifest = _write_manifest(tmp_path / "manifest.json", [_entry("a.xlsx", b"outside")])

    with pytest.raises(ManifestValidationError, match="符号链接"):
        FrozenInputManifest.load(manifest).validate(source)


def test_validate_rejects_directory_instead_of_file(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "a.xlsx").mkdir()
    manifest = _write_manifest(tmp_path / "manifest.json", [_entry("a.xlsx", b"")])

    with pytest.raises(ManifestValidationError, match="普通文件"):
        FrozenInputManifest.load(manifest).validate(source)


@pytest.mark.parametrize("mutation", ["size", "sha256"])
def test_validate_rejects_size_or_hash_mismatch(tmp_path: Path, mutation: str) -> None:
    source = tmp_path / "source"
    source.mkdir()
    payload = b"actual"
    (source / "a.xlsx").write_bytes(payload)
    entry = _entry("a.xlsx", payload)
    if mutation == "size":
        entry["size"] = len(payload) + 1
    else:
        entry["sha256"] = "0" * 64
    manifest = _write_manifest(tmp_path / "manifest.json", [entry])

    with pytest.raises(ManifestValidationError, match="大小|SHA-256"):
        FrozenInputManifest.load(manifest).validate(source)


def test_checked_in_manifest_has_the_frozen_identity() -> None:
    project_root = Path(__file__).resolve().parents[2]
    manifest = FrozenInputManifest.load(
        project_root / "config/test_manifests/data_source_0123-20260710-v1.json"
    )

    assert manifest.manifest_id == "data_source_0123-20260710-v1"
    assert manifest.expected_business_date.isoformat() == "2026-07-10"
    assert len(manifest.files) == 12
