# 限额配置 Excel 重构方案（已完成留痕）

**版本：** 1.0
**日期：** 2026-04-22
**状态：** 已完成（留痕文档）

> 说明：本文保留的是立项与实施阶段的原始方案。实际落地过程中，该重构已与后续
> DB 迁移合并实现；如与当前代码不一致，以 `docs/db_migration_plan.md` 与仓库
> 当前实现为准。

---

## 一、背景与目标

### 现状

`data_source_0123/限额监控_阶段0_指标设置.xlsx` 采用"每日展开时序格式"：
配置表通过与标准日期表 cross-join，将每条配置复制为全年 365 行，用于支持限额调整从指定日期生效的历史追溯需求。

| 统计 | 数值 |
|---|---|
| 有日期列的 Sheet 数 | 13 个 |
| 实际有效配置项数 | ~426 条 |
| 当前总行数 | ~116,000 行 |
| 膨胀倍数 | 365× |

此外，`持仓限额_指标.xlsx` 是截面格式（30行），但**当前代码中完全未被引用**，属于孤立文件。

### 目标

用 **"截面 Excel + 每日归档快照"** 替代 **"Excel 内嵌时序"**，两者历史追溯能力等价，但新机制维护更轻：

| 操作 | 旧机制 | 新机制 |
|---|---|---|
| 变更限额 | 从变更日期起改写所有后续行 | 直接改当前 Excel 对应行 |
| 删减配置 | 需要特殊标记或停止填写 | 直接删行 |
| 历史追溯 | 查文件内对应日期的行 | 查对应日期的归档快照文件 |
| 年度续接 | 需每年重新生成全年日期展开 | 无需任何操作 |

---

## 二、原始边界假设（留痕）

- **不改** 任何 merge / join 逻辑
- **不改** 输出表的列名和格式
- **不删除** 旧文件 `限额监控_阶段0_指标设置.xlsx`
- **不处理** `持仓限额_指标.xlsx`（孤立文件，后续另议）
- **原始假设**：不改 `config/limits.yaml`
- **最终实现**：`config/limits.yaml` 已退休，相关运行时口径已转入 DB / 新配置链路
- **原始假设**：不改任何展示层代码
- **最终实现**：展示层已配合 DB 单源做了读取链路切换

---

## 三、实施步骤

### Step 0：生成重构前基准快照（实施前必须先执行）

在做任何代码改动之前，用固定数据源跑一遍完整流程，保存输出作为对比基准：

```bash
export LIMIT_MONITOR_PROFILE=local
python run_stage0.py && python run_stage1.py && python run_stage2.py
python scripts/generate_display_snapshot.py

# 保存展示层基准
cp -r data/current/display_snapshots data/_pre_refactor_baseline_display

# 保存限额明细基准
mkdir -p data/_pre_refactor_baseline_stage
cp data/current/stage1_output/限额明细_*.xlsx data/_pre_refactor_baseline_stage/
cp data/current/stage2_output/限额明细_*.xlsx data/_pre_refactor_baseline_stage/
```

---

### Step 1：生成新配置文件 `限额配置_当前.xlsx`

**源文件：** `data_source_0123/限额监控_阶段0_指标设置.xlsx`
**目标文件：** `data_source_0123/限额配置_当前.xlsx`（用户后续上传到 sjz-share 对应路径）

**规则：**

1. 对有 `日期` 列的 13 个 Sheet：
   - 找出该 Sheet 的**最新日期**（代表当前有效配置）
   - 只保留该最新日期对应的所有记录
   - 删除 `日期` 列
   - Sheet 名称不变，其余列顺序不变

2. 对无 `日期` 列的 2 个 Sheet（`穿透高收益债券`、`高收益限额`）：
   - 原样复制

3. 执行完毕后打印每个 Sheet 的行数对比：原始总行数 → 最新日期 → 新文件行数

> **注意：** 不能对全年数据做 `drop_duplicates` 来生成当前配置表，
> 必须明确取最新日期那一天的记录，保证语义是"当前有效配置"而非"历史全量去重"。

**预期结果（各 Sheet 行数）：**

| Sheet | 原始行数 | 新文件行数 |
|---|---|---|
| 单一债券规模限额 | 7300 | ~20 |
| 单一债券集中度限额 | 8030 | ~22 |
| 特批单一债券限额 | 3650 | ~10 |
| 特定主体限额 | 10585 | ~29 |
| 特定实控人限额 | 8395 | ~23 |
| 单一主体规模限额 | 5475 | ~15 |
| 单一实控人规模限额 | 5475 | ~15 |
| 单一担保公司规模限额 | 15695 | ~43 |
| 单一省份限额 | 12775 | ~35 |
| 高风险集中度限额 | 730 | ~2 |
| 中债隐含评级表 | 34310 | ~94 |
| 高风险省份表 | 2555 | ~7 |
| 高风险行业表 | 5110 | ~14 |
| 穿透高收益债券 | 89 | 89（不变） |
| 高收益限额 | 6 | 6（不变） |
| **合计** | **~116,000** | **~426** |

---

### Step 2：更新路径配置

**目标文件：** `config/settings.yaml`

在 `data_sources.path_profiles.migration.file_subpaths` 下新增一条映射：

```yaml
限额配置_当前.xlsx: "限额/限额监控"
```

此条与现有 `限额监控_阶段0_指标设置.xlsx: "限额/限额监控"` 保持一致，
确保 `config.get_data_file_path("限额配置_当前.xlsx")` 在 migration profile 下能正确解析。

---

### Step 3：新建配置加载模块

**新建文件：** `src/utils/limit_config_loader.py`

实现以下函数：

