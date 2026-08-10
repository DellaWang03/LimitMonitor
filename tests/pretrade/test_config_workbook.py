from __future__ import annotations

from hashlib import sha256

import pytest

from src.pretrade.config_workbook import (
    LIMIT_CONFIG_WORKBOOK_NAME,
    PretradeConfigWorkbookError,
    capture_config_workbook,
)


def test_capture_reads_exact_stage1_config_bytes(tmp_path) -> None:
    payload = b"PK\x03\x04fixture-xlsx"
    source = tmp_path / LIMIT_CONFIG_WORKBOOK_NAME
    source.write_bytes(payload)

    class Config:
        def get_data_file_path(self, name):
            assert name == LIMIT_CONFIG_WORKBOOK_NAME
            return source

    workbook = capture_config_workbook(Config())

    assert workbook.file_name == LIMIT_CONFIG_WORKBOOK_NAME
    assert workbook.payload == payload
    assert workbook.payload_hash == sha256(payload).hexdigest()


def test_capture_rejects_missing_workbook(tmp_path) -> None:
    class Config:
        def get_data_file_path(self, name):
            return tmp_path / name

    with pytest.raises(PretradeConfigWorkbookError, match="无法读取"):
        capture_config_workbook(Config())
