from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from scripts import run_daily_pipeline as daily


def _install_dependencies(monkeypatch, *, archive_error=None, publish_error=None, display_error=None):
    calls: list[str] = []
    config = SimpleNamespace(get_data_dir=lambda: Path("/tmp/source"))
    runtime = SimpleNamespace()

    class FakeStore:
        def prepare_schema(self):
            return None

        def publish(self, snapshot_id, usage):
            calls.append("publish")
            assert snapshot_id == "snapshot"
            assert usage == "PROD"
            if publish_error:
                raise publish_error

    monkeypatch.setattr(daily, "get_config", lambda: config)
    monkeypatch.setattr(
        daily,
        "validate_current_inputs",
        lambda config, target_date, environment: calls.append("validate"),
    )
    monkeypatch.setattr(
        daily,
        "run_daily_runtime",
        lambda **kwargs: calls.append("runtime") or runtime,
    )
    monkeypatch.setattr(
        daily.ArchiveDB,
        "from_env",
        classmethod(lambda cls: SimpleNamespace(engine=object())),
    )
    monkeypatch.setattr(daily, "PretradeContextStore", lambda engine: FakeStore())
    monkeypatch.setattr(
        daily,
        "build_ready_context",
        lambda runtime, store, **kwargs: calls.append("build") or "snapshot",
    )

    def archive(archive_date):
        calls.append("archive")
        assert archive_date == "2026-07-15"
        if archive_error:
            raise archive_error
        return 0

    monkeypatch.setattr(daily, "archive_to_db", archive)

    def display(snapshot_dir):
        calls.append("display")
        assert snapshot_dir == daily.CURRENT_DIR / "display_snapshots"
        if display_error:
            raise display_error

    monkeypatch.setattr(daily, "write_display_snapshots", display)
    return calls


def test_daily_pipeline_uses_the_required_success_sequence(monkeypatch) -> None:
    calls = _install_dependencies(monkeypatch)

    assert daily.main(["--archive-date", "2026-07-15"]) == 0

    assert calls == ["validate", "runtime", "build", "archive", "publish", "display"]


def test_archive_failure_does_not_publish_pretrade_pointer(monkeypatch) -> None:
    calls = _install_dependencies(monkeypatch, archive_error=RuntimeError("archive"))

    assert daily.main(["--archive-date", "2026-07-15"]) == 1

    assert calls == ["validate", "runtime", "build", "archive"]


def test_publish_failure_does_not_generate_display_snapshot(monkeypatch) -> None:
    calls = _install_dependencies(monkeypatch, publish_error=RuntimeError("publish"))

    assert daily.main(["--archive-date", "2026-07-15"]) == 1

    assert calls == ["validate", "runtime", "build", "archive", "publish"]


def test_display_failure_keeps_published_data_and_returns_nonzero(monkeypatch) -> None:
    calls = _install_dependencies(monkeypatch, display_error=RuntimeError("display"))

    assert daily.main(["--archive-date", "2026-07-15"]) == 2

    assert calls == ["validate", "runtime", "build", "archive", "publish", "display"]
