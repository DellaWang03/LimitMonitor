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

非持仓债默认启用真实 WindPy + Excel/Wind 主数据查询；缺失或非法主数据仍返回
不可计算，不会按 0 处理。需要在单机维护或 Wind 环境异常时临时关闭，可设置：

```bash
export LIMIT_MONITOR_WIND_FIELD_MAPPING_VERIFIED=false
```

Windows 可在未提交的 `config\local_env.bat` 中临时关闭：

```bat
set LIMIT_MONITOR_WIND_FIELD_MAPPING_VERIFIED=false
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
6. 启用科创监控时，基于本次归档回执运行独立科创分支；该分支失败不撤销既有发布

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

## 十、科创资产监控

侧栏新增“科创资产监控”。债券仅取底稿1的直接持仓，以 Wind `scitechbondornot`
识别，数量使用 `库存数量(万)_PR`（万元）。所有部门、账户一并汇总，不纳入
底稿2穿透持仓。以持仓日期为基准，`回售/到期日` 距离为 0–7 个自然日时提醒；
不使用其他到期字段、不设最低规模、不将回售视为必然兑付。负数量按原值保留并列入
待核实，不产生七日提醒。

基金读取 `统计报表底稿3_股基产.xlsx` 的 `基金持仓明细表`，仅纳入
`资产种类=基金` 且 `名称` 含“科创”的记录。`库存数量` 除以 10,000 展示万份，
不纳入私募基金、不做日期预警。债券和基金不合并金额。部门、账户和证券筛选只影响
明细及对应 CSV 下载，顶部概览始终汇总全部部门。

`config/settings.yaml` 的 `scitech.enabled` 控制每日附加分支（默认开启），
`scitech.wind_timeout_seconds` 为 Wind 子进程硬超时（默认 90 秒）。Windows
和 migration 路径已将底稿3配置在底稿1、2同目录；local 从现有 `data_dir` 读取。
主机需安装并登录 Wind，运行 Python 可加载 WindPy。底稿3日期必须与本次主快照一致。

该分支在既有归档、交易前 current 发布及展示快照尝试完成后运行。Stage1 只额外
保留同一次读取的原始债券副本，不修改其标准化输出。归档事务提供精确的
`(data_date, captured_at)` 回执；科创输入、分类原值、查询时间、结果及错误写入
独立 `scitech_runs` 表，使用自己的事务和结果版本，不写主结果表或 current。
首次每日运行会自动创建该表；网页只有读取权限需求，不负责建表或连接 Wind。

分类未知或异常列入待核实，不按“否”处理；未生成、运行中、中断、失败、完整和有待核实
记录分别展示。页面只读取所选主快照对应批次，不回退到其他日期或其他批次。
历史分类使用保存值；补跑会重新查询分类并记录实际取数时间。
债券与基金输入分别校验：一侧缺文件、缺字段或持仓日期不符时，该侧显示“不可用”，
指标保存为 null，不当作零；另一侧继续计算。两侧均不可用才整批失败。
明确不属于科创的债券以及范围外的基金不因其无关数量/日期异常污染科创待核实清单。

每日入口退出码：`0` 全部完成；`1` 主编排失败；`2` 既有数据已发布但展示快照失败
（同时查看科创分支日志）；`3` 既有数据已发布但科创失败或有待核实记录。
科创失败不撤销已发布结果。关闭 `scitech.enabled` 可停用附加分支，旧页面继续运行。
单独运行 Stage 脚本或 `daily_archive.py` 不生成科创结果，请使用每日入口。

Wind 分类失败或运行中断时，可使用启动日志中的 `run_id` 独立补跑，复用保存的原输入：

```bash
# macOS/Linux，使用与每日入口相同的 DB 环境变量
.venv/bin/python scripts/retry_scitech.py --run-id <run_id>
# Windows，使用与每日入口相同的 DB 环境变量
.venv\Scripts\python.exe scripts\retry_scitech.py --run-id <run_id>
```

补跑只更新科创数据，不重跑主链路。只允许补跑同一主快照下最新的科创运行；
正在运行的任务拒绝重复启动，超过配置的 Wind 硬超时加五分钟处理宽限期后标为“可能已中断”，
允许补跑。并发补跑串行检查，已有后续尝试时拒绝旧运行，避免覆盖新结果。
若同日主快照已被覆盖也会拒绝旧批次补跑。运行状态写入失败时仍会输出 run_id 及原因。
补跑不会修复已保存的缺失或错误日期输入；可重试有效的一侧，缺失的一侧仍不可用。
要修复底稿输入，必须补齐底稿后运行新的每日批次。两侧输入均不可用时不允许独立补跑。
开关必须为 YAML 布尔值，超时必须为正整数；科创配置错误不阻断旧归档和发布。

模块及旧链路回归：`.venv/bin/python -m pytest -q tests`。新增测试覆盖自然日边界、
资产范围、原输出不变、超时/失败隔离、事务回滚、旧批次拒绝、补跑版本及页面筛选。
