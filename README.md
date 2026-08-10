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
python -m venv .venv
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
    windows:
      data_dir: '\\192.168.136.150\sjz-share\PBI'
      data_config_source: '\\192.168.136.150\sjz-share\PBI\限额\限额监控'
```

上线使用共享盘时，重点确认：

- `data_sources.active_profile` 使用 `migration`
- `path_profiles.migration.data_dir` 指向共享盘根目录
- `path_profiles.migration.file_subpaths` 与共享盘实际目录一致
- `path_profiles.migration.path_overrides.净资产.xlsx` 指向净资产文件实际路径
- `path_profiles.migration.data_config_source` 指向共享盘上的 Base64 拆出表目录，当前为 `/Volumes/sjz-share/PBI/限额/限额监控`
- Windows 生产环境由 `start_web.bat` / `run_daily.bat` 自动使用 `windows` profile
- `local` profile 仍读取项目根目录下的 `data_source_0123/`，其中包含本地调试用的 Base64 拆出表

也可以用环境变量临时切换 profile：

```bash
export LIMIT_MONITOR_PROFILE=migration
```

Windows 上如需手工验证 profile：

```bat
set LIMIT_MONITOR_PROFILE=windows
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

Windows 可在系统环境变量中配置；也可在本机创建不提交 Git 的 `config\local_env.bat`：

```bat
set DB_HOST=<host>
set DB_PORT=3306
set DB_USER=<user>
set DB_PASSWORD=<password>
set DB_NAME=<database>
```

非持仓债依赖真实 WindPy + Excel/Wind 字段验收。验收完成后才可显式启用；
未设置时服务保持失败关闭，不会把缺失主数据当作可计算：

```bash
export LIMIT_MONITOR_WIND_FIELD_MAPPING_VERIFIED=true
```

Windows 可在未提交的 `config\local_env.bat` 中设置：

```bat
set LIMIT_MONITOR_WIND_FIELD_MAPPING_VERIFIED=true
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

Windows 脚本会自动设置 `LIMIT_MONITOR_PROFILE=windows`、`LIMIT_MONITOR_ENV=production` 和 Python UTF-8 输出，并优先使用 `.venv\Scripts\python.exe`。归档日期由 Python 按当天生成，不依赖 Windows 的本地化日期格式。

macOS/Linux 生产模式建议显式指定：

```bash
LIMIT_MONITOR_ENV=production bash run_daily.sh
```

每日脚本统一调用 `scripts/run_daily_pipeline.py`，由同一进程依次完成：

1. Stage0、Stage1、Stage2 与共享运行期上下文计算
2. 生成待发布的交易前快照
3. 单事务归档既有结果
4. 发布交易前 `current` 指针
5. 生成展示快照

## 五、补跑历史日期

用于 T+N 补跑 T-1 数据：

```bash
python scripts/run_daily_pipeline.py --target-date 2026-04-07 --archive-date 2026-04-08
```

`--target-date` 是业务目标日期，`--archive-date` 是归档运行日；覆盖与历史读取按结果中的 `data_date` 执行。直接运行 Stage 或归档脚本仅用于诊断，不会完成交易前 `current` 的完整发布。

## 六、启动看板

```bash
bash start_web.sh
```

Windows：

```bat
start_web.bat
```

Windows 脚本会自动加载 `config\local_env.bat`（如存在），检查 DB 环境变量和 `streamlit` 后再启动。

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
bash tests/run_full_integration_test.sh [DATA_DATE] [REF_DIR]
```

如需指定解释器：

```bash
PYTHON_BIN=.venv/bin/python bash tests/run_full_integration_test.sh [DATA_DATE] [REF_DIR]
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
│   ├── run_daily_pipeline.py
│   └── audit_bond_quota_query.py
├── src/
│   ├── pipeline/
│   ├── pretrade/
│   └── risk_core/
├── start_web.sh / start_web.bat
├── tests/
└── validation/
```

## 九、保留的主要入口

- 每日跑数：`bash run_daily.sh`
- 统一 Python 入口：`python scripts/run_daily_pipeline.py`
- Web 看板：`bash start_web.sh`
- Stage、DB 归档与展示快照的独立入口：仅用于诊断或隔离验证
- 上线前验收：`bash tests/run_full_integration_test.sh [DATA_DATE] [REF_DIR]`
