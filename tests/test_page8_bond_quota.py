from __future__ import annotations

import sys
import types
from datetime import date
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

fake_streamlit = types.SimpleNamespace(
    fragment=lambda func: func,
    session_state={},
    markdown=lambda *args, **kwargs: None,
)
sys.modules.setdefault("streamlit", fake_streamlit)

from src.visualization.pages import page8_bond_quota
from src.visualization.pages.page8_bond_quota import _build_query_cache_key


class LoaderWithArchive:
    target_date = date(2026, 4, 27)
    archive_date_str = "2026-04-27"
    _snapshot_version = "snapshot-a"


class LoaderWithDifferentArchive:
    target_date = date(2026, 4, 28)
    archive_date_str = "2026-04-28"
    _snapshot_version = "snapshot-b"


def test_page8_query_cache_key_includes_archive_and_snapshot_version():
    first_key = _build_query_cache_key("240001", LoaderWithArchive())
    second_key = _build_query_cache_key("240001", LoaderWithDifferentArchive())

    assert first_key != second_key
    assert first_key == ("240001", "2026-04-27", "snapshot-a")
    assert second_key == ("240001", "2026-04-28", "snapshot-b")


class _Context:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _ResultSlot:
    def warning(self, *_args, **_kwargs):
        return None

    def info(self, *_args, **_kwargs):
        return None

    def container(self):
        return _Context()


class _FakeStreamlit:
    def __init__(self):
        self.session_state = {
            "page8_bond_quota_input": "26津渤海MTN003",
            "page8_query_requested": True,
        }

    def columns(self, *_args, **_kwargs):
        return [_Context(), _Context()]

    def text_input(self, *_args, **_kwargs):
        return self.session_state["page8_bond_quota_input"]

    def button(self, *_args, **_kwargs):
        return False

    def markdown(self, *_args, **_kwargs):
        return None

    def empty(self):
        return _ResultSlot()


def test_page8_query_uses_snapshot_data_date_instead_of_archive_date(monkeypatch):
    captured = {}

    def fake_query(_loader, _query_text, target_date=None):
        captured["target_date"] = target_date
        return {"success": True}

    fake_st = _FakeStreamlit()
    monkeypatch.setattr(page8_bond_quota, "st", fake_st)
    monkeypatch.setattr(page8_bond_quota, "query_bond_remaining_quota", fake_query)
    monkeypatch.setattr(page8_bond_quota, "_render_query_result", lambda _result: None)

    page8_bond_quota._render_query_area(LoaderWithDifferentArchive())

    assert captured["target_date"] is None
