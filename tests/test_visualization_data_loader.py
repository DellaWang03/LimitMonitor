from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("sqlalchemy")

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.utils import archive_db as archive_db_module
from src.utils.archive_db import ArchiveDB, _prepare_dataframe_for_storage
from src.visualization import data_loader as data_loader_module
from src.visualization.data_loader import DataLoader


def test_archive_db_from_env_reuses_instance(monkeypatch):
    monkeypatch.setenv("DB_HOST", "127.0.0.1")
    monkeypatch.setenv("DB_PORT", "3306")
    monkeypatch.setenv("DB_USER", "tester")
    monkeypatch.setenv("DB_PASSWORD", "secret")
    monkeypatch.setenv("DB_NAME", "limit_monitor")

    archive_db_module._build_archive_db_from_env_values.cache_clear()

    db1 = ArchiveDB.from_env()
    db2 = ArchiveDB.from_env()

    assert db1 is db2


def test_data_loader_static_archive_methods_share_catalog_cache(monkeypatch):
    class FakeDB:
        def __init__(self) -> None:
            self.list_calls = 0

        def list_archive_meta(self):
            self.list_calls += 1
            return [
                {
                    "archive_date": "2026-04-27",
                    "data_date": "2026-04-26",
                    "is_current": 1,
                    "captured_at": datetime(2026, 4, 27, 8, 30, 0),
                },
                {
                    "archive_date": "2026-04-26",
                    "data_date": "2026-04-26",
                    "is_current": 0,
                    "captured_at": datetime(2026, 4, 26, 8, 30, 0),
                },
                {
                    "archive_date": "2026-04-26",
                    "data_date": "2026-04-25",
                    "is_current": 0,
                    "captured_at": datetime(2026, 4, 26, 8, 30, 0),
                },
            ]

    fake_db = FakeDB()
    DataLoader.clear_runtime_caches()
    monkeypatch.setattr(
        data_loader_module.ArchiveDB,
        "from_env",
        classmethod(lambda cls: fake_db),
    )

    assert DataLoader.get_available_dates() == [
        date(2026, 4, 26),
        date(2026, 4, 25),
    ]
    assert DataLoader.get_current_archive_date() == date(2026, 4, 27)
    assert DataLoader.get_current_data_date() == "2026-04-26"
    assert DataLoader.get_archive_date_for_data(date(2026, 4, 25)) == "2026-04-26"
    assert DataLoader.get_available_date_options() == [
        (date(2026, 4, 26), "2026-04-27"),
        (date(2026, 4, 25), "2026-04-26"),
    ]
    assert fake_db.list_calls == 1


def test_prepare_dataframe_for_storage_keeps_archive_and_data_dates_separate():
    source = pd.DataFrame(
        {
            "archive_date": ["old-archive"],
            "data_date": ["old-data"],
            "资产名称": ["测试债券"],
        }
    )

    prepared = _prepare_dataframe_for_storage(
        df=source,
        archive_date="2026-06-18",
        data_date="2026-06-17",
        table_name="stage1_credit_1_2",
    )

    assert list(prepared.columns[:3]) == ["archive_date", "data_date", "资产名称"]
    assert prepared.loc[0, "archive_date"] == "2026-06-18"
    assert prepared.loc[0, "data_date"] == "2026-06-17"
    assert source.loc[0, "archive_date"] == "old-archive"
    assert source.loc[0, "data_date"] == "old-data"


