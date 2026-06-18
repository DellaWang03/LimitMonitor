"""
数据加载器 —— 全面查询 MySQL 归档库（详见 docs/DB_ARCHIVE_REFERENCE.md）。

口径要点：

- 当前模式 (``target_date=None``) → 读取 ``archive_meta.is_current = 1``
  对应的 ``data_date``；
- 历史模式 (``target_date=<date>``) → 读取该 ``data_date`` 对应的快照；
- 任一模式都**不再**读取 ``data/current/`` / ``data/history/`` 下的业务
  Excel、配置 Excel 或 ``data_date.txt``；DB 不存在对应快照时直接抛错，
  不静默降级。

对外接口（必须保持稳定，外部页面与脚本依赖）：

- ``DataLoader(target_date=None)``；
- 12 张业务结果表的 ``load_stage*_*()``；
- 4 个配置读取入口 ``load_high_yield_annual_limit`` /
  ``load_alert_thresholds`` / ``load_regulatory_concentration_limit`` 与
  原有 ``load_*_limit`` 命名保持兼容；
- 静态方法 ``get_available_dates`` / ``get_archive_date_for_data``。

不入库的两张表（``load_stage1_single_bond`` /
``load_stage1_merged``）当前没有可视化调用方，本文件保留其方法签名但调用时
直接抛 ``NotImplementedError``，避免外部误用。
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime
from functools import lru_cache
import json
from typing import Any, Dict, List, Optional

import pandas as pd

from src.utils.archive_db import ArchiveDB
from src.visualization.code_utils import attach_display_code

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
_ARCHIVE_CATALOG_TTL_SECONDS = 10.0
_archive_catalog_cache: Dict[str, Any] = {
    "value": None,
    "expires_at": 0.0,
}


def _copy_dataframe(df: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
    if df is None:
        return None
    return df.copy(deep=True)


def _get_archive_catalog_cached() -> tuple[tuple[str, Optional[str], int], ...]:
    """
    归档元数据目录缓存。

    sidebar 会频繁读取 current/archive 日期与历史下拉项；这里把这些元数据
    合并成一次查询，避免同一轮页面渲染里多次访问 archive_meta。
    """
    now = time.monotonic()
    cached_value = _archive_catalog_cache.get("value")
    expires_at = float(_archive_catalog_cache.get("expires_at", 0.0))
    if cached_value is not None and now < expires_at:
        return cached_value

    db = ArchiveDB.from_env()
    rows = db.list_archive_meta()
    catalog_items: list[tuple[str, Optional[str], int]] = []
    seen_data_dates: set[str] = set()
    for row in rows:
        if not row.get("data_date"):
            continue
        data_date = str(row["data_date"])
        if data_date in seen_data_dates:
            continue
        seen_data_dates.add(data_date)
        catalog_items.append(
            (
                data_date,
                row.get("archive_date"),
                int(row.get("is_current", 0)),
            )
        )
    catalog = tuple(catalog_items)
    _archive_catalog_cache["value"] = catalog
    _archive_catalog_cache["expires_at"] = now + _ARCHIVE_CATALOG_TTL_SECONDS
    return catalog


@lru_cache(maxsize=256)
def _read_table_cached(
    table_name: str,
    data_date_str: str,
    snapshot_version: str,
    attach_code: bool,
) -> Optional[pd.DataFrame]:
    """
    表数据缓存。

    key 中带上 ``snapshot_version``（当前取 archive_meta.captured_at），这样即便
    同一个 ``data_date`` 被重新归档，也不会误复用旧快照内容。
    """
    del snapshot_version  # 仅作为缓存版本键使用
    db = ArchiveDB.from_env()
    df = db.read_dataframe_by_data_date(table_name, data_date_str)
    if df is None:
        return None
    if attach_code:
        df = attach_display_code(df)
    return df.copy(deep=True)


def _clear_runtime_caches() -> None:
    """测试 / 手工刷新时使用。"""
    _archive_catalog_cache["value"] = None
    _archive_catalog_cache["expires_at"] = 0.0
    _read_table_cached.cache_clear()


class DataLoader:
    """数据加载器 —— DB 单源（current / history 同口径）。"""

    # ------------------------------------------------------------------
    # 构造
    # ------------------------------------------------------------------
    def __init__(self, target_date: Optional[date] = None):
        """
        Args:
            target_date: 目标日期。``None`` 表示加载 ``archive_meta.is_current=1``
                对应的当前快照；非空时按 ``data_date = target_date`` 读取历史快照。
        """
        self.target_date = target_date
        self._db: ArchiveDB = ArchiveDB.from_env()
        archive_meta: Optional[Dict[str, Any]] = None

        if target_date is None:
            data_date_str = self._db.get_current_data_date()
            if data_date_str is None:
                raise FileNotFoundError(
                    "DB 中不存在 current 快照（archive_meta.is_current=1 未置位），"
                    "请先运行 scripts/daily_archive.py。"
                )
            archive_meta = self._db.get_archive_meta_by_data_date(data_date_str)
            if archive_meta is None:
                raise FileNotFoundError(
                    f"DB 中不存在 data_date={data_date_str} 的 archive_meta，"
                    "快照不完整，请重新运行 scripts/daily_archive.py。"
                )
        else:
            data_date_str = target_date.strftime("%Y-%m-%d")
            archive_meta = self._db.get_archive_meta_by_data_date(data_date_str)
            if archive_meta is None:
                raise FileNotFoundError(
                    f"DB 中不存在 data_date={data_date_str} 的快照，"
                    "请先确认该业务数据日期已成功归档。"
                )

        self.data_date_str: str = str(archive_meta["data_date"])
        self.archive_date_str: str = str(archive_meta["archive_date"])
        self._archive_meta: Dict[str, Any] = dict(archive_meta)
        captured_at = self._archive_meta.get("captured_at")
        self._snapshot_version: str = (
            captured_at.isoformat() if captured_at is not None else self.data_date_str
        )
        self.data_source: str = f"DB data_date={self.data_date_str}"
        logger.info(f"数据加载器初始化: {self.data_source}")

    # ------------------------------------------------------------------
    # 元数据接口（静态方法 / 实例方法签名保持稳定）
    # ------------------------------------------------------------------
    @staticmethod
    def _make_db() -> ArchiveDB:
        return ArchiveDB.from_env()

    @staticmethod
    def clear_runtime_caches() -> None:
        """清理 DataLoader 运行期缓存。"""
        _clear_runtime_caches()

    def _get_archive_meta_or_raise(self) -> Dict[str, Any]:
        """读取当前快照的 archive_meta；缺失时直接报错，不静默降级。"""
        if not self._archive_meta:
            raise FileNotFoundError(
                f"DB 中不存在 data_date={self.data_date_str} 的 archive_meta，"
                "快照不完整，请重新运行 scripts/daily_archive.py。"
            )
        return dict(self._archive_meta)

    @staticmethod
    def get_available_dates() -> List[date]:
        """
        返回 ``archive_meta`` 中所有 ``data_date``（datetime.date 列表，
        从新到旧排序），对齐历史模式按业务数据日期选择的行为。
        """
        return [
            datetime.strptime(d, "%Y-%m-%d").date()
            for d, _, _ in _get_archive_catalog_cached()
        ]

    @staticmethod
    def get_available_date_options() -> List[tuple[date, Optional[str]]]:
        """返回历史日期下拉所需的 ``(data_date, archive_date)`` 列表。"""
        return [
            (datetime.strptime(d, "%Y-%m-%d").date(), archive_date)
            for d, archive_date, _ in _get_archive_catalog_cached()
        ]

    @staticmethod
    def get_archive_date_for_data(data_date: date) -> Optional[str]:
        """
        返回某 ``data_date`` 对应的 ``archive_date``（YYYY-MM-DD 字符串）。
        """
        target = data_date.strftime("%Y-%m-%d")
        for data_date_str, archive_date, _ in _get_archive_catalog_cached():
            if data_date_str == target:
                return archive_date
        return None

    @staticmethod
    def get_data_date_for_archive(archive_date: date) -> Optional[str]:
        """
        兼容旧调用：返回某 ``archive_date`` 下最新登记的 ``data_date``。
        若同一归档日存在多个业务数据日，只返回元数据目录中的第一条。
        """
        target = archive_date.strftime("%Y-%m-%d")
        for data_date_str, archive_date_str, _ in _get_archive_catalog_cached():
            if archive_date_str == target:
                return data_date_str
        return None

    @staticmethod
    def get_current_archive_date() -> Optional[date]:
        """返回 current 快照的 ``archive_date``；不存在时返回 ``None``。"""
        for _, archive_date_str, is_current in _get_archive_catalog_cached():
            if is_current == 1:
                return datetime.strptime(archive_date_str, "%Y-%m-%d").date()
        return None

    @staticmethod
    def get_current_data_date() -> Optional[str]:
        """
        返回 current 快照的 ``data_date``（YYYY-MM-DD）；不存在时返回 ``None``。
        """
        for data_date, _, is_current in _get_archive_catalog_cached():
            if is_current == 1:
                return data_date
        return None

    # ------------------------------------------------------------------
    # 内部统一表读取入口
    # ------------------------------------------------------------------
    def _load_table(
        self,
        table_name: str,
        attach_code: bool = False,
    ) -> pd.DataFrame:
        """
        从 DB 读取指定表对应当前 ``data_date`` 的数据。

        - 表 / 数据缺失 → ``FileNotFoundError``（不再回退本地 Excel）；
        - ``日期`` 列由 ``ArchiveDB.read_dataframe`` 还原为 ``datetime``；
        - ``attach_code=True`` 时调用 ``attach_display_code`` 补充展示代码列，
          与旧版本读 Excel 后立即 ``_attach_display_code`` 的行为对齐。
        """
        df = _read_table_cached(
            table_name=table_name,
            data_date_str=self.data_date_str,
            snapshot_version=self._snapshot_version,
            attach_code=attach_code,
        )
        if df is None:
            raise FileNotFoundError(
                f"DB 中不存在 data_date={self.data_date_str} 的 "
                f"{table_name}，请先运行 scripts/daily_archive.py。"
            )
        return _copy_dataframe(df)

    def _attach_display_code(self, df: pd.DataFrame) -> pd.DataFrame:
        """对外仍保留：少数调用点（如自定义 loader 子类）会复用此方法。"""
        return attach_display_code(df)

    # ==================== Stage1 数据加载 ====================
    def load_stage1_credit_1_1(self) -> pd.DataFrame:
        """阶段1 - 债券持仓明细表_信用债 1_1（DB: stage1_credit_1_1）。"""
        return self._load_table("stage1_credit_1_1", attach_code=True)

    def load_stage1_credit_1_2(self) -> pd.DataFrame:
        """阶段1 - 债券持仓明细表_信用债 1_2（DB: stage1_credit_1_2）。"""
        return self._load_table("stage1_credit_1_2", attach_code=True)

    def load_stage1_single_bond(self) -> pd.DataFrame:
        """
        阶段1 - 单一债券明细。

        ``限额明细_单一债券.xlsx`` 当前无可视化调用方，不纳入 DB
        归档范围。保留方法签名以兼容潜在外部引用，调用时直接抛错。
        """
        raise NotImplementedError(
            "load_stage1_single_bond() 在 DB 化方案中不入库；"
            "该表当前无可视化调用方，如需恢复请补充 stage1_single_bond 表。"
        )

    def load_stage1_full_regulatory_concentration(self) -> pd.DataFrame:
        """阶段1 - 全量债券监管集中度（DB: stage1_full_regulatory）。"""
        return self._load_table("stage1_full_regulatory", attach_code=True)

    def load_stage1_guarantee(self) -> pd.DataFrame:
        """阶段1 - 单一担保人（DB: stage1_guarantee）。"""
        return self._load_table("stage1_guarantee")

    def load_stage1_merged(self) -> pd.DataFrame:
        """
        阶段1 - 债券持仓明细表_信用债_合并风险限额相关。

        该表当前无可视化调用方，不纳入 DB 归档范围。
        """
        raise NotImplementedError(
            "load_stage1_merged() 在 DB 化方案中不入库；"
            "该表当前无可视化调用方，如需恢复请补充 stage1_merged 表。"
        )

    # ==================== Stage2 数据加载 ====================
    def load_stage2_credit_2(self) -> pd.DataFrame:
        """阶段2 - 债券持仓明细表_信用债 2（DB: stage2_credit_2）。"""
        return self._load_table("stage2_credit_2", attach_code=True)

    def load_stage2_high_risk_industry(self) -> pd.DataFrame:
        """阶段2 - 高风险行业汇总（DB: stage2_high_risk_industry）。"""
        return self._load_table("stage2_high_risk_industry")

    def load_stage2_high_risk_province(self) -> pd.DataFrame:
        """阶段2 - 高风险省份汇总（DB: stage2_high_risk_province）。"""
        return self._load_table("stage2_high_risk_province")

    def load_stage2_high_risk_province_detail(self) -> pd.DataFrame:
        """阶段2 - 高风险省份明细（DB: stage2_high_risk_province_detail）。"""
        return self._load_table("stage2_high_risk_province_detail")

    def load_stage2_high_risk_industry_detail(self) -> pd.DataFrame:
        """阶段2 - 高风险行业明细（DB: stage2_high_risk_industry_detail）。"""
        return self._load_table("stage2_high_risk_industry_detail")

    def load_stage2_regional(self) -> pd.DataFrame:
        """阶段2 - 地域集中度限额(含城投)（DB: stage2_regional）。"""
        return self._load_table("stage2_regional")

    def load_stage2_high_yield(self) -> pd.DataFrame:
        """阶段2 - 高收益债券明细（DB: stage2_high_yield）。"""
        return self._load_table("stage2_high_yield", attach_code=True)

    def load_stage2_high_yield_capital(self) -> pd.DataFrame:
        """阶段2 - 高收益投资本金规模（DB: stage2_high_yield_capital）。"""
        return self._load_table("stage2_high_yield_capital")

    # ==================== 配置 / 阈值（来源已切 DB） ====================
    def load_high_yield_annual_limit(self) -> int:
        """
        年度高收益本金上限（万元）。

        来源切换至 ``archive_meta.high_yield_annual_limit_wan``。该值由
        ``daily_archive.py`` 在归档当日从 ``限额配置_当前.xlsx`` 读取后固化到
        元数据里，避免 ``stage2_high_yield_capital`` 当天 0 行时无法再从结果表
        恢复年度限额。
        """
        meta = self._get_archive_meta_or_raise()
        value = meta.get("high_yield_annual_limit_wan")
        if value is None or pd.isna(value):
            raise ValueError(
                f"archive_meta.data_date={self.data_date_str} 的 "
                "high_yield_annual_limit_wan 为空，"
                "无法确定归档当日年度高收益限额。"
            )
        return int(value)

    def load_high_yield_limit_maps(self) -> Dict[str, Dict[str, Optional[float]]]:
        """
        高收益页按资产/主体使用的限额映射。

        数据直接来自 ``stage2_high_yield`` 结果表中的配置附加列，保持当前业务
        口径不变，但把配置读取职责统一收敛到 ``DataLoader``，与其他页面一致由
        页面/展示层通过 loader 取配置，而不是在 builder 内自行解析结果表。
        """
        df = self.load_stage2_high_yield()
        if df.empty:
            empty_map = {"__default__": None}
            return {
                "bond_limits": empty_map.copy(),
                "entity_limits": empty_map.copy(),
            }

        required_columns = ["单一债券限额(万)", "单一主体限额(万)", "按类别限额JSON"]
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            raise KeyError(
                "stage2_high_yield 缺少高收益限额附加列: "
                + ", ".join(missing_columns)
            )

        bond_default = df["单一债券限额(万)"].iloc[0]
        entity_default = df["单一主体限额(万)"].iloc[0]
        raw_category_json = df["按类别限额JSON"].iloc[0]

        if pd.isna(bond_default):
            raise ValueError("stage2_high_yield.单一债券限额(万) 首行为空")
        if pd.isna(entity_default):
            raise ValueError("stage2_high_yield.单一主体限额(万) 首行为空")
        if pd.isna(raw_category_json):
            raise ValueError("stage2_high_yield.按类别限额JSON 首行为空")

        try:
            category_limits = json.loads(raw_category_json)
        except (TypeError, ValueError) as exc:
            raise ValueError("stage2_high_yield.按类别限额JSON 不是合法 JSON") from exc
        if not isinstance(category_limits, dict):
            raise ValueError("stage2_high_yield.按类别限额JSON 解析结果不是对象")

        bond_limits: Dict[str, Optional[float]] = {"__default__": float(bond_default)}
        entity_limits: Dict[str, Optional[float]] = {"__default__": float(entity_default)}
        for key, value in category_limits.items():
            try:
                float_value = float(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"按类别限额JSON 中类别 {key!r} 的限额值非法: {value!r}"
                ) from exc
            bond_limits[str(key)] = float_value
            entity_limits[str(key)] = float_value

        return {
            "bond_limits": bond_limits,
            "entity_limits": entity_limits,
        }

    def load_alert_thresholds(self) -> Dict[str, float]:
        """
        看板告警阈值（warning / overlimit）。

        来源切换至 ``archive_meta.alert_warning_threshold`` /
        ``alert_overlimit_threshold``，由 ``daily_archive.py``
        从 ``settings.yaml`` 拷贝写入。
        """
        meta = self._get_archive_meta_or_raise()
        return {
            "warning": float(meta["alert_warning_threshold"]),
            "overlimit": float(meta["alert_overlimit_threshold"]),
        }

    def load_regulatory_concentration_limit(self) -> float:
        """
        监管集中度限额（标量，例如 0.16）。

        来源切换至 ``stage1_full_regulatory.监管集中度限额指标值``
        （由 stage1 计算时随结果一并写入），每行同值，
        直接取 ``iloc[0]``。
        """
        df = self._load_table("stage1_full_regulatory")
        column = "监管集中度限额指标值"
        if column not in df.columns:
            raise KeyError(
                f"stage1_full_regulatory 缺少列 {column}，"
                "快照不完整，请检查 stage1 写出与 daily_archive 入库。"
            )

        value = df[column].iloc[0]
        if pd.isna(value):
            raise ValueError(
                f"stage1_full_regulatory.{column} 首行为空，"
                "无法确定归档当日监管集中度限额。"
            )
        return float(value)

    # ==================== 辅助方法 ====================
    def get_latest_date(self) -> datetime:
        """
        返回看板顶部展示用的"数据日期"（datetime）。

        直接取 ``archive_meta.data_date``（由 ``daily_archive.py`` 写入；
        与 ``DataLoader`` 的 DB 单源读取口径一致）。缺失时视为快照不完整，直接报错。
        """
        meta = self._get_archive_meta_or_raise()
        data_date = meta.get("data_date")
        if not data_date:
            raise ValueError(
                f"archive_meta.data_date={self.data_date_str} 的 data_date 为空，"
                "无法展示当前快照的数据日期。"
            )
        return datetime.strptime(data_date, "%Y-%m-%d")

    def get_available_accounts(
        self,
        page_name: Optional[str] = None,
    ) -> List[str]:
        """根据当前页面数据源返回账户列表（用于筛选器）。"""
        df = self._get_filter_source_df(page_name)

        accounts = sorted(
            df["内部证券账户名称"].dropna().astype(str).unique().tolist()
        )
        return ["全部"] + accounts

    def _get_filter_source_df(self, page_name: Optional[str]) -> pd.DataFrame:
        """顶部筛选器的数据源应与页面主表严格同源。"""
        if page_name == "单一信用限额":
            return self.load_stage1_credit_1_2()
        if page_name == "分类信用限额":
            return self.load_stage2_credit_2()
        if page_name == "高收益明细":
            return self.load_stage2_high_yield()
        return self.load_stage1_credit_1_1()

    def get_available_bond_types(
        self,
        page_name: Optional[str] = None,
    ) -> List[str]:
        """根据当前页面数据源返回债券分类列表（用于筛选器）。"""
        df = self._get_filter_source_df(page_name)
        bond_types = sorted(df["债券分类2"].dropna().astype(str).unique().tolist())
        return ["全部"] + bond_types

    def get_filter_options(
        self,
        page_name: Optional[str] = None,
    ) -> Dict[str, List[str]]:
        """
        一次性返回顶部筛选器所需的枚举项，避免同一张源表重复读取两次。
        """
        df = self._get_filter_source_df(page_name)
        bond_types = (
            sorted(df["债券分类2"].dropna().astype(str).unique().tolist())
            if "债券分类2" in df.columns
            else []
        )
        accounts = (
            sorted(df["内部证券账户名称"].dropna().astype(str).unique().tolist())
            if "内部证券账户名称" in df.columns
            else []
        )
        return {
            "bond_types": ["全部"] + bond_types,
            "accounts": ["全部"] + accounts,
        }

    def get_summary_metrics(self) -> Dict[str, Any]:
        """获取关键指标汇总（看板首屏 KPI 用）。"""
        df = self.load_stage2_credit_2()

        total_position = df["库存数量(万)_PR"].sum()
        overlimit_count = len(df[df["是否超限"] == "是"])
        total_count = len(df)

        return {
            "total_position": total_position,
            "total_position_formatted": f"{total_position:,.2f}",
            "overlimit_count": overlimit_count,
            "total_count": total_count,
            "overlimit_ratio": (
                f"{overlimit_count / total_count * 100:.1f}%"
                if total_count > 0
                else "0%"
            ),
            "latest_date": self.get_latest_date().strftime("%Y年%m月%d日"),
        }
