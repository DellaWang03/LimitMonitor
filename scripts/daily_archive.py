"""
每日归档脚本 —— 单点 DB 写库者（详见 docs/DB_ARCHIVE_REFERENCE.md）。

职责：
    扫描 ``data/current/`` 下的 16 张产物 Excel（4 张 Stage0 必需中间表
    + 12 张 Stage1/Stage2 业务结果表），加上从 ``限额配置_当前.xlsx`` 拷贝的
    系统参数阈值 / 高收益年度限额，先完成 schema 预同步，再在 **单个数据事务**
    内写入 MySQL 的 16 张业务表 + ``archive_meta`` 并切换 ``is_current=1``。

非职责（已从旧版本移除）：
    - 不再 ``shutil.copytree`` 业务文件到 ``data/history/``；
    - 不再写 ``data_date.txt``（由 ``archive_meta.data_date`` 替代）；
    - 不再拷贝 ``config_snapshot/限额配置_*.xlsx``（业务配置不进 DB）；
    - 不再调用 ``write_display_snapshots``（展示快照走独立入口）；
    - 不再做 ``required_dirs`` 等本地目录完整性检查（任一文件缺失直接
      ``FileNotFoundError`` 中断，事务自动回滚）。

异常处理：
    - 任一文件缺失 → ``FileNotFoundError``；
    - 任一写库失败 → ``write_batch`` 内数据事务整体回滚 → 不留半成品业务快照。
      （若失败发生在 schema 预同步阶段，可能仅留下建表 / 补列结果。）
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.utils.archive_db import ArchiveDB  # noqa: E402
from src.utils.config_loader import ConfigLoader  # noqa: E402
from src.utils.limit_config_loader import load_limit_config  # noqa: E402

# ---------------------------------------------------------------------------
# 路径常量（相对项目根）
# ---------------------------------------------------------------------------
CURRENT_DIR = _PROJECT_ROOT / "data" / "current"

# 4 张 Stage0 必需中间表（被 Stage1/2 直接消费）
REQUIRED_STAGE0_FILES: dict[str, Path] = {
    "stage0_bond_pool": CURRENT_DIR / "stage0_output" / "风控部债券池.xlsx",
    "stage0_adjusted_controller": CURRENT_DIR / "stage0_output" / "调整实控人名单.xlsx",
    "stage0_issuer_pool": CURRENT_DIR / "stage0_output" / "风控部债券池_主体.xlsx",
    "stage0_net_assets_daily": CURRENT_DIR / "stage0_output" / "公司净资产_手工_每日.xlsx",
}

# 12 张业务结果表
BUSINESS_RESULT_FILES: dict[str, Path] = {
    "stage1_credit_1_1": CURRENT_DIR / "stage1_output" / "限额明细_债券持仓明细表_信用债1_1.xlsx",
    "stage1_credit_1_2": CURRENT_DIR / "stage1_output" / "限额明细_债券持仓明细表_信用债1_2.xlsx",
    "stage1_full_regulatory": CURRENT_DIR / "stage1_output" / "限额明细_全量债券监管集中度.xlsx",
    "stage1_guarantee": CURRENT_DIR / "stage1_output" / "限额明细_单一担保人.xlsx",
    "stage2_credit_2": CURRENT_DIR / "stage2_output" / "限额明细_债券持仓明细表_信用债2.xlsx",
    "stage2_high_risk_industry": CURRENT_DIR / "stage2_output" / "限额明细_高风险行业.xlsx",
    "stage2_high_risk_province": CURRENT_DIR / "stage2_output" / "限额明细_高风险省份.xlsx",
    "stage2_high_risk_province_detail": CURRENT_DIR / "stage2_output" / "高风险省份总持仓_2.xlsx",
    "stage2_high_risk_industry_detail": CURRENT_DIR / "stage2_output" / "高风险行业总持仓_2.xlsx",
    "stage2_regional": CURRENT_DIR / "stage2_output" / "限额明细_地域集中度限额(含城投).xlsx",
    "stage2_high_yield": CURRENT_DIR / "stage2_output" / "限额明细_高收益.xlsx",
    "stage2_high_yield_capital": CURRENT_DIR / "stage2_output" / "限额明细_高收益_投资本金规模.xlsx",
}

# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def _read_alert_thresholds() -> tuple[float, float]:
    """
    从当前生效的 ``限额配置_当前.xlsx / 系统参数`` 读取展示阈值。

    该值需要写入 ``archive_meta``，保证 current/history 展示都按归档当日
    配置回放，而不是前端运行时再读取当前 Excel。
    """
    cfg = load_limit_config(
        sheet_name="系统参数",
        config=ConfigLoader(),
        inject_date=False,
    )
    required_columns = {"参数名", "值"}
    missing_columns = required_columns - set(cfg.columns)
    if missing_columns:
        raise KeyError(
            "系统参数 sheet 缺少必需列: " + ", ".join(sorted(missing_columns))
        )

    params = cfg.copy()
    params["_参数名_标准"] = params["参数名"].astype(str).str.strip()

    def require_param(name: str) -> float:
        matches = params.loc[params["_参数名_标准"] == name, "值"]
        if matches.empty:
            raise KeyError(f"系统参数 sheet 缺少参数：{name}")
        value = pd.to_numeric(matches, errors="coerce").iloc[0]
        if pd.isna(value):
            raise ValueError(f"系统参数 sheet 中 {name} 为空或非法")
        return float(value)

    return require_param("告警阈值_预警"), require_param("告警阈值_超限")


def _read_data_date(stage_tables: dict[str, pd.DataFrame]) -> Optional[str]:
    """
    从 ``stage1_credit_1_2`` 的"日期"列取 ``max`` 作为 ``data_date``
    用于看板"归档日 (数据日期: xxx)"展示。
    """
    df = stage_tables.get("stage1_credit_1_2")
    if df is None or "日期" not in df.columns:
        return None
    series = pd.to_datetime(df["日期"], errors="coerce")
    max_date = series.max()
    if pd.isna(max_date):
        return None
    return max_date.strftime("%Y-%m-%d")


def _read_high_yield_annual_limit() -> float:
    """
    从当前生效的 ``限额配置_当前.xlsx`` 读取"年度高收益债券投资本金规模"。

    该值需要写入 ``archive_meta``，保证高收益页面在"当日 0 行结果"场景下
    仍能从 DB 单源拿到年度限额。
    """
    cfg = load_limit_config(
        sheet_name="高收益限额",
        config=ConfigLoader(),
        inject_date=False,
    )
    required_columns = {"指标", "限额(万)"}
    missing_columns = required_columns - set(cfg.columns)
    if missing_columns:
        raise KeyError(
            "高收益限额 sheet 缺少必需列: " + ", ".join(sorted(missing_columns))
        )

    indicator_series = cfg["指标"].astype(str).str.strip()
    matches = cfg.loc[indicator_series == "年度高收益债券投资本金规模", "限额(万)"]
    if matches.empty:
        raise KeyError("高收益限额 sheet 缺少指标：年度高收益债券投资本金规模")

    value = pd.to_numeric(matches, errors="coerce").iloc[0]
    if pd.isna(value):
        raise ValueError("高收益限额 sheet 中 年度高收益债券投资本金规模 为空或非法")
    return float(value)


def _require_data_date(data_date: Optional[str]) -> str:
    """
    ``data_date`` 是 DB 快照的必需元数据；为空时拒绝写库。
    """
    if data_date:
        return data_date
    raise ValueError(
        "无法从 stage1_credit_1_2.日期 解析 data_date；"
        "当前快照元数据不完整，已拒绝写入 DB。"
    )


def _load_stage_tables() -> dict[str, pd.DataFrame]:
    """
    一次性扫描 16 张 Excel 产物为 ``{table_name: dataframe}``。

    任一文件缺失立即抛 ``FileNotFoundError`` —— 由 ``main`` 兜住，
    不进入 ``write_batch``，DB 上不会出现半成品快照。
    """
    stage_tables: dict[str, pd.DataFrame] = {}
    files = {**REQUIRED_STAGE0_FILES, **BUSINESS_RESULT_FILES}
    total = len(files)
    for idx, (table_name, path) in enumerate(files.items(), start=1):
        if not path.exists():
            raise FileNotFoundError(
                f"缺失产物（无法归档）: {path}（对应表 {table_name}）"
            )
        df = pd.read_excel(path)
        stage_tables[table_name] = df
        print(f"  [{idx:>2}/{total}] {table_name:<36s} ← {path.name}  ({len(df)} 行)")
    return stage_tables


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def archive_to_db(archive_date: str) -> int:
    """
    执行单点归档写库。

    流程：

        1. 解析 / 校验 ``archive_date``；
        2. 扫描 16 张产物 dataframe（任一缺失抛 ``FileNotFoundError``）；
        3. 从 ``stage1_credit_1_2`` 解析 ``data_date``；
        4. 从配置文件读取展示阈值 / 高收益年度限额；
        5. ``ArchiveDB.prepare_stage_tables_schema()`` 预同步 schema；
        6. ``ArchiveDB.write_batch()`` 按 ``data_date`` 覆盖写入 16 张表
           + ``archive_meta``。

    任一步失败：异常向上抛；若失败发生在第 6 步，数据事务整体回滚。
    """
    print("📦 开始每日归档（DB 单点写入）...")
    print(f"📅 archive_date: {archive_date}")
    print("=" * 70)

    if not CURRENT_DIR.exists():
        raise FileNotFoundError(f"data/current 目录不存在: {CURRENT_DIR}")

    print("\n[1/5] 扫描 data/current/ 下 16 张产物 Excel...")
    stage_tables = _load_stage_tables()

    print("\n[2/5] 解析 data_date（取 stage1_credit_1_2.日期 的 max）...")
    data_date = _require_data_date(_read_data_date(stage_tables))
    print(f"  data_date = {data_date}")

    print("\n[3/5] 读取展示阈值与高收益年度限额...")
    warning, overlimit = _read_alert_thresholds()
    high_yield_annual_limit_wan = _read_high_yield_annual_limit()
    print(f"  warning   = {warning}")
    print(f"  overlimit = {overlimit}")
    print(f"  high_yield_annual_limit_wan = {high_yield_annual_limit_wan}")

    print("\n[4/5] 预同步 DB schema（archive_meta + 16 张 stage 表）...")
    db = ArchiveDB.from_env()
    db.prepare_stage_tables_schema(
        archive_date=archive_date,
        data_date=data_date,
        stage_tables=stage_tables,
    )

    print(
        "\n[5/5] 单事务写入 DB"
        "（按 data_date 覆盖；16 张 stage 表 + archive_meta，切 is_current=1）..."
    )
    db.write_batch(
        archive_date=archive_date,
        stage_tables=stage_tables,
        data_date=data_date,
        alert_warning_threshold=warning,
        alert_overlimit_threshold=overlimit,
        high_yield_annual_limit_wan=high_yield_annual_limit_wan,
    )

    print("\n" + "=" * 70)
    print("✅ 归档完成（已切 is_current=1）")
    print(f"   archive_date : {archive_date}")
    print(f"   data_date    : {data_date}")
    print(f"   tables       : {len(stage_tables)} 张（4 stage0 + 12 业务）")
    print(f"   thresholds   : warning={warning}, overlimit={overlimit}")
    print(f"   hy_limit_wan : {high_yield_annual_limit_wan}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="每日归档脚本（DB 单点写库者）"
    )
    parser.add_argument(
        "--archive-date",
        type=str,
        default=None,
        help="归档日期（YYYY-MM-DD），默认为今天；T-1 补跑请显式传入",
    )
    args = parser.parse_args()

    archive_date = args.archive_date or datetime.now().strftime("%Y-%m-%d")

    try:
        datetime.strptime(archive_date, "%Y-%m-%d")
    except ValueError:
        print(f"❌ archive_date 必须为 'YYYY-MM-DD' 格式，收到: {archive_date!r}")
        return 1

    try:
        return archive_to_db(archive_date)
    except FileNotFoundError as e:
        print(f"\n❌ 归档失败（产物缺失）: {e}")
        return 1
    except Exception as e:
        print(
            "\n❌ 归档失败：数据快照未提交。"
            "若失败发生在 schema 预同步阶段，可能仅留下建表/补列结果。"
        )
        print(f"   详细错误: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
