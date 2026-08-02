from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

from src.visualization.pages import page10_basket_pretrade


def test_page10_starts_with_one_blank_dynamic_trade_row() -> None:
    frame = page10_basket_pretrade._empty_basket()

    assert len(frame) == 1
    assert frame.loc[0, "债券代码"] == ""
    assert frame.loc[0, "拟买金额(万)_PR"] == ""
    assert frame.loc[0, "拟买入账户"] == "自营部交易性"


def test_page10_account_column_uses_real_accounts_when_available() -> None:
    """账户列曾是自由文本，不校验账户是否真实存在，容易录错账户；
    可选时改为限定选项的下拉，且新增行默认沿用既有默认账户。"""

    config = page10_basket_pretrade._account_column_config(
        ["做市交易部做市业务", "自营部交易性"]
    )

    assert config["type_config"]["type"] == "selectbox"
    assert set(config["type_config"]["options"]) == {
        "做市交易部做市业务",
        "自营部交易性",
    }
    assert config["default"] == "自营部交易性"


def test_page10_account_column_falls_back_to_free_text_without_accounts() -> None:
    """账户列表取数失败时不能让整张录入表报错或阻断录入，回落为自由文本。"""

    config = page10_basket_pretrade._account_column_config([])

    assert config["type_config"]["type"] == "text"


def test_page10_uses_shared_pretrade_ui_and_user_facing_wait_copy() -> None:
    source = Path("src/visualization/pages/page10_basket_pretrade.py").read_text(
        encoding="utf-8"
    )

    assert "render_pretrade_header" in source
    assert "render_pretrade_status" in source
    assert "render_pretrade_input_summary" in source
    assert "account_options" in source
    # KPI 卡片与空态改用展示页共享组件，不再走交易前专属实现。
    assert "render_metric_card" in source
    assert "render_pretrade_kpi_card" not in source
    assert "render_pretrade_empty_state" not in source
    assert "正在读取限额快照并计算风险，请稍候" in source
    assert 'title="债券组合超限试算"' in source
    assert "计算组合结果" in source
    assert "计算篮子结果" not in source
    assert 'type="primary"' in source
    assert 'type="secondary"' in source
    assert "use_container_width" not in source


def test_page10_never_shows_raw_exception_text_to_users() -> None:
    source = Path("src/visualization/pages/page10_basket_pretrade.py").read_text(
        encoding="utf-8"
    )

    assert "st.error(str(exc))" not in source
    assert "SNAPSHOT_UNAVAILABLE_MESSAGE" in source
    assert "SERVICE_UNAVAILABLE_MESSAGE" in source
    assert "user_facing_input_message" in source


def test_page10_rewrites_explanation_columns_and_avoids_internal_wording() -> None:
    source = Path("src/visualization/pages/page10_basket_pretrade.py").read_text(
        encoding="utf-8"
    )

    assert source.count("rewrite_explanation_column") >= 4
    assert "内核" not in source
    assert "snapshot_id" not in source
    assert "Stage" not in source


def test_page10_input_summary_keeps_only_count_and_total() -> None:
    source = Path("src/visualization/pages/page10_basket_pretrade.py").read_text(
        encoding="utf-8"
    )
    summary_call = source.split("render_pretrade_input_summary(", 1)[1].split(
        "calculate, clear", 1
    )[0]

    assert "已录入" in summary_call
    assert "拟买金额合计" in summary_call
    assert "新增交易" not in summary_call


def test_page10_primary_button_does_not_span_the_content_area() -> None:
    source = Path("src/visualization/pages/page10_basket_pretrade.py").read_text(
        encoding="utf-8"
    )

    assert "st.columns([4, 1])" not in source
    assert "st.columns([5.4, 1.6, 1])" in source


