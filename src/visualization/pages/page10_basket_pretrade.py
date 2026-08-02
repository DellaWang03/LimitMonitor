"""债券组合交易前超限试算页面：只调用共同交易前服务。"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from src.pretrade.pretrade_service import PretradeServiceError
from src.pretrade.result_adapter import BasketCheck
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
    render_pretrade_input_summary,
    render_pretrade_status,
    rewrite_explanation_column,
    user_facing_input_message,
)
from src.visualization.components.tables import render_data_table
from src.visualization.pretrade_presenter import (
    basket_input_result_frame,
    basket_lines_from_frame,
    basket_summary,
    business_dimension_frame,
    business_line_audit_frame,
)
from src.visualization.pretrade_service import get_pretrade_risk_service


_DEFAULT_ACCOUNT = "自营部交易性"
_INPUT_COLUMNS = ("债券代码", "拟买金额(万)_PR", "拟买入账户", "拟买全价成本(万)")


def _empty_basket() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "债券代码": "",
                "拟买金额(万)_PR": "",
                "拟买入账户": _DEFAULT_ACCOUNT,
                "拟买全价成本(万)": "",
            }
        ],
        columns=_INPUT_COLUMNS,
    )


def _render_title() -> None:
    cached = st.session_state.get("page10_pretrade_result")
    snapshot_data_date = str(cached.snapshot_data_date) if cached else None
    render_pretrade_header(
        icon="🧺",
        title="债券组合超限试算",
        description="逐笔录入拟买交易，查看组合合并后的总体结论和共享风险约束。",
        snapshot_data_date=snapshot_data_date,
    )


def _input_overview(frame: pd.DataFrame) -> tuple[int, float]:
    codes = frame["债券代码"].fillna("").astype(str).str.strip()
    amounts = pd.to_numeric(frame["拟买金额(万)_PR"], errors="coerce")
    active = codes.ne("") | amounts.notna()
    return int(active.sum()), float(amounts[active].fillna(0).sum())


def _account_column_config(accounts: list[str]) -> Any:
    """账户列可选时限定为真实账户，取数失败时回落为自由文本，不阻断主流程。"""

    if accounts:
        return st.column_config.SelectboxColumn(
            "拟买账户",
            width="medium",
            options=accounts,
            default=_DEFAULT_ACCOUNT,
            help="仅可选择当前快照中实际存在的账户，避免账户名录入错误",
        )
    return st.column_config.TextColumn("拟买账户", width="medium")


def _render_basket_editor(accounts: list[str]) -> pd.DataFrame:
    """渲染交易清单编辑器；结果态可由外层折叠以优先展示结论。

    高度必须保持常量：Streamlit 会把 height 计入 data_editor 的组件 ID，
    一旦按录入行数动态调整，用户每新增一行都会让组件换新 ID 并丢失已录内容。
    """

    with st.container(key="page10_pretrade_editor_shell"):
        st.caption("金额单位为万元；高收益债需填写全价成本。")
        return st.data_editor(
            _empty_basket(),
            key="page10_pretrade_lines",
            hide_index=True,
            num_rows="dynamic",
            width="stretch",
            column_config={
                "债券代码": st.column_config.TextColumn(
                    "债券代码",
                    width="medium",
                    help="支持标准市场后缀，例如 1980082.IB",
                ),
                "拟买金额(万)_PR": st.column_config.TextColumn(
                    "拟买金额",
                    validate=r"^\s*(?:\d+(?:\.\d*)?|\.\d+)?\s*$",
                    help="请输入不小于 0 的数字，单位为万元",
                ),
                "拟买入账户": _account_column_config(accounts),
                "拟买全价成本(万)": st.column_config.TextColumn(
                    "全价成本（高收益，可选）",
                    validate=r"^\s*(?:\d+(?:\.\d*)?|\.\d+)?\s*$",
                    help="仅高收益债适用，单位为万元",
                ),
            },
        )


def _status_content(result: BasketCheck) -> tuple[str, str, str]:
    if result.status == "已超限":
        return (
            "danger",
            "组合交易已超限，请调整交易清单",
            f"共有 {result.confirmed_breach_count} 个风险维度形成超限结论。请先处理关键风险约束，再重新试算。",
        )
    if result.status == "不可计算":
        return (
            "warning",
            "组合交易不可计算，暂不能给出交易建议",
            f"共有 {result.uncomputable_count} 个必检风险维度缺少完整计算条件；系统不会将其显示为未超限。",
        )
    return (
        "success",
        "组合交易未超限",
        "全部必检风险维度均未形成超限结论。结果已按重复债券和共享风险对象合并计算。",
    )


def _render_status(result: BasketCheck) -> None:
    tone, title, description = _status_content(result)
    render_pretrade_status(
        eyebrow="组合交易结论",
        title=title,
        description=description,
        tone=tone,
    )


def _render_result(result: BasketCheck, *, submitted_frame: pd.DataFrame) -> None:
    summary = basket_summary(result)
    _render_status(result)

    dimension_table = rewrite_explanation_column(
        business_dimension_frame(
            result.dimensions,
            remaining_label="交易后剩余额度（万元）",
        ),
        "说明",
    )
    key_constraints = dimension_table.loc[
        dimension_table["状态"].ne("不适用"),
        ["风险维度", "状态", "适用对象", "交易后剩余额度（万元）", "限额"],
    ].head(5)
    binding_dimension = (
        str(key_constraints.iloc[0]["风险维度"])
        if not key_constraints.empty
        else "无适用约束"
    )
    breach_count = int(summary["超限维度"])
    uncomputable_count = int(summary["不可计算维度"])

    cards = st.columns(4)
    with cards[0]:
        render_metric_card(
            "本次拟买总额",
            f"{float(summary['本次拟买总额(万)']):,.2f}",
            "万元",
            "accent",
            min_height=KPI_CARD_MIN_HEIGHT,
        )
    with cards[1]:
        render_metric_card(
            "超限维度",
            f"{breach_count:,}",
            "无超限" if breach_count == 0 else "个",
            "success" if breach_count == 0 else "danger",
            min_height=KPI_CARD_MIN_HEIGHT,
        )
    with cards[2]:
        render_metric_card(
            "不可计算维度",
            f"{uncomputable_count:,}",
            "全部可计算" if uncomputable_count == 0 else "个",
            "neutral" if uncomputable_count == 0 else "warning",
            min_height=KPI_CARD_MIN_HEIGHT,
        )
    with cards[3]:
        render_metric_card(
            "最紧风险约束",
            binding_dimension,
            "当前约束",
            min_height=KPI_CARD_MIN_HEIGHT,
        )

    render_vertical_space(24)

    result_tab, constraints_tab, data_tab = st.tabs(
        ["交易结果", "风险约束", "数据说明"]
    )
    with result_tab:
        st.markdown("#### 逐笔交易结果")
        st.caption("用于核对本次提交的交易行、主数据状态和不可计算原因。")
        line_table = rewrite_explanation_column(
            basket_input_result_frame(
                submitted_frame,
                result.line_audits,
                result.line_reasons,
            ),
            "计算说明",
        )
        render_data_table(
            line_table,
            height=min(480, 120 + len(line_table) * 38),
            highlight_column="主数据状态",
            show_summary=False,
            enable_export=False,
        )

    with constraints_tab:
        if not key_constraints.empty:
            st.markdown("#### 关键风险约束")
            st.caption("优先展示已超限、不可计算及剩余额度最紧的风险维度。")
            render_data_table(
                key_constraints,
                height=min(250, 120 + len(key_constraints) * 38),
                highlight_column="状态",
                show_summary=False,
                enable_export=False,
            )

        with st.expander(
            f"查看全部风险维度（{len(dimension_table)}）",
            expanded=False,
        ):
            st.caption("共享主体、实控人、担保人及其他风险维度已按组合合并；金额单位均为万元。")
            render_data_table(
                dimension_table,
                height=min(650, 120 + len(dimension_table) * 38),
                highlight_column="状态",
                show_summary=False,
                enable_export=True,
                export_key="export_page10_pretrade_dimensions",
            )

    with data_tab:
        st.markdown("#### 主数据与快照")
        st.caption("展示各输入行实际采用的数据来源和数据日期，不展示系统内部技术字段。")
        audit_table = rewrite_explanation_column(
            business_line_audit_frame(
                result.line_audits,
                snapshot_data_date=result.snapshot_data_date,
            ),
            "说明",
        )
        render_data_table(
            audit_table,
            height=min(420, 120 + len(audit_table) * 38),
            highlight_column="主数据状态",
            show_summary=False,
            enable_export=False,
        )
        with st.expander("口径说明"):
            st.markdown(
                """
                - **组合合并**：重复债券以及共享主体、实控人、担保人的交易会合并计算。
                - **PR 口径**：除高收益年度限额外，各风险维度均按拟买 PR 金额试算。
                - **高收益全价成本**：仅高收益债适用；触发该维度时必须填写拟买全价成本。
                - **不可计算**：任一必检风险维度缺少必要条件时，总体结果不会显示为未超限。
                """
            )


def render(filters: dict[str, Any], data_loader: Any) -> None:
    """渲染债券组合页面；参数保持既有页面路由兼容。"""

    del filters
    inject_pretrade_ui_css()
    _render_title()

    if getattr(data_loader, "target_date", None) is not None:
        st.info("交易前试算仅支持已发布的最新交易前快照；请在侧边栏切换到「最新数据」。")
        return

    accounts = account_options(data_loader, default_account=_DEFAULT_ACCOUNT)

    if st.session_state.get("page10_pretrade_result") is None:
        st.markdown("#### 交易清单")
        edited = _render_basket_editor(accounts)
    else:
        with st.expander("交易清单（已提交，可展开修改）", expanded=False):
            edited = _render_basket_editor(accounts)
    input_count, input_total = _input_overview(edited)
    render_pretrade_input_summary(
        ("已录入", f"{input_count} 笔交易"),
        ("拟买金额合计", f"{input_total:,.2f} 万元"),
    )

    _spacer, calculate, clear = st.columns([5.4, 1.6, 1])
    with calculate:
        calculate_clicked = st.button(
            "计算组合结果",
            type="primary",
            width="stretch",
            key="page10_pretrade_calculate",
        )
    with clear:
        if st.button(
            "清空",
            type="secondary",
            width="stretch",
            key="page10_pretrade_clear",
        ):
            st.session_state.pop("page10_pretrade_lines", None)
            st.session_state.pop("page10_pretrade_result", None)
            st.session_state.pop("page10_pretrade_submitted_lines", None)
            st.rerun()

    if calculate_clicked:
        try:
            lines = basket_lines_from_frame(edited)
            with st.spinner("正在读取限额快照并计算风险，请稍候"):
                result = get_pretrade_risk_service().check_basket(lines)
        except PretradeServiceError:
            st.session_state.pop("page10_pretrade_result", None)
            st.session_state.pop("page10_pretrade_submitted_lines", None)
            st.error(SNAPSHOT_UNAVAILABLE_MESSAGE)
        except (TypeError, ValueError) as exc:
            st.session_state.pop("page10_pretrade_result", None)
            st.session_state.pop("page10_pretrade_submitted_lines", None)
            st.error(user_facing_input_message(str(exc)))
        except Exception:
            st.session_state.pop("page10_pretrade_result", None)
            st.session_state.pop("page10_pretrade_submitted_lines", None)
            st.error(SERVICE_UNAVAILABLE_MESSAGE)
        else:
            st.session_state["page10_pretrade_result"] = result
            st.session_state["page10_pretrade_submitted_lines"] = edited.copy(
                deep=True
            )
            st.rerun()

    result = st.session_state.get("page10_pretrade_result")
    if result is None:
        st.info("录入至少一笔拟买交易后，点击「计算组合结果」。")
        return
    submitted_frame = st.session_state.get(
        "page10_pretrade_submitted_lines",
        edited,
    )

    render_vertical_space(8)
    _render_result(result, submitted_frame=submitted_frame)
