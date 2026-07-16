from __future__ import annotations

import pandas.testing as pdt
import pytest

sqlalchemy = pytest.importorskip("sqlalchemy")
from sqlalchemy import create_engine, inspect, text

from src.pretrade.context_store import (
    PretradeContextIntegrityError,
    PretradeContextStore,
    PretradePublishError,
)
from src.pretrade.input_contract import PretradeSnapshotRequest

from .conftest import make_config_workbook, make_kernel_input


@pytest.fixture
def engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def context_request():
    return PretradeSnapshotRequest.from_kernel_input(
        make_kernel_input(), make_config_workbook()
    )


def _assert_kernel_input_equal(actual, expected) -> None:
    assert actual.business_date == expected.business_date
    assert actual.parameters == expected.parameters
    assert tuple(actual.frames) == tuple(expected.frames)
    for dataset_code in actual.frames:
        pdt.assert_frame_equal(
            actual.frames[dataset_code], expected.frames[dataset_code], check_dtype=True
        )


def test_prepare_schema_creates_only_the_minimal_four_tables(engine) -> None:
    PretradeContextStore(engine).prepare_schema()

    inspector = inspect(engine)
    assert set(inspector.get_table_names()) == {
        "pretrade_snapshot",
        "pretrade_snapshot_dataset",
        "pretrade_snapshot_current",
        "pretrade_config_workbook",
    }
    assert inspector.get_pk_constraint("pretrade_snapshot")["constrained_columns"] == [
        "snapshot_id"
    ]
    assert inspector.get_pk_constraint("pretrade_snapshot_dataset")["constrained_columns"] == [
        "snapshot_id",
        "dataset_code",
    ]
    assert inspector.get_pk_constraint("pretrade_snapshot_current")["constrained_columns"] == [
        "pointer_id"
    ]
    assert inspector.get_pk_constraint("pretrade_config_workbook")[
        "constrained_columns"
    ] == ["snapshot_id"]


def test_write_snapshot_stores_one_payload_for_each_input(engine, context_request) -> None:
    store = PretradeContextStore(engine)
    store.prepare_schema()

    snapshot_id = store.write_snapshot(context_request)
    restored = store.load_kernel_input(snapshot_id)

    _assert_kernel_input_equal(restored, context_request.kernel_input)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT dataset_code, length(payload) FROM pretrade_snapshot_dataset "
                "WHERE snapshot_id = :snapshot_id"
            ),
            {"snapshot_id": str(snapshot_id)},
        ).all()
    assert len(rows) == 27
    assert all(size > 0 for _, size in rows)


def test_config_workbook_round_trips_byte_for_byte(engine, context_request) -> None:
    store = PretradeContextStore(engine)
    store.prepare_schema()

    snapshot_id = store.write_snapshot(context_request)

    assert store.load_config_workbook(snapshot_id) == context_request.config_workbook


def test_failed_dataset_write_rolls_back_and_keeps_current(engine, context_request) -> None:
    store = PretradeContextStore(engine)
    store.prepare_schema()
    old_snapshot = store.write_snapshot(context_request)
    store.publish_current(old_snapshot)

    with pytest.raises(RuntimeError, match="injected dataset failure"):
        store.write_snapshot(context_request, fail_after_dataset=1)

    assert store.list_snapshot_ids() == [old_snapshot]
    assert store.get_current_snapshot().snapshot_id == old_snapshot


def test_failed_config_workbook_write_rolls_back_and_keeps_current(
    engine, context_request
) -> None:
    store = PretradeContextStore(engine)
    store.prepare_schema()
    old_snapshot = store.write_snapshot(context_request)
    store.publish_current(old_snapshot)

    with pytest.raises(RuntimeError, match="injected config workbook failure"):
        store.write_snapshot(context_request, fail_after_config_workbook=True)

    assert store.list_snapshot_ids() == [old_snapshot]
    assert store.get_current_snapshot().snapshot_id == old_snapshot
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM pretrade_snapshot")).scalar() == 1
        assert (
            conn.execute(text("SELECT count(*) FROM pretrade_snapshot_dataset")).scalar()
            == 27
        )
        assert (
            conn.execute(text("SELECT count(*) FROM pretrade_config_workbook")).scalar()
            == 1
        )


def test_snapshots_are_append_only_even_for_same_input(engine, context_request) -> None:
    store = PretradeContextStore(engine)
    store.prepare_schema()

    first = store.write_snapshot(context_request)
    second = store.write_snapshot(context_request)

    assert first != second
    assert set(store.list_snapshot_ids()) == {first, second}
    _assert_kernel_input_equal(store.load_kernel_input(first), context_request.kernel_input)
    _assert_kernel_input_equal(store.load_kernel_input(second), context_request.kernel_input)


def test_load_rejects_corrupt_payload_hash(engine, context_request) -> None:
    store = PretradeContextStore(engine)
    store.prepare_schema()
    snapshot_id = store.write_snapshot(context_request)

    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE pretrade_snapshot_dataset SET payload_hash = :payload_hash "
                "WHERE snapshot_id = :snapshot_id AND dataset_code = :dataset_code"
            ),
            {
                "payload_hash": "0" * 64,
                "snapshot_id": str(snapshot_id),
                "dataset_code": "债券持仓明细表",
            },
        )

    with pytest.raises(PretradeContextIntegrityError, match="摘要"):
        store.load_kernel_input(snapshot_id)


def test_corrupt_config_workbook_hash_is_rejected(engine, context_request) -> None:
    store = PretradeContextStore(engine)
    store.prepare_schema()
    snapshot_id = store.write_snapshot(context_request)

    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE pretrade_config_workbook SET payload_hash = :payload_hash "
                "WHERE snapshot_id = :snapshot_id"
            ),
            {"payload_hash": "0" * 64, "snapshot_id": str(snapshot_id)},
        )

    with pytest.raises(PretradeContextIntegrityError, match="配置工作簿"):
        store.load_config_workbook(snapshot_id)


def test_publish_rejects_snapshot_without_config_workbook(engine, context_request) -> None:
    store = PretradeContextStore(engine)
    store.prepare_schema()
    snapshot_id = store.write_snapshot(context_request)
    with engine.begin() as conn:
        conn.execute(
            text(
                "DELETE FROM pretrade_config_workbook "
                "WHERE snapshot_id = :snapshot_id"
            ),
            {"snapshot_id": str(snapshot_id)},
        )

    with pytest.raises(PretradePublishError, match="配置工作簿"):
        store.publish_current(snapshot_id)


def test_current_snapshot_is_read_and_published_without_archive_meta(
    engine, context_request
) -> None:
    store = PretradeContextStore(engine)
    store.prepare_schema()
    snapshot_id = store.write_snapshot(context_request)

    store.publish_current(snapshot_id)

    current = store.get_current_snapshot()
    assert current is not None
    assert current.snapshot_id == snapshot_id
    _assert_kernel_input_equal(
        store.load_current_kernel_input(), context_request.kernel_input
    )
    assert "archive_meta" not in inspect(engine).get_table_names()
