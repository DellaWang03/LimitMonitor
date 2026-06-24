from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.common.wind_code_resolver import WindCodeResolver
from src.stage0.stage0_processor import Stage0Processor


class PartialExcelHelper:
    def batch_get_wind_codes(self, issuer_names: list[str]) -> pd.DataFrame:
        assert issuer_names == ["已补主体", "零值主体", "错误值主体", "仍缺主体"]
        return pd.DataFrame(
            [
                {"发行人名称": "已补主体", "Wind代码": "RESOLVED.WI"},
                {"发行人名称": "零值主体", "Wind代码": "0"},
                {"发行人名称": "错误值主体", "Wind代码": "#N/A"},
            ]
        )


def test_batch_resolve_missing_keeps_unresolved_issuers(tmp_path: Path):
    resolver = WindCodeResolver(
        data_dir=tmp_path,
        use_excel_helper=False,
        cache_new_codes=True,
    )
    resolver.excel_helper = PartialExcelHelper()
    resolver.missing_issuers = ["已补主体", "零值主体", "错误值主体", "仍缺主体"]

    resolved = resolver.batch_resolve_missing()

    assert resolved == 2
    assert resolver.get_code("已补主体") == "RESOLVED.WI"
    assert resolver.get_code("零值主体") == "0"
    assert resolver.missing_issuers == ["错误值主体", "仍缺主体"]


def test_zero_wind_code_is_not_cached_for_future_runs(tmp_path: Path):
    mapping_file = tmp_path / "issuer_wind_code_mapping.csv"
    pd.DataFrame(
        [
            {"发行人": "错误值主体", "wind代码": "#N/A"},
            {"发行人": "零值主体", "wind代码": "0"},
            {"发行人": "零值文本主体", "wind代码": "0.00"},
            {"发行人": "正常主体", "wind代码": "NORMAL.WI"},
        ]
    ).to_csv(mapping_file, index=False)

    resolver = WindCodeResolver(
        data_dir=tmp_path,
        mapping_file=mapping_file,
        use_excel_helper=False,
    )

    assert resolver.get_code("错误值主体") is None
    assert resolver.get_code("零值主体") is None
    assert resolver.get_code("零值文本主体") is None
    assert resolver.get_code("正常主体") == "NORMAL.WI"
    assert resolver.missing_issuers == ["错误值主体", "零值主体", "零值文本主体"]


def test_cache_code_replaces_old_invalid_rows(tmp_path: Path):
    mapping_file = tmp_path / "issuer_wind_code_mapping.csv"
    pd.DataFrame(
        [
            {"发行人": "旧零值主体", "wind代码": "0"},
            {"发行人": "旧零值主体", "wind代码": "#N/A"},
        ]
    ).to_csv(mapping_file, index=False)
    resolver = WindCodeResolver(
        data_dir=tmp_path,
        mapping_file=mapping_file,
        use_excel_helper=False,
    )

    resolver._cache_code("旧零值主体", "REAL.WI")

    assert resolver.get_code("旧零值主体") == "REAL.WI"
    saved = pd.read_csv(mapping_file)
    assert saved[saved["发行人"] == "旧零值主体"]["wind代码"].tolist() == ["REAL.WI"]


def test_stage0_stops_when_wind_codes_remain_missing(tmp_path: Path):
    processor = Stage0Processor(tmp_path / "data", tmp_path / "out")
    empty = pd.DataFrame({"占位": []})

    for attr in [
        "query_beijing_guoyou",
        "query_adjusted_controller",
        "query_bond_pool",
        "query_original_issuer_pool",
        "query_virtual_issuer_addition",
        "query_bond_pool_dates",
        "query_virtual_issuer_daily",
        "query_issuer_pool",
        "query_net_assets_manual",
        "query_net_assets_daily",
    ]:
        setattr(processor, attr, lambda df=empty: df.copy())

    processor.wind_resolver.missing_issuers = ["仍缺主体"]
    processor.wind_resolver.batch_resolve_missing = lambda: 0

    with pytest.raises(RuntimeError, match="Wind代码未完全获得"):
        processor.process_all()
