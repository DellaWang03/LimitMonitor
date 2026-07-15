from __future__ import annotations

from collections.abc import Mapping

import pandas as pd

from .contracts import (
    STAGE1_REQUIRED_FRAMES,
    STAGE2_REQUIRED_FRAMES,
    ProductionKernelInput,
    _copy_frame,
)
from .position_context import (
    attach_isin_to_results,
    build_credit_risk_context,
    normalize_bond_position,
    normalize_credit_position,
    normalize_regulatory_position,
)
from .stage1_aggregates import (
    calculate_single_bond_total_position,
    calculate_single_controller_total_position,
    calculate_single_issuer_total_position,
    calculate_specific_controller_total_position,
    calculate_specific_issuer_total_position,
    calculate_single_guarantee_total_position,
    calculate_single_guarantee_total_position_unfiltered,
)
from .stage1_limits import Stage1LimitEngine
from .stage2_limits import Stage2RiskEngine


class ProductionRiskKernel:
    """Pure orchestration shell populated incrementally by extraction tasks."""

    def run_stage1(self, inputs: ProductionKernelInput) -> dict[str, pd.DataFrame]:
        if not isinstance(inputs, ProductionKernelInput):
            raise TypeError("inputs must be ProductionKernelInput")
        frames = inputs.require_frames(STAGE1_REQUIRED_FRAMES)
        bond_position = normalize_bond_position(frames["债券持仓明细表"])
        credit_position = normalize_credit_position(frames["债券持仓明细表_信用债"])
        regulatory_position = normalize_regulatory_position(
            frames["债券持仓明细表_全量债券监管集中度"]
        )
        context_frames = dict(frames)
        context_frames["债券持仓明细表_信用债"] = credit_position
        credit_context = build_credit_risk_context(context_frames)
        results: dict[str, pd.DataFrame] = {
            "风控部债券池": _copy_frame(frames["风控部债券池"]),
            "风控部主体池": _copy_frame(frames["风控部主体池"]),
            "调整实控人名单": _copy_frame(frames["调整实控人名单"]),
            "发行人类型调整表": _copy_frame(frames["发行人类型调整表"]),
            "穿透高收益债券": _copy_frame(frames["穿透高收益债券"]),
            "债券持仓明细表": bond_position,
            "债券持仓明细表_信用债": credit_position,
            "债券持仓明细表_全量债券监管集中度": regulatory_position,
            "中债隐含评级AAA&AAA+": _copy_frame(frames["中债隐含评级AAA&AAA+"]),
            "单一债券规模限额": _copy_frame(frames["单一债券规模限额"]),
            "单一债券集中度限额": _copy_frame(frames["单一债券集中度限额"]),
            "特批单一债券限额": _copy_frame(frames["特批单一债券限额"]),
            "单一主体规模限额": _copy_frame(frames["单一主体规模限额"]),
            "单一实控人规模限额": _copy_frame(frames["单一实控人规模限额"]),
            "特定主体限额": _copy_frame(frames["特定主体限额"]),
            "特定实控人限额": _copy_frame(frames["特定实控人限额"]),
            "单一担保公司规模限额": _copy_frame(frames["单一担保公司规模限额"]),
            "债券持仓明细表_信用债_合并风险限额相关": credit_context,
        }
        results["单一债券总持仓"] = calculate_single_bond_total_position(
            credit_position
        )
        results["单一主体总持仓"] = calculate_single_issuer_total_position(
            credit_position
        )
        results["特定主体总持仓"] = calculate_specific_issuer_total_position(
            credit_position,
            frames["特定主体限额"],
            frames["穿透高收益债券"],
            frames["金融工具池设置"],
        )
        results["单一实控人总持仓"] = calculate_single_controller_total_position(
            credit_context
        )
        results["特定实控人总持仓"] = calculate_specific_controller_total_position(
            credit_context,
            frames["特定实控人限额"],
            frames["穿透高收益债券"],
            frames["金融工具池设置"],
        )

        engine_frames = dict(frames)
        engine_frames.update(results)
        limit_engine = Stage1LimitEngine(
            engine_frames,
            regulatory_concentration_limit=(
                inputs.parameters.regulatory_concentration_limit
            ),
        )

        def register(name: str, frame: pd.DataFrame) -> pd.DataFrame:
            results[name] = frame
            limit_engine.cache[name] = _copy_frame(frame)
            return frame

        register(
            "限额明细_特定主体",
            limit_engine.calculate_limit_detail_specific_issuer(),
        )
        register(
            "限额明细_特定实控人",
            limit_engine.calculate_limit_detail_specific_controller(),
        )
        register(
            "单一担保人总持仓",
            calculate_single_guarantee_total_position(
                limit_engine.cache["债券持仓明细表_信用债_合并风险限额相关"],
                limit_engine.cache.get("限额明细_特定主体"),
                limit_engine.cache.get("限额明细_特定实控人"),
                limit_engine.cache.get("单一主体规模限额"),
                limit_engine.cache.get("单一担保公司规模限额"),
                limit_engine.cache.get("穿透高收益债券"),
                limit_engine.cache.get("金融工具池设置"),
            ),
        )
        register(
            "单一担保人总持仓_不剔除",
            calculate_single_guarantee_total_position_unfiltered(
                limit_engine.cache.get("单一担保公司规模限额"),
                limit_engine.cache.get(
                    "债券持仓明细表_信用债_合并风险限额相关"
                ),
            ),
        )
        register(
            "限额明细_债券持仓明细表_信用债1_2",
            limit_engine.calculate_limit_detail_1_2(),
        )
        register(
            "限额明细_单一债券",
            limit_engine.calculate_limit_detail_single_bond(),
        )
        register(
            "限额明细_单一主体",
            limit_engine.calculate_limit_detail_single_issuer(),
        )
        register(
            "限额明细_单一实控人",
            limit_engine.calculate_limit_detail_single_controller(),
        )
        register(
            "限额明细_单一实控人_取最高额度",
            limit_engine.calculate_limit_detail_single_controller_max(),
        )
        register(
            "限额明细_单一担保人",
            limit_engine.calculate_limit_detail_single_guarantee(),
        )
        register(
            "限额明细_债券持仓明细表_信用债1_1",
            limit_engine.calculate_limit_detail_1_1(),
        )
        register(
            "限额明细_全量债券监管集中度",
            limit_engine.calculate_limit_detail_full_regulatory_concentration(),
        )
        return attach_isin_to_results(results, frames["ISIN码映射"])

    def run_stage2(
        self,
        inputs: ProductionKernelInput,
        stage1_tables: Mapping[str, pd.DataFrame],
    ) -> dict[str, pd.DataFrame]:
        if not isinstance(inputs, ProductionKernelInput):
            raise TypeError("inputs must be ProductionKernelInput")
        frames = inputs.require_frames(STAGE2_REQUIRED_FRAMES)
        if not isinstance(stage1_tables, Mapping):
            raise TypeError("stage1_tables must be a mapping of pandas DataFrame values")
        for name, frame in stage1_tables.items():
            if not isinstance(name, str) or not isinstance(frame, pd.DataFrame):
                raise TypeError("stage1_tables must map string keys to pandas DataFrame values")
            frames[name] = _copy_frame(frame)

        engine = Stage2RiskEngine(frames)
        results: dict[str, pd.DataFrame] = {
            "高风险行业": _copy_frame(frames["高风险行业"]),
            "高风险省份": _copy_frame(frames["高风险省份"]),
            "高风险限额": _copy_frame(frames["高风险限额"]),
            "地域集中度限额(含城投)": _copy_frame(
                frames["地域集中度限额(含城投)"]
            ),
            "金融工具池设置": _copy_frame(frames["金融工具池设置"]),
            "债券持仓明细表_信用债": _copy_frame(
                frames["债券持仓明细表_信用债"]
            ),
            "债券持仓明细表_信用债_合并风险限额相关": _copy_frame(
                frames["债券持仓明细表_信用债_合并风险限额相关"]
            ),
        }

        def register(name: str, method_name: str) -> pd.DataFrame:
            frame = getattr(engine, method_name)()
            results[name] = frame
            engine.cache[name] = _copy_frame(frame)
            return frame

        register("信用债总持仓", "query_total_credit_position")
        register("单一地域总持仓", "query_single_region_total_position")
        register("单一地域城投总持仓", "query_single_region_citybond_position")
        register("高风险行业总持仓", "query_high_risk_industry_position")
        register("高风险行业总持仓_2", "query_high_risk_industry_position_detail")
        register("高风险省份总持仓", "query_high_risk_province_position")
        register("高风险省份总持仓_2", "query_high_risk_province_position_detail")
        register("限额明细_债券持仓明细表_信用债2", "query_credit_bond_detail_2")
        register("限额明细_高风险行业", "query_high_risk_industry_detail")
        register("限额明细_高风险行业_2", "query_high_risk_industry_detail_2")
        register("限额明细_高风险省份", "query_high_risk_province_detail")
        register("限额明细_高风险省份2", "query_high_risk_province_detail_2")
        register(
            "限额明细_地域集中度限额(含城投)",
            "query_region_concentration_detail",
        )
        register("限额明细_高收益", "query_high_yield_detail")
        register("限额明细_高收益_投资本金规模", "query_high_yield_capital")
        return results
