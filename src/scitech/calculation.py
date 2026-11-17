"""纯计算：只读输入，不执行文件、网络或数据库操作。"""
from __future__ import annotations

from numbers import Number
import math
import pandas as pd

BOND_COLUMNS = ['日期', '部门', '内部证券账户名称', '资产代码', '资产名称', '库存数量(万)_PR', '回售/到期日']
FUND_COLUMNS = ['日期', '部门', '内部证券账户名称', '资产代码', '名称', '资产种类', '库存数量']
RULE_VERSION = 'scitech-v2'
ALERTS = {'七日内回售/到期', '持仓日当日回售/到期'}


def clean(value):
    return '' if pd.isna(value) else str(value).strip()


def day(value):
    if isinstance(value, Number) or not clean(value):
        return pd.NaT
    try:
        parsed = pd.Timestamp(value)
        return parsed.normalize() if not pd.isna(parsed) and parsed.tz is None else pd.NaT
    except (ValueError, TypeError):
        return pd.NaT


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) and not isinstance(value, bool) else None
    except (ValueError, TypeError, OverflowError):
        return None


def validate(frame, columns, business_date, label):
    missing = set(columns) - set(frame.columns)
    if missing:
        raise ValueError(f'{label}缺少字段: {sorted(missing)}')
    checked = frame
    if label == '基金':
        # 不让明确不在范围内的私募基金/普通基金异常污染科创结果。
        names = frame['名称'].map(clean)
        checked = frame.loc[frame['资产种类'].map(clean).eq('基金') &
                            (names.str.contains('科创', regex=False) | names.eq(''))]
    dates = checked['日期'].map(day)
    if dates.isna().any() or (dates != business_date).any():
        raise ValueError(f'{label}持仓日期与主快照 {business_date.date()} 不一致或不可解析')


def calculate(bonds, funds, flags, data_date):
    business_date = day(data_date)
    if pd.isna(business_date):
        raise ValueError('无效持仓日期')
    validate(bonds, BOND_COLUMNS, business_date, '债券')
    validate(funds, FUND_COLUMNS, business_date, '基金')
    bond_rows, fund_rows, issues = [], [], []
    unknown_bond_codes = set()

    def issue(row, reason):
        issues.append({**row, '待核实原因': reason})

    for position, (_, source) in enumerate(bonds.iterrows(), 2):
        row = {k: clean(source[k]) for k in ['部门', '内部证券账户名称', '资产代码', '资产名称']}
        row.update({'日期': str(business_date.date()), '源行号': position, '资产类型': '债券'})
        row['资产代码'] = row['资产代码'].upper()
        qty = number(source['库存数量(万)_PR'])
        row['PR后券面(万元)'] = qty
        if qty == 0:
            continue
        flag = flags.get(row['资产代码'], {})
        value = flag.get('value')
        if value == '否':
            continue
        if qty is None:
            issue(row, 'PR后券面缺失或非法')
        if value not in ('是', '否'):
            unknown_bond_codes.add(row['资产代码'])
            issue(row, flag.get('error') or 'Wind科创标识待核实')
            continue
        expiry = day(source['回售/到期日'])
        days = None if pd.isna(expiry) else int((expiry - business_date).days)
        status = ('预警日期待核实' if days is None else '日期已过，待核对' if days < 0
                  else '持仓日当日回售/到期' if days == 0 else '七日内回售/到期' if days <= 7
                  else '未进入七日提醒')
        if qty is None:
            status = '持仓数量待核实'
        elif qty < 0:
            status = '负持仓，待核对'
        row.update({'科创标识': value, '识别依据': 'Wind scitechbondornot',
                    '回售/到期日': None if pd.isna(expiry) else str(expiry.date()),
                    '剩余天数': days, '监控状态': status})
        bond_rows.append(row)
        if status in {'预警日期待核实', '日期已过，待核对', '负持仓，待核对'}:
            issue(row, status)

    for position, (_, source) in enumerate(funds.iterrows(), 2):
        if clean(source['资产种类']) != '基金':
            continue
        name = clean(source['名称'])
        if name and '科创' not in name:
            continue
        qty = number(source['库存数量'])
        if qty == 0:
            continue
        row = {k: clean(source[k]) for k in ['部门', '内部证券账户名称', '资产代码']}
        row.update({'日期': str(business_date.date()), '源行号': position, '资产类型': '基金',
                    '资产代码': row['资产代码'].upper(), '资产名称': name,
                    '持仓份额(万份)': None if qty is None else qty / 10000,
                    '识别依据': '资产种类=基金，名称含科创'})
        if not name:
            issue(row, '基金名称缺失，无法识别'); continue
        fund_rows.append(row)
        if qty is None or qty < 0 or not row['资产代码']:
            issue(row, '基金数量或代码待核实')

    alert_rows = sorted([r for r in bond_rows if r['监控状态'] in ALERTS], key=lambda r: r['剩余天数'])
    return {'rule_version': RULE_VERSION, 'data_date': str(business_date.date()),
            'bonds': bond_rows, 'funds': fund_rows, 'alerts': alert_rows, 'issues': issues,
            'coverage': {'unknown_bond_codes': len(unknown_bond_codes),
                         'bond_issues': sum(r['资产类型'] == '债券' for r in issues),
                         'fund_issues': sum(r['资产类型'] == '基金' for r in issues)},
            'summary': {'bond_pr_wan': sum(r['PR后券面(万元)'] or 0 for r in bond_rows),
                        'fund_shares_wan': sum(r['持仓份额(万份)'] or 0 for r in fund_rows),
                        'alert_bond_count': len({r['资产代码'] for r in alert_rows}),
                        'alert_pr_wan': sum(r['PR后券面(万元)'] for r in alert_rows)}}
