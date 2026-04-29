"""
展示层快照生成脚本（DB 单源薄包装）。

职责（详见 docs/db_migration_plan.md §5 阶段四 4f / §6.2）：

1. 通过 ``DataLoader(target_date=...)`` 从 MySQL 归档库读取展示数据（``--archive-date``
   省略时读 ``archive_meta.is_current=1`` 对应快照）；
2. 调用 ``display_builders`` 复用页面构造逻辑；
3. 输出 10 张主清单 CSV 到 ``data/current/display_snapshots/``，供
   ``validation/validate_dashboard_display.py`` 黄金校验比对。

非职责（已从旧版本移除）：

- 不再内置 ``SnapshotDataLoader`` 直接读 ``data/current/stage*_output/`` 的
  Excel；DB 化后 stage 输出读取统一收敛在 ``DataLoader`` 内部。
- 不再写入 ``data/history/<date>/display_snapshots/``：历史目录在本期
  彻底退出运行链路（§2.4 / §6.2）。
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def _resolve_snapshot_datetime(loader) -> str:
    """
    给"高风险省份/行业"两张投影 CSV 注入统一的 ``日期`` 字符串。

    口径：取 ``stage2_credit_2.日期`` 的 max，与历史快照行为完全一致；缺失时
    返回空串（projection helpers 会兜底为 NA）。
    """
    try:
        df = loader.load_stage2_credit_2()
        if "日期" in df.columns and not df.empty:
            dt = pd.to_datetime(df["日期"], errors="coerce").max()
            if pd.notna(dt):
                return pd.Timestamp(dt).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        pass
    return ""


def _project_high_risk_province(table: pd.DataFrame, date_str: str) -> pd.DataFrame:
    out = table.rename(
        columns={"省份": "省份名称", "PR后规模(万)": "高风险省份总持仓_PR"}
    ).copy()
    if date_str:
        out["日期"] = date_str
    expected = ["省份名称", "日期", "高风险省份总持仓_PR"]
    for col in expected:
        if col not in out.columns:
            out[col] = pd.NA
    return out[expected]


def _project_high_risk_industry(table: pd.DataFrame, date_str: str) -> pd.DataFrame:
    out = table.rename(
        columns={"行业": "行业名称", "PR后规模(万)": "高风险行业总持仓_PR"}
    ).copy()
    if date_str:
        out["日期"] = date_str
    expected = ["行业名称", "日期", "高风险行业总持仓_PR"]
    for col in expected:
        if col not in out.columns:
            out[col] = pd.NA
    return out[expected]


def _project_high_yield_asset(table: pd.DataFrame) -> pd.DataFrame:
    out = table.drop(columns=["代码"], errors="ignore").copy()
    expected = ["资产名称", "PR后规模(万)", "限额(万)", "剩余投资额度(万)", "是否超限"]
    for col in expected:
        if col not in out.columns:
            out[col] = pd.NA
    return out[expected]


def _ensure_snapshot_dir(path: Path) -> None:
    """保证 snapshot 目录存在且为空（清掉上一次的 CSV / 子目录）。"""
    path.mkdir(parents=True, exist_ok=True)
    for child in path.iterdir():
        if child.is_file():
            child.unlink()
        elif child.is_dir():
            shutil.rmtree(child)


def _save_csvs(base_dir: Path, csv_map: dict[str, pd.DataFrame]) -> None:
    """逐张写出 CSV；``日期`` 列统一格式化为 ``%Y-%m-%d %H:%M:%S``。"""
    for name, df in csv_map.items():
        out = df.copy()
        if "日期" in out.columns:
            raw_dates = out["日期"].copy()
            date_series = pd.to_datetime(out["日期"], errors="coerce")
            out["日期"] = date_series.dt.strftime("%Y-%m-%d %H:%M:%S")
            out.loc[date_series.isna(), "日期"] = (
                raw_dates[date_series.isna()].fillna("").astype(str)
            )
        out.to_csv(base_dir / name, index=False, encoding="utf-8-sig")


def write_display_snapshots(
    snapshot_dir: Path,
    archive_date: Optional[str] = None,
) -> None:
    """
    从 DB 读数据 + 用 ``display_builders`` 构造展示对象 + 写出 10 张 CSV。

    Args:
        snapshot_dir: 输出目录（默认 ``data/current/display_snapshots``）。
        archive_date: ``YYYY-MM-DD``；``None`` 时读取 current 快照。
    """
    from src.visualization.data_loader import DataLoader
    from src.visualization.display_builders import (
        build_page4_guarantee_views,
        build_page5_high_risk_views,
        build_page6_regional_views,
        build_page7_high_yield_views,
        build_page9_full_regulatory_views,
        export_legacy_page1_single_credit_table,
        export_legacy_page2_specific_credit_table,
        export_legacy_page3_category_credit_table,
    )

    target_date = (
        datetime.strptime(archive_date, "%Y-%m-%d").date()
        if archive_date
        else None
    )
    loader = DataLoader(target_date=target_date)
    print(f"📋 展示快照数据源: {loader.data_source}")

    page4 = build_page4_guarantee_views(loader)
    page5 = build_page5_high_risk_views(loader)
    page6 = build_page6_regional_views(loader)
    page7 = build_page7_high_yield_views(loader)
    page9 = build_page9_full_regulatory_views(loader)
    snapshot_datetime = _resolve_snapshot_datetime(loader)

    csv_map = {
        "单一信用限额.csv": export_legacy_page1_single_credit_table(loader),
        "特定信用限额.csv": export_legacy_page2_specific_credit_table(loader),
        "分类信用限额.csv": export_legacy_page3_category_credit_table(loader),
        "专业担保明细.csv": page4.get("tables", {}).get("main", pd.DataFrame()),
        "地域类明细.csv": page6.get("tables", {}).get("tab1_detail", pd.DataFrame()),
        "高收益明细1.csv": _project_high_yield_asset(
            page7.get("tables", {}).get("tab2_asset_summary", pd.DataFrame())
        ),
        "高收益明细2.csv": page7.get("tables", {}).get(
            "tab2_issuer_summary", pd.DataFrame()
        ),
        "高风险明细1.csv": _project_high_risk_province(
            page5.get("tables", {}).get("tab1_province_summary", pd.DataFrame()),
            snapshot_datetime,
        ),
        "高风险明细2.csv": _project_high_risk_industry(
            page5.get("tables", {}).get("tab2_industry_summary", pd.DataFrame()),
            snapshot_datetime,
        ),
        "全量债券监管集中度.csv": page9.get("tables", {}).get(
            "main", pd.DataFrame()
        ),
    }

    _ensure_snapshot_dir(snapshot_dir)
    _save_csvs(snapshot_dir, csv_map)

    print(
        f"📋 展示层快照生成完成（{len(csv_map)} 张 CSV，含 page9 主表）"
        f" → {snapshot_dir}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="生成展示层核心对象 CSV 快照（DB 单源；含 page9 主表）"
    )
    parser.add_argument(
        "--archive-date",
        type=str,
        default=None,
        help="归档日期（YYYY-MM-DD），默认读 archive_meta.is_current=1",
    )
    parser.add_argument(
        "--snapshot-dir",
        type=str,
        default=None,
        help="输出目录，默认 <project_root>/data/current/display_snapshots",
    )
    args = parser.parse_args()

    if args.archive_date is not None:
        try:
            datetime.strptime(args.archive_date, "%Y-%m-%d")
        except ValueError:
            print(
                f"❌ archive_date 必须为 'YYYY-MM-DD' 格式，收到: {args.archive_date!r}"
            )
            return 1

    snapshot_dir = (
        Path(args.snapshot_dir)
        if args.snapshot_dir
        else _PROJECT_ROOT / "data" / "current" / "display_snapshots"
    )

    try:
        write_display_snapshots(snapshot_dir, archive_date=args.archive_date)
    except Exception as exc:
        print(f"❌ 展示快照生成失败: {exc}")
        import traceback

        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
