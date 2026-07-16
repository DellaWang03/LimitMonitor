# 交易前试算文档状态登记

状态日期：2026-07-16

适用分支：`main`（后续实施分支从包含权威规格与安全金样的 `main` 创建）

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
| `docs/PRETRADE_SHARED_CORE_SPEC.md` | 已冻结 | 唯一业务口径、共同内核、MVP 数据库上下文、Wind 边界和总体验收规格 |

权威规格所引用的生产事实来自 GitHub `main@579af695...` 的 Stage0、Stage1、Stage2 行为；若自然语言与已冻结生产特征测试发生歧义，必须暂停并补充规格评审，不能自行选择更严或更松的解释。

## 3. ACTIVE_IMPLEMENTATION_PLAN

| 文档 | 状态 | 用途 |
|---|---|---|
| `docs/superpowers/plans/2026-07-15-pretrade-safe-baseline.md` | 已完成 | 已在零生产逻辑修改下生成 `data_source_0123` 的双跑可重复金样；已按权威规格 2.1 纳入静态主体代码解析依赖 |
| `docs/superpowers/plans/2026-07-15-production-shared-kernel-extraction.md` | 已完成 | Stage1/Stage2 生产业务转换已抽成无文件 I/O 的共同内核；两次独立候选均通过逐表、逐行、逐字段零差异门禁 |
| `docs/superpowers/plans/2026-07-15-pretrade-mvp-db-context.md` | 已完成（DEV 零差异验收） | 以同次日常运行的 27 项实际输入构建 `pretrade_` 快照；开发和验收只写 `DEV`，不改既有归档/展示读路径 |
| `docs/superpowers/plans/2026-07-16-pretrade-context-simplification.md` | 已完成（最小三表重置验收） | 已重置旧四张新增验收表，冻结数据在正式库创建 1 个未发布三表快照；数据库读回、共同内核重放和 10/35/22 金样指纹均为零差异 |
| `docs/superpowers/plans/2026-07-16-pretrade-config-workbook-audit.md` | 已完成（正式库冻结验收） | 在不改变共同内核的前提下，将每次实际使用的 `限额配置_当前.xlsx` 原件作为第四张、独立于 27 输入的审计附件表保存；数据库逐字节读回、Stage0/1/2 金样和 current 未发布状态均已验证 |

完成证据：`docs/evidence/pretrade-baseline-20260710.json`。正式双跑总逻辑指纹均为
`2efae81c46b55da9b8f6a6b848f71e6341b2584059e7f5108562e4cf9f554d85`，Stage0/1/2
分别输出 10、35、22 张表；生产计算范围相对上线基线保持零差异。

共同内核与 MVP 数据库上下文门禁已经通过；交易前服务、Wind 和前端门禁完成前仍然：

- 不合并旧交易前功能分支；
- 不把现有交易前页面结果作为业务正确性证据；
- 不把本次 `DEV` 验收当作生产日常发布，或改动生产 `current` 指针。

共同内核实施期间只移动并复用了现有生产逻辑，未批准任何限额口径变更；冻结样本若出现业务差异即失败，未通过更新金样接受差异。

共同内核完成证据：`docs/evidence/production-shared-kernel-20260710.json`。候选提交
`970ef6daa82dfb9fa4e458dd1da30f496ab26447` 的两次独立重跑均得到逻辑指纹
`2efae81c46b55da9b8f6a6b848f71e6341b2584059e7f5108562e4cf9f554d85`，Stage0/1/2
分别输出 10、35、22 张表，所有文件、表、schema、行序、字段及浮点序列化差异均为 0。

旧 MVP 数据库上下文的 `DEV` 验收记录保留在 `docs/evidence/pretrade-db-context-20260710.json`，但其四表/用途模型已重置，不再是运行契约。当前有效证据为 `docs/evidence/pretrade-context-minimal-reset-20260710.json`：快照 `aa721fc5-7db7-40e9-9bac-d57accbf4d34` 含 27 项输入和 1 个原始配置附件，重放 Stage1/Stage2 分别为 35/22 张表，逻辑指纹与金样一致；原件逐字节读回等于冻结输入中的 `限额配置_当前.xlsx`（29,504 字节、16 个 sheet），唯一 current 未切换，既有展示归档、`archive_meta`、16 张归档表和展示快照保持原样。附件不参与共同内核重放，也不保存 Wind 实时主数据。

下一阶段才可设计“单券和一揽子共同内核服务与 on-the-fly Wind”。该服务必须只读 `PretradeContextStore` 的唯一 current 指针；未知账户必须拒绝；持仓债主数据只能来自交易前快照；非持仓债仅可按需获取最新 Wind 数据并在内存中校验，缺少必需字段即不可计算，且不得落库。日常 current 实际接入、交易前服务、Wind 和两个页面均未在本阶段完成或发布。

2026-07-15 交接门禁已完成：相关测试 114 项通过（另有 1 项全库跳过）；静态扫描确认 `src/pretrade`、日常运行期编排和 DEV 命令不含 pickle、展示快照读取、`ArchiveDB.write_batch()` 或旧归档写入。扫描唯一命中的 Wind 字样是静态 `issuer_wind_code_mapping.csv` 的来源清单记录；既有展示与展示快照代码不读取 `pretrade_` 表。后续服务设计不得放宽上述边界。

2026-07-16 最小化重置与原始工作簿审计门禁已完成：全量测试 `290 passed, 1 skipped`；静态扫描确认三张计算上下文表和一张原始工作簿附件表、日常编排和冻结验收命令不含 pickle、展示快照读取、旧归档写入或 Wind 请求。唯一 `Wind` 命中是冻结验收复制/验证静态 `issuer_wind_code_mapping.csv` 的路径；既有展示与展示快照仍不读取 `pretrade_` 表。

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
| `docs/superpowers/specs/2026-07-15-pretrade-mvp-db-context-design.md` | 四表、DEV/PROD、来源清单与分块设计，已由三表唯一 current 的最小契约替代 |
| `docs/superpowers/specs/2026-07-14-pretrade-db-only-context-design.md` | 同上；可保留字段映射、列校验和事务经验，但不能保留第二套公式或最终快照身份模型 |
| `PRETRADE_SHARED_CORE_SPEC.md` 附录 A | 原全量闭包、34 投影、类型化事实、Wind 落库与独立 TEST 物理隔离草案；已由当前 MVP 数据库上下文契约替代 |

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
3. 交易前 MVP 数据库上下文计划；
4. 单券和一揽子共同内核服务与 on-the-fly Wind 计划；
5. 全量差分、故障注入和回滚计划；
6. 两个指定页面的最终 UI 回归计划。

每份后续计划必须显式引用 `docs/PRETRADE_SHARED_CORE_SPEC.md`，并列出它实现的规格章节。未通过前一门禁时，不得把后一计划标记为可执行。
