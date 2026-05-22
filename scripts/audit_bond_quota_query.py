"""
单券可购额度查询页独立审计脚本。

默认行为：
1. 通过 DataLoader 读取指定归档日（未指定则取 current）数据；
2. 以 page8 五张来源表并集作为查询全集；
3. 逐只调用 query_bond_remaining_quota，输出覆盖率与结果层级统计。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.visualization.bond_quota_query import DATAFRAME_SOURCES, query_bond_remaining_quota
from src.visualization.code_utils import clean_code_like_value
from src.visualization.data_loader import DataLoader


def _normalize_date(value: Any) -> pd.Timestamp:
    return pd.Timestamp(value).normalize()


def _load_source_frames(loader: DataLoader) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    for source_key, source_label, method_name in DATAFRAME_SOURCES:
        load_method = getattr(loader, method_name, None)
        if load_method is None:
            raise AttributeError(f"{source_label} 缺少加载方法 {method_name}()")
        df = load_method()
        if not isinstance(df, pd.DataFrame):
            raise TypeError(f"{source_label} 加载结果不是 DataFrame")
        frames[source_key] = df.copy()
    return frames


def _get_latest_date(frames: dict[str, pd.DataFrame]) -> pd.Timestamp | None:
    latest_dates: list[pd.Timestamp] = []
    for df in frames.values():
        if df.empty or "日期" not in df.columns:
            continue
        latest_dates.append(_normalize_date(df["日期"].max()))
    if not latest_dates:
        return None
    return max(latest_dates)


def _collect_audit_codes(
    frames: dict[str, pd.DataFrame],
    latest_date: pd.Timestamp,
) -> tuple[list[str], dict[str, int]]:
    all_codes: list[str] = []
    source_counts: dict[str, int] = {}

    for source_key, source_label, _ in DATAFRAME_SOURCES:
        df = frames.get(source_key, pd.DataFrame())
        if df.empty:
            source_counts[source_label] = 0
            continue
        if "日期" not in df.columns or "资产代码" not in df.columns:
            source_counts[source_label] = 0
            continue

        latest_df = df[df["日期"].apply(_normalize_date) == latest_date].copy()
        latest_df["__code__"] = latest_df["资产代码"].apply(clean_code_like_value)
        latest_codes = [code for code in latest_df["__code__"].dropna().unique().tolist() if code]

        source_counts[source_label] = len(latest_codes)
        all_codes.extend(latest_codes)

    codes = sorted(dict.fromkeys(all_codes))
    return codes, source_counts


def main() -> int:
    parser = argparse.ArgumentParser(description="审计单券可购额度查询页的全量覆盖与返回口径。")
    parser.add_argument(
        "--archive-date",
        help="归档日期，格式 YYYY-MM-DD；省略时读取 current 快照。",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="仅抽查前 N 只债券；默认 0 表示全量。",
    )
    args = parser.parse_args()

    target_date = pd.Timestamp(args.archive_date).date() if args.archive_date else None
    loader = DataLoader(target_date=target_date) if target_date else DataLoader()
    source_frames = _load_source_frames(loader)
    if all(df.empty for df in source_frames.values()):
        print("page8 五张来源表均为空，无法执行审计。")
        return 1

    latest_date = _get_latest_date(source_frames)
    if latest_date is None:
        print("五张来源表均缺少可识别的日期字段，无法执行审计。")
        return 1

    codes, source_counts = _collect_audit_codes(source_frames, latest_date)
    if args.limit > 0:
        codes = codes[: args.limit]

    errors = []
    no_dim = []
    bond_scope = 0
    account_scope = 0
    for code in codes:
        result = query_bond_remaining_quota(loader, code, target_date=latest_date)
        if result.get("error"):
            errors.append({"code": code, "error": result["error"]})
            continue

        if result.get("result_scope") == "bond":
            bond_scope += 1
        else:
            account_scope += 1

        applicable_dims = [
            item for item in result.get("dimensions", [])
            if item.get("是否超限") != "不适用"
        ]
        if not applicable_dims:
            no_dim.append({"code": code, "scope": result.get("result_scope")})

    print("=" * 72)
    print("单券可购额度查询页审计结果")
    print("=" * 72)
    print(f"审计日期: {latest_date.strftime('%Y-%m-%d')}")
    print(f"审计债券数: {len(codes)}")
    print("来源表覆盖数:")
    for source_label, count in source_counts.items():
        print(f"- {source_label}: {count}")
    print(f"账户级结果数: {account_scope}")
    print(f"债券级结果数: {bond_scope}")
    print(f"报错数: {len(errors)}")
    print(f"无适用维度数: {len(no_dim)}")

    if errors:
        print("\n[示例报错]")
        for item in errors[:10]:
            print(f"- {item['code']}: {item['error']}")

    if no_dim:
        print("\n[示例无适用维度]")
        for item in no_dim[:10]:
            print(f"- {item['code']} ({item['scope']})")

    print("=" * 72)
    return 0 if not errors and not no_dim else 2


if __name__ == "__main__":
    sys.exit(main())
