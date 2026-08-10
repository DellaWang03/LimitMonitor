# Production Shared Kernel Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不改变任何已上线业务结果的前提下，把 Stage1/Stage2 中的生产清洗、分类、关联、聚合、限额选择、剩余额度与超限判断提取为唯一的无文件 I/O 共享计算内核，并让当前每日生产处理器通过兼容适配器调用该内核。

**Architecture:** Stage0 本轮保持现状，继续负责 Access/Excel/静态主体代码映射等采集与物化；它的 10 张结果表连同原始持仓、限额配置及参考表构成共享内核的显式输入。`src/risk_core` 只接收已加载的 DataFrame 和显式参数，禁止读取 Excel、配置文件、数据库、Wind、路径或环境变量。现有 `Stage1Processor`、`Stage2Processor` 保留文件加载、缓存、写 Excel 和日志职责，但所有业务转换均逐组委托给 `src/risk_core`。每次函数迁移后都用冻结的 `data_source_0123` 重跑 Stage0→Stage1→Stage2，并与已封存金样逐文件、逐表、逐行、逐字段零差异比较。

**Tech Stack:** Python 3.14、pandas、numpy、openpyxl、pytest、现有安全基线编排器、macOS `sandbox-exec`。

## Authority and frozen baseline

- 唯一业务依据：`docs/PRETRADE_SHARED_CORE_SPEC.md`。
- 本计划实现规格：3.1—3.8、6.1—6.3、7.1、8（第 4 步）、9；不提前实现第 4—5 节数据库契约。
- 上线行为基线：GitHub `main@579af695fb8727dec8249f66d07a8b0e723da137`。
- 安全金样输入：`config/test_manifests/data_source_0123-20260710-v1.json`，业务日 `2026-07-10`。
- 安全金样证据：`docs/evidence/pretrade-baseline-20260710.json`。
- 期望总逻辑指纹：`2efae81c46b55da9b8f6a6b848f71e6341b2584059e7f5108562e4cf9f554d85`。
- 期望输出数量：Stage0 10 张表、Stage1 35 张表、Stage2 22 张表。
- 当前计划起点至少包含 `main@093852991f6a079939b84d7ff5e66747a37d46ee`；执行前必须确认 `579af695...` 和 `09385299...` 均为当前分支祖先。
- 静态 `issuer_wind_code_mapping.csv` 继续按已确认口径使用当前表，不建立历史映射表；期望 11,063 行，SHA-256 为 `202a477df0be7f174c37a70d775d57629f802bf866ba3cba229d89859c329f02`，22 条显式代码 `0` 结果必须原样保留。

## Non-negotiable gates

1. 本轮不创建或修改业务数据库表，不调用 Wind，不接入两个交易前页面，不合并历史 `src/pretrade` 实现。
2. `src/risk_core` 不得导入 `ConfigLoader`、`ArchiveDB`、Wind 客户端或任何 Stage Processor，不得调用 `read_excel`、`to_excel`、`open`、`Path` 或网络 API。
3. 缺少输入表与合法空表严格区分：缺少必需键立即失败；存在但为空的 DataFrame 按生产函数现有行为继续计算。
4. 内核必须深拷贝输入；调用前后的输入 DataFrame 内容、索引、列顺序和 dtype 均不得被修改。
5. 生产输出的表集合、工作表、列顺序、逻辑 dtype、空值、行顺序和每个单元格必须与金样完全一致。
6. 数值比较无容差；二进制浮点差异可单独归类说明，但仍判失败。
7. 特批单债只让 `规模指标值` 生效，`集中度指标值` 不生效。
8. 1_1/1_2、西咸例外、特定主体/实控人覆盖、同一主体多约束、实控人取最高、担保三键与关注池非对称行为只能移动，不能重写或“统一优化”。
9. 生产已有 `fillna(0)`、回退和缺失行为原样保留；本轮不把增强数据质量状态写回 67 张生产表。
10. 剩余额度 `< 0` 超限，`= 0` 不超限但无可购空间；不得加入 `1e-9` 等容差。
11. 高收益 PR 与年度全价成本口径继续分离；本轮不得用 PR 替代全价成本，也不得改变现有日期/统计分组。
12. 任一任务产生业务差异，立即停止后续提取；先定位到原函数、输入行与字段，不能更新金样来接受差异。

