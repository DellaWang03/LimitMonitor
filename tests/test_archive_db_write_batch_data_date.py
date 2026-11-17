from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd
import pytest

pytest.importorskip("sqlalchemy")

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.utils.archive_db import ArchiveDB


class _FakeResult:
    def __init__(self, scalar_value=None, rows=None) -> None:
        self._scalar_value = scalar_value
        self._rows = rows or []

    def scalar(self):
        return self._scalar_value

    def all(self):
        return list(self._rows)


class _FakeConnection:
    def __init__(self, lock_result=1) -> None:
        self.lock_result = lock_result
        self.executed: list[tuple[str, dict]] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def begin(self):
        return _FakeBegin(self)

    def commit(self):
        self.executed.append(("CONNECTION_COMMIT", {}))

    def execute(self, statement, params=None):
        sql = str(statement)
        bound = dict(params or {})
        self.executed.append((sql, bound))

        if "GET_LOCK" in sql:
            return _FakeResult(scalar_value=self.lock_result)
        if "RELEASE_LOCK" in sql:
            return _FakeResult(scalar_value=1)
        if "SELECT archive_date" in sql and "FROM archive_meta" in sql:
            return _FakeResult(rows=[("2026-06-17",)])
        return _FakeResult()


class _FakeBegin:
    def __init__(self, conn: _FakeConnection) -> None:
        self.conn = conn

    def __enter__(self):
        self.conn.executed.append(("TRANSACTION_BEGIN", {}))
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.conn.executed.append(("TRANSACTION_COMMIT", {}))
        else:
            self.conn.executed.append(("TRANSACTION_ROLLBACK", {}))
        return False


class _FakeEngine:
    def __init__(self, conn: _FakeConnection) -> None:
        self.conn = conn

    def begin(self):
        return _FakeBegin(self.conn)

    def connect(self):
        return self.conn


def _make_archive_db(conn: _FakeConnection) -> ArchiveDB:
    db = object.__new__(ArchiveDB)
    db._engine = _FakeEngine(conn)
    return db


def _index_containing(conn: _FakeConnection, pattern: str) -> int:
    for index, (sql, _) in enumerate(conn.executed):
        if pattern in sql:
            return index
    raise AssertionError(f"未找到 SQL/事件: {pattern}")


def test_write_batch_serializes_and_overwrites_by_data_date():
    conn = _FakeConnection()
    db = _make_archive_db(conn)
    write_calls = []

    def fake_write_dataframe_in_conn(**kwargs):
        write_calls.append(kwargs)
        return len(kwargs["df"])

    db._write_dataframe_in_conn = fake_write_dataframe_in_conn

    db.write_batch(
        archive_date="2026-06-18",
        data_date="2026-06-17",
        stage_tables={
            "stage1_credit_1_2": pd.DataFrame({"资产名称": ["旧债"]}),
            "stage2_high_yield": pd.DataFrame({"资产名称": ["高收益债"]}),
        },
        alert_warning_threshold=0.8,
        alert_overlimit_threshold=1.0,
        high_yield_annual_limit_wan=5000,
    )

    assert len(write_calls) == 2
    assert {call["data_date"] for call in write_calls} == {"2026-06-17"}
    assert {call["archive_date"] for call in write_calls} == {"2026-06-18"}
    assert all(call["old_archive_dates"] == ["2026-06-17"] for call in write_calls)

    sqls = [sql for sql, _ in conn.executed]
    assert _index_containing(conn, "GET_LOCK") < _index_containing(
        conn, "TRANSACTION_COMMIT"
    )
    assert any("UPDATE archive_meta SET is_current = 0" in sql for sql in sqls)
    assert any("DELETE FROM archive_meta WHERE data_date" in sql for sql in sqls)
    assert any("INSERT INTO archive_meta" in sql for sql in sqls)
    assert _index_containing(conn, "TRANSACTION_COMMIT") < _index_containing(
        conn, "RELEASE_LOCK"
    )


def test_write_batch_releases_data_date_lock_when_write_fails():
    conn = _FakeConnection()
    db = _make_archive_db(conn)

    def fake_write_dataframe_in_conn(**_kwargs):
        raise RuntimeError("boom")

    db._write_dataframe_in_conn = fake_write_dataframe_in_conn

    with pytest.raises(RuntimeError, match="boom"):
        db.write_batch(
            archive_date="2026-06-18",
            data_date="2026-06-17",
            stage_tables={"stage1_credit_1_2": pd.DataFrame({"资产名称": ["旧债"]})},
            alert_warning_threshold=0.8,
            alert_overlimit_threshold=1.0,
            high_yield_annual_limit_wan=5000,
        )

    assert _index_containing(conn, "GET_LOCK") < _index_containing(
        conn, "TRANSACTION_ROLLBACK"
    )
    assert _index_containing(conn, "TRANSACTION_ROLLBACK") < _index_containing(
        conn, "RELEASE_LOCK"
    )


def test_write_batch_fails_when_data_date_lock_cannot_be_acquired():
    conn = _FakeConnection(lock_result=0)
    db = _make_archive_db(conn)

    with pytest.raises(TimeoutError, match="归档写锁超时"):
        db.write_batch(
            archive_date="2026-06-18",
            data_date="2026-06-17",
            stage_tables={"stage1_credit_1_2": pd.DataFrame({"资产名称": ["旧债"]})},
            alert_warning_threshold=0.8,
            alert_overlimit_threshold=1.0,
            high_yield_annual_limit_wan=5000,
        )

    sqls = [sql for sql, _ in conn.executed]
    assert any("GET_LOCK" in sql for sql in sqls)
    assert not any("DELETE FROM archive_meta" in sql for sql in sqls)


def test_optional_receipt_captures_version_inside_transaction_and_publishes_after_commit():
    from datetime import datetime
    class ReceiptConnection(_FakeConnection):
        def execute(self, statement, params=None):
            result = super().execute(statement, params)
            if str(statement).startswith('SELECT captured_at'):
                return _FakeResult(scalar_value=datetime(2026, 11, 16, 10, 0, 0, 123456))
            return result
    conn = ReceiptConnection()
    db = _make_archive_db(conn)
    db._write_dataframe_in_conn = lambda **kwargs: 0
    class Receipt(dict):
        def update(self, **kwargs):
            assert _index_containing(conn, 'TRANSACTION_COMMIT') < len(conn.executed)
            super().update(**kwargs)
    receipt = Receipt()
    db.write_batch(archive_date='2026-11-16', data_date='2026-11-13',
                   stage_tables={'stage1_credit_1_2': pd.DataFrame({'资产名称': ['测试债']})},
                   alert_warning_threshold=0.8, alert_overlimit_threshold=1.0,
                   high_yield_annual_limit_wan=5000, receipt=receipt)
    assert receipt == {'data_date': '2026-11-13', 'parent_version': '2026-11-16T10:00:00.123456'}
    assert _index_containing(conn, 'INSERT INTO archive_meta') < _index_containing(conn, 'SELECT captured_at')
    assert _index_containing(conn, 'SELECT captured_at') < _index_containing(conn, 'TRANSACTION_COMMIT')
