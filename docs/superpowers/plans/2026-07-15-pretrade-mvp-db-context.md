# 交易前 MVP 数据库上下文实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不改变 Stage0/Stage1/Stage2 限额业务规则、不修改既有展示页面的前提下，让每次完整日常运行同时发布既有展示归档和一份可从数据库重建共同内核的交易前 `PROD` 上下文；开发验收只写同一正式库中的 `DEV` 上下文。

**Architecture:** 既有展示链路保持为“每日计算 → 16 张归档结果表 → `archive_meta` → 展示快照/既有页面”。新增交易前链路由同一次 Stage0/1/2 运行的实际缓存生成 27 张共同内核输入，序列化到四张 `pretrade_` 表中；页面读取将来的 `PROD` 指针，而非展示快照或长表。由于当前 `run_daily.sh`/`run_daily.bat` 以三个独立 Python 进程运行各 Stage，必须新增一个同进程日常编排器保留实际缓存；它复用原处理器与业务函数，不复制任何限额公式。

**Tech Stack:** Python 3.14、pandas、pyarrow、SQLAlchemy、PyMySQL/MySQL、pytest、既有 Stage0/Stage1/Stage2 与 `ProductionRiskKernel`。

## Global Constraints

- 上线业务基线为 GitHub `main@579af695fb8727dec8249f66d07a8b0e723da137`；共同内核候选 `970ef6daa82dfb9fa4e458dd1da30f496ab26447` 已有零差异证据。
- 本计划以 `docs/superpowers/specs/2026-07-15-pretrade-mvp-db-context-design.md` 为数据库上下文设计依据；实施开始时先将其已确认内容写回权威文档状态登记。
- `data_source_0123-20260710-v1`、业务日 `2026-07-10`、冻结 manifest 和逻辑指纹 `2efae81c46b55da9b8f6a6b848f71e6341b2584059e7f5108562e4cf9f554d85` 是首轮验收唯一业务输入与金样。
- 只能新增 `pretrade_snapshot`、`pretrade_snapshot_dataset`、`pretrade_snapshot_dataset_chunk`、`pretrade_snapshot_current` 及其必要索引；不得修改 `archive_meta`、既有 16 张归档表、`ArchiveDB.write_batch()` 或既有展示读路径。
- 每个完成的数据日正常构建一次交易前快照；同一 `data_date` 修数重跑生成新的 `snapshot_id`，绝不覆盖原快照；只有显式发布才移动指针。
- 日常运行选择最新**完整**的已有业务数据，不以 T-1/T-2 交易日新鲜度作为阻断归档的条件；页面、归档和快照都记录实际 `data_date`。缺少必需输入、日期无法解析或 27 输入契约不完整仍必须失败，不能因取消新鲜度门槛而放宽完整性。
- 开发、自动化验收和人工数据库验证只能写 `usage=DEV`；不得创建 TEST schema、账号或实例。`usage=PROD` 的构建与发布仅由生产日常编排器显式调用。
- 非持仓债 Wind 主数据不属于本计划的落库对象，不建 Wind 缓存、不建 Wind 表、不写本地 JSON。在线查询时按需取最新 Wind 返回、内存规范化并完成字段校验是后续服务阶段的职责。
- 交易前上下文包含共同内核的 27 个外部输入、业务日、监管集中度参数、来源摘要和哈希；不保存展示快照长表、12 张展示结果的副本、内核输出、逐笔交易或第二套限额事实表。
- 既有展示快照及其长表始终是下游投影，交易前代码不得读取它们；`PROD` 发布和在线读取都必须要求交易前快照 `data_date == archive_meta.is_current` 的 `data_date`。日期不同只返回“数据同步中”，不得混用两批数据。
- 每项实现先写失败测试，再写最小实现；不得修改 `src/risk_core`、`src/stage0`、`src/stage1`、`src/stage2` 内的限额业务转换、公式、阈值、`fillna`、路由或字段含义。
- 本计划结束时不接入两个新增页面、不调用 Wind、不迁移展示页面；这些依赖交易前上下文零差异验收后的独立服务与 UI 计划。

## File Structure

- Modify: `docs/PRETRADE_SHARED_CORE_SPEC.md` — 用已批准的 MVP 上下文边界替换全量事实/Wind 落库/独立 TEST 要求。
- Modify: `docs/PRETRADE_DOCUMENT_STATUS.md` — 将本计划登记为唯一下一阶段，更新已失效的全量快照路径。
- Modify: `requirements.txt` — 显式加入与当前解释器兼容的 `pyarrow`。
- Create: `src/pretrade/__init__.py` — 交易前数据库上下文公开 API。
- Create: `src/pretrade/input_contract.py` — 27 项注册表、快照请求/元数据契约、哈希工具。
- Create: `src/pretrade/frame_codec.py` — DataFrame 的版本化 Parquet 编解码与 8 MiB 分块工具。
- Create: `src/pretrade/context_capture.py` — 从同次 Stage1/Stage2 实际缓存捕获唯一 `ProductionKernelInput`。
- Create: `src/pretrade/context_store.py` — 四张 `pretrade_` 表的 DDL、事务写入、读取、`DEV`/`PROD` 指针和日期守卫。
- Create: `src/pretrade/context_build.py` — 构建、读回和发布流程编排；不含业务公式。
- Create: `src/pipeline/daily_runtime.py` — 在同一 Python 进程中依次调用既有 Stage0/1/2 处理器并暴露它们的运行期缓存。
- Create: `scripts/run_pretrade_context.py` — `data_source_0123` 的隔离 `DEV` 构建/重放命令，绝不发布 `PROD`。
- Create: `scripts/run_daily_pipeline.py` — 正常日常运行编排：Stage0/1/2 → `READY` 上下文 → 既有归档 → `PROD` 发布 → 既有展示快照。
- Modify: `src/stage1/stage1_processor.py` — 记录本次已实际解析的监管集中度参数，供运行期捕获使用；不改变计算调用。
- Modify: `run_daily.sh` and `run_daily.bat` — 改为调用同一 Python 日常编排器，保留现有环境变量、失败退出和展示快照行为。
- Create: `tests/pretrade/conftest.py` — 小型 27 输入夹具、SQLite 测试引擎和不可变指针断言。
- Create: `tests/pretrade/test_input_contract.py` — 输入注册表、哈希和快照请求测试。
- Create: `tests/pretrade/test_frame_codec.py` — Parquet、分块、空表、索引、日期/数值/空值的往返测试。
- Create: `tests/pretrade/test_context_capture.py` — 同次缓存捕获、重叠输入相等性和参数捕获测试。
- Create: `tests/pretrade/test_context_store.py` — DDL、事务、读回、指针、日期守卫和故障注入测试。
- Create: `tests/pretrade/test_context_build.py` — 构建流程及无文件/网络读取边界测试。
- Create: `tests/pipeline/test_daily_runtime.py` — 同进程 Stage 编排不改变既有结果契约的测试。
- Create: `tests/scripts/test_run_pretrade_context.py` and `tests/scripts/test_run_daily_pipeline.py` — CLI 参数、默认 `DEV`、禁止误发布和失败退出测试。
- Create: `docs/evidence/pretrade-db-context-20260710.json` — 仅在完整 `DEV` 验收成功后写入的结果证据。