## File structure

### Create

- `config/test_manifests/pretrade-output-contract-v1.json`
- `src/risk_core/__init__.py`
- `src/risk_core/contracts.py`
- `src/risk_core/position_context.py`
- `src/risk_core/stage1_aggregates.py`
- `src/risk_core/stage1_limits.py`
- `src/risk_core/stage2_limits.py`
- `src/risk_core/kernel.py`
- `src/testing/output_contract.py`
- `src/testing/output_diff.py`
- `scripts/run_kernel_candidate.py`
- `tests/risk_core/conftest.py`
- `tests/risk_core/test_contracts.py`
- `tests/risk_core/test_io_boundary.py`
- `tests/risk_core/test_position_context_characterization.py`
- `tests/risk_core/test_stage1_aggregates_characterization.py`
- `tests/risk_core/test_stage1_limits_characterization.py`
- `tests/risk_core/test_stage2_limits_characterization.py`
- `tests/risk_core/test_kernel_orchestration.py`
- `tests/testing/test_output_contract.py`
- `tests/testing/test_output_diff.py`
- `tests/scripts/test_run_kernel_candidate.py`
- `docs/evidence/production-shared-kernel-20260710.json`

### Modify

- `src/stage1/stage1_processor.py`
- `src/stage1/stage1_limit_detail.py`
- `src/stage2/stage2_processor.py`
- `docs/PRETRADE_DOCUMENT_STATUS.md`

### Must not modify

- `src/stage0/**`
- `src/pretrade/**`（若其他分支存在也不得复制或 cherry-pick）
- `src/db/**`
- `src/visualization/**`
- `config/settings.yaml`
- `scripts/daily_archive.py`
- `data/current/**`
- `data/archive/**`
- `data_source_0123/**`
- `issuer_wind_code_mapping.csv` 的内容

## Kernel boundary

内核公开接口固定为：

```python
@dataclass(frozen=True)
class ProductionKernelParameters:
    regulatory_concentration_limit: float


@dataclass(frozen=True)
class ProductionKernelInput:
    business_date: pd.Timestamp
    frames: Mapping[str, pd.DataFrame]
    parameters: ProductionKernelParameters

    def detached_frames(self) -> dict[str, pd.DataFrame]:
        return {name: frame.copy(deep=True) for name, frame in self.frames.items()}


@dataclass(frozen=True)
class ProductionKernelResult:
    stage1_tables: Mapping[str, pd.DataFrame]
    stage2_tables: Mapping[str, pd.DataFrame]


class ProductionRiskKernel:
    def run_stage1(self, inputs: ProductionKernelInput) -> dict[str, pd.DataFrame]: ...
    def run_stage2(
        self,
        inputs: ProductionKernelInput,
        stage1_tables: Mapping[str, pd.DataFrame],
    ) -> dict[str, pd.DataFrame]: ...
```

`frames` 的键沿用生产缓存中的中文表名，避免本轮新增字段映射。所有必需键在 `contracts.py` 中分为 `STAGE1_REQUIRED_FRAMES` 和 `STAGE2_REQUIRED_FRAMES`；存在空表合法，键不存在非法。当前三个数据质量枚举只在权威规格中保留，本计划不创建会被误认为已完成质量判断的半成品记录。

## Task 1: Create an isolated execution branch and re-confirm the green baseline

**Files:** No production file changes.

- [ ] **Step 1: Create an isolated worktree**

Use `superpowers:using-git-worktrees`. Create branch `codex/production-shared-kernel` from the current `main` that contains this plan. Do not reuse `codex/pretrade-shared-core` and do not delete the host-owned `.codex-worktrees` entry.

