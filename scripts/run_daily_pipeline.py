#!/usr/bin/env python3
"""日常生产入口：共同内核输入、既有归档、current 与展示快照。"""

from __future__ import annotations

import argparse
from datetime import datetime
import os
from pathlib import Path
import sys
from typing import Sequence

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from run_stage0 import validate_current_inputs
from scripts.daily_archive import archive_to_db
from scripts.generate_display_snapshot import write_display_snapshots
from src.pipeline.daily_runtime import run_daily_runtime
from src.pretrade.context_build import build_ready_context
from src.pretrade.context_store import PretradeContextStore
from src.utils.archive_db import ArchiveDB
from src.utils.config_loader import get_config


CURRENT_DIR = _PROJECT_ROOT / "data" / "current"

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--archive-date",
        default=datetime.now().strftime("%Y-%m-%d"),
        help="既有归档时间标签（YYYY-MM-DD），默认今天。",
    )
    parser.add_argument(
        "--target-date",
        default=None,
        help="补跑时传给 Stage0 的业务目标日期（YYYY-MM-DD）。",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        datetime.strptime(args.archive_date, "%Y-%m-%d")
    except ValueError:
        print(f"❌ archive_date 必须为 YYYY-MM-DD，收到: {args.archive_date!r}")
        return 1

    try:
        config = get_config()
        data_dir = config.get_data_dir()
        environment = os.getenv("LIMIT_MONITOR_ENV", "production").lower()
        validate_current_inputs(config, args.target_date, environment)

        runtime = run_daily_runtime(
            config=config,
            data_dir=data_dir,
            current_dir=CURRENT_DIR,
            target_date=args.target_date,
        )
        store = PretradeContextStore(ArchiveDB.from_env().engine)
        store.prepare_schema()
        snapshot_id = build_ready_context(runtime, store)

        # 旧入口/调用者仍可不传回执；科创分支只绑定本次事务实际发布的版本。
        scitech_config_error = None
        try:
            getter = getattr(config, 'get', None)
            scitech_enabled = getter('scitech.enabled', False) if getter else False
            if not isinstance(scitech_enabled, bool):
                raise ValueError('scitech.enabled 必须为 YAML 布尔值 true/false')
        except Exception as exc:
            scitech_enabled = False
            scitech_config_error = f'{type(exc).__name__}: {exc}'
        receipt = {} if scitech_enabled else None
        archive_status = (archive_to_db(args.archive_date, receipt=receipt) if scitech_enabled
                          else archive_to_db(args.archive_date))
        if archive_status != 0:
            print("❌ 既有归档返回失败状态；交易前 current 指针未发布。")
            return 1
        store.publish_current(snapshot_id)
    except Exception as exc:
        print(f"❌ 日常生产编排失败：{type(exc).__name__}: {exc}")
        return 1

    display_failed = False
    try:
        write_display_snapshots(CURRENT_DIR / "display_snapshots")
    except Exception as exc:
        print(f"⚠️  展示快照生成失败；归档与交易前 current 已成功：{type(exc).__name__}: {exc}")
        display_failed = True

    scitech_failed = scitech_config_error is not None
    if scitech_config_error:
        print(f'⚠️ 科创配置无效，本次未执行科创分支：{scitech_config_error}')
    if scitech_enabled:
        try:
            from src.scitech.service import run_extension
            outcome = run_extension(runtime, config, receipt, ArchiveDB.from_env().engine)
            scitech_failed = outcome['status'] != 'READY'
            print(f"科创监控：{outcome}")
        except Exception as exc:
            scitech_failed = True
            print(f"⚠️ 科创监控失败，既有结果保持已发布：{type(exc).__name__}: {exc}")
    if display_failed:
        return 2
    if scitech_failed:
        print("⚠️ 既有归档与交易前 current 已成功，科创模块未完整完成。")
        return 3

    print("✅ 日常生产编排完成：既有归档与交易前 current 已发布。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
