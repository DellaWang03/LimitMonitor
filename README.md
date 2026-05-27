# 限额监控自动化系统

## 📋 项目简介

**Fixed Income Bond Investment Limit Monitoring System**

固定收益事业部债券投资限额自动化监控系统，替代原有的 Excel Power Query 流程，实现自动化监控、实时展示和历史数据管理。

### 核心特性

- ✅ **多维度限额监控**: 单一债券、主体、实控人、担保人、地域、行业、省份、监管集中度、高收益
- ✅ **自动化数据处理**: 取代手工Excel刷新，一键运行
- ✅ **实时Web展示**: 现代化可视化看板，交互式数据浏览
- ✅ **DB历史快照**: current / history 均从归档库读取，支持按归档日期回放
- ✅ **高精度匹配**: 严格对照Excel M代码逻辑，数据准确一致

---

## 🚀 快速开始

### 1. 环境要求

- **Python**: 3.9+
- **操作系统**: Windows / macOS / Linux
- **推荐虚拟环境**: `.venv`
- **依赖包**: 见 `requirements.txt`（已包含数据处理、DB 归档、Web 展示与测试依赖）

### 2. 安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

> Windows 可使用 `.venv\Scripts\activate` 激活环境。`WindPy`、`pyodbc` 仍依赖本机 Wind 终端 / Access 驱动等外部组件。

### 3. 准备数据

数据源路径通过 `config/settings.yaml` 的 `data_sources.active_profile` 统一配置：
- **生产/补跑**：使用 `migration` profile，从网络共享盘读取
- **本地固定样本调试**：使用 `local` profile，从 `data_source_0123/` 读取

主要数据源文件（由配置文件管理，无需手动放置）：
- `风控部债券池.accdb`（债券池数据库）
- `统计报表底稿1_债券.xlsx` / `统计报表底稿2_债券SPPI.xlsx`
- `限额配置_当前.xlsx`（限额配置主文件）
- `净资产.xlsx` / `标准日期表.xlsx`

修改路径请编辑 `config/settings.yaml` 中的 `path_profiles` 配置。

### 4. 配置归档库连接

每日归档与 Web 展示已切到 DB 单源。运行 `run_daily.sh`、生成展示快照或启动看板前，
需先注入以下环境变量：

```bash
export DB_HOST=<host>
export DB_PORT=<port>
export DB_USER=<user>
export DB_PASSWORD=<password>
export DB_NAME=<database>
```

### 5. 运行数据处理

**方式一：每日完整运行（推荐）**
```bash
# macOS/Linux
bash run_daily.sh

# Windows
run_daily.bat
```

**方式二：分阶段运行**
```bash
python run_stage0.py  # 阶段0: Wind代码处理与数据提取
python run_stage1.py  # 阶段1: 限额明细计算
python run_stage2.py  # 阶段2: 集中度指标计算
```

---

### 补跑历史漏跑数据（T+N 补跑 T-1）

**场景**：T 日忘记运行，在 T+1（或更晚）补跑 T-1 的数据。此时统计报表底稿
Excel 通常尚未更新仍是 T-1 数据，但 `风控部债券池.accdb` 已更新到新日期，
需要指定目标日期。

```bash
# 1. 从 accdb 取 T-1 日期的记录（使用 migration profile，读网盘）
python run_stage0.py --target-date 2026-04-07

# 2. Stage1/Stage2 正常运行
python run_stage1.py
python run_stage2.py

# 3. 归档到对应日期（写入 DB）
python scripts/daily_archive.py --archive-date 2026-04-07

# 4. 从该归档日快照生成展示层 CSV
python scripts/generate_display_snapshot.py --archive-date 2026-04-07

# 5.（可选）校验展示层快照
python validation/validate_dashboard_display.py \
    --ref-dir <对应日期的参考目录>
```

> **说明**：当前历史回放与 current 口径统一走 DB；`generate_display_snapshot.py` 只会把 CSV 写到 `data/current/display_snapshots/`。

---

### 测试与验证

当前测试入口已收口为两类：

```bash
# 代码级回归
python3 -m pytest -q tests

# 上线前全流程集成测试（需先完成 run_daily 并写入 DB current）
bash tests/run_full_integration_test.sh [ARCHIVE_DATE] [REF_DIR]
```

