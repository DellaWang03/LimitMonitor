# KPI卡片总持仓修复说明

## 问题描述

在可视化页面的KPI卡片中，"总持仓"的计算存在**重复计算**问题：

### 错误逻辑（修复前）
```python
# 对已汇总的列求和
total_position = df['单一债券总持仓_PR'].sum()
```

### 问题原因
- `单一债券总持仓_PR` 等字段在数据表中**每行都是该债券的总持仓**（已汇总）
- 如果一个债券有3笔明细持仓，表格中有3行
- 每行的 `单一债券总持仓_PR` 都显示相同的值（例如600万）
- 对这列求和：600 + 600 + 600 = **1,800万**（错误！重复计算3次）
- 正确应该是：对明细持仓求和 = 100 + 200 + 300 = **600万**

---

## 修复方案

### 核心原则
**统一使用明细级别的持仓列（`库存数量(万)_PR`），不使用已汇总的列（`XX总持仓_PR`）**

---

## 修复详情

### ✅ **Page1 - 单一信用限额**

#### 修复内容
1. 移除 `_render_kpi_cards` 函数的 `total_column` 参数
2. 统一使用 `position_column`（默认为 `库存数量(万)_PR`）
3. 更新所有调用，移除已汇总列参数

#### 修复前
```python
def _render_kpi_cards(df, highlight_column, position_column='库存数量(万)_PR', total_column=None):
    if total_column and total_column in df.columns:
        total_position = df[total_column].sum()  # ← 错误：对已汇总列求和
    elif position_column in df.columns:
        total_position = df[position_column].sum()

# 调用
_render_kpi_cards(filtered_df, '单一债券是否超限', '库存数量(万)_PR', '单一债券总持仓_PR')
```

#### 修复后
```python
def _render_kpi_cards(df, highlight_column, position_column='库存数量(万)_PR'):
    """统一使用明细级别的持仓列，避免重复计算"""
    if position_column in df.columns:
        total_position = df[position_column].sum()  # ✓ 正确：对明细持仓求和

# 调用
_render_kpi_cards(filtered_df, '单一债券是否超限', '库存数量(万)_PR')
```

#### 影响范围
- Tab1 - 单一债券规模
- Tab3 - 单一主体规模
- Tab4 - 单一实控人规模
- Tab5 - 单一担保人规模

---

### ✅ **Page3 - 分类信用限额**

#### 状态
**已正确**，无需修复

```python
total_position = df['库存数量(万)_PR'].sum()  # ✓ 正确
```

---

### ✅ **Page4 - 专业担保明细**

#### 修复内容
修正KPI计算逻辑，正确处理多日期和多业务分类的数据

#### 问题分析
数据源唯一键是：`(日期, 业务分类, 授信担保公司名称)`
- 同一公司可能有多个业务分类（如"自营"、"资管"）
- 如果按公司名称去重并取 `first()`，会**丢失其他业务分类的持仓**

#### 修复前（错误）
```python
# ❌ 问题：groupby().first() 会丢失同一公司的其他业务分类记录
df_latest = df.sort_values('日期', ascending=False).groupby('授信担保公司名称', as_index=False).first()
total_companies = len(df_latest)
total_position = df_latest['单一担保人总持仓_PR'].sum()  # ← 错误：丢失了其他业务分类
```

#### 修复后（正确）
```python
# ✓ 正确逻辑：
# 1. 先筛选最新日期的所有记录（包含所有业务分类）
latest_date = df['日期'].max()
df_latest_date = df[df['日期'] == latest_date].copy()

# 2. 公司数量：按公司名称去重计算
total_companies = df_latest_date['授信担保公司名称'].nunique()

# 3. 总持仓、总限额：使用最新日期所有记录的总和（不去重，包含所有业务分类）
total_position = df_latest_date['单一担保人总持仓_PR'].sum()
total_limit = df_latest_date['单一担保公司规模限额'].sum()
```

#### 关键区别
| 指标 | 错误逻辑 | 正确逻辑 |
|------|---------|---------|
| **公司数** | `groupby().first()` 后的行数 | `nunique()` 去重计数 |
| **总持仓** | 去重后的sum()（丢失业务分类） ❌ | 最新日期所有记录的sum() ✅ |
| **总限额** | 去重后的sum()（丢失业务分类） ❌ | 最新日期所有记录的sum() ✅ |

---

### ✅ **Page5 - 高风险**

#### 状态
**已正确**，无需修复

```python
row = df_province.iloc[0]  # 取第一行（汇总数据）
total_position = row.get('高风险省份总持仓_PR', 0)  # ✓ 正确
```

---

## 数据字段说明

### 字段命名规则
| 字段类型 | 示例 | 含义 | 单位 |
|---------|------|------|------|
| 明细持仓 | `库存数量(万)_PR` | 每笔债券持仓的明细金额 | 万元 |
| 汇总持仓 | `单一债券总持仓_PR` | 按债券代码汇总的总持仓 | 万元 |
| 汇总持仓 | `单一主体总持仓_PR` | 按主体汇总的总持仓 | 万元 |
| 汇总持仓 | `单一地域总持仓_PR` | 按省份汇总的总持仓 | 万元 |

### 重要提示
- **明细持仓**：可以安全求和，每行代表一笔独立的持仓
- **汇总持仓**：已经是汇总值，直接求和会**重复计算**
- **KPI卡片**：应统一使用明细持仓求和

---

## 单位显示

### KPI卡片单位标注
- **Page1, Page3**：万元 ÷ 10,000 = **亿元** ✅
- **Page4, Page5**：直接显示**万元** ✅
- **表格合计行**：统一显示**万元** ✅

---

## 验证方法

### 1. 检查KPI卡片数值
```python
# 正确计算
total = df['库存数量(万)_PR'].sum()

# 错误计算（会重复）
total = df['单一债券总持仓_PR'].sum()
```

### 2. 对比测试
- 如果一个债券有3笔持仓，KPI显示的总持仓应该等于3笔明细之和
- 不应该等于（单一债券总持仓 × 3）

---

## 修复时间
2026-01-29

## 修复范围
- Page1: 单一信用限额（4个Tab）
- Page4: 专业担保明细

## 无需修复
- Page3: 分类信用限额（已正确）
- Page5: 高风险（已正确）
