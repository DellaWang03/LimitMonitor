"""单券交易前可购额度页面：只调用已发布交易前快照的共同服务。"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from src.pretrade.pretrade_service import PretradeServiceError
from src.pretrade.result_adapter import DimensionResult, SingleBondQuote
from src.visualization.components.controls import (
    render_metric_card,
    render_vertical_space,
)
from src.visualization.components.pretrade_ui import (
    KPI_CARD_MIN_HEIGHT,
    SERVICE_UNAVAILABLE_MESSAGE,
    SNAPSHOT_UNAVAILABLE_MESSAGE,
    account_options,
    inject_pretrade_ui_css,
    render_pretrade_header,
    render_pretrade_status,
    rewrite_explanation_column,
    user_facing_input_message,
)
from src.visualization.components.tables import render_data_table
from src.visualization.pretrade_presenter import (
    business_dimension_frame,
    business_line_audit_frame,
    single_quote_status,
)
from src.visualization.pretrade_service import get_pretrade_risk_service


_DEFAULT_ACCOUNT = "自营部交易性"


def _format_wan(value: float | None) -> str:
    return "—" if value is None or pd.isna(value) else f"{float(value):,.2f} 万元"


def _wan_card_text(value: float | None) -> tuple[str, str]:
    """金额指标按展示页惯例拆成「数值」与「单位」两行。"""

    if value is None or pd.isna(value):
        return "—", "万元"
    return f"{float(value):,.2f}", "万元"


def _limit_card_text(value: float | None, unit: str | None) -> tuple[str, str]:
    if value is None or pd.isna(value):
        return "—", "适用限额"
    if unit == "比例":
        return f"{float(value) * 100:.2f}%", "适用限额"
    return f"{float(value):,.2f}", unit or "适用限额"


def _render_title() -> None:
    cached = st.session_state.get("page8_pretrade_quote")
    snapshot_data_date = (
        str(cached.snapshot_data_date) if cached is not None else None
    )
    render_pretrade_header(
        icon="🔍",
        title="单券可购额度查询",
        description="输入债券与账户，查看当前交易前快照下的 PR 可购上限及关键风险约束。",
        snapshot_data_date=snapshot_data_date,
    )


def _status_content(quote: SingleBondQuote) -> tuple[str, str, str]:
    status = single_quote_status(quote)
    if status == "已超限":
        return (
            "danger",
            "已超限，请调整交易安排",
            "已有必检风险维度超过限额。请在「风险约束」中查看具体维度与原因。",
        )
    if status == "不可计算":
        return (
            "warning",
            "不可计算，暂不能给出可购建议",
            "必需数据或计算条件不完整。系统未将缺失值按 0 处理，请在「数据说明」中查看原因。",
        )
    if (
        quote.purchasable_pr_cap_wan is not None
        and quote.purchasable_pr_cap_wan <= 0
    ):
        return (
            "warning",
            "未超限，当前可购额度为 0",
            "当前持仓尚未形成已超限结论，但最紧风险约束已没有新增交易空间。",
        )
    return (
        "success",
        "未超限，可继续评估交易",
        "全部必检风险维度均未形成超限结论；实际拟买金额不得超过下方 PR 可购上限。",
    )


def _binding_result(quote: SingleBondQuote) -> DimensionResult | None:
    if not quote.binding_dimension:
        return None
    return next(
        (
            item
            for item in quote.dimensions
            if item.name == quote.binding_dimension
        ),
        None,
    )


def _render_status(quote: SingleBondQuote) -> None:
    tone, title, description = _status_content(quote)
    render_pretrade_status(
        eyebrow="交易前结论",
        title=title,
        description=description,
        tone=tone,
    )


def _render_quote(quote: SingleBondQuote) -> None:
    _render_status(quote)
    binding = _binding_result(quote)

    cap_value, cap_caption = _wan_card_text(quote.purchasable_pr_cap_wan)
    used_value, used_caption = _wan_card_text(
        binding.current_used_wan if binding else None
    )
    limit_value, limit_caption = _limit_card_text(
        binding.limit_value if binding else None,
        binding.limit_unit if binding else None,
    )

    cards = st.columns(4)
    with cards[0]:
        render_metric_card(
            "PR 可购上限",
            cap_value,
            cap_caption,
            "accent" if quote.purchasable_pr_cap_wan is not None else "neutral",
            min_height=KPI_CARD_MIN_HEIGHT,
        )
    with cards[1]:
        render_metric_card(
            "最紧风险约束",
            quote.binding_dimension or "—",
            "当前约束",
            min_height=KPI_CARD_MIN_HEIGHT,
        )
    with cards[2]:
        render_metric_card(
            "当前占用",
            used_value,
            used_caption,
            min_height=KPI_CARD_MIN_HEIGHT,
        )
    with cards[3]:
        render_metric_card(
            "风险限额",
            limit_value,
            limit_caption,
            min_height=KPI_CARD_MIN_HEIGHT,
        )

    render_vertical_space(24)

    constraints_tab, data_tab = st.tabs(["风险约束", "数据说明"])
    with constraints_tab:
        st.markdown("#### 全部风险维度")
        st.caption("按已超限、不可计算、未超限、不适用排序；金额单位均为万元。")
        table = rewrite_explanation_column(
            business_dimension_frame(
                quote.dimensions,
                remaining_label="交易前剩余额度（万元）",
            ),
            "说明",
        )
        render_data_table(
            table,
            height=min(620, 120 + len(table) * 38),
            highlight_column="状态",
            show_summary=False,
            enable_export=True,
            export_key="export_page8_pretrade_dimensions",
        )
        if quote.full_price_cost_remaining_wan is not None:
            st.caption(
                "高收益年度全价成本剩余："
                f"{_format_wan(quote.full_price_cost_remaining_wan)}"
                "（独立于 PR 可购上限）"
            )

    with data_tab:
        st.markdown("#### 主数据与快照")
        st.caption("展示本次查询实际采用的数据来源和数据日期，不展示系统内部技术字段。")
        audit_table = rewrite_explanation_column(
            business_line_audit_frame(
                quote.line_audits,
                snapshot_data_date=quote.snapshot_data_date,
            ),
            "说明",
        )
        render_data_table(
            audit_table,
            height=min(320, 120 + len(audit_table) * 38),
            highlight_column="主数据状态",
            show_summary=False,
            enable_export=False,
        )
        with st.expander("口径说明"):
            st.markdown(
                """
                - **PR 可购上限**：本次查询时点下，该债券在该账户可新增的 PR 上限。
                - **最紧风险约束**：全部可计算且适用的 PR 风险维度中，剩余额度最小的维度。
                - **不可计算**：必需数据或计算条件不完整，不代表未超限，也不会按 0 处理。
                - **高收益年度全价成本剩余**：独立于 PR 可购上限，仅在债券适用高收益限额时提供。
                """
            )


def render(filters: dict[str, Any], data_loader: Any) -> None:
    """渲染单券页面；参数保持既有页面路由兼容。"""

    del filters
    inject_pretrade_ui_css()
    _render_title()

    if getattr(data_loader, "target_date", None) is not None:
        st.info("交易前试算仅支持已发布的最新交易前快照；请在侧边栏切换到「最新数据」。")
        return

    try:
        service = get_pretrade_risk_service()
        accounts = account_options(service, default_account=_DEFAULT_ACCOUNT)
    except PretradeServiceError:
        st.error(SNAPSHOT_UNAVAILABLE_MESSAGE)
        return

    st.markdown("#### 查询条件")
    with st.form(
        "page8_pretrade_quote_form",
        clear_on_submit=False,
        border=False,
    ):
        code_column, account_column, button_column = st.columns(
            [2.8, 2.8, 1.4],
            vertical_alignment="bottom",
        )
        with code_column:
            bond_code = st.text_input(
                "债券代码",
                placeholder="例如：1980082.IB",
                key="page8_pretrade_bond_code",
            )
        with account_column:
            account = st.selectbox(
                "拟买账户",
                accounts,
                key="page8_pretrade_account",
                help="仅可选择当前交易前快照中实际存在的账户",
            )
        with button_column:
            submitted = st.form_submit_button(
                "查询可购额度",
                type="primary",
                width="stretch",
            )

    if submitted:
        try:
            with st.spinner("正在读取限额快照并计算风险，请稍候"):
                quote = service.quote_single_bond(
                    bond_code,
                    account,
                )
        except PretradeServiceError:
            st.session_state.pop("page8_pretrade_quote", None)
            st.error(SNAPSHOT_UNAVAILABLE_MESSAGE)
        except ValueError as exc:
            st.session_state.pop("page8_pretrade_quote", None)
            st.error(user_facing_input_message(str(exc)))
        except Exception:
            st.session_state.pop("page8_pretrade_quote", None)
            st.error(SERVICE_UNAVAILABLE_MESSAGE)
        else:
            st.session_state["page8_pretrade_quote"] = quote
            st.rerun()

    cached = st.session_state.get("page8_pretrade_quote")
    if cached is None:
        st.info("输入债券代码和拟买账户后，点击「查询可购额度」。")
        return

    render_vertical_space(8)
    _render_quote(cached)
