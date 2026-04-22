# 限额监控自动化系统

## 📋 项目简介

**Fixed Income Bond Investment Limit Monitoring System**

固定收益事业部债券投资限额自动化监控系统，替代原有的 Excel Power Query 流程，实现自动化监控、实时展示和历史数据管理。

### 核心特性

- ✅ **7大维度限额监控**: 单一债券、主体、实控人、担保人、地域、行业、省份
- ✅ **自动化数据处理**: 取代手工Excel刷新，一键运行
- ✅ **实时Web展示**: 现代化可视化看板，交互式数据浏览
- ✅ **历史数据管理**: 支持按日期查询历史快照
- ✅ **高精度匹配**: 严格对照Excel M代码逻辑，数据准确一致

---

## 🚀 快速开始

### 1. 环境要求

- **Python**: 3.9+
- **操作系统**: Windows / macOS / Linux
- **依赖包**: 见 `requirements.txt`

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 准备数据

数据源路径通过 `config/settings.yaml` 的 `data_sources.active_profile` 统一配置：
- **生产/补跑**：使用 `migration` profile，从网络共享盘读取
- **黄金测试**：使用 `local` profile，从 `data_source_0123/` 读取

主要数据源文件（由配置文件管理，无需手动放置）：
- `风控部债券池.accdb`（债券池数据库）
- `统计报表底稿1_债券.xlsx` / `统计报表底稿2_债券SPPI.xlsx`
- `限额监控_阶段0_指标设置.xlsx`（限额指标配置）
- `净资产.xlsx` / `标准日期表.xlsx`

修改路径请编辑 `config/settings.yaml` 中的 `path_profiles` 配置。

### 4. 运行数据处理

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

# 3. 归档到对应日期（自动同时生成 current/ 和 history/ 两端的展示层快照）
python scripts/daily_archive.py --date 2026-04-07

# 4.（可选）校验展示层快照
python validation/validate_dashboard_display.py \
    --ref-dir <对应日期的参考目录>
```

> **说明**：步骤3归档完成后 `display_snapshots/` 已自动写入两端，无需单独执行 `generate_display_snapshot.py`。

---

### 代码修改后验证（黄金集成测试）

**场景**：修改了处理逻辑后，用固定的样本数据集验证代码正确性。

```bash
bash tests/run_golden_test.sh
```

- 数据源：`data_source_0123/`（2026-01-23 冻结快照）
- 参考基准：`data_for_testing_0123/`（固定 9 张展示表 CSV）
- 覆盖：Stage0 → Stage1 → Stage2 → 展示层全链路，任意阶段代码改动均可验证
- 无需网络盘连接，测试输出写入 `data/current/`

**黄金基准更新时机**：
- `data_source_0123/` 的原始数据需要换新版本时（重命名目录 + 更新 `settings.yaml`）
- 限额配置发生业务变更（`限额监控_阶段0_指标设置.xlsx` 改动）后重新导出参考CSV
- 纯代码逻辑修改不更新基准，用基准来验证代码

---

### 5. 启动Web界面

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
│   ├── calculators/         # 限额计算器
│   ├── aggregators/         # 数据聚合器
│   ├── outputs/             # 输出格式化
│   ├── utils/               # 通用工具（配置加载、日志等）
│   └── validators/          # 数据验证器
├── 限额/                     # 数据源目录 ⭐
│   ├── 风控部债券池.accdb    # Access数据库
│   ├── 标准日期表.xlsx       # 交易日日历
│   ├── 统计报表底稿1_债券.xlsx
│   └── ...                  # 其他数据源文件
├── data/                    # 输出数据
│   ├── current/            # 最新数据（3个stage输出）
│   └── history/            # 历史数据快照
├── config/                  # 配置文件 ⭐
│   ├── limits.yaml         # 限额配置
│   └── settings.yaml       # 系统设置（含数据源路径）
├── docs/                    # 文档
│   ├── CONFIG_MANAGEMENT.md  # 配置管理说明 ⭐
│   └── DATE_VALIDATOR_FIX.md # 日期验证修复说明
├── scripts/                 # 运维与工具脚本
│   ├── __init__.py         # 使 scripts 成为 Python 包（供 daily_archive.py 导入）
│   ├── daily_archive.py    # 每日归档
│   └── generate_display_snapshot.py  # 展示层 9 张 CSV 快照生成
├── tests/                   # 测试与验证
│   └── run_golden_test.sh  # 黄金集成测试入口 ⭐
├── data_source_0123/        # 黄金测试数据源（Jan 23 冻结快照）⭐
├── data_for_testing_0123/   # 黄金测试参考基准（Jan 23 展示层CSV）⭐
├── validation/              # 验证脚本
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

**数据源路径配置**（v2.1新增）：
```yaml
data_sources:
  # 数据源根目录（相对于项目根目录）
  data_dir: "限额"
