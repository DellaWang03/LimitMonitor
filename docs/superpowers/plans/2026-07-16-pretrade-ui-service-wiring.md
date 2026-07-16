# 交易前共同服务页面接线实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 仅将“单券可购额度查询”和“一揽子债券超限试算”接到已验收的 `PretradeRiskService`，使持仓债可使用交易前 current 快照计算，非持仓债在 WindPy 未验证期间明确不可计算。

**Architecture:** 页面层通过一个只读服务工厂取得 `PretradeContextStore(ArchiveDB.from_env().engine)` 与无字段映射的 `WindPyBondMasterProvider`。页面只把用户输入转换为 `PretradeLine`、调用服务并展示 dataclass 结果；不得读取展示归档结果、复制限额公式或写入数据库。结果表转换留在纯 Python presenter，便于在没有 Streamlit 的测试中验收。

**Tech Stack:** Python 3.14、Streamlit、pandas、现有 SQLAlchemy `ArchiveDB`、`PretradeRiskService`。

## Global Constraints

- 仅修改新增的两个交易前页面及其新增展示辅助文件、`app.py`、侧边栏导航；其余页面不得改动。
- 共同内核、Stage0/1/2、展示快照、既有展示归档和 `archive_meta` 不得修改。
- 页面不得调用 `prepare_schema`、`write_snapshot` 或 `publish_current`。
- 页面不得把非持仓债降级为零额度；无已验证 Wind 映射必须显示“不可计算”。
- 交易前试算只支持 pretrade current；用户处于历史展示模式时必须提示切换最新数据，不能混用 `archive_meta` 历史批次。
- 账户输入不加白名单；共同服务继续使用既有“做市交易部做市业务 → 做市业务，其他 → 自营业务”规则。

---

### Task 1: 建立只读页面服务边界与纯结果展示适配

**Files:**
- Create: `src/visualization/pretrade_service.py`
- Create: `src/visualization/pretrade_presenter.py`
- Test: `tests/visualization/test_pretrade_presenter.py`

**Consumes:** `ArchiveDB.from_env().engine`、`PretradeContextStore`、`PretradeRiskService`、`SingleBondQuote`、`BasketCheck`、`DimensionResult`。

**Produces:** `get_pretrade_risk_service()`、`single_quote_status()`、`dimension_frame()`、`basket_summary()`、`basket_lines_from_frame()`。

- [x] **Step 1: Write failing pure presenter tests.**

```python
def test_basket_parser_discards_blank_rows_and_preserves_user_account() -> None:
    lines = basket_lines_from_frame(pd.DataFrame([...]))
    assert lines == (PretradeLine(1, "102480811.IB", "任意账户", 100.0, None),)

def test_dimension_frame_keeps_missing_master_as_uncomputable_not_zero() -> None:
    frame = dimension_frame((missing_master_dimension,))
    assert frame.loc[0, "状态"] == "不可计算"
    assert pd.isna(frame.loc[0, "交易后剩余(万)")
```

- [x] **Step 2: Run presenter tests to confirm missing-module failure.**

Run: `pytest tests/visualization/test_pretrade_presenter.py -q`

Expected: collection fails because the presenter module does not exist.

- [x] **Step 3: Implement only the page boundary and presentation conversion.**

```python
def get_pretrade_risk_service() -> PretradeRiskService:
    return PretradeRiskService(
        store=PretradeContextStore(ArchiveDB.from_env().engine),
        wind_provider=WindPyBondMasterProvider(),
    )
```

`dimension_frame()` maps each returned dimension to display fields only; it preserves `None` numeric values as missing and maps `CALCULATED` / `NOT_APPLICABLE` / other states to Chinese display labels. `basket_lines_from_frame()` ignores rows where all editable fields are blank, validates through `PretradeLine`, and leaves final numeric validation to `check_basket()`.

- [x] **Step 4: Run focused tests.**

Run: `pytest tests/visualization/test_pretrade_presenter.py tests/pretrade/test_pretrade_service.py -q`

Expected: PASS.

### Task 2: 用共同服务替换单券页面的平行查询

**Files:**
- Modify: `src/visualization/pages/page8_bond_quota.py`
- Test: `tests/visualization/test_pretrade_presenter.py`

**Consumes:** Task 1 presentation functions and the active Streamlit session.

**Produces:** 单券页面只调用 `quote_single_bond(code, account)`；不再导入或调用 `bond_quota_query`。

- [x] **Step 1: Add a failing source-boundary test.**

