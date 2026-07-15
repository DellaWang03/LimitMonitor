from __future__ import annotations

import uuid

import pandas.testing as pdt
import pytest

sqlalchemy = pytest.importorskip("sqlalchemy")
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateTable

from src.pretrade.context_store import (
    PRETRADE_SNAPSHOT_DATASET_CHUNK,
    PretradeContextIntegrityError,
    PretradeContextStore,
    PretradePublishError,
)
from src.pretrade.input_contract import PretradeSnapshotRequest

from .conftest import make_kernel_input


def test_chunk_payload_schema_supports_the_eight_mebibyte_contract_on_mysql() -> None:
    ddl = str(CreateTable(PRETRADE_SNAPSHOT_DATASET_CHUNK).compile(dialect=mysql.dialect()))

    assert "LONGBLOB" in ddl


@pytest.fixture
def engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def context_request(source_manifest):
    return PretradeSnapshotRequest.from_kernel_input(
        make_kernel_input(),
        usage="DEV",
        source_manifest=source_manifest,
        code_commit="test-commit",
    )


def _assert_kernel_input_equal(actual, expected) -> None:
    assert actual.business_date == expected.business_date
    assert actual.parameters == expected.parameters
    assert tuple(actual.frames) == tuple(expected.frames)
    for dataset_code in actual.frames:
        pdt.assert_frame_equal(
            actual.frames[dataset_code], expected.frames[dataset_code], check_dtype=True
        )


def test_prepare_schema_creates_only_the_four_pretrade_tables(engine) -> None:
    store = PretradeContextStore(engine)
    store.prepare_schema()

    inspector = inspect(engine)
    assert set(inspector.get_table_names()) == {
        "pretrade_snapshot",
        "pretrade_snapshot_dataset",
        "pretrade_snapshot_dataset_chunk",
        "pretrade_snapshot_current",
    }
    assert inspector.get_pk_constraint("pretrade_snapshot")["constrained_columns"] == [
        "snapshot_id"
    ]
    assert inspector.get_pk_constraint("pretrade_snapshot_dataset")[
        "constrained_columns"
    ] == ["snapshot_id", "dataset_code"]
    assert inspector.get_pk_constraint("pretrade_snapshot_dataset_chunk")[
        "constrained_columns"
    ] == ["snapshot_id", "dataset_code", "chunk_ordinal"]
    assert inspector.get_pk_constraint("pretrade_snapshot_current")["constrained_columns"] == [
        "usage"
    ]


def test_write_ready_snapshot_rehydrates_all_27_inputs_and_chunks(engine, context_request) -> None:
    store = PretradeContextStore(engine)
    store.prepare_schema()

    snapshot_id = store.write_ready_snapshot(context_request)
    restored = store.load_kernel_input(snapshot_id)

    _assert_kernel_input_equal(restored, context_request.kernel_input)
    with engine.connect() as conn:
        status = conn.execute(
            text("SELECT status FROM pretrade_snapshot WHERE snapshot_id = :snapshot_id"),
            {"snapshot_id": str(snapshot_id)},
        ).scalar_one()
        dataset_count = conn.execute(
            text(
                "SELECT COUNT(*) FROM pretrade_snapshot_dataset "
                "WHERE snapshot_id = :snapshot_id"
            ),
            {"snapshot_id": str(snapshot_id)},
        ).scalar_one()
        chunks = conn.execute(
            text(
                "SELECT dataset_code, chunk_ordinal, length(payload) "
                "FROM pretrade_snapshot_dataset_chunk "
                "WHERE snapshot_id = :snapshot_id ORDER BY dataset_code, chunk_ordinal"
            ),
            {"snapshot_id": str(snapshot_id)},
        ).all()

    assert status == "READY"
    assert dataset_count == 27
    assert chunks
    assert all(size <= 8 * 1024 * 1024 for _, _, size in chunks)
    per_dataset_ordinals: dict[str, list[int]] = {}
    for dataset_code, ordinal, _ in chunks:
        per_dataset_ordinals.setdefault(dataset_code, []).append(ordinal)
    assert all(ordinals == list(range(len(ordinals))) for ordinals in per_dataset_ordinals.values())


