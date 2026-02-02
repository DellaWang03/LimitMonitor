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

将源数据文件放入 `限额/` 目录：
- `统计报表底稿2_债券SPPI.xlsx`
- `限额监控_阶段0.xlsx`
- `限额监控_阶段1.xlsx`
- `限额监控_阶段2.xlsx`

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
python run_stage0.py  # 阶段0: 数据提取
python run_stage1.py  # 阶段1: 限额计算
python run_stage2.py  # 阶段2: 汇总分析
```

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
│   ├── stage0/              # 阶段0：数据提取
│   ├── stage1/              # 阶段1：限额计算
│   ├── stage2/              # 阶段2：汇总分析
│   ├── visualization/       # Web可视化
│   ├── common/              # 公共工具
│   ├── extractors/          # 数据提取器
│   ├── transformers/        # 数据转换器
│   └── calculators/         # 限额计算器
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
├── scripts/                 # 辅助脚本
├── tests/                   # 测试文件
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
└── 2026-01-19/           # 日期文件夹
    ├── stage0_output/    # 阶段0完整快照
    ├── stage1_output/    # 阶段1完整快照
    └── stage2_output/    # 阶段2完整快照
```

---

## 🧪 测试与验证

### 运行测试

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

**最后更新**: 2026-01-29
