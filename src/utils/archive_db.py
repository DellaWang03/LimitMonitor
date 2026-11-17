"""
归档库封装（MySQL）—— 单点写入 + 历史回放读取层。

调用约定（详见 docs/DB_ARCHIVE_REFERENCE.md）：

- ``ArchiveDB.from_env()``：仅从环境变量
  ``DB_HOST`` / ``DB_PORT`` / ``DB_USER`` / ``DB_PASSWORD`` / ``DB_NAME``
  读取连接参数，仓库 / 文档 / 脚本严禁出现明文凭据。
- ``ArchiveDB.prepare_stage_tables_schema()``：在写数据前预同步 schema
  （建表 / 补列 / 建索引）。该阶段可能触发 MySQL DDL 隐式提交，因此与数据
  事务分离；失败时只会留下 schema 变更，不会留下半批业务快照。
- ``ArchiveDB.write_batch()``：``daily_archive.py`` 唯一入口，单事务内按
  ``data_date`` 完成所有 stage 表"删旧 + 写新" + ``archive_meta`` current 切换；
  前提是 schema 已预同步完成。
- ``ArchiveDB.read_dataframe`` / ``get_archive_meta`` / ``get_available_dates``
  / ``get_current_archive_date``：``DataLoader`` 读取入口。
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

import pandas as pd
from sqlalchemy import bindparam, create_engine, inspect, text
from sqlalchemy.dialects.mysql import (
    BIGINT,
    DATETIME as MYSQL_DATETIME,
    DOUBLE,
    LONGTEXT,
    TINYINT,
    VARCHAR,
)
from sqlalchemy.engine import URL, Connection, Engine
from sqlalchemy.types import TypeEngine

from src.utils.logger import get_logger

logger = get_logger()
_ARCHIVE_WRITE_LOCK_TIMEOUT_SECONDS = 60


# ---------------------------------------------------------------------------
# DDL：archive_meta
# ---------------------------------------------------------------------------
_ARCHIVE_META_DDL = """
CREATE TABLE IF NOT EXISTS archive_meta (
    archive_date              VARCHAR(10)    NOT NULL,
    data_date                 VARCHAR(10)    NOT NULL,
    is_current                TINYINT(1)     NOT NULL DEFAULT 0,
    alert_warning_threshold   DECIMAL(10,4)  NOT NULL DEFAULT 0.8000,
    alert_overlimit_threshold DECIMAL(10,4)  NOT NULL DEFAULT 1.0000,
    high_yield_annual_limit_wan DOUBLE       NULL,
    captured_at               DATETIME(6)    NOT NULL,
    KEY idx_archive_meta_current (is_current),
    KEY idx_archive_meta_archive_date (archive_date),
    KEY idx_archive_meta_data_date (data_date)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
""".strip()

_ARCHIVE_META_REQUIRED_COLUMNS: dict[str, str] = {
    "archive_date": "VARCHAR(10) NOT NULL",
    "data_date": "VARCHAR(10) NULL",
    "is_current": "TINYINT(1) NOT NULL DEFAULT 0",
    "alert_warning_threshold": "DECIMAL(10,4) NOT NULL DEFAULT 0.8000",
    "alert_overlimit_threshold": "DECIMAL(10,4) NOT NULL DEFAULT 1.0000",
    "high_yield_annual_limit_wan": "DOUBLE NULL",
    "captured_at": "DATETIME(6) NOT NULL",
}


def _resolve_dtype(df: pd.DataFrame) -> dict[str, TypeEngine]:
    """
    根据 dataframe 的 pandas dtype 推断 ``to_sql`` 的字段类型，避免 Excel
    空值 / 混合类型在首次建表时造成字段类型漂移。

    映射规则：

        - ``bool``                       → ``TINYINT(1)``
        - 整型（含 ``Int64`` 可空整数）   → ``BIGINT``
        - 浮点                            → ``DOUBLE``
        - ``datetime64[ns]``              → ``DATETIME``
        - 其余 / ``object``               → ``LONGTEXT``（兜底，按文本落库；
                                            读取侧再做日期/数值还原）
        - ``archive_date`` / ``data_date`` 快照键固定 → ``VARCHAR(10)``

    注意：本函数应当对同一张表的每次写入都返回相同类型映射；后续写入仍以此为准，
    避免某一批次的空列被 pandas 推断为 ``object`` 而触发隐式 ALTER。
    """
    dtype_map: dict[str, TypeEngine] = {}
    for col, dt in df.dtypes.items():
        if col in {"archive_date", "data_date"}:
            dtype_map[col] = VARCHAR(10)
            continue

        if pd.api.types.is_bool_dtype(dt):
            dtype_map[col] = TINYINT(1)
        elif pd.api.types.is_integer_dtype(dt):
            dtype_map[col] = BIGINT()
        elif pd.api.types.is_float_dtype(dt):
            dtype_map[col] = DOUBLE()
        elif pd.api.types.is_datetime64_any_dtype(dt):
            dtype_map[col] = MYSQL_DATETIME()
        else:
            dtype_map[col] = LONGTEXT()
    return dtype_map


def _quote_identifier(name: str) -> str:
    """为 MySQL 标识符做最小转义。"""
    return f"`{str(name).replace('`', '``')}`"


def _should_widen_to_double(existing_type: TypeEngine, desired_type: TypeEngine) -> bool:
    """
    旧表若把实际可带小数的持仓字段建成整数，后续 ``to_sql`` 追加会被 MySQL
    截断。新批次 dtype 已推断为 DOUBLE 时，将整数或零小数位 DECIMAL 列扩为 DOUBLE。
    """
    desired_text = str(desired_type).upper()
    if "DOUBLE" not in desired_text:
        return False

    existing_text = str(existing_type).upper().replace(" ", "")
    existing_name = existing_type.__class__.__name__.upper()
    if any(token in existing_text for token in ("DOUBLE", "FLOAT", "REAL")):
        return False

    if "DECIMAL" in existing_text or "NUMERIC" in existing_text:
        scale = getattr(existing_type, "scale", None)
        return scale in (None, 0)

    integer_type_names = {
        "BIGINT",
        "INTEGER",
        "INT",
        "SMALLINT",
        "TINYINT",
        "MEDIUMINT",
    }
    return existing_name in integer_type_names or existing_text in integer_type_names


def _prepare_dataframe_for_storage(
    df: pd.DataFrame,
    archive_date: str,
    table_name: str,
    data_date: Optional[str] = None,
) -> pd.DataFrame:
    """统一补快照日期列，保证 schema 预同步与正式写入口径一致。"""
    if df is None:
        raise ValueError(f"{table_name} dataframe 为 None")

    prepared = df.copy()
    for snapshot_col in ("archive_date", "data_date"):
        if snapshot_col in prepared.columns:
            prepared = prepared.drop(columns=[snapshot_col])
    prepared.insert(0, "archive_date", archive_date)
    if data_date is not None:
        prepared.insert(1, "data_date", data_date)
    return prepared


@lru_cache(maxsize=8)
def _build_archive_db_from_env_values(
    cls: type["ArchiveDB"],
    host: str,
    port: int,
    user: str,
    password: str,
    database: str,
) -> "ArchiveDB":
    """
    复用同一组连接参数对应的 ``ArchiveDB`` 实例，避免 Streamlit 每次 rerun
    都重复创建 SQLAlchemy engine / 连接池。
    """
    return cls(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
    )


class ArchiveDB:
    """MySQL 归档库封装：建表 / 批量写入 / 历史回放读取。"""

    # ------------------------------------------------------------------
    # 构造与 schema
    # ------------------------------------------------------------------
    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        database: str,
    ) -> None:
        url = URL.create(
            drivername="mysql+pymysql",
            username=user,
            password=password,
            host=host,
            port=port,
            database=database,
            query={"charset": "utf8mb4"},
        )
        self._engine: Engine = create_engine(
            url,
            pool_pre_ping=True,
            pool_recycle=3600,
            future=True,
        )

    @classmethod
    def from_env(cls) -> "ArchiveDB":
        """
        从环境变量构造连接：
        ``DB_HOST`` / ``DB_PORT`` / ``DB_USER`` / ``DB_PASSWORD`` / ``DB_NAME``。

        缺失任一项立即抛 ``KeyError`` —— 由调用方决定如何提示，
        避免在代码中放置任何形式的"默认明文凭据"。
        """
        return _build_archive_db_from_env_values(
            cls,
            host=os.environ["DB_HOST"],
            port=int(os.environ["DB_PORT"]),
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
            database=os.environ["DB_NAME"],
        )

    def init_schema(self) -> None:
        """
        创建 / 补齐 ``archive_meta``（幂等）。
        """
        with self._engine.begin() as conn:
            conn.execute(text(_ARCHIVE_META_DDL))
            self._ensure_archive_meta_columns(conn)
            self._ensure_archive_meta_allows_repeated_archive_dates(conn)
            self._ensure_archive_meta_indexes(conn)
        logger.info("archive_meta 表已就绪")

    @property
    def engine(self) -> Engine:
        """对外暴露底层 engine，方便测试或自定义查询。日常请走封装方法。"""
        return self._engine

    # ------------------------------------------------------------------
    # 批次写入（daily_archive 单点入口）
    # ------------------------------------------------------------------
    def write_batch(
        self,
        archive_date: str,
        stage_tables: dict[str, pd.DataFrame],
        data_date: Optional[str],
        alert_warning_threshold: float,
        alert_overlimit_threshold: float,
        high_yield_annual_limit_wan: float,
        receipt: Optional[dict] = None,
    ) -> None:
        """
        在 schema 已预同步的前提下，单事务完成：

        1. 对 ``stage_tables`` 中每张表按 ``data_date`` 删旧 + 追加写新；
        2. ``UPDATE archive_meta SET is_current = 0``；
        3. 删除 ``archive_meta`` 中同 ``data_date`` 的旧记录并插入本次元数据：
           ``archive_date``、``is_current=1``、``alert_*_threshold``、
           ``high_yield_annual_limit_wan``、``captured_at=NOW(6)``。

        该事务只包含 DML，不再在事务内执行建表 / 补列 / 建索引等 DDL；
        因此任一步失败时，数据批次会整体回滚，不会出现"业务表已写但 meta 未切"
        的中间态。
        """
        if not stage_tables:
            raise ValueError("write_batch: stage_tables 不能为空")
        if not isinstance(archive_date, str) or len(archive_date) != 10:
            raise ValueError(
                f"write_batch: archive_date 必须为 'YYYY-MM-DD' 字符串，收到 {archive_date!r}"
            )
        if not isinstance(data_date, str) or len(data_date) != 10:
            raise ValueError(
                f"write_batch: data_date 必须为 'YYYY-MM-DD' 字符串，收到 {data_date!r}"
            )

        with self._engine.connect() as conn:
            lock_name = self._acquire_data_date_lock(conn, data_date)
            try:
                # GET_LOCK is connection-scoped. SQLAlchemy may still autobegin
                # around the SELECT, so close that implicit transaction before
                # opening the business DML transaction on the same connection.
                conn.commit()

                with conn.begin():
                    old_archive_dates = self._get_archive_dates_for_data_date(
                        conn, data_date
                    )
                    for table_name, df in stage_tables.items():
                        rows = self._write_dataframe_in_conn(
                            conn=conn,
                            table_name=table_name,
                            archive_date=archive_date,
                            data_date=data_date,
                            df=df,
                            old_archive_dates=old_archive_dates,
                        )
                        logger.info(
                            f"write_batch: {table_name} 写入 {rows} 行 "
                            f"(archive_date={archive_date}, data_date={data_date})"
                        )

                    conn.execute(text("UPDATE archive_meta SET is_current = 0"))
                    conn.execute(
                        text("DELETE FROM archive_meta WHERE data_date = :data_date"),
                        {"data_date": data_date},
                    )

                    conn.execute(
                        text(
                            """
                            INSERT INTO archive_meta (
                                archive_date, data_date, is_current,
                                alert_warning_threshold, alert_overlimit_threshold,
                                high_yield_annual_limit_wan,
                                captured_at
                            ) VALUES (
                                :archive_date, :data_date, 1,
                                :warning, :overlimit, :high_yield_annual_limit_wan,
                                NOW(6)
                            )
                            """
                        ),
                        {
                            "archive_date": archive_date,
                            "data_date": data_date,
                            "warning": float(alert_warning_threshold),
                            "overlimit": float(alert_overlimit_threshold),
                            "high_yield_annual_limit_wan": float(
                                high_yield_annual_limit_wan
                            ),
                        },
                    )
                    # 在同一事务、同一日期锁内取得本次版本，避免事后误认其他批次。
                    if receipt is not None:
                        captured_at = conn.execute(text(
                            'SELECT captured_at FROM archive_meta WHERE data_date = :data_date'
                        ), {'data_date': data_date}).scalar()
                if receipt is not None:
                    receipt.update(data_date=data_date, parent_version=(
                        captured_at.isoformat() if hasattr(captured_at, 'isoformat') else str(captured_at)
                    ))
            finally:
                self._release_data_date_lock(conn, lock_name)

        logger.info(
            f"write_batch: archive_date={archive_date} 提交成功 "
            f"(tables={len(stage_tables)}, data_date={data_date})"
        )

    # ------------------------------------------------------------------
    # 业务结果表 / Stage0 表
    # ------------------------------------------------------------------
    def write_dataframe(
        self,
        table_name: str,
        archive_date: str,
        df: pd.DataFrame,
        data_date: Optional[str] = None,
    ) -> int:
        """
        按 ``archive_date`` 覆盖写入指定表（删旧 + 追加），返回写入行数。

        独立调用时会先完成 schema 预同步，再开启新事务执行删旧 + 写新。
        """
        self.prepare_stage_tables_schema(
            archive_date=archive_date,
            data_date=data_date,
            stage_tables={table_name: df},
        )
        with self._engine.begin() as conn:
            return self._write_dataframe_in_conn(
                conn=conn,
                table_name=table_name,
                archive_date=archive_date,
                data_date=data_date,
                df=df,
            )

    def prepare_stage_tables_schema(
        self,
        archive_date: str,
        stage_tables: dict[str, pd.DataFrame],
        data_date: Optional[str] = None,
    ) -> None:
        """
        预同步业务表 schema（建表 / 补列 / 建索引）。

        该阶段显式与 ``write_batch()`` 的数据事务分离，避免 MySQL DDL 的隐式提交
        破坏"快照批次原子提交"语义。
        """
        if not stage_tables:
            raise ValueError("prepare_stage_tables_schema: stage_tables 不能为空")

        self.init_schema()
        with self._engine.begin() as conn:
            for table_name, df in stage_tables.items():
                prepared_df = _prepare_dataframe_for_storage(
                    df=df,
                    archive_date=archive_date,
                    data_date=data_date,
                    table_name=table_name,
                )
                dtype_map = _resolve_dtype(prepared_df)
                inspector = inspect(conn)
                if inspector.has_table(table_name):
                    self._ensure_table_columns(conn, table_name, dtype_map)
                else:
                    prepared_df.head(0).to_sql(
                        name=table_name,
                        con=conn,
                        if_exists="fail",
                        index=False,
                        dtype=dtype_map,
                    )
                    logger.info(f"prepare_stage_tables_schema: 已创建新表 {table_name}")

                self._ensure_snapshot_key_indexes(conn, table_name, dtype_map)

    def _write_dataframe_in_conn(
        self,
        conn: Connection,
        table_name: str,
        archive_date: str,
        df: pd.DataFrame,
        data_date: Optional[str] = None,
        old_archive_dates: Optional[list[str]] = None,
    ) -> int:
        """
        在指定连接（已开启事务）上完成"删旧 + 写新"。

        关键约束：

        - 写入前若 dataframe 已有快照日期列先丢掉，再统一首列插入，
          保证字段顺序与 to_sql 自动建表的列顺序稳定；
        - 调用前必须已完成 schema 预同步；
        - 通过 :func:`_resolve_dtype` 显式提供 ``dtype`` 映射，避免 Excel 空值 /
          混合类型导致写入时字段类型漂移。
        """
        df = _prepare_dataframe_for_storage(
            df=df,
            archive_date=archive_date,
            data_date=data_date,
            table_name=table_name,
        )

        dtype_map = _resolve_dtype(df)

        inspector = inspect(conn)
        if not inspector.has_table(table_name):
            raise RuntimeError(
                f"_write_dataframe_in_conn: {table_name} 尚未完成 schema 预同步，"
                "请先调用 prepare_stage_tables_schema()。"
            )

        if data_date is None:
            conn.execute(
                text(f"DELETE FROM `{table_name}` WHERE archive_date = :ad"),
                {"ad": archive_date},
            )
        else:
            conn.execute(
                text(f"DELETE FROM `{table_name}` WHERE data_date = :dd"),
                {"dd": data_date},
            )
            archive_dates_to_clean = [
                old_archive_date
                for old_archive_date in (old_archive_dates or [])
                if old_archive_date
            ]
            if archive_dates_to_clean:
                stmt = text(
                    f"DELETE FROM `{table_name}` "
                    "WHERE archive_date IN :archive_dates "
                    "AND (data_date IS NULL OR data_date = '')"
                ).bindparams(bindparam("archive_dates", expanding=True))
                conn.execute(stmt, {"archive_dates": archive_dates_to_clean})

        if not df.empty:
            df.to_sql(
                name=table_name,
                con=conn,
                if_exists="append",
                index=False,
                dtype=dtype_map,
                method="multi",
                chunksize=1000,
            )
        return len(df)

    @staticmethod
    def _ensure_archive_meta_columns(conn: Connection) -> None:
        """对已存在的 ``archive_meta`` 表补齐新增列。"""
        inspector = inspect(conn)
        existing_columns = {
            column["name"] for column in inspector.get_columns("archive_meta")
        }
        for column_name, ddl in _ARCHIVE_META_REQUIRED_COLUMNS.items():
            if column_name in existing_columns:
                continue
            conn.execute(
                text(
                    f"ALTER TABLE `archive_meta` "
                    f"ADD COLUMN {_quote_identifier(column_name)} {ddl}"
                )
            )
            logger.info(f"_ensure_archive_meta_columns: 新增列 {column_name} ({ddl})")

    @staticmethod
    def _ensure_archive_meta_allows_repeated_archive_dates(conn: Connection) -> None:
        """
        旧版本以 ``archive_date`` 作为 ``archive_meta`` 主键；新口径允许同一天
        归档多个不同 ``data_date``，因此需要移除这个唯一性约束。
        """
        inspector = inspect(conn)
        pk_columns = (
            inspector.get_pk_constraint("archive_meta").get("constrained_columns")
            or []
        )
        if pk_columns == ["archive_date"]:
            conn.execute(text("ALTER TABLE archive_meta DROP PRIMARY KEY"))
            logger.info(
                "_ensure_archive_meta_allows_repeated_archive_dates: "
                "已移除 archive_meta.archive_date 主键"
            )

    @staticmethod
    def _ensure_archive_meta_indexes(conn: Connection) -> None:
        """补齐 ``archive_meta`` 查询索引。"""
        ArchiveDB._ensure_index(
            conn=conn,
            table_name="archive_meta",
            column_name="is_current",
            index_name="idx_archive_meta_current",
        )
        ArchiveDB._ensure_index(
            conn=conn,
            table_name="archive_meta",
            column_name="archive_date",
            index_name="idx_archive_meta_archive_date",
        )
        ArchiveDB._ensure_index(
            conn=conn,
            table_name="archive_meta",
            column_name="data_date",
            index_name="idx_archive_meta_data_date",
        )

    @staticmethod
    def _ensure_table_columns(
        conn: Connection,
        table_name: str,
        dtype_map: dict[str, TypeEngine],
    ) -> None:
        """
        对已存在表补齐 dataframe 中新增的列，保证历史库能平滑接收新版本快照。
        """
        inspector = inspect(conn)
        existing_column_map = {
            column["name"]: column for column in inspector.get_columns(table_name)
        }
        missing_columns = [
            (col_name, col_type)
            for col_name, col_type in dtype_map.items()
            if col_name not in existing_column_map
        ]

        for col_name, col_type in missing_columns:
            ddl_type = col_type.compile(dialect=conn.dialect)
            conn.execute(
                text(
                    f"ALTER TABLE {_quote_identifier(table_name)} "
                    f"ADD COLUMN {_quote_identifier(col_name)} {ddl_type} NULL"
                )
            )
            logger.info(
                f"_ensure_table_columns: {table_name} 新增列 {col_name} ({ddl_type})"
            )

        widen_columns = [
            (col_name, col_type)
            for col_name, col_type in dtype_map.items()
            if col_name in existing_column_map
            and _should_widen_to_double(existing_column_map[col_name]["type"], col_type)
        ]
        for col_name, col_type in widen_columns:
            ddl_type = col_type.compile(dialect=conn.dialect)
            conn.execute(
                text(
                    f"ALTER TABLE {_quote_identifier(table_name)} "
                    f"MODIFY COLUMN {_quote_identifier(col_name)} {ddl_type} NULL"
                )
            )
            logger.info(
                f"_ensure_table_columns: {table_name} 扩展列 {col_name} 为 {ddl_type}"
            )

    @staticmethod
    def _ensure_snapshot_key_indexes(
        conn: Connection,
        table_name: str,
        dtype_map: dict[str, TypeEngine],
    ) -> None:
        """补齐业务表 ``archive_date`` / ``data_date`` 查询索引。"""
        ArchiveDB._ensure_index(
            conn=conn,
            table_name=table_name,
            column_name="archive_date",
            index_name=f"idx_{table_name}_date",
        )
        if "data_date" in dtype_map:
            ArchiveDB._ensure_index(
                conn=conn,
                table_name=table_name,
                column_name="data_date",
                index_name=f"idx_{table_name}_data_date",
            )

    @staticmethod
    def _ensure_index(
        conn: Connection,
        table_name: str,
        column_name: str,
        index_name: str,
    ) -> None:
        """
        MySQL 不支持 ``CREATE INDEX IF NOT EXISTS``，这里查 ``information_schema``
        后按需创建。
        """
        exists = conn.execute(
            text(
                """
                SELECT COUNT(*) FROM information_schema.statistics
                WHERE table_schema = DATABASE()
                  AND table_name = :table_name
                  AND index_name = :index_name
                """
            ),
            {"table_name": table_name, "index_name": index_name},
        ).scalar()
        if not exists:
            conn.execute(
                text(
                    f"CREATE INDEX `{index_name}` "
                    f"ON `{table_name}` (`{column_name}`)"
                )
            )

    @staticmethod
    def _get_archive_dates_for_data_date(
        conn: Connection,
        data_date: str,
    ) -> list[str]:
        """返回同一 ``data_date`` 已登记过的归档日，用于清理旧口径业务行。"""
        rows = conn.execute(
            text(
                """
                SELECT archive_date
                FROM archive_meta
                WHERE data_date = :data_date
                """
            ),
            {"data_date": data_date},
        ).all()
        return [str(row[0]) for row in rows if row[0]]

    @staticmethod
    def _data_date_lock_name(data_date: str) -> str:
        """MySQL advisory lock 名称，长度需控制在 64 字符以内。"""
        return f"limit_monitor_archive:{data_date}"

    @staticmethod
    def _acquire_data_date_lock(conn: Connection, data_date: str) -> str:
        """同一 ``data_date`` 归档串行化，避免人工补跑和定时任务交错写库。"""
        lock_name = ArchiveDB._data_date_lock_name(data_date)
        acquired = conn.execute(
            text("SELECT GET_LOCK(:lock_name, :timeout_seconds)"),
            {
                "lock_name": lock_name,
                "timeout_seconds": _ARCHIVE_WRITE_LOCK_TIMEOUT_SECONDS,
            },
        ).scalar()
        if int(acquired or 0) != 1:
            raise TimeoutError(
                f"获取 data_date={data_date} 的归档写锁超时，"
                "可能已有同一业务数据日的归档任务正在执行。"
            )
        return lock_name

    @staticmethod
    def _release_data_date_lock(conn: Connection, lock_name: str) -> None:
        """释放 MySQL advisory lock；释放失败只记录日志，不覆盖原始写库异常。"""
        try:
            conn.execute(
                text("SELECT RELEASE_LOCK(:lock_name)"),
                {"lock_name": lock_name},
            )
        except Exception as exc:  # pragma: no cover - 防御性日志，不改变主流程结果
            logger.warning(f"释放归档写锁失败: {lock_name}: {exc}")

    def read_dataframe(
        self,
        table_name: str,
        archive_date: str,
    ) -> Optional[pd.DataFrame]:
        """
        读取指定 ``archive_date`` 的数据。

        返回值约定：

        - 表不存在 → 返回 ``None``；
        - 表存在但该日期无数据 → 返回带正确列结构的空 dataframe；
        - 返回的 dataframe **不含** ``archive_date`` / ``data_date`` 列；
        - 若包含 ``日期`` 列，自动还原为 pandas ``datetime``，兜住 ``LONGTEXT``
          落库的退化场景（确保下游 ``DataLoader`` 拿到的结构与原读 Excel 一致）。
        """
        with self._engine.connect() as conn:
            inspector = inspect(conn)
            if not inspector.has_table(table_name):
                return None
            df = pd.read_sql(
                text(f"SELECT * FROM `{table_name}` WHERE archive_date = :ad"),
                conn,
                params={"ad": archive_date},
            )

        return self._normalize_dataframe_from_storage(df)

    def read_dataframe_by_data_date(
        self,
        table_name: str,
        data_date: str,
    ) -> Optional[pd.DataFrame]:
        """
        读取指定 ``data_date`` 的数据。看板历史回放使用该入口，确保同一业务
        数据日无论在哪天归档都只读取最新版。
        """
        with self._engine.connect() as conn:
            inspector = inspect(conn)
            if not inspector.has_table(table_name):
                return None
            column_names = {
                column["name"] for column in inspector.get_columns(table_name)
            }
            if "data_date" not in column_names:
                archive_date = (
                    conn.execute(
                        text(
                            """
                            SELECT archive_date
                            FROM archive_meta
                            WHERE data_date = :dd
                            ORDER BY captured_at DESC
                            LIMIT 1
                            """
                        ),
                        {"dd": data_date},
                    ).scalar()
                )
                if not archive_date:
                    df = pd.read_sql(
                        text(f"SELECT * FROM `{table_name}` WHERE 1 = 0"),
                        conn,
                    )
                    return self._normalize_dataframe_from_storage(df)
                df = pd.read_sql(
                    text(f"SELECT * FROM `{table_name}` WHERE archive_date = :ad"),
                    conn,
                    params={"ad": archive_date},
                )
                return self._normalize_dataframe_from_storage(df)

            df = pd.read_sql(
                text(f"SELECT * FROM `{table_name}` WHERE data_date = :dd"),
                conn,
                params={"dd": data_date},
            )

        return self._normalize_dataframe_from_storage(df)

    @staticmethod
    def _normalize_dataframe_from_storage(df: pd.DataFrame) -> pd.DataFrame:
        """去掉内部快照键并恢复常用字段类型。"""
        for snapshot_col in ("archive_date", "data_date"):
            if snapshot_col in df.columns:
                df = df.drop(columns=[snapshot_col])

        if "日期" in df.columns:
            df["日期"] = pd.to_datetime(df["日期"], errors="coerce")

        return df

    # ------------------------------------------------------------------
    # 元数据（DataLoader 读取）
    # ------------------------------------------------------------------
    def get_archive_meta(self, archive_date: str) -> Optional[dict]:
        """
        返回某 ``archive_date`` 的元数据：

        ``{archive_date, data_date, is_current, alert_warning_threshold,
        alert_overlimit_threshold, high_yield_annual_limit_wan, captured_at}``。

        不存在则 ``None``。``alert_*_threshold`` 已转 ``float``，
        ``is_current`` 已转 ``int``，其余字段保持驱动返回的原生类型。
        """
        with self._engine.connect() as conn:
            row = (
                conn.execute(
                    text(
                        """
                        SELECT archive_date, data_date, is_current,
                               alert_warning_threshold, alert_overlimit_threshold,
                               high_yield_annual_limit_wan,
                               captured_at
                        FROM archive_meta
                        WHERE archive_date = :ad
                        ORDER BY is_current DESC, captured_at DESC
                        LIMIT 1
                        """
                    ),
                    {"ad": archive_date},
                )
                .mappings()
                .first()
            )

        return self._archive_meta_row_to_dict(row)

    def get_archive_meta_by_data_date(self, data_date: str) -> Optional[dict]:
        """
        返回某 ``data_date`` 的元数据。新归档口径下，``data_date`` 是业务覆盖键。
        """
        with self._engine.connect() as conn:
            row = (
                conn.execute(
                    text(
                        """
                        SELECT archive_date, data_date, is_current,
                               alert_warning_threshold, alert_overlimit_threshold,
                               high_yield_annual_limit_wan,
                               captured_at
                        FROM archive_meta
                        WHERE data_date = :dd
                        ORDER BY captured_at DESC
                        LIMIT 1
                        """
                    ),
                    {"dd": data_date},
                )
                .mappings()
                .first()
            )

        return self._archive_meta_row_to_dict(row)

    @staticmethod
    def _archive_meta_row_to_dict(row) -> Optional[dict]:
        """统一转换 ``archive_meta`` 查询结果。"""
        if row is None:
            return None

        return {
            "archive_date": row["archive_date"],
            "data_date": row["data_date"],
            "is_current": int(row["is_current"]),
            "alert_warning_threshold": float(row["alert_warning_threshold"]),
            "alert_overlimit_threshold": float(row["alert_overlimit_threshold"]),
            "high_yield_annual_limit_wan": (
                None
                if row["high_yield_annual_limit_wan"] is None
                else float(row["high_yield_annual_limit_wan"])
            ),
            "captured_at": row["captured_at"],
        }

    def list_archive_meta(self) -> list[dict]:
        """
        一次性读取 sidebar 需要的归档元数据，避免历史日期下拉逐项查询。
        """
        with self._engine.connect() as conn:
            rows = (
                conn.execute(
                    text(
                        """
                        SELECT archive_date, data_date, is_current, captured_at
                        FROM archive_meta
                        ORDER BY data_date DESC, captured_at DESC
                        """
                    )
                )
                .mappings()
                .all()
            )
        return [
            {
                "archive_date": row["archive_date"],
                "data_date": row["data_date"],
                "is_current": int(row["is_current"]),
                "captured_at": row["captured_at"],
            }
            for row in rows
        ]

    def get_available_dates(self) -> list[str]:
        """返回 ``archive_meta`` 中全部 ``data_date``，按降序排列。"""
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT DISTINCT data_date FROM archive_meta "
                    "ORDER BY data_date DESC"
                )
            ).all()
        return [r[0] for r in rows]

    def get_current_archive_date(self) -> Optional[str]:
        """返回 ``is_current = 1`` 的 ``archive_date``，不存在则 ``None``。"""
        with self._engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT archive_date FROM archive_meta "
                    "WHERE is_current = 1 ORDER BY captured_at DESC LIMIT 1"
                )
            ).first()
        return row[0] if row else None

    def get_current_data_date(self) -> Optional[str]:
        """返回 ``is_current = 1`` 的 ``data_date``，不存在则 ``None``。"""
        with self._engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT data_date FROM archive_meta "
                    "WHERE is_current = 1 ORDER BY captured_at DESC LIMIT 1"
                )
            ).first()
        return row[0] if row else None
