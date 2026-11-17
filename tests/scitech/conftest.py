import pandas as pd
import pytest
from sqlalchemy import create_engine, text
from src.scitech.calculation import BOND_COLUMNS, FUND_COLUMNS
from src.scitech.store import ScitechStore


@pytest.fixture
def receipt():
    return {'data_date': '2026-11-13', 'parent_version': '2026-11-16T08:00:00.123456'}


@pytest.fixture
def frames():
    bonds = pd.DataFrame([
        ['2026-11-13', '自营', '自营账户', 'B1.SH', '测试科创债', 100, '2026-11-20'],
        ['2026-11-13', '做市', '做市账户', 'B1.SH', '测试科创债', 50, '2026-11-20'],
        ['2026-11-13', '其他部门', '其他账户', 'B2.IB', '普通债', 900, '2026-11-13'],
    ], columns=BOND_COLUMNS)
    funds = pd.DataFrame([
        ['2026-11-13', '其他部门', '其他账户', '589360.SH', '科创50ETF国泰', '基金', 788700],
        ['2026-11-13', '自营', '自营账户', 'F2', '科创私募', '私募基金', 99999999],
        ['2026-11-13', '自营', '自营账户', 'F3', '普通基金', '基金', 99999999],
    ], columns=FUND_COLUMNS)
    return bonds, funds


@pytest.fixture
def flags():
    return {'B1.SH': {'value': '是'}, 'B2.IB': {'value': '否'}}


@pytest.fixture
def store(receipt):
    engine = create_engine('sqlite://')
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE archive_meta (data_date TEXT PRIMARY KEY, captured_at TEXT, is_current INTEGER)'))
        conn.execute(text('INSERT INTO archive_meta VALUES (:data_date, :parent_version, 1)'), receipt)
        conn.execute(text('CREATE TABLE original_result (amount REAL)'))
        conn.execute(text('INSERT INTO original_result VALUES (12345)'))
        conn.execute(text('CREATE TABLE pretrade_current (snapshot_id TEXT)'))
        conn.execute(text("INSERT INTO pretrade_current VALUES ('unchanged')"))
    result = ScitechStore(engine)
    result.prepare()
    yield result
    engine.dispose()
