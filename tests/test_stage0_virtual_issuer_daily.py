from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.stage0.stage0_processor import Stage0Processor


def _make_processor(tmp_path: Path) -> Stage0Processor:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    output_dir = tmp_path / "out"

    pd.DataFrame(
        {"日期": pd.to_datetime(["2026-06-10", "2026-06-11", "2026-06-12"])}
    ).to_excel(data_dir / "标准日期表.xlsx", sheet_name="标准日期表", index=False)

    return Stage0Processor(data_dir, output_dir, target_date="2026-06-12")


def test_virtual_issuer_daily_keeps_latest_effective_pool_per_issuer_and_date(tmp_path):
    processor = _make_processor(tmp_path)
    processor.cache["风控部债券池_主体_虚拟添加"] = pd.DataFrame(
        [
            {"变动日期": "2023-09-01", "发行人名称": "北京汽车股份有限公司", "主体池": "B"},
            {"变动日期": "2025-06-20", "发行人名称": "北京汽车股份有限公司", "主体池": "A"},
            {"变动日期": "2025-06-20", "发行人名称": "晋江市路桥建设开发有限公司", "主体池": "C"},
            {"变动日期": "2025-06-20", "发行人名称": "晋江市路桥建设开发有限公司", "主体池": "B"},
        ]
    )
    processor.cache["债券池日期"] = pd.DataFrame({"日期": pd.to_datetime(["2026-06-11"])})

    result = processor.query_virtual_issuer_daily()

    assert result.duplicated(subset=["日期", "发行人名称"]).sum() == 0
    pool_by_issuer = result.set_index("发行人名称")["主体池"].to_dict()
    assert pool_by_issuer == {
        "北京汽车股份有限公司": "A",
        "晋江市路桥建设开发有限公司": "B",
    }


def test_issuer_pool_reports_conflicting_pool_per_issuer_and_date(tmp_path):
    processor = _make_processor(tmp_path)
    processor.wind_resolver.get_code = lambda _name, strict=False: "TEST.WI"
    base_date = pd.Timestamp("2026-06-11")
    processor.cache["原始风控部债券池_主体"] = pd.DataFrame(
        [{"日期": base_date, "发行人名称": "冲突主体", "主体池": "A"}]
    )
    processor.cache["风控部债券池_主体_虚拟添加_每日"] = pd.DataFrame(
        [{"日期": base_date, "发行人名称": "冲突主体", "主体池": "B"}]
    )

    with pytest.raises(ValueError, match="风控部主体池存在同日同发行人多个主体池"):
        processor.query_issuer_pool()
