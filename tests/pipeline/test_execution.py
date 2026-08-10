from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from src.pipeline import execution
from src.pipeline.execution import (
    BaselineExecutionError,
    BaselineRunRequest,
    run_frozen_pipeline,
)
from src.pipeline.paths import PipelinePaths
from src.testing.frozen_config import FrozenInputConfig
from src.testing.frozen_manifest import ValidatedInputManifest


class FakeBaseConfig:
    def get(self, key: str, default=None):
        return default

    def get_limit(self, key: str, default=None):
        return default

    def load_settings(self):
        return {}

    def load_limits(self):
        return {}


@pytest.fixture
def baseline_request(tmp_path: Path) -> BaselineRunRequest:
    source = tmp_path / "source"
    root = tmp_path / "run"
    source.mkdir()
    root.mkdir(mode=0o700)
    manifest = ValidatedInputManifest(
        manifest_id="fixture-v1",
        expected_business_date=date(2026, 7, 10),
        input_root=source.resolve(),
        files=(),
    )
    paths = PipelinePaths.create(root)
    config = FrozenInputConfig(
        base=FakeBaseConfig(),
        manifest=manifest,
        pipeline_root=paths.root,
        access_export_dir=paths.access_export,
    )
    return BaselineRunRequest(
        manifest=manifest,
        config=config,
        paths=paths,
        business_date=date(2026, 7, 10),
    )


def _write_fake_result(output: Path, name: str) -> dict[str, pd.DataFrame]:
    frame = pd.DataFrame()
    frame.to_excel(output / f"{name}.xlsx", index=False)
    return {name: frame}


def _install_successful_fakes(
    monkeypatch: pytest.MonkeyPatch,
    baseline_request: BaselineRunRequest,
    calls: list[tuple[str, object]] | None = None,
) -> None:
    calls = calls if calls is not None else []

    class FakeStage0:
        def __init__(self, data_dir, output_dir, config, target_date):
            calls.append(("stage0_init", (data_dir, output_dir, config, target_date)))

        def process_all(self):
            calls.append(("stage0_run", None))
            return _write_fake_result(baseline_request.paths.stage0, "s0")

    class FakeStage1:
        def __init__(self, data_dir, output_dir, stage0_output_dir, config):
            calls.append(("stage1_init", (data_dir, output_dir, stage0_output_dir, config)))

        def process_all(self):
            calls.append(("stage1_run", None))
            return _write_fake_result(baseline_request.paths.stage1, "s1")

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
            return _write_fake_result(baseline_request.paths.stage2, "s2")

    monkeypatch.setattr(execution, "Stage0Processor", FakeStage0)
    monkeypatch.setattr(execution, "Stage1Processor", FakeStage1)
    monkeypatch.setattr(execution, "Stage2Processor", FakeStage2)


def test_run_uses_production_processor_interfaces_in_exact_order(
    monkeypatch: pytest.MonkeyPatch,
    baseline_request: BaselineRunRequest,
) -> None:
    calls: list[tuple[str, object]] = []
    _install_successful_fakes(monkeypatch, baseline_request, calls)

    result = run_frozen_pipeline(baseline_request)

    assert [name for name, _ in calls] == [
        "stage0_init",
        "stage0_run",
        "stage1_init",
        "stage1_run",
        "stage2_init",
        "stage2_run",
    ]
    stage0_args = calls[0][1]
    assert stage0_args == (
        baseline_request.manifest.input_root,
        baseline_request.paths.stage0,
        baseline_request.config,
        "2026-07-10",
    )
    assert result.business_date == date(2026, 7, 10)
    assert [stage.stage for stage in result.stages] == ["stage0", "stage1", "stage2"]
    assert [stage.table_names for stage in result.stages] == [("s0",), ("s1",), ("s2",)]


def test_legal_empty_dataframe_passes_when_workbook_exists(
    monkeypatch: pytest.MonkeyPatch,
    baseline_request: BaselineRunRequest,
) -> None:
    _install_successful_fakes(monkeypatch, baseline_request)

    result = run_frozen_pipeline(baseline_request)

    assert all(stage.tables[0].row_count == 0 for stage in result.stages)


def test_missing_workbook_rejects_stage0_swallowed_failure(
    monkeypatch: pytest.MonkeyPatch,
    baseline_request: BaselineRunRequest,
) -> None:
    _install_successful_fakes(monkeypatch, baseline_request)
    monkeypatch.setattr(
        execution.Stage0Processor,
        "process_all",
        lambda self: {"风控部债券池": pd.DataFrame()},
    )

    with pytest.raises(BaselineExecutionError, match="stage0.*缺少输出工作簿"):
        run_frozen_pipeline(baseline_request)


@pytest.mark.parametrize(
    "bad_result",
    [
        None,
        [],
        {},
        {"": pd.DataFrame()},
        {"nested/name": pd.DataFrame()},
        {"name": object()},
    ],
)
def test_rejects_invalid_stage_result_contract(
    monkeypatch: pytest.MonkeyPatch,
    baseline_request: BaselineRunRequest,
    bad_result,
) -> None:
    _install_successful_fakes(monkeypatch, baseline_request)
    monkeypatch.setattr(execution.Stage0Processor, "process_all", lambda self: bad_result)

    with pytest.raises(BaselineExecutionError, match="stage0"):
        run_frozen_pipeline(baseline_request)


def test_stops_before_stage1_when_stage0_fails(
    monkeypatch: pytest.MonkeyPatch,
    baseline_request: BaselineRunRequest,
) -> None:
    calls: list[tuple[str, object]] = []
    _install_successful_fakes(monkeypatch, baseline_request, calls)

    def fail(self):
        raise ValueError("boom")

    monkeypatch.setattr(execution.Stage0Processor, "process_all", fail)

    with pytest.raises(BaselineExecutionError, match="stage0.*boom"):
        run_frozen_pipeline(baseline_request)
    assert [name for name, _ in calls] == ["stage0_init"]


def test_rejects_unexpected_stage_workbook(
    monkeypatch: pytest.MonkeyPatch,
    baseline_request: BaselineRunRequest,
) -> None:
    _install_successful_fakes(monkeypatch, baseline_request)

    def stage0_with_extra():
        result = _write_fake_result(baseline_request.paths.stage0, "expected")
        pd.DataFrame().to_excel(baseline_request.paths.stage0 / "unexpected.xlsx", index=False)
        return result

    monkeypatch.setattr(execution.Stage0Processor, "process_all", lambda self: stage0_with_extra())

    with pytest.raises(BaselineExecutionError, match="工作簿集合"):
        run_frozen_pipeline(baseline_request)


def test_request_rejects_date_or_manifest_mismatch(baseline_request: BaselineRunRequest) -> None:
    with pytest.raises(BaselineExecutionError, match="业务日期"):
        BaselineRunRequest(
            manifest=baseline_request.manifest,
            config=baseline_request.config,
            paths=baseline_request.paths,
            business_date=date(2026, 7, 9),
        )

    other = ValidatedInputManifest(
        manifest_id="other",
        expected_business_date=date(2026, 7, 10),
        input_root=baseline_request.manifest.input_root,
        files=(),
    )
    with pytest.raises(BaselineExecutionError, match="同一清单"):
        BaselineRunRequest(
            manifest=other,
            config=baseline_request.config,
            paths=baseline_request.paths,
            business_date=date(2026, 7, 10),
        )
