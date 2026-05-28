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
