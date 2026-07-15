"""在一个 Python 进程中顺序执行既有 Stage0/1/2 处理器。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from src.stage0 import Stage0Processor
from src.stage1 import Stage1Processor
from src.stage2 import Stage2Processor


@dataclass(frozen=True)
class DailyRuntimeResult:
    """保留本次计算的处理器和既有输出，供交易前上下文捕获。"""

    stage0_results: Mapping[str, pd.DataFrame]
    stage1_processor: Stage1Processor
    stage2_processor: Stage2Processor
    stage1_results: Mapping[str, pd.DataFrame]
    stage2_results: Mapping[str, pd.DataFrame]


def run_daily_runtime(
    *,
    config: Any,
    data_dir: Path,
    current_dir: Path,
    target_date: str | None = None,
) -> DailyRuntimeResult:
    """复用上线处理器，并保留其实际运行期缓存。

    处理器构造参数和输出目录与原来的三个脚本完全一致；本函数不解释或重算
    任何业务规则。任一阶段抛错会立即中止，不会构造下游处理器。
    """

    data_dir = Path(data_dir)
    current_dir = Path(current_dir)
    stage0_output_dir = current_dir / "stage0_output"
    stage1_output_dir = current_dir / "stage1_output"
    stage2_output_dir = current_dir / "stage2_output"

    stage0 = Stage0Processor(
        data_dir=data_dir,
        output_dir=stage0_output_dir,
        config=config,
        target_date=target_date,
    )
    stage0_results = stage0.process_all()

    stage1 = Stage1Processor(
        data_dir=data_dir,
        output_dir=stage1_output_dir,
        stage0_output_dir=stage0_output_dir,
        config=config,
    )
    stage1_results = stage1.process_all()

    stage2 = Stage2Processor(
        data_dir=data_dir,
        output_dir=stage2_output_dir,
        stage0_output_dir=stage0_output_dir,
        stage1_output_dir=stage1_output_dir,
        config=config,
    )
    stage2_results = stage2.process_all()

    return DailyRuntimeResult(
        stage0_results=stage0_results,
        stage1_processor=stage1,
        stage2_processor=stage2,
        stage1_results=stage1_results,
        stage2_results=stage2_results,
    )
