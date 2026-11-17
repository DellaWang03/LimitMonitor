"""非持仓债的请求内 Wind 主数据适配器。

该模块只复现持仓底稿的原始字段来源；它不计算限额、不写数据库、不缓存
Wind 返回，也不修改日常 Stage0 的发行人代码解析器。
"""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from datetime import UTC, datetime
import importlib
import json
from math import isfinite, isnan
import os
from pathlib import Path
import subprocess
import sys
from threading import Lock
from typing import Any, ContextManager, Mapping, Protocol

import pandas as pd

from .master_derivations import (
    derive_bond_category,
    derive_classifications,
    derive_isin,
    derive_issuer_type,
)
from .service_models import (
    BondMaster,
    MasterResolution,
    MasterSource,
    missing_required_bond_master_fields,
)
from .wind_excel_master import ExcelWindMasterGateway


DEFAULT_WIND_FIELDS = (
    "SEC_NAME,ISIN_CODE,ISSUER,ISSUERUPDATED,"
    "AGENCY_GUARANTOR,WINDL1TYPE,WINDL2TYPE,NATURE1,MUNICIPALBONDWIND"
)
_WINDPY_PATH_ENV = "LIMIT_MONITOR_WINDPY_PATH"
_OFFICIAL_MACOS_WINDPY_PATH = Path("/Applications/Wind API.app/Contents/python")
_WINDPY_START_WAIT_SECONDS = 20
_WINDPY_START_LOCK = Lock()
_WINDPY_SUBPROCESS_TIMEOUT_SECONDS = 30
_WINDPY_WORKER_RESULT_PREFIX = "LIMIT_MONITOR_WINDPY_RESULT="
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_IS_MACOS = sys.platform == "darwin"


class WindGateway(Protocol):
    """WindPy 的最小可替换接口，避免导入时初始化 Wind。"""

    def start(self) -> Any:
        raise NotImplementedError

    def wss(self, bond_code: str, fields: str, *, usedf: bool) -> Any:
        raise NotImplementedError


@dataclass(frozen=True)
class _WindRawFields:
    asset_name: str
    isin_code: object
    issuer: str | None
    issuer_updated: str | None
    guarantor_name: str
    bond_type: str
    bond_type2: str
    nature1: str | None
    is_city_investment_bond: str | None


@dataclass(frozen=True)
class _WindQueryResult:
    error_code: int
    rows: list[Mapping[str, Any]]
    reason: str | None


