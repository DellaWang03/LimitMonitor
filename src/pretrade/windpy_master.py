"""仅请求一次的 WindPy 债券主数据边界。

字段代码必须先经只读连通性验收后由调用方显式传入。本模块不保留 Wind
响应，也不读写文件或数据库。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from math import isfinite, isnan
from typing import Any, Mapping, Protocol

from .service_models import BondMaster, MasterResolution, MasterSource


_MASTER_ATTRIBUTES = (
    "main_security_code",
    "isin_code",
    "bond_name",
    "issuer_name",
    "issuer_wind_code",
    "controller_name",
    "guarantor_name",
    "guarantor_wind_code",
    "outstanding_balance_yi",
    "bond_classification",
    "bond_type",
    "issuer_type",
    "is_city_investment_bond",
    "bond_category",
    "wind_industry",
    "province",
)
_OPTIONAL_MASTER_ATTRIBUTES = frozenset(
    {"isin_code", "guarantor_name", "guarantor_wind_code"}
)


class WindGateway(Protocol):
    """WindPy 的最小可替换接口，避免在导入时初始化 Wind。"""

    def start(self) -> Any:
        raise NotImplementedError

    def wss(self, bond_code: str, fields: str, *, usedf: bool) -> Any:
        raise NotImplementedError


@dataclass(frozen=True)
class WindFieldMap:
    """一个已经通过能力门禁验证的 Wind 字段映射。"""

    main_security_code: str
    isin_code: str
    bond_name: str
    issuer_name: str
    issuer_wind_code: str
    controller_name: str
    guarantor_name: str
    guarantor_wind_code: str
    outstanding_balance_yi: str
    bond_classification: str
    bond_type: str
    issuer_type: str
    is_city_investment_bond: str
    bond_category: str
    wind_industry: str
    province: str
    wind_data_date: str | None = None
    optional_attributes: frozenset[str] = field(
        default_factory=lambda: _OPTIONAL_MASTER_ATTRIBUTES
    )

    def __post_init__(self) -> None:
        unknown_optional = set(self.optional_attributes) - set(_MASTER_ATTRIBUTES)
        if unknown_optional:
            raise ValueError(f"Wind 可选字段未知: {sorted(unknown_optional)}")
        for attribute in _MASTER_ATTRIBUTES:
            vendor_field = getattr(self, attribute)
            if not isinstance(vendor_field, str) or not vendor_field.strip():
                raise ValueError(f"Wind 字段映射为空: {attribute}")
        if self.wind_data_date is not None and not self.wind_data_date.strip():
            raise ValueError("Wind 数据日期字段不能为空字符串")

    @property
    def request_fields(self) -> str:
        fields = [getattr(self, attribute) for attribute in _MASTER_ATTRIBUTES]
        if self.wind_data_date is not None:
            fields.append(self.wind_data_date)
        return ",".join(fields)

    @property
    def required_attributes(self) -> tuple[str, ...]:
        return tuple(
            attribute
            for attribute in _MASTER_ATTRIBUTES
            if attribute not in self.optional_attributes
        )


class WindPyBondMasterProvider:
    """对一只确认非持仓债进行一次 WindPy 主数据请求。"""

    def __init__(
        self,
        *,
        gateway: WindGateway | None = None,
        field_map: WindFieldMap | None = None,
    ) -> None:
        self._gateway = gateway
        self._field_map = field_map

    def resolve(self, bond_code: str) -> MasterResolution:
        input_code = _normalize_input_code(bond_code)
        if input_code is None:
            return _missing("债券代码为空或非法")
        if self._field_map is None:
            return _missing("Wind 字段映射尚未通过连通性验收")

        gateway = self._gateway or self._load_production_gateway()
        if gateway is None:
            return _missing("WindPy 不可用")
        try:
            if _error_code(gateway.start()) != 0:
                return _missing("WindPy 启动失败")
            response = gateway.wss(
                input_code, self._field_map.request_fields, usedf=True
            )
        except Exception as exc:
            return _missing(f"Wind 请求失败: {type(exc).__name__}")

        error_code, raw_rows = _parse_wss_response(response)
        if error_code != 0:
            return _missing(f"Wind 返回错误码: {error_code}")
        if len(raw_rows) != 1:
            return _missing("Wind 主数据返回记录数不是 1")

        record = raw_rows[0]
        values = {
            attribute: _clean_value(record.get(getattr(self._field_map, attribute)))
            for attribute in _MASTER_ATTRIBUTES
        }
        missing = [
            attribute
            for attribute in self._field_map.required_attributes
            if values[attribute] is None
        ]
        if missing:
            return _missing(f"Wind 主数据缺少必填字段: {', '.join(missing)}")

        try:
            master = BondMaster(
                input_code=input_code,
                main_security_code=_normalize_main_security_code(
                    _as_text(values["main_security_code"])
                ),
                isin_code=_as_optional_text(values["isin_code"]),
                bond_name=_as_text(values["bond_name"]),
                issuer_name=_as_text(values["issuer_name"]),
                issuer_wind_code=_as_optional_text(values["issuer_wind_code"]),
                controller_name=_as_optional_text(values["controller_name"]),
                guarantor_name=_as_optional_text(values["guarantor_name"]),
                guarantor_wind_code=_as_optional_text(values["guarantor_wind_code"]),
                outstanding_balance_yi=_as_optional_finite_float(
                    values["outstanding_balance_yi"]
                ),
                bond_classification=_as_optional_text(values["bond_classification"]),
                bond_type=_as_optional_text(values["bond_type"]),
                issuer_type=_as_optional_text(values["issuer_type"]),
                is_city_investment_bond=_as_optional_text(
                    values["is_city_investment_bond"]
                ),
                bond_category=_as_optional_text(values["bond_category"]),
                wind_industry=_as_optional_text(values["wind_industry"]),
                province=_as_optional_text(values["province"]),
            )
        except (TypeError, ValueError) as exc:
            return _missing(f"Wind 主数据规范化失败: {exc}")
        if not master.main_security_code:
            return _missing("Wind 主数据缺少主证券代码")

        wind_data_date = None
        if self._field_map.wind_data_date is not None:
            wind_data_date = _as_optional_text(
                _clean_value(record.get(self._field_map.wind_data_date))
            )
        return MasterResolution(
            source=MasterSource.WIND,
            master=master,
            reason=None,
            wind_fetched_at=datetime.now(UTC),
            wind_data_date=wind_data_date,
        )

    @staticmethod
    def _load_production_gateway() -> WindGateway | None:
        try:
            from WindPy import w  # type: ignore[import-not-found]
        except Exception:
            return None
        return w


def _missing(reason: str) -> MasterResolution:
    return MasterResolution(
        source=MasterSource.MISSING_MASTER,
        master=None,
        reason=reason,
    )


def _normalize_input_code(value: object) -> str | None:
    normalized = _as_optional_text(_clean_value(value))
    return normalized.upper() if normalized is not None else None


def _normalize_main_security_code(value: str) -> str:
    return value.upper().split(".", maxsplit=1)[0].strip()


def _parse_wss_response(response: Any) -> tuple[int, list[Mapping[str, Any]]]:
    if isinstance(response, tuple) and len(response) == 2:
        error_code, frame = response
    else:
        error_code = getattr(response, "ErrorCode", None)
        frame = getattr(response, "Data", None)
    if _error_code(error_code) != 0:
        return _error_code(error_code), []
    if hasattr(frame, "to_dict"):
        records = frame.to_dict(orient="records")
    elif isinstance(frame, Mapping):
        records = [frame]
    elif isinstance(frame, list) and all(isinstance(row, Mapping) for row in frame):
        records = frame
    else:
        records = []
    return 0, list(records)


def _error_code(result: Any) -> int:
    value = getattr(result, "ErrorCode", result)
    if isinstance(value, bool):
        return 0 if value is False else 1
    try:
        return int(value)
    except (TypeError, ValueError):
        return 1


def _clean_value(value: Any) -> Any | None:
    if value is None:
        return None
    if isinstance(value, float) and isnan(value):
        return None
    if isinstance(value, str):
        value = value.strip()
        return None if value.lower() in {"", "nan", "none", "null", "nat"} else value
    return value


def _as_text(value: Any | None) -> str:
    normalized = _as_optional_text(value)
    if normalized is None:
        raise ValueError("文本字段为空")
    return normalized


def _as_optional_text(value: Any | None) -> str | None:
    value = _clean_value(value)
    return str(value).strip() if value is not None else None


def _as_optional_finite_float(value: Any | None) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("数值字段不是数字") from exc
    if not isfinite(numeric):
        raise ValueError("数值字段不是有限数")
    return numeric
