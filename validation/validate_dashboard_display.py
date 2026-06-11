"""
展示层 CSV 严格校验（单模式）：
逐字段对比 snapshot 与目标目录中的 CSV（数值列允许容差）。
默认会校验参考目录下全部 CSV；若目录为空，再退回内置主清单。
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any

import pandas as pd


NUM_TOLERANCE = 0.01
MAX_DIFF_ROWS = 5
TABLE_FILES = [
    "单一信用限额.csv",
    "特定信用限额.csv",
    "分类信用限额.csv",
    "专业担保明细.csv",
    "地域类明细.csv",
    "高收益明细1.csv",
    "高收益明细2.csv",
    "高风险明细1.csv",
    "高风险明细2.csv",
    "全量债券监管集中度.csv",
]


def _resolve_table_files(ref_dir: Path) -> list[str]:
    """优先校验参考目录中的全部 CSV，确保人工目标目录所见即所得。"""
    ref_files = sorted(path.name for path in ref_dir.glob("*.csv"))
    return ref_files or TABLE_FILES


def _read_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(str(path), encoding="utf-8-sig", low_memory=False)
    # 兼容手工导出时产生的全空 Unnamed 列，避免影响结构性对比。
    unnamed_cols = [c for c in df.columns if str(c).startswith("Unnamed:")]
    drop_cols: list[str] = []
    for col in unnamed_cols:
        series = df[col]
        normalized = series.fillna("").astype(str).str.strip()
        if normalized.eq("").all():
            drop_cols.append(col)
    if drop_cols:
        df = df.drop(columns=drop_cols)
    return df


def _fmt(val: Any) -> str:
    if pd.isna(val):
        return "NaN"
    if isinstance(val, float):
        return f"{val:,.4f}"
    return str(val)


def _detect_key_columns(columns: list[str]) -> list[str]:
    candidates = ["资产代码", "代码", "债务主体", "资产名称", "省份名称", "行业名称", "省份", "行业"]
    keys = [c for c in candidates if c in columns]
    return keys[:2]


def _row_label(snap_row: pd.Series, ref_row: pd.Series, idx: int, key_cols: list[str]) -> str:
    parts = [f"row={idx}"]
    for key in key_cols:
        sv = _fmt(snap_row.get(key))
        rv = _fmt(ref_row.get(key))
        if sv == rv:
            parts.append(f"{key}={sv}")
        else:
            parts.append(f"{key}=snap:{sv}|ref:{rv}")
    return ", ".join(parts)


def _compare_table_file(snap_path: Path, ref_path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "PASS",
        "structural_errors": [],
        "snap_rows": 0,
        "ref_rows": 0,
        "numeric_value_diffs": [],
        "numeric_null_diffs": [],
        "text_diffs": [],
    }
    try:
        snap = _read_csv(snap_path)
        ref = _read_csv(ref_path)
    except Exception as exc:
        result["status"] = "FAIL"
        result["structural_errors"].append(f"读取失败: {exc}")
        return result

    result["snap_rows"] = int(len(snap))
    result["ref_rows"] = int(len(ref))

    if list(snap.columns) != list(ref.columns):
        result["status"] = "FAIL"
        result["structural_errors"].append(f"列集合不一致: snap={list(snap.columns)} ref={list(ref.columns)}")
        return result

    if len(snap) != len(ref):
        result["status"] = "FAIL"
        result["structural_errors"].append(f"行数不一致: snap={len(snap)} ref={len(ref)}")

    sort_cols = list(snap.columns)
    snap_cmp = snap.copy()
    ref_cmp = ref.copy()
    for col in sort_cols:
        snap_cmp[f"__sort_{col}"] = snap_cmp[col].fillna("").astype(str)
        ref_cmp[f"__sort_{col}"] = ref_cmp[col].fillna("").astype(str)
    sort_keys = [f"__sort_{c}" for c in sort_cols]
    snap_cmp = snap_cmp.sort_values(sort_keys, kind="mergesort").reset_index(drop=True)
    ref_cmp = ref_cmp.sort_values(sort_keys, kind="mergesort").reset_index(drop=True)
    snap_cmp = snap_cmp[sort_cols]
    ref_cmp = ref_cmp[sort_cols]

    cmp_len = min(len(snap_cmp), len(ref_cmp))
    snap_cmp = snap_cmp.iloc[:cmp_len].reset_index(drop=True)
    ref_cmp = ref_cmp.iloc[:cmp_len].reset_index(drop=True)
    key_cols = _detect_key_columns(sort_cols)

    for col in snap.columns:
        s_num = pd.to_numeric(snap_cmp[col], errors="coerce")
        r_num = pd.to_numeric(ref_cmp[col], errors="coerce")
        numeric_like = (s_num.notna().any() or r_num.notna().any())
        if numeric_like:
            both = s_num.notna() & r_num.notna()
            if both.any():
                bad = both & ((s_num - r_num).abs() > NUM_TOLERANCE)
                if bad.any():
                    bad_idx = bad[bad].index.tolist()
                    sample_idx = bad_idx[:MAX_DIFF_ROWS]
                    samples = []
                    for i in sample_idx:
                        label = _row_label(snap_cmp.iloc[i], ref_cmp.iloc[i], int(i), key_cols)
                        samples.append(f"{label}, snap={_fmt(s_num.iloc[i])}, ref={_fmt(r_num.iloc[i])}")
                    result["numeric_value_diffs"].append({
                        "column": col,
                        "count": int(bad.sum()),
                        "samples": samples,
                    })
            s_only = s_num.notna() & r_num.isna()
            r_only = s_num.isna() & r_num.notna()
            if s_only.any() or r_only.any():
                idx = (s_only | r_only)
                sample_idx = idx[idx].index.tolist()[:MAX_DIFF_ROWS]
                samples = [
                    f"{_row_label(snap_cmp.iloc[i], ref_cmp.iloc[i], int(i), key_cols)}, snap={_fmt(snap_cmp[col].iloc[i])}, ref={_fmt(ref_cmp[col].iloc[i])}"
                    for i in sample_idx
                ]
                result["numeric_null_diffs"].append({
                    "column": col,
                    "count": int(idx.sum()),
                    "samples": samples,
                })
            continue

        s_txt = snap_cmp[col].fillna("").astype(str).str.strip()
        r_txt = ref_cmp[col].fillna("").astype(str).str.strip()
        mismatch = s_txt != r_txt
        if mismatch.any():
            bad_idx = mismatch[mismatch].index.tolist()
            sample_idx = bad_idx[:MAX_DIFF_ROWS]
            samples = []
            for i in sample_idx:
                label = _row_label(snap_cmp.iloc[i], ref_cmp.iloc[i], int(i), key_cols)
                samples.append(f"{label}, snap={s_txt.iloc[i]!r}, ref={r_txt.iloc[i]!r}")
            result["text_diffs"].append({
                "column": col,
                "count": int(mismatch.sum()),
                "samples": samples,
            })

    has_data_diff = any([
        result["numeric_value_diffs"],
        result["numeric_null_diffs"],
        result["text_diffs"],
    ])
    if result["structural_errors"] or has_data_diff:
        result["status"] = "FAIL"
    return result


def _print_column_group(title: str, items: list[dict[str, Any]], detail_limit: int, show_samples: bool):
    if not items:
        return
    print(f"   - {title}:")
    sorted_items = sorted(items, key=lambda x: x["count"], reverse=True)
    for item in sorted_items[:detail_limit]:
        print(f"     * {item['column']}: {item['count']} 行")
        if show_samples:
            for sample in item["samples"]:
                print(f"       - {sample}")


def main():
    parser = argparse.ArgumentParser(description="展示层 CSV 严格校验")
    parser.add_argument(
        "--ref-dir",
        default="data_for_testing",
        help="参考目录（默认：data_for_testing/）",
    )
    parser.add_argument("--snapshot-dir", default="data/current/display_snapshots", help="快照目录")
    parser.add_argument("--table", default=None, help="只校验单张表，支持带或不带 .csv")
    parser.add_argument("--verbose", action="store_true", help="打印详细差异样本")
    parser.add_argument("--quiet", action="store_true", help="仅打印总览与汇总")
    parser.add_argument("--detail-limit", type=int, default=3, help="每类差异最多展示的列数")
    args = parser.parse_args()

    root = Path(__file__).parent.parent
    snap_dir = Path(args.snapshot_dir) if Path(args.snapshot_dir).is_absolute() else root / args.snapshot_dir
    ref_dir = Path(args.ref_dir) if Path(args.ref_dir).is_absolute() else root / args.ref_dir

    print("=" * 70)
    print("展示层 CSV 严格校验")
    print("=" * 70)
    print(f"快照目录: {snap_dir}")
    print(f"参考目录: {ref_dir}")
    selected_tables = _resolve_table_files(ref_dir)
    if args.table:
        name = args.table.strip()
        if not name.endswith(".csv"):
            name = f"{name}.csv"
        selected_tables = [name]

    print(f"校验表数: {len(selected_tables)}")
    print(f"差异容差: {NUM_TOLERANCE}")
    print("=" * 70)

    results: dict[str, dict[str, Any]] = {}
    for table_name in selected_tables:
        snap_path = snap_dir / table_name
        ref_path = ref_dir / table_name
        if not snap_path.exists():
            results[table_name] = {
                "status": "FAIL",
                "structural_errors": [f"快照缺失: {snap_path}"],
                "snap_rows": 0,
                "ref_rows": 0,
                "numeric_value_diffs": [],
                "numeric_null_diffs": [],
                "text_diffs": [],
            }
            continue
        if not ref_path.exists():
            results[table_name] = {
                "status": "FAIL",
                "structural_errors": [f"参考缺失: {ref_path}"],
                "snap_rows": 0,
                "ref_rows": 0,
                "numeric_value_diffs": [],
                "numeric_null_diffs": [],
                "text_diffs": [],
            }
            continue

        results[table_name] = _compare_table_file(snap_path, ref_path)

    print("结果总览:")
    for table_name in selected_tables:
        res = results[table_name]
        status = res["status"]
        icon = "✅" if status == "PASS" else "❌"
        structural_cnt = len(res["structural_errors"])
        num_cnt = len(res["numeric_value_diffs"])
        null_cnt = len(res["numeric_null_diffs"])
        text_cnt = len(res["text_diffs"])
        row_info = f"{res['snap_rows']}/{res['ref_rows']}"
        print(
            f"{icon} {status:<5} {table_name:<16} 行(snap/ref)={row_info:<11} "
            f"结构={structural_cnt} 数值={num_cnt} 可空={null_cnt} 文本={text_cnt}"
        )

    if not args.quiet:
        fail_tables = [t for t in selected_tables if results[t]["status"] == "FAIL"]
        if fail_tables:
            print(f"\n{'=' * 70}")
            print("失败明细:")
            print("=" * 70)
            for table_name in fail_tables:
                res = results[table_name]
                print(f"\n❌ {table_name}")
                for err in res["structural_errors"]:
                    print(f"   - 结构: {err}")
                _print_column_group("数值差异列", res["numeric_value_diffs"], args.detail_limit, args.verbose)
                _print_column_group("可空性差异列", res["numeric_null_diffs"], args.detail_limit, args.verbose)
                _print_column_group("文本差异列", res["text_diffs"], args.detail_limit, args.verbose)

    n_pass = sum(1 for v in results.values() if v["status"] == "PASS")
    n_fail = sum(1 for v in results.values() if v["status"] == "FAIL")
    print(f"\n{'=' * 70}")
    print(f"汇总: ✅ {n_pass}  ❌ {n_fail}  共 {len(results)} 项")
    print("=" * 70)
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
