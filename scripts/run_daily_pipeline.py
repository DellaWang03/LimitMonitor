#!/usr/bin/env python3
"""日常生产的唯一编排入口：共同输入快照、既有归档、受守卫发布与展示快照。"""

from __future__ import annotations

import argparse
import csv
from datetime import UTC, datetime
from hashlib import sha256
import os
from pathlib import Path
import subprocess
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

# 这些是 Stage0/1/2 在一次既有日跑中实际读取、并可影响共同内核输入的原始文件。
# 不遍历共享盘目录，避免把无关文件纳入运行时间和审计摘要。
KERNEL_SOURCE_FILE_NAMES = (
    "德勤-主体评级列表.xlsx",
    "风控部债券池.accdb",
    "风控部债券池_主体_虚拟添加.xlsx",
    "标准日期表.xlsx",
    "净资产.xlsx",
    "统计报表底稿1_债券.xlsx",
    "统计报表底稿2_债券SPPI.xlsx",
    "发行人类型调整表.xlsx",
    "金融工具池设置.xlsx",
    "限额配置_当前.xlsx",
)


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


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_manifest(config, *, current_dir: Path = CURRENT_DIR) -> dict[str, object]:
    """记录实际共同内核源文件与当次使用的静态发行人映射摘要。"""

    source_files = []
    for file_name in KERNEL_SOURCE_FILE_NAMES:
        path = Path(config.get_data_file_path(file_name))
        if not path.is_file():
            raise FileNotFoundError(f"共同内核来源文件不存在: {path}")
        source_files.append(
            {
                "name": file_name,
                "sha256": _sha256_file(path),
                "size": path.stat().st_size,
            }
        )

    mapping_path = current_dir / "stage0_output" / "issuer_wind_code_mapping.csv"
    if not mapping_path.is_file():
        raise FileNotFoundError(f"当次发行人静态映射不存在: {mapping_path}")
    with mapping_path.open("r", encoding="utf-8-sig", newline="") as source:
        mapping_rows = sum(1 for _ in csv.DictReader(source))

    return {
        "files": source_files,
        "static_issuer_mapping": {
            "sha256": _sha256_file(mapping_path),
            "row_count": mapping_rows,
        },
        "captured_at": datetime.now(UTC).isoformat(),
    }


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=_PROJECT_ROOT, text=True
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return ""


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
        snapshot_id = build_ready_context(
            runtime,
            store,
            usage="PROD",
            source_manifest=_source_manifest(config, current_dir=CURRENT_DIR),
            code_commit=_git_commit(),
        )

        if archive_to_db(args.archive_date) != 0:
            print("❌ 既有归档返回失败状态；交易前 PROD 指针未发布。")
            return 1
        store.publish(snapshot_id, "PROD")
    except Exception as exc:
        print(f"❌ 日常生产编排失败：{type(exc).__name__}: {exc}")
        return 1

    try:
        write_display_snapshots(CURRENT_DIR / "display_snapshots")
    except Exception as exc:
        print(f"⚠️  展示快照生成失败；归档与交易前 PROD 已成功：{type(exc).__name__}: {exc}")
        return 2

    print("✅ 日常生产编排完成：既有归档与交易前 PROD 已发布。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
