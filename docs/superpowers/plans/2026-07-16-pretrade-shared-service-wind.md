# Pretrade Shared-Service and WindPy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the two pretrade back-end services—single-bond purchasable PR capacity and basket post-trade limit checking—by adding an in-memory trade overlay to the already extracted production Stage0/1/2 kernel, with on-the-fly WindPy only for confirmed non-held bonds.

**Architecture:** `PretradeContextStore` remains the single database read boundary: every request starts from its current 27-input snapshot and never reads Excel, `data/current`, archive result tables, or local business configuration. A resolver obtains a complete master record from the held-position snapshot or, only for a confirmed non-held bond, a request-local WindPy provider; an overlay appends the normalized trade rows to the same raw production inputs before running `ProductionRiskKernel`. A thin result adapter projects the resulting production rows and adds data-quality/status metadata without recreating any limit formula, pool rule, aggregation, threshold, or tolerance.

**Tech Stack:** Python 3.12, pandas, SQLAlchemy, pytest, existing `src.risk_core.ProductionRiskKernel`, database-backed `PretradeContextStore`, optional local Wind `WindPy` API.

## Global Constraints

- Business authority is `docs/PRETRADE_SHARED_CORE_SPEC.md`, baseline is `main@579af695fb8727dec8249f66d07a8b0e723da137`; a Stage0/1/2 business-output difference is a failure.
- Reuse production account mapping exactly: `做市交易部做市业务 → 做市业务`; every other account maps to `自营业务`.
- Do not add a second formula engine, account whitelist, new pool rule, missing-value-to-zero fallback, numerical tolerance, database table, cache, Wind persistence, TEST account, DEV/PROD pointer, or display-snapshot dependency.
- Preserve current high-yield annual-cost behavior exactly: the accounting route and penetration route are appended; a code occurring in both is retained twice. The current 2026-07-10 lack of overlap is not a rule.
- A held position with incomplete master data is `MISSING_SNAPSHOT` and must not call Wind. Wind is invoked only after a complete held-position lookup proves no matching position exists.
- Wind data is request-local only. It is neither written to a database nor cached in process, on disk, `data/current`, or a result table.
- User-entered basket PR is finite and strictly positive. The single-bond API internally performs a zero-PR probe only; that probe is not an input transaction and is never persisted.
- A remaining amount `< 0` is breached; `= 0` is not breached. Formatting must not affect the decision.
- Scope ends at domain service, database-read boundary, and verification. Do not modify the existing display pages or display-snapshot builder in this plan; their UI wiring is a later, separate task.

---

## File map

- Modify `src/pretrade/context_store.py` and `tests/pretrade/test_context_store.py` — remove the obsolete cross-read of `archive_meta`; retain complete-snapshot validation and the existing one-pointer schema.
- Create `src/risk_core/high_yield_capital_sources.py`; modify `src/risk_core/stage2_limits.py`, `src/stage2/stage2_processor.py`, and `tests/risk_core/test_stage2_limits_characterization.py` — expose the two existing high-yield-cost source constructors without changing their output.
- Create `src/pretrade/service_models.py`, `src/pretrade/windpy_master.py`, `src/pretrade/master_resolution.py`, `src/pretrade/trade_overlay.py`, `src/pretrade/result_adapter.py`, and `src/pretrade/pretrade_service.py` — immutable request/result records, Wind boundary, resolver, in-memory raw-input overlay, direct output projection, and single/basket orchestration.
- Create `tests/pretrade/test_windpy_master.py`, `tests/pretrade/test_master_resolution.py`, `tests/pretrade/test_trade_overlay.py`, `tests/pretrade/test_result_adapter.py`, and `tests/pretrade/test_pretrade_service.py` — fixed in-memory response tests and end-to-end invariants.
- Create `scripts/probe_windpy_bond_master.py` and `tests/scripts/test_probe_windpy_bond_master.py` — an explicit, read-only, no-persistence production-environment field-capability gate.
- Modify `docs/PRETRADE_SHARED_CORE_SPEC.md`, `docs/PRETRADE_DOCUMENT_STATUS.md`, and `docs/superpowers/specs/2026-07-16-pretrade-shared-service-wind-design.md` only to record implemented, verified behavior and the final read-only Wind field map. No business decision is made in code.

### Task 1: Simplify the current-snapshot read boundary

**Files:**
- Modify: `src/pretrade/context_store.py:10-25, 93-113, 236-303`
- Modify: `tests/pretrade/test_context_store.py:1-255`

**Consumes:** `PretradeSnapshotRequest`, `ProductionKernelInput`, the existing four `pretrade_` tables.

**Produces:** `PretradeContextStore.get_current_snapshot() -> PretradeContextSnapshot | None` and `publish_current(snapshot_id) -> None` that validate only the selected pretrade snapshot.

- [ ] **Step 1: Write the failing no-archive test.**

  Replace the current `archive_meta` helper and mismatch test with this test; it intentionally creates no `archive_meta` table:

  ```python
  def test_current_snapshot_is_read_and_published_without_archive_meta(
      engine, context_request
  ) -> None:
      store = PretradeContextStore(engine)
      store.prepare_schema()
      snapshot_id = store.write_snapshot(context_request)

      store.publish_current(snapshot_id)

      current = store.get_current_snapshot()
      assert current is not None
      assert current.snapshot_id == snapshot_id
      _assert_kernel_input_equal(store.load_current_kernel_input(), context_request.kernel_input)
      assert "archive_meta" not in inspect(engine).get_table_names()
  ```

