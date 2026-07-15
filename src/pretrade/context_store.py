"""交易前共同内核输入的最小事务型存储。

本模块只操作四张 ``pretrade_`` 表。它不读取展示快照、不调用归档写入接口，
也不包含任何限额计算规则。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
from typing import Any
from uuid import UUID, uuid4

import pandas as pd
from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    MetaData,
    String,
    Table,
    Text,
    and_,
    insert,
    select,
    text,
    update,
)
from sqlalchemy.dialects.mysql import LONGBLOB as MYSQL_LONGBLOB
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import SQLAlchemyError

from src.risk_core import ProductionKernelInput, ProductionKernelParameters

from .frame_codec import (
    FrameCodecError,
    SerializedFrame,
    deserialize_frame,
    join_payload,
    serialize_frame,
    split_payload,
)
from .input_contract import (
    ALLOWED_USAGES,
    KERNEL_INPUT_DATASETS,
    PretradeSnapshotRequest,
)


PRETRADE_METADATA = MetaData()

PRETRADE_SNAPSHOT = Table(
    "pretrade_snapshot",
    PRETRADE_METADATA,
    Column("snapshot_id", String(36), primary_key=True),
    Column("usage", String(4), nullable=False),
    Column("data_date", String(10), nullable=False),
    Column("status", String(16), nullable=False),
    Column("regulatory_concentration_limit", Float, nullable=False),
    Column("code_commit", String(128), nullable=False),
    Column("engine_version", String(128), nullable=False),
    Column("input_contract_version", String(128), nullable=False),
    Column("source_manifest_json", Text, nullable=False),
    Column("source_manifest_hash", String(64), nullable=False),
    Column("input_hash", String(64), nullable=False),
    Column("created_at", DateTime, nullable=False),
    Column("ready_at", DateTime, nullable=True),
)

PRETRADE_SNAPSHOT_DATASET = Table(
    "pretrade_snapshot_dataset",
    PRETRADE_METADATA,
    Column(
        "snapshot_id",
        String(36),
        ForeignKey("pretrade_snapshot.snapshot_id"),
        primary_key=True,
    ),
    Column("dataset_code", String(128), primary_key=True),
    Column("content_hash", String(64), nullable=False),
    Column("schema_json", Text, nullable=False),
    Column("row_count", BigInteger, nullable=False),
    Column("payload_size_bytes", BigInteger, nullable=False),
    Column("serializer_version", String(64), nullable=False),
)

PRETRADE_SNAPSHOT_DATASET_CHUNK = Table(
    "pretrade_snapshot_dataset_chunk",
    PRETRADE_METADATA,
    Column(
        "snapshot_id",
        String(36),
        ForeignKey("pretrade_snapshot.snapshot_id"),
        primary_key=True,
    ),
    Column("dataset_code", String(128), primary_key=True),
    Column("chunk_ordinal", Integer, primary_key=True),
    Column(
        "payload",
        LargeBinary().with_variant(MYSQL_LONGBLOB(), "mysql"),
        nullable=False,
    ),
)

PRETRADE_SNAPSHOT_CURRENT = Table(
    "pretrade_snapshot_current",
    PRETRADE_METADATA,
    Column("usage", String(4), primary_key=True),
    Column(
        "snapshot_id",
        String(36),
        ForeignKey("pretrade_snapshot.snapshot_id"),
        nullable=False,
    ),
    Column("data_date", String(10), nullable=False),
    Column("published_at", DateTime, nullable=False),
)


class PretradeContextStoreError(RuntimeError):
    """交易前上下文无法被安全写入或读取。"""


class PretradeContextIntegrityError(PretradeContextStoreError):
    """数据库内容不满足输入契约或完整性校验。"""


class PretradePublishError(PretradeContextStoreError):
    """交易前当前指针不能安全发布。"""


class PretradeDataSyncError(PretradeContextStoreError):
    """展示归档和交易前上下文不是同一数据日。"""


@dataclass(frozen=True)
class PretradeContextSnapshot:
    """快照元数据；不暴露可变数据库行。"""

    snapshot_id: UUID
    usage: str
    data_date: str
    status: str
    input_hash: str
    source_manifest_hash: str
    created_at: datetime
    ready_at: datetime | None


def _now_utc_naive() -> datetime:
    """两种目标数据库均可保存的 UTC 时间。"""

    return datetime.now(UTC).replace(tzinfo=None)


def _as_uuid(snapshot_id: UUID | str) -> UUID:
    try:
        return UUID(str(snapshot_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise PretradeContextStoreError("snapshot_id 必须是有效 UUID") from exc


def _validate_usage(usage: str) -> None:
    if usage not in ALLOWED_USAGES:
        raise PretradePublishError("usage 仅允许 DEV 或 PROD")


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _snapshot_from_row(row: Any) -> PretradeContextSnapshot:
    return PretradeContextSnapshot(
        snapshot_id=UUID(row["snapshot_id"]),
        usage=row["usage"],
        data_date=str(row["data_date"]),
        status=row["status"],
        input_hash=row["input_hash"],
        source_manifest_hash=row["source_manifest_hash"],
        created_at=row["created_at"],
        ready_at=row["ready_at"],
    )


class PretradeContextStore:
    """对四张交易前上下文表的唯一写入入口。"""

    def __init__(self, engine: Engine) -> None:
        if not isinstance(engine, Engine):
            raise TypeError("engine 必须是 SQLAlchemy Engine")
        self._engine = engine

    def prepare_schema(self) -> None:
        """幂等创建四张新表，不触碰任何既有归档表。"""

        PRETRADE_METADATA.create_all(self._engine)
        if self._engine.dialect.name == "mysql":
            self._upgrade_mysql_chunk_payload_column()

    def _upgrade_mysql_chunk_payload_column(self) -> None:
        """将历史测试创建的 BLOB 列无损扩容到 8 MiB 分块所需的 LONGBLOB。"""

        with self._engine.begin() as conn:
            data_type = conn.execute(
                text(
                    "SELECT data_type FROM information_schema.columns "
                    "WHERE table_schema = DATABASE() "
                    "AND table_name = 'pretrade_snapshot_dataset_chunk' "
                    "AND column_name = 'payload'"
                )
            ).scalar_one_or_none()
            if str(data_type).lower() != "longblob":
                conn.execute(
                    text(
                        "ALTER TABLE `pretrade_snapshot_dataset_chunk` "
                        "MODIFY COLUMN `payload` LONGBLOB NOT NULL"
                    )
                )

    def write_ready_snapshot(
        self,
        request: PretradeSnapshotRequest,
        *,
        fail_after_chunk: int | None = None,
    ) -> UUID:
        """事务写入并读回校验一份新的 READY 上下文。

        ``fail_after_chunk`` 仅用于故障注入测试；正常调用方不得传入。
        """

        if not isinstance(request, PretradeSnapshotRequest):
            raise TypeError("request 必须是 PretradeSnapshotRequest")
        if fail_after_chunk is not None and fail_after_chunk < 1:
            raise ValueError("fail_after_chunk 必须大于零")

        snapshot_id = uuid4()
        snapshot_id_text = str(snapshot_id)
        frames = request.kernel_input.detached_frames()
        serialized_frames = {
            dataset_code: serialize_frame(frames[dataset_code])
            for dataset_code in KERNEL_INPUT_DATASETS
        }
        created_at = _now_utc_naive()
        source_manifest_json = _canonical_json(request.source_manifest)

        try:
            with self._engine.begin() as conn:
                conn.execute(
                    insert(PRETRADE_SNAPSHOT).values(
                        snapshot_id=snapshot_id_text,
                        usage=request.usage,
                        data_date=request.kernel_input.business_date.date().isoformat(),
                        status="LOADING",
                        regulatory_concentration_limit=(
                            request.kernel_input.parameters.regulatory_concentration_limit
                        ),
                        code_commit=request.code_commit,
                        engine_version=request.engine_version,
                        input_contract_version=request.input_contract_version,
                        source_manifest_json=source_manifest_json,
                        source_manifest_hash=request.source_manifest_hash,
                        input_hash=request.input_hash,
                        created_at=created_at,
                        ready_at=None,
                    )
                )

                written_chunks = 0
                for dataset_code in KERNEL_INPUT_DATASETS:
                    serialized = serialized_frames[dataset_code]
                    conn.execute(
                        insert(PRETRADE_SNAPSHOT_DATASET).values(
                            snapshot_id=snapshot_id_text,
                            dataset_code=dataset_code,
                            content_hash=serialized.content_hash,
                            schema_json=serialized.schema_json,
                            row_count=serialized.row_count,
                            payload_size_bytes=serialized.payload_size_bytes,
                            serializer_version=serialized.serializer_version,
                        )
                    )
                    for ordinal, chunk in enumerate(split_payload(serialized.payload)):
                        conn.execute(
                            insert(PRETRADE_SNAPSHOT_DATASET_CHUNK).values(
                                snapshot_id=snapshot_id_text,
                                dataset_code=dataset_code,
                                chunk_ordinal=ordinal,
                                payload=chunk,
                            )
                        )
                        written_chunks += 1
                        if (
                            fail_after_chunk is not None
                            and written_chunks >= fail_after_chunk
                        ):
                            raise RuntimeError("injected chunk failure")

                self._load_kernel_input(conn, snapshot_id, allow_loading=True)
                conn.execute(
                    update(PRETRADE_SNAPSHOT)
                    .where(PRETRADE_SNAPSHOT.c.snapshot_id == snapshot_id_text)
                    .values(status="READY", ready_at=_now_utc_naive())
                )
        except (PretradeContextStoreError, RuntimeError):
            raise
        except (SQLAlchemyError, FrameCodecError, ValueError, TypeError) as exc:
            raise PretradeContextStoreError("交易前快照写入失败") from exc

        return snapshot_id

    def load_kernel_input(self, snapshot_id: UUID | str) -> ProductionKernelInput:
        """从 READY 快照重建共同内核的唯一输入对象。"""

        normalized_snapshot_id = _as_uuid(snapshot_id)
        try:
            with self._engine.connect() as conn:
                return self._load_kernel_input(conn, normalized_snapshot_id, allow_loading=False)
        except PretradeContextStoreError:
            raise
        except (SQLAlchemyError, FrameCodecError, ValueError, TypeError) as exc:
            raise PretradeContextIntegrityError("交易前快照读取失败") from exc

    def get_current_snapshot(self, usage: str) -> PretradeContextSnapshot | None:
        """取得当前指针；PROD 额外执行展示归档的数据日期守卫。"""

        _validate_usage(usage)
        try:
            with self._engine.connect() as conn:
                pointer = conn.execute(
                    select(PRETRADE_SNAPSHOT_CURRENT).where(
                        PRETRADE_SNAPSHOT_CURRENT.c.usage == usage
                    )
                ).mappings().one_or_none()
                if pointer is None:
                    return None
                snapshot = self._get_snapshot_row(conn, UUID(pointer["snapshot_id"]))
                if snapshot.data_date != str(pointer["data_date"]):
                    raise PretradeContextIntegrityError("当前指针的数据日期与快照不一致")
                if usage == "PROD":
                    archive_data_date = self._current_archive_data_date(conn, for_publish=False)
                    if archive_data_date != snapshot.data_date:
                        raise PretradeDataSyncError(
                            "数据同步中：展示归档与交易前上下文的数据日期不一致"
                        )
                return snapshot
        except PretradeContextStoreError:
            raise
        except SQLAlchemyError as exc:
            raise PretradeContextStoreError("读取交易前当前指针失败") from exc

    def publish(self, snapshot_id: UUID | str, usage: str) -> None:
        """原子发布同用途的 READY 快照；PROD 必须同日展示归档已发布。"""

        _validate_usage(usage)
        normalized_snapshot_id = _as_uuid(snapshot_id)
        try:
            with self._engine.begin() as conn:
                snapshot = self._get_snapshot_row(conn, normalized_snapshot_id)
                if snapshot.usage != usage:
                    raise PretradePublishError("快照 usage 与发布 usage 不一致")
                if snapshot.status != "READY":
                    raise PretradePublishError("仅 READY 快照可以发布")
                if usage == "PROD":
                    archive_data_date = self._current_archive_data_date(conn, for_publish=True)
                    if archive_data_date != snapshot.data_date:
                        raise PretradePublishError(
                            "交易前快照与 archive_meta 当前数据日期不一致"
                        )

                values = {
                    "snapshot_id": str(normalized_snapshot_id),
                    "data_date": snapshot.data_date,
                    "published_at": _now_utc_naive(),
                }
                updated = conn.execute(
                    update(PRETRADE_SNAPSHOT_CURRENT)
                    .where(PRETRADE_SNAPSHOT_CURRENT.c.usage == usage)
                    .values(**values)
                )
                if updated.rowcount == 0:
                    conn.execute(insert(PRETRADE_SNAPSHOT_CURRENT).values(usage=usage, **values))
        except PretradeContextStoreError:
            raise
        except SQLAlchemyError as exc:
            raise PretradePublishError("交易前当前指针发布失败") from exc

    def list_snapshot_ids(self) -> list[UUID]:
        """仅供验收审计列出已提交快照。"""

        try:
            with self._engine.connect() as conn:
                rows = conn.execute(
                    select(PRETRADE_SNAPSHOT.c.snapshot_id).order_by(
                        PRETRADE_SNAPSHOT.c.created_at, PRETRADE_SNAPSHOT.c.snapshot_id
                    )
                ).scalars().all()
        except SQLAlchemyError as exc:
            raise PretradeContextStoreError("读取交易前快照列表失败") from exc
        return [UUID(value) for value in rows]

    def _get_snapshot_row(
        self, conn: Connection, snapshot_id: UUID
    ) -> PretradeContextSnapshot:
        row = conn.execute(
            select(PRETRADE_SNAPSHOT).where(
                PRETRADE_SNAPSHOT.c.snapshot_id == str(snapshot_id)
            )
        ).mappings().one_or_none()
        if row is None:
            raise PretradeContextIntegrityError("交易前快照不存在")
        return _snapshot_from_row(row)

    def _load_kernel_input(
        self,
        conn: Connection,
        snapshot_id: UUID,
        *,
        allow_loading: bool,
    ) -> ProductionKernelInput:
        snapshot = self._get_snapshot_row(conn, snapshot_id)
        if snapshot.status != "READY" and not (allow_loading and snapshot.status == "LOADING"):
            raise PretradeContextIntegrityError("仅 READY 快照可以读取")

        dataset_rows = conn.execute(
            select(PRETRADE_SNAPSHOT_DATASET)
            .where(PRETRADE_SNAPSHOT_DATASET.c.snapshot_id == str(snapshot_id))
            .order_by(PRETRADE_SNAPSHOT_DATASET.c.dataset_code)
        ).mappings().all()
        dataset_map = {row["dataset_code"]: row for row in dataset_rows}
        actual_datasets = set(dataset_map)
        expected_datasets = set(KERNEL_INPUT_DATASETS)
        if actual_datasets != expected_datasets:
            missing = sorted(expected_datasets - actual_datasets)
            extra = sorted(actual_datasets - expected_datasets)
            raise PretradeContextIntegrityError(
                "共同内核输入集合不完整"
                f"（缺少: {', '.join(missing) or '无'}；"
                f"冗余: {', '.join(extra) or '无'}）"
            )

        restored_frames: dict[str, pd.DataFrame] = {}
        for dataset_code in KERNEL_INPUT_DATASETS:
            dataset = dataset_map[dataset_code]
            chunk_rows = conn.execute(
                select(
                    PRETRADE_SNAPSHOT_DATASET_CHUNK.c.chunk_ordinal,
                    PRETRADE_SNAPSHOT_DATASET_CHUNK.c.payload,
                )
                .where(
                    and_(
                        PRETRADE_SNAPSHOT_DATASET_CHUNK.c.snapshot_id == str(snapshot_id),
                        PRETRADE_SNAPSHOT_DATASET_CHUNK.c.dataset_code == dataset_code,
                    )
                )
                .order_by(PRETRADE_SNAPSHOT_DATASET_CHUNK.c.chunk_ordinal)
            ).all()
            ordinals = [row.chunk_ordinal for row in chunk_rows]
            if ordinals != list(range(len(ordinals))):
                raise PretradeContextIntegrityError(f"{dataset_code} 的 Parquet 分块不连续")
            if not chunk_rows:
                raise PretradeContextIntegrityError(f"{dataset_code} 缺少 Parquet 分块")
            payload = join_payload(tuple(bytes(row.payload) for row in chunk_rows))
            serialized = SerializedFrame(
                payload=payload,
                content_hash=dataset["content_hash"],
                schema_json=dataset["schema_json"],
                row_count=dataset["row_count"],
                payload_size_bytes=dataset["payload_size_bytes"],
                serializer_version=dataset["serializer_version"],
            )
            try:
                restored_frames[dataset_code] = deserialize_frame(serialized)
            except FrameCodecError as exc:
                raise PretradeContextIntegrityError(
                    f"{dataset_code} 的 Parquet 摘要或结构校验失败"
                ) from exc

        try:
            kernel_input = ProductionKernelInput(
                business_date=pd.Timestamp(snapshot.data_date),
                frames=restored_frames,
                parameters=ProductionKernelParameters(
                    self._snapshot_regulatory_limit(conn, snapshot_id)
                ),
            )
            source_manifest = json.loads(
                self._snapshot_source_manifest(conn, snapshot_id)
            )
            expected_source_hash = sha256(
                _canonical_json(source_manifest).encode("utf-8")
            ).hexdigest()
            if expected_source_hash != snapshot.source_manifest_hash:
                raise PretradeContextIntegrityError("来源清单摘要校验失败")
            recomputed = PretradeSnapshotRequest.from_kernel_input(
                kernel_input,
                usage=snapshot.usage,
                code_commit=self._snapshot_text_field(conn, snapshot_id, "code_commit"),
                engine_version=self._snapshot_text_field(conn, snapshot_id, "engine_version"),
                input_contract_version=self._snapshot_text_field(
                    conn, snapshot_id, "input_contract_version"
                ),
                source_manifest=source_manifest,
            )
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise PretradeContextIntegrityError("交易前快照元数据无法重建") from exc
        if recomputed.input_hash != snapshot.input_hash:
            raise PretradeContextIntegrityError("共同内核输入摘要校验失败")
        return kernel_input

    @staticmethod
    def _snapshot_regulatory_limit(conn: Connection, snapshot_id: UUID) -> float:
        return float(
            conn.execute(
                select(PRETRADE_SNAPSHOT.c.regulatory_concentration_limit).where(
                    PRETRADE_SNAPSHOT.c.snapshot_id == str(snapshot_id)
                )
            ).scalar_one()
        )

    @staticmethod
    def _snapshot_source_manifest(conn: Connection, snapshot_id: UUID) -> str:
        return str(
            conn.execute(
                select(PRETRADE_SNAPSHOT.c.source_manifest_json).where(
                    PRETRADE_SNAPSHOT.c.snapshot_id == str(snapshot_id)
                )
            ).scalar_one()
        )

    @staticmethod
    def _snapshot_text_field(
        conn: Connection, snapshot_id: UUID, field_name: str
    ) -> str:
        columns = {
            "code_commit": PRETRADE_SNAPSHOT.c.code_commit,
            "engine_version": PRETRADE_SNAPSHOT.c.engine_version,
            "input_contract_version": PRETRADE_SNAPSHOT.c.input_contract_version,
        }
        return str(
            conn.execute(
                select(columns[field_name]).where(
                    PRETRADE_SNAPSHOT.c.snapshot_id == str(snapshot_id)
                )
            ).scalar_one()
        )

    @staticmethod
    def _current_archive_data_date(
        conn: Connection, *, for_publish: bool
    ) -> str:
        try:
            rows = conn.execute(
                select_text_current_archive_date()
            ).scalars().all()
        except SQLAlchemyError as exc:
            if for_publish:
                raise PretradePublishError("无法读取 archive_meta 当前数据日期") from exc
            raise PretradeDataSyncError("数据同步中：无法读取 archive_meta 当前数据日期") from exc
        if len(rows) != 1 or rows[0] is None:
            if for_publish:
                raise PretradePublishError("archive_meta 必须恰有一条当前数据")
            raise PretradeDataSyncError("数据同步中：archive_meta 当前数据不可用")
        return str(rows[0])


def select_text_current_archive_date():
    """延迟构造旧表的只读查询，避免把它注册进本模块的 DDL。"""

    from sqlalchemy import text

    return text("SELECT data_date FROM archive_meta WHERE is_current = 1")
