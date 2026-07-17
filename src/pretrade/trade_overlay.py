"""将交易前拟买行追加到共同内核的原始输入，不修改快照。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from math import isfinite

import pandas as pd

from src.risk_core import ProductionKernelInput
from src.risk_core.high_yield_capital_sources import (
    select_accounting_high_yield_capital_rows,
    select_penetration_high_yield_capital_rows,
)

from .service_models import MasterResolution, PretradeLine


_RAW_POSITION_DATASETS = (
    "债券持仓明细表",
    "债券持仓明细表_信用债",
    "债券持仓明细表_全量债券监管集中度",
)


class TradeOverlayError(ValueError):
    """无法安全地将拟买交易映射为生产原始输入。"""


class TradeOverlayBuilder:
    """副本追加器；不得修改输入快照，也不得重算任何限额规则。"""

    def build(
        self,
        inputs: ProductionKernelInput,
        lines: Sequence[PretradeLine],
        resolutions: Mapping[int, MasterResolution],
    ) -> ProductionKernelInput:
        if not isinstance(inputs, ProductionKernelInput):
            raise TypeError("inputs 必须是 ProductionKernelInput")
        frames = inputs.detached_frames()
        for dataset in _RAW_POSITION_DATASETS:
            if dataset not in frames:
                raise TradeOverlayError(f"共同内核缺少原始持仓输入: {dataset}")

        for line in lines:
            resolution = resolutions.get(line.line_id)
            if resolution is None:
                raise TradeOverlayError(f"输入行 {line.line_id} 缺少主数据解析结果")
            if resolution.master is None:
                continue
            master = resolution.master
            row = _position_row(inputs.business_date, line, master)
            for dataset in _RAW_POSITION_DATASETS:
                frames[dataset] = _append_row(frames[dataset], row)
            if line.full_price_cost_wan is not None:
                _append_high_yield_cost_rows(frames, inputs.business_date, line, master)

        return ProductionKernelInput(
            business_date=inputs.business_date,
            frames=frames,
            parameters=inputs.parameters,
        )


def _position_row(
    business_date: pd.Timestamp, line: PretradeLine, master
) -> dict[str, object]:
    code = _normalized_code(line.bond_code)
    asset_name = master.asset_name or master.bond_name
    main_security_name = master.main_security_name or master.bond_name
    return {
        "日期": business_date,
        "内部证券账户名称": line.account,
        "资产代码": code,
        "ISIN码": master.isin_code,
        "资产名称": asset_name,
        "债券分类2": master.bond_classification,
        "债券类型1": master.bond_type,
        "主证券代码": master.main_security_code,
        "主证券名称": main_security_name,
        "库存数量(万)_PR": line.pr_wan,
        "债券余额(亿)": master.outstanding_balance_yi,
        "发行人类型": master.issuer_type,
        "债务主体": master.issuer_name,
        "债务主体wind代码": master.issuer_wind_code,
        "实际控制人名称": master.controller_name,
        "实际控制人名称_修正": master.controller_name,
        "担保人": master.guarantor_name,
        "担保人wind代码": master.guarantor_wind_code,
        "是否城投债": master.is_city_investment_bond,
        "债券类别": master.bond_category,
        "wind行业": master.wind_industry,
        "省份": master.province,
        "合并辅助列": pd.NA,
    }


def _append_row(frame: pd.DataFrame, row: Mapping[str, object]) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame):
        raise TradeOverlayError("共同内核原始持仓输入不是 DataFrame")
    payload = {column: row.get(column, pd.NA) for column in frame.columns}
    return pd.concat(
        [frame.copy(deep=True), pd.DataFrame([payload], columns=frame.columns)],
        ignore_index=True,
    )


def _append_high_yield_cost_rows(
    frames: dict[str, pd.DataFrame],
    business_date: pd.Timestamp,
    line: PretradeLine,
    master,
) -> None:
    try:
        full_price_cost_wan = float(line.full_price_cost_wan)
    except (TypeError, ValueError) as exc:
        raise TradeOverlayError("拟买全价成本必须是有限数") from exc
    if not isfinite(full_price_cost_wan):
        raise TradeOverlayError("拟买全价成本必须是有限数")

    asset_name = master.asset_name or master.bond_name
    accounting_source = pd.DataFrame(
        [
            {
                "日期": business_date,
                "账户": line.account,
                "简称": asset_name,
                "代码": master.main_security_code,
                "持仓面额(元)": line.pr_wan * 10_000,
                "全价成本(元)": full_price_cost_wan * 10_000,
            }
        ]
    )
    accounting_rows = select_accounting_high_yield_capital_rows(
        accounting_source, frames.get("金融工具池设置")
    )
    if not accounting_rows.empty:
        current = frames.get("债券持仓表_核算系统")
        if current is not None:
            frames["债券持仓表_核算系统"] = pd.concat(
                [current.copy(deep=True), accounting_rows], ignore_index=True
            )

    penetrate_source = pd.DataFrame(
        [
            {
                "日期": business_date,
                "ISIN码": master.isin_code,
                "资产代码": _normalized_code(line.bond_code),
                "资产名称": asset_name,
                "内部证券账户名称": line.account,
                "库存数量(万)_PR": line.pr_wan,
                "本币成本": full_price_cost_wan * 10_000,
            }
        ]
    )
    penetration_rows = select_penetration_high_yield_capital_rows(
        penetrate_source, frames.get("穿透高收益债券")
    )
    if not penetration_rows.empty:
        current = frames.get("穿透高收益_投资本金规模")
        if current is not None:
            frames["穿透高收益_投资本金规模"] = pd.concat(
                [current.copy(deep=True), penetration_rows], ignore_index=True
            )


def _normalized_code(value: object) -> str:
    normalized = str(value).strip().upper()
    if not normalized:
        raise TradeOverlayError("债券代码为空")
    return normalized