- [ ] **Step 2: Run the focused test and confirm it fails because the store reads `archive_meta`.**

  Run: `pytest tests/pretrade/test_context_store.py::test_current_snapshot_is_read_and_published_without_archive_meta -q`

  Expected: FAIL with `PretradePublishError` mentioning `archive_meta`.

- [ ] **Step 3: Remove only the cross-table date guard.**

  In `src/pretrade/context_store.py` remove `text` from the SQLAlchemy imports, delete `PretradeDataSyncError`, `_current_archive_data_date`, and `select_text_current_archive_date`. Replace the two methods with the following bodies (all existing hash/schema/config-workbook validation remains):

  ```python
  def get_current_snapshot(self) -> PretradeContextSnapshot | None:
      """取得唯一 current，并只校验该交易前快照自身。"""
      try:
          with self._engine.connect() as conn:
              pointer = conn.execute(
                  select(PRETRADE_SNAPSHOT_CURRENT).where(
                      PRETRADE_SNAPSHOT_CURRENT.c.pointer_id == 1
                  )
              ).mappings().one_or_none()
              if pointer is None:
                  return None
              return self._get_snapshot_row(conn, UUID(pointer["snapshot_id"]))
      except PretradeContextStoreError:
          raise
      except SQLAlchemyError as exc:
          raise PretradeContextStoreError("读取交易前当前指针失败") from exc

  def publish_current(self, snapshot_id: UUID | str) -> None:
      """读回验证完整快照后，切换唯一 current。"""
      normalized_snapshot_id = _as_uuid(snapshot_id)
      try:
          with self._engine.begin() as conn:
              self._get_snapshot_row(conn, normalized_snapshot_id)
              self._load_kernel_input(conn, normalized_snapshot_id)
              try:
                  self._load_config_workbook(conn, normalized_snapshot_id)
              except PretradeContextIntegrityError as exc:
                  raise PretradePublishError("交易前快照原始配置工作簿无效") from exc
              values = {"snapshot_id": str(normalized_snapshot_id)}
              updated = conn.execute(
                  update(PRETRADE_SNAPSHOT_CURRENT)
                  .where(PRETRADE_SNAPSHOT_CURRENT.c.pointer_id == 1)
                  .values(**values)
              )
              if updated.rowcount == 0:
                  conn.execute(
                      insert(PRETRADE_SNAPSHOT_CURRENT).values(pointer_id=1, **values)
                  )
      except PretradeContextStoreError:
          raise
      except (SQLAlchemyError, FrameCodecError, ValueError, TypeError) as exc:
          raise PretradePublishError("交易前当前指针发布失败") from exc
  ```

- [ ] **Step 4: Remove obsolete archive setup from all context-store tests.**

  Delete `PretradeDataSyncError` from imports, delete `_create_current_archive`, and delete every call to that helper. Keep the existing rollback tests: they now prove a failed write cannot displace an already published complete snapshot without manufacturing an old-archive table.

- [ ] **Step 5: Run the context-store suite.**

  Run: `pytest tests/pretrade/test_context_store.py -q`

  Expected: PASS; no test creates or queries `archive_meta`.

- [ ] **Step 6: Commit the independently reviewable simplification.**

  ```bash
  git add src/pretrade/context_store.py tests/pretrade/test_context_store.py \
    docs/PRETRADE_SHARED_CORE_SPEC.md docs/PRETRADE_DOCUMENT_STATUS.md
  git commit -m "refactor: remove pretrade archive date guard"
  ```

### Task 2: Extract the two existing high-yield annual-cost source constructors

**Files:**
- Create: `src/risk_core/high_yield_capital_sources.py`
- Modify: `src/risk_core/stage2_limits.py:1067-1163`
- Modify: `src/stage2/stage2_processor.py:628-675`
- Modify: `tests/risk_core/test_stage2_limits_characterization.py`

**Consumes:** Existing raw `债券持仓表_核算系统`, `穿透高收益_投资本金规模`, `穿透高收益债券`, and `金融工具池设置` frames.

**Produces:** Pure, production-identical source functions:

```python
HIGH_YIELD_CAPITAL_COLUMNS: tuple[str, ...]
select_accounting_high_yield_capital_rows(
    accounting_positions: pd.DataFrame, financial_tool_pool: pd.DataFrame | None
) -> pd.DataFrame
select_penetration_high_yield_capital_rows(
    penetrate_positions: pd.DataFrame, penetrate_high_yield: pd.DataFrame | None
) -> pd.DataFrame
append_high_yield_capital_sources(
    accounting_rows: pd.DataFrame, penetration_rows: pd.DataFrame
) -> pd.DataFrame
```

- [ ] **Step 1: Add a failing characterization of intentional cross-source duplication.**

  Add this test next to the current high-yield capital characterization tests:

  ```python
  def test_high_yield_capital_appends_identical_codes_from_two_sources() -> None:
      accounting = pd.DataFrame(
          [{"日期": pd.Timestamp("2026-07-10"), "账户": "高收益账户", "简称": "样例债", "代码": "100001", "持仓面额(元)": 100_000.0, "全价成本(元)": 100_000.0}]
      )
      penetration = accounting.assign(账户="自营部交易性")

      actual = append_high_yield_capital_sources(accounting, penetration)

      assert len(actual) == 2
      assert actual["代码"].tolist() == ["100001", "100001"]
      assert actual["全价成本(元)"].sum() == 200_000.0
  ```

- [ ] **Step 2: Run the new characterization and confirm the helper does not exist.**

  Run: `pytest tests/risk_core/test_stage2_limits_characterization.py::test_high_yield_capital_appends_identical_codes_from_two_sources -q`

  Expected: FAIL with an import error for `append_high_yield_capital_sources`.

