from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from src.visualization.components.pretrade_ui import (
    INPUT_INVALID_MESSAGE,
    KPI_CARD_MIN_HEIGHT,
    account_options,
    business_explanation,
    rewrite_explanation_column,
    user_facing_input_message,
)


def test_pretrade_ui_takes_visual_specs_from_the_shared_display_components() -> None:
    """交易前两页不得自建卡片/标题/状态条规格，一律沿用展示页组件。"""

    source = Path(
        "src/visualization/components/pretrade_ui.py"
    ).read_text(encoding="utf-8")

    assert "from src.visualization.components.controls import render_page_header" in source
    assert "render_page_header(" in source
    # 自建的标题、卡片、状态条、空态与章节标题样式已全部退役。
    for retired in (
        "pretrade-page-header",
        "pretrade-status",
        "pretrade-kpi-card",
        "pretrade-empty-state",
        "pretrade-section-title",
        "pretrade-input-summary",
    ):
        assert retired not in source
    # 结论一律走应用内既有提示框，颜色之外始终保留文字。
    assert "st.success" in source
    assert "st.warning" in source
    assert "st.error" in source
    assert "限额快照" in source


def test_pretrade_kpi_cards_match_the_display_page_card_height() -> None:
    """展示页 KPI 卡片自然高度为 136px，交易前卡片必须对齐同一规格。"""

    assert KPI_CARD_MIN_HEIGHT == 136


def test_account_options_returns_real_accounts_with_default_first() -> None:
    """拟买账户不应是不做校验的自由文本；下拉必须来自当前快照的真实账户。"""

    data_loader = SimpleNamespace(
        get_available_accounts=lambda: ["全部", "自营高收益账户", "自营部交易性", "做市交易部做市业务"]
    )

    accounts = account_options(data_loader, default_account="自营部交易性")

    assert "全部" not in accounts
    assert accounts[0] == "自营部交易性"
    assert set(accounts) == {"自营高收益账户", "自营部交易性", "做市交易部做市业务"}


def test_account_options_always_includes_the_default_even_if_snapshot_lacks_it() -> None:
    """默认账户必须始终在候选项内，否则依赖它的下拉/单选会因缺省值非法而报错。"""

    data_loader = SimpleNamespace(get_available_accounts=lambda: ["自营高收益账户"])

    accounts = account_options(data_loader, default_account="自营部交易性")

    assert accounts[0] == "自营部交易性"
    assert "自营高收益账户" in accounts


def test_account_options_falls_back_to_empty_when_data_loader_lacks_the_method() -> None:
    """历史快照等场景传入的 data_loader 可能不支持该方法，不应因此崩溃。"""

    assert account_options(SimpleNamespace(), default_account="自营部交易性") == []


def test_account_options_falls_back_to_empty_when_the_lookup_raises() -> None:
    """账户列表取数失败（如快照/DB 不可用）时回落为空列表，不阻断查询主流程。"""

    def _boom():
        raise RuntimeError("db unavailable")

    data_loader = SimpleNamespace(get_available_accounts=_boom)

    assert account_options(data_loader, default_account="自营部交易性") == []


def test_account_options_falls_back_to_empty_when_snapshot_has_no_real_accounts() -> None:
    """快照数据源为空（仅剩「全部」占位）时同样回落为自由文本，不展示空下拉。"""

    data_loader = SimpleNamespace(get_available_accounts=lambda: ["全部"])

    assert account_options(data_loader, default_account="自营部交易性") == []


@pytest.mark.parametrize(
    "reason",
    [
        "缺少主数据解析结果",
        "持仓快照缺少信用债原始持仓",
        "持仓快照缺少可用债券代码列",
        "共同内核缺少适用维度结果表",
        "共同内核缺少适用维度结果行",
        "共同内核未产生高收益年度本金结果",
        "生产结果标记为不可计算",
        "生产结果缺少是否超限状态",
        "生产结果未给出适用限额",
        "生产结果缺少适用维度的当前占用,限额",
        "持仓快照主数据缺少必填字段: 省份, 债务主体",
        "持仓快照主数据矛盾: issuer_name",
        "持仓快照主数据规范化失败: invalid literal for float()",
        "Wind 主数据缺少必填字段: windIndustry",
    ],
)
def test_business_explanation_removes_internal_wording(reason: str) -> None:
    explanation = business_explanation(reason)

    for marker in ("内核", "生产结果", "快照主数据", "必填字段", "Wind", "_"):
        assert marker not in explanation


