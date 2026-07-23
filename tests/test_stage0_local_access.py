from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.stage0 import stage0_processor
from src.stage0.stage0_processor import Stage0Processor


class _ReaderCapture:
    init_kwargs: dict[str, object]

    def __init__(self, db_path: Path, **kwargs: object) -> None:
        self.db_path = db_path
        type(self).init_kwargs = kwargs

    def read_table(self, table_name: str) -> pd.DataFrame:
        assert table_name == "风控部债券池"
        return pd.DataFrame(
            [
                {
                    "日期": "2026-07-10",
                    "债券代码": "102480811",
                    "市场名称": "银行间",
                    "发行人名称": "测试发行人 ",
                }
            ]
        )


def test_local_stage0_enables_mdb_export_from_its_own_accdb(
    monkeypatch, tmp_path: Path
):
    """local profile must not silently fall back to an old stage0 output."""
    accdb_path = tmp_path / "风控部债券池.accdb"
    accdb_path.touch()

    processor = object.__new__(Stage0Processor)
    processor.data_dir = tmp_path
    processor.config = None
    processor.target_date = None
    processor._data_file_path = lambda _file_name: accdb_path

    monkeypatch.setattr(stage0_processor, "AccessDatabaseReader", _ReaderCapture)

    result = processor.query_bond_pool()

    assert _ReaderCapture.init_kwargs["export_dir"] == tmp_path
    assert _ReaderCapture.init_kwargs["source_accdb_path"] == accdb_path
    assert result.loc[0, "发行人名称"] == "测试发行人"
    assert result.loc[0, "代码"] == "102480811.IB"


def test_stage0_required_query_failure_is_raised_without_running_later_queries(
    monkeypatch, tmp_path: Path
) -> None:
    processor = object.__new__(Stage0Processor)
    processor.output_dir = tmp_path
    processor.cache = {}
    calls: list[str] = []

    def fail_first() -> pd.DataFrame:
        calls.append("first")
        raise RuntimeError("required query failed")

    def later_query() -> pd.DataFrame:
        calls.append("later")
        return pd.DataFrame()

    processor.query_beijing_guoyou = fail_first
    for name in (
        "query_adjusted_controller",
        "query_bond_pool",
        "query_original_issuer_pool",
        "query_virtual_issuer_addition",
        "query_bond_pool_dates",
        "query_virtual_issuer_daily",
        "query_issuer_pool",
        "query_net_assets_manual",
        "query_net_assets_daily",
    ):
        setattr(processor, name, later_query)
    monkeypatch.setattr(pd.DataFrame, "to_excel", lambda *args, **kwargs: None)

    with pytest.raises(RuntimeError, match="required query failed"):
        processor.process_all()

    assert calls == ["first"]
