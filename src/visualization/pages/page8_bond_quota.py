"""
页面8：单券可购额度查询 - 输入债券代码或名称，展示剩余可购额度。
"""
from html import escape
from textwrap import dedent
from typing import Any

import pandas as pd
import streamlit as st

from src.visualization.bond_quota_query import query_bond_remaining_quota
from src.visualization.components.controls import inject_compact_controls_css
from src.visualization.components.tables import render_data_table

if hasattr(st, "fragment"):
    _fragment = st.fragment
else:
    def _fragment(func):
        return func

COLOR_CARD_BG = "#ffffff"
COLOR_BORDER = "#e2e8f0"
COLOR_TEXT = "#1e293b"
COLOR_TITLE = "#0f172a"
COLOR_LABEL = "#64748b"
COLOR_MUTED = "#94a3b8"
COLOR_SUCCESS = "#22c55e"
COLOR_SUCCESS_BG = "#f0fdf4"
COLOR_SUCCESS_BORDER = "#bbf7d0"
COLOR_DANGER = "#ef4444"
COLOR_DANGER_BG = "#fef2f2"
COLOR_DANGER_BORDER = "#fecaca"
COLOR_SELECTED_BG = "#eff6ff"
COLOR_SELECTED_BORDER = "#3b82f6"


def _html(markup: str) -> None:
    st.markdown(dedent(markup).strip(), unsafe_allow_html=True)


def _request_query() -> None:
    st.session_state["page8_query_requested"] = True


def _build_query_cache_key(query_text: str, data_loader) -> tuple[str, str, str]:
    snapshot_date = getattr(data_loader, "data_date_str", None)
    target_date = getattr(data_loader, "target_date", None)
    if snapshot_date is None and hasattr(target_date, "isoformat"):
        snapshot_date = target_date.isoformat()
    snapshot_version = getattr(data_loader, "_snapshot_version", None) or getattr(data_loader, "data_source", "")
    return (str(query_text or "").strip(), str(snapshot_date or ""), str(snapshot_version or ""))


def _inject_page8_css() -> None:
    # Streamlit rebuilds the DOM on every rerun, so page-level styles must be
    # emitted every time. Otherwise widgets outside the query form can trigger a
    # rerun and leave the custom result cards unstyled.
    _html(
        """
        <style>
          .page8-card-value {
            overflow-wrap: anywhere;
          }
          .page8-card-subtext {
            overflow-wrap: anywhere;
          }
        </style>
        """,
    )


def _display_value(value: Any) -> Any:
    if value is None or pd.isna(value):
        return "—"
    return value


def _format_wan(value: Any) -> str:
    if value is None or pd.isna(value):
        return "—"
    try:
        return f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return str(value)


def _pick_bond_info(common_bond_info: dict) -> dict:
    fields = ["代码", "资产名称", "债务主体", "日期"]
    return {field: common_bond_info.get(field) for field in fields if common_bond_info.get(field) not in (None, "")}


def _render_dashboard_card(
    *,
    label: str,
    value: Any,
    unit: str = "",
    bg: str = COLOR_CARD_BG,
    border: str = COLOR_BORDER,
    value_color: str = COLOR_TEXT,
    value_size: str = "1.75rem",
) -> None:
    unit_html = (
        f'<p class="page8-card-subtext" style="font-size: 0.75rem; color: {COLOR_MUTED}; margin: 4px 0 0 0;">{escape(unit)}</p>'
        if unit
        else ""
    )
    _html(
        f"""
        <div style="background: {bg}; border: 1px solid {border}; border-radius: 12px; padding: 20px; min-height: 112px;">
            <p style="font-size: 0.7rem; color: {COLOR_LABEL}; text-transform: uppercase; letter-spacing: 0.5px; margin: 0 0 8px 0;">{escape(label)}</p>
            <p class="page8-card-value" style="font-size: {value_size}; font-weight: 700; line-height: 1.18; color: {value_color}; margin: 0;">{escape(str(_display_value(value)))}</p>
            {unit_html}
        </div>
        """,
    )


def _render_bond_info(common_bond_info: dict) -> None:
    info = _pick_bond_info(common_bond_info)
    if not info:
        return

    st.markdown("#### 债券信息")
    cols = st.columns(min(4, len(info)) or 1)
    for index, (label, value) in enumerate(info.items()):
        with cols[index % len(cols)]:
            _render_dashboard_card(label=label, value=value, value_size="1.05rem")