```bash
git status --short
git merge-base --is-ancestor 579af695fb8727dec8249f66d07a8b0e723da137 HEAD
git merge-base --is-ancestor 093852991f6a079939b84d7ff5e66747a37d46ee HEAD
```

Expected: clean worktree and both commands exit `0`.

- [ ] **Step 2: Run the current test suite before changes**

```bash
/opt/homebrew/bin/python3 -m pytest -q
```

Expected starting point: `146 passed, 4 skipped`. If counts differ because new tests landed on `main`, all collected tests must still pass and the reason for count drift must be recorded.

- [ ] **Step 3: Verify sealed evidence and reference artifacts**

```bash
/opt/homebrew/bin/python3 - <<'PY'
import json
from pathlib import Path
evidence = json.loads(Path('docs/evidence/pretrade-baseline-20260710.json').read_text())
assert evidence['status'] == 'success'
assert evidence['output_fingerprint']['logical_sha256'] == '2efae81c46b55da9b8f6a6b848f71e6341b2584059e7f5108562e4cf9f554d85'
assert [(s['stage'], s['table_count']) for s in evidence['stages']] == [
    ('stage0', 10), ('stage1', 35), ('stage2', 22)
]
print('sealed baseline verified')
PY
test -d /Users/dellawang/Desktop/LimitMonitorAutomation-test-output/pretrade-baseline-20260710-main1/stage0
test -d /Users/dellawang/Desktop/LimitMonitorAutomation-test-output/pretrade-baseline-20260710-main1/stage1
test -d /Users/dellawang/Desktop/LimitMonitorAutomation-test-output/pretrade-baseline-20260710-main1/stage2
```

The three stage-level logical fingerprints of this reference root must equal the
three `logical_fingerprint.logical_sha256` values in the sealed evidence. A
directory-existence check alone is insufficient. Do not modify or regenerate
this reference root. The earlier `pretrade-baseline-20260710-gold1` directory is
a failed partial run and is explicitly forbidden as a reference.

## Task 2: Add a fail-closed table/row/field differential harness

**Files:**

- Create: `config/test_manifests/pretrade-output-contract-v1.json`
- Create: `src/testing/output_contract.py`
- Create: `src/testing/output_diff.py`
- Test: `tests/testing/test_output_contract.py`
- Test: `tests/testing/test_output_diff.py`

- [ ] **Step 1: Write failing output-contract tests**

Tests prove:

- contract dataset set equals sealed evidence exactly;
- all Stage0/1/2 XLSX tables and the Stage0 mapping CSV are represented;
- every table records sheet name, exact column order, logical dtype, stable key columns and tie-break columns;
- load fails on missing/extra table, reordered/missing column, duplicate entry or unknown dtype;
- stable keys reference existing columns;
- real duplicate business rows use `duplicate_ordinal: true` instead of being dropped.

```python
def test_contract_rejects_missing_table(tmp_path: Path) -> None:
    contract_path = write_contract(tmp_path, omit='stage1/限额明细_单一债券.xlsx')
    with pytest.raises(OutputContractError, match='输出集合不完整'):
        OutputContract.load(contract_path, evidence_path=SEALED_EVIDENCE)
```

- [ ] **Step 2: Write failing exact-diff tests**

Cover exact match, table missing, schema drift, added/deleted row, duplicate count drift, string/null drift, int/float drift, datetime drift, row-order drift and one-bit floating drift. No test uses `pytest.approx`.

```python
def test_float_serialization_difference_is_reported_but_fails() -> None:
    reference = pd.DataFrame({'代码': ['A'], '剩余额度': [0.3]})
    candidate = pd.DataFrame({'代码': ['A'], '剩余额度': [0.30000000000000004]})
    report = compare_frame(reference, candidate, contract_for(['代码']))
    assert report.passed is False
    assert report.float_serialization_differences == 1
    assert report.field_differences == 1
```

