"""
校验 DB current / history 两种读取模式的看板口径一致。

目标：
1. 确认 ``DataLoader(target_date=None)`` 读取到的 current 快照就是本次测试归档；
2. 确认 current 模式与显式 ``archive_date`` 历史模式返回相同的原始表、
   看板筛选/摘要元数据以及页面 builder 结果；
3. 额外生成两套展示快照 CSV 做逐表严格对比，确保“最终校验数据”和
   “看板实际读取数据”是同一份 DB 结果。
"""

from __future__ import annotations

import argparse
import math
import shutil
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


NUM_TOLERANCE = 0.01
MAX_SAMPLES = 3


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except Exception:
        return False


def _format_scalar(value: Any) -> str:
    if _is_missing(value):
        return "NaN"
    if isinstance(value, (pd.Timestamp, datetime)):
        return pd.Timestamp(value).strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float):
        return f"{value:,.4f}"
    return str(value)


def _normalize_scalar(value: Any) -> Any:
    if _is_missing(value):
        return None
    if isinstance(value, (pd.Timestamp, datetime)):
        return pd.Timestamp(value).to_pydatetime()
    if isinstance(value, date):
        return value.isoformat()
    return value


def _sort_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.reset_index(drop=True)

    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[col]):
            out[col] = out[col].dt.strftime("%Y-%m-%d %H:%M:%S")
        elif col == "日期":
            maybe_dt = pd.to_datetime(out[col], errors="coerce")
            if maybe_dt.notna().any():
                out[col] = maybe_dt.dt.strftime("%Y-%m-%d %H:%M:%S")

    sort_cols = []
    for col in out.columns:
        sort_col = f"__sort_{col}"
        out[sort_col] = out[col].fillna("").astype(str)
        sort_cols.append(sort_col)

    out = out.sort_values(sort_cols, kind="mergesort").reset_index(drop=True)
    return out[df.columns]


def _compare_dataframes(label: str, current_df: pd.DataFrame, history_df: pd.DataFrame, failures: list[str]) -> None:
    current = _sort_dataframe(current_df)
    history = _sort_dataframe(history_df)

    if list(current.columns) != list(history.columns):
        failures.append(
            f"{label}: 列不一致 current={list(current.columns)} history={list(history.columns)}"
        )
        return

    if len(current) != len(history):
        failures.append(f"{label}: 行数不一致 current={len(current)} history={len(history)}")

    compare_len = min(len(current), len(history))
    current = current.iloc[:compare_len].reset_index(drop=True)
    history = history.iloc[:compare_len].reset_index(drop=True)

    for col in current.columns:
        c_num = pd.to_numeric(current[col], errors="coerce")
        h_num = pd.to_numeric(history[col], errors="coerce")
        numeric_like = c_num.notna().any() or h_num.notna().any()

        if numeric_like:
            both = c_num.notna() & h_num.notna()
            if both.any():
                diff_mask = both & ((c_num - h_num).abs() > NUM_TOLERANCE)
                if diff_mask.any():
                    sample_idx = diff_mask[diff_mask].index.tolist()[:MAX_SAMPLES]
                    samples = ", ".join(
                        [
                            f"row={i} current={_format_scalar(c_num.iloc[i])} history={_format_scalar(h_num.iloc[i])}"
                            for i in sample_idx
                        ]
                    )
                    failures.append(
                        f"{label}.{col}: 数值不一致 {int(diff_mask.sum())} 行；样例: {samples}"
                    )

            null_mask = c_num.isna() ^ h_num.isna()
            if null_mask.any():
                sample_idx = null_mask[null_mask].index.tolist()[:MAX_SAMPLES]
                samples = ", ".join(
                    [
                        f"row={i} current={_format_scalar(current[col].iloc[i])} history={_format_scalar(history[col].iloc[i])}"
                        for i in sample_idx
                    ]
                )
                failures.append(
                    f"{label}.{col}: 空值分布不一致 {int(null_mask.sum())} 行；样例: {samples}"
                )
            continue

        c_text = current[col].fillna("").astype(str).str.strip()
        h_text = history[col].fillna("").astype(str).str.strip()
        diff_mask = c_text != h_text
        if diff_mask.any():
            sample_idx = diff_mask[diff_mask].index.tolist()[:MAX_SAMPLES]
            samples = ", ".join(
                [
                    f"row={i} current={c_text.iloc[i]!r} history={h_text.iloc[i]!r}"
                    for i in sample_idx
                ]
            )
            failures.append(
                f"{label}.{col}: 文本不一致 {int(diff_mask.sum())} 行；样例: {samples}"
            )


