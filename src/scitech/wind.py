"""有硬超时的 Wind 子进程；页面从不导入 WindPy。"""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import sys

PREFIX = 'SCITECH_FLAGS='


def fetch_flags(codes, timeout=90):
    codes = sorted({str(c).strip().upper() for c in codes if str(c).strip()})
    if not codes:
        return {}
    try:
        completed = subprocess.run([sys.executable, '-m', 'src.scitech.wind'],
            input=json.dumps(codes), capture_output=True, text=True, encoding='utf-8', errors='replace',
            env={**os.environ, 'PYTHONIOENCODING': 'utf-8'},
            cwd=Path(__file__).resolve().parents[2], timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f'Wind查询超时（{timeout}秒）') from None
    for line in reversed(completed.stdout.splitlines()):
        if line.startswith(PREFIX):
            payload = json.loads(line[len(PREFIX):])
            if payload.get('error'):
                raise RuntimeError(payload['error'])
            if completed.returncode == 0:
                return payload['flags']
    raise RuntimeError(f'Wind子进程未返回有效结果（退出码 {completed.returncode}）')


def query(wind, codes):
    flags = {}
    for start in range(0, len(codes), 100):
        batch = codes[start:start + 100]
        try:
            batch_flags = _query_batch(wind, batch)
        except Exception as exc:
            # 单批次异常不抹掉其他批次的已确认分类；异常批次整批待核实。
            batch_flags = {c: {'value': None, 'error': f'Wind批次异常：{type(exc).__name__}: {exc}'} for c in batch}
        flags.update(batch_flags)
    return flags


def _query_batch(wind, batch):
    response = wind.wss(','.join(batch), 'scitechbondornot')
    error = getattr(response, 'ErrorCode', None)
    if error != 0:
        return {c: {'value': None, 'error': f'Wind错误码 {error}'} for c in batch}
    fields, returned, data = response.Fields, response.Codes, response.Data
    if (len(fields) != 1 or str(fields[0]).upper() != 'SCITECHBONDORNOT'
            or len(data) != 1 or len(data[0]) != len(returned)):
        raise RuntimeError('Wind科创标识返回结构异常')
    flags = {}
    for code, value in zip(returned, data[0]):
        code = str(code).strip().upper()
        if code not in batch or code in flags:
            raise RuntimeError('Wind返回重复或非请求证券代码')
        value = str(value).strip() if value is not None else None
        flags[code] = {'value': value if value in ('是', '否') else None,
                      'error': None if value in ('是', '否') else 'Wind标识为空或未知值'}
    for code in set(batch) - flags.keys():
        flags[code] = {'value': None, 'error': 'Wind未返回该证券'}
    return flags


def main():
    try:
        codes = json.loads(sys.stdin.read())
        from src.pretrade.windpy_master import _import_windpy, _start_gateway
        module = _import_windpy()
        if module is None or _start_gateway(module.w) != 0:
            raise RuntimeError('Wind不可用或启动失败，请检查本机登录及API权限')
        payload = {'flags': query(module.w, codes)}
    except Exception as exc:
        payload = {'error': f'{type(exc).__name__}: {exc}'}
    print(PREFIX + json.dumps(payload, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
