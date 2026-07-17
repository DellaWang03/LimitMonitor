"""不可变的交易前服务请求、主数据与解析结果契约。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol


class MasterSource(StrEnum):
    """一笔交易前主数据的唯一来源或无法取得的原因类别。"""

    SNAPSHOT = "SNAPSHOT"
    WIND = "WIND"
    MISSING_SNAPSHOT = "MISSING_SNAPSHOT"
    MISSING_MASTER = "MISSING_MASTER"


@dataclass(frozen=True)
class PretradeLine:
    """用户输入的一行拟买交易；金额单位为万元 PR。"""

    line_id: int
    bond_code: str
    account: str
    pr_wan: float
    full_price_cost_wan: float | None = None


@dataclass(frozen=True)
class BondMaster:
    """共同内核构造一笔交易行所需的证券及发行人主数据。"""

    input_code: str
    main_security_code: str
    isin_code: str | None
    bond_name: str
    issuer_name: str
    issuer_wind_code: str | None
    controller_name: str | None
    guarantor_name: str | None
    guarantor_wind_code: str | None
    outstanding_balance_yi: float | None
    bond_classification: str | None
    bond_type: str | None
    issuer_type: str | None
    is_city_investment_bond: str | None
    bond_category: str | None
    wind_industry: str | None
    province: str | None
    # 旧测试和高收益附加源暂时仍使用 bond_name；交易原始行必须使用下列
    # 两个有明确语义的名称，不能再将二者混为一谈。
    asset_name: str | None = None
    main_security_name: str | None = None


@dataclass(frozen=True)
class MasterResolution:
    """一次、仅在当前请求内有效的主数据解析结果。"""

    source: MasterSource
    master: BondMaster | None
    reason: str | None
    wind_fetched_at: datetime | None = None
    wind_data_date: str | None = None


class BondMasterProvider(Protocol):
    """非持仓债主数据边界；实现不得持久化或缓存响应。"""

    def resolve(self, bond_code: str, business_date: datetime) -> MasterResolution:
        raise NotImplementedError
