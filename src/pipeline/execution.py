"""Run the deployed Stage0/1/2 processors without reproducing their rules."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from ..stage0.stage0_processor import Stage0Processor
from ..stage1.stage1_processor import Stage1Processor
from ..stage2.stage2_processor import Stage2Processor
from ..testing.frozen_config import FrozenInputConfig
from ..testing.frozen_manifest import ValidatedInputManifest
from .paths import PipelinePaths


class BaselineExecutionError(RuntimeError):
    """The frozen production pipeline failed or violated its output contract."""


@dataclass(frozen=True)
class BaselineRunRequest:
    manifest: ValidatedInputManifest
    config: FrozenInputConfig
    paths: PipelinePaths
    business_date: date

    def __post_init__(self) -> None:
        if self.business_date != self.manifest.expected_business_date:
            raise BaselineExecutionError(
                "请求业务日期必须等于冻结清单 expected_business_date"
            )
        if self.config.manifest is not self.manifest:
            raise BaselineExecutionError("请求和冻结配置必须引用同一清单实例")
        for path in self.paths.children:
            if not path.is_relative_to(self.paths.root):
                raise BaselineExecutionError(f"流水线路径逃逸运行根目录: {path}")


@dataclass(frozen=True)
class TableRunSummary:
    name: str
    row_count: int
    column_count: int


@dataclass(frozen=True)
class StageRunResult:
    stage: str
    output_dir: Path
    tables: tuple[TableRunSummary, ...]

    @property
    def table_names(self) -> tuple[str, ...]:
        return tuple(table.name for table in self.tables)


@dataclass(frozen=True)
class BaselineRunResult:
    business_date: date
    stages: tuple[StageRunResult, ...]


def run_frozen_pipeline(request: BaselineRunRequest) -> BaselineRunResult:
    """Execute only the existing production processors, in dependency order."""

    stage0 = _construct(
        "stage0",
        Stage0Processor,
        data_dir=request.manifest.input_root,
        output_dir=request.paths.stage0,
        config=request.config,
        target_date=request.business_date.isoformat(),
    )
    stage0_result = _run_stage("stage0", request.paths.stage0, stage0.process_all)

    stage1 = _construct(
        "stage1",
        Stage1Processor,
        data_dir=request.manifest.input_root,
        output_dir=request.paths.stage1,
        stage0_output_dir=request.paths.stage0,
        config=request.config,
    )
    stage1_result = _run_stage("stage1", request.paths.stage1, stage1.process_all)

    stage2 = _construct(
        "stage2",
        Stage2Processor,
        data_dir=request.manifest.input_root,
        output_dir=request.paths.stage2,
        stage0_output_dir=request.paths.stage0,
        stage1_output_dir=request.paths.stage1,
        config=request.config,
    )
    stage2_result = _run_stage("stage2", request.paths.stage2, stage2.process_all)

    return BaselineRunResult(
        business_date=request.business_date,
        stages=(stage0_result, stage1_result, stage2_result),
    )


def _construct(stage: str, constructor: Callable[..., Any], **kwargs: Any) -> Any:
    try:
        return constructor(**kwargs)
    except Exception as exc:
        raise BaselineExecutionError(f"{stage} 初始化失败: {exc}") from exc


def _run_stage(
    stage: str,
    output_dir: Path,
    process_all: Callable[[], object],
) -> StageRunResult:
    try:
        raw_result = process_all()
    except Exception as exc:
        raise BaselineExecutionError(f"{stage} 执行失败: {exc}") from exc
    return _validate_stage_result(stage, output_dir, raw_result)


def _validate_stage_result(
    stage: str,
    output_dir: Path,
    raw_result: object,
) -> StageRunResult:
    if not isinstance(raw_result, Mapping):
        raise BaselineExecutionError(f"{stage} process_all() 必须返回映射")
    if not raw_result:
        raise BaselineExecutionError(f"{stage} process_all() 返回了空映射")

    summaries: list[TableRunSummary] = []
    expected_workbooks: set[str] = set()
    for name, frame in raw_result.items():
        if (
            not isinstance(name, str)
            or not name.strip()
            or name in {".", ".."}
            or "/" in name
            or "\\" in name
        ):
            raise BaselineExecutionError(f"{stage} 返回了无效结果键: {name!r}")
        if not isinstance(frame, pd.DataFrame):
            raise BaselineExecutionError(f"{stage}/{name} 结果不是 DataFrame")

        workbook = output_dir / f"{name}.xlsx"
        expected_workbooks.add(workbook.name)
        if workbook.is_symlink() or not workbook.is_file():
            raise BaselineExecutionError(f"{stage}/{name} 缺少输出工作簿: {workbook}")
        try:
            resolved = workbook.resolve(strict=True)
        except OSError as exc:
            raise BaselineExecutionError(f"{stage}/{name} 输出工作簿无法解析") from exc
        if resolved.parent != output_dir:
            raise BaselineExecutionError(f"{stage}/{name} 输出工作簿逃逸阶段目录")
        summaries.append(
            TableRunSummary(
                name=name,
                row_count=len(frame),
                column_count=len(frame.columns),
            )
        )

    actual_workbooks = {
        path.name
        for path in output_dir.iterdir()
        if path.is_file() and not path.is_symlink() and path.suffix.lower() == ".xlsx"
    }
    if actual_workbooks != expected_workbooks:
        raise BaselineExecutionError(
            f"{stage} 工作簿集合与结果键不一致; "
            f"missing={sorted(expected_workbooks - actual_workbooks)}; "
            f"unexpected={sorted(actual_workbooks - expected_workbooks)}"
        )

    return StageRunResult(
        stage=stage,
        output_dir=output_dir,
        tables=tuple(sorted(summaries, key=lambda item: item.name)),
    )
