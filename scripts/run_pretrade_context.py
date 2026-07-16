#!/opt/homebrew/bin/python3
"""用冻结 data_source_0123 构建并验收一份交易前上下文。"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sys
from typing import Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.pipeline.daily_runtime import run_daily_runtime
from src.pipeline.paths import PipelinePaths
from src.pretrade.context_build import (
    assert_replay_matches_runtime,
    build_ready_context,
    replay_kernel_from_snapshot,
    verify_rehydrated_context,
)
from src.pretrade.context_capture import capture_production_kernel_input
from src.pretrade.context_store import PretradeContextStore
from src.pretrade.frame_codec import serialize_frame
from src.pretrade.input_contract import KERNEL_INPUT_DATASETS
from src.testing.current_issuer_resolver import (
    stage_current_issuer_resolver,
    validate_current_issuer_resolver,
)
from src.testing.frozen_config import FrozenInputConfig
from src.testing.frozen_manifest import FrozenInputManifest
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

    inputs = capture_production_kernel_input(
        runtime.stage1_processor, runtime.stage2_processor
    )
    store = PretradeContextStore(ArchiveDB.from_env().engine)
    store.prepare_schema()
    snapshot_id = build_ready_context(runtime, store)
    verify_rehydrated_context(store, snapshot_id, inputs)
    replayed = replay_kernel_from_snapshot(store, snapshot_id)
    assert_replay_matches_runtime(replayed, runtime)

    summary = {
        "snapshot_id": str(snapshot_id),
        "data_date": inputs.business_date.date().isoformat(),
        "note": args.note,
        "datasets": [
            {
                "dataset_code": dataset_code,
                "row_count": len(inputs.frames[dataset_code]),
                "payload_hash": serialize_frame(
                    inputs.frames[dataset_code]
                ).payload_hash,
            }
            for dataset_code in KERNEL_INPUT_DATASETS
        ],
        "replay": {
            "passed": True,
            "stage1_table_count": len(replayed.stage1_tables),
            "stage2_table_count": len(replayed.stage2_tables),
        },
    }
    (output_root / "pretrade_context_summary.json").write_text(
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


if __name__ == "__main__":
    raise SystemExit(main())
