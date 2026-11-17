from __future__ import annotations

import io
import sys
from types import SimpleNamespace

import pandas as pd

from scripts import daily_archive


def test_archive_console_output_is_cp936_safe(monkeypatch, tmp_path) -> None:
    stage_tables = {"stage1_credit_1_2": pd.DataFrame({"日期": ["2026-07-14"]})}
    database = SimpleNamespace(
        prepare_stage_tables_schema=lambda **kwargs: None,
        write_batch=lambda **kwargs: None,
    )
    monkeypatch.setattr(daily_archive, "CURRENT_DIR", tmp_path)
    monkeypatch.setattr(daily_archive, "_load_stage_tables", lambda: stage_tables)
    monkeypatch.setattr(daily_archive, "_read_alert_thresholds", lambda: (0.75, 1.0))
    monkeypatch.setattr(daily_archive, "_read_high_yield_annual_limit", lambda: 100.0)
    monkeypatch.setattr(
        daily_archive.ArchiveDB,
        "from_env",
        classmethod(lambda cls: database),
    )
    output = io.BytesIO()
    console = io.TextIOWrapper(output, encoding="cp936", errors="strict")
    monkeypatch.setattr(sys, "stdout", console)

    assert daily_archive.archive_to_db("2026-07-15") == 0
    console.flush()
