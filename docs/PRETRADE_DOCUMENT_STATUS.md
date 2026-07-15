# 交易前试算文档状态登记

状态日期：2026-07-15

适用分支：`codex/pretrade-shared-core`

上线行为基线：GitHub `main` 提交 `579af695fb8727dec8249f66d07a8b0e723da137`

## 1. 使用规则

本登记用于消除历史方案、旧实现和当前权威口径之间的冲突。

1. `AUTHORITATIVE` 是业务、数据和验收结论的唯一依据。
2. `ACTIVE_IMPLEMENTATION_PLAN` 只能实施 `AUTHORITATIVE` 已冻结内容，不得创设新业务口径。
3. `SUPERSEDED` 仅用于追溯历史决策和审计问题，不得作为开发、测试、验收或合并依据。
4. `DEFERRED_VISUAL_REFERENCE` 只可在业务、数据库及差分验收通过后用于两个指定页面的视觉参考，不得修改业务结论。
5. 文档未在本登记出现时，不自动取得权威地位；发生冲突一律以 `AUTHORITATIVE` 为准。
6. 任何新结论必须先修改权威规格并单独评审，不能通过代码、测试或旧文档反向改变规格。

## 2. AUTHORITATIVE

| 文档 | 状态 | 用途 |
|---|---|---|
| `docs/PRETRADE_SHARED_CORE_SPEC.md` | 已冻结 | 唯一业务口径、共同内核、数据库契约、Wind 边界和总体验收规格 |

权威规格所引用的生产事实来自 GitHub `main@579af695...` 的 Stage0、Stage1、Stage2 行为；若自然语言与已冻结生产特征测试发生歧义，必须暂停并补充规格评审，不能自行选择更严或更松的解释。

## 3. ACTIVE_IMPLEMENTATION_PLAN

| 文档 | 状态 | 用途 |
|---|---|---|
| `docs/superpowers/plans/2026-07-15-pretrade-safe-baseline.md` | 待执行 | 在零生产逻辑修改下生成 `data_source_0123` 的可重复金样；这是共同内核开发前的第一道正式门禁 |

该计划完成前：

- 不提取共同业务内核；
- 不迁移最终交易前数据库；
- 不合并旧交易前功能分支；
- 不把现有交易前页面结果作为业务正确性证据；
- 不运行正式归档或改动生产 `current` 指针。

## 4. SUPERSEDED

以下材料可能存在于 `delivery/clean-code-snapshot`、`codex/pretrade-bond-limits` 或其历史提交中。保留它们是为了审计追溯，不代表它们仍有效。

| 历史文档 | 失效原因 |
|---|---|
| `docs/PRETRADE_LIMIT_ACCEPTANCE.md` | 验收对象是旧交易前实现，不能证明与上线 Stage0/1/2 严格同口径 |
| `docs/superpowers/plans/2026-07-13-pretrade-bond-limits.md` | 补丁式新增模块计划，先于共同内核和不可变数据库契约 |
| `docs/superpowers/plans/2026-07-14-pretrade-audit-fixes.md` | 修复旧平行规则引擎，不能替代共同内核重构 |
| `docs/superpowers/plans/2026-07-14-pretrade-latest-only-simplification.md` | 以旧数据读取模型为前提，已被不可变快照契约取代 |
| `docs/superpowers/specs/2026-07-14-pretrade-latest-only-simplification-design.md` | 同上 |
| `docs/superpowers/plans/2026-07-15-pretrade-latest-available-snapshot.md` | 仅表达“最新可用”选择，未形成生产结果闭包和共同内核 |
| `docs/superpowers/specs/2026-07-15-pretrade-latest-available-snapshot-design.md` | 同上 |
| `docs/superpowers/specs/2026-07-15-pretrade-business-parity-remediation-design.md` | 仍以修补交易前平行引擎为主，未达到零业务差异目标 |
| `docs/superpowers/plans/2026-07-15-pretrade-db-only-context.md` | 已完成的过渡性只读上下文计划，按 `data_date` 覆盖且依赖本地 Wind 缓存，不是最终不可变数据库设计 |
| `docs/superpowers/specs/2026-07-14-pretrade-db-only-context-design.md` | 同上；可保留字段映射、列校验和事务经验，但不能保留第二套公式或最终快照身份模型 |

### 对应代码的治理状态

- `delivery/clean-code-snapshot@d87aa2e9` 的数据库只读上下文：`TRANSITIONAL_EVIDENCE_ONLY`。允许复用经重新验证的输入映射、完整性检查和事务模式；禁止直接认定为最终数据库架构。
- `codex/pretrade-bond-limits@5a0e9e54` 的交易前功能：`AUDIT_EVIDENCE_ONLY`。允许提取回归案例和已发现缺陷；禁止整体合并、整体 cherry-pick 或把 `src/pretrade` 的公式作为共同内核。
- 当前共同内核分支只从 `579af695...` 向前实施。任何历史代码复用都必须逐文件证明不引入第二套业务规则。

## 5. DEFERRED_VISUAL_REFERENCE

以下材料只描述两个新增页面的视觉与交互方向：

- `docs/superpowers/plans/2026-07-14-pretrade-ui-style-alignment.md`
- `docs/superpowers/specs/2026-07-14-pretrade-ui-style-alignment-design.md`
- `docs/superpowers/plans/2026-07-14-pretrade-institutional-compact-ui.md`
- `docs/superpowers/specs/2026-07-14-pretrade-institutional-compact-ui-design.md`

这些材料不决定限额适用性、聚合、限额选择、公式、边界、缺失/不适用状态或数据库读取方式。只有在权威规格第 7 节的业务、数据库和差分门禁全部通过后，才可在“不修改其余页面”的范围内实施 UI 验收。

## 6. 后续文档顺序

后续只允许按以下顺序新增计划：

1. 安全金标基线实施及证据；
2. 生产共同内核提取计划；
3. 不可变数据库快照与全量落库计划；
4. 持仓/非持仓主数据适配与 Wind 落库计划；
5. 单券和一揽子服务接入计划；
6. 全量差分、故障注入和回滚计划；
7. 两个指定页面的最终 UI 回归计划。

每份后续计划必须显式引用 `docs/PRETRADE_SHARED_CORE_SPEC.md`，并列出它实现的规格章节。未通过前一门禁时，不得把后一计划标记为可执行。
