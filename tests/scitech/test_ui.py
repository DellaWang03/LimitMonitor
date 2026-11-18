import pytest
from streamlit.testing.v1 import AppTest
from src.scitech.calculation import calculate


def page_app(snapshot):
    from types import SimpleNamespace
    from src.visualization.pages import page11_scitech as page
    page.load_snapshot = lambda loader: snapshot
    loader = SimpleNamespace(get_snapshot_identity=lambda: {
        'data_date': '2026-11-13', 'parent_version': 'parent'})
    page.render({}, loader)


def snapshot(frames, flags):
    return {'status': 'READY', 'result_version': 'test', 'result': calculate(*frames, flags, '2026-11-13')}


def cards(app):
    return [e.value for e in app.markdown if 'min-height:' in e.value and 'border-radius: 12px' in e.value]


def test_global_kpis_stay_fixed_when_detail_filters_change(frames, flags, monkeypatch):
    from src.visualization.pages import page11_scitech as page
    monkeypatch.setattr(page, 'load_snapshot', page.load_snapshot)  # restore after AppTest
    app = AppTest.from_function(page_app, args=(snapshot(frames, flags),)).run()
    assert not app.exception
    original_cards = cards(app)
    assert len(original_cards) == 4
    assert '150.00' in original_cards[0] and '78.87' in original_cards[1]
    assert len(app.dataframe[0].value) == 2
    app.multiselect[0].set_value(['做市']).run()
    assert not app.exception and cards(app) == original_cards
    assert len(app.dataframe[0].value) == 1
    assert app.dataframe[0].value.iloc[0]['部门'] == '做市'
    app.text_input[0].set_value('no-match').run()
    assert not app.exception and len(app.dataframe) == 0


@pytest.mark.parametrize('state,message', [(None, '暂无科创监控数据'), ('RUNNING', '正在更新'),
                                          ('INTERRUPTED', '更新未完成'), ('FAILED', '更新失败')])
def test_unavailable_not_rendered_as_zero_or_no_alert(state, message, monkeypatch):
    from src.visualization.pages import page11_scitech as page
    monkeypatch.setattr(page, 'load_snapshot', page.load_snapshot)
    data = None if state is None else {'status': state}
    app = AppTest.from_function(page_app, args=(data,)).run()
    assert not app.exception and not cards(app)
    assert any(message in e.value for e in list(app.info) + list(app.error))


def test_unknown_bond_flags_show_unknown_but_fund_still_available(frames, monkeypatch):
    from src.visualization.pages import page11_scitech as page
    monkeypatch.setattr(page, 'load_snapshot', page.load_snapshot)
    data = snapshot(frames, {})
    data['status'] = 'PARTIAL'
    app = AppTest.from_function(page_app, args=(data,)).run()
    assert not app.exception
    assert '待核实' in cards(app)[0] and '78.87' in cards(app)[1]
    assert '待核实' in cards(app)[2] and '待核实' in cards(app)[3]
    assert len(app.warning) == 1
    assert '2 只债券的科创分类暂不可用' in app.warning[0].value
    assert '补查' in app.warning[0].value


@pytest.mark.parametrize('broken,unavailable_cards', [('funds', [1]), ('bonds', [0, 2, 3])])
def test_missing_input_is_unavailable_without_hiding_valid_asset_section(
        store, receipt, frames, flags, monkeypatch, broken, unavailable_cards):
    from src.scitech import service
    from src.visualization.pages import page11_scitech as page
    monkeypatch.setattr(page, 'load_snapshot', page.load_snapshot)
    inputs = dict(zip(['bonds', 'funds'], map(service.encode, frames)))
    inputs.pop(broken)
    service.execute_inputs(store, receipt, inputs, fetcher=lambda *a, **kw: flags)
    app = AppTest.from_function(page_app, args=(store.read(**receipt),)).run()
    assert not app.exception
    for index in unavailable_cards:
        assert '不可用' in cards(app)[index]
    if broken == 'funds':
        assert '150.00' in cards(app)[0] and '150.00' in cards(app)[3]
        assert '不影响债券提醒' in app.warning[0].value
        assert any('基金持仓数据暂不可用' in item.value for item in app.info)
    else:
        assert '78.87' in cards(app)[1]
        assert any('债券持仓数据暂不可用' in item.value for item in app.info)


