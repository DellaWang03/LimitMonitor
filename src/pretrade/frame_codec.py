"""DataFrame 的无 Pickle Parquet 编解码。"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import json
from numbers import Integral, Real

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


SERIALIZER_VERSION = "parquet-arrow-v1"


class FrameCodecError(ValueError):
    """Parquet 编解码或完整性验证失败。"""


@dataclass(frozen=True)
class SerializedFrame:
    """可落库的一张输入表及其完整性信息。"""

    payload: bytes
    payload_hash: str
    schema_json: str


def _sha256(payload: bytes) -> str:
    return sha256(payload).hexdigest()


def _schema_metadata(
    frame: pd.DataFrame,
    *,
    tagged_object_column_positions: tuple[int, ...],
) -> str:
    """保存 pandas 扩展 dtype，确保重建后口径型字段类型稳定。"""

    metadata = {
        "columns": [str(column) for column in frame.columns],
        "dtypes": [str(dtype) for dtype in frame.dtypes],
        "index_name": frame.index.name,
        "tagged_object_column_positions": list(tagged_object_column_positions),
    }
    return json.dumps(metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _encode_object_cell(value: object) -> dict[str, object]:
    """将 object 列单元格编码为类型化 JSON，避免 Arrow 对混合列的隐式推断。"""

    if value is None:
        return {"type": "none"}
    if value is pd.NA:
        return {"type": "pd_na"}
    if value is pd.NaT:
        return {"type": "pd_nat"}
    if isinstance(value, bool):
        return {"type": "bool", "value": value}
    if isinstance(value, str):
        return {"type": "str", "value": value}
    if isinstance(value, Integral):
        return {"type": "int", "value": str(int(value))}
    if isinstance(value, Real):
        return {"type": "float", "value": repr(float(value))}
    raise FrameCodecError(f"object 列包含不支持的单元格类型: {type(value).__name__}")


def _decode_object_cell(encoded: str) -> object:
    try:
        value = json.loads(encoded)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise FrameCodecError("object 单元格编码无效") from exc
    if not isinstance(value, dict) or not isinstance(value.get("type"), str):
        raise FrameCodecError("object 单元格编码缺少类型")

    cell_type = value["type"]
    raw = value.get("value")
    try:
        if cell_type == "none":
            return None
        if cell_type == "pd_na":
            return pd.NA
        if cell_type == "pd_nat":
            return pd.NaT
        if cell_type == "bool" and isinstance(raw, bool):
            return raw
        if cell_type == "str" and isinstance(raw, str):
            return raw
        if cell_type == "int" and isinstance(raw, str):
            return int(raw)
        if cell_type == "float" and isinstance(raw, str):
            return float(raw)
    except (TypeError, ValueError) as exc:
        raise FrameCodecError(f"object 单元格无法解码: {cell_type}") from exc
    raise FrameCodecError(f"object 单元格类型或值无效: {cell_type}")


def _prepare_for_parquet(frame: pd.DataFrame) -> tuple[pd.DataFrame, tuple[int, ...]]:
    """显式编码 object 列，保留原 DataFrame 的混合 Python 标量语义。"""

    prepared = frame.copy(deep=True)
    encoded_positions: list[int] = []
    for position, dtype in enumerate(frame.dtypes):
        if not pd.api.types.is_object_dtype(dtype):
            continue
        encoded = [
            json.dumps(
                _encode_object_cell(value),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            for value in frame.iloc[:, position].tolist()
        ]
        prepared[prepared.columns[position]] = pd.Series(
            encoded,
            index=frame.index,
            dtype="string",
        )
        encoded_positions.append(position)
    return prepared, tuple(encoded_positions)


def serialize_frame(frame: pd.DataFrame) -> SerializedFrame:
    """将 DataFrame 编码为 Parquet，并返回可校验的载荷。"""

    if not isinstance(frame, pd.DataFrame):
        raise FrameCodecError("只支持 pandas.DataFrame 输入")
    if not frame.columns.is_unique:
        raise FrameCodecError("共同内核输入表不允许重复列名")

    prepared, tagged_object_column_positions = _prepare_for_parquet(frame)
    try:
        table = pa.Table.from_pandas(prepared, preserve_index=True)
    except (pa.ArrowException, TypeError, ValueError) as exc:
        raise FrameCodecError("DataFrame 无法编码为 Parquet") from exc
    buffer = BytesIO()
    pq.write_table(table, buffer, compression="zstd")
    payload = buffer.getvalue()

    return SerializedFrame(
        payload=payload,
        payload_hash=_sha256(payload),
        schema_json=_schema_metadata(
            frame,
            tagged_object_column_positions=tagged_object_column_positions,
        ),
    )


def deserialize_frame(serialized: SerializedFrame) -> pd.DataFrame:
    """验证摘要后读回一张输入表，并恢复 pandas dtype。"""

    if not isinstance(serialized, SerializedFrame):
        raise FrameCodecError("输入必须是 SerializedFrame")
    if serialized.payload_hash != _sha256(serialized.payload):
        raise FrameCodecError("Parquet 载荷摘要校验失败")

    try:
        metadata = json.loads(serialized.schema_json)
        frame = pq.read_table(pa.BufferReader(serialized.payload)).to_pandas()
    except (pa.ArrowException, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise FrameCodecError("Parquet 载荷无法读取") from exc

    expected_columns = metadata.get("columns", [])
    expected_dtypes = metadata.get("dtypes", [])
    if list(map(str, frame.columns)) != expected_columns or len(expected_columns) != len(expected_dtypes):
        raise FrameCodecError("Parquet 列结构与契约不一致")

    encoded_positions = metadata.get("tagged_object_column_positions", [])
    if (
        not isinstance(encoded_positions, list)
        or len(set(encoded_positions)) != len(encoded_positions)
        or any(not isinstance(position, int) or position < 0 or position >= len(frame.columns) for position in encoded_positions)
    ):
        raise FrameCodecError("object 列编码元数据无效")
    encoded_position_set = set(encoded_positions)

    for position, dtype in enumerate(expected_dtypes):
        try:
            if position in encoded_position_set:
                decoded = [
                    _decode_object_cell(value)
                    for value in frame.iloc[:, position].tolist()
                ]
                frame[frame.columns[position]] = pd.Series(
                    decoded,
                    index=frame.index,
                    dtype="object",
                )
            else:
                frame[frame.columns[position]] = frame.iloc[:, position].astype(dtype)
        except (FrameCodecError, TypeError, ValueError) as exc:
            column = expected_columns[position]
            raise FrameCodecError(f"无法恢复列类型: {column} -> {dtype}") from exc

    frame.index.name = metadata.get("index_name")
    return frame