## Out of Scope

- 两个交易前页面的改版、单券/一揽子查询服务、Wind API 调用及其前端展示；它们必须在本计划的数据库重放门禁成功后另立计划。
- 34 张兼容投影、既有页面读取迁移、`ArchiveDB` 改造、`archive_meta` 指针替换、对象存储、原始 Excel/ACCDB 入库、Wind 落库、逐行血缘、事实表、缓存、逐笔审计、独立测试环境与权限体系。
- 把 `pretrade_` 快照作为展示快照、长表或既有页面输入。

### Task 1: 将已批准的 MVP 边界写入权威文档

**Files:**

- Modify: `docs/PRETRADE_SHARED_CORE_SPEC.md:3.1, 4.2-4.4, 5, 6.4, 7`
- Modify: `docs/PRETRADE_DOCUMENT_STATUS.md:2-6`
- Modify: `docs/superpowers/specs/2026-07-15-pretrade-mvp-db-context-design.md` only if implementation discovery exposes a contradiction; otherwise keep it unchanged.

**Interfaces:**

- Consumes: 已批准的 MVP 设计与现有共同内核零差异证据。
- Produces: 一份允许后续代码实施引用的权威范围：27 输入快照、四张 `pretrade_` 表、同进程日常捕获、Wind on-the-fly、不改展示链路。

- [ ] **Step 1: 修改权威规格的非业务架构段落**

保留 `PRETRADE_SHARED_CORE_SPEC.md` 第 2、3.2-3.7 的业务规则和金样要求不变。将第 3.1 中“Wind 采集服务写数据库”的表述替换为以下运行边界：

```markdown
交易前上下文中的持仓、池、配置、分类、分母和参数由同次每日运行持久化到 `pretrade_` 快照；非持仓债仅在当次交易前查询调用 Wind，规范化后驻留内存，不落库。交易前服务不得读取展示快照、展示长表、Excel、ACCDB 或本地业务配置。
```

将第 5、6.4、7 节中“34 张投影、类型化事实、Wind 表和独立 TEST 账号”替换为本计划 Global Constraints 的四表契约、`DEV`/`PROD` 逻辑隔离、数据日期守卫与第 7 个任务的验收门禁。明确既有 16 表和 `archive_meta` 不受此阶段 DDL/DML 影响。

- [ ] **Step 2: 更新文档状态登记**

将 MVP 设计列为 `AUTHORITATIVE` 的数据库上下文附录，并在 `ACTIVE_IMPLEMENTATION_PLAN` 增加本文件。把“不可变数据库快照与全量落库、Wind 主数据落库、34 投影”标为 `SUPERSEDED` 架构方向，不删除其审计记录。将后续顺序改为：

```text
共同内核证据 → 交易前 MVP 数据库上下文 → 单券/一揽子共同内核服务与 on-the-fly Wind → 两个指定页面 → 全量业务/UI 验收
```

- [ ] **Step 3: 审查文档冲突并提交**

Run:

```bash
rg -n "Wind.*落库|独立 TEST|34 张|类型化事实|展示快照.*输入" docs/PRETRADE_SHARED_CORE_SPEC.md docs/PRETRADE_DOCUMENT_STATUS.md
git diff --check
git add docs/PRETRADE_SHARED_CORE_SPEC.md docs/PRETRADE_DOCUMENT_STATUS.md
git commit -m "docs: adopt pretrade mvp context contract"
```

Expected: 没有把展示快照作为交易前输入、没有要求 Wind 落库或独立 TEST 账号的现行实施性文字；业务规则章节未改动。

### Task 2: 定义唯一的 27 输入契约与无损 Parquet 编解码

**Files:**

- Modify: `requirements.txt`
- Create: `src/pretrade/__init__.py`
- Create: `src/pretrade/input_contract.py`
- Create: `src/pretrade/frame_codec.py`
- Create: `tests/pretrade/conftest.py`
- Create: `tests/pretrade/test_input_contract.py`
- Create: `tests/pretrade/test_frame_codec.py`

**Interfaces:**

