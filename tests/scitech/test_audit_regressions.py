"""审计反例：对外行为断言，覆盖部分输入失败和补跑生命周期。"""
from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import text
from src.scitech import service
from src.scitech.calculation import calculate


def encoded(frames):
    return dict(zip(('bonds', 'funds'), map(service.encode, frames)))


@pytest.mark.parametrize('missing', ['NaT', 'nan', 'NaN'])
def test_text_null_event_is_row_issue_not_batch_failure(frames, flags, missing):
    frames[0].loc[0, '回售/到期日'] = missing
    result = calculate(*frames, flags, '2026-11-13')
    assert result['bonds'][0]['监控状态'] == '预警日期待核实'
    assert len(result['alerts']) == 1


def test_non_scitech_bad_quantity_does_not_pollute_monitoring(frames, flags):
    frames[0].loc[2, '库存数量(万)_PR'] = float('nan')
    result = calculate(*frames, flags, '2026-11-13')
    assert not result['issues']
    assert result['summary']['alert_pr_wan'] == 150


@pytest.mark.parametrize('failure', ['missing', 'wrong_date', 'missing_column'])
def test_fund_input_failure_does_not_suppress_valid_bond_alerts(store, receipt, frames, flags, failure):
    data = encoded(frames)
    if failure == 'missing':
        data.pop('funds')
        data['capture_errors'] = {'funds': '底稿3读取失败'}
    elif failure == 'wrong_date':
        frames[1].loc[0, '日期'] = '2026-11-12'
        data = encoded(frames)
    else:
        data['funds'] = service.encode(frames[1].drop(columns=['库存数量']))
    outcome = service.execute_inputs(store, receipt, data, fetcher=lambda *a, **kw: flags)
    assert outcome['status'] == 'PARTIAL'
    result = store.read(**receipt)['result']
    assert result['summary']['alert_pr_wan'] == 150
    assert result['summary']['fund_shares_wan'] is None
    assert not result['funds'] and result['coverage']['fund_input_available'] is False


def test_bad_bond_input_keeps_fund_and_does_not_query_wind(store, receipt, frames):
    data = encoded(frames)
    data['bonds'] = service.encode(frames[0].drop(columns=['回售/到期日']))
    def forbidden(*a, **kw):
        pytest.fail('无有效债券输入不能查询 Wind')
    outcome = service.execute_inputs(store, receipt, data, fetcher=forbidden)
    result = store.read(**receipt)['result']
    assert outcome['status'] == 'PARTIAL'
    assert result['summary']['bond_pr_wan'] is None
    assert result['summary']['alert_pr_wan'] is None
    assert result['summary']['fund_shares_wan'] == 78.87


def test_crashed_run_exposes_interrupted_state(store, receipt, frames):
    run_id = store.begin(receipt, encoded(frames))
    old_time = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    with store.engine.begin() as conn:
        conn.execute(text('UPDATE scitech_runs SET created_at=:t WHERE run_id=:r'), {'t': old_time, 'r': run_id})
    assert store.read(**receipt)['status'] == 'INTERRUPTED'


def test_retry_running_or_superseded_attempt_cannot_hide_latest_success(store, receipt, frames, flags, monkeypatch):
    monkeypatch.setattr(service, 'fetch_flags', lambda *a, **kw: flags)
    running = store.begin(receipt, encoded(frames))
    with pytest.raises(ValueError, match='运行中'):
        service.retry(store.engine, running)
    store.finish(running, receipt, error='模拟失败')
    newest = service.execute_inputs(store, receipt, encoded(frames), fetcher=lambda *a, **kw: flags)
    with pytest.raises(ValueError, match='最新'):
        service.retry(store.engine, running)
    assert store.read(**receipt)['run_id'] == newest['run_id']
    assert store.read(**receipt)['status'] == 'READY'


def test_persistence_failure_keeps_recovery_id_and_original_error(store, receipt, frames, flags, monkeypatch, capsys):
    def unavailable(*a, **kw):
        raise RuntimeError('模拟数据库断开')
    monkeypatch.setattr(store, 'finish', unavailable)
    result = service.execute_inputs(store, receipt, encoded(frames), fetcher=lambda *a, **kw: flags)
    assert result['status'] == 'FAILED'
    assert result['run_id'] in capsys.readouterr().out
    assert '模拟数据库断开' in result['error']


def test_excluded_fund_rows_do_not_block_scitech_input(frames, flags):
    frames[1].loc[1:, '日期'] = 'bad'
    result = calculate(*frames, flags, '2026-11-13')
    assert result['summary']['fund_shares_wan'] == 78.87
    assert not result['issues']


def test_interrupted_retry_uses_saved_inputs_without_rereading_files(store, receipt, frames, flags, monkeypatch):
    run_id = store.begin(receipt, encoded(frames))
    with store.engine.begin() as conn:
        conn.execute(text('UPDATE scitech_runs SET created_at=:t'),
            {'t': (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()})
    monkeypatch.setattr(service, 'fetch_flags', lambda *a, **kw: flags)
    result = service.retry(store.engine, run_id)
    assert result['status'] == 'READY'
    current = store.read(**receipt)
    assert current['run_id'] != run_id
    assert current['inputs']['bonds'] == encoded(frames)['bonds']
    assert current['inputs']['funds'] == encoded(frames)['funds']


def test_two_retries_cannot_both_start_for_the_same_attempt(tmp_path, receipt, frames, flags, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from sqlalchemy import create_engine
    from src.scitech.store import ScitechStore
    engine = create_engine(f'sqlite:///{tmp_path / "concurrency.sqlite"}')
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE archive_meta (data_date TEXT PRIMARY KEY, captured_at TEXT)'))
        conn.execute(text('INSERT INTO archive_meta VALUES (:data_date, :parent_version)'), receipt)
    local_store = ScitechStore(engine)
    local_store.prepare()
    run_id = local_store.begin(receipt, encoded(frames))
    local_store.finish(run_id, receipt, error='first attempt failed')
    barrier = Barrier(2)
    original_get = ScitechStore.get_run
    def synchronize(self, target):
        previous = original_get(self, target)
        barrier.wait(timeout=5)
        return previous
    calls = []
    monkeypatch.setattr(ScitechStore, 'get_run', synchronize)
    monkeypatch.setattr(service, 'fetch_flags', lambda *a, **kw: calls.append('wind') or flags)
    def attempt():
        try:
            return service.retry(engine, run_id)['status']
        except ValueError as exc:
            assert '最新' in str(exc)
            return 'REJECTED'
    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: attempt(), range(2)))
    assert sorted(outcomes) == ['READY', 'REJECTED']
    assert calls == ['wind']
    assert local_store.read(**receipt)['status'] == 'READY'
    engine.dispose()


def test_clock_rollback_does_not_promote_previous_result(store, receipt, frames, flags):
    first = service.execute_inputs(store, receipt, encoded(frames), fetcher=lambda *a, **kw: flags)
    with store.engine.begin() as conn:
        conn.execute(text('UPDATE scitech_runs SET created_at=:t'),
            {'t': (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()})
    second = service.execute_inputs(store, receipt, encoded(frames), fetcher=lambda *a, **kw: flags)
    assert first['run_id'] != second['run_id']
    assert store.read(**receipt)['run_id'] == second['run_id']