```

- 所有主程序（`run_stage0/1/2.py`）从此配置读取数据源路径
- 修改此配置即可切换整个系统的数据源目录
- 无需在多个文件中修改硬编码路径

**详细说明**：查看 [`docs/CONFIG_MANAGEMENT.md`](docs/CONFIG_MANAGEMENT.md)

### limits.yaml - 限额配置

定义各维度的限额值、准入标准、风险分类等。

### settings.yaml - 系统设置

配置数据路径、日志级别、处理参数等。

---

## 📈 历史数据管理

系统支持历史数据快照功能：

```bash
# 每日运行会自动归档到 data/history/YYYY-MM-DD/
bash run_daily.sh

# Web界面可选择查看历史日期
# 左侧边栏 → 选择日期 → 选择历史快照
```

历史数据结构：
```
data/history/
└── 2026-04-10/              # 日期文件夹
    ├── stage0_output/       # 阶段0完整快照
    ├── stage1_output/       # 阶段1完整快照
    ├── stage2_output/       # 阶段2完整快照
    ├── display_snapshots/   # 展示层 9 张 CSV 快照
    └── data_date.txt        # 数据业务日期
```

---

## 🧪 测试与验证

### 运行测试

**黄金集成测试（代码改动后首选）**

```bash
bash tests/run_golden_test.sh
```

一键运行全链路（Stage0→Stage1→Stage2→展示层），对比 `data_for_testing_0123/` 中的参考基准。无需网络盘，无需历史归档。

```bash
# 环境检查
python tests/check_environment.py

# Stage1验证
python tests/validate_stage1.py

# Stage2验证
python validation/validate_stage2.py

# 完整验证
python validation/validate_all.py
```

### 展示层快照校验（单模式 9 CSV 严格校验）

将 Python Pipeline 生成的看板数据与 Excel 手动导出的参考 CSV 逐字段对比：

```bash
# 使用默认参考目录（data_for_testing_0410/）
python validation/validate_dashboard_display.py

# 指定参考目录或历史快照目录
python validation/validate_dashboard_display.py --ref-dir data_for_testing_0407
python validation/validate_dashboard_display.py --snapshot-dir data/history/2026-04-10/display_snapshots

# 只校验某张表（固定 9 张清单内）
python validation/validate_dashboard_display.py --table 单一信用限额
```

> 校验前须确保 `data/current/display_snapshots/` 已生成（`run_daily.sh` 步骤 [4/5] 自动生成；
> 补数后可手动执行 `python scripts/generate_display_snapshot.py` 刷新）。
> 当前黄金测试只覆盖 9 张展示表 CSV，不覆盖 KPI、page8 查询样例、page9 页面级对象。

### 数据对比

所有输出数据都经过严格验证，与Excel Power BI参考数据对比：

- ✅ 单一担保人总持仓
- ✅ 特定主体限额明细
- ✅ 特定实控人限额明细
- ✅ 高收益债券全价成本
- ✅ 地域集中度限额

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

1. 在 `config/limits.yaml` 添加配置
2. 在 `src/stage1/` 或 `src/stage2/` 添加计算逻辑
3. 在 `src/visualization/pages/` 添加展示页面
4. 验证数据准确性

### Q4: 历史数据占用空间大？

历史数据会随时间累积，建议定期清理旧数据：

```bash
# 保留最近30天的历史数据
find data/history/ -type d -mtime +30 -exec rm -rf {} +
```

---

## 📞 支持与反馈

如有问题或建议，请：
1. 检查 `.cursorrules` 文件中的交互规范
2. 查看 `docs/` 目录中的详细文档
3. 运行诊断脚本进行问题排查

---

## 📜 更新日志

### v2.4 (2026-04-14)
- ✅ **引入黄金集成测试**（`tests/run_golden_test.sh`）
  - 数据源：`data_source_0123/`（2026-01-23 冻结快照）
  - 参考基准：`data_for_testing_0123/`（9个展示层CSV）
  - 替代原「历史数据重跑」方案，覆盖 Stage0/1/2 + 展示层全链路
- ✅ `config/settings.yaml` local profile 配置 `data_dir: "data_source_0123"`
- ✅ `run_daily.sh` / `run_daily.bat` 步骤编号统一为 5 步制
- ✅ 展示层快照生成独立为 `scripts/generate_display_snapshot.py`（单模式 9 CSV）
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

**最后更新**: 2026-04-14
