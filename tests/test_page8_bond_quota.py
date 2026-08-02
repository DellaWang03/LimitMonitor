from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

from src.visualization.pages import page8_bond_quota


def test_page8_does_not_retain_legacy_parallel_quota_query() -> None:
    source = Path("src/visualization/pages/page8_bond_quota.py").read_text(
        encoding="utf-8"
    )

    assert "query_bond_remaining_quota" not in source
    assert "get_pretrade_risk_service" in source
    assert "render_pretrade_header" in source
    assert "render_pretrade_status" in source
    # KPI 卡片改用展示页共享组件，不再走交易前专属实现。
    assert "render_metric_card" in source
    assert "render_pretrade_kpi_card" not in source
    assert "render_pretrade_empty_state" not in source
    assert "正在读取限额快照并计算风险，请稍候" in source
    assert "use_container_width" not in source


def test_page8_never_shows_raw_exception_text_to_users() -> None:
    source = Path("src/visualization/pages/page8_bond_quota.py").read_text(
        encoding="utf-8"
    )

    assert "st.error(str(exc))" not in source
    assert "SNAPSHOT_UNAVAILABLE_MESSAGE" in source
    assert "SERVICE_UNAVAILABLE_MESSAGE" in source
    assert "user_facing_input_message" in source


def test_page8_rewrites_explanation_columns_and_avoids_internal_wording() -> None:
    source = Path("src/visualization/pages/page8_bond_quota.py").read_text(
        encoding="utf-8"
    )

    assert source.count("rewrite_explanation_column") >= 3
    assert "内核" not in source
    assert "snapshot_id" not in source
    assert "Stage" not in source


def test_page8_shows_snapshot_date_once_and_keeps_both_tabs() -> None:
    source = Path("src/visualization/pages/page8_bond_quota.py").read_text(
        encoding="utf-8"
    )

    assert 'st.tabs(["风险约束", "数据说明"])' in source
    # 快照日期只由共享标题区承担，不在 KPI 说明里重复。
    assert "limit_quota_snapshot_caption" not in source
    assert "限额快照日期：" not in source
    assert "border=False" in source
    # 章节标题与其他展示页一样使用 H4 markdown，不再走交易前专属组件。
    assert "render_pretrade_section_title" not in source
    assert 'st.markdown("#### ' in source


def test_page8_uses_account_options_instead_of_unvalidated_free_text() -> None:
    """拟买账户曾是自由文本框，不校验账户是否真实存在，容易录错账户；
    改为从当前快照真实账户中选择，取数失败时才回落为自由文本。"""

    source = Path("src/visualization/pages/page8_bond_quota.py").read_text(
        encoding="utf-8"
    )

    assert "account_options" in source
    assert "st.selectbox(" in source


def test_page8_historical_mode_does_not_call_current_pretrade_service(monkeypatch) -> None:
    messages: list[str] = []
    fake_streamlit = SimpleNamespace(info=messages.append)
    monkeypatch.setattr(page8_bond_quota, "st", fake_streamlit)
    monkeypatch.setattr(page8_bond_quota, "inject_pretrade_ui_css", lambda: None)
    monkeypatch.setattr(page8_bond_quota, "_render_title", lambda: None)
    monkeypatch.setattr(
        page8_bond_quota,
        "get_pretrade_risk_service",
        lambda: (_ for _ in ()).throw(AssertionError("must not call service")),
    )

    page8_bond_quota.render({}, SimpleNamespace(target_date=date(2026, 7, 10)))

    assert messages == ["交易前试算仅支持已发布的最新交易前快照；请在侧边栏切换到「最新数据」。"]
