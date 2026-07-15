from datetime import date
from pathlib import Path

import pytest

from src.pipeline.paths import PipelinePaths
from src.testing.frozen_config import FrozenConfigError, FrozenInputConfig
from src.testing.frozen_manifest import FrozenFile, ValidatedInputManifest


class FakeBaseConfig:
    def get(self, key: str, default=None):
        return {"limits.threshold": 0.8}.get(key, default)

    def get_limit(self, key: str, default=None):
        return {"legacy.limit": 100}.get(key, default)

    def load_settings(self):
        return {"settings": "delegated"}

    def load_limits(self):
        return {"limits": "delegated"}


@pytest.fixture
def frozen_fixture(tmp_path: Path):
    source = tmp_path / "source"
    output = tmp_path / "output"
    source.mkdir()
    output.mkdir(mode=0o700)
    (source / "a.xlsx").write_bytes(b"a")
    (source / "风控部债券池.accdb").write_bytes(b"db")
    manifest = ValidatedInputManifest(
        manifest_id="fixture-v1",
        expected_business_date=date(2026, 7, 10),
        input_root=source.resolve(),
        files=(
            FrozenFile("a.xlsx", 1, "0" * 64),
            FrozenFile("风控部债券池.accdb", 2, "1" * 64),
        ),
    )
    paths = PipelinePaths.create(output)
    config = FrozenInputConfig(
        base=FakeBaseConfig(),
        manifest=manifest,
        pipeline_root=paths.root,
        access_export_dir=paths.access_export,
    )
    return source, paths, manifest, config


def test_delegates_non_path_configuration(frozen_fixture) -> None:
    _, _, _, config = frozen_fixture

    assert config.get("limits.threshold") == 0.8
    assert config.get("missing", "fallback") == "fallback"
    assert config.get_limit("legacy.limit") == 100
    assert config.load_settings() == {"settings": "delegated"}
    assert config.load_limits() == {"limits": "delegated"}


def test_all_path_methods_are_frozen_to_validated_manifest(
    frozen_fixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, paths, manifest, config = frozen_fixture
    monkeypatch.setenv("LIMIT_MONITOR_PROFILE", "migration")

    assert config.manifest is manifest
    assert config.get_active_profile() == "local"
    assert config.get_data_dir() == source.resolve()
    assert config.get_data_file_path("a.xlsx") == (source / "a.xlsx").resolve()
    assert config.get_data_file_path_without_override("风控部债券池.accdb") == (
        source / "风控部债券池.accdb"
    ).resolve()
    assert config.get_data_config_source_dir() == paths.access_export


def test_rejects_file_outside_manifest(frozen_fixture) -> None:
    _, _, _, config = frozen_fixture

    with pytest.raises(FrozenConfigError, match="不在冻结清单"):
        config.get_data_file_path("other.xlsx")


def test_rejects_access_export_outside_pipeline_root(tmp_path: Path) -> None:
    source = tmp_path / "source"
    output = tmp_path / "output"
    outside = tmp_path / "outside"
    source.mkdir()
    output.mkdir()
    outside.mkdir()
    manifest = ValidatedInputManifest(
        manifest_id="fixture-v1",
        expected_business_date=date(2026, 7, 10),
        input_root=source.resolve(),
        files=(),
    )

    with pytest.raises(FrozenConfigError, match="流水线根目录"):
        FrozenInputConfig(
            base=FakeBaseConfig(),
            manifest=manifest,
            pipeline_root=output,
            access_export_dir=outside,
        )
