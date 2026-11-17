from types import SimpleNamespace
import subprocess
import pytest
from src.scitech import wind


def response(codes, data, error=0, fields=None):
    return SimpleNamespace(Codes=codes, Data=[data], Fields=fields or ['SCITECHBONDORNOT'], ErrorCode=error)


def test_wind_uses_proven_field_handles_reordering_and_missing_codes():
    def wss(codes, field):
        assert codes == 'A,B,C,D' and field == 'scitechbondornot'
        return response(['C', 'A', 'B'], [None, '是', '否'])
    flags = wind.query(SimpleNamespace(wss=wss), ['A', 'B', 'C', 'D'])
    assert [flags[k]['value'] for k in ['A', 'B', 'C', 'D']] == ['是', '否', None, None]
    assert flags['C']['error'] and flags['D']['error']


def test_batch_error_remains_unknown_and_other_batches_continue():
    calls = []
    def wss(codes, field):
        batch = codes.split(',')
        calls.append(batch)
        return response(batch, ['否'] * len(batch), error=-1 if len(calls) == 1 else 0)
    result = wind.query(SimpleNamespace(wss=wss), [str(n) for n in range(101)])
    assert len(calls) == 2 and len(calls[0]) == 100
    assert result['0']['value'] is None and result['100']['value'] == '否'


@pytest.mark.parametrize('bad', [response(['A', 'A'], ['是', '否']), response(['B'], ['是']),
                                 response(['A'], []), response(['A'], ['是'], fields=['WRONG'])])
def test_ambiguous_wind_response_fails_explicitly(bad):
    result = wind.query(SimpleNamespace(wss=lambda *a: bad), ['A'])
    assert result['A']['value'] is None and result['A']['error']


def test_exception_in_one_batch_preserves_valid_earlier_and_later_batches():
    calls = []
    def wss(codes, field):
        batch = codes.split(',')
        calls.append(batch)
        if len(calls) == 2:
            raise RuntimeError('模拟单批取数异常')
        return response(batch, ['是'] * len(batch))
    result = wind.query(SimpleNamespace(wss=wss), [str(i) for i in range(201)])
    assert len(calls) == 3
    assert result['0']['value'] == result['200']['value'] == '是'
    assert all(result[str(i)]['value'] is None for i in range(100, 200))


def test_native_timeout_is_bounded(monkeypatch):
    def fail(*args, **kwargs):
        assert kwargs['timeout'] == 3
        assert kwargs['env']['PYTHONIOENCODING'] == 'utf-8'  # Windows 中文“是/否”也固定 UTF-8
        raise subprocess.TimeoutExpired('wind', 3)
    monkeypatch.setattr(wind.subprocess, 'run', fail)
    with pytest.raises(RuntimeError, match='超时'):
        wind.fetch_flags(['A'], timeout=3)


def test_import_module_does_not_load_wind_sdk():
    completed = subprocess.run([wind.sys.executable, '-c',
        "import sys; import src.scitech.service; import src.visualization.pages.page11_scitech; assert 'WindPy' not in sys.modules"],
        capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
