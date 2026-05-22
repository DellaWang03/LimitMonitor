# 限额配置重构 —— 专项验收校验方案（一次性）

**版本：** 1.1
**日期：** 2026-04-23
**目标：** 验证「限额配置 Excel 重构」未引入行为变化

---

## 一、先区分两套校验口径

### 1) 重构专项校验（本文档）

- **用途**：仅用于本次「限额配置 Excel 重构」验收
- **展示基准**：`data/_pre_refactor_baseline_display`
- **Stage 基准**：`data/_pre_refactor_baseline_stage`
- **当前状态**：专项脚本入口已下线，本文档仅保留为验收留痕

### 2) 前期上线全流程集成测试（发布前/收口期）

- **用途**：上线前校验、后续重要逻辑改动后的业务正确性校验
- **基准**：`data_for_testing`（或后续约定的人工目标目录）
- **执行入口**：`bash tests/run_full_integration_test.sh`
- **前置条件**：先完成 `run_daily.sh` / `run_daily.bat`，确保 current 已切到待校验归档日

> 两套校验不可混用。
> `data/_pre_refactor_baseline_*` 是一次性专项验收基准，不是长期默认黄金基准。

---

## 二、专项基准说明

`_pre_refactor` 基准由重构前同源数据跑出，仅用于回答“重构前后行为是否一致”：

- `data/_pre_refactor_baseline_display/`：展示层 9 张 CSV
- `data/_pre_refactor_baseline_stage/`：Stage1/Stage2 限额明细 Excel

这套基准在专项验收通过后可归档或删除，不应作为长期默认校验口径。

---

## 三、重构专项验收执行方式（留痕）

本轮重构收尾后，专项脚本 `tests/run_refactor_validation.sh` 已删除。
若需回溯当时的专项验收口径，应人工复用以下动作：

1. `Stage0 -> Stage1 -> Stage2`
2. 生成 `data/current/display_snapshots`
3. 用 `data/_pre_refactor_baseline_display` 做展示层对比
4. 用 `data/_pre_refactor_baseline_stage` 校验 Stage 限额明细行数

---

## 四、专项通过标准

- 展示层 9 张 CSV 全部 PASS，且无结构/内容差异
- `限额明细_*.xlsx` 与专项 Stage 基准行数一致
- 如出现差异，优先排查：
  - `inject_date` 日期注入是否与业务日期一致
  - Stage2 业务日期来源是否与 Stage1 口径一致
  - 配置读取是否仍误用旧文件/旧 sheet

---

## 五、前期上线全流程集成测试不受影响

本专项验收通过后，日常与发布前校验仍按前期上线全流程集成测试口径执行：

```bash
bash tests/run_full_integration_test.sh
```

当前全流程集成测试覆盖展示对象为：

- 9 张既有展示表 CSV
- page9 主表 CSV：`全量债券监管集中度.csv`

说明：

- page9 已纳入主校验链路（由同一快照/校验链路处理，不走旁路脚本）
- KPI 暂不纳入展示快照范围（含 page9 KPI）
- page8 为查询型页面，本轮仍不纳入当前展示快照范围

`validation/validate_dashboard_display.py` 仍保持通用工具定位；全流程集成测试入口脚本会显式开启 page9 校验。

---

## 六、专项完成后处理

重构验收通过、代码合并后，可按需清理专项基准：

```bash
rm -rf data/_pre_refactor_baseline_display
rm -rf data/_pre_refactor_baseline_stage
```

如需审计留痕，也可将该目录转存到归档位置后再删除。
