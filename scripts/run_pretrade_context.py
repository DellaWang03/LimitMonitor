#!/opt/homebrew/bin/python3
"""用冻结 data_source_0123 构建并验收一份交易前 DEV 上下文。"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Sequence

import pandas.testing as pdt


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.pipeline.daily_runtime import run_daily_runtime
from src.pipeline.paths import PipelinePaths
from src.pretrade.context_build import build_ready_context, replay_kernel_from_snapshot
from src.pretrade.context_capture import capture_production_kernel_input
from src.pretrade.context_store import PretradeContextStore
from src.pretrade.frame_codec import serialize_frame
from src.pretrade.input_contract import KERNEL_INPUT_DATASETS, PretradeSnapshotRequest
from src.testing.current_issuer_resolver import (
    stage_current_issuer_resolver,
    validate_current_issuer_resolver,
)
from src.testing.frozen_config import FrozenInputConfig
from src.testing.frozen_manifest import FrozenInputManifest, ValidatedInputManifest
from src.testing.legacy_local_compat import (
    cleanup_legacy_local_limit_config,
    stage_legacy_local_limit_config,
)
from src.testing.safe_paths import create_unique_test_output
from src.utils.archive_db import ArchiveDB
from src.utils.config_loader import ConfigLoader


DEFAULT_FROZEN_REFERENCE_ROOT = (
    Path.home()
    / "Desktop"
    / "LimitMonitorAutomation-test-output"
    / "pretrade-baseline-20260710-main1"
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--allow-output-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--usage", choices=("DEV",), default="DEV")
    parser.add_argument("--note", default="")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        return _run(args)
    except Exception as exc:
        print(f"pretrade-context error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


def _run(args: argparse.Namespace) -> int:
    manifest = FrozenInputManifest.load(args.manifest).validate(args.input_root)
    output_root = create_unique_test_output(
        allow_root=args.allow_output_root,
        requested=args.output,
        project_root=PROJECT_ROOT,
        input_root=manifest.input_root,
    )
    pipeline_root = output_root / "pipeline"
    pipeline_root.mkdir(mode=0o700)
    pipeline_paths = PipelinePaths.create(pipeline_root)
    current_dir = output_root / "current"
    current_dir.mkdir(mode=0o700)

    resolver = _frozen_issuer_resolver()
    stage_current_issuer_resolver(resolver, pipeline_paths)
    runtime_stage0_dir = current_dir / "stage0_output"
    runtime_stage0_dir.mkdir(mode=0o700)
    shutil.copy2(
        pipeline_paths.stage0 / "issuer_wind_code_mapping.csv",
        runtime_stage0_dir / "issuer_wind_code_mapping.csv",
    )

    compatibility = stage_legacy_local_limit_config(manifest, PROJECT_ROOT)
    previous_cwd = Path.cwd()
    try:
        config = FrozenInputConfig(
            base=ConfigLoader(config_dir=str(PROJECT_ROOT / "config")),
            manifest=manifest,
            pipeline_root=pipeline_paths.root,
            access_export_dir=pipeline_paths.access_export,
        )
        os.chdir(pipeline_paths.tmp)
        runtime = run_daily_runtime(
            config=config,
            data_dir=manifest.input_root,
            current_dir=current_dir,
            target_date=manifest.expected_business_date.isoformat(),
        )
    finally:
        os.chdir(previous_cwd)
        cleanup_legacy_local_limit_config(compatibility)

    source_manifest = _source_manifest(manifest, resolver)
    store = PretradeContextStore(ArchiveDB.from_env().engine)
    store.prepare_schema()
    snapshot_id = build_ready_context(
        runtime,
        store,
        usage="DEV",
        source_manifest=source_manifest,
        code_commit=_git_commit(),
    )
    replayed = replay_kernel_from_snapshot(store, snapshot_id)
    _assert_replay_matches_runtime(replayed, runtime)

    inputs = capture_production_kernel_input(
        runtime.stage1_processor, runtime.stage2_processor
    )
    request = PretradeSnapshotRequest.from_kernel_input(
        inputs,
        usage="DEV",
        source_manifest=source_manifest,
        code_commit=_git_commit(),
    )
    summary = {
        "snapshot_id": str(snapshot_id),
        "usage": "DEV",
        "data_date": inputs.business_date.date().isoformat(),
        "input_hash": request.input_hash,
        "note": args.note,
        "datasets": [
            {
                "dataset_code": dataset_code,
                "row_count": len(inputs.frames[dataset_code]),
                "content_hash": serialize_frame(
                    inputs.frames[dataset_code]
                ).content_hash,
            }
            for dataset_code in KERNEL_INPUT_DATASETS
        ],
        "replay": {
            "passed": True,
            "stage1_table_count": len(replayed.stage1_tables),
            "stage2_table_count": len(replayed.stage2_tables),
        },
    }
    (output_root / "pretrade_context_dev_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


def _frozen_issuer_resolver():
    reference = DEFAULT_FROZEN_REFERENCE_ROOT
    if reference.is_symlink() or not reference.is_dir():
        raise RuntimeError(f"冻结主体映射参考输出不可用: {reference}")
    return validate_current_issuer_resolver(
        reference / "stage0" / "issuer_wind_code_mapping.csv",
        reference / "stage0" / "风控部债券池_主体.xlsx",
    )


def _source_manifest(manifest: ValidatedInputManifest, resolver) -> dict[str, object]:
    captured_at = datetime.now(UTC).isoformat()
    return {
        "files": [
            {"name": item.name, "sha256": item.sha256, "size": item.size}
            for item in manifest.files
        ],
        "static_issuer_mapping": {
            "sha256": resolver.mapping_sha256,
            "row_count": resolver.mapping_row_count,
            "validated_at": captured_at,
        },
        "captured_at": captured_at,
    }


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, text=True
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _assert_replay_matches_runtime(replayed, runtime) -> None:
    _assert_stage_tables_equal("Stage1", replayed.stage1_tables, runtime.stage1_results)
    _assert_stage_tables_equal("Stage2", replayed.stage2_tables, runtime.stage2_results)


def _assert_stage_tables_equal(name: str, actual, expected) -> None:
    if tuple(sorted(actual)) != tuple(sorted(expected)):
        raise RuntimeError(f"{name} 数据库重放表集合与实际运行不一致")
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
            raise RuntimeError(f"{name} 数据库重放不一致: {table_name}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