- [ ] **Step 3: Confirm red**

```bash
/opt/homebrew/bin/python3 -m pytest -q tests/testing/test_output_contract.py tests/testing/test_output_diff.py
```

- [ ] **Step 4: Implement the frozen output contract**

Build `pretrade-output-contract-v1.json` from the read-only gold root. The JSON contains every concrete filename, never wildcard patterns. Every table stores `relative_path`, `sheet_name`, the full actual `columns`, `logical_dtypes`, `stable_key_columns`, `tie_breaker_columns` and `duplicate_ordinal`.

Core output identities:

- credit detail: date + source-row identity when present; otherwise date + account + asset/master security + holding amount + duplicate ordinal;
- single bond: date + normalized single-bond grouping key/business category, with original code tie-breakers;
- issuer: date + business category + issuer Wind code/name;
- controller: date + business category + adjusted controller + applicable limit category;
- guarantee: date + business category + guarantor Wind code/name;
- special issuer/controller: date + business category + indicator name + issuer/controller identity + asset code when bond-level;
- region/industry/province: date + category/indicator name;
- high-yield detail: date + account + high-yield grouping key + asset code + duplicate ordinal;
- high-yield capital: date + account + code + short name + duplicate ordinal.

Reference/config tables use their full production join keys. Contract validation never calls `drop_duplicates`.

- [ ] **Step 5: Implement exact comparison**

`compare_output_trees()` must compare file set, sheet set/name, exact columns/dtypes, canonical values using existing `canonical_scalar()`, row identity/duplicate ordinal, added/deleted rows, per-field old/new values, row order, binary-float serialization and final logical tree fingerprint. It writes a deterministic JSON report and fails for every difference category. Full row-level reports stay in the isolated output and are not committed.

- [ ] **Step 6: Verify and commit**

```bash
/opt/homebrew/bin/python3 -m pytest -q tests/testing/test_output_contract.py tests/testing/test_output_diff.py
git diff --check
git add config/test_manifests/pretrade-output-contract-v1.json src/testing/output_contract.py src/testing/output_diff.py tests/testing/test_output_contract.py tests/testing/test_output_diff.py
git commit -m "test: add exact production output diff gate"
```

## Task 3: Add a sandboxed candidate runner without weakening the sealed runner

**Files:**

- Create: `scripts/run_kernel_candidate.py`
- Test: `tests/scripts/test_run_kernel_candidate.py`

- [ ] **Step 1: Write failing runner tests**

Require test/local environment, exact frozen manifest and static mapping, non-existing external output path, Stage0→1→2 order, no DB/Wind/archive/current mutation, candidate SHA and production-scope diff recording, exact comparison against evidence/reference, non-zero exit on any difference, unchanged protected inventory, and evidence only after success.

- [ ] **Step 2: Confirm red**

```bash
/opt/homebrew/bin/python3 -m pytest -q tests/scripts/test_run_kernel_candidate.py
```

- [ ] **Step 3: Compose existing safety utilities**

Reuse `FrozenInputManifest`, `CurrentIssuerResolver`, safe paths/environment, frozen config/path injection, sandbox probes, protected inventory, pipeline execution and logical fingerprinting. Do not modify `scripts/run_frozen_baseline.py`. Candidate runner records intentional source diffs but rejects changes outside this plan's allowlist.

- [ ] **Step 4: Verify and commit**

```bash
/opt/homebrew/bin/python3 -m pytest -q tests/scripts/test_run_kernel_candidate.py
git diff --check
git add scripts/run_kernel_candidate.py tests/scripts/test_run_kernel_candidate.py
git commit -m "test: add sandboxed kernel candidate runner"
```

## Task 4: Freeze current production behavior with characterization tests

**Files:**

- Create: `tests/risk_core/conftest.py`
- Create: `tests/risk_core/test_position_context_characterization.py`
- Create: `tests/risk_core/test_stage1_aggregates_characterization.py`
- Create: `tests/risk_core/test_stage1_limits_characterization.py`
- Create: `tests/risk_core/test_stage2_limits_characterization.py`

