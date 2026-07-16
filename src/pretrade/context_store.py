"""交易前共同内核输入的最小事务型存储。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pandas as pd
from sqlalchemy import (
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
    insert,
    select,
    text,
    update,
)
from sqlalchemy.dialects.mysql import LONGBLOB as MYSQL_LONGBLOB
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import SQLAlchemyError

from src.risk_core import ProductionKernelInput, ProductionKernelParameters

from .frame_codec import FrameCodecError, SerializedFrame, deserialize_frame, serialize_frame
from .input_contract import KERNEL_INPUT_DATASETS, PretradeSnapshotRequest


PRETRADE_METADATA = MetaData()

PRETRADE_SNAPSHOT = Table(
    "pretrade_snapshot",
    PRETRADE_METADATA,
    Column("snapshot_id", String(36), primary_key=True),
    Column("data_date", String(10), nullable=False),
    Column("regulatory_concentration_limit", Float, nullable=False),
    Column("captured_at", DateTime, nullable=False),
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
    Column("schema_json", Text, nullable=False),
    Column("payload_hash", String(64), nullable=False),
    Column(
        "payload",
        LargeBinary().with_variant(MYSQL_LONGBLOB(), "mysql"),
        nullable=False,
    ),
)

PRETRADE_SNAPSHOT_CURRENT = Table(
    "pretrade_snapshot_current",
    PRETRADE_METADATA,
    Column("pointer_id", Integer, primary_key=True),
    Column(
        "snapshot_id",
        String(36),
        ForeignKey("pretrade_snapshot.snapshot_id"),
        nullable=False,
    ),
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
    """快照的必要业务元数据。"""

    snapshot_id: UUID
    data_date: str
    captured_at: datetime


def _now_utc_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _as_uuid(snapshot_id: UUID | str) -> UUID:
    try:
        return UUID(str(snapshot_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise PretradeContextStoreError("snapshot_id 必须是有效 UUID") from exc


def _snapshot_from_row(row: Any) -> PretradeContextSnapshot:
    return PretradeContextSnapshot(
        snapshot_id=UUID(row["snapshot_id"]),
        data_date=str(row["data_date"]),
        captured_at=row["captured_at"],
    )


class PretradeContextStore:
    """对三张交易前上下文表的唯一读写入口。"""

    def __init__(self, engine: Engine) -> None:
        if not isinstance(engine, Engine):
            raise TypeError("engine 必须是 SQLAlchemy Engine")
        self._engine = engine

    def prepare_schema(self) -> None:
        """幂等创建三张新增表，不触碰既有归档表。"""

        PRETRADE_METADATA.create_all(self._engine)

    def write_snapshot(
        self,
        request: PretradeSnapshotRequest,
        *,
        fail_after_dataset: int | None = None,
    ) -> UUID:
        """在一个事务中写入 header 和全部 27 项输入。"""

        if not isinstance(request, PretradeSnapshotRequest):
            raise TypeError("request 必须是 PretradeSnapshotRequest")
        if fail_after_dataset is not None and fail_after_dataset < 1:
            raise ValueError("fail_after_dataset 必须大于零")

        snapshot_id = uuid4()
        snapshot_id_text = str(snapshot_id)
        frames = request.kernel_input.detached_frames()
        try:
            serialized_frames = {
                dataset_code: serialize_frame(frames[dataset_code])
                for dataset_code in KERNEL_INPUT_DATASETS
            }
            with self._engine.begin() as conn:
                conn.execute(
                    insert(PRETRADE_SNAPSHOT).values(
                        snapshot_id=snapshot_id_text,
                        data_date=request.kernel_input.business_date.date().isoformat(),
                        regulatory_concentration_limit=(
                            request.kernel_input.parameters.regulatory_concentration_limit
                        ),
                        captured_at=_now_utc_naive(),
                    )
                )
                for ordinal, dataset_code in enumerate(KERNEL_INPUT_DATASETS, start=1):
                    serialized = serialized_frames[dataset_code]
                    conn.execute(
                        insert(PRETRADE_SNAPSHOT_DATASET).values(
                            snapshot_id=snapshot_id_text,
                            dataset_code=dataset_code,
                            schema_json=serialized.schema_json,
                            payload_hash=serialized.payload_hash,
                            payload=serialized.payload,
                        )
                    )
                    if (
                        fail_after_dataset is not None
                        and ordinal >= fail_after_dataset
                    ):
                        raise RuntimeError("injected dataset failure")
        except (PretradeContextStoreError, RuntimeError):
            raise
        except (SQLAlchemyError, FrameCodecError, ValueError, TypeError) as exc:
            raise PretradeContextStoreError("交易前快照写入失败") from exc

        return snapshot_id

    def load_kernel_input(self, snapshot_id: UUID | str) -> ProductionKernelInput:
        """从一份完整快照重建共同内核唯一输入。"""

        normalized_snapshot_id = _as_uuid(snapshot_id)
        try:
            with self._engine.connect() as conn:
                return self._load_kernel_input(conn, normalized_snapshot_id)
        except PretradeContextStoreError:
            raise
        except (SQLAlchemyError, FrameCodecError, ValueError, TypeError) as exc:
            raise PretradeContextIntegrityError("交易前快照读取失败") from exc

    def get_current_snapshot(self) -> PretradeContextSnapshot | None:
        """取得唯一 current；与既有归档不同日时拒绝读取。"""

        try:
            with self._engine.connect() as conn:
                pointer = conn.execute(
                    select(PRETRADE_SNAPSHOT_CURRENT).where(
                        PRETRADE_SNAPSHOT_CURRENT.c.pointer_id == 1
                    )
                ).mappings().one_or_none()
                if pointer is None:
                    return None
                snapshot = self._get_snapshot_row(conn, UUID(pointer["snapshot_id"]))
                archive_data_date = self._current_archive_data_date(
                    conn, for_publish=False
                )
                if archive_data_date != snapshot.data_date:
                    raise PretradeDataSyncError(
                        "数据同步中：展示归档与交易前上下文的数据日期不一致"
                    )
                return snapshot
        except PretradeContextStoreError:
            raise
        except SQLAlchemyError as exc:
            raise PretradeContextStoreError("读取交易前当前指针失败") from exc

    def load_current_kernel_input(self) -> ProductionKernelInput:
        """读取唯一 current 的完整共同内核输入。"""

        snapshot = self.get_current_snapshot()
        if snapshot is None:
            raise PretradeContextIntegrityError("交易前当前快照不存在")
        return self.load_kernel_input(snapshot.snapshot_id)

    def publish_current(self, snapshot_id: UUID | str) -> None:
        """读回验证快照且确认归档日期一致后，切换唯一 current。"""

        normalized_snapshot_id = _as_uuid(snapshot_id)
        try:
            with self._engine.begin() as conn:
                snapshot = self._get_snapshot_row(conn, normalized_snapshot_id)
                self._load_kernel_input(conn, normalized_snapshot_id)
                archive_data_date = self._current_archive_data_date(conn, for_publish=True)
                if archive_data_date != snapshot.data_date:
                    raise PretradePublishError(
                        "交易前快照与 archive_meta 当前数据日期不一致"
                    )
                values = {"snapshot_id": str(normalized_snapshot_id)}
                updated = conn.execute(
                    update(PRETRADE_SNAPSHOT_CURRENT)
                    .where(PRETRADE_SNAPSHOT_CURRENT.c.pointer_id == 1)
                    .values(**values)
                )
                if updated.rowcount == 0:
                    conn.execute(
                        insert(PRETRADE_SNAPSHOT_CURRENT).values(
                            pointer_id=1, **values
                        )
                    )
        except PretradeContextStoreError:
            raise
        except (SQLAlchemyError, FrameCodecError, ValueError, TypeError) as exc:
            raise PretradePublishError("交易前当前指针发布失败") from exc

    def list_snapshot_ids(self) -> list[UUID]:
        try:
            with self._engine.connect() as conn:
                rows = conn.execute(
                    select(PRETRADE_SNAPSHOT.c.snapshot_id).order_by(
                        PRETRADE_SNAPSHOT.c.captured_at,
                        PRETRADE_SNAPSHOT.c.snapshot_id,
                    )
                ).scalars().all()
        except SQLAlchemyError as exc:
            raise PretradeContextStoreError("读取交易前快照列表失败") from exc
        return [UUID(value) for value in rows]

    @staticmethod
    def _get_snapshot_row(
        conn: Connection, snapshot_id: UUID
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
        self, conn: Connection, snapshot_id: UUID
    ) -> ProductionKernelInput:
        snapshot = self._get_snapshot_row(conn, snapshot_id)
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
            serialized = SerializedFrame(
                payload=bytes(dataset["payload"]),
                payload_hash=dataset["payload_hash"],
                schema_json=dataset["schema_json"],
            )
            try:
                restored_frames[dataset_code] = deserialize_frame(serialized)
            except FrameCodecError as exc:
                raise PretradeContextIntegrityError(
                    f"{dataset_code} 的 Parquet 摘要或结构校验失败"
                ) from exc

        try:
            return ProductionKernelInput(
                business_date=pd.Timestamp(snapshot.data_date),
                frames=restored_frames,
                parameters=ProductionKernelParameters(
                    float(
                        conn.execute(
                            select(
                                PRETRADE_SNAPSHOT.c.regulatory_concentration_limit
                            ).where(
                                PRETRADE_SNAPSHOT.c.snapshot_id == str(snapshot_id)
                            )
                        ).scalar_one()
                    )
                ),
            )
        except (TypeError, ValueError) as exc:
            raise PretradeContextIntegrityError("交易前快照元数据无法重建") from exc

    @staticmethod
    def _current_archive_data_date(
        conn: Connection, *, for_publish: bool
    ) -> str:
        try:
            rows = conn.execute(select_text_current_archive_date()).scalars().all()
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
    """延迟构造旧表只读查询，避免注册到新增表 DDL。"""

    return text("SELECT data_date FROM archive_meta WHERE is_current = 1")