- Consumes: `src.risk_core.STAGE1_REQUIRED_FRAMES`, `STAGE2_REQUIRED_FRAMES`, `ProductionKernelInput`, `ProductionKernelParameters`。
- Produces: `KERNEL_INPUT_DATASETS`, `PretradeSnapshotRequest`, `SerializedFrame`, `serialize_frame(frame)`, `deserialize_frame(serialized)` and `split_payload(payload)`; Task 3 only accepts these values.

- [ ] **Step 1: 写失败测试，固定输入集合和快照元数据**

在 `tests/pretrade/test_input_contract.py` 写入下列断言：输入集合是 `tuple(dict.fromkeys(STAGE1_REQUIRED_FRAMES + STAGE2_REQUIRED_FRAMES))`，长度为 27；重复键只出现一次；缺少键、额外键、NaT 业务日期、非有限监管参数或非法 `usage` 都失败。测试同一帧内容变化、参数变化、业务日变化会改变 `input_hash`，而字典插入顺序不改变哈希。

```python
def test_kernel_input_dataset_registry_is_the_exact_27_frame_union() -> None:
    assert KERNEL_INPUT_DATASETS == tuple(
        dict.fromkeys(STAGE1_REQUIRED_FRAMES + STAGE2_REQUIRED_FRAMES)
    )
    assert len(KERNEL_INPUT_DATASETS) == 27

def test_snapshot_request_rejects_missing_or_extra_dataset() -> None:
    frames = make_all_kernel_frames()
    frames.pop(KERNEL_INPUT_DATASETS[-1])
    with pytest.raises(PretradeInputContractError, match="缺少共同内核输入"):
        PretradeSnapshotRequest.from_kernel_input(make_kernel_input(frames), usage="DEV")
```

- [ ] **Step 2: 写失败测试，固定 Parquet 往返约束**

覆盖空 DataFrame、空字符串、`pd.NA`、`NaT`、`datetime64[ns]`、带时区以外的日期、可空整数、浮点、`Decimal`、中文列名和非默认索引。每个用例调用 `serialize_frame` 后再 `deserialize_frame`，并使用 `pandas.testing.assert_frame_equal(check_dtype=True, check_exact=True, check_names=True)` 比较。测试 8 MiB 边界：`8 * 1024 * 1024` 字节刚好一块，超出一字节时两块；拼接后 SHA-256 与原 payload 一致。

```python
def test_round_trip_preserves_frame_values_dtypes_columns_and_index() -> None:
    frame = pd.DataFrame({"日期": pd.Series([pd.Timestamp("2026-07-10"), pd.NaT]),
                          "金额": pd.Series([Decimal("1.20"), None], dtype="object"),
                          "代码": pd.Series(["102480811.IB", pd.NA], dtype="string")},
                         index=pd.Index(["a", "b"], name="行"))
    restored = deserialize_frame(serialize_frame(frame))
    pdt.assert_frame_equal(restored, frame, check_dtype=True, check_exact=True)
```

- [ ] **Step 3: 实现最小输入契约**

在 `input_contract.py` 使用下列公开形状，不为交易业务增加字段或状态机：

```python
KERNEL_INPUT_DATASETS: tuple[str, ...] = tuple(
    dict.fromkeys(STAGE1_REQUIRED_FRAMES + STAGE2_REQUIRED_FRAMES)
)

@dataclass(frozen=True)
class PretradeSnapshotRequest:
    usage: Literal["DEV", "PROD"]
    kernel_input: ProductionKernelInput
    code_commit: str
    engine_version: str
    input_contract_version: str
    source_manifest: Mapping[str, object]
    note: str | None = None

    @classmethod
    def from_kernel_input(cls, kernel_input: ProductionKernelInput, *, usage: str,
                          code_commit: str = "", engine_version: str = "risk-core-v1",
                          input_contract_version: str = "pretrade-input-v1",
                          source_manifest: Mapping[str, object] | None = None,
                          note: str | None = None) -> "PretradeSnapshotRequest": ...
```

`from_kernel_input` 先取 `kernel_input.detached_frames()`，精确校验 27 键集合，再用按 `KERNEL_INPUT_DATASETS` 顺序排列的每帧 `content_hash`、`business_date.isoformat()` 和监管参数计算 `input_hash`。`source_manifest` 必须包含 `files`、`static_issuer_mapping`、`captured_at` 三个键；静态映射仅记录 SHA-256、行数和验证时间。

- [ ] **Step 4: 实现无损编解码与依赖固定**

在 `requirements.txt` 增加一行 `pyarrow>=23.0.0,<24.0.0`。`frame_codec.py` 使用 `pyarrow.Table.from_pandas(frame, preserve_index=True)` 和 Zstandard 压缩的 Parquet bytes；禁止 pickle、CSV、JSON 或将未知 object 单元格静默字符串化。编解码器返回：

```python
@dataclass(frozen=True)
class SerializedFrame:
    payload: bytes
    content_hash: str
    schema_json: str
    row_count: int
    payload_size_bytes: int
    serializer_version: str = "parquet-arrow-v1"

def split_payload(payload: bytes, *, chunk_size: int = 8 * 1024 * 1024) -> tuple[bytes, ...]: ...
def join_payload(chunks: Sequence[bytes]) -> bytes: ...
```

`deserialize_frame` 先验证 payload SHA-256，再执行 `pq.read_table(...).to_pandas()`；读取结果与输入的列、index、dtype 不一致时由调用方的帧相等性验证抛错，绝不降级类型。

- [ ] **Step 5: 验证并提交**

Run:

```bash
/opt/homebrew/bin/python3 -m pytest -q tests/pretrade/test_input_contract.py tests/pretrade/test_frame_codec.py
git diff --check
git add requirements.txt src/pretrade tests/pretrade/conftest.py tests/pretrade/test_input_contract.py tests/pretrade/test_frame_codec.py
git commit -m "feat: define pretrade input snapshot codec"
```

