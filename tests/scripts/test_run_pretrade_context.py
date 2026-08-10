from __future__ import annotations

from datetime import datetime
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from scripts import run_pretrade_context as runner
from src.pretrade.config_workbook import (
    LIMIT_CONFIG_WORKBOOK_NAME,
    PretradeConfigWorkbook,
)


def test_cli_accepts_only_the_frozen_acceptance_surface() -> None:
    parser = runner._build_parser()
    destinations = {action.dest for action in parser._actions}

    assert {"input_root", "manifest", "allow_output_root", "output", "note"} <= destinations
    assert destinations.isdisjoint(
        {
            "publish",
            "data_date",
            "archive_date",
            "wind",
            "database_url",
            "reference",
            "usage",
        }
    )


def test_cli_rejects_removed_usage_option() -> None:
    with pytest.raises(SystemExit) as exc_info:
        runner._build_parser().parse_args(
            [
                "--input-root",
                "/tmp/input",
                "--manifest",
                "/tmp/manifest.json",
                "--allow-output-root",
                "/tmp/output",
                "--output",
                "/tmp/output/new",
                "--usage=DEV",
            ]
        )

    assert exc_info.value.code == 2


def test_frozen_summary_records_the_verified_config_workbook(
    monkeypatch, tmp_path
) -> None:
    output_root = tmp_path / "output"
    output_root.mkdir()
    workbook = PretradeConfigWorkbook(
        file_name=LIMIT_CONFIG_WORKBOOK_NAME,
        payload=b"PK\x03\x04frozen-config",
        payload_hash="cf00bea9ae247024fb4cf21a6a0c972aa1619e193de46be3e686e89f0b3f6c41",
    )
    snapshot_id = uuid4()
    store = SimpleNamespace(
        prepare_schema=lambda: None,
        load_config_workbook=lambda value: workbook,
    )
    manifest = SimpleNamespace(
        input_root=tmp_path,
        expected_business_date=datetime(2026, 7, 10),
    )
    inputs = SimpleNamespace(business_date=datetime(2026, 7, 10))
    replayed = SimpleNamespace(stage1_tables={}, stage2_tables={})

    monkeypatch.setattr(
        runner.FrozenInputManifest,
        "load",
        lambda path: SimpleNamespace(validate=lambda input_root: manifest),
    )
    monkeypatch.setattr(runner, "create_unique_test_output", lambda **kwargs: output_root)
    monkeypatch.setattr(runner, "_frozen_issuer_resolver", lambda: object())
    monkeypatch.setattr(runner, "stage_current_issuer_resolver", lambda *args: None)
    monkeypatch.setattr(runner.shutil, "copy2", lambda *args: None)
    monkeypatch.setattr(runner, "stage_legacy_local_limit_config", lambda *args: object())
    monkeypatch.setattr(runner, "cleanup_legacy_local_limit_config", lambda value: None)
    monkeypatch.setattr(runner, "ConfigLoader", lambda **kwargs: object())
    monkeypatch.setattr(runner, "FrozenInputConfig", lambda **kwargs: object())
    monkeypatch.setattr(
        runner,
        "run_daily_runtime",
        lambda **kwargs: SimpleNamespace(
            stage1_processor=object(), stage2_processor=object()
        ),
    )
    monkeypatch.setattr(
        runner, "ArchiveDB", SimpleNamespace(from_env=lambda: SimpleNamespace(engine=object()))
    )
    monkeypatch.setattr(runner, "PretradeContextStore", lambda engine: store)
    monkeypatch.setattr(runner, "capture_production_kernel_input", lambda *args: inputs)
    monkeypatch.setattr(runner, "build_ready_context", lambda *args: snapshot_id)
    monkeypatch.setattr(runner, "verify_rehydrated_context", lambda *args: None)
    monkeypatch.setattr(runner, "replay_kernel_from_snapshot", lambda *args: replayed)
    monkeypatch.setattr(runner, "assert_replay_matches_runtime", lambda *args: None)
    monkeypatch.setattr(runner, "KERNEL_INPUT_DATASETS", ())

    assert (
        runner._run(
            SimpleNamespace(
                input_root=tmp_path,
                manifest=tmp_path / "manifest.json",
                allow_output_root=tmp_path,
                output=output_root,
                note="fixture",
            )
        )
        == 0
    )

    summary = json.loads(
        (output_root / "pretrade_context_summary.json").read_text(encoding="utf-8")
    )
    assert summary["config_workbook"]["file_name"] == LIMIT_CONFIG_WORKBOOK_NAME
    assert len(summary["config_workbook"]["payload_hash"]) == 64
    assert summary["config_workbook"]["byte_count"] > 0
    assert summary["replay"]["passed"] is True
