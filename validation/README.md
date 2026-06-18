# 校验入口

`validation/` 当前只保留上线前仍在使用的 DB current 与展示层校验工具。

## 保留脚本

- `validate_db_dashboard_consistency.py`：校验 DB current 与指定 `data_date` 的看板读取口径一致
- `validate_dashboard_display.py`：对比 `data/current/display_snapshots/` 与人工参考 CSV

## 推荐入口

```bash
bash tests/run_full_integration_test.sh [DATA_DATE] [REF_DIR]
```

可通过 `PYTHON_BIN` 指定解释器：

```bash
PYTHON_BIN=.venv/bin/python bash tests/run_full_integration_test.sh [DATA_DATE] [REF_DIR]
```

该入口会依次执行：

1. 校验 DB current 是否指向待校验业务数据日
2. 重新生成展示层 CSV 快照
3. 对比展示层快照与参考 CSV

当前全流程测试是上线前临时集成验收入口。每日稳定运行后，可重写业务逻辑相关测试与黄金基准体系。
