from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pandas.testing as pdt
import pytest

sqlalchemy = pytest.importorskip("sqlalchemy")
from sqlalchemy import create_engine

from src.pretrade import context_build
from src.pretrade.context_build import (
    build_ready_context,
    replay_kernel_from_snapshot,
)
from src.pretrade.context_capture import FRAME_SOURCE, capture_production_kernel_input
from src.pretrade.context_store import PretradeContextStore
from src.pretrade.input_contract import KERNEL_INPUT_DATASETS


def _runtime() -> SimpleNamespace:
    stage1_cache: dict[str, pd.DataFrame] = {}
    stage2_cache: dict[str, pd.DataFrame] = {}
    for dataset_code, source in FRAME_SOURCE.items():
        frame = pd.DataFrame({"数据集": [dataset_code], "值": [len(dataset_code)]})
        if source in {"stage1", "overlap"}:
            stage1_cache[dataset_code] = frame
        if source in {"stage2", "overlap"}:
            stage2_cache[dataset_code] = frame.copy(deep=True)
    return SimpleNamespace(
        stage1_processor=SimpleNamespace(
            cache=stage1_cache,
            _business_date=pd.Timestamp("2026-07-10"),
            _runtime_regulatory_concentration_limit=0.16,
        ),
        stage2_processor=SimpleNamespace(
            cache=stage2_cache,
            _business_date=pd.Timestamp("2026-07-10"),
        ),
    )


def test_build_writes_then_verifies_database_round_trip(source_manifest, monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    store = PretradeContextStore(engine)
    store.prepare_schema()
    runtime = _runtime()

    class KernelMustNotRun:
        def __init__(self):
            raise AssertionError("正常构建路径不得重跑共同内核")

    monkeypatch.setattr(context_build, "ProductionRiskKernel", KernelMustNotRun)
    snapshot_id = build_ready_context(
        runtime,
        store,
        usage="DEV",
        source_manifest=source_manifest,
        code_commit="test-commit",
    )

    expected = capture_production_kernel_input(
        runtime.stage1_processor, runtime.stage2_processor
    )
    restored = store.load_kernel_input(snapshot_id)
    assert tuple(restored.frames) == KERNEL_INPUT_DATASETS
    assert restored.business_date == expected.business_date
    assert restored.parameters == expected.parameters
    for dataset_code in KERNEL_INPUT_DATASETS:
        assert restored.frames[dataset_code].equals(expected.frames[dataset_code])
    assert store.get_current_snapshot("DEV") is None
    engine.dispose()


def test_replay_kernel_is_explicit_and_uses_only_rehydrated_input(monkeypatch) -> None:
    sentinel_inputs = object()
    sentinel_stage1 = {"stage1": pd.DataFrame({"value": [1]})}
    sentinel_stage2 = {"stage2": pd.DataFrame({"value": [2]})}
    calls: list[object] = []

    class FakeStore:
        def load_kernel_input(self, snapshot_id):
            calls.append(("load", snapshot_id))
            return sentinel_inputs

    class FakeKernel:
        def run_stage1(self, inputs):
            calls.append(("stage1", inputs))
            return sentinel_stage1

        def run_stage2(self, inputs, stage1_tables):
            calls.append(("stage2", inputs, stage1_tables))
            return sentinel_stage2

    monkeypatch.setattr(context_build, "ProductionRiskKernel", FakeKernel)
    result = replay_kernel_from_snapshot(FakeStore(), "snapshot")

    pdt.assert_frame_equal(result.stage1_tables["stage1"], sentinel_stage1["stage1"])
    pdt.assert_frame_equal(result.stage2_tables["stage2"], sentinel_stage2["stage2"])
    assert calls == [
        ("load", "snapshot"),
        ("stage1", sentinel_inputs),
        ("stage2", sentinel_inputs, sentinel_stage1),
    ]