def _render_account_cards(account_summary: list[dict], selected_account_name: str | None) -> None:
    if not account_summary:
        return

    title = "分账户可购额度" if len(account_summary) > 1 else "账户可购额度"
    st.markdown(f"#### {title}")
    cols = st.columns(min(3, len(account_summary)))
    for index, item in enumerate(account_summary):
        account_name = str(item.get("内部证券账户名称") or "未识别账户")
        quota = float(item.get("最终可购额度(万)") or 0.0)
        limiting = str(item.get("限制维度") or "—")
        is_selected = account_name == selected_account_name
        is_available = quota > 0 and item.get("是否存在超限维度") != "是"

        border = COLOR_SELECTED_BORDER if is_selected else (
            COLOR_SUCCESS_BORDER if is_available else COLOR_DANGER_BORDER
        )
        bg = COLOR_SELECTED_BG if is_selected else (COLOR_SUCCESS_BG if is_available else COLOR_DANGER_BG)
        value_color = COLOR_SUCCESS if is_available else COLOR_DANGER
        suffix = " · 当前查看" if is_selected else ""

        with cols[index % len(cols)]:
            _render_dashboard_card(
                label=account_name + suffix,
                value=_format_wan(quota),
                unit=f"万元｜最紧约束：{limiting}",
                bg=bg,
                border=border,
                value_color=value_color,
                value_size="1.75rem",
            )


def _resolve_selected_account_name(account_results: list[dict], fallback_account_name: str | None) -> str | None:
    if not account_results:
        return fallback_account_name

    account_options = [item["account_name"] for item in account_results]
    selected_account_name = st.session_state.get("page8_selected_account") or fallback_account_name
    if selected_account_name not in account_options:
        selected_account_name = account_options[0]
        st.session_state["page8_selected_account"] = selected_account_name
    return selected_account_name


def _select_account_result(
    account_results: list[dict],
    selected_account_name: str | None,
) -> dict:
    if len(account_results) <= 1:
        return account_results[0]

    account_options = [item["account_name"] for item in account_results]
    selected_account_name = _resolve_selected_account_name(account_results, selected_account_name)
    default_index = account_options.index(selected_account_name) if selected_account_name in account_options else 0

    st.markdown("#### 查看账户")
    if len(account_options) <= 3:
        selected_account = st.segmented_control(
            "查看账户",
            account_options,
            default=account_options[default_index],
            key="page8_selected_account",
            label_visibility="collapsed",
        )
        selected_account = selected_account or account_options[default_index]
    else:
        selected_account = st.selectbox(
            "查看账户",
            account_options,
            index=default_index,
            key="page8_selected_account",
        )
    return next(item for item in account_results if item["account_name"] == selected_account)


def _build_dimension_table(dimensions: list[dict], public_dimensions: list[str]) -> pd.DataFrame:
    if not dimensions:
        return pd.DataFrame(columns=["维度名称", "剩余额度(万)", "是否超限", "适用范围"])

    dim_df = pd.DataFrame(dimensions).copy()
    dim_df["适用范围"] = dim_df["维度名称"].apply(
        lambda value: "全账户" if value in public_dimensions else "当前账户"
    )
    dim_df["剩余额度(万)"] = dim_df["剩余额度(万)"].apply(
        lambda value: "不适用" if value is None or pd.isna(value) else _format_wan(value)
    )
    dim_df["是否超限"] = dim_df["是否超限"].fillna("不适用")
    return dim_df[["维度名称", "剩余额度(万)", "是否超限", "适用范围"]]


def _render_result_summary(selected_result: dict, quota_wan: float, account_name: str | None) -> None:
    account_text = account_name or "不区分账户"
    limiting_text = "、".join(selected_result.get("limiting_dimensions") or []) or "—"
    st.caption(
        f"当前口径：{account_text} ｜ 可购剩余额度：{_format_wan(quota_wan)} 万元 ｜ 最紧约束：{limiting_text}"
    )