Expected: 所有单元测试通过；没有 `pickle`、`to_csv`、`read_csv` 或业务公式进入 `src/pretrade`。

### Task 3: 实现四表快照存储、读回和指针日期守卫

**Files:**

- Create: `src/pretrade/context_store.py`
- Create: `tests/pretrade/test_context_store.py`

**Interfaces:**

- Consumes: `PretradeSnapshotRequest`、`SerializedFrame`、SQLAlchemy `Engine` 和可选的既有 `archive_meta` 只读查询。
- Produces: `PretradeContextStore.prepare_schema()`, `write_ready_snapshot(request)`, `load_kernel_input(snapshot_id)`, `get_current_snapshot(usage)`, `publish(snapshot_id, usage)`; Tasks 5/6 只能通过这些方法写 `pretrade_` 表。

- [ ] **Step 1: 写失败测试，固定通用 DDL 形状**

使用 SQLite 内存引擎运行单元测试，以确保无独立数据库即可验证事务；用 SQLAlchemy metadata 创建四张表。断言表名、主键和唯一约束：

```text
pretrade_snapshot: snapshot_id PK
pretrade_snapshot_dataset: (snapshot_id, dataset_code) PK
pretrade_snapshot_dataset_chunk: (snapshot_id, dataset_code, chunk_ordinal) PK
pretrade_snapshot_current: usage PK
```

测试写入成功后只有一个 `READY` snapshot、恰好 27 条 dataset 元数据、所有 chunk ordinal 从零连续、每个块不超过 8 MiB；写入任一中间块失败时四表中不存在该 snapshot，旧 current 不变。

```python
def test_failed_chunk_write_rolls_back_snapshot_and_keeps_current(engine, request) -> None:
    store = PretradeContextStore(engine)
    old = store.write_ready_snapshot(request)
    store.publish(old, "DEV")
    with pytest.raises(RuntimeError, match="injected chunk failure"):
        store.write_ready_snapshot(request, fail_after_chunk=1)
    assert store.get_current_snapshot("DEV").snapshot_id == old
    assert store.list_snapshot_ids() == [old]
```

- [ ] **Step 2: 写失败测试，固定读回、不可变和发布行为**

测试从数据库读回的 `ProductionKernelInput` 与原输入逐帧严格相等；删除一个块、交换块顺序或篡改 `content_hash` 必须在反序列化前失败。测试 `READY` snapshot 的字段不可 update；同一日期两次 `write_ready_snapshot` 生成不同 UUID。测试 `DEV` snapshot 不能发布到 `PROD`，`LOADING` 不能被读取。使用 SQLite 建立最小 `archive_meta` 表模拟既有归档：`publish(PROD)` 仅在 snapshot `data_date` 等于 `is_current=1` 的日期时成功，`DEV` 不受该限制。

- [ ] **Step 3: 实现四表和事务写入**

`PretradeContextStore` 只接受调用方注入的 `Engine`；生产构造器可使用 `ArchiveDB.from_env().engine`，但不得调用 `ArchiveDB.prepare_stage_tables_schema()`、`write_batch()` 或任何旧表写方法。`prepare_schema()` 只执行本任务四张表的 `metadata.create_all(engine)` 和必要索引创建。

在一个 `engine.begin()` 事务内按以下顺序完成 `write_ready_snapshot`：

```text
insert pretrade_snapshot(status=LOADING)
→ 按 KERNEL_INPUT_DATASETS 写 metadata 与顺序 chunk
→ 从同一事务连接按 ordinal 读回全部 chunks
→ 校验每帧 payload/content hash/schema/row count 与 aggregate input_hash
→ 置 status=READY, ready_at=UTC now
→ commit
```

捕获任意异常并让事务回滚；不插入 `FAILED` 行。调用方无法传入自定义表名、chunk 大小或任意 SQL。

`load_kernel_input` 要求 snapshot `READY`，读取 27 项、检查集合和 ordinal 连续性、拼接/校验/反序列化，并构造：

```python
ProductionKernelInput(
    business_date=pd.Timestamp(snapshot.data_date),
    frames=restored_frames,
    parameters=ProductionKernelParameters(snapshot.regulatory_concentration_limit),
)
```

`publish` 在短事务内校验 usage、READY、usage 匹配；对 `PROD` 再 `SELECT data_date FROM archive_meta WHERE is_current = 1`，缺行、重复行或日期不同均抛 `PretradePublishError`。随后以更新或插入的方式原子设置该 usage 的一行 current 指针。

- [ ] **Step 4: 验证并提交**

Run:

```bash
/opt/homebrew/bin/python3 -m pytest -q tests/pretrade/test_context_store.py
git diff --check
git add src/pretrade/context_store.py tests/pretrade/test_context_store.py
git commit -m "feat: add transactional pretrade context store"
```

Expected: 事务、`DEV`/`PROD` 隔离、日期不匹配拒绝、缺块拒绝和旧指针保留全部通过；测试没有创建任何 `archive_` 表或执行旧表 DML。

### Task 4: 从同一日常运行捕获实际共同内核输入

**Files:**

- Modify: `src/stage1/stage1_processor.py:82-88, 326`
- Create: `src/pretrade/context_capture.py`
- Create: `src/pipeline/daily_runtime.py`
- Create: `tests/pretrade/test_context_capture.py`
- Create: `tests/pipeline/test_daily_runtime.py`

**Interfaces:**

- Consumes: 已执行完的 `Stage1Processor.cache`、`Stage2Processor.cache`、两个处理器的业务日期和 Stage1 实际解析的监管集中度参数。
- Produces: `capture_production_kernel_input(stage1, stage2) -> ProductionKernelInput` 和 `DailyRuntimeResult(stage0, stage1, stage2)`；Task 5 不得重新打开 Excel/ACCDB/配置文件来补这 27 项输入。

