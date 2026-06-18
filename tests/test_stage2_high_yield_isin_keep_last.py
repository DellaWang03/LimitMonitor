from __future__ import annotations

import pandas as pd

from src.stage2 import stage2_processor
from src.stage2.stage2_processor import (
    Stage2Processor,
    _build_penetrate_isin_type_map_keep_last,
)


def test_stage2_penetrate_high_yield_load_preserves_source_rows(monkeypatch, tmp_path):
    def fake_load_limit_config(*, sheet_name, **kwargs):
        assert sheet_name == "穿透高收益债券"
        return pd.DataFrame(
            [
                {
                    "债券代码": "OLD.MOX",
                    "ISIN代码": "XS0000000001",
                    "名称": "旧名称",
                    "类型": "高收益",
                },
                {
                    "债券代码": "NEW.MOX",
                    "ISIN代码": "XS0000000001",
                    "名称": "新名称",
                    "类型": "非高收益",
                },
            ]
        )

    monkeypatch.setattr(stage2_processor, "load_limit_config", fake_load_limit_config)

    processor = Stage2Processor(
        data_dir=tmp_path,
        output_dir=tmp_path / "out",
        stage0_output_dir=tmp_path / "stage0",
        stage1_output_dir=tmp_path / "stage1",
    )

    result = processor.query_penetrate_high_yield()

    assert len(result) == 2
    assert result["债券代码"].tolist() == ["OLD.MOX", "NEW.MOX"]


def test_stage2_penetrate_isin_type_map_keeps_last_duplicate_isin():
    mapping = _build_penetrate_isin_type_map_keep_last(
        pd.DataFrame(
            [
                {
                    "债券代码": "OLD.MOX",
                    "ISIN代码": "XS0000000001",
                    "名称": "旧名称",
                    "类型": "高收益",
                },
                {
                    "债券代码": "NEW.MOX",
                    "ISIN代码": "XS0000000001",
                    "名称": "新名称",
                    "类型": "非高收益",
                },
            ]
        )
    )

    assert mapping == {"XS0000000001": "非高收益"}
