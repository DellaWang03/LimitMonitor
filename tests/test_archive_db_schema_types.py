from __future__ import annotations

import pytest

sqlalchemy = pytest.importorskip("sqlalchemy")

from sqlalchemy.dialects.mysql import BIGINT, DECIMAL, DOUBLE, INTEGER, LONGTEXT

from src.utils.archive_db import _should_widen_to_double


def test_should_widen_integer_or_zero_scale_decimal_columns_for_float_data():
    assert _should_widen_to_double(BIGINT(), DOUBLE())
    assert _should_widen_to_double(INTEGER(), DOUBLE())
    assert _should_widen_to_double(DECIMAL(20, 0), DOUBLE())


def test_should_not_widen_non_numeric_or_already_float_columns():
    assert not _should_widen_to_double(DOUBLE(), DOUBLE())
    assert not _should_widen_to_double(LONGTEXT(), DOUBLE())
    assert not _should_widen_to_double(BIGINT(), BIGINT())
