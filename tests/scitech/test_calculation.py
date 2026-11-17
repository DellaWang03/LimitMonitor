import pandas as pd
import pytest
from pandas.testing import assert_frame_equal
from src.scitech.calculation import calculate


def test_scope_units_and_no_input_mutation(frames, flags):
    bonds, funds = frames
    originals = [f.copy(deep=True) for f in frames]
    result = calculate(bonds, funds, flags, '2026-11-13')
    assert result['summary'] == {'bond_pr_wan': 150, 'fund_shares_wan': 78.87,
                                  'alert_bond_count': 1, 'alert_pr_wan': 150}
    assert len(result['bonds']) == 2  # 同券跨部门不丢行、不重复读底稿2
    assert {r['部门'] for r in result['bonds']} == {'做市', '自营'}
    assert [r['资产代码'] for r in result['funds']] == ['589360.SH']
    assert '回售/到期日' not in result['funds'][0]
    assert not result['issues']
    for original, actual in zip(originals, frames):
        assert_frame_equal(original, actual)


@pytest.mark.parametrize('event,status,alert', [
    ('2026-11-12', '日期已过，待核对', False),
    ('2026-11-13', '持仓日当日回售/到期', True),
    ('2026-11-14', '七日内回售/到期', True),
    ('2026-11-20', '七日内回售/到期', True),
    ('2026-11-21', '未进入七日提醒', False),
    (None, '预警日期待核实', False),
    ('无日期', '预警日期待核实', False),
])
def test_calendar_day_boundaries_use_holding_date_and_only_agreed_column(frames, flags, event, status, alert):
    bonds, funds = frames
    bonds = bonds.iloc[:1].copy()
    bonds['回售/到期日'] = event
    bonds['到期日期'] = '2026-11-13'
    bonds['回售日'] = '2026-11-14'
    result = calculate(bonds, funds, flags, '2026-11-13')
    assert result['bonds'][0]['监控状态'] == status
    assert bool(result['alerts']) is alert
    assert not {'到期日期', '回售日'} & result['bonds'][0].keys()


@pytest.mark.parametrize('value', [None, '', 'Y', 1, float('nan')])
def test_unknown_classification_never_becomes_no_or_healthy_zero(frames, flags, value):
    flags['B1.SH'] = {'value': value}
    result = calculate(*frames, flags, '2026-11-13')
    assert not result['bonds'] and not result['alerts']
    assert result['coverage']['unknown_bond_codes'] == 1
    assert len(result['issues']) == 2
    assert result['summary']['fund_shares_wan'] == 78.87


@pytest.mark.parametrize('quantity,status', [(None, '持仓数量待核实'), (-10, '负持仓，待核对'), ('bad', '持仓数量待核实')])
def test_invalid_or_negative_position_never_alerts(frames, flags, quantity, status):
    bonds, funds = frames
    bonds = bonds.iloc[:1].copy().astype({'库存数量(万)_PR': object})
    bonds.loc[0, '库存数量(万)_PR'] = quantity
    result = calculate(bonds, funds, flags, '2026-11-13')
    assert result['bonds'][0]['监控状态'] == status
    assert result['issues'] and not result['alerts']
    assert result['summary']['bond_pr_wan'] == (-10 if quantity == -10 else 0)


def test_zero_position_not_unknown_or_alert(frames):
    bonds, funds = frames
    bonds['库存数量(万)_PR'] = 0
    funds['库存数量'] = 0
    result = calculate(bonds, funds, {}, '2026-11-13')
    assert not result['issues'] and not result['bonds'] and not result['funds']
    assert result['summary']['bond_pr_wan'] == 0


@pytest.mark.parametrize('kind', ['missing_column', 'different_date', 'invalid_date'])
def test_incompatible_input_rejected(frames, flags, kind):
    bonds, funds = frames
    if kind == 'missing_column':
        bonds = bonds.drop(columns=['回售/到期日'])
    else:
        funds.loc[0, '日期'] = '2026-11-12' if kind == 'different_date' else 'bad'
    with pytest.raises(ValueError):
        calculate(bonds, funds, flags, '2026-11-13')


def test_any_fund_name_containing_keyword_in_exact_asset_class(frames, flags):
    bonds, funds = frames
    funds.loc[0, ['资产代码', '名称', '库存数量']] = ['NEW.OF', '新科创混合', 30000]
    result = calculate(bonds, funds, flags, '2026-11-13')
    assert result['summary']['fund_shares_wan'] == 3
    assert result['funds'][0]['资产代码'] == 'NEW.OF'