---

### 6. 启动Web界面

```bash
# macOS/Linux
bash start_web.sh

# Windows
start_web.bat
```

访问 http://localhost:8501 查看可视化看板。

---

## 📊 功能模块

### 数据处理流程

```
Stage 0: 数据提取
  ├─ 债券持仓数据提取
  ├─ Wind代码匹配
  └─ 基础字段映射
      ↓
Stage 1: 限额计算
  ├─ 单一债券规模限额
  ├─ 单一主体规模限额
  ├─ 单一实控人规模限额
  ├─ 单一担保人规模限额
  ├─ 特定主体限额明细
  └─ 特定实控人限额明细
      ↓
Stage 2: 汇总分析
  ├─ 高风险行业集中度
  ├─ 高风险省份集中度
  ├─ 地域集中度限额
  ├─ 城投集中度限额
  └─ 高收益债券投资本金规模
```

### Web可视化看板

1. **单一信用限额** - 债券/主体/实控人/担保人规模监控
2. **特定信用限额** - 特定主体与实控人限额明细
3. **分类信用限额** - 按行业/省份/地域/城投维度监控
4. **专业担保明细** - 授信担保公司规模限额
5. **高风险类明细** - 高风险行业与省份集中度
6. **地域类明细** - 地域与城投集中度限额
7. **高收益明细** - 年度高收益债券投资本金监控
8. **全量债券监管集中度** - 全量债券监管集中度明细
9. **单券可购额度查询** - 按债券代码、主证券代码、ISIN 或名称查询可购额度

---

## 📁 项目结构

```
LimitMonitorAutomation/
├── src/                      # 源代码
│   ├── stage0/              # 阶段0：Wind代码处理与数据提取
│   ├── stage1/              # 阶段1：限额明细计算
│   ├── stage2/              # 阶段2：集中度指标计算
│   ├── visualization/       # Web可视化（Streamlit 看板）
│   ├── common/              # 公共工具
│   ├── extractors/          # 数据提取器
│   ├── transformers/        # 数据转换器
│   └── utils/               # 通用工具（配置加载、日志、DB归档等）
├── 限额/                     # 数据源目录 ⭐
│   ├── 风控部债券池.accdb    # Access数据库
│   ├── 标准日期表.xlsx       # 交易日日历
│   ├── 统计报表底稿1_债券.xlsx
│   └── ...                  # 其他数据源文件
├── data/                    # 输出数据
│   └── current/            # 最新数据与展示层快照
├── config/                  # 配置文件 ⭐
│   └── settings.yaml       # 系统设置（含数据源路径）
├── docs/                    # 文档
│   ├── CONFIG_MANAGEMENT.md  # 配置管理说明 ⭐
│   └── DATE_VALIDATOR_FIX.md # 日期验证修复说明
├── scripts/                 # 运维与工具脚本
│   ├── __init__.py         # 使 scripts 成为 Python 包（供 daily_archive.py 导入）
│   ├── daily_archive.py    # 每日归档
│   ├── generate_display_snapshot.py  # 展示层核心对象 CSV 快照生成（含 page9 主表）
│   └── audit_bond_quota_query.py     # page8 单券查询审计工具
├── tests/                   # 代码级回归与上线前集成测试入口
├── data_for_testing/        # 当前默认人工目标基准目录 ⭐
├── data_source_0123/        # 固定样本数据源（Jan 23 冻结快照）⭐
├── data_for_testing_0123/   # 固定参考基准（Jan 23 展示层CSV）⭐
├── validation/              # 当前展示层 / DB current 校验脚本
├── archive/                 # 上线收尾归档（旧测试、旧 validation、一次性脚本）
├── app.py                   # Web应用入口
├── run_stage0.py           # 运行阶段0
├── run_stage1.py           # 运行阶段1
├── run_stage2.py           # 运行阶段2
├── run_daily.sh/.bat       # 每日完整运行
└── start_web.sh/.bat       # 启动Web界面
```

---

## 🔧 配置说明

### settings.yaml - 系统配置 ⭐

