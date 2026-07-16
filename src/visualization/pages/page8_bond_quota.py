"""单券交易前可购额度页面：只调用已发布交易前快照的共同服务。"""

from __future__ import annotations

from html import escape
from typing import Any

import pandas as pd
import streamlit as st

from src.pretrade.pretrade_service import PretradeServiceError
from src.pretrade.result_adapter import SingleBondQuote
from src.visualization.components.controls import inject_compact_controls_css
from src.visualization.components.tables import render_data_table
from src.visualization.pretrade_presenter import dimension_frame, single_quote_status
from src.visualization.pretrade_service import get_pretrade_risk_service


_DEFAULT_ACCOUNT = "自营部交易性"


def _format_wan(value: float | None) -> str:
    return "—" if value is None or pd.isna(value) else f"{float(value):,.2f} 万元"


def _card(label: str, value: str, caption: str = "", tone: str = "neutral") -> None:
    palette = {
        "neutral": ("#ffffff", "#e2e8f0", "#0f172a"),
        "success": ("#f0fdf4", "#bbf7d0", "#15803d"),
        "warning": ("#fffbeb", "#fde68a", "#b45309"),
        "danger": ("#fef2f2", "#fecaca", "#dc2626"),
    }[tone]
    background, border, color = palette
    st.markdown(
        f"""
        <div style="background:{background};border:1px solid {border};border-radius:10px;padding:16px;min-height:104px">
          <div style="font-size:0.72rem;color:#64748b;font-weight:600">{escape(label)}</div>
          <div style="font-size:1.65rem;line-height:1.25;font-weight:700;color:{color};margin-top:7px">{escape(value)}</div>
          <div style="font-size:0.75rem;color:#94a3b8;margin-top:5px">{escape(caption)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_title() -> None:
    st.markdown("## 🔎 单券可购额度查询")
    st.caption("指定债券代码和拟买入账户，基于已发布交易前快照查看 PR 可购上限。")


def _render_quote(quote: SingleBondQuote, *, bond_code: str, account: str) -> None:
    status = single_quote_status(quote)
    status_tone = "success" if status == "可计算" else "warning"
    cards = st.columns(4)
    with cards[0]:
        _card("PR 可购上限", _format_wan(quote.purchasable_pr_cap_wan), "共同内核交易前试算")
    with cards[1]:
        _card("结果状态", status, "交易前试算", status_tone)
    with cards[2]:
        _card("最紧约束", quote.binding_dimension or "—", "决定最终 PR 额度")
    with cards[3]:
        _card(
            "高收益年度全价成本剩余",
            _format_wan(quote.full_price_cost_remaining_wan),
            "独立于 PR 可购上限",
        )

    st.caption(
        f"债券：{bond_code} ｜ 拟买入账户：{account} ｜ 交易前快照：{quote.snapshot_data_date}"
    )
    if quote.purchasable_pr_cap_wan is None:
        st.warning("存在必需数据缺失，系统未给出最终可购额度；请查看下表原因。")

    st.markdown("#### 各维度交易前剩余额度")
    table = dimension_frame(quote.dimensions, remaining_label="交易前剩余(万)")
    render_data_table(
        table,
        height=min(560, 120 + len(table) * 38),
        highlight_column="状态",
        show_summary=False,
        enable_export=True,
        export_key="export_page8_pretrade_dimensions",
    )


def render(filters: dict[str, Any], data_loader: Any) -> None:
    """渲染单券页面；参数保持既有页面路由兼容。"""

    del filters
    inject_compact_controls_css("_page8_compact_controls_css_injected")
    _render_title()

    if getattr(data_loader, "target_date", None) is not None:
        st.info("交易前试算仅支持已发布的最新交易前快照；请在侧边栏切换到「最新数据」。")
        return

    with st.form("page8_pretrade_quote_form", clear_on_submit=False):
        code_column, account_column = st.columns(2)
        with code_column:
            bond_code = st.text_input(
                "债券代码",
                placeholder="例如：102480811.IB",
                key="page8_pretrade_bond_code",
            )
        with account_column:
            account = st.text_input(
                "拟买入账户",
                value=_DEFAULT_ACCOUNT,
                key="page8_pretrade_account",
            )
        submitted = st.form_submit_button("计算剩余额度", type="primary", use_container_width=True)

    if submitted:
        try:
            quote = get_pretrade_risk_service().quote_single_bond(bond_code, account)
        except (ValueError, PretradeServiceError) as exc:
            st.session_state.pop("page8_pretrade_quote", None)
            st.error(str(exc))
        except Exception as exc:
            st.session_state.pop("page8_pretrade_quote", None)
            st.error(f"交易前服务暂不可用：{type(exc).__name__}: {exc}")
        else:
            st.session_state["page8_pretrade_quote"] = (quote, bond_code.strip().upper(), account.strip())

    cached = st.session_state.get("page8_pretrade_quote")
    if cached is None:
        st.info("输入债券代码和拟买入账户后，点击「计算剩余额度」。")
        return
    quote, displayed_code, displayed_account = cached
    _render_quote(quote, bond_code=displayed_code, account=displayed_account)