```python
def test_single_bond_page_uses_pretrade_service_not_legacy_query() -> None:
    source = Path("src/visualization/pages/page8_bond_quota.py").read_text()
    assert "query_bond_remaining_quota" not in source
    assert "get_pretrade_risk_service" in source
```

- [x] **Step 2: Run the test and confirm it fails on the legacy query import.**

Run: `pytest tests/visualization/test_pretrade_presenter.py::test_single_bond_page_uses_pretrade_service_not_legacy_query -q`

Expected: FAIL.

- [x] **Step 3: Replace only Page 8 implementation.**

Use a compact code/account form, a request button, `quote_single_bond`, summary cards and `dimension_frame()`. Catch `PretradeServiceError` and input errors as user-facing messages. If `data_loader.target_date` is not `None`, do not call the service and prompt users to switch to 最新数据.

- [x] **Step 4: Run focused tests.**

Run: `pytest tests/visualization/test_pretrade_presenter.py -q`

Expected: PASS.

### Task 3: 新增篮子页面并接入导航

**Files:**
- Create: `src/visualization/pages/page10_basket_pretrade.py`
- Modify: `src/visualization/components/sidebar.py`
- Modify: `app.py`
- Test: `tests/visualization/test_pretrade_presenter.py`

**Consumes:** Task 1 presenter and service factory.

**Produces:** `🧺 一揽子债券超限试算` 页面；导航与应用路由仅增加该页面。

- [x] **Step 1: Add failing route and source-boundary tests.**

```python
def test_app_and_sidebar_expose_only_the_new_basket_route() -> None:
    assert "一揽子债券超限试算" in Path("app.py").read_text()
    assert "一揽子债券超限试算" in Path("src/visualization/components/sidebar.py").read_text()
```

- [x] **Step 2: Run the route test and confirm it fails.**

Run: `pytest tests/visualization/test_pretrade_presenter.py::test_app_and_sidebar_expose_only_the_new_basket_route -q`

Expected: FAIL.

- [x] **Step 3: Implement the minimal basket interaction.**

Render a five-row editable table with `债券代码`、`拟买金额(万)_PR`、`拟买入账户`、`拟买全价成本(万)` columns; on submit, use `basket_lines_from_frame()` then `check_basket()`. Show overall status, total PR, confirmed breach/uncomputable counts, line-level reasons, and `dimension_frame()` results. A blank input set is a user error; high-yield cost handling remains entirely in the service. Historical mode is blocked exactly as in Task 2.

- [x] **Step 4: Run focused tests.**

Run: `pytest tests/visualization/test_pretrade_presenter.py -q`

Expected: PASS.

### Task 4: Verify the isolated UI wiring and document the Wind gate

**Files:**
- Modify: `docs/PRETRADE_DOCUMENT_STATUS.md`
- Test: `tests/visualization/test_pretrade_presenter.py`

- [x] **Step 1: Run all test suites and static boundaries.**

Run:

```bash
pytest tests/visualization/test_pretrade_presenter.py tests/pretrade -q
pytest -q
rg -n "query_bond_remaining_quota|write_snapshot|publish_current|prepare_schema" \
  src/visualization/pages/page8_bond_quota.py \
  src/visualization/pages/page10_basket_pretrade.py
```

Expected: tests pass; `rg` has no matches.

- [x] **Step 2: Record actual behaviour.**

Document that the two pages read only the pretrade current snapshot; held bonds calculate, while non-held bonds remain `MISSING_MASTER` until a WindPy field map is verified. State that no other page or display snapshot was changed.

- [x] **Step 3: Commit.**

```bash
git add src/visualization/pretrade_service.py src/visualization/pretrade_presenter.py \
  src/visualization/pages/page8_bond_quota.py \
  src/visualization/pages/page10_basket_pretrade.py \
  src/visualization/pages/__init__.py src/visualization/components/sidebar.py \
  app.py tests/visualization/test_pretrade_presenter.py \
  docs/PRETRADE_DOCUMENT_STATUS.md
git commit -m "feat: wire pretrade pages to shared service"
```

## Plan self-review

- The plan never modifies common limit calculations or existing display snapshots.
- The UI accesses only the existing four pretrade tables through the service factory; it creates no table and writes no pointer.
- It handles the unavailable Wind dependency conservatively and preserves the user-approved unrestricted account mapping.
- Tests cover the parser/display boundary and source-level assurance that Page 8 no longer reaches the old parallel quota calculator; no browser automation or visual restyling outside the two pages is introduced.

## Execution handoff

The user has approved inline execution in this already-isolated worktree. Execute Tasks 1–4 with test-first steps; do not merge or publish the branch during this plan.
