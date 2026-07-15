from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_daily_shell_wrapper_has_only_one_pipeline_entrypoint() -> None:
    content = (PROJECT_ROOT / "run_daily.sh").read_text(encoding="utf-8")

    assert "scripts/run_daily_pipeline.py" in content
    assert "run_stage0.py" not in content
    assert "run_stage1.py" not in content
    assert "run_stage2.py" not in content
    assert "scripts/daily_archive.py" not in content
    assert "scripts/generate_display_snapshot.py" not in content
    for variable in ("DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME"):
        assert variable in content


def test_daily_windows_wrapper_has_only_one_pipeline_entrypoint() -> None:
    content = (PROJECT_ROOT / "run_daily.bat").read_text(encoding="utf-8")

    assert "scripts\\run_daily_pipeline.py" in content
    assert "run_stage0.py" not in content
    assert "run_stage1.py" not in content
    assert "run_stage2.py" not in content
    assert "scripts\\daily_archive.py" not in content
    assert "scripts\\generate_display_snapshot.py" not in content
    for variable in ("DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME"):
        assert variable in content
