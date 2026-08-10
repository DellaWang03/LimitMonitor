"""供两个交易前页面使用的只读共同服务工厂。"""

from __future__ import annotations

import os

from src.pretrade.context_store import PretradeContextStore
from src.pretrade.pretrade_service import PretradeRiskService, PretradeServiceError
from src.pretrade.windpy_master import WindPyBondMasterProvider
from src.utils.archive_db import ArchiveDB


def get_pretrade_risk_service() -> PretradeRiskService:
    """构造一次请求使用的服务；不创建 schema、不写快照或 current 指针。"""

    try:
        engine = ArchiveDB.from_env().engine
    except Exception as exc:
        raise PretradeServiceError("交易前数据库配置或连接不可用") from exc
    return PretradeRiskService(
        store=PretradeContextStore(engine),
        wind_provider=WindPyBondMasterProvider(
            field_mapping_verified=_wind_field_mapping_verified()
        ),
    )


def _wind_field_mapping_verified() -> bool:
    return os.environ.get(
        "LIMIT_MONITOR_WIND_FIELD_MAPPING_VERIFIED", "true"
    ).strip().lower() not in {"0", "false", "no", "off"}
