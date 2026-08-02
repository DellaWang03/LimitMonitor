"""请求内执行与持仓底稿一致的 Wind Excel 主数据公式。"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
import csv
from dataclasses import dataclass
import platform
import re
from typing import Any, ContextManager, Mapping, Protocol

import pandas as pd


_PROVINCE_OVERRIDES = {
    "144212.SZ": "北京",
    "292680009.IB": "海外",
    "292480003.IB": "海外",
    "292480007.IB": "海外",
    "102582786.IB": "海外",
}


class FormulaEvaluator(Protocol):
    """在一个短生命周期 Excel 工作簿中计算一批公式。"""

    def evaluate(self, formulas: Mapping[str, str]) -> Mapping[str, Any]:
        raise NotImplementedError


@dataclass(frozen=True)
class InitialExcelValues:
    main_security_code: Any
    wind_industry: Any
    province: Any
    issuer_wind_code: Any = None
    guarantor_wind_code: Any = None


@dataclass(frozen=True)
class AnchorExcelValues:
    main_security_name: Any
    outstanding_balance_yi: Any


class ExcelWindMasterGateway:
    """将底稿的 Excel Wind 公式封装为无状态、可替换的请求边界。"""

    def __init__(self, evaluator: FormulaEvaluator | None = None) -> None:
        self._evaluator = evaluator or XlwingsFormulaEvaluator()

    def session(self) -> ContextManager[None]:
        """把连续多批公式收进同一个 Excel 应用生命周期。"""

        session = getattr(self._evaluator, "session", None)
        return session() if callable(session) else nullcontext()

    def resolve_initial(
        self,
        bond_code: str,
        *,
        issuer_name: str | None,
        guarantor_name: str | None,
    ) -> InitialExcelValues:
        normalized_code = _required_text(bond_code, "债券代码")
        formulas = {
            "main_security_code": _formula("b_info_anchorbond", normalized_code),
            "wind_industry": _formula("b_issuer_windindustry", normalized_code, 4),
        }
        province = _PROVINCE_OVERRIDES.get(normalized_code.upper())
        if province is None:
            formulas["province"] = _formula("s_info_province", normalized_code)
        if issuer_name is not None:
            formulas["issuer_wind_code"] = _formula("To_WindCode", issuer_name)
        if guarantor_name is not None:
            formulas["guarantor_wind_code"] = _formula("To_WindCode", guarantor_name)

        values = self._evaluator.evaluate(formulas)
        return InitialExcelValues(
            main_security_code=_source_value(values.get("main_security_code")),
            wind_industry=_source_value(values.get("wind_industry")),
            province=province if province is not None else _source_value(values.get("province")),
            issuer_wind_code=_source_value(values.get("issuer_wind_code")),
            guarantor_wind_code=_source_value(values.get("guarantor_wind_code")),
        )

    def resolve_anchor_attributes(
        self, main_security_code: str, business_date: pd.Timestamp
    ) -> AnchorExcelValues:
        normalized_code = _required_text(main_security_code, "主证券代码")
        date_text = pd.Timestamp(business_date).strftime("%Y-%m-%d")
        values = self._evaluator.evaluate(
            {
                "main_security_name": _formula("b_info_name", normalized_code),
                "outstanding_balance_yi": _formula(
                    "b_info_outstandingbalance", normalized_code, date_text
                ),
            }
        )
        return AnchorExcelValues(
            main_security_name=_source_value(values.get("main_security_name")),
            outstanding_balance_yi=_source_value(values.get("outstanding_balance_yi")),
        )


class XlwingsFormulaEvaluator:
    """生产 Excel 计算器：Windows 用 xlwings，macOS 用预写公式工作簿。"""

    @contextmanager
    def session(self) -> Iterator[None]:
        if platform.system() != "Darwin":
            # Windows 的 xlwings 路径每批自带 App 生命周期，保持不变。
            yield
            return
        from src.common.macos_wind_excel import excel_session

        with excel_session():
            yield

    def evaluate(self, formulas: Mapping[str, str]) -> Mapping[str, Any]:
        if not formulas:
            return {}
        if platform.system() == "Darwin":
            from src.common.macos_wind_excel import MacOSWindExcelFormulaRunner

            raw_values = MacOSWindExcelFormulaRunner().evaluate(
                [_macos_formula(formula) for formula in formulas.values()],
                labels=list(formulas.keys()),
            )
            return dict(zip(formulas, raw_values, strict=True))
        try:
            import xlwings as xw
        except ImportError as exc:  # pragma: no cover - 依赖生产 Windows 安装
            raise RuntimeError("未安装 xlwings 或 Excel Wind 环境") from exc

        app = None
        book = None
        try:  # pragma: no cover - 需 Windows Excel + Wind 的集成验证
            # 保持 Windows 已验证的生产行为不变。
            app = xw.App(visible=False, add_book=False)
            app.display_alerts = False
            book = app.books.add()
            sheet = book.sheets[0]
            target = sheet.range("A1").resize(len(formulas), 1)
            target.formula = [[formula] for formula in formulas.values()]
            app.calculate()
            raw_values = target.value
            if len(formulas) == 1:
                raw_values = [raw_values]
            return dict(zip(formulas, raw_values, strict=True))
        finally:
            if book is not None:
                book.close()
            if app is not None:
                app.quit()


def _formula(function_name: str, *arguments: object) -> str:
    rendered = ",".join(_formula_argument(argument) for argument in arguments)
    return f"={function_name}({rendered})"


def _formula_argument(value: object) -> str:
    if isinstance(value, str):
        return f'"{value.replace(chr(34), chr(34) * 2)}"'
    return str(value)


def _macos_formula(formula: str) -> str:
    """把 Windows 可直接调用的 Wind 字段函数转为 macOS Excel WSS 公式。"""

    match = re.fullmatch(r"=([A-Za-z][A-Za-z0-9_]*)\((.*)\)", formula)
    if match is None:
        return formula
    function_name = match.group(1)
    try:
        arguments = next(csv.reader([match.group(2)], skipinitialspace=True))
    except (csv.Error, StopIteration):
        return formula
    field_name = function_name.casefold()
    if field_name in {
        "b_info_anchorbond",
        "s_info_province",
        "b_info_name",
    } and len(arguments) == 1:
        return _formula("WSS", arguments[0], field_name)
    if field_name == "b_issuer_windindustry" and len(arguments) == 2:
        return _formula(
            "WSS",
            arguments[0],
            field_name,
            f"industryType={arguments[1]}",
        )
    if field_name == "b_info_outstandingbalance" and len(arguments) == 2:
        return _formula(
            "WSS",
            arguments[0],
            field_name,
            f"tradeDate={arguments[1]}",
        )
    return formula


def _source_value(value: Any) -> Any:
    """保留公式的显式 0，仅把 Excel 错误和空输出转为 None。"""

    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text or text.lower() in {"nan", "none", "null", "nat"}:
            return None
        if text.startswith("#"):
            return None
        return text
    if isinstance(value, float) and pd.isna(value):
        return None
    return value


def _required_text(value: object, field_name: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text:
        raise ValueError(f"{field_name}不能为空")
    return text
