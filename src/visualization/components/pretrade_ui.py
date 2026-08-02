"""交易前页面共享展示组件。

视觉规格一律取自 `components.controls` 与全局样式，本模块不再自建卡片、
标题或状态条的尺寸与配色，只负责交易前两页共有的版式编排，以及把后端诊断
文案改写为业务用户语言；不包含任何交易前计算、数据读取或业务状态判断。
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from src.visualization.components.controls import render_page_header


SNAPSHOT_UNAVAILABLE_MESSAGE = "当前交易前快照暂不可用，请稍后重试或联系系统管理员。"
SERVICE_UNAVAILABLE_MESSAGE = "交易前服务暂不可用，请稍后重试或联系系统管理员。"
INPUT_INVALID_MESSAGE = "录入内容格式不正确，请检查债券代码、金额和账户后重新提交。"

# 交易前 KPI 卡片统一使用展示页卡片的自然高度，避免文本型指标换行后错位。
KPI_CARD_MIN_HEIGHT = 136

# 后端诊断文案按实现口径书写，展示前统一改写为业务语言。
_EXPLANATION_REWRITES = {
    "缺少主数据解析结果": "未取得该债券完整主数据",
    "持仓快照缺少信用债原始持仓": "当前限额快照缺少信用债持仓数据",
    "持仓快照缺少可用债券代码列": "当前限额快照缺少债券代码信息",
    "共同内核缺少适用维度结果表": "系统暂未给出该风险维度结果",
    "共同内核缺少适用维度结果行": "系统暂未给出该风险维度结果",
    "共同内核未产生高收益年度本金结果": "系统暂未给出高收益年度限额结果",
    "生产结果标记为不可计算": "该风险维度当前不可计算",
    "生产结果缺少是否超限状态": "系统暂未给出该风险维度的超限判定",
    "生产结果未给出适用限额": "该风险维度未提供适用限额",
    # 限额结果自带的不可计算原因，按业务口径展开
    "缺归并主键": "该债券缺少监管归并信息",
    "缺债券余额": "该债券缺少债券余额数据",
}
_EXPLANATION_PREFIX_REWRITES = (
    ("持仓快照主数据缺少必填字段", "该债券主数据不完整"),
    ("持仓快照主数据矛盾", "该债券主数据存在冲突，需人工核对"),
    ("持仓快照主数据规范化失败", "该债券主数据格式异常，需人工核对"),
    ("Wind 主数据缺少必填字段", "该债券主数据不完整"),
    ("生产结果缺少适用维度的", "该风险维度缺少计算所需数据"),
)

# 主数据取数链路的诊断文案含行情终端名称、错误码与异常类型，
# 一律收敛为同一句业务结论，避免把取数实现细节带到界面上。
_MASTER_CHANNEL_MARKERS = ("Wind", "wind", "WindPy", "Excel", "excel")
_MASTER_CHANNEL_MESSAGE = "暂时无法取得该债券完整主数据"

# 兜底：任何仍带实现口径的文案都不直接展示。
_EXPLANATION_INTERNAL_MARKERS = (
    "生产结果",
    "共同内核",
    "内核",
    "规范化",
    "错误码",
    "记录数",
    "原始值",
    "解析结果",
    "验收",
    "字段",
    "主键",
    "Traceback",
    "Exception",
    "Error",
    "None",
    "Stage",
    "stage",
    "SQL",
    "snapshot",
)
_EXPLANATION_FALLBACK = "必需数据不完整，暂时无法计算"

# 只有明确面向录入者的校验提示才原样显示，其余回落为统一提示。
_INPUT_MESSAGE_SUFFIXES = ("不能为空", "必须是有限正数", "必须为数字")
_INPUT_MESSAGE_INTERNAL_MARKERS = ("缺少列", "行编号", "表格", "_PR", "(万)", "（万）")


def business_explanation(reason: str | None) -> str:
    """把后端诊断文案改写为业务语言；业务口径原因原样保留。

    未登记的文案一律按实现口径处理：命中取数链路或内部标记时改写为统一
    业务结论，避免行情终端名称、错误码、异常类型或字段名出现在界面上。
    """

    text = "" if reason is None else str(reason).strip()
    if not text or text in {"—", "nan", "None"}:
        return "—"
    if text in _EXPLANATION_REWRITES:
        return _EXPLANATION_REWRITES[text]
    segments = [part.strip() for part in text.split("、") if part.strip()]
    if len(segments) > 1 and all(part in _EXPLANATION_REWRITES for part in segments):
        return "、".join(_EXPLANATION_REWRITES[part] for part in segments)
    for prefix, rewritten in _EXPLANATION_PREFIX_REWRITES:
        if text.startswith(prefix):
            return rewritten
    if any(marker in text for marker in _MASTER_CHANNEL_MARKERS):
        return _MASTER_CHANNEL_MESSAGE
    if any(marker in text for marker in _EXPLANATION_INTERNAL_MARKERS):
        return _EXPLANATION_FALLBACK
    return text


def rewrite_explanation_column(frame: pd.DataFrame, column: str) -> pd.DataFrame:
    """就地改写展示表中的说明列，缺失该列时原样返回。"""

    if column not in frame.columns:
        return frame
    rewritten = frame.copy()
    rewritten[column] = rewritten[column].map(business_explanation)
    return rewritten


def user_facing_input_message(message: str) -> str:
    """录入类校验提示只在不含内部口径时原样显示。"""

    text = str(message).strip()
    if not text or any(
        marker in text for marker in _INPUT_MESSAGE_INTERNAL_MARKERS
    ):
        return INPUT_INVALID_MESSAGE
    if text.endswith(_INPUT_MESSAGE_SUFFIXES):
        return text
    return INPUT_INVALID_MESSAGE


def account_options(data_loader: Any, *, default_account: str) -> list[str]:
    """从当前快照的真实持仓数据中取账户名列表，替代自由文本输入。

    「拟买账户」曾是纯文本框：系统里实际存在多个账户（自营部交易性、自营
    高收益账户、做市交易部做市业务等），但输入内容不校验是否真实存在，
    打错字或选错账户会被当成全新账户计算，「当前占用」显示为空而不报错，
    容易给出误导性结果。取数失败或快照暂不可用时返回空列表，页面据此回落
    为不限选项的自由文本输入，避免连带影响交易前查询主流程。
    """

    getter = getattr(data_loader, "get_available_accounts", None)
    if getter is None:
        return []
    try:
        raw_accounts = getter()
    except Exception:
        return []
    accounts = {str(item) for item in raw_accounts if str(item) and str(item) != "全部"}
    if not accounts:
        return []
    accounts.add(default_account)
    return sorted(accounts, key=lambda item: (item != default_account, item))


def inject_pretrade_ui_css() -> None:
    """注入交易前两页仅有的两处局部修正，卡片与标题一律沿用展示页规格。"""

    st.markdown(
        """
        <style>
          /* 全局样式把所有按钮渲染为蓝色主按钮，这里恢复「清空」的次级层级 */
          button[kind="secondary"] {
            background: #ffffff;
            border: 1px solid #cbd5e1;
            color: #475569;
          }
          button[kind="secondary"]:hover {
            background: #f8fafc;
            border-color: #94a3b8;
            box-shadow: none;
          }
          /* 录入表沿用共享表格的外框 */
          .st-key-page10_pretrade_editor_shell [data-testid="stDataFrame"] {
            border: 1px solid #e2e8f0;
            border-radius: 12px;
            overflow: hidden;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_pretrade_header(
    *,
    icon: str,
    title: str,
    description: str,
    snapshot_data_date: str | None,
) -> None:
    """渲染与展示页同规格的标题区，并在其下补一行限额快照日期。"""

    render_page_header(f"{icon} {title}", description)
    st.caption(f"限额快照 · {snapshot_data_date or '查询后确认'}")


def render_pretrade_status(
    *,
    eyebrow: str,
    title: str,
    description: str,
    tone: str,
) -> None:
    """用应用内既有的提示框渲染交易前结论；颜色之外始终保留明确文字。"""

    renderer = {
        "success": st.success,
        "warning": st.warning,
        "danger": st.error,
    }.get(tone, st.info)
    renderer(f"**{eyebrow}：{title}**\n\n{description}")


def render_pretrade_input_summary(*items: tuple[str, str]) -> None:
    """渲染紧凑的交易输入摘要。"""

    st.caption(" ｜ ".join(f"{label} **{value}**" for label, value in items))
