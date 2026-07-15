from pathlib import Path

import pytest

from src.pipeline.paths import PipelinePathError, PipelinePaths


def test_create_builds_exact_isolated_children(tmp_path: Path) -> None:
    root = tmp_path / "run"
    root.mkdir(mode=0o700)

    paths = PipelinePaths.create(root)

    assert paths.root == root.resolve()
    assert {path.name for path in paths.children} == {
        "stage0",
        "stage1",
        "stage2",
        "logs",
        "access_export",
        "tmp",
        "home",
    }
    assert all(path.is_dir() and not path.is_symlink() for path in paths.children)


def test_create_rejects_non_empty_root(tmp_path: Path) -> None:
    root = tmp_path / "run"
    root.mkdir()
    (root / "existing").mkdir()

    with pytest.raises(PipelinePathError, match="必须为空"):
        PipelinePaths.create(root)


def test_create_rejects_repeated_creation(tmp_path: Path) -> None:
    root = tmp_path / "run"
    root.mkdir()
    PipelinePaths.create(root)

    with pytest.raises(PipelinePathError, match="必须为空"):
        PipelinePaths.create(root)


def test_create_rejects_symlink_root(tmp_path: Path) -> None:
    real = tmp_path / "real"
    linked = tmp_path / "linked"
    real.mkdir()
    linked.symlink_to(real, target_is_directory=True)

    with pytest.raises(PipelinePathError, match="符号链接"):
        PipelinePaths.create(linked)
