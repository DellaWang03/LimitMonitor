# 校验入口

当前 `validation/` 仅保留上线前仍在使用的展示层与 DB current 校验工具。

## 保留脚本

- `validate_db_dashboard_consistency.py`：确认 DB current / 指定 archive_date 与展示层读取口径一致
- `validate_dashboard_display.py`：将 `data/current/display_snapshots/` 与人工参考 CSV 逐表对比

## 推荐入口

```bash
bash tests/run_full_integration_test.sh [ARCHIVE_DATE] [REF_DIR]
```

可通过 `PYTHON_BIN=.venv/bin/python` 指定解释器。

该入口会依次执行：

1. 校验 DB current 是否指向待校验归档日
2. 重新生成展示层 CSV 快照
3. 对比展示层快照与参考 CSV

历史 Stage 级、专项修复级、一次性诊断校验已归档到：

```text
archive/launch_cleanup_2026-05-26/validation/
```