**数据源路径配置**：
```yaml
data_sources:
  active_profile: "local"
  path_profiles:
    local:
      data_dir: "data_source_0123"
    migration:
      data_dir: "/Volumes/sjz-share/共享数据（财务、部门）_紫琪维护"
      file_subpaths:
        限额配置_当前.xlsx: "限额/限额监控"

alerts:
  thresholds_default:
    warning: 0.80
    overlimit: 1.00
```

- `active_profile` 或环境变量 `LIMIT_MONITOR_PROFILE` 用于切换数据源 profile
- `限额配置_当前.xlsx` 是当前限额配置主文件；旧 `config/limits.yaml` 已退休
- `alerts.thresholds_default` 由 `daily_archive.py` 拷贝到 `archive_meta`，看板按归档日读取

**详细说明**：查看 [`docs/CONFIG_MANAGEMENT.md`](docs/CONFIG_MANAGEMENT.md)

### settings.yaml - 系统设置

配置数据路径、日志级别、处理参数等。

---

## 📈 历史数据管理

系统当前通过 DB 管理 current / history 快照：

```bash
# 每日运行会把当批产物写入 DB，并切换 archive_meta.is_current=1
bash run_daily.sh

# Web界面可选择查看历史 archive_date
# 左侧边栏 → 选择日期 → 选择历史数据
```

- 当前数据：`archive_meta.is_current = 1`
- 历史数据：按 `archive_date` 从 DB 读取
- 展示层 CSV 快照仅写到 `data/current/display_snapshots/`
- `data/history/` 已退出运行主链路，不再作为历史回放来源

---

## 🧪 测试与验证

### 运行测试

代码级回归测试：

```bash
python3 -m pytest -q tests
```

当前保留的测试覆盖：

- 单券可购额度查询核心口径
- 业务日期 / 交易日校验
- DB 快照读取与 DataLoader 缓存行为

旧的 Stage 级验证、环境检查和一次性脚本式测试已归档到 `archive/launch_cleanup_2026-05-26/`。

### 上线前全流程集成测试

该入口用于发布前或重要逻辑改动后的端到端核对：

```bash
bash tests/run_full_integration_test.sh [ARCHIVE_DATE] [REF_DIR]
```

如需显式使用 `.venv`：

```bash
PYTHON_BIN=.venv/bin/python bash tests/run_full_integration_test.sh [ARCHIVE_DATE] [REF_DIR]
```

前置条件：

- 已完成 `bash run_daily.sh`，且本次结果已成功写入 DB current
- 已注入 `DB_HOST` / `DB_PORT` / `DB_USER` / `DB_PASSWORD` / `DB_NAME`
- `REF_DIR` 指向人工确认的展示层参考 CSV 目录

测试内容：

- 校验 DB current 是否指向待校验归档日
- 重新生成 `data/current/display_snapshots/`
- 对比展示层快照与参考 CSV（含 page9 主表）

`tests/run_golden_test.sh` 作为兼容入口保留，会转发到 `tests/run_full_integration_test.sh`。

### 数据对比

历史逻辑校验材料仍保留在归档目录，当前上线测试以 DB current 和展示层 CSV 对比为准：

- `validation/validate_db_dashboard_consistency.py`
- `validation/validate_dashboard_display.py`
- `archive/launch_cleanup_2026-05-26/validation/logic_check/`

---

## 📝 开发规范

### 数据处理原则

1. **严格对标Excel M代码** - 所有逻辑必须与Power Query M代码一致
2. **不修改中间精度** - 仅在UI展示时格式化，中间计算保持完整精度
3. **保持列名一致** - 字段命名与Excel输出完全对应
4. **验证每次修改** - 任何逻辑变更必须验证数据准确性

### 代码风格

- 遵循PEP 8规范
- 函数添加docstring说明
- 复杂逻辑添加注释
- 使用类型提示(Type Hints)

### 提交规范

- 不创建总结性文档（除非明确要求）
- 保持诚实，不夸大或虚报
- 严格遵循Excel M代码逻辑
- 修改后必须验证数据准确性

---

## 🛠️ 常见问题

### Q1: 数据不匹配怎么办？