- [ ] **Step 3: Implement the pure helpers by moving, not modifying, the existing production transformations.**

  `select_accounting_high_yield_capital_rows` must preserve the current aliases (`内部证券账户名称 → 账户`, `资产名称 → 简称`, `资产代码 → 代码`), date coercion, code suffix removal, `账户` containing `高收益` OR `row_in_financial_tool_pool(...)` predicate, selected six columns, and `drop_duplicates()` within accounting only. `select_penetration_high_yield_capital_rows` must preserve the current ISIN-column fallback, `drop_duplicates(keep="last")` on the configuration ISIN list, inner join, conversions `库存数量(万)_PR * 10000` and `本币成本 → 全价成本(元)`, and selected columns.

  The append function is deliberately only:

  ```python
  def append_high_yield_capital_sources(
      accounting_rows: pd.DataFrame, penetration_rows: pd.DataFrame
  ) -> pd.DataFrame:
      if penetration_rows.empty:
          return accounting_rows.copy()
      return pd.concat([accounting_rows, penetration_rows], ignore_index=True)
  ```

  Do not add a code-level, ISIN-level, account-level, or full-row de-duplication after this concat.

- [ ] **Step 4: Replace both legacy callers with the shared helpers.**

  In `Stage2RiskEngine.query_high_yield_capital`, obtain `part_accounting` from `select_accounting_high_yield_capital_rows`, copy the existing cached penetration input, and call `append_high_yield_capital_sources` before the existing annual-limit grouping code. In `Stage2Processor.query_penetrate_high_yield_capital`, retain only file loading and missing-file logging, then pass its loaded source and cache configuration to `select_penetration_high_yield_capital_rows`.

  The methods retain their existing empty-data log behavior and output columns. Do not change `query_high_yield_detail`, calculation units, or final `高收益年度总投资本金(万)` calculation.

- [ ] **Step 5: Run characterization and full risk-core regression.**

  Run:

  ```bash
  pytest tests/risk_core/test_stage2_limits_characterization.py -q
  pytest tests/risk_core -q
  ```

  Expected: PASS; the new test has two rows for the same code, and all pre-existing Stage2 characterizations remain unchanged.

- [ ] **Step 6: Run the frozen kernel diff before committing.**

  Run:

  ```bash
  ENV=test LIMIT_MONITOR_PROFILE=local /opt/homebrew/bin/python3 \
    scripts/run_kernel_candidate.py \
    --input-root /Users/dellawang/Desktop/LimitMonitorAutomation/data_source_0123 \
    --allow-output-root /Users/dellawang/Desktop/LimitMonitorAutomation-test-output \
    --output /Users/dellawang/Desktop/LimitMonitorAutomation-test-output/pretrade-high-yield-source-parity \
    --reference /Users/dellawang/Desktop/LimitMonitorAutomation-test-output/pretrade-baseline-20260710-main1
  ```

  Expected: exit `0`; every Stage0/1/2 business table matches the frozen baseline.

- [ ] **Step 7: Commit the extraction and characterization.**

  ```bash
  git add src/risk_core/high_yield_capital_sources.py src/risk_core/stage2_limits.py \
    src/stage2/stage2_processor.py tests/risk_core/test_stage2_limits_characterization.py
  git commit -m "refactor: share high yield capital source builders"
  ```

### Task 3: Define immutable pretrade records and a non-persistent Wind boundary

**Files:**
- Create: `src/pretrade/service_models.py`
- Create: `src/pretrade/windpy_master.py`
- Create: `tests/pretrade/test_windpy_master.py`

**Consumes:** Normalized trade code strings and a `BondMasterProvider` supplied to the service.

**Produces:** The following sole adapter contract; no adapter exposes pandas frames or a database write method:

```python
class MasterSource(StrEnum):
    SNAPSHOT = "SNAPSHOT"
    WIND = "WIND"
    MISSING_SNAPSHOT = "MISSING_SNAPSHOT"
    MISSING_MASTER = "MISSING_MASTER"

@dataclass(frozen=True)
class PretradeLine:
    line_id: int
    bond_code: str
    account: str
    pr_wan: float
    full_price_cost_wan: float | None = None

@dataclass(frozen=True)
class BondMaster:
    input_code: str
    main_security_code: str
    isin_code: str | None
    bond_name: str
    issuer_name: str
    issuer_wind_code: str | None
    controller_name: str | None
    guarantor_name: str | None
    guarantor_wind_code: str | None
    outstanding_balance_yi: float | None
    bond_classification: str | None
    bond_type: str | None
    issuer_type: str | None
    is_city_investment_bond: str | None
    bond_category: str | None
    wind_industry: str | None
    province: str | None

@dataclass(frozen=True)
class MasterResolution:
    source: MasterSource
    master: BondMaster | None
    reason: str | None
    wind_fetched_at: datetime | None = None
    wind_data_date: str | None = None

class BondMasterProvider(Protocol):
    def resolve(self, bond_code: str) -> MasterResolution:
        raise NotImplementedError
```

