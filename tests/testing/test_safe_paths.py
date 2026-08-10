import os
from pathlib import Path

import pytest

from src.testing.safe_paths import UnsafeTestPath, create_unique_test_output


@pytest.fixture
def path_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    project = tmp_path / "project"
    source = tmp_path / "source"
    allow = tmp_path / "allow"
    project.mkdir()
    (project / "data").mkdir()
    source.mkdir()
    allow.mkdir()
    return project, source, allow


def test_create_unique_output_succeeds_with_mode_0700(
    path_fixture: tuple[Path, Path, Path],
) -> None:
    project, source, allow = path_fixture
    requested = allow / "run-1"

    result = create_unique_test_output(
        allow_root=allow,
        requested=requested,
        project_root=project,
        input_root=source,
    )

    assert result == requested.resolve()
    assert result.is_dir()
    assert result.stat().st_mode & 0o777 == 0o700


def test_rejects_missing_allow_root(
    path_fixture: tuple[Path, Path, Path],
) -> None:
    project, source, allow = path_fixture
    allow.rmdir()

    with pytest.raises(UnsafeTestPath, match="白名单根"):
        create_unique_test_output(
            allow_root=allow,
            requested=allow / "run",
            project_root=project,
            input_root=source,
        )


def test_rejects_allow_root_inside_project(tmp_path: Path) -> None:
    project = tmp_path / "project"
    source = tmp_path / "source"
    allow = project / "outputs"
    allow.mkdir(parents=True)
    source.mkdir()

    with pytest.raises(UnsafeTestPath, match="禁止"):
        create_unique_test_output(
            allow_root=allow,
            requested=allow / "run",
            project_root=project,
            input_root=source,
        )


def test_rejects_configured_forbidden_root(
    path_fixture: tuple[Path, Path, Path],
) -> None:
    project, source, allow = path_fixture

    with pytest.raises(UnsafeTestPath, match="禁止"):
        create_unique_test_output(
            allow_root=allow,
            requested=allow / "run",
            project_root=project,
            input_root=source,
            forbidden_roots=(allow,),
        )


def test_rejects_existing_output_even_when_empty(
    path_fixture: tuple[Path, Path, Path],
) -> None:
    project, source, allow = path_fixture
    requested = allow / "run"
    requested.mkdir()

    with pytest.raises(UnsafeTestPath, match="已存在"):
        create_unique_test_output(
            allow_root=allow,
            requested=requested,
            project_root=project,
            input_root=source,
        )


def test_rejects_broken_symlink_at_output_path(
    path_fixture: tuple[Path, Path, Path],
) -> None:
    project, source, allow = path_fixture
    requested = allow / "run"
    requested.symlink_to(allow / "missing", target_is_directory=True)
    assert not requested.exists()
    assert os.path.lexists(requested)

    with pytest.raises(UnsafeTestPath, match="已存在"):
        create_unique_test_output(
            allow_root=allow,
            requested=requested,
            project_root=project,
            input_root=source,
        )


def test_output_rejects_symlink_parent_escape(
    path_fixture: tuple[Path, Path, Path],
) -> None:
    project, source, allow = path_fixture
    outside = project.parent / "outside"
    outside.mkdir()
    (allow / "escape").symlink_to(outside, target_is_directory=True)

    with pytest.raises(UnsafeTestPath, match="白名单根|符号链接"):
        create_unique_test_output(
            allow_root=allow,
            requested=allow / "escape" / "run",
            project_root=project,
            input_root=source,
        )


def test_rejects_input_output_overlap(tmp_path: Path) -> None:
    project = tmp_path / "project"
    allow = tmp_path / "allow"
    source = allow / "source"
    project.mkdir()
    allow.mkdir()
    source.mkdir()

    with pytest.raises(UnsafeTestPath, match="输入目录"):
        create_unique_test_output(
            allow_root=allow,
            requested=source / "run",
            project_root=project,
            input_root=source,
        )