1. 对比Excel M代码逻辑
2. 检查字段映射是否正确
3. 运行验证脚本对比差异
4. 检查数据精度和格式化

### Q2: Web界面显示异常？

1. 清除浏览器缓存（Cmd+Shift+R / Ctrl+Shift+R）
2. 清除Streamlit缓存（界面右上角 ⋮ → Clear cache）
3. 重启Streamlit应用

### Q3: 如何添加新的限额维度？

1. 在 `限额配置_当前.xlsx` 中补充对应配置
2. 在 `src/stage1/` 或 `src/stage2/` 添加计算逻辑
3. 在 `src/visualization/pages/` 添加展示页面
4. 验证数据准确性

### Q4: 历史数据占用空间大？

历史快照已切到 DB，保留策略请按数据库侧运维规则执行。

```bash
# 示例：由 DBA 或运维按 archive_date 制定保留策略
# 具体清理方式请结合实际数据库环境执行
```

---

## 📞 支持与反馈

如有问题或建议，请：
1. 检查 `.cursorrules` 文件中的交互规范
2. 查看 `docs/` 目录中的详细文档
3. 按 `tests/README.md` 运行当前测试入口；历史诊断脚本见 `archive/launch_cleanup_2026-05-26/`

---

## 📜 更新日志

### v2.4 (2026-04-14)
- ✅ **切换至 DB 归档与展示快照链路**
  - 以前置 `run_daily` 为准，写入 DB current / history 并生成展示层快照
  - 上线前集成测试入口收口为 `tests/run_full_integration_test.sh`
  - 用于上线前期每日全链路核对
- ✅ `config/settings.yaml` local profile 配置 `data_dir: "data_source_0123"`
- ✅ `run_daily.sh` / `run_daily.bat` 步骤编号统一为 5 步制
- ✅ 展示层快照生成独立为 `scripts/generate_display_snapshot.py`（单模式，现可包含 page9 主表）
- ✅ 新增 `scripts/__init__.py`，使 scripts 成为显式 Python 包

### v2.3 (2026-01-29)
- ✅ **修复KPI卡片总持仓重复计算问题（重要）**
  - Page1-单一信用限额：移除对已汇总列的求和，统一使用明细持仓
  - Page4-专业担保明细：修正多业务分类计算逻辑，确保包含所有业务分类的持仓
  - 关键修复：公司数量用 `nunique()` 去重，总持仓/总限额用最新日期所有记录求和
  - 修复工具池读取：动态检测工作表名称（sheet0.xml/sheet1.xml）
  - 详见：`docs/KPI_FIX.md`

### v2.2 (2026-01-29)
- ✅ **修复高收益债券识别逻辑（重要）**
  - 金融工具池筛选：只保留品种="可转债"的记录
  - 匹配字段修正：改用"资产名称（简称）"而非"资产代码"
  - 穿透表逻辑完善：通过ISIN码匹配"类型"列，对所有债券生效
  - 移除账户类型限制：所有账户的可转债都检查白名单
  - **预期效果**：高收益总额从47,373.47万增加至接近PBI的48,885.07万
- ✅ 与PBI M-code逻辑完全一致
- ✅ 详细文档：`docs/HIGH_YIELD_BOND_FIX.md`

### v2.1 (2026-01-29)
- ✅ 实现统一配置管理
- ✅ 数据源路径从配置文件读取
- ✅ 修复交易日判断逻辑（使用日期类别）
- ✅ 数据源切换到 `/限额` 目录
- ✅ 增强配置加载器功能

### v2.0 (2026-01-24)
- ✅ 完成UI现代化改造
- ✅ 修复滕州信华合并逻辑
- ✅ 修复高收益债券全价成本计算
- ✅ 优化数值显示格式（智能小数位）
- ✅ 优化地域类明细页面性能
- ✅ 移除持仓为0的省份展示
- ✅ 优化Arrow序列化警告处理

### v1.0 (Earlier)
- ✅ 实现7大维度限额监控
- ✅ 完成Excel M代码逻辑复刻
- ✅ 建立历史数据管理机制
- ✅ 开发Web可视化看板

---

## 📄 许可证

内部使用系统 - 固定收益事业部

---

**最后更新**: 2026-04-29