- [ ] **Step 1: Write the failing Wind adapter tests with an in-memory gateway.**

  Use a fake gateway that records calls and returns a structured single-record fixture. Cover all four observable outcomes:

  ```python
  def test_provider_normalizes_one_complete_wind_record() -> None:
      provider = WindPyBondMasterProvider(gateway=FakeGateway.single(COMPLETE_WIND_ROW))
      result = provider.resolve("102480811.IB")
      assert result.source is MasterSource.WIND
      assert result.master is not None
      assert result.master.main_security_code == "102480811"
      assert result.wind_fetched_at is not None

  @pytest.mark.parametrize("gateway", [FakeGateway.start_failure(), FakeGateway.error(), FakeGateway.multiple_rows()])
  def test_provider_returns_missing_master_without_fallback(gateway) -> None:
      result = WindPyBondMasterProvider(gateway=gateway).resolve("102480811.IB")
      assert result.source is MasterSource.MISSING_MASTER
      assert result.master is None
      assert result.reason
  ```

  Add a fifth test whose fixture has one required source field missing; it must return `MISSING_MASTER`, not a `BondMaster` whose field is silently zero-filled.

- [ ] **Step 2: Run the module test and confirm it fails because the module does not exist.**

  Run: `pytest tests/pretrade/test_windpy_master.py -q`

  Expected: FAIL during collection with `ModuleNotFoundError: src.pretrade.windpy_master`.

- [ ] **Step 3: Implement request-only models and `WindPyBondMasterProvider`.**

  The provider constructor accepts a `WindGateway` only for tests; production construction lazily imports `from WindPy import w` inside the provider. The provider performs `w.start()` then one `w.wss(bond_code, fields, usedf=True)` request, validates exactly one record and every required mapped field, builds `BondMaster`, and returns `MISSING_MASTER` for import failure, startup failure, vendor error code, empty/multiple record, field absence, or normalization failure.

  It must have no module-global response dict, no `lru_cache`, no path argument, no pandas file I/O, no SQLAlchemy import, and no write. `wind_fetched_at` uses `datetime.now(UTC)` and `wind_data_date` is only populated if the response supplies an explicit vendor date.

  Define `WindFieldMap` as an immutable constructor argument, not a permissive dictionary lookup. The concrete field-name map is introduced only after Task 7 has produced a successful field-capability result; before then a production service must return `MISSING_MASTER` with `Wind 字段映射尚未通过连通性验收` rather than issuing guessed field requests.

- [ ] **Step 4: Run the module suite.**

  Run: `pytest tests/pretrade/test_windpy_master.py -q`

  Expected: PASS with no import of local `WindPy` during tests.

- [ ] **Step 5: Commit the isolated contract.**

  ```bash
  git add src/pretrade/service_models.py src/pretrade/windpy_master.py \
    tests/pretrade/test_windpy_master.py
  git commit -m "feat: add request local Wind bond master boundary"
  ```

### Task 4: Resolve held records and build production-shaped raw-input overlays

**Files:**
- Create: `src/pretrade/master_resolution.py`
- Create: `src/pretrade/trade_overlay.py`
- Create: `tests/pretrade/test_master_resolution.py`
- Create: `tests/pretrade/test_trade_overlay.py`

**Consumes:** `ProductionKernelInput`, `PretradeLine`, `BondMasterProvider`, `BondMaster`, and Task 2 high-yield source helpers.

**Produces:**

```python
class SnapshotBondMasterResolver:
    def resolve(self, inputs: ProductionKernelInput, bond_code: str) -> MasterResolution:
        raise NotImplementedError

class TradeOverlayBuilder:
    def build(
        self, inputs: ProductionKernelInput, lines: Sequence[PretradeLine],
        resolutions: Mapping[int, MasterResolution]
    ) -> ProductionKernelInput:
        raise NotImplementedError
```

- [ ] **Step 1: Add failing held/non-held resolver tests.**

  Construct snapshot raw frames containing one complete held code and one held code whose issuer is null. Use a provider that increments `calls`:

  ```python
  def test_complete_held_bond_uses_snapshot_without_wind(kernel_input) -> None:
      wind = CountingProvider(complete_master("900001.IB"))
      result = SnapshotBondMasterResolver(wind).resolve(kernel_input, "102480811.IB")
      assert result.source is MasterSource.SNAPSHOT
      assert wind.calls == []

  def test_incomplete_held_bond_never_falls_back_to_wind(kernel_input) -> None:
      wind = CountingProvider(complete_master("900001.IB"))
      result = SnapshotBondMasterResolver(wind).resolve(kernel_input, "900002.IB")
      assert result.source is MasterSource.MISSING_SNAPSHOT
      assert result.master is None
      assert wind.calls == []

  def test_confirmed_nonheld_bond_calls_wind_once(kernel_input) -> None:
      wind = CountingProvider(complete_master("900003.IB"))
      result = SnapshotBondMasterResolver(wind).resolve(kernel_input, "900003.IB")
      assert result.source is MasterSource.WIND
      assert wind.calls == ["900003.IB"]
  ```

- [ ] **Step 2: Run the resolver tests and confirm they fail because the resolver is absent.**

  Run: `pytest tests/pretrade/test_master_resolution.py -q`

  Expected: FAIL during collection with `ModuleNotFoundError`.

- [ ] **Step 3: Implement complete-position identification with production code normalization.**

  The resolver uses `normalize_security_code_series` from the production position-context module on the complete raw holding facts, not any display table. It distinguishes exactly these cases:

  1. the held-position dataset/key is not usable → `MISSING_SNAPSHOT`, without Wind;
  2. a normalized match exists but any field needed by `BondMaster` is absent or contradictory → `MISSING_SNAPSHOT`, without Wind;
  3. no normalized match exists in a complete raw position dataset → delegate once to `BondMasterProvider.resolve`.

  It must not infer master facts from a Stage1/Stage2 output or make the current account/bond pool membership part of held-vs-non-held identification.