class WindPyBondMasterProvider:
    """以一次 WindPy 原始字段请求和两批 Excel 公式构造一笔非持仓债。"""

    def __init__(
        self,
        *,
        gateway: WindGateway | None = None,
        excel_gateway: ExcelWindMasterGateway | None = None,
        issuer_wind_code_mapping: Mapping[str, str] | None = None,
        field_mapping_verified: bool = False,
    ) -> None:
        self._gateway = gateway
        self._excel = excel_gateway or ExcelWindMasterGateway()
        self._issuer_wind_code_mapping = dict(issuer_wind_code_mapping or {})
        self._field_mapping_verified = field_mapping_verified

    def master_session(self) -> ContextManager[None]:
        """让一次试算里的多笔非持仓债共用一个 Excel 应用生命周期。"""

        session = getattr(self._excel, "session", None)
        return session() if callable(session) else nullcontext()

    def resolve(
        self, bond_code: str, business_date: pd.Timestamp
    ) -> MasterResolution:
        input_code = _normalized_text(bond_code)
        if input_code is None:
            return _missing("债券代码为空或非法")
        if not self._field_mapping_verified:
            return _missing("Wind 字段映射尚未通过真实环境验收")

        if self._gateway is None and (_IS_MACOS or sys.platform == "win32"):
            query = _query_production_windpy_isolated(input_code)
            if query.reason is not None:
                return _missing(query.reason)
            error_code, rows = query.error_code, query.rows
        else:
            gateway = self._gateway or self._load_production_gateway()
            if gateway is None:
                return _missing("WindPy 不可用")
            try:
                if _start_gateway(gateway) != 0:
                    return _missing("WindPy 启动失败")
                response = gateway.wss(input_code, DEFAULT_WIND_FIELDS, usedf=True)
            except Exception as exc:
                return _missing(f"Wind 请求失败: {type(exc).__name__}")
            error_code, rows = _parse_wss_response(response)

        if error_code != 0:
            return _missing(f"Wind 返回错误码: {error_code}")
        if len(rows) != 1:
            return _missing("Wind 主数据返回记录数不是 1")

        raw, reason = _parse_raw_fields(rows[0])
        if raw is None:
            return _missing(reason or "Wind 主数据缺少结构性字段")

        issuer_name = raw.issuer if raw.bond_type2 == "资产支持证券" else raw.issuer_updated
        if issuer_name is None:
            return _missing("Wind 主数据缺少债务主体")

        mapped_issuer_code = _source_text(
            self._issuer_wind_code_mapping.get(issuer_name)
        )
        excel_issuer_name = None if mapped_issuer_code is not None else issuer_name
        excel_guarantor_name = (
            None if raw.guarantor_name == "0" else raw.guarantor_name
        )
        # 主证券属性依赖上一批公式解析出的主证券代码，两批无法合并；但共用
        # 一个会话可以让这两批只启停一次 Excel。
        with self.master_session():
            try:
                initial = self._excel.resolve_initial(
                    input_code,
                    issuer_name=excel_issuer_name,
                    guarantor_name=excel_guarantor_name,
                )
            except Exception as exc:
                return _missing(f"Excel Wind 主数据请求失败: {type(exc).__name__}")

            main_security_code = _source_text(initial.main_security_code)
            if main_security_code is None or main_security_code == "0":
                return _missing("Wind Excel 主数据缺少主证券代码")
            issuer_wind_code = (
                mapped_issuer_code
                if mapped_issuer_code is not None
                else _source_text(initial.issuer_wind_code)
            )
            if issuer_wind_code is None:
                return _missing("Wind Excel 主数据缺少债务主体wind代码")

            try:
                anchor = self._excel.resolve_anchor_attributes(
                    main_security_code, pd.Timestamp(business_date)
                )
            except Exception as exc:
                return _missing(
                    f"Excel Wind 主证券属性请求失败: {type(exc).__name__}"
                )

        base_classification, bond_classification = derive_classifications(raw.bond_type2)
        if bond_classification == "利率债":
            # 生产共同内核在信用债位置标准化时剔除利率债；现有地方
            # 政府债的发行人类型/实控人仅为占位，不参与信用维度。
            issuer_type = None
        else:
            if raw.nature1 is None:
                return _missing("Wind 主数据缺少发行人类型原始值")
            issuer_type = derive_issuer_type(raw.nature1)
        wind_industry = _source_text(initial.wind_industry)
        city_investment = raw.is_city_investment_bond
        bond_category = derive_bond_category(
            base_classification,
            city_investment or "",
            wind_industry or "",
            issuer_type or "",
        )
        try:
            master = BondMaster(
                input_code=input_code,
                main_security_code=main_security_code,
                isin_code=derive_isin(input_code, raw.isin_code),
                bond_name=raw.asset_name,
                issuer_name=issuer_name,
                issuer_wind_code=issuer_wind_code,
                controller_name=None,  # 试算入口从同一持仓快照解析，不向 Wind 取值。
                guarantor_name=raw.guarantor_name,
                guarantor_wind_code=_guarantor_code(
                    raw.guarantor_name, initial.guarantor_wind_code
                ),
                outstanding_balance_yi=_finite_float(anchor.outstanding_balance_yi),
                bond_classification=bond_classification,
                bond_type=raw.bond_type,
                issuer_type=issuer_type,
                is_city_investment_bond=city_investment,
                bond_category=bond_category,
                wind_industry=wind_industry,
                province=_source_text(initial.province),
                asset_name=raw.asset_name,
                main_security_name=_source_text(anchor.main_security_name),
            )
        except (TypeError, ValueError) as exc:
            return _missing(f"Wind 主数据规范化失败: {exc}")
        missing = missing_required_bond_master_fields(master, require_controller=False)
        if missing:
            return _missing(f"Wind 主数据缺少必填字段: {', '.join(missing)}")
        return MasterResolution(
            source=MasterSource.WIND,
            master=master,
            reason=None,
            wind_fetched_at=datetime.now(UTC),
            wind_data_date=pd.Timestamp(business_date).date().isoformat(),
        )

    @staticmethod
    def _load_production_gateway() -> WindGateway | None:
        module = _import_windpy()
        return getattr(module, "w", None) if module is not None else None


def _start_gateway(gateway: WindGateway) -> int:
    """启动同一进程内的 WindPy 会话，避免并发登录框无限等待。"""

    with _WINDPY_START_LOCK:
        is_connected = getattr(gateway, "isconnected", None)
        if callable(is_connected) and is_connected():
            return 0
        try:
            result = gateway.start(waitTime=_WINDPY_START_WAIT_SECONDS)
        except TypeError:
            # 测试或其它兼容网关可能只实现无参 start；生产 WindPy 支持
            # waitTime，必须走上面的有界调用。
            result = gateway.start()
    return _error_code(result)


