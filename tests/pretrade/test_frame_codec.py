from __future__ import annotations

from decimal import Decimal

import pandas as pd
import pandas.testing as pdt
import pytest

from src.pretrade.frame_codec import (
    FrameCodecError,
    deserialize_frame,
    serialize_frame,
)


def test_parquet_round_trip_preserves_values_dtypes_columns_and_index() -> None:
    frame = pd.DataFrame(
        {
            "日期": pd.Series(
                [pd.Timestamp("2026-07-10"), pd.NaT], dtype="datetime64[ns]"
            ),
            "金额": pd.Series([1.2, None], dtype="object"),
            "代码": pd.Series(["102480811.IB", pd.NA], dtype="string"),
            "数量": pd.Series([1, pd.NA], dtype="Int64"),
        },
        index=pd.Index(["a", "b"], name="行"),
    )

    restored = deserialize_frame(serialize_frame(frame))

    pdt.assert_frame_equal(restored, frame, check_dtype=True, check_exact=True)


def test_parquet_round_trip_preserves_an_empty_frame_schema() -> None:
    frame = pd.DataFrame(
        {
            "代码": pd.Series(dtype="string"),
            "金额": pd.Series(dtype="Float64"),
            "日期": pd.Series(dtype="datetime64[ns]"),
        }
    )

    restored = deserialize_frame(serialize_frame(frame))

    pdt.assert_frame_equal(restored, frame, check_dtype=True, check_exact=True)


def test_parquet_round_trip_preserves_supported_mixed_object_cells_without_pickle() -> None:
    frame = pd.DataFrame(
        {
            "特殊条款": pd.Series(
                ["含回售", 0, 1.25, True, None, pd.NA],
                dtype="object",
            )
        }
    )

    restored = deserialize_frame(serialize_frame(frame))

    pdt.assert_frame_equal(restored, frame, check_dtype=True, check_exact=True)


def test_parquet_rejects_unsupported_object_cells() -> None:
    frame = pd.DataFrame({"特殊条款": pd.Series([Decimal("1.25")], dtype="object")})

    with pytest.raises(FrameCodecError, match="不支持"):
        serialize_frame(frame)
