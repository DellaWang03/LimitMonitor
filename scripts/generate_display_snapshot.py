"""
展示层快照生成脚本（单模式）：
仅输出 9 张 CSV，用于黄金校验。
"""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd


def _ensure_project_import_path(project_root: Path):
    project_root_str = str(project_root)
    if project_root_str not in sys.path:
        sys.path.insert(0, project_root_str)


class SnapshotDataLoader:
    """供快照脚本使用的轻量 DataLoader，避免依赖运行时状态。"""

    def __init__(self, project_root: Path, current_dir: Path):
        self.project_root = project_root
        self.stage1_output_dir = current_dir / "stage1_output"
        self.stage2_output_dir = current_dir / "stage2_output"
        self.target_date = None

    @staticmethod
    def _load_excel(path: Path) -> pd.DataFrame:
        df = pd.read_excel(str(path))
        if "日期" in df.columns:
            df["日期"] = pd.to_datetime(df["日期"], errors="coerce")
        return df

    @staticmethod
    def _attach_display_code(df: pd.DataFrame) -> pd.DataFrame:
        if "资产代码" not in df.columns and "证券代码" in df.columns:
            df = df.copy()
            df["资产代码"] = df["证券代码"]
        if "资产代码" not in df.columns:
            return df
        out = df.copy()
        out["资产代码"] = out["资产代码"].astype(str).str.strip()
        if "ISIN码" in out.columns:
            out["ISIN码"] = out["ISIN码"].astype(str).str.strip()
            out["代码"] = out["ISIN码"].where(out["ISIN码"].str.len() > 0, out["资产代码"])
        else:
            out["代码"] = out["资产代码"]
        return out

    def load_stage1_credit_1_1(self) -> pd.DataFrame:
        return self._attach_display_code(self._load_excel(self.stage1_output_dir / "限额明细_债券持仓明细表_信用债1_1.xlsx"))

    def load_stage1_credit_1_2(self) -> pd.DataFrame:
        return self._attach_display_code(self._load_excel(self.stage1_output_dir / "限额明细_债券持仓明细表_信用债1_2.xlsx"))

    def load_stage1_guarantee(self) -> pd.DataFrame:
        return self._load_excel(self.stage1_output_dir / "限额明细_单一担保人.xlsx")

    def load_stage1_full_regulatory_concentration(self) -> pd.DataFrame:
        return self._attach_display_code(self._load_excel(self.stage1_output_dir / "限额明细_全量债券监管集中度.xlsx"))

    def load_stage2_credit_2(self) -> pd.DataFrame:
        return self._attach_display_code(self._load_excel(self.stage2_output_dir / "限额明细_债券持仓明细表_信用债2.xlsx"))

    def load_stage2_high_risk_industry(self) -> pd.DataFrame:
        return self._load_excel(self.stage2_output_dir / "限额明细_高风险行业.xlsx")

    def load_stage2_high_risk_province(self) -> pd.DataFrame:
        return self._load_excel(self.stage2_output_dir / "限额明细_高风险省份.xlsx")

    def load_stage2_high_risk_province_detail(self) -> pd.DataFrame:
        return self._load_excel(self.stage2_output_dir / "高风险省份总持仓_2.xlsx")

    def load_stage2_high_risk_industry_detail(self) -> pd.DataFrame:
        return self._load_excel(self.stage2_output_dir / "高风险行业总持仓_2.xlsx")

    def load_stage2_regional(self) -> pd.DataFrame:
        return self._load_excel(self.stage2_output_dir / "限额明细_地域集中度限额(含城投).xlsx")

    def load_stage2_high_yield(self) -> pd.DataFrame:
        return self._attach_display_code(self._load_excel(self.stage2_output_dir / "限额明细_高收益.xlsx"))

    def load_stage2_high_yield_capital(self) -> pd.DataFrame:
        return self._load_excel(self.stage2_output_dir / "限额明细_高收益_投资本金规模.xlsx")

    def load_high_yield_annual_limit(self) -> int:
        from src.utils.config_loader import ConfigLoader

        fallback = 100000
        try:
            config = ConfigLoader(str(self.project_root / "config"))
            file_path = config.get_data_file_path("限额监控_阶段0_指标设置.xlsx")
            df = pd.read_excel(str(file_path), sheet_name="高收益限额")
            row = df[df["指标"].astype(str).str.strip() == "年度高收益债券投资本金规模"]
            if row.empty:
                return fallback
            return int(row.iloc[0]["限额(万)"])
        except Exception:
            return fallback