- [ ] **Step 1: Build minimal in-memory production-label fixtures**

Include ordinary proprietary/market-making bonds; normalized asset/master codes; three high-yield identification paths; bond/issuer pool override/fallback; controller adjustment/fallback; special bond scale+concentration; general special issuer, exact Xixian issuer and special controller; multiple constraints for one issuer; two controller categories; guarantee three-key and excluded row; attention-pool asymmetry; high-risk industry/province/region/city-investment; high-yield annual cost; zero, negative, explicit-zero limit, missing match and legal empty table.

- [ ] **Step 2: Characterize position/context construction**

Bind tests to `query_bond_position`, `query_bond_position_credit`, `query_bond_position_regulatory_full`, `query_bond_position_credit_merged`, source-row validation/collapse and all high-yield paths. Assert exact columns, order, identity, normalization, pool fallback, issuer type, controller, guarantee applicability, industry/province labels.

- [ ] **Step 3: Characterize Stage1**

Bind every total-position query from line 1490 onward and every `calculate_limit_detail_*`. Prove special scale applies/concentration does not; normal→1_2; special issuer→1_1 and baseline exclusion; exact Xixian/controller ordering; multiple issuer constraints; controller highest rule; guarantee branch/three-key/exclusions; query-specific attention pool; zero not exceeded and negative exceeded without tolerance.

- [ ] **Step 4: Characterize Stage2**

Bind calculations from `query_total_credit_position` through `query_high_yield_capital`. Prove denominators, aggregations, region/high-risk formulas, ISIN keep-last, high-yield classification and limits, annual full-price grouping, zero/negative boundary.

- [ ] **Step 5: Confirm green before extraction and commit tests only**

```bash
/opt/homebrew/bin/python3 -m pytest -q tests/risk_core
git diff --check
git add tests/risk_core
git commit -m "test: characterize production risk rules"
```

## Task 5: Define pure contracts and enforce the I/O firewall

**Files:**

- Create: `src/risk_core/__init__.py`
- Create: `src/risk_core/contracts.py`
- Create: `src/risk_core/kernel.py`
- Test: `tests/risk_core/test_contracts.py`
- Test: `tests/risk_core/test_io_boundary.py`
- Test: `tests/risk_core/test_kernel_orchestration.py`

- [ ] **Step 1: Write failing contract tests**

Test business-date validity, finite regulatory limit, missing key versus empty table, input/output copy isolation and deterministic repeated calls.

- [ ] **Step 2: Write failing AST/import firewall tests**

Fail on `pathlib`, `os`, database modules, config loaders, ArchiveDB, Wind, imports from Stage processors/pretrade, Excel/CSV/file/network reads or writes.

- [ ] **Step 3: Implement contracts and orchestration shell**

Implement the “Kernel boundary” API. Required-frame constants use exact Chinese cache keys and cover raw/credit/regulatory positions, Stage0 tables, adjustments, high-yield/rating/risk maps, all limits/parameters/denominators and Stage2 inputs. An empty DataFrame is present; a missing key fails.

- [ ] **Step 4: Verify and commit**

```bash
/opt/homebrew/bin/python3 -m pytest -q tests/risk_core/test_contracts.py tests/risk_core/test_io_boundary.py
git diff --check
git add src/risk_core tests/risk_core/test_contracts.py tests/risk_core/test_io_boundary.py tests/risk_core/test_kernel_orchestration.py
git commit -m "refactor: define production risk kernel boundary"
```

## Task 6: Extract position normalization and shared risk context

**Files:**

- Create: `src/risk_core/position_context.py`
- Modify: `src/stage1/stage1_processor.py`
- Modify: `src/risk_core/kernel.py`
- Test: `tests/risk_core/test_position_context_characterization.py`

- [ ] **Step 1: Add pure signatures**