> 实施更正（2026-07-15）：冻结 `data_source_0123` 的同进程诊断证明，Stage2 会从 Stage1 Excel 导出重新读取共享上下文，造成 `债券持仓明细表_信用债` 的二进制浮点尾差；`穿透高收益债券` 也会经历 Stage1 清洗后再读的边界。为保证共同内核严格复用 Stage1 实际计算输入，所有共享外部输入改由 Stage1 缓存作为唯一来源，不再要求两个缓存逐帧相等。以此重放时 Stage1 35 表和 Stage2 限额计算结果严格一致；仅两张命名的 Stage2 原始上下文展示表按权威规格第 4.1 节作 `1e-12` 绝对尾差验证，业务计算和状态判断不使用容差。

- [ ] **Step 1: 写失败测试，固定来源与重叠验证**

使用带精确中文表名的假 Stage1/Stage2 缓存测试：每个 27 输入键只能从指定运行缓存取得；`债券持仓明细表`、各 Stage1 限额表、债券/主体池、调整表及全部共享输入从 Stage1；`高风险限额`、地域限额、核算系统持仓、高收益投资本金、净资产和高收益限额从 Stage2。Stage2 的 Excel 重读副本不得成为共同内核输入来源。

测试任一必需键缺失、两个业务日期不相等、监管参数未被 Stage1 记录都失败；捕获结果的 27 帧与缓存脱离，随后修改缓存不改变 `ProductionKernelInput`。

```python
def test_capture_uses_stage1_canonical_frame_when_legacy_stage2_rereads_differ(
    stage1_runtime, stage2_runtime
) -> None:
    stage2_runtime.cache["债券持仓明细表_信用债"] = pd.DataFrame({"代码": ["stage2-reread"]})
    captured = capture_production_kernel_input(stage1_runtime, stage2_runtime)
    assert_frame_equal(
        captured.frames["债券持仓明细表_信用债"],
        stage1_runtime.cache["债券持仓明细表_信用债"],
    )
```

- [ ] **Step 2: 最小化记录实际监管参数**

在 `Stage1Processor._build_limit_calculator()` 中保留现有 `resolver._load_regulatory_concentration_limit()` 的唯一调用，并紧随其后写入：

```python
self._runtime_regulatory_concentration_limit = float(regulatory_limit)
```

继续以原参数构造 `LimitDetailCalculator`。不得再次读取 `ConfigLoader`，不得改变 `_build_limit_calculator` 的返回值、缓存、输出文件或限额计算顺序。

- [ ] **Step 3: 实现捕获器与单进程日常运行时对象**

在 `context_capture.py` 固定 `FRAME_SOURCE` 映射，列出全部 27 代码和唯一来源；共享输入固定使用 Stage1 实际内存帧，Stage2 仅提供其专属 6 项输入。验证 `stage1._business_date == stage2._business_date` 后构造 `ProductionKernelInput`。

`daily_runtime.py` 不重新实现业务逻辑。它顺序实例化既有 `Stage0Processor`、`Stage1Processor`、`Stage2Processor`，调用各自 `process_all()`，保留对象和返回表：

```python
@dataclass(frozen=True)
class DailyRuntimeResult:
    stage0_results: Mapping[str, pd.DataFrame]
    stage1_processor: Stage1Processor
    stage2_processor: Stage2Processor
    stage1_results: Mapping[str, pd.DataFrame]
    stage2_results: Mapping[str, pd.DataFrame]

def run_daily_runtime(*, config: Any, data_dir: Path, current_dir: Path,
                      target_date: str | None = None) -> DailyRuntimeResult: ...
```

输出目录必须仍为 `current_dir/stage0_output`、`stage1_output`、`stage2_output`，让现有 `daily_archive.py` 读取完全相同的文件。`target_date` 仅透传至 `Stage0Processor`；Stage1/2 行为保持现有逻辑。

- [ ] **Step 4: 验证日常运行时不改变生产输出**

在 `tests/pipeline/test_daily_runtime.py` 注入假处理器，断言实例化与调用顺序严格为 Stage0 → Stage1 → Stage2，路径不变、每个 `process_all()` 恰好一次，异常立即中止且不构造下游处理器。再通过 `scripts/run_kernel_candidate.py` 对 `data_source_0123` 做一次完整候选重跑并与已封存金样逐表零差异。

Run:

```bash
/opt/homebrew/bin/python3 -m pytest -q tests/pretrade/test_context_capture.py tests/pipeline/test_daily_runtime.py
ENV=test LIMIT_MONITOR_PROFILE=local /opt/homebrew/bin/python3 scripts/run_kernel_candidate.py --input-root /Users/dellawang/Desktop/LimitMonitorAutomation/data_source_0123 --allow-output-root /Users/dellawang/Desktop/LimitMonitorAutomation-test-output --output /Users/dellawang/Desktop/LimitMonitorAutomation-test-output/pretrade-context-runtime-parity --reference /Users/dellawang/Desktop/LimitMonitorAutomation-test-output/pretrade-baseline-20260710-main1
git diff --check
git add src/stage1/stage1_processor.py src/pretrade/context_capture.py src/pipeline/daily_runtime.py tests/pretrade/test_context_capture.py tests/pipeline/test_daily_runtime.py
git commit -m "feat: capture daily runtime kernel inputs"
```

Expected: 10/35/22 表、逻辑指纹和每一字段零差异；捕获器从运行缓存得到精确 27 输入，不读取展示结果或显示快照。

### Task 5: 编排 `DEV` 上下文构建、读回验证和隔离重放

**Files:**

