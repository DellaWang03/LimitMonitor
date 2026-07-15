"""交易前上下文的捕获、读回校验与验收重放编排。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

import pandas.testing as pdt

from src.risk_core import (
    ProductionKernelInput,
    ProductionKernelResult,
    ProductionRiskKernel,
)

from .context_capture import capture_production_kernel_input
from .context_store import PretradeContextStore
from .input_contract import PretradeSnapshotRequest


STAGE2_EXCEL_ROUND_TRIP_TABLES = frozenset(
    {
        "债券持仓明细表_信用债",
        "债券持仓明细表_信用债_合并风险限额相关",
    }
)
STAGE2_EXCEL_ROUND_TRIP_ABSOLUTE_TOLERANCE = 1e-12


class PretradeContextBuildError(RuntimeError):
    """捕获输入和数据库读回的内容不完全一致。"""


def assert_kernel_input_equal(
    actual: ProductionKernelInput, expected: ProductionKernelInput
) -> None:
    """以共同内核输入的严格等值作为持久化完成门槛。"""

    if actual.business_date != expected.business_date:
        raise PretradeContextBuildError("数据库读回的业务日期不一致")
    if actual.parameters != expected.parameters:
        raise PretradeContextBuildError("数据库读回的共同内核参数不一致")
    if tuple(actual.frames) != tuple(expected.frames):
        raise PretradeContextBuildError("数据库读回的共同内核输入集合不一致")
    for dataset_code in expected.frames:
        try:
            pdt.assert_frame_equal(
                actual.frames[dataset_code],
                expected.frames[dataset_code],
                check_dtype=True,
                check_exact=True,
                check_names=True,
            )
        except AssertionError as exc:
            raise PretradeContextBuildError(
                f"数据库读回的共同内核输入不一致: {dataset_code}"
            ) from exc


def verify_rehydrated_context(
    store: PretradeContextStore,
    snapshot_id: UUID | str,
    expected: ProductionKernelInput,
) -> ProductionKernelInput:
    """读回数据库快照并逐表核验；不执行任何限额计算。"""

    restored = store.load_kernel_input(snapshot_id)
    assert_kernel_input_equal(restored, expected)
    return restored


def build_ready_context(
    runtime: Any,
    store: PretradeContextStore,
    *,
    usage: str,
    source_manifest: Mapping[str, object],
    code_commit: str = "",
    engine_version: str = "risk-core-v1",
    input_contract_version: str = "pretrade-input-v1",
) -> UUID:
    """捕获一次实际运行输入，存储并立即验证其数据库往返。"""

    stage1 = getattr(runtime, "stage1_processor", None)
    stage2 = getattr(runtime, "stage2_processor", None)
    if stage1 is None or stage2 is None:
        raise PretradeContextBuildError("日常运行结果缺少 Stage1 或 Stage2 处理器")
    kernel_input = capture_production_kernel_input(stage1, stage2)
    request = PretradeSnapshotRequest.from_kernel_input(
        kernel_input,
        usage=usage,
        source_manifest=source_manifest,
        code_commit=code_commit,
        engine_version=engine_version,
        input_contract_version=input_contract_version,
    )
    snapshot_id = store.write_ready_snapshot(request)
    verify_rehydrated_context(store, snapshot_id, kernel_input)
    return snapshot_id


def replay_kernel_from_snapshot(
    store: PretradeContextStore, snapshot_id: UUID | str
) -> ProductionKernelResult:
    """仅供验收：从数据库重建输入后，显式重跑纯共同内核。"""

    inputs = store.load_kernel_input(snapshot_id)
    kernel = ProductionRiskKernel()
    stage1 = kernel.run_stage1(inputs)
    stage2 = kernel.run_stage2(inputs, stage1)
    return ProductionKernelResult(stage1, stage2)


def assert_replay_matches_runtime(
    replayed: ProductionKernelResult,
    runtime: Any,
) -> None:
    """验证数据库重放与同次生产运行一致。

    Stage2 历史适配器会从 Stage1 的 Excel 输出重新读取两张上下文表。共同内核
    则保留 Stage1 内存中的原始浮点值；这两张非限额结果表只允许 1e-12 的绝对
    序列化尾差，且重放值必须与 Stage1 输出严格一致。其余全部表严格一致。
    """

    stage1_runtime = getattr(runtime, "stage1_results", None)
    stage2_runtime = getattr(runtime, "stage2_results", None)
    if not isinstance(stage1_runtime, Mapping) or not isinstance(stage2_runtime, Mapping):
        raise PretradeContextBuildError("日常运行结果缺少 Stage1 或 Stage2 表")

    _assert_stage_tables_exact(
        "Stage1", replayed.stage1_tables, stage1_runtime
    )
    _assert_stage2_tables_match_runtime(
        replayed.stage2_tables,
        stage1_runtime,
        stage2_runtime,
    )


def _assert_stage_tables_exact(name: str, actual: Mapping[str, Any], expected: Mapping[str, Any]) -> None:
    if tuple(sorted(actual)) != tuple(sorted(expected)):
        raise PretradeContextBuildError(f"{name} 数据库重放表集合与实际运行不一致")
    for table_name in sorted(expected):
        try:
            pdt.assert_frame_equal(
                actual[table_name],
                expected[table_name],
                check_dtype=True,
                check_exact=True,
                check_names=True,
            )
        except AssertionError as exc:
            raise PretradeContextBuildError(
                f"{name} 数据库重放不一致: {table_name}"
            ) from exc


def _assert_stage2_tables_match_runtime(
    actual: Mapping[str, Any],
    stage1_runtime: Mapping[str, Any],
    stage2_runtime: Mapping[str, Any],
) -> None:
    if tuple(sorted(actual)) != tuple(sorted(stage2_runtime)):
        raise PretradeContextBuildError("Stage2 数据库重放表集合与实际运行不一致")
    for table_name in sorted(stage2_runtime):
        if table_name not in STAGE2_EXCEL_ROUND_TRIP_TABLES:
            try:
                pdt.assert_frame_equal(
                    actual[table_name],
                    stage2_runtime[table_name],
                    check_dtype=True,
                    check_exact=True,
                    check_names=True,
                )
            except AssertionError as exc:
                raise PretradeContextBuildError(
                    f"Stage2 数据库重放不一致: {table_name}"
                ) from exc
            continue

        if table_name not in stage1_runtime:
            raise PretradeContextBuildError(
                f"Stage1 缺少 Stage2 Excel 往返上下文表: {table_name}"
            )
        try:
            pdt.assert_frame_equal(
                actual[table_name],
                stage1_runtime[table_name],
                check_dtype=True,
                check_exact=True,
                check_names=True,
            )
        except AssertionError as exc:
            raise PretradeContextBuildError(
                f"Stage2 共同内核上下文不一致: {table_name}"
            ) from exc
        try:
            pdt.assert_frame_equal(
                actual[table_name],
                stage2_runtime[table_name],
                check_dtype=True,
                check_exact=False,
                rtol=0.0,
                atol=STAGE2_EXCEL_ROUND_TRIP_ABSOLUTE_TOLERANCE,
                check_names=True,
            )
        except AssertionError as exc:
            raise PretradeContextBuildError(
                f"Stage2 Excel 往返边界超出 1e-12: {table_name}"
            ) from exc
