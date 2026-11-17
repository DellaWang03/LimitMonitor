"""仅重试科创分支，复用已保存的原批次输入，不重跑或发布主快照。"""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--timeout', type=int, default=90)
    args = parser.parse_args(argv)
    if args.timeout <= 0:
        parser.error('--timeout 必须为正整数秒')
    from src.utils.archive_db import ArchiveDB
    from src.scitech.service import retry
    try:
        result = retry(ArchiveDB.from_env().engine, args.run_id, timeout=args.timeout)
    except Exception as exc:
        print(f'科创补跑未执行或失败，run_id={args.run_id}：{type(exc).__name__}: {exc}')
        return 1
    print(result)
    return 0 if result['status'] == 'READY' else 1


if __name__ == '__main__':
    raise SystemExit(main())
