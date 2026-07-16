"""供两个交易前页面使用的只读共同服务工厂。"""

from __future__ import annotations

from src.pretrade.context_store import PretradeContextStore
from src.pretrade.pretrade_service import PretradeRiskService
from src.pretrade.windpy_master import WindPyBondMasterProvider
from src.utils.archive_db import ArchiveDB


def get_pretrade_risk_service() -> PretradeRiskService:
    """构造一次请求使用的服务；不创建 schema、不写快照或 current 指针。"""

    return PretradeRiskService(
        store=PretradeContextStore(ArchiveDB.from_env().engine),
        wind_provider=WindPyBondMasterProvider(),
    )