def _resolve_snapshot_datetime(loader: SnapshotDataLoader) -> str:
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
    out = table.rename(columns={"省份": "省份名称", "PR后规模(万)": "高风险省份总持仓_PR"}).copy()
    if date_str:
        out["日期"] = date_str
    expected = ["省份名称", "日期", "高风险省份总持仓_PR"]
    for col in expected:
        if col not in out.columns:
            out[col] = pd.NA
    return out[expected]


def _project_high_risk_industry(table: pd.DataFrame, date_str: str) -> pd.DataFrame:
    out = table.rename(columns={"行业": "行业名称", "PR后规模(万)": "高风险行业总持仓_PR"}).copy()
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


def _ensure_snapshot_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)
    for child in path.iterdir():
        if child.is_file():
            child.unlink()
        elif child.is_dir():
            import shutil
            shutil.rmtree(child)


def _save_single_mode_csv(base_dir: Path, csv_map: dict[str, pd.DataFrame]):
    for name, df in csv_map.items():
        out = df.copy()
        if "日期" in out.columns:
            raw_dates = out["日期"].copy()
            date_series = pd.to_datetime(out["日期"], errors="coerce")
            out["日期"] = date_series.dt.strftime("%Y-%m-%d %H:%M:%S")
            out.loc[date_series.isna(), "日期"] = raw_dates[date_series.isna()].fillna("").astype(str)
        out.to_csv(base_dir / name, index=False, encoding="utf-8-sig")


def write_display_snapshots(project_root: Path, history_target: "Path | None", current_dir: Path):
    try:
        _ensure_project_import_path(project_root)
        from src.visualization.display_builders import (
            export_legacy_page1_single_credit_table,
            export_legacy_page2_specific_credit_table,
            export_legacy_page3_category_credit_table,
            build_page4_guarantee_views,
            build_page5_high_risk_views,
            build_page6_regional_views,
            build_page7_high_yield_views,
        )
    except Exception as exc:
        print(f"❌ 导入展示构造层失败: {exc}")
        return

    current_snap_dir = current_dir / "display_snapshots"
    current_snap_dir.mkdir(parents=True, exist_ok=True)
    history_snap_dir = None
    if history_target is not None:
        history_snap_dir = history_target / "display_snapshots"
        history_snap_dir.mkdir(parents=True, exist_ok=True)

    loader = SnapshotDataLoader(project_root, current_dir)
    page4 = build_page4_guarantee_views(loader)
    page5 = build_page5_high_risk_views(loader)
    page6 = build_page6_regional_views(loader)
    page7 = build_page7_high_yield_views(loader)
    snapshot_datetime = _resolve_snapshot_datetime(loader)

    csv_map = {
        "单一信用限额.csv": export_legacy_page1_single_credit_table(loader),
        "特定信用限额.csv": export_legacy_page2_specific_credit_table(loader),
        "分类信用限额.csv": export_legacy_page3_category_credit_table(loader),
        "专业担保明细.csv": page4.get("tables", {}).get("main", pd.DataFrame()),
        "地域类明细.csv": page6.get("tables", {}).get("tab1_detail", pd.DataFrame()),
        "高收益明细1.csv": _project_high_yield_asset(page7.get("tables", {}).get("tab2_asset_summary", pd.DataFrame())),
        "高收益明细2.csv": page7.get("tables", {}).get("tab2_issuer_summary", pd.DataFrame()),
        "高风险明细1.csv": _project_high_risk_province(page5.get("tables", {}).get("tab1_province_summary", pd.DataFrame()), snapshot_datetime),
        "高风险明细2.csv": _project_high_risk_industry(page5.get("tables", {}).get("tab2_industry_summary", pd.DataFrame()), snapshot_datetime),
    }

    _ensure_snapshot_dir(current_snap_dir)
    _save_single_mode_csv(current_snap_dir, csv_map)

    if history_snap_dir is not None:
        _ensure_snapshot_dir(history_snap_dir)
        _save_single_mode_csv(history_snap_dir, csv_map)

    print("📋 展示层快照生成完成（单模式 9 CSV）")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="生成展示层 9 张 CSV 快照")
    parser.add_argument(
        "--current-dir",
        type=str,
        default=None,
        help="data/current 目录路径，默认为 <project_root>/data/current",
    )
    args = parser.parse_args()

    project_root = Path(__file__).parent.parent
    current_dir = Path(args.current_dir) if args.current_dir else project_root / "data" / "current"

    if not current_dir.exists():
        print(f"❌ 错误: current目录不存在: {current_dir}")
        return 1

    write_display_snapshots(project_root, None, current_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