def _compare_values(label: str, current_value: Any, history_value: Any, failures: list[str]) -> None:
    if isinstance(current_value, pd.DataFrame) and isinstance(history_value, pd.DataFrame):
        _compare_dataframes(label, current_value, history_value, failures)
        return

    if isinstance(current_value, dict) and isinstance(history_value, dict):
        current_keys = set(current_value.keys())
        history_keys = set(history_value.keys())
        if current_keys != history_keys:
            failures.append(
                f"{label}: 键集合不一致 current={sorted(current_keys)} history={sorted(history_keys)}"
            )
            return
        for key in sorted(current_keys):
            _compare_values(f"{label}.{key}", current_value[key], history_value[key], failures)
        return

    if isinstance(current_value, (list, tuple)) and isinstance(history_value, (list, tuple)):
        if len(current_value) != len(history_value):
            failures.append(
                f"{label}: 长度不一致 current={len(current_value)} history={len(history_value)}"
            )
            return
        for idx, (cur_item, hist_item) in enumerate(zip(current_value, history_value)):
            _compare_values(f"{label}[{idx}]", cur_item, hist_item, failures)
        return

    cur = _normalize_scalar(current_value)
    hist = _normalize_scalar(history_value)
    if cur is None and hist is None:
        return

    if isinstance(cur, (int, float)) and isinstance(hist, (int, float)):
        if math.isnan(float(cur)) and math.isnan(float(hist)):
            return
        if abs(float(cur) - float(hist)) > NUM_TOLERANCE:
            failures.append(
                f"{label}: 数值不一致 current={_format_scalar(cur)} history={_format_scalar(hist)}"
            )
        return

    if cur != hist:
        failures.append(
            f"{label}: 值不一致 current={_format_scalar(cur)} history={_format_scalar(hist)}"
        )


def _build_dashboard_views(loader: Any, builders: dict[str, Callable[[Any], Any]]) -> dict[str, Any]:
    return {
        page_name: builder(loader)
        for page_name, builder in builders.items()
    }


def _compare_snapshot_dirs(
    current_dir: Path,
    history_dir: Path,
    failures: list[str],
    table_files: list[str],
    compare_table_file: Callable[[Path, Path], dict[str, Any]],
) -> None:
    for table_name in table_files:
        current_path = current_dir / table_name
        history_path = history_dir / table_name
        result = compare_table_file(current_path, history_path)
        if result["status"] == "PASS":
            continue

        details = []
        details.extend(result.get("structural_errors", []))
        for group_name in ("numeric_value_diffs", "numeric_null_diffs", "text_diffs"):
            for item in result.get(group_name, [])[:MAX_SAMPLES]:
                sample_text = " | ".join(item.get("samples", [])[:MAX_SAMPLES])
                details.append(f"{item['column']}({item['count']}): {sample_text}")
        detail_text = "; ".join(details[:MAX_SAMPLES]) if details else "存在差异"
        failures.append(f"snapshot.{table_name}: {detail_text}")