```python
def load_limit_config(
    sheet_name: str,
    business_date=None,
    config=None,
    inject_date: bool = True
) -> pd.DataFrame:
    """
    从 限额配置_当前.xlsx 读取指定 Sheet 的截面配置。

    参数：
        sheet_name:    Sheet 名称
        business_date: 业务日期（str "YYYY-MM-DD" 或 pd.Timestamp）
        config:        ConfigLoader 实例，用于路径 profile 切换
        inject_date:   True 时注入 '日期' 列 = pd.Timestamp(business_date)，
                       保持下游 merge(on=[..., '日期']) 兼容；
                       False 时直接返回原表（用于穿透高收益债券等）

    路径解析：
        通过 config.get_data_file_path("限额配置_当前.xlsx") 获取；
        无 config 时 fallback 到项目根目录下的 data_source_0123/限额配置_当前.xlsx
    """
```

---

### Step 4：改造 Stage1 的配置读取

**目标文件：** `src/stage1/stage1_processor.py`

**业务日期来源：**
`Stage1Processor` 构造函数中没有 `business_date` 字段。
Stage1 先加载持仓数据，在第 3 层限额配置查询开始前，
从已缓存的 `债券持仓明细表_信用债` 中取 `df['日期'].max()` 作为 `business_date`。

**需要改写的 12 个函数（均改为调用 `load_limit_config()`）：**

| 函数名 | sheet 参数 | inject_date |
|---|---|---|
| `query_single_bond_concentration_limit` | `单一债券集中度限额` | True |
| `query_single_bond_scale_limit` | `单一债券规模限额` | True |
| `query_special_single_bond_limit` | `特批单一债券限额` | True |
| `query_single_issuer_scale_limit` | `单一主体规模限额` | True |
| `query_single_controller_scale_limit` | `单一实控人规模限额` | True |
| `query_specific_issuer_limit` | `特定主体限额` | True |
| `query_specific_controller_limit` | `特定实控人限额` | True |
| `query_single_guarantee_company_limit` | `单一担保公司规模限额` | True |
| `query_bond_rating_aaa` | `中债隐含评级表` | True |
| `query_high_risk_industry` | `高风险行业表` | True |
| `query_high_risk_province` | `高风险省份表` | True |
| `query_high_yield_penetration` | `穿透高收益债券` | **False** |

**约束：** 保留各函数原有的数据清洗逻辑（`str.strip()`、类型转换、代码标准化等）。

---

### Step 5：改造 Stage2 的配置读取

**目标文件：** `src/stage2/stage2_processor.py`

**业务日期来源（需特别处理）：**
Stage2 当前处理顺序是"先加载配置，再加载 Stage1 数据"，
但业务日期来自 Stage1 数据。
解决方案：在 `process_all()` 开头，先从 Stage1 输出文件读取业务日期：

```python
# 从 Stage1 输出推断业务日期
ref_file = self.stage1_output_dir / "限额明细_债券持仓明细表_信用债1_2.xlsx"
if ref_file.exists():
    df_ref = pd.read_excel(ref_file, usecols=['日期'])
    business_date = df_ref['日期'].max()
else:
    # fallback：从持仓数据读取
    business_date = pd.Timestamp.today().normalize()
    logger.warning("未找到Stage1输出，使用当日日期作为business_date")
```

**需要改写的 4 个函数：**

| 函数名 | sheet 参数 | inject_date |
|---|---|---|
| `query_high_risk_industry` | `高风险行业表` | True |
| `query_high_risk_province` | `高风险省份表` | True |
| `query_high_risk_concentration_limit` | `高风险集中度限额` | True |
| `query_region_concentration_limit` | `单一省份限额` | True |

**约束：** 保留现有后处理逻辑，尤其是 `ProvinceNormalizer` 省份标准化。

---

### Step 6：扩展每日归档快照（原始方案，最终未采用）

本节原计划是在本地 `data/history/` 下追加 `config_snapshot/` 与 `data_date.txt`
式快照。最终实现已改为：

- `scripts/daily_archive.py` 直接写入 MySQL；
- 历史回放通过 `archive_meta + stage 表` 完成；
- 不再写 `data/history/`、`config_snapshot/`、`data_date.txt`。

也就是说，配置历史口径由“归档当日写入 DB 的 stage 结果 / archive_meta”承接，
不再保留本地目录式配置快照方案。

---

## 四、新增文件清单

| 文件 | 说明 |
|---|---|
| `data_source_0123/限额配置_当前.xlsx` | 新格式截面配置文件（需用户上传 sjz-share） |
| `src/utils/limit_config_loader.py` | 配置加载模块 |

## 五、修改文件清单

| 文件 | 改动内容 |
|---|---|
| `config/settings.yaml` | `file_subpaths` 新增一行映射 |
| `src/stage1/stage1_processor.py` | 12 个配置读取函数改调 `load_limit_config()` |
| `src/stage2/stage2_processor.py` | 4 个配置读取函数改调 `load_limit_config()`，补充业务日期获取逻辑 |
| `scripts/daily_archive.py` | 新增配置文件快照步骤 |

---

## 六、T-1 补跑说明（最终口径）

补跑场景（`python run_stage0.py --target-date YYYY-MM-DD`）仅限于 T-1，
即在 T 日运行补处理 T-1 数据。

最终实现中，系统不再维护 `data/history/T-1/config_snapshot/`。

若配置在 T-1 到 T 之间发生变更（极罕见），当前口径是：
1. 由业务侧准备 T-1 当时生效的 `限额配置_当前.xlsx`
2. 临时替换当前配置后执行补跑
3. 补跑结束后恢复最新配置
4. 历史展示回放仍以 DB 中该次归档写入的 stage 结果 / `archive_meta` 为准

当前代码不会自动查找“历史配置快照”，这也是后续 DB 单源设计中明确接受的边界。