def _render_query_result(result: dict) -> None:
    data_health = result.get("data_health") or {}
    if result.get("error"):
        st.error(result["error"])
        health_errors = data_health.get("errors") or []
        if health_errors:
            for item in health_errors:
                st.write(f"- {item}")
        return

    if result.get("message") and result.get("candidates"):
        st.warning(result["message"])
        candidate_df = pd.DataFrame(result["candidates"])
        candidate_columns = ["资产代码", "主证券代码_标准", "ISIN码", "资产名称", "债务主体"]
        candidate_df = candidate_df[[col for col in candidate_columns if col in candidate_df.columns]]
        render_data_table(
            candidate_df,
            title="候选债券",
            height=min(420, 120 + len(candidate_df) * 40),
            show_summary=True,
            enable_export=True,
            export_key="export_page8_candidates",
        )
        return

    health_warnings = data_health.get("warnings") or []
    for item in health_warnings:
        st.warning(item)

    common_bond_info = result.get("common_bond_info") or result.get("bond_info", {})
    account_results = result.get("account_results", [])
    account_summary = result.get("account_summary", [])
    bond_level_result = result.get("bond_level_result")
    final_quota_wan = float(result.get("final_quota_wan", 0.0) or 0.0)
    selected_account_name = result.get("selected_account_name")
    result_scope = result.get("result_scope", "account")
    public_dimensions = result.get("public_dimensions", [])

    if result_scope == "account" and not account_results:
        st.warning("未找到可展示的账户结果。")
        return
    if result_scope == "bond" and not bond_level_result:
        st.warning("未找到可展示的债券结果。")
        return

    if result_scope == "account" and len(account_results) > 1:
        selected_account_name = _resolve_selected_account_name(account_results, selected_account_name)

    selected_result = bond_level_result if result_scope == "bond" else account_results[0]

    _render_bond_info(common_bond_info)
    _html("<div style='height: 24px;'></div>")

    if result_scope == "account" and len(account_results) > 1:
        _render_account_cards(account_summary, selected_account_name)
        _html("<div style='height: 24px;'></div>")
        selected_result = _select_account_result(account_results, selected_account_name)
        _html("<div style='height: 24px;'></div>")
    elif result_scope == "account":
        _render_account_cards(account_summary, selected_result.get("account_name"))
        _html("<div style='height: 24px;'></div>")

    selected_quota = float(selected_result.get("final_quota_wan", final_quota_wan) or 0.0)
    selected_account = selected_result.get("account_name") if result_scope == "account" else None
    st.markdown("#### 各维度剩余额度")
    _render_result_summary(selected_result, selected_quota, selected_account)
    dimension_df = _build_dimension_table(selected_result.get("dimensions", []), public_dimensions)
    render_data_table(
        dimension_df,
        height=min(520, 120 + len(dimension_df) * 38),
        highlight_column="是否超限",
        show_summary=False,
        enable_export=False,
    )


def _render_page_title() -> None:
    _html(
        f"""
        <div style="margin-bottom: 20px;">
            <h1 style="font-size: 1.75rem; font-weight: 700; color: {COLOR_TITLE}; margin: 0;">
                🔎 单券可购额度查询
            </h1>
            <p style="font-size: 0.875rem; color: {COLOR_LABEL}; margin: 8px 0 0 0;">
                输入债券代码或名称，查看单债可购剩余额度
            </p>
        </div>
        """,
    )


@_fragment
def _render_query_area(data_loader) -> None:
    query_text = str(st.session_state.get("page8_bond_quota_input", "") or "").strip()
    do_query = bool(st.session_state.pop("page8_query_requested", False))
    current_cache_key = _build_query_cache_key(query_text, data_loader)
    cached_query_key = st.session_state.get("page8_last_query_cache_key")
    cached_result = st.session_state.get("page8_last_query_result")
    query_warning: str | None = None
    result = None

    if do_query and not query_text:
        st.session_state.pop("page8_last_query_text", None)
        st.session_state.pop("page8_last_query_cache_key", None)
        st.session_state.pop("page8_last_query_result", None)
        query_warning = "请输入债券代码或名称。"
    elif do_query:
        if current_cache_key == cached_query_key and cached_result:
            result = cached_result
        else:
            result = query_bond_remaining_quota(data_loader, query_text)
            st.session_state["page8_last_query_text"] = query_text
            st.session_state["page8_last_query_cache_key"] = current_cache_key
            st.session_state["page8_last_query_result"] = result

    col_input, col_btn = st.columns([4, 1])
    with col_input:
        bond_input = st.text_input(
            "债券代码或名称",
            placeholder="输入债券代码、主证券代码、ISIN 或债券名称",
            key="page8_bond_quota_input",
            on_change=_request_query,
        )
    with col_btn:
        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        st.button(
            "查询",
            type="primary",
            use_container_width=True,
            key="page8_bond_quota_btn",
            on_click=_request_query,
        )

    result_slot = st.empty()

    if query_warning:
        result_slot.warning(query_warning)
        return

    query_text = (bond_input or "").strip()
    if result is None and not query_text:
        result_slot.info("请输入债券代码或名称并点击「查询」。")
        return

    if result is None:
        result = cached_result
        current_cache_key = _build_query_cache_key(query_text, data_loader)
        if not result or current_cache_key != cached_query_key:
            result_slot.info("请输入债券代码或名称并点击「查询」。")
            return

    with result_slot.container():
        _render_query_result(result)


def render(filters: dict, data_loader):
    """渲染单券可购额度查询页面。"""
    inject_compact_controls_css("_page8_compact_controls_css_injected")
    _inject_page8_css()
    _render_page_title()
    _render_query_area(data_loader)