```python
def normalize_bond_position(raw: pd.DataFrame) -> pd.DataFrame: ...
def normalize_credit_position(raw: pd.DataFrame) -> pd.DataFrame: ...
def normalize_regulatory_position(raw: pd.DataFrame) -> pd.DataFrame: ...
def build_credit_risk_context(frames: Mapping[str, pd.DataFrame]) -> pd.DataFrame: ...
def attach_isin_to_results(results, isin_mapping) -> dict[str, pd.DataFrame]: ...
```

- [ ] **Step 2: Move exact transformation bodies**

Move only transformation portions after `read_excel` from the three position queries; move `query_bond_position_credit_merged`, source-row validation/collapse, ISIN attachment and shared high-yield helpers. Preserve operation order, `astype(str)`, coercion, merge suffixes, sort, `drop_duplicates`, `fillna` and row-wise functions exactly. Do not optimize/vectorize.

- [ ] **Step 3: Keep Stage1 as compatibility adapter**

Existing methods load the same file/sheet, call the pure function and retain logging/output behavior.

- [ ] **Step 4: Focused verification**

```bash
/opt/homebrew/bin/python3 -m pytest -q tests/risk_core/test_position_context_characterization.py tests/test_stage_high_yield_and_specific_controller.py tests/test_stage0_virtual_issuer_daily.py
```

- [ ] **Step 5: Full zero-difference gate**

```bash
ENV=test LIMIT_MONITOR_PROFILE=local /opt/homebrew/bin/python3 scripts/run_kernel_candidate.py --input-root /Users/dellawang/Desktop/LimitMonitorAutomation/data_source_0123 --allow-output-root /Users/dellawang/Desktop/LimitMonitorAutomation-test-output --output /Users/dellawang/Desktop/LimitMonitorAutomation-test-output/kernel-task6 --reference /Users/dellawang/Desktop/LimitMonitorAutomation-test-output/pretrade-baseline-20260710-main1
```

Expected: `passed=true`, zero differences, exact `2efae81c...54d85`.

- [ ] **Step 6: Commit**

```bash
git diff --check
git add src/risk_core/position_context.py src/risk_core/kernel.py src/stage1/stage1_processor.py tests/risk_core/test_position_context_characterization.py
git commit -m "refactor: extract production position context"
```

## Task 7: Extract Stage1 exposure aggregation without changing query asymmetry

**Files:**

- Create: `src/risk_core/stage1_aggregates.py`
- Modify: `src/stage1/stage1_processor.py`
- Modify: `src/risk_core/kernel.py`
- Test: `tests/risk_core/test_stage1_aggregates_characterization.py`

- [ ] **Step 1: Lift every Stage1 total-position calculation**

Create one pure function per current query from `query_single_bond_total_position` through `query_single_guarantee_total_position_unfiltered`. Move the exact non-high-yield filter for reuse. Functions take explicit frames, not a Processor.

- [ ] **Step 2: Preserve dependency and insertion order**

`run_stage1()` computes in the same order as `Stage1Processor.process_all`, updating a local registry after each result. Do not reorder “independent” calculations.

- [ ] **Step 3: Verify focused asymmetry**

```bash
/opt/homebrew/bin/python3 -m pytest -q tests/risk_core/test_stage1_aggregates_characterization.py tests/risk_core/test_position_context_characterization.py
```

Assert attention-pool query differences, filtered/unfiltered guarantee totals and multiple issuer constraints.

- [ ] **Step 4: Full zero-difference gate**

Repeat Task 6 candidate command with output `kernel-task7`.

- [ ] **Step 5: Commit**

```bash
git diff --check
git add src/risk_core/stage1_aggregates.py src/risk_core/kernel.py src/stage1/stage1_processor.py tests/risk_core/test_stage1_aggregates_characterization.py
git commit -m "refactor: extract production stage1 aggregations"
```

## Task 8: Extract Stage1 limit details with explicit regulatory parameter

**Files:**