- [ ] **Step 4: Add failing overlay tests that prove raw-only mutation and baseline account mapping.**

  ```python
  def test_overlay_appends_only_raw_position_frames_and_keeps_else_account_mapping(
      kernel_input, complete_resolution
  ) -> None:
      line = PretradeLine(1, "900003.IB", "任意未列账户", 123.45)
      overlay = TradeOverlayBuilder().build(kernel_input, [line], {1: complete_resolution})

      assert len(overlay.frames["债券持仓明细表"]) == len(kernel_input.frames["债券持仓明细表"]) + 1
      assert len(overlay.frames["债券持仓明细表_信用债"]) == len(kernel_input.frames["债券持仓明细表_信用债"]) + 1
      assert len(overlay.frames["债券持仓明细表_全量债券监管集中度"]) == len(kernel_input.frames["债券持仓明细表_全量债券监管集中度"]) + 1
      assert "自营业务" in overlay.frames["债券持仓明细表_信用债"]["业务分类"].tolist()
  ```

  Add a second test for a line that carries full-price cost and satisfies both current high-yield source predicates. It must assert that the temporary source inputs produce two annual-cost rows after Task 2’s `append_high_yield_capital_sources` call.

- [ ] **Step 5: Run the overlay tests and confirm they fail before implementation.**

  Run: `pytest tests/pretrade/test_trade_overlay.py -q`

  Expected: FAIL during collection with `ModuleNotFoundError`.

- [ ] **Step 6: Implement `TradeOverlayBuilder.build` as copy-and-append only.**

  Start from `inputs.detached_frames()`, retain the original `business_date` and `parameters`, and append only one production-shaped row per resolved line to each of these raw datasets:

  ```text
  债券持仓明细表
  债券持仓明细表_信用债
  债券持仓明细表_全量债券监管集中度
  ```

  Populate the same code, issuer, controller, guarantor, classification, balance, industry, province, and city-investment fields that those production raw frames consume. Set the trade PR field to `line.pr_wan`; retain missing external facts as missing rather than invented defaults. Map the account exactly with:

  ```python
  business_category = "做市业务" if line.account == "做市交易部做市业务" else "自营业务"
  ```

  For a supplied full-price cost, append an accounting-shaped temporary row, then use the Task 2 source helpers to decide independently whether the penetration-shaped row is also present. Do not decide high-yield eligibility from a Wind label and do not remove a duplicate output row from the two source paths. The builder returns a new `ProductionKernelInput`; it never modifies the current snapshot’s frames.

- [ ] **Step 7: Run resolver and overlay suites.**

  Run:

  ```bash
  pytest tests/pretrade/test_master_resolution.py tests/pretrade/test_trade_overlay.py -q
  pytest tests/risk_core/test_stage2_limits_characterization.py -q
  ```

  Expected: PASS; the existing source-characterization remains the only definition of high-yield annual-cost routing.

- [ ] **Step 8: Commit the resolver and overlay.**

  ```bash
  git add src/pretrade/master_resolution.py src/pretrade/trade_overlay.py \
    tests/pretrade/test_master_resolution.py tests/pretrade/test_trade_overlay.py
  git commit -m "feat: overlay pretrade lines on production inputs"
  ```

### Task 5: Project kernel results and implement the single/basket service

**Files:**
- Create: `src/pretrade/result_adapter.py`
- Create: `src/pretrade/pretrade_service.py`
- Create: `tests/pretrade/test_result_adapter.py`
- Create: `tests/pretrade/test_pretrade_service.py`

**Consumes:** `PretradeContextStore.load_current_kernel_input`, `SnapshotBondMasterResolver`, `TradeOverlayBuilder`, `ProductionRiskKernel`, and production Stage1/Stage2 result tables.

**Produces:**

```python
class PretradeRiskService:
    def quote_single_bond(self, bond_code: str, account: str) -> SingleBondQuote:
        raise NotImplementedError

    def check_basket(self, lines: Sequence[PretradeLine]) -> BasketCheck:
        raise NotImplementedError
```

`SingleBondQuote` exposes raw PR remaining, non-negative purchasable PR cap only when all required PR dimensions are calculable, independent high-yield full-price remaining, binding dimension, per-dimension production projections, and data-quality statuses. `BasketCheck` exposes `已超限` / `不可计算` / `未超限`, total PR, confirmed breach count, uncomputable count, reasons, and all applicable projected dimensions.

- [ ] **Step 1: Add failing direct-projection tests.**

  Build a controlled Stage1/Stage2 output fixture containing a zero remaining row, a negative remaining row, a not-applicable row, and an uncomputable row. Assert:

  ```python
  def test_adapter_uses_raw_remaining_and_does_not_apply_tolerance() -> None:
      result = PretradeResultAdapter().basket_from_kernel(FIXTURE_KERNEL_RUN)
      assert result.status == "已超限"
      assert result.confirmed_breach_count == 1
      assert next(item for item in result.dimensions if item.name == "零额维度").breached is False

  def test_adapter_keeps_full_price_out_of_pr_minimum() -> None:
      quote = PretradeResultAdapter().single_from_probe(FIXTURE_KERNEL_RUN)
      assert quote.raw_pr_remaining_wan == 0.0
      assert quote.purchasable_pr_cap_wan == 0.0
      assert quote.full_price_cost_remaining_wan == 50.0
  ```

  The fixture must make no assertion about an independently recomputed threshold; it must only provide the production output fields already calculated by the kernel.

- [ ] **Step 2: Run the adapter suite and confirm it fails before the module exists.**

  Run: `pytest tests/pretrade/test_result_adapter.py -q`

  Expected: FAIL during collection with `ModuleNotFoundError`.

