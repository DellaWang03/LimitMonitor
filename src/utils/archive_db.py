"""
归档库封装（MySQL）—— 单点写入 + 历史回放读取层。

调用约定（详见 docs/DB_ARCHIVE_REFERENCE.md）：

- ``ArchiveDB.from_env()``：仅从环境变量
  ``DB_HOST`` / ``DB_PORT`` / ``DB_USER`` / ``DB_PASSWORD`` / ``DB_NAME``
  读取连接参数，仓库 / 文档 / 脚本严禁出现明文凭据。
- ``ArchiveDB.prepare_stage_tables_schema()``：在写数据前预同步 schema
  （建表 / 补列 / 建索引）。该阶段可能触发 MySQL DDL 隐式提交，因此与数据
  事务分离；失败时只会留下 schema 变更，不会留下半批业务快照。
- ``ArchiveDB.write_batch()``：``daily_archive.py`` 唯一入口，单事务内完成
  所有 stage 表"删旧 + 写新" + ``archive_meta`` upsert + ``is_current`` 切换；
  前提是 schema 已预同步完成。
- ``ArchiveDB.read_dataframe`` / ``get_archive_meta`` / ``get_available_dates``
  / ``get_current_archive_date``：``DataLoader`` 读取入口。
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

import pandas as pd
from sqlalchemy import create_engine, inspect, text
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


# ---------------------------------------------------------------------------
# DDL：archive_meta
# ---------------------------------------------------------------------------
_ARCHIVE_META_DDL = """
CREATE TABLE IF NOT EXISTS archive_meta (
    archive_date              VARCHAR(10)    NOT NULL PRIMARY KEY,
    data_date                 VARCHAR(10)    NULL,
    is_current                TINYINT(1)     NOT NULL DEFAULT 0,
    alert_warning_threshold   DECIMAL(10,4)  NOT NULL DEFAULT 0.8000,
    alert_overlimit_threshold DECIMAL(10,4)  NOT NULL DEFAULT 1.0000,
    high_yield_annual_limit_wan DOUBLE       NULL,
    captured_at               DATETIME(6)    NOT NULL,
    KEY idx_archive_meta_current (is_current)
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
        - ``archive_date`` 业务键固定     → ``VARCHAR(10)``

    注意：本函数应当对同一张表的每次写入都返回相同类型映射；后续写入仍以此为准，
    避免某一批次的空列被 pandas 推断为 ``object`` 而触发隐式 ALTER。
    """
    dtype_map: dict[str, TypeEngine] = {}
    for col, dt in df.dtypes.items():
        if col == "archive_date":
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


def _prepare_dataframe_for_storage(
    df: pd.DataFrame,
    archive_date: str,
    table_name: str,
) -> pd.DataFrame:
    """统一补 ``archive_date`` 首列，保证 schema 预同步与正式写入口径一致。"""
    if df is None:
        raise ValueError(f"{table_name} dataframe 为 None")

    prepared = df.copy()
    if "archive_date" in prepared.columns:
        prepared = prepared.drop(columns=["archive_date"])
    prepared.insert(0, "archive_date", archive_date)
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
    ) -> None:
        """
        在 schema 已预同步的前提下，单事务完成：

        1. 对 ``stage_tables`` 中每张表按 ``archive_date`` 删旧 + 追加写新；
        2. ``UPDATE archive_meta SET is_current = 0``；
        3. ``INSERT ... ON DUPLICATE KEY UPDATE`` ``archive_meta``：
           ``is_current=1``、``data_date``、``alert_*_threshold``、
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

        with self._engine.begin() as conn:
            for table_name, df in stage_tables.items():
                rows = self._write_dataframe_in_conn(
                    conn=conn,
                    table_name=table_name,
                    archive_date=archive_date,
                    df=df,
                )
                logger.info(
                    f"write_batch: {table_name} 写入 {rows} 行 "
                    f"(archive_date={archive_date})"
                )

            conn.execute(text("UPDATE archive_meta SET is_current = 0"))

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
                    ON DUPLICATE KEY UPDATE
                        data_date = VALUES(data_date),
                        is_current = 1,
                        alert_warning_threshold = VALUES(alert_warning_threshold),
                        alert_overlimit_threshold = VALUES(alert_overlimit_threshold),
                        high_yield_annual_limit_wan = VALUES(high_yield_annual_limit_wan),
                        captured_at = VALUES(captured_at)
                    """
                ),
                {
                    "archive_date": archive_date,
                    "data_date": data_date,
                    "warning": float(alert_warning_threshold),
                    "overlimit": float(alert_overlimit_threshold),
                    "high_yield_annual_limit_wan": float(high_yield_annual_limit_wan),
                },
            )

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
    ) -> int:
        """
        按 ``archive_date`` 覆盖写入指定表（删旧 + 追加），返回写入行数。

        独立调用时会先完成 schema 预同步，再开启新事务执行删旧 + 写新。
        """
        self.prepare_stage_tables_schema(
            archive_date=archive_date,
            stage_tables={table_name: df},
        )
        with self._engine.begin() as conn:
            return self._write_dataframe_in_conn(
                conn=conn,
                table_name=table_name,
                archive_date=archive_date,
                df=df,
            )

    def prepare_stage_tables_schema(
        self,
        archive_date: str,
        stage_tables: dict[str, pd.DataFrame],
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

                self._ensure_archive_date_index(conn, table_name)

    def _write_dataframe_in_conn(
        self,
        conn: Connection,
        table_name: str,
        archive_date: str,
        df: pd.DataFrame,
    ) -> int:
        """
        在指定连接（已开启事务）上完成"删旧 + 写新"。

        关键约束：

        - 写入前若 dataframe 已有 ``archive_date`` 列先丢掉，再统一首列插入，
          保证字段顺序与 to_sql 自动建表的列顺序稳定；
        - 调用前必须已完成 schema 预同步；
        - 通过 :func:`_resolve_dtype` 显式提供 ``dtype`` 映射，避免 Excel 空值 /
          混合类型导致写入时字段类型漂移。
        """
        df = _prepare_dataframe_for_storage(
            df=df,
            archive_date=archive_date,
            table_name=table_name,
        )

        dtype_map = _resolve_dtype(df)

        inspector = inspect(conn)
        if not inspector.has_table(table_name):
            raise RuntimeError(
                f"_write_dataframe_in_conn: {table_name} 尚未完成 schema 预同步，"
                "请先调用 prepare_stage_tables_schema()。"
            )

        conn.execute(
            text(f"DELETE FROM `{table_name}` WHERE archive_date = :ad"),
            {"ad": archive_date},
        )

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
    def _ensure_table_columns(
        conn: Connection,
        table_name: str,
        dtype_map: dict[str, TypeEngine],
    ) -> None:
        """
        对已存在表补齐 dataframe 中新增的列，保证历史库能平滑接收新版本快照。
        """
        inspector = inspect(conn)
        existing_columns = {
            column["name"] for column in inspector.get_columns(table_name)
        }
        missing_columns = [
            (col_name, col_type)
            for col_name, col_type in dtype_map.items()
            if col_name not in existing_columns
        ]
        if not missing_columns:
            return

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

    @staticmethod
    def _ensure_archive_date_index(conn: Connection, table_name: str) -> None:
        """
        MySQL 不支持 ``CREATE INDEX IF NOT EXISTS``，这里查 ``information_schema``
        后按需创建（命名沿用 ``idx_<table>_date`` 约定）。
        """
        index_name = f"idx_{table_name}_date"
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
                    f"ON `{table_name}` (`archive_date`)"
                )
            )

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
        - 返回的 dataframe **不含** ``archive_date`` 列；
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

        if "archive_date" in df.columns:
            df = df.drop(columns=["archive_date"])

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
                        """
                    ),
                    {"ad": archive_date},
                )
                .mappings()
                .first()
            )

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
                        ORDER BY archive_date DESC
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
        """返回 ``archive_meta`` 中全部 ``archive_date``，按降序排列。"""
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT archive_date FROM archive_meta "
                    "ORDER BY archive_date DESC"
                )
            ).all()
        return [r[0] for r in rows]

    def get_current_archive_date(self) -> Optional[str]:
        """返回 ``is_current = 1`` 的 ``archive_date``，不存在则 ``None``。"""
        with self._engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT archive_date FROM archive_meta "
                    "WHERE is_current = 1 LIMIT 1"
                )
            ).first()
        return row[0] if row else None