- Create: `src/risk_core/stage1_limits.py`
- Modify: `src/stage1/stage1_limit_detail.py`
- Modify: `src/stage1/stage1_processor.py`
- Modify: `src/risk_core/kernel.py`
- Test: `tests/risk_core/test_stage1_limits_characterization.py`

- [ ] **Step 1: Create pure `Stage1LimitEngine`**

Move all current public calculation methods and helpers. Constructor receives copied frames and an explicit finite regulatory concentration limit. Its `_load_regulatory_concentration_limit()` simply returns that value. Core imports only pandas/numpy and pure `src.common` helpers.

- [ ] **Step 2: Retain `LimitDetailCalculator` compatibility**

The old module keeps the same class/import path. It resolves the system parameter exactly as today only when no override is supplied, then initializes `Stage1LimitEngine`. Configuration loading stays outside core.

- [ ] **Step 3: Wire orchestration without changing result order**

Stage1 adapter loads the same system parameter and passes it explicitly. Result insertion and ISIN attachment order remain unchanged.

- [ ] **Step 4: Focused verification**

```bash
/opt/homebrew/bin/python3 -m pytest -q tests/risk_core/test_stage1_limits_characterization.py tests/test_stage_high_yield_and_specific_controller.py tests/test_daily_archive_thresholds.py
```

Tests fail if special concentration activates, Xixian/controller order changes, controller switches to minimum, attention behavior is unified, or zero remaining becomes exceeded.

- [ ] **Step 5: Full zero-difference gate**

Repeat Task 6 command with output `kernel-task8`.

- [ ] **Step 6: Commit**

```bash
git diff --check
git add src/risk_core/stage1_limits.py src/risk_core/kernel.py src/stage1/stage1_limit_detail.py src/stage1/stage1_processor.py tests/risk_core/test_stage1_limits_characterization.py
git commit -m "refactor: extract production stage1 limit engine"
```

## Task 9: Extract Stage2 concentration, high-risk and high-yield calculations

**Files:**

- Create: `src/risk_core/stage2_limits.py`
- Modify: `src/stage2/stage2_processor.py`
- Modify: `src/risk_core/kernel.py`
- Test: `tests/risk_core/test_stage2_limits_characterization.py`

- [ ] **Step 1: Keep I/O in Stage2 adapter**

Processor retains Stage1/accounting/config/ISIN/tool-pool reads, damaged-Excel parsing, business-date inference, output writes and logging.

- [ ] **Step 2: Move calculations**

Core receives explicit frames and owns credit/region/city-investment/high-risk totals; Stage2 credit detail; industry/province/region details; high-yield detail and annual capital; text, ISIN keep-last and category limit pure helpers.

- [ ] **Step 3: Make high-yield configuration explicit**

Adapter loads `高收益限额` once and supplies it internally. Remove both calculation-time config reads without changing defaults, categories, annual selection, grouping or outputs. Do not expose a new Stage2 output table.

- [ ] **Step 4: Preserve exact Stage2 order and verify**

```bash
/opt/homebrew/bin/python3 -m pytest -q tests/risk_core/test_stage2_limits_characterization.py tests/test_stage2_high_yield_isin_keep_last.py tests/test_display_builders_page7_high_yield.py
```

Repeat full candidate with output `kernel-task9`.

- [ ] **Step 5: Commit**

```bash
git diff --check
git add src/risk_core/stage2_limits.py src/risk_core/kernel.py src/stage2/stage2_processor.py tests/risk_core/test_stage2_limits_characterization.py
git commit -m "refactor: extract production stage2 risk engine"
```

## Task 10: Complete orchestration, prove deterministic parity and seal evidence

**Files:**

- Modify: `src/risk_core/kernel.py`
- Modify: `src/stage1/stage1_processor.py`
- Modify: `src/stage2/stage2_processor.py`
- Modify: `tests/risk_core/test_kernel_orchestration.py`
- Create: `docs/evidence/production-shared-kernel-20260710.json`
- Modify: `docs/PRETRADE_DOCUMENT_STATUS.md`

