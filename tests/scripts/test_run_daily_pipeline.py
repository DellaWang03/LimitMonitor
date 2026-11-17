from __future__ import annotations

import io
from pathlib import Path
import sys
from types import SimpleNamespace
import pytest

from scripts import run_daily_pipeline as daily


def _install_dependencies(monkeypatch, *, archive_error=None, publish_error=None, display_error=None):
    calls: list[str] = []
    config = SimpleNamespace(get_data_dir=lambda: Path("/tmp/source"))
    runtime = SimpleNamespace()

    class FakeStore:
        def prepare_schema(self):
            return None

        def publish_current(self, snapshot_id):
            calls.append("publish_current")
            assert snapshot_id == "snapshot"
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
        lambda runtime, store: calls.append("build") or "snapshot",
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

    assert calls == [
        "validate",
        "runtime",
        "build",
        "archive",
        "publish_current",
        "display",
    ]


def test_daily_pipeline_console_output_is_cp936_safe(monkeypatch) -> None:
    _install_dependencies(monkeypatch)
    output = io.BytesIO()
    console = io.TextIOWrapper(output, encoding="cp936", errors="strict")
    monkeypatch.setattr(sys, "stdout", console)

    assert daily.main(["--archive-date", "2026-07-15"]) == 0
    console.flush()


def test_archive_failure_does_not_publish_pretrade_pointer(monkeypatch) -> None:
    calls = _install_dependencies(monkeypatch, archive_error=RuntimeError("archive"))

    assert daily.main(["--archive-date", "2026-07-15"]) == 1

    assert calls == ["validate", "runtime", "build", "archive"]


def test_publish_failure_does_not_generate_display_snapshot(monkeypatch) -> None:
    calls = _install_dependencies(monkeypatch, publish_error=RuntimeError("publish"))

    assert daily.main(["--archive-date", "2026-07-15"]) == 1

    assert calls == ["validate", "runtime", "build", "archive", "publish_current"]


def test_display_failure_keeps_published_data_and_returns_nonzero(monkeypatch) -> None:
    calls = _install_dependencies(monkeypatch, display_error=RuntimeError("display"))

    assert daily.main(["--archive-date", "2026-07-15"]) == 2

    assert calls == [
        "validate",
        "runtime",
        "build",
        "archive",
        "publish_current",
        "display",
    ]


@pytest.mark.parametrize('module_status,display_error,expected', [
    ('READY', None, 0), ('PARTIAL', None, 3), ('FAILED', None, 3),
    (RuntimeError('Wind unavailable'), None, 3),
    ('READY', RuntimeError('display failed'), 2),
])
@pytest.mark.parametrize('console_encoding', ['utf-8', 'cp936'])
def test_scitech_runs_after_core_publication_and_cannot_undo_it(monkeypatch, module_status, display_error, expected, console_encoding):
    from src.scitech import service
    output = io.BytesIO()
    console = io.TextIOWrapper(output, encoding=console_encoding, errors='strict')
    monkeypatch.setattr(sys, 'stdout', console)
    calls = _install_dependencies(monkeypatch, display_error=display_error)
    config = SimpleNamespace(get_data_dir=lambda: Path('/tmp/source'), get=lambda k, default: True)
    monkeypatch.setattr(daily, 'get_config', lambda: config)
    receipt_value = {'data_date': '2026-07-10', 'parent_version': '2026-07-15T10:20:00.123456'}
    def archive(date, *, receipt):
        calls.append('archive')
        assert date == '2026-07-15'
        receipt.update(receipt_value)
        return 0
    def extension(runtime, config, receipt, engine):
        calls.append('scitech')
        assert receipt == receipt_value  # 不用运行日期，也不事后读 global current
        if isinstance(module_status, Exception):
            raise module_status
        return {'status': module_status}
    monkeypatch.setattr(daily, 'archive_to_db', archive)
    monkeypatch.setattr(service, 'run_extension', extension)
    assert daily.main(['--archive-date', '2026-07-15']) == expected
    assert calls == ['validate', 'runtime', 'build', 'archive', 'publish_current', 'display', 'scitech']
    console.flush()
    assert '科创监控' in output.getvalue().decode(console_encoding)


def test_new_module_import_failure_does_not_prevent_core_publication(monkeypatch):
    import builtins
    calls = _install_dependencies(monkeypatch)
    monkeypatch.setattr(daily, 'get_config', lambda: SimpleNamespace(
        get_data_dir=lambda: Path('/tmp/source'), get=lambda k, default: True))
    def archive(date, **kwargs):
        calls.append('archive')
        return 0
    monkeypatch.setattr(daily, 'archive_to_db', archive)
    original_import = builtins.__import__
    def guarded(name, *args, **kwargs):
        if name.startswith('src.scitech'):
            raise ImportError('module unavailable')
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', guarded)
    assert daily.main(['--archive-date', '2026-07-15']) == 3
    assert calls == ['validate', 'runtime', 'build', 'archive', 'publish_current', 'display']


@pytest.mark.parametrize('setting', ['false', RuntimeError('科创配置读取失败')])
def test_invalid_optional_configuration_does_not_block_existing_publication(monkeypatch, setting):
    calls = _install_dependencies(monkeypatch)
    def get_setting(*args):
        if isinstance(setting, Exception):
            raise setting
        return setting
    monkeypatch.setattr(daily, 'get_config', lambda: SimpleNamespace(
        get_data_dir=lambda: Path('/tmp/source'), get=get_setting))
    assert daily.main(['--archive-date', '2026-07-15']) == 3
    assert calls == ['validate', 'runtime', 'build', 'archive', 'publish_current', 'display']
