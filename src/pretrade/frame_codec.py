"""DataFrame 的无 Pickle Parquet 编解码。"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import json

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


SERIALIZER_VERSION = "parquet-arrow-v1"
MAX_CHUNK_SIZE_BYTES = 8 * 1024 * 1024


class FrameCodecError(ValueError):
    """Parquet 编解码或完整性验证失败。"""


@dataclass(frozen=True)
class SerializedFrame:
    """可落库的一张输入表及其完整性信息。"""

    payload: bytes
    content_hash: str
    schema_json: str
    row_count: int
    payload_size_bytes: int
    serializer_version: str = SERIALIZER_VERSION


def _sha256(payload: bytes) -> str:
    return sha256(payload).hexdigest()


def _schema_metadata(frame: pd.DataFrame) -> str:
    """保存 pandas 扩展 dtype，确保重建后口径型字段类型稳定。"""

    metadata = {
        "columns": [str(column) for column in frame.columns],
        "dtypes": [str(dtype) for dtype in frame.dtypes],
        "index_name": frame.index.name,
        "index_dtype": str(frame.index.dtype),
    }
    return json.dumps(metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def serialize_frame(frame: pd.DataFrame) -> SerializedFrame:
    """将 DataFrame 编码为 Parquet，并返回可校验的载荷。"""

    if not isinstance(frame, pd.DataFrame):
        raise FrameCodecError("只支持 pandas.DataFrame 输入")
    if not frame.columns.is_unique:
        raise FrameCodecError("共同内核输入表不允许重复列名")

    table = pa.Table.from_pandas(frame, preserve_index=True)
    buffer = BytesIO()
    pq.write_table(table, buffer, compression="zstd")
    payload = buffer.getvalue()

    return SerializedFrame(
        payload=payload,
        content_hash=_sha256(payload),
        schema_json=_schema_metadata(frame),
        row_count=len(frame),
        payload_size_bytes=len(payload),
    )


def deserialize_frame(serialized: SerializedFrame) -> pd.DataFrame:
    """验证摘要后读回一张输入表，并恢复 pandas dtype。"""

    if not isinstance(serialized, SerializedFrame):
        raise FrameCodecError("输入必须是 SerializedFrame")
    if serialized.payload_size_bytes != len(serialized.payload):
        raise FrameCodecError("Parquet 载荷长度校验失败")
    if serialized.content_hash != _sha256(serialized.payload):
        raise FrameCodecError("Parquet 载荷摘要校验失败")
    if serialized.serializer_version != SERIALIZER_VERSION:
        raise FrameCodecError(f"不支持的序列化版本: {serialized.serializer_version}")

    try:
        metadata = json.loads(serialized.schema_json)
        frame = pq.read_table(pa.BufferReader(serialized.payload)).to_pandas()
    except (pa.ArrowException, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise FrameCodecError("Parquet 载荷无法读取") from exc

    expected_columns = metadata.get("columns", [])
    expected_dtypes = metadata.get("dtypes", [])
    if list(map(str, frame.columns)) != expected_columns or len(expected_columns) != len(expected_dtypes):
        raise FrameCodecError("Parquet 列结构与契约不一致")

    for position, dtype in enumerate(expected_dtypes):
        try:
            frame[frame.columns[position]] = frame.iloc[:, position].astype(dtype)
        except (TypeError, ValueError) as exc:
            column = expected_columns[position]
            raise FrameCodecError(f"无法恢复列类型: {column} -> {dtype}") from exc

    frame.index.name = metadata.get("index_name")
    if len(frame) != serialized.row_count:
        raise FrameCodecError("Parquet 行数校验失败")
    return frame


def split_payload(payload: bytes, *, chunk_size: int = MAX_CHUNK_SIZE_BYTES) -> tuple[bytes, ...]:
    """按数据库行安全上限切分 Parquet 载荷。"""

    if not isinstance(payload, bytes):
        raise FrameCodecError("载荷必须是 bytes")
    if chunk_size <= 0:
        raise FrameCodecError("分块大小必须大于零")
    if not payload:
        return (b"",)
    return tuple(payload[offset : offset + chunk_size] for offset in range(0, len(payload), chunk_size))


def join_payload(chunks: Iterable[bytes]) -> bytes:
    """按序合并数据库中读取的 Parquet 分块。"""

    normalized_chunks = tuple(chunks)
    if not all(isinstance(chunk, bytes) for chunk in normalized_chunks):
        raise FrameCodecError("Parquet 分块必须是 bytes")
    return b"".join(normalized_chunks)
