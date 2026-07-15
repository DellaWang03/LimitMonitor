from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.pipeline import daily_runtime


def _install_runtime_fakes(monkeypatch, calls: list[tuple[str, object]], *, fail_at=None):
    class FakeStage0:
        def __init__(self, data_dir, output_dir, config, target_date):
            calls.append(("stage0_init", (data_dir, output_dir, config, target_date)))

        def process_all(self):
            calls.append(("stage0_run", None))
            if fail_at == "stage0":
                raise RuntimeError("stage0 failed")
            return {"s0": pd.DataFrame({"value": [0]})}

    class FakeStage1:
        def __init__(self, data_dir, output_dir, stage0_output_dir, config):
            calls.append(("stage1_init", (data_dir, output_dir, stage0_output_dir, config)))

        def process_all(self):
            calls.append(("stage1_run", None))
            if fail_at == "stage1":
                raise RuntimeError("stage1 failed")
            return {"s1": pd.DataFrame({"value": [1]})}

    class FakeStage2:
        def __init__(self, data_dir, output_dir, stage0_output_dir, stage1_output_dir, config):
            calls.append(
                (
                    "stage2_init",
                    (data_dir, output_dir, stage0_output_dir, stage1_output_dir, config),
                )
            )

        def process_all(self):
            calls.append(("stage2_run", None))
            if fail_at == "stage2":
                raise RuntimeError("stage2 failed")
            return {"s2": pd.DataFrame({"value": [2]})}

    monkeypatch.setattr(daily_runtime, "Stage0Processor", FakeStage0)
    monkeypatch.setattr(daily_runtime, "Stage1Processor", FakeStage1)
    monkeypatch.setattr(daily_runtime, "Stage2Processor", FakeStage2)


def test_run_daily_runtime_uses_existing_processors_in_exact_order(
    monkeypatch, tmp_path: Path
) -> None:
    calls: list[tuple[str, object]] = []
    _install_runtime_fakes(monkeypatch, calls)
    data_dir = tmp_path / "input"
    current_dir = tmp_path / "current"
    config = object()

    result = daily_runtime.run_daily_runtime(
        config=config,
        data_dir=data_dir,
        current_dir=current_dir,
        target_date="2026-07-10",
    )

    assert [name for name, _ in calls] == [
        "stage0_init",
        "stage0_run",
        "stage1_init",
        "stage1_run",
        "stage2_init",
        "stage2_run",
    ]
    assert calls[0][1] == (
        data_dir,
        current_dir / "stage0_output",
        config,
        "2026-07-10",
    )
    assert calls[2][1] == (
        data_dir,
        current_dir / "stage1_output",
        current_dir / "stage0_output",
        config,
    )
    assert calls[4][1] == (
        data_dir,
        current_dir / "stage2_output",
        current_dir / "stage0_output",
        current_dir / "stage1_output",
        config,
    )
    assert list(result.stage0_results) == ["s0"]
    assert list(result.stage1_results) == ["s1"]
    assert list(result.stage2_results) == ["s2"]


def test_daily_runtime_stops_before_downstream_processor_on_failure(monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple[str, object]] = []
    _install_runtime_fakes(monkeypatch, calls, fail_at="stage1")

    with pytest.raises(RuntimeError, match="stage1 failed"):
        daily_runtime.run_daily_runtime(
            config=object(), data_dir=tmp_path / "input", current_dir=tmp_path / "current"
        )

    assert [name for name, _ in calls] == [
        "stage0_init",
        "stage0_run",
        "stage1_init",
        "stage1_run",
    ]
