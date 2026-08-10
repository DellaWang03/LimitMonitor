from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

import run_stage0


def test_current_input_validation_only_warns_when_access_is_not_t_minus_1(
    monkeypatch, tmp_path: Path
) -> None:
    access_path = tmp_path / "风控部债券池.accdb"
    access_path.touch()
    calls: list[bool] = []

    class FakeConfig:
        def get_data_dir(self) -> Path:
            return tmp_path

        def get_data_file_path(self, name: str) -> Path:
            assert name == "风控部债券池.accdb"
            return access_path

    class FakeValidator:
        def __init__(self, data_dir, config):
            assert data_dir == tmp_path
            assert config is fake_config

        def log_business_date_summary(self):
            return None

        def get_t_minus_1_date(self):
            return date(2026, 7, 14)

        def validate_access_database_freshness(self, path, strict_mode):
            assert path == access_path
            calls.append(strict_mode)
            return False, "outdated", date(2026, 7, 13)

    fake_config = FakeConfig()
    monkeypatch.setattr(run_stage0, "DateValidator", FakeValidator)
    monkeypatch.delenv("DATA_INCOMPLETE", raising=False)

    result = run_stage0.validate_current_inputs(
        fake_config,
        target_date=None,
        environment="production",
    )

    assert calls == [False]
    assert result == {
        "actual_date": "2026-07-13",
        "expected_t_minus_1_date": "2026-07-14",
        "is_t_minus_1": False,
        "target_date": None,
    }
    assert "DATA_INCOMPLETE" not in __import__("os").environ


def test_current_input_validation_still_rejects_missing_access_input(
    monkeypatch, tmp_path: Path
) -> None:
    class FakeConfig:
        def get_data_dir(self) -> Path:
            return tmp_path

        def get_data_file_path(self, name: str) -> Path:
            return tmp_path / name

    class FakeValidator:
        def __init__(self, data_dir, config):
            return None

        def log_business_date_summary(self):
            return None

    monkeypatch.setattr(run_stage0, "DateValidator", FakeValidator)

    with pytest.raises(FileNotFoundError, match="Access 数据库不存在"):
        run_stage0.validate_current_inputs(
            FakeConfig(), target_date=None, environment="production"
        )