- Create: `src/pretrade/context_build.py`
- Create: `scripts/run_pretrade_context.py`
- Create: `tests/pretrade/test_context_build.py`
- Create: `tests/scripts/test_run_pretrade_context.py`

**Interfaces:**

- Consumes: `DailyRuntimeResult`、`capture_production_kernel_input`、`PretradeContextStore`、`ProductionRiskKernel` 和冻结输入工具。
- Produces: `build_ready_context(runtime, store, request) -> UUID`、`verify_rehydrated_context(store, snapshot_id) -> ProductionKernelInput` 和只写 `DEV` 的命令行入口。

- [ ] **Step 1: 写失败测试，构建后立即读回而不重算业务规则**

测试 `build_ready_context` 的操作顺序：捕获 → `write_ready_snapshot` → `load_kernel_input` → 逐帧相等 → 返回 UUID。任何帧不相等、哈希不符或构造 `ProductionKernelInput` 失败，均抛错且 `DEV` current 不变。测试构建函数本身不调用 `ProductionRiskKernel.run_stage1/run_stage2`，因此生产日常不会再跑第二遍完整限额计算；完整内核重放只在下述验收命令中执行。

```python
def test_build_verifies_database_round_trip_before_returning_ready_snapshot(runtime, store) -> None:
    snapshot_id = build_ready_context(runtime, store, make_dev_request(runtime))
    restored = store.load_kernel_input(snapshot_id)
    assert_kernel_input_equal(restored, capture_production_kernel_input(
        runtime.stage1_processor, runtime.stage2_processor
    ))
```

- [ ] **Step 2: 实现构建与离线重放辅助函数**

`context_build.py` 只做输入捕获、请求创建、存储、读回和等值比较。公开一个仅测试/验收使用的函数：

```python
def replay_kernel_from_snapshot(store: PretradeContextStore, snapshot_id: UUID) -> ProductionKernelResult:
    inputs = store.load_kernel_input(snapshot_id)
    kernel = ProductionRiskKernel()
    stage1 = kernel.run_stage1(inputs)
    stage2 = kernel.run_stage2(inputs, stage1)
    return ProductionKernelResult(stage1, stage2)
```

日常构建路径不调用此函数；验收路径使用其结果与冻结 35/22 输出逐表、逐行、逐字段比较。

- [ ] **Step 3: 实现默认 `DEV` 的隔离 CLI**

`run_pretrade_context.py` 接收：

```text
--input-root PATH (required)
--manifest PATH (required)
--allow-output-root PATH (required)
--output PATH (required, new empty child)
--usage DEV (only accepted value)
--note TEXT (optional)
```

它复用 `FrozenInputManifest`、`FrozenInputConfig`、`PipelinePaths` 和 `run_daily_runtime`，运行 `data_source_0123` 到隔离输出，再连接 `ArchiveDB.from_env().engine` 并只调用 `PretradeContextStore`。它必须拒绝 `--usage PROD`、`--publish`、`--data-date` 覆盖、符号链接输入和非空输出目录。成功时写入输出目录的 JSON 摘要，包含 `snapshot_id`、`usage=DEV`、27 个 dataset 的行数/hash 和 replay diff 结论；摘要不含数据库凭据或 Wind 数据。

- [ ] **Step 4: 运行单元测试并提交**

Run:

```bash
/opt/homebrew/bin/python3 -m pytest -q tests/pretrade/test_context_build.py tests/scripts/test_run_pretrade_context.py
git diff --check
git add src/pretrade/context_build.py scripts/run_pretrade_context.py tests/pretrade/test_context_build.py tests/scripts/test_run_pretrade_context.py
git commit -m "feat: add dev pretrade context builder"
```

Expected: 默认与显式输入均只允许 `DEV`，没有 `ArchiveDB.write_batch()`、Wind、展示快照或 `PROD` 指针调用。

### Task 6: 将正常日常运行改为同进程构建、既有归档与受守卫发布

**Files:**

- Create: `scripts/run_daily_pipeline.py`
- Modify: `run_daily.sh`
- Modify: `run_daily.bat`
- Create: `tests/scripts/test_run_daily_pipeline.py`

**Interfaces:**

- Consumes: 既有配置/日期验证、`run_daily_runtime`、`build_ready_context`、`archive_to_db`、`PretradeContextStore.publish` 和 `write_display_snapshots`。
- Produces: 唯一的日常生产顺序；同一完整数据日的展示 `archive_meta` 与交易前 `PROD` pointer 只有同时可读或交易前页面返回“数据同步中”。

- [ ] **Step 1: 写失败测试，固定成功与失败时序**

用 monkeypatch 的假函数记录调用序列。成功序列必须精确为：

```text
validate_current_inputs
→ run_daily_runtime
→ build_ready_context(usage=PROD, no pointer move)
→ archive_to_db
→ publish(snapshot_id, PROD)
→ write_display_snapshots
```

测试上下文构建失败时不得调用 `archive_to_db`；既有归档失败时不得调用 `publish` 或展示快照；发布失败时不得调用展示快照，且交易前读取器由于日期守卫拒绝使用旧 `PROD` pointer；展示快照失败记录非零状态但不回滚已经成功的两份数据归档。额外测试：当实际业务日期不是 T-1 但 27 项输入完整时，日期校验只记录 warning，仍走完整成功序列；日期无法解析、必需输入缺失或捕获契约不完整时，仍在 `build_ready_context` 前失败。

```python
def test_archive_failure_does_not_publish_pretrade_pointer(monkeypatch) -> None:
    calls = install_fake_daily_dependencies(monkeypatch, archive_error=RuntimeError("archive"))
    assert main(["--archive-date", "2026-07-15"]) == 1
    assert calls == ["validate", "runtime", "build", "archive"]
```