- [ ] **Step 1: Finish thin adapters and orchestration tests**

No business formula remains in file read/write methods. In-memory kernel returns detached deterministic Stage1/Stage2 mappings in exact production key order. Existing archive/test import paths remain compatible. Compare every pure function with its wrapper and verify input non-mutation/repeatability.

```bash
/opt/homebrew/bin/python3 -m pytest -q tests/risk_core
/opt/homebrew/bin/python3 -m pytest -q
```

- [ ] **Step 2: Run two independent final candidates**

```bash
ENV=test LIMIT_MONITOR_PROFILE=local /opt/homebrew/bin/python3 scripts/run_kernel_candidate.py --input-root /Users/dellawang/Desktop/LimitMonitorAutomation/data_source_0123 --allow-output-root /Users/dellawang/Desktop/LimitMonitorAutomation-test-output --output /Users/dellawang/Desktop/LimitMonitorAutomation-test-output/kernel-final-1 --reference /Users/dellawang/Desktop/LimitMonitorAutomation-test-output/pretrade-baseline-20260710-main1
ENV=test LIMIT_MONITOR_PROFILE=local /opt/homebrew/bin/python3 scripts/run_kernel_candidate.py --input-root /Users/dellawang/Desktop/LimitMonitorAutomation/data_source_0123 --allow-output-root /Users/dellawang/Desktop/LimitMonitorAutomation-test-output --output /Users/dellawang/Desktop/LimitMonitorAutomation-test-output/kernel-final-2 --reference /Users/dellawang/Desktop/LimitMonitorAutomation-test-output/pretrade-baseline-20260710-main1
```

Both independently require counts `10/35/22`, exact fingerprint, zero file/table/schema/row/order/field differences, unchanged protected paths, no DB/Wind/archive/current access, and identical logical fingerprints.

- [ ] **Step 3: Seal evidence**

`docs/evidence/production-shared-kernel-20260710.json` records schema/status, authority sections, baseline/candidate SHAs, manifest/date/hash, static mapping count/SHA/22 zero count, runtime, source allowlist diff, both fingerprints/counts, all-zero diff summary, I/O firewall, full tests, protected inventory, and explicit DB/Wind/service/UI exclusion. Do not commit XLSX or full business-valued diff reports.

- [ ] **Step 4: Update status**

Mark this plan complete only after both runs pass. Link evidence and exact fingerprint. Declare immutable database snapshot/full archival as the next and only executable phase. Do not mark read-only DB context, Wind, services or UI as final-complete.

- [ ] **Step 5: Final verification, review and commit**

Use `superpowers:verification-before-completion`, then `superpowers:requesting-code-review`.

```bash
/opt/homebrew/bin/python3 -m pytest -q
git diff --check
git status --short
git add src/risk_core src/stage1 src/stage2 src/testing scripts/run_kernel_candidate.py config/test_manifests/pretrade-output-contract-v1.json tests/risk_core tests/testing tests/scripts/test_run_kernel_candidate.py docs/evidence/production-shared-kernel-20260710.json docs/PRETRADE_DOCUMENT_STATUS.md
git commit -m "refactor: establish shared production risk kernel"
```

Review rejects every business difference even if the new value appears more reasonable.

## Completion gate and next phase

This plan is complete only when:

1. current daily Stage1/Stage2 use `src/risk_core`;
2. core passes the I/O firewall;
3. all characterization and repository tests pass;
4. two frozen runs equal gold at file/table/row/field level;
5. no production table gains, loses or changes a value, row, column or order;
6. evidence is committed and independently reviewed.

Only then write and execute the immutable database snapshot/full archival plan. It may reuse the completed read-only DB context's proven schema checks and transaction patterns, but must store enough immutable inputs/context to reconstruct this exact kernel call; it must not revive parallel rules or date-spliced snapshots.