- [ ] **Step 3: Implement a table/column projection registry, not formulas.**

  In `result_adapter.py`, define immutable `DimensionProjection` entries that name only production result tables and their existing columns for the following scopes:

  ```text
  限额明细_债券持仓明细表_信用债1_2
  限额明细_债券持仓明细表_信用债1_1
  限额明细_全量债券监管集中度
  限额明细_债券持仓明细表_信用债2
  限额明细_高收益
  限额明细_高收益_投资本金规模
  ```

  The registry projects `dimension name`, `scope`, `current used`, `trade amount`, `limit`, `unit`, `raw remaining`, production applicability, reason, and input line IDs. It cannot calculate `limit - used`, alter a group key, or call a `risk_core` limit function. It obtains the current/trade delta from the separately executed baseline and overlay kernel results using the same stable row key and returns the overlay’s actual production value as the decision value.

  Classify data quality independently: an absent/invalid master yields its resolution status; a missing required input/output yields `MISSING_INPUT`; a production result marked not applicable yields `NOT_APPLICABLE`; no branch converts a real null into numeric zero.

- [ ] **Step 4: Add failing service invariants.**

  Use a `PretradeContextStore` backed by in-memory SQLite and fixed `BondMasterProvider` fixtures. Add these named tests:

  ```python
  def test_same_issuer_basket_is_combined_by_kernel_not_page_sum(service) -> None:
      result = service.check_basket([
          PretradeLine(1, "900001.IB", "自营部交易性", 60.0),
          PretradeLine(2, "900002.IB", "自营部交易性", 60.0),
      ])
      assert result.status == "已超限"
      assert any(item.scope == "同一债务主体" and item.trade_amount_wan == 120.0 for item in result.dimensions)

  def test_split_merge_and_line_order_do_not_change_basket_result(service) -> None:
      merged = service.check_basket([PretradeLine(1, "900001.IB", "自营部交易性", 100.0)])
      split = service.check_basket([
          PretradeLine(2, "900001.IB", "自营部交易性", 40.0),
          PretradeLine(1, "900001.IB", "自营部交易性", 60.0),
      ])
      assert (split.status, split.dimensions) == (merged.status, merged.dimensions)

  @pytest.mark.parametrize("amount", [0.0, -1.0, float("nan"), float("inf")])
  def test_user_non_positive_or_non_finite_pr_is_invalid(service, amount) -> None:
      with pytest.raises(ValueError, match="有限正数"):
          service.check_basket([PretradeLine(1, "900001.IB", "自营部交易性", amount)])

  def test_single_quote_matches_direct_zero_probe(service, direct_zero_probe_quote) -> None:
      quote = service.quote_single_bond("900001.IB", "自营部交易性")
      assert quote.dimensions == direct_zero_probe_quote.dimensions
      assert quote.raw_pr_remaining_wan == direct_zero_probe_quote.raw_pr_remaining_wan

  def test_confirmed_breach_wins_over_missing_master(service_with_breach_and_missing_master) -> None:
      result = service_with_breach_and_missing_master.check_basket([
          PretradeLine(1, "900001.IB", "自营部交易性", 100.0),
          PretradeLine(2, "900099.IB", "自营部交易性", 10.0),
      ])
      assert result.status == "已超限"
      assert any(item.data_quality_status == "MISSING_MASTER" for item in result.dimensions)

  def test_nonheld_missing_master_is_not_silently_excluded(service_with_missing_master) -> None:
      result = service_with_missing_master.check_basket([
          PretradeLine(1, "900099.IB", "自营部交易性", 10.0),
      ])
      assert result.status == "不可计算"
      assert result.line_reasons == {1: "MISSING_MASTER"}

  def test_high_yield_without_full_price_keeps_pr_and_blocks_annual_cost(high_yield_service) -> None:
      result = high_yield_service.check_basket([
          PretradeLine(1, "900088.IB", "自营部交易性", 10.0, None),
      ])
      assert any(item.measure == "PR_WAN" for item in result.dimensions)
      assert any(
          item.measure == "FULL_PRICE_COST_WAN" and item.calculation_status == "UNCOMPUTABLE"
          for item in result.dimensions
      )
  ```

  `direct_zero_probe_quote` is a test fixture that invokes the same resolver, `TradeOverlayBuilder`, `ProductionRiskKernel.run_stage1`, `ProductionRiskKernel.run_stage2`, and `PretradeResultAdapter.single_from_probe` with `PretradeLine(1, "900001.IB", "自营部交易性", 0.0)`. It is not a public service API and proves that the single-bond endpoint does not have a separate formula path.

  The split/merge test uses two positive lines for the same code/account whose sum equals the one-line PR amount. The missing-master test must retain a line-specific `MISSING_MASTER` reason and cannot return `未超限` merely because the row was skipped.

- [ ] **Step 5: Run the service suite and confirm it fails before orchestration exists.**

  Run: `pytest tests/pretrade/test_pretrade_service.py -q`

  Expected: FAIL with missing `PretradeRiskService`.

- [ ] **Step 6: Implement the two orchestration methods.**

  `check_basket` validates every `PretradeLine` before resolving any master; validates finite `pr_wan > 0`; resolves each distinct normalized code once within the method call only; builds one overlay; runs both production kernel stages; and delegates all business result interpretation to `PretradeResultAdapter`.

  `quote_single_bond` creates a private `PretradeLine(line_id=1, pr_wan=0.0)` only after external input validation, resolves it through the same resolver/overlay/kernel path, and delegates to `single_from_probe`. It must never expose or persist a user-selectable zero transaction.

  The only overall status selection is:

  ```python
  if any(item.breached for item in dimensions if item.calculation_status == "CALCULATED"):
      status = "已超限"
  elif any(item.calculation_status == "UNCOMPUTABLE" and item.required for item in dimensions):
      status = "不可计算"
  else:
      status = "未超限"
  ```

  No call path imports `src.visualization`, reads a file, writes through `PretradeContextStore`, uses old pretrade calculations, or caches a response after method return.

