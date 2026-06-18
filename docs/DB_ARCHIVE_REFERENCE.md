# DB 归档运行口径

本文记录上线运行需要保留的 DB current/history 口径，替代历史迁移实施计划。

## 连接方式

DB 连接信息只从环境变量读取，不写入仓库：

```bash
export DB_HOST=<host>
export DB_PORT=<port>
export DB_USER=<user>
export DB_PASSWORD=<password>
export DB_NAME=<database>
```

## 写入入口

`scripts/daily_archive.py` 是唯一 DB 写入入口。每日主链路在 Stage0、Stage1、Stage2 产物生成后调用该脚本，把 `data/current/` 下的产物写入 MySQL。

写入范围：

- 4 张 Stage0 必需中间表
- 12 张 Stage1/Stage2 业务结果表
- `archive_meta` 元数据表

`archive_meta` 记录：

- `archive_date`：归档运行日期
- `data_date`：业务数据日期，也是覆盖与历史读取键
- `is_current`
- 告警阈值
- 高收益年度限额
- `captured_at`

写入业务表时，每张表都会补充 `archive_date` 与 `data_date` 两列。重跑时按
`data_date` 清理旧业务行和旧元数据，再写入本次结果。因此：

- 同一个 `data_date` 无论在哪个自然日重跑，只保留最新一版。
- 不同 `data_date` 即使在同一个自然日归档，也会同时保留。
- `archive_date` 不再作为业务快照唯一键，只用于记录这批数据是哪天归档的。

## 读取口径

展示层通过 `src.visualization.data_loader.DataLoader` 读取 DB：

- `target_date=None`：读取 `archive_meta.is_current=1` 对应快照
- `target_date=<date>`：读取指定 `data_date` 快照

展示层不再从 `data/history/` 读取业务结果，也不从历史目录读取 `data_date.txt`。

## 展示快照

`scripts/generate_display_snapshot.py` 从 DB 读取展示数据，并生成 `data/current/display_snapshots/` 下的 CSV，用于上线前展示层校验。

## 失败处理

- 输入产物缺失时，归档直接失败。
- 写库失败时，业务数据事务回滚。
- schema 预同步阶段可能已完成建表、补列或建索引；该阶段与业务数据事务分离。