def _query_production_windpy_isolated(bond_code: str) -> _WindQueryResult:
    """在独立进程主线程执行生产 WindPy，并由父进程提供硬超时。"""

    command = (
        sys.executable,
        "-m",
        "src.pretrade.windpy_worker",
        bond_code,
    )
    try:
        completed = subprocess.run(
            command,
            cwd=_PROJECT_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            check=False,
            timeout=_WINDPY_SUBPROCESS_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return _WindQueryResult(
            1,
            [],
            f"Wind 请求超时（{_WINDPY_SUBPROCESS_TIMEOUT_SECONDS}秒）",
        )
    except UnicodeError:
        return _WindQueryResult(1, [], "Wind 子进程返回的文本编码无效")
    except OSError as exc:
        return _WindQueryResult(
            1,
            [],
            f"Wind 子进程启动失败: {type(exc).__name__}",
        )

    payload = _parse_worker_payload(completed.stdout)
    if payload is None:
        return _WindQueryResult(
            1,
            [],
            f"Wind 子进程未返回有效结果（退出码: {completed.returncode}）",
        )

    error_code = _error_code(payload.get("error_code"))
    reason = _source_text(payload.get("reason"))
    raw_rows = payload.get("rows")
    if not isinstance(raw_rows, list) or not all(
        isinstance(row, Mapping) for row in raw_rows
    ):
        return _WindQueryResult(1, [], "Wind 子进程返回的数据结构无效")
    if completed.returncode != 0 and reason is None:
        reason = f"Wind 子进程失败（退出码: {completed.returncode}）"
    return _WindQueryResult(error_code, list(raw_rows), reason)


def _parse_worker_payload(stdout: str) -> Mapping[str, Any] | None:
    for line in reversed(stdout.splitlines()):
        if not line.startswith(_WINDPY_WORKER_RESULT_PREFIX):
            continue
        try:
            payload = json.loads(line[len(_WINDPY_WORKER_RESULT_PREFIX) :])
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, Mapping) else None
    return None


def _parse_raw_fields(record: Mapping[str, Any]) -> tuple[_WindRawFields | None, str | None]:
    asset_name = _source_text(record.get("SEC_NAME"))
    bond_type = _source_text(record.get("WINDL1TYPE"))
    bond_type2 = _source_text(record.get("WINDL2TYPE"))
    nature1 = _source_text(record.get("NATURE1"))
    if asset_name is None:
        return None, "Wind 主数据缺少资产名称"
    if bond_type is None:
        return None, "Wind 主数据缺少债券类型1"
    if bond_type2 is None:
        return None, "Wind 主数据缺少债券类型2"
    # 底稿 b_agency_guarantor 的无担保输出为 0；WSS 的空输出在此处同义化。
    guarantor_name = _source_text(record.get("AGENCY_GUARANTOR")) or "0"
    return (
        _WindRawFields(
            asset_name=asset_name,
            isin_code=record.get("ISIN_CODE"),
            issuer=_source_text(record.get("ISSUER")),
            issuer_updated=_source_text(record.get("ISSUERUPDATED")),
            guarantor_name=guarantor_name,
            bond_type=bond_type,
            bond_type2=bond_type2,
            nature1=nature1,
            is_city_investment_bond=_source_text(record.get("MUNICIPALBONDWIND")),
        ),
        None,
    )


def _guarantor_code(guarantor_name: str, value: object) -> str | None:
    if guarantor_name == "0":
        return None
    code = _source_text(value)
    # 底稿的 IF(To_WindCode(担保人)=0, "", To_WindCode(担保人)) 明确把 0 置空。
    return None if code in {None, "0"} else code


def _import_windpy() -> Any | None:
    """加载官方 WindPy，不触发登录或数据请求。"""

    try:
        return importlib.import_module("WindPy")
    except Exception:
        pass

    for directory in _windpy_search_paths():
        if not directory.is_dir():
            continue
        directory_text = str(directory)
        if directory_text not in sys.path:
            sys.path.insert(0, directory_text)
        try:
            return importlib.import_module("WindPy")
        except Exception:
            continue
    return None


def _windpy_search_paths() -> tuple[Path, ...]:
    configured = os.environ.get(_WINDPY_PATH_ENV, "").strip()
    candidates = [
        *( [Path(configured).expanduser()] if configured else [] ),
        _OFFICIAL_MACOS_WINDPY_PATH,
    ]
    return tuple(dict.fromkeys(candidates))


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


def _normalized_text(value: object) -> str | None:
    text = _source_text(value)
    return text.upper() if text is not None else None


def _source_text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and isnan(value):
        return None
    text = str(value).strip()
    return text if text and text.lower() not in {"nan", "none", "null", "nat"} else None


def _finite_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("债券余额不是数值") from exc
    if not isfinite(number):
        raise ValueError("债券余额不是有限数")
    return number


def _missing(reason: str) -> MasterResolution:
    return MasterResolution(
        source=MasterSource.MISSING_MASTER,
        master=None,
        reason=reason,
    )
