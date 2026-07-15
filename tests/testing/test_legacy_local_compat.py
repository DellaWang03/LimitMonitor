import hashlib
from datetime import date
from pathlib import Path

import pytest

from src.testing.frozen_manifest import FrozenFile, ValidatedInputManifest
from src.testing.legacy_local_compat import (
    LegacyLocalCompatibilityError,
    cleanup_legacy_local_limit_config,
    stage_legacy_local_limit_config,
)


def _manifest(tmp_path: Path) -> ValidatedInputManifest:
    return _manifest_at(tmp_path / "source")


def _manifest_at(source: Path) -> ValidatedInputManifest:
    source.mkdir()
    payload = b"frozen-limit-config"
    name = "限额配置_当前.xlsx"
    (source / name).write_bytes(payload)
    return ValidatedInputManifest(
        manifest_id="fixture-v1",
        expected_business_date=date(2026, 7, 10),
        input_root=source.resolve(),
        files=(
            FrozenFile(
                name=name,
                size=len(payload),
                sha256=hashlib.sha256(payload).hexdigest(),
            ),
        ),
    )


def test_stage_and_cleanup_deployed_local_compatibility_path(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    project_root = tmp_path / "project"
    project_root.mkdir()
    source = manifest.input_root / "限额配置_当前.xlsx"
    source_before = source.read_bytes()

    staged = stage_legacy_local_limit_config(manifest, project_root)

    expected = project_root / "data_source_0123/限额配置_当前.xlsx"
    assert staged.path == expected
    assert staged.created_by_runner is True
    assert staged.path.read_bytes() == source_before
    assert staged.sha256 == manifest.files[0].sha256
    assert source.read_bytes() == source_before

    cleanup_legacy_local_limit_config(staged)

    assert not expected.exists()
    assert not expected.parent.exists()
    assert source.read_bytes() == source_before


def test_reuses_frozen_input_when_it_is_the_deployed_local_path(
    tmp_path: Path,
) -> None:
    manifest = _manifest_at(tmp_path / "data_source_0123")
    source = manifest.input_root / "限额配置_当前.xlsx"
    companion = manifest.input_root / "other-input.xlsx"
    companion.write_bytes(b"preserve")
    source_before = source.read_bytes()

    staged = stage_legacy_local_limit_config(manifest, tmp_path)

    assert staged.path == source
    assert staged.created_by_runner is False

    cleanup_legacy_local_limit_config(staged)

    assert source.read_bytes() == source_before
    assert companion.read_bytes() == b"preserve"


def test_reused_frozen_input_is_validated_but_never_deleted(tmp_path: Path) -> None:
    manifest = _manifest_at(tmp_path / "data_source_0123")
    source = manifest.input_root / "限额配置_当前.xlsx"
    staged = stage_legacy_local_limit_config(manifest, tmp_path)
    source.write_bytes(b"changed")

    with pytest.raises(LegacyLocalCompatibilityError, match="发生变化"):
        cleanup_legacy_local_limit_config(staged)

    assert source.read_bytes() == b"changed"


def test_stage_refuses_existing_local_compatibility_directory(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    project_root = tmp_path / "project"
    existing = project_root / "data_source_0123"
    existing.mkdir(parents=True)
    (existing / "user-file.txt").write_text("preserve", encoding="utf-8")

    with pytest.raises(LegacyLocalCompatibilityError, match="已存在"):
        stage_legacy_local_limit_config(manifest, project_root)

    assert (existing / "user-file.txt").read_text(encoding="utf-8") == "preserve"


def test_cleanup_refuses_changed_compatibility_file(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    project_root = tmp_path / "project"
    project_root.mkdir()
    staged = stage_legacy_local_limit_config(manifest, project_root)
    staged.path.write_bytes(b"changed")

    with pytest.raises(LegacyLocalCompatibilityError, match="发生变化"):
        cleanup_legacy_local_limit_config(staged)

    assert staged.path.read_bytes() == b"changed"