def test_data_loader_history_mode_uses_data_date_not_archive_date(monkeypatch):
    class FakeDB:
        def get_archive_meta_by_data_date(self, data_date: str):
            if data_date != "2026-04-26":
                return None
            return {
                "archive_date": "2026-04-27",
                "data_date": data_date,
                "is_current": 1,
                "alert_warning_threshold": 0.8,
                "alert_overlimit_threshold": 1.0,
                "high_yield_annual_limit_wan": 5000.0,
                "captured_at": datetime(2026, 4, 27, 9, 15, 0),
            }

        def read_dataframe_by_data_date(self, table_name: str, data_date: str):
            assert table_name == "stage1_credit_1_2"
            assert data_date == "2026-04-26"
            return pd.DataFrame(
                {
                    "日期": [pd.Timestamp("2026-04-26")],
                    "资产代码": ["123456"],
                    "资产名称": ["测试债券"],
                    "内部证券账户名称": ["账户A"],
                    "债券分类2": ["产业债"],
                }
            )

    DataLoader.clear_runtime_caches()
    monkeypatch.setattr(
        data_loader_module.ArchiveDB,
        "from_env",
        classmethod(lambda cls: FakeDB()),
    )

    loader = DataLoader(target_date=date(2026, 4, 26))

    assert loader.archive_date_str == "2026-04-27"
    assert loader.data_date_str == "2026-04-26"
    assert loader.load_stage1_credit_1_2().loc[0, "资产名称"] == "测试债券"


def test_data_loader_table_cache_returns_isolated_copies(monkeypatch):
    class FakeDB:
        def __init__(self) -> None:
            self.read_calls = 0

        def get_current_data_date(self):
            return "2026-04-26"

        def get_archive_meta_by_data_date(self, data_date: str):
            if data_date != "2026-04-26":
                return None
            return {
                "archive_date": "2026-04-27",
                "data_date": data_date,
                "is_current": 1,
                "alert_warning_threshold": 0.8,
                "alert_overlimit_threshold": 1.0,
                "high_yield_annual_limit_wan": 5000.0,
                "captured_at": datetime(2026, 4, 27, 9, 15, 0),
            }

        def read_dataframe_by_data_date(self, table_name: str, data_date: str):
            self.read_calls += 1
            assert table_name == "stage1_credit_1_2"
            assert data_date == "2026-04-26"
            return pd.DataFrame(
                {
                    "日期": [pd.Timestamp("2026-04-26")],
                    "资产代码": ["123456"],
                    "资产名称": ["测试债券"],
                    "内部证券账户名称": ["账户A"],
                    "债券分类2": ["产业债"],
                }
            )

    fake_db = FakeDB()
    DataLoader.clear_runtime_caches()
    monkeypatch.setattr(
        data_loader_module.ArchiveDB,
        "from_env",
        classmethod(lambda cls: fake_db),
    )

    loader = DataLoader(target_date=None)
    df1 = loader.load_stage1_credit_1_2()
    df1.loc[0, "资产名称"] = "已修改"

    df2 = loader.load_stage1_credit_1_2()

    assert fake_db.read_calls == 1
    assert df2.loc[0, "资产名称"] == "测试债券"
    assert df2.loc[0, "代码"] == "123456"


def test_data_loader_load_high_yield_limit_maps(monkeypatch):
    class FakeDB:
        def get_archive_meta_by_data_date(self, data_date: str):
            if data_date != "2026-04-26":
                return None
            return {
                "archive_date": "2026-04-27",
                "data_date": data_date,
                "is_current": 1,
                "alert_warning_threshold": 0.8,
                "alert_overlimit_threshold": 1.0,
                "high_yield_annual_limit_wan": 5000.0,
                "captured_at": datetime(2026, 4, 27, 9, 15, 0),
            }

        def read_dataframe_by_data_date(self, table_name: str, data_date: str):
            assert table_name == "stage2_high_yield"
            assert data_date == "2026-04-26"
            return pd.DataFrame(
                {
                    "单一债券限额(万)": [3000.0],
                    "单一主体限额(万)": [5000.0],
                    "按类别限额JSON": ['{"资产A": 1200, "主体B": 2300}'],
                }
            )

    DataLoader.clear_runtime_caches()
    monkeypatch.setattr(
        data_loader_module.ArchiveDB,
        "from_env",
        classmethod(lambda cls: FakeDB()),
    )

    loader = DataLoader(target_date=date(2026, 4, 26))
    limit_maps = loader.load_high_yield_limit_maps()

    assert limit_maps["bond_limits"]["__default__"] == 3000.0
    assert limit_maps["entity_limits"]["__default__"] == 5000.0
    assert limit_maps["bond_limits"]["资产A"] == 1200.0
    assert limit_maps["entity_limits"]["主体B"] == 2300.0
