# 数据库落地实施计划

> 文档版本：v3.0
> 修订日期：2026-04-24
> 状态：已落地（随代码演进维护的实施留痕）

---

## 目录

1. [背景与目标](#1-背景与目标)
2. [改动文件清单](#2-改动文件清单)
3. [配置治理与口径收敛](#3-配置治理与口径收敛)
4. [数据库 Schema 设计](#4-数据库-schema-设计)
5. [分阶段实施步骤](#5-分阶段实施步骤)
6. [兼容与运行策略](#6-兼容与运行策略)
7. [边界说明](#7-边界说明)

---

## 1. 背景与目标

### 现状

当前系统的数据流经过本地文件系统中转：

```text
Stage0 计算 → data/current/stage0_output/*.xlsx
                    ↓（Stage1/2 读取）
Stage1/Stage2 计算 → data/current/{stage1,stage2}_output/*.xlsx
                    ↓ daily_archive.py
data/history/{date}/ 文件副本 + data_date.txt + config_snapshot/限额配置_当前.xlsx
                    ↓（可视化读取）
DataLoader 读本地 Excel + 配置快照
```

具体问题：

1. 可视化层（当前 / 历史）直接读取本地 Excel + 配置快照，I/O 成本高，且无法脱离文件系统运行。
2. `daily_archive.py` 通过 `shutil.copytree()` 复制整批业务文件 + 复制配置 Excel + 写 `data_date.txt`，归档逻辑依赖目录形态。
3. Stage0 中至少有 4 张被 Stage1/2 直接消费的关键中间表（调整实控人名单、风控部债券池、风控部债券池_主体、公司净资产_手工_每日），来自 `.accdb` 动态数据 + 人工维护的参考 Excel。若参考 Excel 发生变化，**历史日期的 Stage0 中间产物将无法精确复现**，必须以 `archive_date` 为键落库。
4. 历史回放强依赖 `data/history/{date}/` 这棵目录树。

### 本期目标（精简版）

> 本期目标严格收敛为：**可视化层（DataLoader / display_builders / sidebar）不再读取任何本地业务文件或配置文件，所有展示数据从 MySQL RDS 读取。**

具体落地为：

1. 把"被可视化使用的"数据全部按 `archive_date` 写入 DB：
   - **4 张 Stage0 必需中间表**（被 Stage1/2 直接消费的）；
   - **12 张 Stage1/Stage2 业务结果表**；
   - **1 张 `archive_meta`**（含 `data_date`、`is_current`、全局展示阈值 `alert_warning_threshold` / `alert_overlimit_threshold`）。
2. 业务配置 `限额配置_当前.xlsx` **不进 DB**。看板需要的所有配置阈值通过两条路径携带：
   - 业务相关阈值（监管集中度、年度高收益本金、单一债券/主体/各类别高收益限额）→ 由 Stage1/Stage2 在结果表里附加为列；
   - 全局展示阈值（warning=0.80、overlimit=1.00）→ 写入 `archive_meta` 两列。
3. `DataLoader(target_date=None)` 与 `DataLoader(target_date=<date>)` 都只查询 DB。
4. `daily_archive.py` 转型为**唯一的 DB 写库者**：扫描 `data/current/` 产物，在单个事务内写完 17 张表 + 切 `is_current=1`。Stage0/1/2 进程不感知 DB。
5. `scripts/generate_display_snapshot.py` 中的 `SnapshotDataLoader` 合并到 `DataLoader`，避免重复实现。
6. 死代码清理：`src/calculators/limit_calculator.py`、`config/limits.yaml`、`data/regulatory_concentration_limit.json`、`settings.yaml/alerts.thresholds`、`scripts/generate_limit_config.py` 不再加入日常运行链路。

### 历史展示回放与 T-1 重跑

为避免"历史回放"与"补跑"被混用，本方案明确区分两类能力：

- **历史展示回放**：给定某个 `archive_date`，看板直接读取该日期已落库的业务结果表和元数据，复现当日展示口径。**本期保证。**
- **T-1 重跑**：仅支持 `run_stage0.py --target-date YYYY-MM-DD` 在 `.accdb` 仍可提供数据的前提下对前一日做补跑。Stage1/2 在补跑时仍读取**当前** `限额配置_当前.xlsx`；这意味着补跑的口径与"昨天的真实口径"可能不一致。

**本期明确不承诺**："任意 `archive_date` 都可重新取源并精确重算"。
- `archive_date` 仅用于结果归档、元数据、展示回放；
- 数据源侧本来就不具备任意日期重取能力（accdb 通常只保留近 1–2 天）；
- 任意日期重算 + 任意日期配置回放属于**远期能力**，不在本期与二期范围。

### 不在本期范围

明确划出本期不做的事，避免实施期反复横跳：

| 项 | 不做的原因 |
|---|---|
| 16 张业务配置 sheet 落库 | 看板不再依赖配置 sheet（已通过 stage 输出列 + archive_meta 携带），DB 内不需要任何配置归档表 |
| Stage0 其余 6 张中间表落库 | 当前无消费方；如未来需要，连同源数据落库一起在远期做 |
| Stage 进程内调 DB | Stage0/1/2 完全不感知 DB；写库由 `daily_archive.py` 单点完成 |
| 原始 Excel 数据源落库 | 固定样本全流程集成测试本期继续用本地 `data/data_source_0123/`；如未来需要"完整自包含的 DB 测试"，再增加 `archive_raw_input` 表 |
| `data/history/` 双写 | 直接切 DB，不做本地双写过渡 |
| `stage1_limit_detail.py` 强制收敛 | 看板不再读 `系统参数 sheet`，监管集中度限额已在 `stage1_full_regulatory.监管集中度限额指标值` 列里；T-1 补跑时计算侧仍读当前配置 ─ 与本期"不承诺历史精确重算"的口径一致 |

### 数据库连接信息

| 参数 | 值 |
|---|---|
| host | `<DB_HOST>` |
| port | `<DB_PORT>` |
| user | `<DB_USER>` |
| password | `<DB_PASSWORD>` |
| database | `<DB_NAME>` |

> 连接参数严禁写入仓库、文档或脚本示例中，统一通过环境变量 `DB_HOST` / `DB_PORT` / `DB_USER` / `DB_PASSWORD` / `DB_NAME` 注入。若已有历史明文凭据，应按泄露事件处理并立即轮换。

**新增依赖项**：`pymysql`、`SQLAlchemy>=2.0`

---

## 2. 改动文件清单

### 2.1 新建文件

| 文件路径 | 说明 |
|---|---|
| `src/utils/archive_db.py` | MySQL 封装层：建表、批量写入、查询；只暴露 `write_batch(archive_date, payload)` 与 `read_*(archive_date)` |

### 2.2 修改文件

| 文件路径 | 改动要点 |
|---|---|
| `src/stage2/stage2_processor.py` | `query_high_yield_detail()` 与 `query_high_yield_capital()` 在写出 dataframe 前，把"高收益限额" sheet 的指标值附加为列；其他 stage2 计算逻辑不动 |
| `scripts/daily_archive.py` | 全面重写：扫 `data/current/` → 先预同步 schema，再单事务写 17 张表 → 切 `is_current=1`；删除 `shutil.copytree` 复制业务文件、`data_date.txt` 写入、`config_snapshot/` 拷贝逻辑 |
| `src/visualization/data_loader.py` | 全面切 DB：删除所有 `_load_excel_*` / `_load_runtime_config_sheet` / `_load_config_snapshot_sheet` / `_load_system_params_map`；4 个 `load_*_limit/threshold*` 改为读 stage 表 / `archive_meta`；`get_latest_date` / `get_available_dates` / `get_data_date_for_archive` 改为查 `archive_meta` |
| `src/visualization/display_builders.py` | `_load_high_yield_limits_from_loader()` 直接从 stage2 高收益结果表读附加列，删除对 `_load_runtime_config_sheet()` 的探测和本地 Excel fallback |
| `src/visualization/components/sidebar.py` | 历史下拉、`data_date` 展示走 DB（通过 `DataLoader.get_available_dates()` / `get_data_date_for_archive()`） |
| `scripts/generate_display_snapshot.py` | 删除内置 `SnapshotDataLoader`，改为薄包装：`DataLoader(target_date) → 写 CSV` |
| `tests/run_full_integration_test.sh` | 在 `generate_display_snapshot.py` 之前插一步 `daily_archive.py --archive-date <test-date>` 把数据写入测试库；`run_golden_test.sh` 保留为兼容转发入口 |
| `run_daily.sh` | 不变（流程不变），只是 `daily_archive.py` 内部行为变成"写库" |

### 2.3 不修改的文件

| 文件 | 原因 |
|---|---|
| `src/stage0/stage0_processor.py` | 写 Excel 的逻辑不变；不感知 DB |
| `src/stage1/stage1_processor.py` | 不变；继续从 `data/current/stage0_output/` 读、写 `data/current/stage1_output/` |
| `src/stage1/stage1_limit_detail.py` | 不变；本期不承诺精确重算 |
| `run_stage0.py` / `run_stage1.py` / `run_stage2.py` | 不变；不需要新增 `--archive-date`，archive_date 由 `daily_archive.py` 单点决定 |

### 2.4 删除 / 退休

| 项 | 处理 |
|---|---|
| `src/calculators/limit_calculator.py` | 删除（死代码，主流程未使用） |
| `config/limits.yaml` | 删除（仅被上述死代码引用） |
| `data/regulatory_concentration_limit.json` | 删除（只被 `generate_limit_config.py` 一次性回填用过） |
| `config/settings.yaml` 中 `alerts.thresholds` 段 | 删除（只被 `generate_limit_config.py` 一次性回填用过；运行时阈值由 `archive_meta` 提供） |
| `scripts/generate_limit_config.py` | 从 `run_daily.sh` 中移除调用；保留为一次性历史辅助脚本，文件头加显式标注"禁止在生产链路调用" |
| `tests/run_refactor_validation.sh` + `data/_pre_refactor_baseline_*` | 配置重构验收通过后下线，DB 化不再单独建专项基线 |
| `data/history/*/data_date.txt` | 不再写入；由 `archive_meta.data_date` 替代 |
| `data/history/*/config_snapshot/` | 不再写入；本地编辑界面 `限额配置_当前.xlsx` 仍保留在仓库 |
| `data/history/{date}/` 历史副本 | 历史旧目录保留不动；新归档不再写入 `data/history/`，直接走 DB |

---

## 3. 配置治理与口径收敛

### 3.1 配置定位（最终态）

| 类型 | 形式 | 用途 |
|---|---|---|
| **业务配置真源** | `data/限额配置_当前.xlsx`（16 张 sheet） | 业务人员可编辑界面 + Stage1/Stage2 计算时读取 |
| **技术配置** | `config/settings.yaml` | 路径 profile、目录映射、日志、运行开关 |
| **运行时连接** | 环境变量 | DB host/port/user/password/database |
| **运行时业务阈值（看板）** | DB 中的 stage 业务结果表附加列 + `archive_meta` 三列 | 看板取数 |

**关键点**：业务配置 Excel **不进 DB**。它在 stage1/2 计算时被读取，相关阈值随计算结果一起写入 stage 业务表 → 进 DB → 看板读出来用。

### 3.2 看板配置依赖去配置化清单

| 看板调用 | 数据本质 | 来源（迁移后） |
|---|---|---|
| `data_loader.load_regulatory_concentration_limit()` | 监管集中度限额（标量 0.16） | `stage1_full_regulatory.监管集中度限额指标值` 列（已存在） |
| `data_loader.load_high_yield_annual_limit()` | 年度高收益本金上限（标量，万） | `archive_meta.high_yield_annual_limit_wan`（由归档时从配置读取并固化） |
| `display_builders._load_high_yield_limits_from_loader()` | 单一债券/主体/各类别高收益限额映射 | `stage2_high_yield` 新增列：`单一债券限额(万)`、`单一主体限额(万)`、`<类别>_限额(万)`（**stage2 新增**） |
| `data_loader.load_alert_thresholds()` | warning=0.80 / overlimit=1.00（全局展示常量） | `archive_meta.alert_warning_threshold` / `alert_overlimit_threshold` |

`data/限额配置_当前.xlsx` 与 `config/settings.yaml` 的定位：

- **业务人员**修改 `限额配置_当前.xlsx` → 下次 stage 跑会用新值；其中高收益类别/债券/主体限额写入 stage2 结果表，年度高收益本金上限由 `daily_archive.py` 额外写入 `archive_meta` → 看板读到新值；
- **运维人员**修改 `settings.yaml/alerts.thresholds_default`（或类似命名）→ `daily_archive.py` 在写 `archive_meta` 时拷贝当前值 → 看板读到新值；
- 历史回放天然准确，因为配置值已"内化"在归档当日的 stage 结果表 / `archive_meta` 行里。

### 3.3 死代码与遗留清理

迁移开始前必须完成（也写入 §2.4）：

1. 删除 `src/calculators/limit_calculator.py`（主流程未使用）。
2. 删除 `config/limits.yaml`（仅被上述死代码引用）。
3. 删除 `data/regulatory_concentration_limit.json`（仅被一次性脚本读取）。
4. 删除 `config/settings.yaml` 中的 `alerts.thresholds` 段；新增的 `alerts.thresholds_default`（或继续用同名字段，仅作语义澄清）专门给 `daily_archive.py` 拷贝到 `archive_meta` 用。
5. 从 `run_daily.sh` 中移除对 `scripts/generate_limit_config.py` 的调用；该脚本仅保留为一次性辅助工具。

> 业务人员维护责任：`generate_limit_config.py` 退休后，`限额配置_当前.xlsx` 的 `系统参数` sheet（含告警阈值与监管集中度限额）由业务人员直接维护。需要在操作手册中明确"如何修改阈值"。

---

## 4. 数据库 Schema 设计

### 4.1 总体原则

1. 所有业务结果表与 Stage0 中间表以 `archive_date VARCHAR(10)` 作为首列，格式 `YYYY-MM-DD`。
2. 同一个 `archive_date` 下的 Stage0 必需表、Stage1/Stage2 业务结果表、`archive_meta` 视为**同一快照批次**；`daily_archive.py` 先完成 schema 预同步，再在单个数据事务内整批写入，最后切 `is_current=1`。
3. 业务结果表 / Stage0 表统一通过 `pandas.to_sql()` 自动建表，但建表 / 补列 / 建索引统一放在 `prepare_stage_tables_schema()` 预处理阶段执行；`archive_meta` 是结构化表，单独定义 DDL 并按需补列。
4. 当前模式与历史模式都查 DB，不再读 `data/current/` 或 `data/history/`。
5. `pandas.to_sql()` 仅作为批量建表/写入手段，不应完全裸奔依赖首次数据推断；实施时需补充固定 `dtype` 映射或首次建表时显式约束，避免空值/混合类型导致字段类型漂移。

### 4.2 日期模型

| 字段 | 含义 |
|---|---|
| `archive_date` | DB 快照主键。日常运行 = 当日；T-1 补跑 = 被补跑的业务日期 |
| `data_date` | 从 stage1 结果表中解析出的实际数据日期，用于"归档日 (数据日期: xxx)" 展示 |
| `captured_at` | 实际写库时间戳（`DATETIME(6)`），用于审计 |
| `target_date` | 仅用于 `run_stage0.py --target-date` 控制 `.accdb` 取哪一天的数据；不进 DB |

约定：

- 正常日常运行：`archive_date = 当日`；
- T-1 补跑：`run_stage0.py --target-date 2026-04-22` 跑完，`run_stage1.py` / `run_stage2.py` 正常跑（读 `data/current/stage0_output/`），最后 `daily_archive.py --archive-date 2026-04-22` 把这批产物贴上 `archive_date=2026-04-22` 标签写库；
- `archive_date` 只需在一个入口（`daily_archive.py`）显式传入；Stage0/1/2 不感知。

### 4.3 业务结果表（12 张）

由 `daily_archive.py` 在归档时**统一写入**。写入策略：

- 写入前按 `archive_date` 删除该日期的旧数据，再追加写入；
- 同一张表的"删旧 + 写新"必须在同一事务内；
- 写入后确保 `archive_date` 索引存在；
- DataLoader 读出后移除 `archive_date` 列，保证返回结构与原来一致。

索引：

```sql
CREATE INDEX idx_stage1_credit_1_1_date ON stage1_credit_1_1(archive_date);
CREATE INDEX idx_stage1_credit_1_2_date ON stage1_credit_1_2(archive_date);
CREATE INDEX idx_stage1_full_regulatory_date ON stage1_full_regulatory(archive_date);
CREATE INDEX idx_stage1_guarantee_date ON stage1_guarantee(archive_date);
CREATE INDEX idx_stage2_credit_2_date ON stage2_credit_2(archive_date);
CREATE INDEX idx_stage2_high_risk_industry_date ON stage2_high_risk_industry(archive_date);
CREATE INDEX idx_stage2_high_risk_province_date ON stage2_high_risk_province(archive_date);
CREATE INDEX idx_stage2_high_risk_province_detail_date ON stage2_high_risk_province_detail(archive_date);
CREATE INDEX idx_stage2_high_risk_industry_detail_date ON stage2_high_risk_industry_detail(archive_date);
CREATE INDEX idx_stage2_regional_date ON stage2_regional(archive_date);
CREATE INDEX idx_stage2_high_yield_date ON stage2_high_yield(archive_date);
CREATE INDEX idx_stage2_high_yield_capital_date ON stage2_high_yield_capital(archive_date);
```

完整表映射：

| DB 表名 | Stage | 来源 Excel 文件 | DataLoader 方法 |
|---|---|---|---|
| `stage1_credit_1_1` | stage1 | 限额明细_债券持仓明细表_信用债1_1.xlsx | `load_stage1_credit_1_1()` |
| `stage1_credit_1_2` | stage1 | 限额明细_债券持仓明细表_信用债1_2.xlsx | `load_stage1_credit_1_2()` |
| `stage1_full_regulatory` | stage1 | 限额明细_全量债券监管集中度.xlsx | `load_stage1_full_regulatory_concentration()` |
| `stage1_guarantee` | stage1 | 限额明细_单一担保人.xlsx | `load_stage1_guarantee()` |
| `stage2_credit_2` | stage2 | 限额明细_债券持仓明细表_信用债2.xlsx | `load_stage2_credit_2()` |
| `stage2_high_risk_industry` | stage2 | 限额明细_高风险行业.xlsx | `load_stage2_high_risk_industry()` |
| `stage2_high_risk_province` | stage2 | 限额明细_高风险省份.xlsx | `load_stage2_high_risk_province()` |
| `stage2_high_risk_province_detail` | stage2 | 高风险省份总持仓_2.xlsx | `load_stage2_high_risk_province_detail()` |
| `stage2_high_risk_industry_detail` | stage2 | 高风险行业总持仓_2.xlsx | `load_stage2_high_risk_industry_detail()` |
| `stage2_regional` | stage2 | 限额明细_地域集中度限额(含城投).xlsx | `load_stage2_regional()` |
| `stage2_high_yield` | stage2 | 限额明细_高收益.xlsx（**新增配置阈值列**） | `load_stage2_high_yield()` |
| `stage2_high_yield_capital` | stage2 | 限额明细_高收益_投资本金规模.xlsx（**新增 `年度限额(万)` 列**） | `load_stage2_high_yield_capital()` |

> **不入库的两张表**
> `load_stage1_single_bond()` → 限额明细_单一债券.xlsx
> `load_stage1_merged()` → 债券持仓明细表_信用债_合并风险限额相关.xlsx
> 当前无可视化调用方，不纳入本期。

#### 4.3.1 Stage2 高收益表新增列（关键改动）

参照 stage2 已有写法（如 `df['高风险行业总持仓限额(万)'] = df['信用债总持仓_PR'] * df['指标值']`），在 `query_high_yield_detail()` 与 `query_high_yield_capital()` 写出 dataframe 前，把"高收益限额" sheet 的指标值附加为列。每行一份相同的标量。

`stage2_high_yield`（限额明细_高收益.xlsx）新增列：

| 列名 | 来源 | 用途 |
|---|---|---|
| `单一债券限额(万)` | `高收益限额` sheet 的 "单一债券票面规模" | 替代 `_load_high_yield_limits_from_loader()` 中 `bond_limits["__default__"]` |
| `单一主体限额(万)` | `高收益限额` sheet 的 "单一主体票面规模" | 替代 `entity_limits["__default__"]` |
| `<类别>_限额(万)` | `高收益限额` sheet 中除上述 3 行（含"年度高收益债券投资本金规模"）外其他指标 | 替代 `bond_limits[indicator] / entity_limits[indicator]` 中按类别覆盖的限额 |

> 实施细节：可以让 stage2 在写 dataframe 前调用 `load_limit_config(sheet_name="高收益限额", ...)` 读到指标 → 限额（万）映射，把"单一债券""单一主体"展开为两个固定列，其余按类别名称展开为 N 个列。命名应稳定（不要随类别数变化命名）。如果类别数本身在变，建议使用一个 JSON 字符串列 `按类别限额JSON` 存储。

`stage2_high_yield_capital`（限额明细_高收益_投资本金规模.xlsx）仍附加年度限额列：

| 列名 | 来源 | 用途 |
|---|---|---|
| `年度限额(万)` | `高收益限额` sheet 的 "年度高收益债券投资本金规模" | 便于结果表自解释；归档时同一标量会额外写入 `archive_meta.high_yield_annual_limit_wan`，供看板在 0 行快照下稳定读取 |

### 4.4 Stage0 中间表（4 张）

由 `daily_archive.py` 在归档时统一写入，与业务结果表写入策略相同。本期只落 4 张被 Stage1/2 直接消费的必需表。

| DB 表名 | 对应 Stage0 查询 | 当前代码中的直接消费方 |
|---|---|---|
| `stage0_bond_pool` | 风控部债券池 | `Stage1Processor.query_wind_bond_pool()` |
| `stage0_adjusted_controller` | 调整实控人名单 | `Stage1Processor.query_adjusted_controller()` |
| `stage0_issuer_pool` | 风控部债券池_主体 | `Stage1Processor.query_wind_issuer_pool()` |
| `stage0_net_assets_daily` | 公司净资产_手工_每日 | `Stage2Processor` 多处集中度计算 |

索引：

```sql
CREATE INDEX idx_stage0_adjusted_controller_date ON stage0_adjusted_controller(archive_date);
CREATE INDEX idx_stage0_bond_pool_date          ON stage0_bond_pool(archive_date);
CREATE INDEX idx_stage0_issuer_pool_date        ON stage0_issuer_pool(archive_date);
CREATE INDEX idx_stage0_net_assets_daily_date   ON stage0_net_assets_daily(archive_date);
```

> **本期范围说明**：Stage1/2 在本期**仍读取本地** `data/current/stage0_output/` 中的 Excel，不读 DB；这 4 张表入库的目的是建立**历史可回放**层（看板未来如需查询当时的 Stage0 中间数据，或二期 Stage 计算切 DB 时使用）。本期不强制 Stage1/2 改为读 DB。

### 4.5 归档元数据表（1 张）

```sql
CREATE TABLE IF NOT EXISTS archive_meta (
    archive_date              VARCHAR(10)    NOT NULL PRIMARY KEY,
    data_date                 VARCHAR(10)    NULL,
    is_current                TINYINT(1)     NOT NULL DEFAULT 0,
    alert_warning_threshold   DECIMAL(10,4)  NOT NULL DEFAULT 0.8000,
    alert_overlimit_threshold DECIMAL(10,4)  NOT NULL DEFAULT 1.0000,
    high_yield_annual_limit_wan DOUBLE       NULL,
    captured_at               DATETIME(6)    NOT NULL,
    KEY idx_archive_meta_current (is_current)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

字段说明：

- `archive_date`：快照归属日期，主键；
- `data_date`：从 `stage1_credit_1_2` 等结果表的 `日期` 列推断（`max(日期)`），用于看板"归档日 (数据日期: xxx)"展示；
- `is_current`：是否为"当前"快照。同一时刻只允许一条 `is_current = 1`；由 `daily_archive.py` 在单事务内保证（先 `UPDATE SET is_current=0`，再 `UPDATE/INSERT SET is_current=1`）；
- `alert_warning_threshold` / `alert_overlimit_threshold`：归档当日生效的展示阈值；写库时从 `settings.yaml` 拷贝。看板的 `load_alert_thresholds()` 直接读这两列；
- `high_yield_annual_limit_wan`：归档当日生效的年度高收益本金上限；写库时从 `限额配置_当前.xlsx` 拷贝，供高收益页面在 0 行快照场景下稳定读取；
- `captured_at`：写库时间戳。

> **删除的字段**：原方案中的 `archive_status` 字段已删除。由于失败的写库不会留下 `archive_meta` 记录（参见 §6.3），该字段永远只能取 `'success'`，无信息量。

> **失败语义**：`daily_archive.py` 会先做 schema 预同步（可能留下建表 / 补列结果），再在单个数据事务内完成 17 张表 + `archive_meta` 写入；若数据事务内任一步失败，不会出现"业务表已写但 meta 未更新"的半批快照状态。

---

## 5. 分阶段实施步骤

### 阶段一：构建 DB 基础层（`archive_db.py`）

**目标**：建立独立、可测试的 MySQL 封装。

**改动范围**：仅新建 `src/utils/archive_db.py`。

**主要接口设计**：

```python
from sqlalchemy import create_engine, text
from datetime import datetime
import pandas as pd

class ArchiveDB:
    def __init__(self, host: str, port: int, user: str, password: str, database: str):
        url = f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}?charset=utf8mb4"
        self._engine = create_engine(url)

    @classmethod
    def from_env(cls) -> "ArchiveDB":
        """从环境变量读取连接参数。"""
        import os
        return cls(
            host=os.environ["DB_HOST"],
            port=int(os.environ["DB_PORT"]),
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
            database=os.environ["DB_NAME"],
        )

    def init_schema(self) -> None:
        """创建 archive_meta；业务表 / Stage0 表由 write_dataframe() 首次写入时自动建表。"""

    # ---------- 批次写入（daily_archive 单点调用） ----------

    def write_batch(
        self,
        archive_date: str,
        stage_tables: dict[str, pd.DataFrame],   # {table_name: df}, 含 4 张 stage0 + 12 张业务表
        data_date: str | None,
        alert_warning_threshold: float,
        alert_overlimit_threshold: float,
    ) -> None:
        """在单事务内：
        1. 对每张 stage_tables，按 archive_date 删旧 + 写新；
        2. UPDATE archive_meta SET is_current=0；
        3. INSERT/UPDATE archive_meta SET is_current=1, data_date=..., 阈值=..., captured_at=NOW(6)。
        任一步失败整体回滚。
        """

    # ---------- 业务结果表 / Stage0 表（DataLoader 读取） ----------

    def write_dataframe(self, table_name: str, archive_date: str, df: pd.DataFrame) -> int:
        """按 archive_date 覆盖写入，返回写入行数。仅在 write_batch 内部使用。"""

    def read_dataframe(self, table_name: str, archive_date: str) -> pd.DataFrame | None:
        """读取指定 archive_date 的数据，不含 archive_date 列。"""

    # ---------- 元数据表（DataLoader 读取） ----------

    def get_archive_meta(self, archive_date: str) -> dict | None:
        """返回 {archive_date, data_date, is_current, alert_warning_threshold,
        alert_overlimit_threshold, captured_at} 或 None。"""

    def get_available_dates(self) -> list[str]:
        """返回 archive_meta 中所有 archive_date 列表（降序）。"""

    def get_current_archive_date(self) -> str | None:
        """返回 is_current=1 的 archive_date，不存在则返回 None。"""
```

**关键实现细节**：

1. `write_dataframe()` 写入前插入 `archive_date` 列，并按日期先 `DELETE` 旧数据再 `to_sql(if_exists="append")`。
2. `read_dataframe()` 读出后删除 `archive_date` 列，保证与现有 `load_*()` 返回结构一致；同时把 `日期` 列恢复为 `datetime`。
3. `write_batch()` 是 `daily_archive.py` 的唯一调用入口；内部用 SQLAlchemy 事务保证原子性。
4. `pandas.to_sql()` 首次建表时需提供 `dtype` 映射，避免 Excel 空值/混合类型导致字段类型漂移；建议封装一个 `_resolve_dtype(df)` 工具方法。

**阶段一验证**：

```python
db = ArchiveDB.from_env()
db.init_schema()

import pandas as pd
df_demo = pd.DataFrame({"col_a": [1, 2], "col_b": ["x", "y"]})
db.write_batch(
    archive_date="2026-04-23",
    stage_tables={"stage1_credit_1_1": df_demo},
    data_date="2026-04-22",
    alert_warning_threshold=0.8,
    alert_overlimit_threshold=1.0,
)
assert db.get_current_archive_date() == "2026-04-23"
assert db.get_archive_meta("2026-04-23")["data_date"] == "2026-04-22"
assert len(db.read_dataframe("stage1_credit_1_1", "2026-04-23")) == 2
```

---

### 阶段二：Stage2 高收益表新增配置阈值列

**目标**：把"高收益限额" sheet 的指标值在 stage2 输出阶段附加为 dataframe 列，确保看板从 stage2 表里就能读到所需阈值。

**改动范围**：仅修改 `src/stage2/stage2_processor.py`。

**改动点**：

1. 在 `query_high_yield_detail()` 末尾、`return df` 之前：
   - 调用 `load_limit_config(sheet_name="高收益限额", config=self._config, inject_date=False)`；
   - 提取 `单一债券票面规模`、`单一主体票面规模` 两个标量；
   - 提取按类别匹配的指标行（除 `年度高收益债券投资本金规模` 外）；
   - 在 dataframe 中新增列 `单一债券限额(万)`、`单一主体限额(万)`，每行写入相同的标量；
   - 按类别匹配的限额：建议序列化为 `按类别限额JSON` 列存储（每行一份相同的 JSON 字符串），由展示侧 `_load_high_yield_limits_from_loader()` 反序列化为 dict。

2. 在 `query_high_yield_capital()` 末尾、`return df` 之前：
   - 同样调用 `load_limit_config()` 提取 `年度高收益债券投资本金规模`；
   - 新增 `年度限额(万)` 列，每行写入相同的标量。

**与既有写法对齐**：参照 stage2 已有的 `df['高风险行业总持仓限额(万)'] = df['信用债总持仓_PR'] * df['指标值']` 等写法，把"配置 → 列"的转换收敛在 stage2，刚好满足"参照其余限额页的构造"的诉求。

**阶段二验证**：

```bash
python run_stage2.py
python -c "
import pandas as pd
df_hy = pd.read_excel('data/current/stage2_output/限额明细_高收益.xlsx')
df_hy_cap = pd.read_excel('data/current/stage2_output/限额明细_高收益_投资本金规模.xlsx')
assert '单一债券限额(万)' in df_hy.columns
assert '单一主体限额(万)' in df_hy.columns
assert '年度限额(万)' in df_hy_cap.columns
print('OK')
"
```

---

### 阶段三：`daily_archive.py` 转型为单点写库者

**目标**：`daily_archive.py` 成为整条链路里**唯一的 DB 写库者**。Stage0/1/2 完全不感知 DB；它们继续按现有方式写本地 Excel。

**改动范围**：仅修改 `scripts/daily_archive.py`。

**新流程**：

```text
1. 解析 --archive-date（默认今天；T-1 补跑场景显式传入）
2. 校验 data/current/ 必需目录存在且产物完整
3. 从 4 张 Stage0 必需 Excel 读取 dataframe
4. 从 12 张业务结果 Excel 读取 dataframe
5. 从 stage1_credit_1_2.xlsx 解析 data_date（max(日期)）
6. 从 settings.yaml 读取当前阈值（warning / overlimit）
7. 单事务 write_batch(archive_date, {16 张表}, data_date, warning, overlimit)
   ├ DELETE 该 archive_date 下旧数据
   ├ INSERT 16 张新数据
   ├ UPDATE archive_meta SET is_current=0
   └ INSERT/UPDATE archive_meta SET is_current=1, ...
8. 任一步失败：整事务回滚 + 抛错退出，不更新 archive_meta
```

**移除以下原有逻辑**：

- `shutil.copytree(source_dir, target_dir)` ─ 不再复制业务文件到 `data/history/`；
- `(history_target / "data_date.txt").write_text(...)` ─ 由 `archive_meta.data_date` 替代；
- `config_snapshot/限额配置_{date}.xlsx` 拷贝 ─ 配置不进 DB，本地 Excel 也不再快照；
- `required_dirs` 目录完整性检查 ─ 改为对入库 dataframe 行数做合理性校验。

**核心代码结构**：

```python
import yaml
from src.utils.archive_db import ArchiveDB

CURRENT_DIR = Path("data/current")

REQUIRED_STAGE0_FILES = {
    "stage0_bond_pool": CURRENT_DIR / "stage0_output" / "风控部债券池.xlsx",
    "stage0_adjusted_controller": CURRENT_DIR / "stage0_output" / "调整实控人名单.xlsx",
    "stage0_issuer_pool": CURRENT_DIR / "stage0_output" / "风控部债券池_主体.xlsx",
    "stage0_net_assets_daily": CURRENT_DIR / "stage0_output" / "公司净资产_手工_每日.xlsx",
}

BUSINESS_RESULT_FILES = {
    "stage1_credit_1_1": CURRENT_DIR / "stage1_output" / "限额明细_债券持仓明细表_信用债1_1.xlsx",
    # ... 其余 11 张
}

def _read_alert_thresholds() -> tuple[float, float]:
    with open("config/settings.yaml") as f:
        cfg = yaml.safe_load(f)
    section = cfg.get("alerts", {}).get("thresholds_default", {})
    return float(section.get("warning", 0.8)), float(section.get("overlimit", 1.0))

def _read_data_date(stage_tables: dict) -> str | None:
    df = stage_tables.get("stage1_credit_1_2")
    if df is None or "日期" not in df.columns:
        return None
    max_date = pd.to_datetime(df["日期"], errors="coerce").max()
    return max_date.strftime("%Y-%m-%d") if pd.notna(max_date) else None

def main(archive_date: str) -> None:
    db = ArchiveDB.from_env()
    db.init_schema()

    stage_tables = {}
    for table_name, path in {**REQUIRED_STAGE0_FILES, **BUSINESS_RESULT_FILES}.items():
        if not path.exists():
            raise FileNotFoundError(f"缺失产物: {path}")
        stage_tables[table_name] = pd.read_excel(path)

    data_date = _read_data_date(stage_tables)
    warning, overlimit = _read_alert_thresholds()

    db.write_batch(
        archive_date=archive_date,
        stage_tables=stage_tables,
        data_date=data_date,
        alert_warning_threshold=warning,
        alert_overlimit_threshold=overlimit,
    )
```

**阶段三验证**：

```bash
python scripts/daily_archive.py --archive-date 2026-04-23
python -c "
from src.utils.archive_db import ArchiveDB
db = ArchiveDB.from_env()
print('current:', db.get_current_archive_date())
print('available:', db.get_available_dates())
meta = db.get_archive_meta('2026-04-23')
print('meta:', meta)
for t in ['stage0_bond_pool','stage0_adjusted_controller','stage0_issuer_pool','stage0_net_assets_daily',
          'stage1_credit_1_1','stage1_credit_1_2','stage1_full_regulatory','stage1_guarantee',
          'stage2_credit_2','stage2_high_risk_industry','stage2_high_risk_province',
          'stage2_high_risk_province_detail','stage2_high_risk_industry_detail',
          'stage2_regional','stage2_high_yield','stage2_high_yield_capital']:
    df = db.read_dataframe(t, '2026-04-23')
    print(t, len(df) if df is not None else 'MISSING')
"
```

---

### 阶段四：可视化层、展示快照、测试入口切换到 DB

**目标**：当前/历史模式统一查 DB，不再读取本地业务文件、配置文件或 `data_date.txt`。

**改动范围**：`src/visualization/data_loader.py`、`src/visualization/display_builders.py`、`src/visualization/components/sidebar.py`、`scripts/generate_display_snapshot.py`、`tests/run_full_integration_test.sh`。

#### 4a. `DataLoader.__init__` 切 DB

```python
self._db = ArchiveDB.from_env()
if target_date is None:
    archive_date_str = self._db.get_current_archive_date()
    if archive_date_str is None:
        raise FileNotFoundError("DB 中不存在 current 快照，请先运行归档。")
else:
    archive_date_str = target_date.strftime("%Y-%m-%d")
self.archive_date_str = archive_date_str
self.data_source = f"DB ({archive_date_str})"
```

**删除的方法**：

- `_validate_directories()`
- `_load_excel_cached()` 与 `clear_local_caches()`（或保留为无操作存根）
- `_load_excel_with_date()`
- `_load_config_snapshot_sheet()`
- `_load_current_config_sheet()`
- `_load_runtime_config_sheet()`
- `_load_system_params_map()`

#### 4b. 抽取统一 `_load_table()`

```python
def _load_table(self, table_name: str, attach_code: bool = False) -> pd.DataFrame:
    df = self._db.read_dataframe(table_name, self.archive_date_str)
    if df is None:
        raise FileNotFoundError(
            f"DB 中不存在 {self.archive_date_str} 的 {table_name}，请先运行归档。"
        )
    if "日期" in df.columns:
        df["日期"] = pd.to_datetime(df["日期"], errors="coerce")
    if attach_code:
        df = self._attach_display_code(df)
    return df
```

12 个 `load_stage*_*()` 方法逐一替换为 `_load_table()` 调用。

#### 4c. 配置读取方法改造

四个配置方法从"读 Excel/JSON"改为"读 DB 表 / meta"：

```python
def load_alert_thresholds(self) -> dict:
    meta = self._db.get_archive_meta(self.archive_date_str)
    return {
        "warning": float(meta["alert_warning_threshold"]),
        "overlimit": float(meta["alert_overlimit_threshold"]),
    }

def load_regulatory_concentration_limit(self) -> float:
    df = self._load_table("stage1_full_regulatory")
    if "监管集中度限额指标值" not in df.columns or df.empty:
        raise ValueError("stage1_full_regulatory 缺少监管集中度限额指标值")
    return float(df["监管集中度限额指标值"].iloc[0])

def load_high_yield_annual_limit(self) -> int:
    meta = self._db.get_archive_meta(self.archive_date_str)
    if meta and meta.get("high_yield_annual_limit_wan") is not None:
        return int(meta["high_yield_annual_limit_wan"])
    raise ValueError("archive_meta 缺少 high_yield_annual_limit_wan")
```

#### 4d. `display_builders._load_high_yield_limits_from_loader()` 改造

不再探测 `_load_runtime_config_sheet`，也不再 fallback 到本地 Excel。直接从 `stage2_high_yield` 表的新增列里读：

```python
def _load_high_yield_limits_from_loader(data_loader) -> tuple[dict, dict]:
    df = data_loader.load_stage2_high_yield()  # 已经是 DB 来源
    bond_limits = {"__default__": 5000.0}
    entity_limits = {"__default__": 7000.0}
    if df.empty:
        return bond_limits, entity_limits
    if "单一债券限额(万)" in df.columns:
        bond_limits["__default__"] = float(df["单一债券限额(万)"].iloc[0])
    if "单一主体限额(万)" in df.columns:
        entity_limits["__default__"] = float(df["单一主体限额(万)"].iloc[0])
    if "按类别限额JSON" in df.columns and pd.notna(df["按类别限额JSON"].iloc[0]):
        import json
        cat_map = json.loads(df["按类别限额JSON"].iloc[0])
        for k, v in cat_map.items():
            bond_limits[k] = float(v)
            entity_limits[k] = float(v)
    return bond_limits, entity_limits
```

#### 4e. 元数据接口改造

```python
@staticmethod
def _make_db() -> ArchiveDB:
    return ArchiveDB.from_env()

@staticmethod
def get_available_dates() -> list[date]:
    db = DataLoader._make_db()
    return [datetime.strptime(d, "%Y-%m-%d").date() for d in db.get_available_dates()]

@staticmethod
def get_data_date_for_archive(archive_date: date) -> str | None:
    db = DataLoader._make_db()
    meta = db.get_archive_meta(archive_date.strftime("%Y-%m-%d"))
    return meta.get("data_date") if meta else None

def get_latest_date(self) -> datetime:
    """改为从 archive_meta.data_date 读取（替代旧的从 stage1_credit_1_1 取 max(日期)）。"""
    meta = self._db.get_archive_meta(self.archive_date_str)
    if meta and meta.get("data_date"):
        return datetime.strptime(meta["data_date"], "%Y-%m-%d")
    raise ValueError("archive_meta.data_date 为空")
```

#### 4f. `generate_display_snapshot.py` 合并 SnapshotDataLoader

删除 `SnapshotDataLoader` 类，改为：

```python
def main(target_date: date | None = None) -> None:
    loader = DataLoader(target_date=target_date)
    # 复用 display_builders 生成 9 个展示对象，写出为 CSV
    ...
```

测试入口即 `python scripts/generate_display_snapshot.py [--archive-date 2026-04-23]`。

#### 4g. `tests/run_full_integration_test.sh` 调整

在原有固定样本校验流程中插入一步"归档写库"，确保展示快照生成时 DB 已具备数据：

```bash
# 1. Stage0/1/2（写本地 data/current/）
python run_stage0.py
python run_stage1.py
python run_stage2.py

# 2. 新增：归档写库（先预同步 schema，再贴 archive_date 标签）
python scripts/daily_archive.py --archive-date "$TEST_ARCHIVE_DATE"

# 3. 展示快照生成（已切到 DB）
python scripts/generate_display_snapshot.py --archive-date "$TEST_ARCHIVE_DATE"

# 4. CSV 比对（不变）
python validation/validate_dashboard_display.py
```

#### 4h. 删除 `tests/run_refactor_validation.sh`

配置重构验收已完成，且 DB 化不再需要专项基线，整套 `data/_pre_refactor_baseline_*` 一并下线。

**阶段四验证**：

```bash
streamlit run app.py
```

验证点：

1. 当前模式可正常打开，且不依赖 `data/current/stage1_output/` 或 `stage2_output/`（可临时改名验证）；
2. 历史模式切换到已入库日期时可正常展示，包括高收益页的限额和阈值颜色；
3. 高收益页的"年度限额""单一债券限额""单一主体限额"以及按类别覆盖的限额，全部来自 `stage2_high_yield*` 表新增列与 `archive_meta.high_yield_annual_limit_wan`；
4. 阈值颜色判断（预警/超限）取自 `archive_meta.alert_*_threshold`；
5. 历史下拉日期列表与 `archive_meta` 一致；`data_date` 与原 `data_date.txt` 一致；
6. 通过断点或日志确认 `src/visualization/` 在运行时不再触发 `read_excel()` / `read_text()` 读取业务或配置文件。

---

### 阶段五：清理与收口

**目标**：完成死代码与遗留文件清理，确认本期目标达成。

**清理清单**（参见 §2.4）：

1. 删除 `src/calculators/limit_calculator.py`；
2. 删除 `config/limits.yaml`；
3. 删除 `data/regulatory_concentration_limit.json`；
4. 删除 `config/settings.yaml` 中 `alerts.thresholds` 段；新增 `alerts.thresholds_default`（或保留同名字段，仅供 `daily_archive.py` 拷贝到 `archive_meta`）；
5. `scripts/generate_limit_config.py` 文件头加显式注释"禁止在生产链路调用"，从 `run_daily.sh` 移除调用；
6. 删除 `tests/run_refactor_validation.sh` 与 `data/_pre_refactor_baseline_*`。

**最终验证清单**：

1. 4 张 Stage0 必需表 + 12 张业务表在 DB 中按 `archive_date` 可读，行数与迁移前一致；
2. `archive_meta` 中的 `data_date` 与原 `data_date.txt` 一致；阈值与 `settings.yaml` 一致；
3. 看板（当前/历史）所有页面打开正常，所有限额数字、阈值颜色、剩余额度与迁移前一致；
4. 把 `data/current/stage1_output/` 与 `data/current/stage2_output/` 改名后，看板仍能正常运行；
5. `run_daily.sh` 完整跑通；T-1 补跑流程（`run_stage0.py --target-date X` + `daily_archive.py --archive-date X`）跑通；
6. `tests/run_full_integration_test.sh` 在新链路下通过（`run_golden_test.sh` 仅作为兼容入口）；
7. 仓库内不再存在 `src/calculators/limit_calculator.py`、`config/limits.yaml`、`data/regulatory_concentration_limit.json`、`tests/run_refactor_validation.sh`、`data/_pre_refactor_baseline_*`。

> 本期验收**不以**"Stage1/Stage2 历史计算重跑完全使用历史配置快照"为通过条件。该能力不在本期范围。

---

## 6. 兼容与运行策略

### 6.1 当前/历史统一走 DB

- `DataLoader(target_date=None)`：读取 `archive_meta.is_current = 1` 对应日期；
- `DataLoader(target_date=<date>)`：读取该日期对应的数据。

两种模式都**不降级**到文件系统。

### 6.2 本地文件角色（最终态）

| 产物 | 迁移后角色 |
|---|---|
| `data/限额配置_当前.xlsx` | 业务人员编辑界面；Stage1/Stage2 计算时读取，**不进 DB** |
| `config/settings.yaml` | 技术配置；`alerts.thresholds_default` 由 `daily_archive.py` 拷贝到 `archive_meta` |
| `data/current/stage0_output/` | Stage0 输出，被 Stage1/2 读取，每次运行覆盖；不归档 |
| `data/current/stage1_output/` | Stage1 输出，被 Stage2 读取，每次运行覆盖；不归档 |
| `data/current/stage2_output/` | Stage2 输出，被 `daily_archive.py` 读取后写入 DB，每次运行覆盖；不归档 |
| `data/current/display_snapshots/*.csv` | 由 `generate_display_snapshot.py` 生成；来源是 DB，不再读本地 Excel |
| `data/history/{date}/` | 历史旧目录原地保留不动；新归档不再写入 |
| `data/data_source_0123/` | 固定样本全流程集成测试数据源，保留不动 |
| `data/data_for_testing_0123/` | 固定参考基准 CSV，保留不动 |

### 6.3 异常处理

- **Stage 计算时**：读写本地文件失败抛异常，行为与改造前一致；
- **`daily_archive.py` 写库时**：schema 预同步失败会留下建表/补列结果；进入数据事务后若任一步失败 → 整事务回滚 → 抛异常退出，**不留下半批业务快照**；
- **看板查询时**：DB 读取失败直接抛错，由 Streamlit 展示明确错误，不静默降级；
- 因为是单事务写入 + 没有"半批成功"状态，所以 `archive_meta` 也不需要 `archive_status` 字段。

### 6.4 何时刷新 current

`is_current=1` 由 `daily_archive.py` 在每次成功写库时刷新。看板的"当前"模式即读最新成功归档的那一天。

### 6.5 T-1 补跑流程

```bash
# 假设要补跑 2026-04-22
python run_stage0.py --target-date 2026-04-22
python run_stage1.py
python run_stage2.py
python scripts/generate_display_snapshot.py
python scripts/daily_archive.py --archive-date 2026-04-22
```

注意：补跑用的是**当前** `限额配置_当前.xlsx`；如果配置在 2026-04-22 → 2026-04-23 之间发生过变更，补跑结果会与"昨天的真实归档"在配置维度上有差异。这是本期已知约束。

---

## 7. 边界说明

| 项目 | 说明 |
|---|---|
| **本期目标** | 可视化层（DataLoader / display_builders / sidebar）不再读取本地业务文件或配置文件 |
| **不修改页面 public 接口** | `pages/page_*.py`、`app.py` 不需要改调用方式 |
| **不修改 `load_*()` 方法签名** | 外部调用保持不变，仅内部实现切 DB |
| **不入库展示层 CSV 快照** | `display_snapshots/*.csv` 是黄金校验工件，不是运行时数据源；其生成来源改为读 DB，文件格式和位置不变 |
| **不入库业务配置 sheet** | `限额配置_当前.xlsx` 不进 DB；看板所需阈值通过 stage 输出列 + `archive_meta` 携带 |
| **不入库 Stage0 扩展 6 张表** | 当前无消费方；如未来需要，连同源数据落库一起在远期做 |
| **不入库原始数据源 Excel** | 固定样本全流程集成测试本期继续用本地 `data/data_source_0123/` |
| **Stage0/1/2 不感知 DB** | 它们只读写本地 `data/current/` 目录；写库由 `daily_archive.py` 单点完成 |
| **Stage0/1/2 不需要 `--archive-date` 参数** | `archive_date` 由 `daily_archive.py` 单点决定 |
| **本期只保证历史展示回放** | 给定 `archive_date`，看板展示读取的是该日期的结果表；Stage1/Stage2 的"历史计算重跑回放"与"任意日期重算"均不在本期、二期承诺范围 |
| **不入库死代码对应的两张表** | `load_stage1_single_bond()`、`load_stage1_merged()` 当前无调用方 |
| **不引入完整 ORM 模型层** | 使用 SQLAlchemy 作为连接和执行层即可 |
| **不删除旧历史文件** | `data/history/` 旧副本原地保留，不再新增 |
| **不做旧历史批量回填** | 历史补录如有需要，后续单独做回填脚本 |
| **不在本期改造离线回归框架** | `validate_dashboard_display.py` 的 CSV 对比逻辑保持不变；当前仅将固定样本全流程集成测试切到 DB |
| **不做本地 history 双写过渡** | 本期直接切 DB；T-1 补跑也走同一条 DB 路径 |