def main() -> int:
    parser = argparse.ArgumentParser(description="校验 DB current/history 模式下的看板口径一致")
    parser.add_argument(
        "--archive-date",
        required=True,
        help="显式历史模式使用的 archive_date（YYYY-MM-DD）",
    )
    args = parser.parse_args()

    try:
        target_date = datetime.strptime(args.archive_date, "%Y-%m-%d").date()
    except ValueError:
        print(f"❌ archive_date 必须为 YYYY-MM-DD，收到: {args.archive_date!r}")
        return 1

    from scripts.generate_display_snapshot import write_display_snapshots
    from src.visualization.data_loader import DataLoader
    from src.visualization.display_builders import (
        build_page1_single_credit_views,
        build_page2_specific_credit_views,
        build_page3_category_credit_views,
        build_page4_guarantee_views,
        build_page5_high_risk_views,
        build_page6_regional_views,
        build_page7_high_yield_views,
        build_page9_full_regulatory_views,
    )
    from validation.validate_dashboard_display import TABLE_FILES, _compare_table_file

    builders: dict[str, Callable[[Any], Any]] = {
        "page1": build_page1_single_credit_views,
        "page2": build_page2_specific_credit_views,
        "page3": build_page3_category_credit_views,
        "page4": build_page4_guarantee_views,
        "page5": build_page5_high_risk_views,
        "page6": build_page6_regional_views,
        "page7": build_page7_high_yield_views,
        "page9": build_page9_full_regulatory_views,
    }

    print("=" * 70)
    print("DB current/history 看板一致性校验")
    print("=" * 70)
    print(f"目标 archive_date: {args.archive_date}")

    current_loader = DataLoader(target_date=None)
    history_loader = DataLoader(target_date=target_date)

    failures: list[str] = []
    if current_loader.archive_date_str != args.archive_date:
        failures.append(
            "current 模式未指向本次测试归档："
            f"current={current_loader.archive_date_str}, expected={args.archive_date}"
        )

    public_checks: list[tuple[str, Callable[[DataLoader], Any]]] = [
        ("archive_date_str", lambda loader: loader.archive_date_str),
        ("data_source", lambda loader: loader.data_source),
        ("latest_date", lambda loader: loader.get_latest_date()),
        ("summary_metrics", lambda loader: loader.get_summary_metrics()),
        ("available_accounts.page1", lambda loader: loader.get_available_accounts(page_name="单一信用限额")),
        ("available_accounts.page2", lambda loader: loader.get_available_accounts(page_name="特定信用限额")),
        ("available_accounts.page3", lambda loader: loader.get_available_accounts(page_name="分类信用限额")),
        ("available_bond_types.page1", lambda loader: loader.get_available_bond_types(page_name="单一信用限额")),
        ("available_bond_types.page2", lambda loader: loader.get_available_bond_types(page_name="特定信用限额")),
        ("available_bond_types.page3", lambda loader: loader.get_available_bond_types(page_name="分类信用限额")),
        ("alert_thresholds", lambda loader: loader.load_alert_thresholds()),
        ("regulatory_concentration_limit", lambda loader: loader.load_regulatory_concentration_limit()),
        ("high_yield_annual_limit", lambda loader: loader.load_high_yield_annual_limit()),
        ("stage1_credit_1_1", lambda loader: loader.load_stage1_credit_1_1()),
        ("stage1_credit_1_2", lambda loader: loader.load_stage1_credit_1_2()),
        ("stage1_full_regulatory", lambda loader: loader.load_stage1_full_regulatory_concentration()),
        ("stage1_guarantee", lambda loader: loader.load_stage1_guarantee()),
        ("stage2_credit_2", lambda loader: loader.load_stage2_credit_2()),
        ("stage2_high_risk_industry", lambda loader: loader.load_stage2_high_risk_industry()),
        ("stage2_high_risk_province", lambda loader: loader.load_stage2_high_risk_province()),
        ("stage2_high_risk_province_detail", lambda loader: loader.load_stage2_high_risk_province_detail()),
        ("stage2_high_risk_industry_detail", lambda loader: loader.load_stage2_high_risk_industry_detail()),
        ("stage2_regional", lambda loader: loader.load_stage2_regional()),
        ("stage2_high_yield", lambda loader: loader.load_stage2_high_yield()),
        ("stage2_high_yield_capital", lambda loader: loader.load_stage2_high_yield_capital()),
    ]

    for label, getter in public_checks:
        _compare_values(label, getter(current_loader), getter(history_loader), failures)

    current_views = _build_dashboard_views(current_loader, builders)
    history_views = _build_dashboard_views(history_loader, builders)
    _compare_values("dashboard_views", current_views, history_views, failures)

    temp_root = Path(tempfile.mkdtemp(prefix="db_dashboard_consistency_"))
    try:
        current_snapshot_dir = temp_root / "current"
        history_snapshot_dir = temp_root / "history"
        write_display_snapshots(current_snapshot_dir, archive_date=None)
        write_display_snapshots(history_snapshot_dir, archive_date=args.archive_date)
        _compare_snapshot_dirs(
            current_snapshot_dir,
            history_snapshot_dir,
            failures,
            TABLE_FILES,
            _compare_table_file,
        )
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)

    if failures:
        print("❌ 一致性校验失败")
        for idx, failure in enumerate(failures[:20], start=1):
            print(f"  {idx}. {failure}")
        if len(failures) > 20:
            print(f"  ... 其余 {len(failures) - 20} 条已省略")
        return 1

    print("✅ current 模式、history 模式及展示快照口径一致")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