def test_failed_chunk_write_rolls_back_and_keeps_old_pointer(engine, context_request) -> None:
    store = PretradeContextStore(engine)
    store.prepare_schema()
    old_snapshot = store.write_ready_snapshot(context_request)
    store.publish(old_snapshot, "DEV")

    with pytest.raises(RuntimeError, match="injected chunk failure"):
        store.write_ready_snapshot(context_request, fail_after_chunk=1)

    assert store.list_snapshot_ids() == [old_snapshot]
    assert store.get_current_snapshot("DEV").snapshot_id == old_snapshot


def test_ready_snapshots_are_append_only_even_for_same_input(engine, context_request) -> None:
    store = PretradeContextStore(engine)
    store.prepare_schema()

    first = store.write_ready_snapshot(context_request)
    second = store.write_ready_snapshot(context_request)

    assert first != second
    assert set(store.list_snapshot_ids()) == {first, second}
    _assert_kernel_input_equal(store.load_kernel_input(first), context_request.kernel_input)
    _assert_kernel_input_equal(store.load_kernel_input(second), context_request.kernel_input)


def test_load_rejects_missing_chunk_or_corrupt_metadata(engine, context_request) -> None:
    store = PretradeContextStore(engine)
    store.prepare_schema()
    snapshot_id = store.write_ready_snapshot(context_request)

    with engine.begin() as conn:
        conn.execute(
            text(
                "DELETE FROM pretrade_snapshot_dataset_chunk "
                "WHERE snapshot_id = :snapshot_id AND dataset_code = :dataset_code "
                "AND chunk_ordinal = 0"
            ),
            {"snapshot_id": str(snapshot_id), "dataset_code": "债券持仓明细表"},
        )
    with pytest.raises(PretradeContextIntegrityError, match="分块"):
        store.load_kernel_input(snapshot_id)

    clean_snapshot = store.write_ready_snapshot(context_request)
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE pretrade_snapshot_dataset SET content_hash = :content_hash "
                "WHERE snapshot_id = :snapshot_id AND dataset_code = :dataset_code"
            ),
            {
                "content_hash": "0" * 64,
                "snapshot_id": str(clean_snapshot),
                "dataset_code": "债券持仓明细表",
            },
        )
    with pytest.raises(PretradeContextIntegrityError, match="摘要"):
        store.load_kernel_input(clean_snapshot)


def test_dev_publish_has_no_archive_requirement_and_prod_requires_same_date(
    engine, context_request, source_manifest
) -> None:
    store = PretradeContextStore(engine)
    store.prepare_schema()
    dev_snapshot = store.write_ready_snapshot(context_request)
    store.publish(dev_snapshot, "DEV")
    assert store.get_current_snapshot("DEV").snapshot_id == dev_snapshot

    prod_request = PretradeSnapshotRequest.from_kernel_input(
        make_kernel_input(business_date="2026-07-10"),
        usage="PROD",
        source_manifest=source_manifest,
    )
    prod_snapshot = store.write_ready_snapshot(prod_request)

    with pytest.raises(PretradePublishError, match="archive_meta"):
        store.publish(prod_snapshot, "PROD")

    with engine.begin() as conn:
        conn.execute(
            text("CREATE TABLE archive_meta (data_date VARCHAR(10), is_current INTEGER)")
        )
        conn.execute(
            text("INSERT INTO archive_meta (data_date, is_current) VALUES ('2026-07-09', 1)")
        )
    with pytest.raises(PretradePublishError, match="数据日期"):
        store.publish(prod_snapshot, "PROD")

    with engine.begin() as conn:
        conn.execute(text("UPDATE archive_meta SET data_date = '2026-07-10'"))
    store.publish(prod_snapshot, "PROD")
    assert store.get_current_snapshot("PROD").snapshot_id == prod_snapshot


def test_prod_snapshot_cannot_be_published_as_dev(engine, source_manifest) -> None:
    store = PretradeContextStore(engine)
    store.prepare_schema()
    prod_request = PretradeSnapshotRequest.from_kernel_input(
        make_kernel_input(), usage="PROD", source_manifest=source_manifest
    )
    snapshot_id = store.write_ready_snapshot(prod_request)

    with pytest.raises(PretradePublishError, match="usage"):
        store.publish(snapshot_id, "DEV")
