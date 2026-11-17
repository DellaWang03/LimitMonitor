from types import SimpleNamespace
import pytest
from sqlalchemy import inspect, text, create_engine
from src.scitech import service
from src.scitech.calculation import calculate
from src.scitech.store import ScitechStore


def snapshot_core(store):
    with store.engine.connect() as conn:
        return {name: conn.execute(text(f'SELECT * FROM {name}')).all()
                for name in ['archive_meta', 'original_result', 'pretrade_current']}


def inputs(frames):
    return dict(zip(['bonds', 'funds'], map(service.encode, frames)))


def test_success_is_atomic_with_own_version_and_unchanged_core(store, receipt, frames, flags):
    original = snapshot_core(store)
    outcome = service.execute_inputs(store, receipt, inputs(frames), fetcher=lambda *a, **kw: flags)
    snapshot = store.read(**receipt)
    assert outcome['status'] == snapshot['status'] == 'READY'
    assert snapshot['result']['summary']['alert_pr_wan'] == 150
    assert snapshot['result']['wind_flags'] == flags
    assert snapshot['result']['wind_queried_at']
    assert snapshot_core(store) == original


def test_wind_failure_preserves_funds_and_inputs_then_retry_replaces_only_module(store, receipt, frames, flags, monkeypatch):
    original = snapshot_core(store)
    def fail(*args, **kwargs):
        raise TimeoutError('test')
    failed = service.execute_inputs(store, receipt, inputs(frames), fetcher=fail)
    prior = store.read(**receipt)
    assert failed['status'] == 'PARTIAL'
    assert prior['result']['summary']['fund_shares_wan'] == 78.87
    assert prior['result']['coverage']['unknown_bond_codes'] == 2
    captured = prior['inputs']
    real_execute = service.execute_inputs
    def execute(store_arg, receipt_arg, inputs_arg, **kwargs):
        assert inputs_arg == captured  # 补跑不重读共享盘
        return real_execute(store_arg, receipt_arg, inputs_arg, fetcher=lambda *a, **k: flags)
    monkeypatch.setattr(service, 'execute_inputs', execute)
    service.retry(store.engine, failed['run_id'])
    current = store.read(**receipt)
    assert current['status'] == 'READY'
    assert current['result_version'] != prior['result_version']
    assert current['run_id'] != prior['run_id']
    assert snapshot_core(store) == original


def test_cross_date_fund_excluded_while_valid_bond_monitoring_continues(store, receipt, frames, flags):
    frames[1].loc[0, '日期'] = '2026-11-12'
    outcome = service.execute_inputs(store, receipt, inputs(frames), fetcher=lambda *a, **kw: flags)
    assert outcome['status'] == 'PARTIAL'
    result = store.read(**receipt)['result']
    assert result['summary']['fund_shares_wan'] is None
    assert result['summary']['alert_pr_wan'] == 150


def test_module_failure_not_fallback_to_previous_success(store, receipt, frames, flags):
    service.execute_inputs(store, receipt, inputs(frames), fetcher=lambda *a, **kw: flags)
    service.execute_inputs(store, receipt, {'capture_error': 'missing workbook3'})
    assert store.read(**receipt)['status'] == 'FAILED'
    with pytest.raises(ValueError, match='捕获不完整'):
        service.retry(store.engine, store.read(**receipt)['run_id'])


def test_changed_parent_rejects_old_result_and_retry(store, receipt, frames, flags):
    run = store.begin(receipt, inputs(frames))
    with store.engine.begin() as conn:
        conn.execute(text("UPDATE archive_meta SET captured_at='2026-11-16T09:00:00.123456'"))
    with pytest.raises(ValueError, match='跨批次'):
        store.finish(run, receipt, result=calculate(*frames, flags, receipt['data_date']))
    with pytest.raises(ValueError, match='跨批次'):
        service.retry(store.engine, run)
    new_receipt = {**receipt, 'parent_version': '2026-11-16T09:00:00.123456'}
    assert store.read(**new_receipt) is None
    with pytest.raises(ValueError, match='跨批次'):
        store.read(**receipt)


def test_failed_write_rolls_back_and_previous_result_never_partial(store, receipt, frames, flags):
    run = store.begin(receipt, inputs(frames))
    invalid = calculate(*frames, flags, receipt['data_date'])
    invalid['summary']['bond_pr_wan'] = float('nan')
    with pytest.raises(ValueError):
        store.finish(run, receipt, result=invalid)
    row = store.get_run(run)
    assert row['status'] == 'RUNNING' and row['result'] is None


def test_read_of_uninitialized_db_does_not_create_any_table(receipt):
    engine = create_engine('sqlite://')
    assert ScitechStore(engine).read(**receipt) is None
    assert inspect(engine).get_table_names() == []


def test_extension_only_reads_fund_workbook_and_captured_bonds(store, receipt, frames, flags, tmp_path):
    path = tmp_path / 'funds.xlsx'
    frames[1].to_excel(path, sheet_name='基金持仓明细表', index=False)
    def data_path(name):
        assert name == '统计报表底稿3_股基产.xlsx'
        return path
    config = SimpleNamespace(get_data_file_path=data_path, get=lambda k, default: default)
    runtime = SimpleNamespace(stage1_processor=SimpleNamespace(_scitech_bond_input=frames[0]))
    result = service.run_extension(runtime, config, receipt, store.engine, fetcher=lambda *a, **kw: flags)
    assert result['status'] == 'READY'
    assert store.read(**receipt)['inputs']['fund_source']['sha256']


def test_missing_bond_capture_stays_local_failure(store, receipt):
    config = SimpleNamespace(get=lambda k, default: default)
    result = service.run_extension(SimpleNamespace(stage1_processor=object()), config, receipt, store.engine)
    assert result['status'] == 'FAILED'
    assert '未捕获' in store.read(**receipt)['error']