- [ ] **Step 2: 实现同进程日常编排器**

将 `run_stage0.py` 中已有的日期验证提取为 `validate_current_inputs(config, target_date, environment)` 函数，现有 `run_stage0.main()` 继续调用它。对“Access 最新日期是否等于 T-1”的检查固定使用 `strict_mode=False`：记录来源日期、预期 T-1 日期和 warning，但绝不设置 `DATA_INCOMPLETE`、绝不创建 `.INCOMPLETE_DATA_WARNING`、绝不阻断归档。`run_daily_pipeline.py` 使用同一个函数与 `get_config()`；它不得新增任何 T-1/T-2 新鲜度硬门槛。业务日期始终从实际 Stage1/2 缓存捕获，`--archive-date` 只用于旧归档的 archive 时间标签。

输入是否可归档只由以下完整性门禁决定：每个 Stage 成功、16 张既有归档输出齐全、捕获到 27 个共同内核输入、两个 Stage 业务日期一致、所有 Parquet 往返/哈希检查通过。日期无法解析、必需文件/输入缺失、缓存重叠不一致或来源校验异常仍必须失败，不能被“最新可用”策略掩盖。

生产运行调用：

```python
runtime = run_daily_runtime(config=config, data_dir=config.get_data_dir(), current_dir=CURRENT_DIR,
                            target_date=args.target_date)
snapshot_id = build_ready_context(runtime, store, make_request(usage="PROD"))
archive_to_db(archive_date)
store.publish(snapshot_id, "PROD")
write_display_snapshots(CURRENT_DIR / "display_snapshots")
```

`archive_to_db` 成功后若 `publish` 因日期不匹配失败，记录 `snapshot_id` 和两个日期，返回非零；不修改旧归档数据，也不尝试回滚它。后续日常重跑或显式恢复命令只能发布同日期的 `READY` snapshot。此情况中交易前读服务的日期检查是唯一允许的响应：返回“数据同步中”，而不是旧数据结果。

- [ ] **Step 3: 修改两个 shell 包装器**

将 `run_daily.sh` 与 `run_daily.bat` 的三个独立 `run_stage*.py` 命令、`daily_archive.py` 和 `generate_display_snapshot.py` 顺序替换为一次 `scripts/run_daily_pipeline.py` 调用。保留：解释器选择、`LIMIT_MONITOR_ENV`、配置的 DB 环境变量检查、非零退出、`data/current` 输出路径和用户可读日志。禁止在 shell 中拼接第二次归档、第二次展示快照或 pointer 修改命令。

- [ ] **Step 4: 验证并提交**

Run:

```bash
/opt/homebrew/bin/python3 -m pytest -q tests/scripts/test_run_daily_pipeline.py tests/pipeline/test_daily_runtime.py
git diff --check
git add scripts/run_daily_pipeline.py run_daily.sh run_daily.bat run_stage0.py tests/scripts/test_run_daily_pipeline.py
git commit -m "feat: publish pretrade context with daily run"
```

Expected: 生产日常只在运行期上下文完整时才写既有归档；非 T-1 的完整数据可正常归档且准确显示实际日期；交易前 `PROD` 永远不能发布不同 `data_date` 的快照；既有页面仍只通过 `archive_meta` 与展示快照读取。

### Task 7: 用 `data_source_0123` 完成正式库 `DEV` 快照的零差异验收

**Files:**

- Create: `docs/evidence/pretrade-db-context-20260710.json`
- Modify: `docs/PRETRADE_DOCUMENT_STATUS.md` only after every command in this task succeeds.

**Interfaces:**

- Consumes: 当前阿里云正式数据库的既有凭据、冻结输入清单、共同内核、已封存 10/35/22 金样和 `DEV` 指针。
- Produces: 可审计证据：新 `DEV` snapshot ID、27 项元数据/hash、数据库重放的 35/22 零差异结果、旧表未写证明；不移动 `PROD`。

- [ ] **Step 1: 对真实冻结数据先跑无数据库候选差分**

Run:

```bash
ENV=test LIMIT_MONITOR_PROFILE=local /opt/homebrew/bin/python3 scripts/run_kernel_candidate.py --input-root /Users/dellawang/Desktop/LimitMonitorAutomation/data_source_0123 --allow-output-root /Users/dellawang/Desktop/LimitMonitorAutomation-test-output --output /Users/dellawang/Desktop/LimitMonitorAutomation-test-output/pretrade-context-final-kernel --reference /Users/dellawang/Desktop/LimitMonitorAutomation-test-output/pretrade-baseline-20260710-main1
```

Expected: Stage0/1/2 逻辑指纹仍为 `2efae81c46b55da9b8f6a6b848f71e6341b2584059e7f5108562e4cf9f554d85`；任何差异停止，不连接数据库。

- [ ] **Step 2: 构建正式库 `DEV` 上下文并重放共同内核**

确认环境变量 `DB_HOST`、`DB_PORT`、`DB_USER`、`DB_PASSWORD`、`DB_NAME` 已由运行环境提供且不打印。然后运行：

```bash
ENV=test LIMIT_MONITOR_PROFILE=local /opt/homebrew/bin/python3 scripts/run_pretrade_context.py --input-root /Users/dellawang/Desktop/LimitMonitorAutomation/data_source_0123 --manifest config/test_manifests/data_source_0123-20260710-v1.json --allow-output-root /Users/dellawang/Desktop/LimitMonitorAutomation-test-output --output /Users/dellawang/Desktop/LimitMonitorAutomation-test-output/pretrade-context-dev-20260710 --usage DEV --note "frozen-data_source_0123 acceptance"
```