def test_page10_editor_keeps_a_stable_widget_identity_across_edits(monkeypatch) -> None:
    """Streamlit 把 height 计入 data_editor 组件 ID。

    若高度随已录入行数变化，用户每加一行都会让组件换新 ID 并丢掉已输入内容，
    表现为「回车或失焦后清空」。这里锁定：录入状态不得影响任何组件 ID 入参。
    """

    captured: list[dict] = []

    class _Recorder:
        def __init__(self, session_state: dict) -> None:
            self.session_state = session_state
            self.column_config = page10_basket_pretrade.st.column_config

        def container(self, **_kwargs):
            from contextlib import nullcontext

            return nullcontext()

        def caption(self, *_args, **_kwargs) -> None:
            return None

        def data_editor(self, _frame, **kwargs):
            captured.append(kwargs)
            return _frame

    empty_state = {}
    edited_state = {
        "page10_pretrade_lines": {
            "added_rows": [{}, {}, {}],
            "deleted_rows": [1],
            "edited_rows": {0: {"债券代码": "1980082.IB"}},
        }
    }

    for state in (empty_state, edited_state):
        monkeypatch.setattr(page10_basket_pretrade, "st", _Recorder(state))
        page10_basket_pretrade._render_basket_editor(["自营部交易性"])

    assert len(captured) == 2
    assert captured[0] == captured[1]
    # 高度显式传入即会参与组件 ID；保持缺省的 "auto" 才能同时自适应且稳定。
    assert "height" not in captured[0]


def test_page10_no_longer_derives_editor_height_from_session_state() -> None:
    source = Path("src/visualization/pages/page10_basket_pretrade.py").read_text(
        encoding="utf-8"
    )

    assert "data_editor_height" not in source
    assert "_editor_row_count" not in source
    assert 'key="page10_pretrade_editor_shell"' in source


def test_page10_key_constraints_live_inside_the_risk_tab() -> None:
    source = Path("src/visualization/pages/page10_basket_pretrade.py").read_text(
        encoding="utf-8"
    )
    tab_body = source.split("with constraints_tab:")[1].split("with data_tab:")[0]

    assert "关键风险约束" in tab_body
    assert "查看全部风险维度" in tab_body
    assert "expanded=False" in tab_body
    # 关键约束与全部维度都走共享表格组件，不再各自调用 st.dataframe。
    assert "st.dataframe(" not in source


def test_page10_shows_snapshot_once_and_uses_fourth_kpi_for_risk() -> None:
    source = Path("src/visualization/pages/page10_basket_pretrade.py").read_text(
        encoding="utf-8"
    )

    assert "限额快照日期" not in source
    assert '"最紧风险约束"' in source
    # 章节标题与其他展示页一样使用 H4 markdown，不再走交易前专属组件。
    assert "render_pretrade_section_title" not in source
    assert 'st.markdown("#### ' in source


def test_page10_uses_bond_portfolio_user_facing_wording() -> None:
    source = Path("src/visualization/pages/page10_basket_pretrade.py").read_text(
        encoding="utf-8"
    )

    assert "债券组合超限试算" in source
    assert "组合交易结论" in source
    assert "组合合并" in source
    assert "一揽子债券超限试算" not in source
    assert "整篮交易" not in source


def test_page10_historical_mode_does_not_call_current_pretrade_service(monkeypatch) -> None:
    messages: list[str] = []
    fake_streamlit = SimpleNamespace(info=messages.append)
    monkeypatch.setattr(page10_basket_pretrade, "st", fake_streamlit)
    monkeypatch.setattr(page10_basket_pretrade, "inject_pretrade_ui_css", lambda: None)
    monkeypatch.setattr(page10_basket_pretrade, "_render_title", lambda: None)
    monkeypatch.setattr(
        page10_basket_pretrade,
        "get_pretrade_risk_service",
        lambda: (_ for _ in ()).throw(AssertionError("must not call service")),
    )

    page10_basket_pretrade.render({}, SimpleNamespace(target_date=date(2026, 7, 10)))

    assert messages == [
        "交易前试算仅支持已发布的最新交易前快照；请在侧边栏切换到「最新数据」。"
    ]