- [ ] **Step 7: Run all service tests and static read-boundary checks.**

  Run:

  ```bash
  pytest tests/pretrade/test_result_adapter.py tests/pretrade/test_pretrade_service.py -q
  rg -n "read_excel|read_csv|read_parquet|open\(|Path\(|ArchiveDB|write_snapshot|publish_current|src\.visualization|data/current" \
    src/pretrade/pretrade_service.py src/pretrade/result_adapter.py \
    src/pretrade/master_resolution.py src/pretrade/trade_overlay.py src/pretrade/windpy_master.py
  ```

  Expected: pytest passes; `rg` has no matches. The only allowed external request code is the lazy WindPy call in `windpy_master.py`.

- [ ] **Step 8: Commit the service.**

  ```bash
  git add src/pretrade/result_adapter.py src/pretrade/pretrade_service.py \
    tests/pretrade/test_result_adapter.py tests/pretrade/test_pretrade_service.py
  git commit -m "feat: add shared kernel pretrade service"
  ```

### Task 6: Prove frozen-input parity, snapshot-only execution, and non-regression

**Files:**
- Modify: `tests/pretrade/test_pretrade_service.py`
- Modify: `docs/PRETRADE_DOCUMENT_STATUS.md`

**Consumes:** The completed Task 1–5 service and frozen `data_source_0123` manifest.

**Produces:** A reproducible service acceptance test that creates an unpublished snapshot and reads it back without reading business files during service invocation.

- [ ] **Step 1: Add a failing frozen-current acceptance test.**

  Add a pytest test marked `integration` that calls the existing frozen runtime builder once, writes its actual 27 frames and config workbook to an in-memory SQLite `PretradeContextStore`, publishes that local test store’s one pointer, then monkeypatches `builtins.open`, `pandas.read_excel`, `pandas.read_csv`, and `pandas.read_parquet` to raise `AssertionError("service must read snapshot only")` before invoking `PretradeRiskService` for a known held code.

  The final assertions are:

  ```python
  assert quote.snapshot_data_date == "2026-07-10"
  assert quote.dimensions
  assert fake_wind.calls == []
  assert quote.purchasable_pr_cap_wan is None or quote.purchasable_pr_cap_wan >= 0
  ```

- [ ] **Step 2: Run it and confirm failure before frozen-service wiring exists.**

  Run: `pytest tests/pretrade/test_pretrade_service.py -m integration -q`

  Expected: FAIL until the test can construct and invoke the complete service using the snapshot-only store.

- [ ] **Step 3: Implement only the fixture wiring necessary for the test.**

  Reuse `FrozenInputManifest`, `FrozenInputConfig`, `PipelinePaths`, `run_daily_runtime`, `capture_production_kernel_input`, and `PretradeSnapshotRequest`. Use the same `stage_legacy_local_limit_config`/cleanup boundary as `scripts/run_pretrade_context.py`. Do not add a new database schema, production pointer, manual Excel transform, test-only business calculation, or a service file-read escape hatch.

- [ ] **Step 4: Run focused, full, and frozen candidate verification.**

  Run:

  ```bash
  pytest tests/pretrade tests/risk_core -q
  ENV=test LIMIT_MONITOR_PROFILE=local /opt/homebrew/bin/python3 \
    scripts/run_kernel_candidate.py \
    --input-root /Users/dellawang/Desktop/LimitMonitorAutomation/data_source_0123 \
    --allow-output-root /Users/dellawang/Desktop/LimitMonitorAutomation-test-output \
    --output /Users/dellawang/Desktop/LimitMonitorAutomation-test-output/pretrade-service-final-parity \
    --reference /Users/dellawang/Desktop/LimitMonitorAutomation-test-output/pretrade-baseline-20260710-main1
  pytest -q
  ```

  Expected: every command exits `0`; the candidate runner reports no business table difference and the service acceptance uses only its locally persisted snapshot after setup.

- [ ] **Step 5: Record the verified service boundary and commit.**

  Add to `PRETRADE_DOCUMENT_STATUS.md` the exact test command, frozen manifest ID, passed result, and the statement that this phase has no page changes. Then commit:

  ```bash
  git add tests/pretrade/test_pretrade_service.py docs/PRETRADE_DOCUMENT_STATUS.md
  git commit -m "test: verify pretrade service from frozen snapshot"
  ```

### Task 7: Perform the explicit WindPy field capability gate and wire its verified map

**Files:**
- Create: `scripts/probe_windpy_bond_master.py`
- Create: `tests/scripts/test_probe_windpy_bond_master.py`
- Modify: `src/pretrade/windpy_master.py`
- Modify: `docs/superpowers/specs/2026-07-16-pretrade-shared-service-wind-design.md`
- Modify: `docs/PRETRADE_DOCUMENT_STATUS.md`

**Consumes:** A locally licensed Wind terminal and a representative bond code supplied on the command line.

**Produces:** A read-only JSON field-capability result on stdout and a `WindFieldMap` accepted only when every `BondMaster` field required by the production raw-input overlay has a verified vendor field mapping.