@pytest.mark.parametrize('page_name,module_name', [
    ('单一信用限额', 'page1_single_credit'), ('特定信用限额', 'page2_specific_credit'),
    ('分类信用限额', 'page3_category_credit'), ('专业担保明细', 'page4_guarantee'),
    ('高风险类明细', 'page5_high_risk'), ('地域类明细', 'page6_regional'),
    ('高收益明细', 'page7_high_yield'), ('单券可购额度查询', 'page8_bond_quota'),
    ('债券组合超限试算', 'page10_basket_pretrade'),
])
def test_existing_routes_work_even_if_scitech_dependency_breaks(monkeypatch, page_name, module_name):
    import builtins
    import importlib
    import streamlit as st
    from src.visualization.components import sidebar, filters
    from src.visualization import data_loader
    monkeypatch.setattr(sidebar, 'render_sidebar', lambda *a: (page_name, None))
    monkeypatch.setattr(filters, 'render_top_filters', lambda *a: {})
    monkeypatch.setattr(data_loader, 'DataLoader', lambda **kw: object())
    module = importlib.import_module(f'src.visualization.pages.{module_name}')
    monkeypatch.setattr(module, 'render', lambda *a: st.write(f'{page_name}原路由正常'))
    original_import = builtins.__import__
    def guarded(name, *args, **kwargs):
        if name.startswith('src.scitech'):
            raise ImportError('科创依赖不可用')
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', guarded)
    app = AppTest.from_file('app.py').run()
    assert not app.exception and not app.error
    assert any(f'{page_name}原路由正常' in item.value for item in app.markdown)


def test_business_copy_and_beijing_timestamp(frames, flags, monkeypatch):
    from src.visualization.pages import page11_scitech as page
    monkeypatch.setattr(page, 'load_snapshot', page.load_snapshot)
    data = snapshot(frames, flags)
    data['result']['wind_queried_at'] = '2026-11-13T18:30:00+00:00'
    app = AppTest.from_function(page_app, args=(data,)).run()
    assert not app.exception
    captions = '\n'.join(item.value for item in app.caption)
    assert '2026-11-14 02:30（北京时间）' in captions
    assert '分类查询时间' in captions and '分类更新时间' not in captions
    assert 'UTC' not in captions
    assert all('源行号' not in table.value.columns for table in app.dataframe)
    assert all('识别依据' not in table.value.columns for table in app.dataframe)
    assert data['result']['bonds'][0]['源行号'] == 2  # presentation must not mutate saved results


def test_download_contains_business_fields_and_preserves_filtered_values(frames, flags, monkeypatch):
    import pandas as pd
    from io import BytesIO
    from types import SimpleNamespace
    from src.visualization.pages import page11_scitech as page
    captured = {}
    monkeypatch.setattr(page, 'st', SimpleNamespace(
        caption=lambda *a: None, dataframe=lambda *a, **kw: None,
        column_config=page.st.column_config,
        download_button=lambda label, data, **kw: captured.update(data=data, **kw)))
    rows = snapshot(frames, flags)['result']['bonds']
    page._table(rows, 'bonds', '2026-11-13', ['做市'], [], '', '')
    exported = pd.read_csv(BytesIO(captured['data']))
    assert captured['file_name'] == '科创资产_债券持仓_2026-11-13.csv'
    assert exported['PR后券面(万元)'].tolist() == [50]
    assert not {'源行号', '识别依据', '科创标识'} & set(exported.columns)
    assert 'scitechbondornot' not in captured['data'].decode('utf-8-sig')


@pytest.mark.parametrize('error_type', [FileNotFoundError, RuntimeError])
def test_global_error_details_are_logged_not_displayed(monkeypatch, caplog, error_type):
    from src.visualization import data_loader
    from src.visualization.components import sidebar
    monkeypatch.setattr(sidebar, 'render_sidebar', lambda *a: ('科创资产监控', None))
    def unavailable(*a, **kw):
        raise error_type('internal-path-and-diagnostic-detail')
    monkeypatch.setattr(data_loader, 'DataLoader', unavailable)
    app = AppTest.from_file('app.py').run()
    assert not app.exception
    assert app.error and not app.code
    assert all('internal-path-and-diagnostic-detail' not in item.value for item in app.error)
    assert 'internal-path-and-diagnostic-detail' in caplog.text
