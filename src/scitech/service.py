"""科创分支编排。异常仅影响本模块；保存输入后才访问 Wind。"""
from hashlib import sha256
from io import BytesIO
from datetime import datetime, timezone
import json
import pandas as pd

from .calculation import BOND_COLUMNS, FUND_COLUMNS, calculate, clean, validate, day
from .store import ScitechStore
from .wind import fetch_flags


def encode(frame):
    return json.loads(frame.to_json(orient='split', date_format='iso', force_ascii=False, double_precision=15))


def decode(value):
    return pd.DataFrame(value['data'], columns=value['columns'])


def _validated_inputs(inputs, business_date):
    frames, errors = {}, {}
    for key, columns, label in [('bonds', BOND_COLUMNS, '债券'), ('funds', FUND_COLUMNS, '基金')]:
        try:
            error = inputs.get('capture_error') or inputs.get('capture_errors', {}).get(key)
            if error:
                raise ValueError(error)
            frame = decode(inputs[key])
            validate(frame, columns, business_date, label)
            frames[key] = frame
        except Exception as exc:
            frames[key] = pd.DataFrame(columns=columns)
            errors[key] = f'{type(exc).__name__}: {exc}'
    return frames, errors


def execute_inputs(store, receipt, inputs, timeout=90, fetcher=None, *, retry_of=None):
    fetcher = fetcher or fetch_flags
    run_id = store.begin(receipt, inputs, timeout=timeout, retry_of=retry_of)
    print(f'科创监控已保存输入，run_id={run_id}', flush=True)
    try:
        business_date = day(receipt['data_date'])
        if pd.isna(business_date):
            raise ValueError('无效持仓日期')
        frames, errors = _validated_inputs(inputs, business_date)
        if len(errors) == 2:
            raise ValueError('；'.join(errors.values()))
        bonds, funds = frames['bonds'], frames['funds']
        codes = sorted({clean(c).upper() for c in bonds['资产代码'] if clean(c)})
        queried_at = datetime.now(timezone.utc).isoformat() if codes else None
        try:
            flags = fetcher(codes, timeout=timeout) if codes else {}
        except Exception as exc:
            # 分类暂不可用时，基金和已知持仓仍可展示；不能把未知当作“否”。
            flags = {c: {'value': None, 'error': f'Wind分类暂不可用：{type(exc).__name__}: {exc}'} for c in codes}
        result = calculate(bonds, funds, flags, receipt['data_date'])
        # 包含“否”的完整原始分类快照，历史查看不重查 Wind。
        result['wind_flags'] = flags
        result['wind_queried_at'] = queried_at
        result['input_errors'] = errors
        for key, label, summary_fields in [
            ('bonds', '债券', ['bond_pr_wan', 'alert_pr_wan', 'alert_bond_count']),
            ('funds', '基金', ['fund_shares_wan'])]:
            prefix = 'bond' if key == 'bonds' else 'fund'
            result['coverage'][f'{prefix}_input_available'] = key not in errors
            if key in errors:
                result['issues'].append({'日期': receipt['data_date'], '部门': '',
                    '内部证券账户名称': '', '资产代码': '', '资产名称': f'{label}底稿',
                    '资产类型': label, '待核实原因': f'{label}输入不可用，请核查底稿文件、字段及持仓日期'})
                result['coverage'][f'{prefix}_issues'] += 1
                for field in summary_fields:
                    result['summary'][field] = None
        store.finish(run_id, receipt, result=result)
        return {'run_id': run_id, 'status': 'PARTIAL' if result['issues'] else 'READY'}
    except Exception as exc:
        error = f'{type(exc).__name__}: {exc}'
        outcome = {'run_id': run_id, 'status': 'FAILED', 'error': error}
        try:
            store.finish(run_id, receipt, error=error)
        except Exception as persist_error:
            outcome['persistence_error'] = f'{type(persist_error).__name__}: {persist_error}'
        return outcome


def run_extension(runtime, config, receipt, engine, fetcher=None):
    store = ScitechStore(engine)
    store.prepare()
    inputs = {'capture_errors': {}}
    try:
        processor = runtime.stage1_processor
        raw = getattr(processor, '_scitech_bond_input', None)
        if raw is None:
            raise ValueError('本批次未捕获债券原始输入，不能重读共享盘冒充原批次')
        inputs['bonds'] = encode(raw)
    except Exception as exc:
        inputs['capture_errors']['bonds'] = f'{type(exc).__name__}: {exc}'
    try:
        path = config.get_data_file_path('统计报表底稿3_股基产.xlsx')
        payload = path.read_bytes()
        funds = pd.read_excel(BytesIO(payload), sheet_name='基金持仓明细表')
        inputs['funds'] = encode(funds[[c for c in FUND_COLUMNS if c in funds]])
        inputs['fund_source'] = {'path': str(path), 'sha256': sha256(payload).hexdigest()}
    except Exception as exc:
        inputs['capture_errors']['funds'] = f'{type(exc).__name__}: {exc}'
    return execute_inputs(store, receipt, inputs, timeout=config.get('scitech.wind_timeout_seconds', 90), fetcher=fetcher)


def retry(engine, run_id, timeout=90):
    store = ScitechStore(engine)
    previous = store.get_run(run_id)
    if previous['inputs'].get('capture_error'):
        raise ValueError('原批次输入捕获不完整，需准备好底稿后运行新的每日批次')
    _, errors = _validated_inputs(previous['inputs'], day(previous['data_date']))
    if len(errors) == 2:
        raise ValueError('原批次输入均不可用，需准备好底稿后运行新的每日批次')
    receipt = {k: previous[k] for k in ('data_date', 'parent_version')}
    return execute_inputs(store, receipt, previous['inputs'], timeout=timeout, retry_of=run_id)
