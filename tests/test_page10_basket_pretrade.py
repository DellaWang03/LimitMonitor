from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from src.visualization.pages import page10_basket_pretrade


def test_page10_historical_mode_does_not_call_current_pretrade_service(monkeypatch) -> None:
    messages: list[str] = []
    fake_streamlit = SimpleNamespace(info=messages.append)
    monkeypatch.setattr(page10_basket_pretrade, "st", fake_streamlit)
    monkeypatch.setattr(
        page10_basket_pretrade, "inject_compact_controls_css", lambda _key: None
    )
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
