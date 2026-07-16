"""一揽子债券交易前超限试算页面：只调用共同交易前服务。"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from src.pretrade.pretrade_service import PretradeServiceError
from src.pretrade.result_adapter import BasketCheck
from src.visualization.components.controls import inject_compact_controls_css
from src.visualization.components.tables import render_data_table
from src.visualization.pretrade_presenter import (
    basket_lines_from_frame,
    basket_summary,
    dimension_frame,
)
from src.visualization.pretrade_service import get_pretrade_risk_service


_DEFAULT_ACCOUNT = "自营部交易性"
_INPUT_COLUMNS = ("债券代码", "拟买金额(万)_PR", "拟买入账户", "拟买全价成本(万)")


def _empty_basket() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "债券代码": "",
                "拟买金额(万)_PR": None,
                "拟买入账户": _DEFAULT_ACCOUNT,
                "拟买全价成本(万)": None,
            }
            for _ in range(5)
        ],
        columns=_INPUT_COLUMNS,
    )


def _render_title() -> None:
    st.markdown("## 🧺 一揽子债券交易前超限试算")
    st.caption("逐行录入债券、拟买金额和账户；共同内核会合并共享风险维度后判断交易结果。")


def _render_result(result: BasketCheck) -> None:
    summary = basket_summary(result)
    status = str(summary["总体状态"])
    if status == "已超限":
        st.error("总体状态：已超限")
    elif status == "不可计算":
        st.warning("总体状态：不可计算")
    else:
        st.success("总体状态：未超限")

    cards = st.columns(4)
    cards[0].metric("本次拟买总额", f"{float(summary['本次拟买总额(万)']):,.2f} 万元")
    cards[1].metric("超限维度", f"{summary['超限维度']} 个")
    cards[2].metric("不可计算维度", f"{summary['不可计算维度']} 个")
    cards[3].metric("限额快照日期", str(summary["快照日期"]))

    if result.line_reasons:
        for line_id, reason in sorted(result.line_reasons.items()):
            st.warning(f"输入第 {line_id} 行：{reason}")

    st.markdown("#### 整篮合并试算明细")
    table = dimension_frame(result.dimensions, remaining_label="交易后剩余(万)")
    render_data_table(
        table,
        height=min(620, 120 + len(table) * 38),
        highlight_column="状态",
        show_summary=False,
        enable_export=True,
        export_key="export_page10_pretrade_dimensions",
    )


def render(filters: dict[str, Any], data_loader: Any) -> None:
    """渲染篮子页面；参数保持既有应用路由兼容。"""

    del filters
    inject_compact_controls_css("_page10_compact_controls_css_injected")
    _render_title()

    if getattr(data_loader, "target_date", None) is not None:
        st.info("交易前试算仅支持已发布的最新交易前快照；请在侧边栏切换到「最新数据」。")
        return

    st.markdown("#### 交易清单")
    st.caption("高收益债券如触发年度全价成本限额，必须填写拟买全价成本；其余维度仍按 PR 口径计算。")
    edited = st.data_editor(
        _empty_basket(),
        key="page10_pretrade_lines",
        hide_index=True,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "债券代码": st.column_config.TextColumn("债券代码", width="medium"),
            "拟买金额(万)_PR": st.column_config.NumberColumn("拟买金额(万)_PR", format="%.2f"),
            "拟买入账户": st.column_config.TextColumn("拟买入账户", width="medium"),
            "拟买全价成本(万)": st.column_config.NumberColumn("拟买全价成本(万)｜高收益必填", format="%.2f"),
        },
    )

    calculate, clear = st.columns([4, 1])
    with calculate:
        calculate_clicked = st.button(
            "整体计算是否超限",
            type="primary",
            use_container_width=True,
            key="page10_pretrade_calculate",
        )
    with clear:
        if st.button("清空", use_container_width=True, key="page10_pretrade_clear"):
            st.session_state.pop("page10_pretrade_lines", None)
            st.session_state.pop("page10_pretrade_result", None)
            st.rerun()

    if calculate_clicked:
        try:
            lines = basket_lines_from_frame(edited)
            result = get_pretrade_risk_service().check_basket(lines)
        except (TypeError, ValueError, PretradeServiceError) as exc:
            st.session_state.pop("page10_pretrade_result", None)
            st.error(str(exc))
        except Exception as exc:
            st.session_state.pop("page10_pretrade_result", None)
            st.error(f"交易前服务暂不可用：{type(exc).__name__}: {exc}")
        else:
            st.session_state["page10_pretrade_result"] = result

    result = st.session_state.get("page10_pretrade_result")
    if result is None:
        st.info("录入至少一笔拟买交易后，点击「整体计算是否超限」。")
        return
    _render_result(result)
