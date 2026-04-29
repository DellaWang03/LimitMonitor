"""
⚠️  禁止在生产链路调用。此脚本为一次性历史辅助工具，已从 run_daily.sh 中移除。
    生产环境中，限额配置由业务人员直接维护 config/settings.yaml 对应 profile
    解析出的 限额配置_当前.xlsx（migration 通常位于共享盘 限额/限额监控）；
    告警阈值通过 config/settings.yaml → alerts.thresholds_default 配置，
    由 daily_archive.py 写入 archive_meta，看板从 DB 读取。

一次性脚本：从 限额监控_阶段0_指标设置.xlsx 生成截面格式的 限额配置_当前.xlsx
规则：
- 有 '日期' 列的 13 个 Sheet：只保留最新日期的记录，删除 '日期' 列
- 无 '日期' 列的 2 个 Sheet（穿透高收益债券、高收益限额）：原样复制
- 追加「系统参数」Sheet：优先复用已有 限额配置_当前.xlsx / 系统参数；首次生成或缺失时使用当前 settings.yaml + 默认监管阈值
"""
import sys
from pathlib import Path

import pandas as pd
import yaml

PROJECT_ROOT = Path(__file__).parent.parent
SRC_FILE = PROJECT_ROOT / "data_source_0123" / "限额监控_阶段0_指标设置.xlsx"
DST_FILE = PROJECT_ROOT / "data_source_0123" / "限额配置_当前.xlsx"
SETTINGS_FILE = PROJECT_ROOT / "config" / "settings.yaml"
SYSTEM_PARAM_NAMES = ["告警阈值_预警", "告警阈值_超限", "监管集中度限额"]
EXCEL_ENGINE = "openpyxl"
DEFAULT_WARNING = 0.80
DEFAULT_OVERLIMIT = 1.00
DEFAULT_REG_LIMIT = 0.16


def _normalize_system_params(df: pd.DataFrame) -> pd.DataFrame | None:
    """校验并标准化系统参数表，仅接受固定两列和三个参数名。"""
    if "参数名" not in df.columns or "值" not in df.columns:
        return None

    normalized = df[["参数名", "值"]].copy()
    normalized["参数名"] = normalized["参数名"].astype(str).str.strip()
    normalized = normalized.drop_duplicates(subset=["参数名"], keep="first")

    if set(normalized["参数名"]) != set(SYSTEM_PARAM_NAMES):
        return None

    normalized["参数名"] = pd.Categorical(
        normalized["参数名"],
        categories=SYSTEM_PARAM_NAMES,
        ordered=True,
    )
    normalized = normalized.sort_values("参数名").reset_index(drop=True)
    normalized["参数名"] = normalized["参数名"].astype(str)
    return normalized


def _load_existing_system_params() -> pd.DataFrame | None:
    """优先沿用已有配置文件中的系统参数，避免重生成时被旧来源覆盖。"""
    if not DST_FILE.exists():
        return None
    try:
        df = pd.read_excel(DST_FILE, sheet_name="系统参数", engine=EXCEL_ENGINE)
        normalized = _normalize_system_params(df)
        if normalized is not None:
            return normalized
        print("  ⚠️  已有系统参数 sheet 格式不符合预期，改用旧来源重建")
    except Exception:
        pass
    return None


def _build_system_params() -> pd.DataFrame:
    """构建系统参数表。优先复用已有 Excel 配置，首次生成时回退旧来源。"""
    existing = _load_existing_system_params()
    if existing is not None:
        return existing

    warning = DEFAULT_WARNING
    overlimit = DEFAULT_OVERLIMIT
    reg_limit = DEFAULT_REG_LIMIT

    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        threshold_cfg = cfg.get("alerts", {}).get("thresholds_default", {}) or {}
        warning = float(threshold_cfg.get("warning", warning))
        overlimit = float(threshold_cfg.get("overlimit", overlimit))
    except Exception as e:
        print(f"  ⚠️  读取 settings.yaml 失败，使用默认值: {e}")

    return pd.DataFrame(
        {
            "参数名": SYSTEM_PARAM_NAMES,
            "值": [warning, overlimit, reg_limit],
        }
    )


def generate():
    if not SRC_FILE.exists():
        print(f"❌ 源文件不存在: {SRC_FILE}")
        sys.exit(1)

    xls = pd.ExcelFile(SRC_FILE, engine=EXCEL_ENGINE)
    sheet_names = xls.sheet_names

    print(f"源文件: {SRC_FILE.name}")
    print(f"目标文件: {DST_FILE.name}")
    print(f"共 {len(sheet_names)} 个 Sheet（+ 1 个系统参数 Sheet）\n")

    header = f"{'Sheet':<28} {'原始行数':>10} {'最新日期':<14} {'新文件行数':>10}"
    print(header)
    print("-" * len(header))

    with pd.ExcelWriter(DST_FILE, engine="openpyxl") as writer:
        for name in sheet_names:
            df = pd.read_excel(SRC_FILE, sheet_name=name, engine=EXCEL_ENGINE)
            orig_rows = len(df)

            if "日期" in df.columns:
                df["日期"] = pd.to_datetime(df["日期"])
                latest_date = df["日期"].max()
                df_new = df[df["日期"] == latest_date].copy()
                df_new = df_new.drop(columns=["日期"])
                df_new = df_new.reset_index(drop=True)
                date_str = latest_date.strftime("%Y-%m-%d")
            else:
                df_new = df.copy()
                latest_date = None
                date_str = "（无日期列）"

            new_rows = len(df_new)
            print(f"{name:<28} {orig_rows:>10} {date_str:<14} {new_rows:>10}")
            df_new.to_excel(writer, sheet_name=name, index=False)

        # 追加系统参数 Sheet（告警阈值 + 监管集中度限额）
        df_sys = _build_system_params()
        df_sys.to_excel(writer, sheet_name="系统参数", index=False)
        print(f"{'系统参数':<28} {'—':>10} {'（从配置读取）':<14} {len(df_sys):>10}")

    print(f"\n✅ 已生成: {DST_FILE}")


if __name__ == "__main__":
    generate()
