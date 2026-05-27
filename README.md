# 限额监控自动化系统

固定收益事业部债券投资限额自动化监控系统。当前仓库定位为上线运行版本，保留每日跑数、DB 归档、展示快照、Web 看板和上线前验收所需的最小入口。

## 一、环境准备

推荐使用项目内 `.venv`：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Windows 可使用：

```bat
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

说明：

- `WindPy` 依赖本机 Wind 终端授权。
- `pyodbc` / Access 读取依赖本机驱动环境。
- MySQL 归档库连接信息只通过环境变量注入，不写入仓库。

## 二、配置数据源路径

数据源路径统一在 `config/settings.yaml` 中配置：

```yaml
data_sources:
  active_profile: "migration"
  path_profiles:
    local:
      data_dir: "data_source_0123"
    migration:
      data_dir: "/Volumes/sjz-share/PBI"
      data_config_source: "/Volumes/sjz-share/PBI/限额/限额监控"
```

上线使用共享盘时，重点确认：

- `data_sources.active_profile` 使用 `migration`
- `path_profiles.migration.data_dir` 指向共享盘根目录
- `path_profiles.migration.file_subpaths` 与共享盘实际目录一致
- `path_profiles.migration.path_overrides.净资产.xlsx` 指向净资产文件实际路径
- `path_profiles.migration.data_config_source` 指向共享盘上的 Base64 拆出表目录，当前为 `/Volumes/sjz-share/PBI/限额/限额监控`
- `local` profile 仍读取项目根目录下的 `data_source_0123/`，其中包含本地调试用的 Base64 拆出表

也可以用环境变量临时切换 profile：

```bash
export LIMIT_MONITOR_PROFILE=migration
```

## 三、配置 DB 连接

每日归档、历史回放、展示快照和看板读取均依赖 DB current/history 快照。运行前注入：

```bash
export DB_HOST=<host>
export DB_PORT=<port>
export DB_USER=<user>
export DB_PASSWORD=<password>
export DB_NAME=<database>
```

## 四、每日运行

推荐使用完整入口：

```bash
bash run_daily.sh
```

Windows：

```bat
run_daily.bat
```

生产模式建议显式指定：

```bash
LIMIT_MONITOR_ENV=production bash run_daily.sh
```

`run_daily.sh` 会依次执行：

1. `run_stage0.py`
2. `run_stage1.py`
3. `run_stage2.py`
4. `scripts/daily_archive.py`
5. `scripts/generate_display_snapshot.py`

## 五、补跑历史日期

用于 T+N 补跑 T-1 数据：

```bash
python run_stage0.py --target-date 2026-04-07
python run_stage1.py
python run_stage2.py
python scripts/daily_archive.py --archive-date 2026-04-07
python scripts/generate_display_snapshot.py --archive-date 2026-04-07
```

## 六、启动看板

```bash
bash start_web.sh
```

Windows：

```bat
start_web.bat
```

默认访问：

```text
http://localhost:8501
```

## 七、上线前验收

代码级回归：

```bash
python3 -m pytest -q tests
```

上线前临时全流程集成验收：

```bash
bash tests/run_full_integration_test.sh [ARCHIVE_DATE] [REF_DIR]
```

如需指定解释器：

```bash
PYTHON_BIN=.venv/bin/python bash tests/run_full_integration_test.sh [ARCHIVE_DATE] [REF_DIR]
```

前置条件：

- 已先运行 `bash run_daily.sh`
- 本次结果已成功写入 DB current
- 已注入 `DB_HOST` / `DB_PORT` / `DB_USER` / `DB_PASSWORD` / `DB_NAME`
- `REF_DIR` 指向人工确认的展示层参考 CSV 目录

当前全流程测试是上线前集成验收入口。每日稳定运行后，业务逻辑相关测试和黄金基准体系可再重写。

## 八、项目结构

```text
LimitMonitorAutomation/
├── app.py
├── config/
│   └── settings.yaml
├── data/
│   └── .gitkeep
├── requirements.txt
├── run_daily.sh / run_daily.bat
├── run_stage0.py
├── run_stage1.py
├── run_stage2.py
├── scripts/
│   ├── daily_archive.py
│   ├── generate_display_snapshot.py
│   └── audit_bond_quota_query.py
├── src/
├── start_web.sh / start_web.bat
├── tests/
└── validation/
```

## 九、保留的主要入口

- 每日跑数：`bash run_daily.sh`
- Web 看板：`bash start_web.sh`
- Stage 单独运行：`python run_stage0.py` / `python run_stage1.py` / `python run_stage2.py`
- DB 归档：`python scripts/daily_archive.py`
- 展示快照：`python scripts/generate_display_snapshot.py`
- 上线前验收：`bash tests/run_full_integration_test.sh [ARCHIVE_DATE] [REF_DIR]`
