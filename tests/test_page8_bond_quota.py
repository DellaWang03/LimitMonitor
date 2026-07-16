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


def test_page8_historical_mode_does_not_call_current_pretrade_service(monkeypatch) -> None:
    messages: list[str] = []
    fake_streamlit = SimpleNamespace(info=messages.append)
    monkeypatch.setattr(page8_bond_quota, "st", fake_streamlit)
    monkeypatch.setattr(page8_bond_quota, "inject_compact_controls_css", lambda _key: None)
    monkeypatch.setattr(page8_bond_quota, "_render_title", lambda: None)
    monkeypatch.setattr(
        page8_bond_quota,
        "get_pretrade_risk_service",
        lambda: (_ for _ in ()).throw(AssertionError("must not call service")),
    )

    page8_bond_quota.render({}, SimpleNamespace(target_date=date(2026, 7, 10)))

    assert messages == ["交易前试算仅支持已发布的最新交易前快照；请在侧边栏切换到「最新数据」。"]
