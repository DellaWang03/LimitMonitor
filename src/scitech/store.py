"""附加模块自己的事务和版本；绝不写 archive_meta 或主结果表。"""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from uuid import uuid4
from sqlalchemy import Column, MetaData, String, Table, Text, inspect, select, text
from sqlalchemy.dialects.mysql import LONGTEXT

metadata = MetaData()
runs = Table('scitech_runs', metadata,
    Column('run_id', String(36), primary_key=True),
    Column('data_date', String(10), nullable=False, index=True),
    Column('parent_version', String(40), nullable=False),
    Column('created_at', String(40), nullable=False),
    Column('result_version', String(36), nullable=False),
    Column('status', String(16), nullable=False),
    Column('inputs_json', Text().with_variant(LONGTEXT(), 'mysql'), nullable=False),
    Column('result_json', Text().with_variant(LONGTEXT(), 'mysql')),
    Column('error', Text()), mysql_engine='InnoDB', mysql_charset='utf8mb4')


def version(value):
    if value is None:
        raise ValueError('主快照缺少版本')
    return value.isoformat() if hasattr(value, 'isoformat') else str(value).replace(' ', 'T')


class ScitechStore:
    def __init__(self, engine):
        self.engine = engine

    def prepare(self):
        metadata.create_all(self.engine)

    def _check_parent(self, conn, receipt):
        current = conn.execute(text('SELECT captured_at FROM archive_meta WHERE data_date=:d'),
                               {'d': receipt['data_date']}).scalar()
        if current is None or version(current) != receipt['parent_version']:
            raise ValueError('主快照已更新，拒绝跨批次发布科创结果')

    @contextmanager
    def _begin_transaction(self, receipt):
        """只串行化同一科创批次的启动；不持有主归档锁，不跨 Wind 调用持锁。"""
        dialect = self.engine.dialect.name
        lock_name = 'scitech:' + sha256(json.dumps(receipt, sort_keys=True).encode()).hexdigest()[:48]
        with self.engine.connect() as conn:
            if dialect == 'mysql':
                acquired = conn.execute(text('SELECT GET_LOCK(:name, 5)'), {'name': lock_name}).scalar()
                conn.commit()
                if acquired != 1:
                    raise TimeoutError('科创批次正在创建，请稍后重试')
            try:
                if dialect == 'sqlite':
                    conn.exec_driver_sql('BEGIN IMMEDIATE')
                else:
                    conn.begin()
                try:
                    yield conn
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise
            finally:
                if dialect == 'mysql':
                    try:
                        conn.execute(text('SELECT RELEASE_LOCK(:name)'), {'name': lock_name})
                        conn.commit()
                    except Exception:
                        # 关闭连接也会释放命名锁；清理失败不掩盖已提交的 run_id。
                        conn.invalidate()

    @staticmethod
    def _latest_query(receipt):
        return select(runs).where(runs.c.data_date == receipt['data_date'],
            runs.c.parent_version == receipt['parent_version']).order_by(
                runs.c.created_at.desc(), runs.c.run_id.desc()).limit(1)

    def begin(self, receipt, inputs, *, retry_of=None, timeout=90):
        if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout <= 0:
            raise ValueError('科创 Wind 超时必须为正整数秒')
        run_id = str(uuid4())
        with self._begin_transaction(receipt) as conn:
            self._check_parent(conn, receipt)
            latest = conn.execute(self._latest_query(receipt)).mappings().first()
            if retry_of:
                if latest is None or latest['run_id'] != retry_of:
                    raise ValueError('仅允许补跑该主快照的最新科创运行，已有后续结果时不能重试旧运行')
                if self._decode(latest)['status'] == 'RUNNING':
                    raise ValueError('科创任务仍在运行中，请等待完成或中断超时后再补跑')
            created_at = datetime.now(timezone.utc)
            if latest:
                # 客户端时钟回拨或同一微秒启动也不能使旧结果覆盖新尝试。
                previous_time = datetime.fromisoformat(latest['created_at']).replace(tzinfo=timezone.utc)
                created_at = max(created_at, previous_time + timedelta(microseconds=1))
            inputs = {**inputs, '_execution': {'wind_timeout_seconds': timeout}}
            conn.execute(runs.insert().values(run_id=run_id, **receipt,
                created_at=created_at.isoformat(), result_version=str(uuid4()),
                status='RUNNING', inputs_json=json.dumps(inputs, ensure_ascii=False, allow_nan=False)))
        return run_id

    def finish(self, run_id, receipt, result=None, error=None):
        with self.engine.begin() as conn:
            self._check_parent(conn, receipt)
            status = 'FAILED' if error else 'PARTIAL' if result['issues'] else 'READY'
            changed = conn.execute(runs.update().where(runs.c.run_id == run_id,
                runs.c.data_date == receipt['data_date'], runs.c.parent_version == receipt['parent_version'],
                runs.c.status == 'RUNNING').values(status=status, result_version=str(uuid4()), error=error,
                    result_json=json.dumps(result, ensure_ascii=False, allow_nan=False) if result else None))
            if changed.rowcount != 1:
                raise ValueError('科创运行不存在或已结束')

    def read(self, data_date, parent_version):
        # 不缓存状态：重试成功后即刻可见，不误用同一主版本下的旧模块缓存。
        if not inspect(self.engine).has_table(runs.name):
            return None
        with self.engine.connect() as conn:
            self._check_parent(conn, {'data_date': data_date, 'parent_version': parent_version})
            row = conn.execute(self._latest_query({'data_date': data_date, 'parent_version': parent_version})).mappings().first()
            return self._decode(row) if row else None

    def get_run(self, run_id):
        with self.engine.connect() as conn:
            row = conn.execute(select(runs).where(runs.c.run_id == run_id)).mappings().one()
            return self._decode(row)

    @staticmethod
    def _decode(row):
        result = dict(row)
        result['inputs'] = json.loads(result.pop('inputs_json'))
        result['result'] = json.loads(result.pop('result_json') or 'null')
        if result['status'] == 'RUNNING':
            timeout = result['inputs'].get('_execution', {}).get('wind_timeout_seconds', 90)
            deadline = datetime.fromisoformat(result['created_at']) + timedelta(seconds=timeout + 300)
            if datetime.now(timezone.utc) > deadline:
                result['status'] = 'INTERRUPTED'
                result['error'] = '运行超过 Wind 硬超时及五分钟处理宽限期，可能已中断，可独立补跑'
        return result
