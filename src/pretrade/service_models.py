"""不可变的交易前服务请求、主数据与解析结果契约。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from math import isfinite
from numbers import Real
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


_REQUIRED_BOND_MASTER_FIELDS = (
    "main_security_code",
    "bond_name",
    "asset_name",
    "main_security_name",
    "issuer_name",
    "issuer_wind_code",
    "controller_name",
    "outstanding_balance_yi",
    "bond_classification",
    "bond_type",
    "issuer_type",
    "is_city_investment_bond",
    "bond_category",
    "wind_industry",
    "province",
)

_RATE_BOND_OPTIONAL_MASTER_FIELDS = frozenset(
    {
        "controller_name",
        "issuer_type",
    }
)


def missing_required_bond_master_fields(
    master: BondMaster, *, require_controller: bool = True
) -> tuple[str, ...]:
    """返回快照与 Wind 共同内核输入所缺的同一组最小必填字段。"""

    missing: list[str] = []
    for field in _REQUIRED_BOND_MASTER_FIELDS:
        # 试算先读取其他主数据，再按原有持仓口径解析实控人并完整校验。
        if field == "controller_name" and not require_controller:
            continue
        if (
            master.bond_classification == "利率债"
            and field in _RATE_BOND_OPTIONAL_MASTER_FIELDS
        ):
            continue
        value = getattr(master, field)
        if isinstance(value, str):
            present = bool(value.strip())
        elif field == "outstanding_balance_yi":
            present = (
                isinstance(value, Real)
                and not isinstance(value, bool)
                and isfinite(float(value))
            )
        else:
            present = value is not None
        if not present:
            missing.append(field)
    return tuple(missing)


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
