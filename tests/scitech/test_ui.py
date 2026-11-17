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
    return [e.value for e in app.markdown if 'min-height: 136px' in e.value]


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


@pytest.mark.parametrize('state,message', [(None, '尚未生成'), ('RUNNING', '尚未完成'),
                                          ('INTERRUPTED', '可能已中断'), ('FAILED', '生成失败')])
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
    assert len(app.warning) == 1


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
        assert any('基金输入不可用' in item.value for item in app.info)
    else:
        assert '78.87' in cards(app)[1]
        assert any('债券输入不可用' in item.value for item in app.info)


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
