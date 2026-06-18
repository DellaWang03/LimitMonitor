# 测试入口

当前上线前保留两类测试入口：

## 代码级回归

```bash
python3 -m pytest -q tests
```

保留范围：

- `test_bond_quota_query.py`：单券可购额度查询核心口径
- `test_date_validator.py`：业务日期与交易日逻辑
- `test_visualization_data_loader.py`：DB 快照读取缓存与展示层数据加载

`test_visualization_data_loader.py` 依赖 `SQLAlchemy`。若当前解释器未安装该依赖，pytest 会跳过该文件；完整环境应按根目录 `requirements.txt` 安装。

## 上线前全流程集成测试

```bash
bash tests/run_full_integration_test.sh [DATA_DATE] [REF_DIR]
```

如需指定解释器：

```bash
PYTHON_BIN=.venv/bin/python bash tests/run_full_integration_test.sh [DATA_DATE] [REF_DIR]
```

前置条件：

- 已先运行 `bash run_daily.sh`，且本次结果已成功写入 DB current
- 已注入 `DB_HOST` / `DB_PORT` / `DB_USER` / `DB_PASSWORD` / `DB_NAME`
- `REF_DIR` 指向人工确认的展示层参考 CSV 目录