def test_business_explanation_keeps_actionable_business_reasons() -> None:
    assert business_explanation("高收益债券缺少拟买全价成本") == "高收益债券缺少拟买全价成本"
    assert business_explanation("债券代码为空或非法") == "债券代码为空或非法"
    assert business_explanation(None) == "—"
    assert business_explanation("   ") == "—"
    assert business_explanation("nan") == "—"


@pytest.mark.parametrize(
    "reason",
    [
        "Wind 字段映射尚未通过真实环境验收",
        "WindPy 不可用",
        "WindPy 启动失败",
        "Wind 请求失败: TimeoutError",
        "Wind 返回错误码: -40521",
        "Wind 主数据返回记录数不是 1",
        "Wind 主数据缺少结构性字段",
        "Wind 主数据规范化失败: invalid literal for float(): 'x'",
        "Excel Wind 主数据请求失败: RuntimeError",
        "Wind Excel 主数据缺少债务主体wind代码",
        "Wind 主数据缺少发行人类型原始值",
    ],
)
def test_business_explanation_collapses_master_channel_diagnostics(reason: str) -> None:
    """取数链路诊断含终端名、错误码与异常类型，一律收敛为同一句业务结论。"""

    explanation = business_explanation(reason)

    assert explanation == "暂时无法取得该债券完整主数据"
    for marker in ("Wind", "wind", "Excel", "Error", "错误码", "验收", "字段"):
        assert marker not in explanation


def test_business_explanation_falls_back_when_wording_stays_internal() -> None:
    """未登记但仍带实现口径的文案不得原样透出。"""

    assert business_explanation("内核未返回结果") == "必需数据不完整，暂时无法计算"
    assert business_explanation("Stage2 输出缺失") == "必需数据不完整，暂时无法计算"
    assert business_explanation("解析结果为 None") == "必需数据不完整，暂时无法计算"


def test_business_explanation_expands_limit_result_reasons() -> None:
    """限额结果自带的不可计算原因按业务口径展开，组合原因逐段改写。"""

    assert business_explanation("缺归并主键") == "该债券缺少监管归并信息"
    assert business_explanation("缺债券余额") == "该债券缺少债券余额数据"
    assert (
        business_explanation("缺归并主键、缺债券余额")
        == "该债券缺少监管归并信息、该债券缺少债券余额数据"
    )


def test_rewrite_explanation_column_only_touches_target_column() -> None:
    frame = pd.DataFrame(
        [
            {"风险维度": "单一债券规模", "说明": "生产结果未给出适用限额"},
            {"风险维度": "单一主体规模", "说明": "—"},
        ]
    )

    rewritten = rewrite_explanation_column(frame, "说明")

    assert rewritten.loc[0, "说明"] == "该风险维度未提供适用限额"
    assert rewritten.loc[1, "说明"] == "—"
    assert list(rewritten["风险维度"]) == ["单一债券规模", "单一主体规模"]
    assert frame.loc[0, "说明"] == "生产结果未给出适用限额"


def test_rewrite_explanation_column_ignores_missing_column() -> None:
    frame = pd.DataFrame([{"风险维度": "单一债券规模"}])

    assert rewrite_explanation_column(frame, "说明") is frame


@pytest.mark.parametrize(
    "message",
    [
        "债券代码不能为空",
        "拟买入账户不能为空",
        "交易清单不能为空",
        "拟买金额必须是有限正数",
        "输入第 2 行的拟买金额必须为数字",
    ],
)
def test_user_facing_input_message_keeps_recorder_guidance(message: str) -> None:
    assert user_facing_input_message(message) == message


@pytest.mark.parametrize(
    "message",
    [
        "交易清单缺少列: 拟买金额(万)_PR",
        "交易清单必须是表格",
        "输入行编号必须是整数",
        "输入行编号不能重复",
        "",
    ],
)
def test_user_facing_input_message_hides_internal_wording(message: str) -> None:
    assert user_facing_input_message(message) == INPUT_INVALID_MESSAGE


def test_pretrade_ui_no_longer_computes_a_state_dependent_editor_height() -> None:
    """录入表高度参与 data_editor 组件 ID，必须保持常量，不能按行数推导。"""

    import src.visualization.components.pretrade_ui as pretrade_ui

    assert not hasattr(pretrade_ui, "data_editor_height")