Expected: 创建一个新的 `pretrade_snapshot(usage=DEV,status=READY,data_date=2026-07-10)`；27 个数据集全部存在、读回相等；共同内核重放 Stage1 35 张与 Stage2 22 张和冻结金样零差异；无 `PROD` 指针变化。

- [ ] **Step 3: 执行数据库只读/失败注入/旧表保护检查**

运行测试套件并使用只读查询检查：`pretrade_snapshot_current` 只存在或更新 `DEV` 行；`archive_meta` 当前记录、16 张既有表的行数与步骤 2 前记录相同。运行在单元测试中已覆盖的断块、哈希、反序列化、日期不匹配和指针保留用例，不对正式库进行故障注入或删改。

```bash
/opt/homebrew/bin/python3 -m pytest -q tests/pretrade tests/pipeline/test_daily_runtime.py tests/scripts/test_run_pretrade_context.py tests/scripts/test_run_daily_pipeline.py
git diff --check
```

- [ ] **Step 4: 写证据并更新状态登记**

仅在步骤 1-3 全部成功后写入 JSON，字段固定为：

```json
{
  "baseline_commit": "579af695fb8727dec8249f66d07a8b0e723da137",
  "kernel_commit": "970ef6daa82dfb9fa4e458dd1da30f496ab26447",
  "manifest_id": "data_source_0123-20260710-v1",
  "business_date": "2026-07-10",
  "usage": "DEV",
  "snapshot_id": "<actual UUID>",
  "dataset_count": 27,
  "stage1_table_count": 35,
  "stage2_table_count": 22,
  "logical_fingerprint": "2efae81c46b55da9b8f6a6b848f71e6341b2584059e7f5108562e4cf9f554d85",
  "legacy_archive_dml": false,
  "prod_pointer_changed": false
}
```

在 `PRETRADE_DOCUMENT_STATUS.md` 标记“交易前 MVP 数据库上下文”已通过 `DEV` 零差异验收，但明确 `PROD` 日常接入、交易前服务、Wind 和页面未完成。提交：

```bash
git add docs/evidence/pretrade-db-context-20260710.json docs/PRETRADE_DOCUMENT_STATUS.md
git commit -m "test: record pretrade context dev parity"
```

### Task 8: 最终代码审计和交接门禁

**Files:**

- Modify: `docs/PRETRADE_DOCUMENT_STATUS.md` only if final commands are green.

**Interfaces:**

- Consumes: Tasks 1-7 的代码、测试和证据。
- Produces: 可进入“单券/一揽子共同内核服务与 on-the-fly Wind”设计阶段的明确门禁结论；不合并、不发布、不改页面。

- [ ] **Step 1: 执行全量相关测试**

Run:

```bash
/opt/homebrew/bin/python3 -m pytest -q tests/risk_core tests/pretrade tests/pipeline tests/scripts/test_run_pretrade_context.py tests/scripts/test_run_daily_pipeline.py tests/test_archive_db_write_batch_data_date.py tests/test_visualization_data_loader.py
```

Expected: 所有相关测试通过；没有把错误通过更新金样、跳过断言或改变业务基线掩盖。

- [ ] **Step 2: 静态边界审计**

Run:

```bash
rg -n "pickle|to_pickle|read_pickle|wind|Wind|display_snapshot|ArchiveDB\.write_batch|archive_meta.*(?:INSERT|UPDATE|DELETE)" src/pretrade src/pipeline/daily_runtime.py scripts/run_pretrade_context.py
rg -n "pretrade_" src/visualization scripts/generate_display_snapshot.py src/utils/archive_db.py
git diff --check
git status --short
```

Expected: `src/pretrade` 不含 pickle、Wind 或展示快照读取；除 `context_store.publish` 的只读 `archive_meta` 日期查询外不写旧归档表；既有展示代码不读取 `pretrade_`；工作树无未提交变更。

- [ ] **Step 3: 形成下一阶段输入，而非开始实现**

记录以下事实作为下一份设计的硬前提：`DEV` 上下文可数据库重放、共同内核零差异、在线服务必须只读 `PROD` pointer、未知账户拒绝、持仓债从快照取主数据、非持仓债使用 on-the-fly Wind 且缺字段不可计算。此任务只更新状态登记并提交，不创建服务、页面、Wind 客户端或 API。

```bash
git add docs/PRETRADE_DOCUMENT_STATUS.md
git commit -m "docs: gate pretrade service on context parity"
```

## Plan Self-Review

### Spec coverage

- 27 个完整共同内核输入、参数、同批数据日期、来源摘要、Parquet 分块、哈希和读回：Tasks 2-5。
- 与既有日常运行同一次、同进程捕获，不重新读展示结果或 Excel：Tasks 4 和 6。
- 既有 16 表、`archive_meta`、展示快照不变，展示/交易前日期不一致时拒绝交易前读取：Tasks 3、6 和 8。
- `DEV`/`PROD` 逻辑隔离、无额外账号/实例、PROD 发布日期守卫：Tasks 3、5-7。
- `data_source_0123` 真实运行、正式库 `DEV` 写入、35/22 内核重放零差异和旧表保护：Task 7。
- Wind 不落库、两个页面不在本阶段：Global Constraints、Out of Scope 和 Task 8。

### Placeholder scan

本计划的路径、接口、命令、错误条件和验收结果均已明确；没有把业务公式、Wind 字段映射或页面实现混入数据库上下文阶段。

### Type consistency

`ProductionKernelInput` 是跨任务唯一的计算输入类型；`PretradeSnapshotRequest` 是唯一写入请求类型；`PretradeContextStore` 是唯一 `pretrade_` 表访问层；`DailyRuntimeResult` 是唯一日常内存捕获载体。后续服务阶段只能读 `PretradeContextStore.load_kernel_input` 返回的 `ProductionKernelInput`。
