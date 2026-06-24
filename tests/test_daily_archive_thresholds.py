from __future__ import annotations

import importlib
import sys
import types

import pandas as pd


def test_read_alert_thresholds_from_current_limit_config_system_parameters(monkeypatch):
    fake_archive_db = types.ModuleType("src.utils.archive_db")
    fake_archive_db.ArchiveDB = object
    monkeypatch.setitem(sys.modules, "src.utils.archive_db", fake_archive_db)
    sys.modules.pop("scripts.daily_archive", None)
    daily_archive = importlib.import_module("scripts.daily_archive")

    calls: list[dict[str, object]] = []

    def fake_load_limit_config(*, sheet_name, config, inject_date):
        calls.append(
            {
                "sheet_name": sheet_name,
                "config": config,
                "inject_date": inject_date,
            }
        )
        return pd.DataFrame(
            {
                "参数名": ["告警阈值_预警", "告警阈值_超限", "监管集中度限额"],
                "值": [0.75, 1.0, 0.16],
            }
        )

    monkeypatch.setattr(daily_archive, "load_limit_config", fake_load_limit_config)

    try:
        assert daily_archive._read_alert_thresholds() == (0.75, 1.0)
        assert len(calls) == 1
        assert calls[0]["sheet_name"] == "系统参数"
        assert calls[0]["config"] is not None
        assert calls[0]["inject_date"] is False
    finally:
        sys.modules.pop("scripts.daily_archive", None)