- [ ] **Step 1: Write the CLI parser tests before the probe.**

  Verify that the parser requires one `--bond-code`, supports repeated `--field vendor_field`, defaults to dry-run, and requires `--execute` before importing `WindPy`:

  ```python
  def test_probe_requires_execute_for_live_wind(monkeypatch) -> None:
      monkeypatch.setattr(probe, "_import_wind", lambda: pytest.fail("must not import"))
      assert probe.main(["--bond-code", "102480811.IB", "--field", "sec_name"]) == 0

  def test_probe_rejects_empty_field() -> None:
      assert probe.main(["--bond-code", "102480811.IB", "--field", ""]) == 2
  ```

- [ ] **Step 2: Run the parser tests and confirm failure before the script exists.**

  Run: `pytest tests/scripts/test_probe_windpy_bond_master.py -q`

  Expected: FAIL with `ImportError` for the script module.

- [ ] **Step 3: Implement the no-persistence probe.**

  The script accepts only `--bond-code`, repeated `--field vendor_field`, and `--execute`. Without `--execute`, print one JSON object with `executed` set to `false`, the supplied bond code, and the supplied field list, then exit `0`; it must not import `WindPy`. With `--execute`, it lazily imports `WindPy`, calls `w.start()`, issues one `w.wss` request, validates a single returned record, and prints field-by-field `available`, `raw_type`, and `is_null` data to stdout. It creates no file, database row, cache, or log under the project directory.

- [ ] **Step 4: Run the tests and then perform the real read-only capability call.**

  Run the deterministic parser tests first:

  ```bash
  pytest tests/scripts/test_probe_windpy_bond_master.py -q
  ```

  Then, from the Python environment containing the locally authorized `WindPy`, run the real call against the complete candidate field set used to derive the overlay’s `BondMaster` map:

  ```bash
  python scripts/probe_windpy_bond_master.py --execute --bond-code 102480811.IB \
    --field sec_name --field sccode --field isin --field outstandingbalance \
    --field issuerupdated --field issuerupdatedcode --field actual_controller \
    --field guarantor --field guarantorwindcode --field windl1type \
    --field bondtype --field issuer_type --field municipalbondWind \
    --field sec_type_de --field windl2type --field province
  ```

  Expected: Wind starts successfully, exactly one record is returned, and every field selected for the final overlay map reports `available: true` and `is_null: false`. If any required `BondMaster` property has no successful candidate, stop: retain the provider’s `MISSING_MASTER` behavior and do not invent a substitute field or default.

- [ ] **Step 5: Add the verified immutable map and a fixed regression fixture.**

  After the successful call, put precisely the accepted `internal → vendor` assignments in one immutable `DEFAULT_WIND_FIELD_MAP` in `windpy_master.py`; add its recorded single-row response as an in-memory test fixture in `tests/pretrade/test_windpy_master.py`. The production constructor may use this map only after the fixture has passed through the same normalizer. Do not save the vendor response, timestamp, code, or returned values outside that test fixture.

- [ ] **Step 6: Run final Wind-adapter and complete regression tests.**

  Run:

  ```bash
  pytest tests/pretrade/test_windpy_master.py tests/pretrade/test_master_resolution.py \
    tests/pretrade/test_trade_overlay.py tests/pretrade/test_result_adapter.py \
    tests/pretrade/test_pretrade_service.py -q
  pytest -q
  ```

  Expected: PASS. A missing `WindPy` installation in CI remains a passing fake-gateway test environment, while a production absence/failed call becomes `MISSING_MASTER`, never a fallback.

- [ ] **Step 7: Record the gate and commit.**

  Record only the verified field names, command exit status, and validation date in the design/status documents; do not record a Wind response or credentials. Then commit:

  ```bash
  git add scripts/probe_windpy_bond_master.py tests/scripts/test_probe_windpy_bond_master.py \
    src/pretrade/windpy_master.py tests/pretrade/test_windpy_master.py \
    docs/superpowers/specs/2026-07-16-pretrade-shared-service-wind-design.md \
    docs/PRETRADE_DOCUMENT_STATUS.md
  git commit -m "feat: verify Wind bond master field map"
  ```

## Plan self-review

- **Specification coverage:** Task 1 implements the accepted no-date-guard current behavior. Task 2 locks the user-approved existing high-yield cross-source append behavior. Tasks 3–5 cover snapshot-first resolution, on-the-fly non-persistent Wind, raw production overlays, the exact account `else → 自营业务` mapping, zero probe, PR/full-price separation, and confirmed-breach priority. Task 6 proves `data_source_0123` parity and snapshot-only service execution. Task 7 makes real Wind capability an explicit stop/go gate rather than guessed production data.
- **Non-goals checked:** no new pretrade table, no use of `archive_meta`, no DEV/PROD split, no TEST account, no cache, no response/audit persistence, no current-pointer change during frozen acceptance, and no changes to the existing pages or snapshot display builder.
- **Type consistency:** `PretradeLine`, `BondMaster`, `MasterResolution`, `BondMasterProvider`, `SnapshotBondMasterResolver`, `TradeOverlayBuilder`, and `PretradeRiskService` are introduced before their later consumers. The high-yield source functions are introduced before the overlay consumes them.
- **Placeholder scan:** dynamic Wind field names are not guessed. Task 7 is an external data-capability gate with a mandatory failure outcome; the code remains closed (`MISSING_MASTER`) until a concrete, verified map is committed.

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-16-pretrade-shared-service-wind.md`.

Two execution options:

1. **Subagent-Driven (recommended by the skill)** — unavailable in this workspace because the active collaboration policy prohibits spawning subagents.
2. **Inline Execution** — execute the tasks in this session with `superpowers:executing-plans`, stopping at the Wind field-capability gate before any live production wiring.
