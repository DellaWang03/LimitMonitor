import pandas as pd
from pandas.testing import assert_frame_equal
from src.risk_core.position_context import normalize_bond_position
from src.stage1.stage1_processor import Stage1Processor


def test_capture_preserves_existing_schema_values_and_is_independent(monkeypatch, frames):
    raw = frames[0].copy()
    raw['到期日期'] = '2099-01-01'
    raw['回售日'] = '2098-01-01'
    raw['库存数量(万)'] = raw['库存数量(万)_PR'] * 2
    expected = normalize_bond_position(raw)
    processor = object.__new__(Stage1Processor)
    processor._data_file_path = lambda name: name
    reads = []
    def read(path, *, sheet_name):
        reads.append((path, sheet_name))
        return raw
    monkeypatch.setattr(pd, 'read_excel', read)
    actual = processor.query_bond_position()
    assert_frame_equal(expected, actual, check_exact=True)
    assert reads == [('统计报表底稿1_债券.xlsx', '债券持仓明细表')]
    assert not {'回售日', '到期日期'} & set(processor._scitech_bond_input.columns)
    processor._scitech_bond_input.loc[0, '库存数量(万)_PR'] = 100000
    assert_frame_equal(expected, actual, check_exact=True)
    assert raw.loc[0, '库存数量(万)_PR'] == 100


def test_missing_new_column_does_not_break_existing_bond_processing(monkeypatch, frames):
    raw = frames[0].drop(columns=['回售/到期日'])
    processor = object.__new__(Stage1Processor)
    processor._data_file_path = lambda name: name
    monkeypatch.setattr(pd, 'read_excel', lambda *a, **kw: raw)
    assert_frame_equal(processor.query_bond_position(), normalize_bond_position(raw), check_exact=True)
