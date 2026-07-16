# Pretrade Context Simplification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将交易前数据库上下文收缩为与既有归档相同的单库、单当前版本模型，同时保留 27 项共同内核输入的无损数据库重放和与既有归档的数据日期一致性保险。

**Architecture:** 新模型只保留不可变快照头、每项输入的一行 Parquet `LONGBLOB` 载荷，以及唯一 current 指针三张表。日常运行成功后切换唯一指针；冻结验证运行只创建 `READY` 快照，不自动切换。既有 `archive_meta`、16 张归档表、展示快照和 Stage0/1/2 业务计算完全不改。

**Tech Stack:** Python 3.14、pandas、pyarrow、SQLAlchemy、PyMySQL/MySQL、pytest。

## Global Constraints

- 上线业务基线仍是 GitHub `main@579af695fb8727dec8249f66d07a8b0e723da137`；不得修改 Stage0/Stage1/Stage2 的业务规则、阈值、`fillna`、路由或字段含义。
- 共同内核候选 `970ef6daa82dfb9fa4e458dd1da30f496ab26447` 的 10/35/22 表和逻辑指纹 `2efae81c46b55da9b8f6a6b848f71e6341b2584059e7f5108562e4cf9f554d85` 是零差异基线。
- 交易前快照继续保存 `STAGE1_REQUIRED_FRAMES ∪ STAGE2_REQUIRED_FRAMES` 的 27 个按序去重输入；不得保存展示长表、内核输出或第二套限额事实。
- 取消 `DEV`/`PROD` 运行时隔离：所有快照在同一命名空间；验证命令不切 current，日常完整运行自动切唯一 current；人工需要时可显式发布已验证的 `READY` 快照。
- 保留 `archive_meta.is_current` 的 `data_date` 守卫。它只防止两次独立事务部分成功，不是 T-1/T-2、新鲜度或 Wind 日期门槛。
- 删除原始文件全量哈希、静态发行人映射摘要、`engine_version`、`input_contract_version`、`source_manifest_*` 和 `usage`；保留 `code_commit`、`input_hash`、每数据集载荷 hash、schema、行数和 Parquet 编码版本。
- 每个数据集只保存一条 `LONGBLOB`；本次验收最大载荷为 1,318,315 字节，27 表总载荷为 2,286,987 字节。若未来单数据集超过数据库允许载荷，明确失败并人工处理，不恢复分块表。
- 数据库迁移只处理 `pretrade_` 新增表，必须保留现有 `READY` 快照可读；不得修改 `archive_meta`、既有 16 张归档表或展示读路径。
- 非持仓债 Wind 仍不在本阶段实现、不落库；两个新增页面仍不在本阶段实现。

## Target Database Contract

```text
pretrade_snapshot
  snapshot_id PK, data_date, status, regulatory_concentration_limit,
  code_commit, input_hash, created_at, ready_at

pretrade_snapshot_dataset
  (snapshot_id, dataset_code) PK, content_hash, schema_json,
  row_count, serializer_version, payload LONGBLOB

pretrade_snapshot_current
  pointer_id PK (= 1), snapshot_id FK, published_at
```

`data_date` 从 `pretrade_snapshot` 获取，不在 current 表重复保存。`serializer_version` 保留在数据集表，因为读取端必须拒绝未知编码；`payload_size_bytes` 从 `OCTET_LENGTH(payload)` 或 Python `len(payload)` 得出，不单独存储。

## File Structure

- Modify: `src/pretrade/input_contract.py` — 移除 usage、来源清单和固定版本字段，保留 27 表校验和输入 hash。
- Modify: `src/pretrade/context_store.py` — 三表 DDL、单载荷读写、单 current 指针、日期守卫；不在日常路径执行 DDL 迁移。
- Modify: `src/pretrade/context_build.py` — 构建函数不再接受 usage/source manifest/engine contract 版本。
- Modify: `scripts/run_daily_pipeline.py` — 删除原文件哈希和 usage 参数，成功归档后调用 `publish_current(snapshot_id)`。
- Modify: `scripts/run_pretrade_context.py` — 冻结验收仅创建并重放 `READY` 快照，删除 `--usage` 与来源清单写入。
- Create: `scripts/migrate_pretrade_context_schema.py` — 只可显式执行的、先 dry-run 后 apply 的一次性数据库迁移。
- Modify: `tests/pretrade/test_input_contract.py` — 固定精简请求契约。
- Modify: `tests/pretrade/test_context_store.py` — 固定三表、单载荷、唯一 pointer、日期守卫和旧快照迁移后可读。
- Modify: `tests/pretrade/test_context_build.py` — 调整构建调用形状，不改变重放差分。
- Modify: `tests/scripts/test_run_pretrade_context.py` — 移除 DEV/PROD CLI 表面。
- Modify: `tests/scripts/test_run_daily_pipeline.py` — 移除来源清单和 usage，验证唯一 current 发布顺序。
- Create: `tests/scripts/test_migrate_pretrade_context_schema.py` — 覆盖 dry-run、单载荷迁移、hash 校验失败和 current 迁移选择。
- Modify: `docs/PRETRADE_SHARED_CORE_SPEC.md` — 将四表/usage/source manifest 表述替换为本计划三表单 current 契约。
- Modify: `docs/PRETRADE_DOCUMENT_STATUS.md` — 登记新契约；明确旧 DEV 快照为迁移前验收证据而非环境隔离模型。

### Task 1: 固定精简契约和单 current API

**Files:**
- Modify: `src/pretrade/input_contract.py`
- Modify: `src/pretrade/context_build.py`
- Modify: `tests/pretrade/test_input_contract.py`
- Modify: `tests/pretrade/test_context_build.py`

**Interfaces:**
- Consumes: `ProductionKernelInput`、`KERNEL_INPUT_DATASETS`。
- Produces: `PretradeSnapshotRequest.from_kernel_input(kernel_input, *, code_commit="")` 和 `build_ready_context(runtime, store, *, code_commit="") -> UUID`。

- [ ] **Step 1: 写失败测试，禁止环境与来源清单进入请求契约**

```python
def test_snapshot_request_needs_only_kernel_input_and_optional_commit() -> None:
    request = PretradeSnapshotRequest.from_kernel_input(
        make_kernel_input(), code_commit="test-commit"
    )

    assert request.code_commit == "test-commit"
    assert request.input_hash
    assert not hasattr(request, "usage")
    assert not hasattr(request, "source_manifest")

def test_snapshot_request_hash_still_changes_when_input_changes() -> None:
    original = PretradeSnapshotRequest.from_kernel_input(make_kernel_input())
    changed_frames = make_all_kernel_frames()
    changed_frames[KERNEL_INPUT_DATASETS[0]].loc[0, "值"] = 999
    changed = PretradeSnapshotRequest.from_kernel_input(make_kernel_input(changed_frames))

    assert original.input_hash != changed.input_hash
```

- [ ] **Step 2: 运行测试，确认旧 API 失败**

Run:

```bash
/tmp/limitmonitor-pretrade-venv/bin/python -m pytest -q tests/pretrade/test_input_contract.py tests/pretrade/test_context_build.py
```

Expected: FAIL；旧 `usage` 和 `source_manifest` 仍是必填参数。

- [ ] **Step 3: 实现最小请求与构建接口**

将 `PretradeSnapshotRequest` 固定为：

```python
@dataclass(frozen=True)
class PretradeSnapshotRequest:
    kernel_input: ProductionKernelInput
    code_commit: str
    input_hash: str

    @classmethod
    def from_kernel_input(
        cls, kernel_input: ProductionKernelInput, *, code_commit: str = ""
    ) -> "PretradeSnapshotRequest":
        if not isinstance(kernel_input, ProductionKernelInput):
            raise PretradeInputContractError("kernel_input 必须是 ProductionKernelInput")
        _validate_frames(kernel_input)
        return cls(kernel_input=kernel_input, code_commit=code_commit,
                   input_hash=_build_input_hash(kernel_input))
```

删除 `ALLOWED_USAGES`、`_validate_source_manifest`、来源清单 canonical JSON 和请求中的 `engine_version`、`input_contract_version`。`_build_input_hash` 的 27 表顺序与监管参数必须不变。

将构建函数改为：

```python
def build_ready_context(
    runtime: Any, store: PretradeContextStore, *, code_commit: str = ""
) -> UUID:
    kernel_input = capture_production_kernel_input(runtime.stage1_processor, runtime.stage2_processor)
    snapshot_id = store.write_ready_snapshot(
        PretradeSnapshotRequest.from_kernel_input(kernel_input, code_commit=code_commit)
    )
    verify_rehydrated_context(store, snapshot_id, kernel_input)
    return snapshot_id
```

- [ ] **Step 4: 运行契约与共同内核重放测试**

Run:

```bash
/tmp/limitmonitor-pretrade-venv/bin/python -m pytest -q tests/pretrade/test_input_contract.py tests/pretrade/test_context_build.py
```

Expected: PASS；27 输入集合、输入 hash 和读回严格等值测试继续通过。

- [ ] **Step 5: 提交**

```bash
git add src/pretrade/input_contract.py src/pretrade/context_build.py tests/pretrade/test_input_contract.py tests/pretrade/test_context_build.py
git commit -m "refactor: simplify pretrade snapshot request"
```

### Task 2: 用三表单载荷实现快照存储与唯一 current 指针

**Files:**
- Modify: `src/pretrade/context_store.py`
- Modify: `src/pretrade/frame_codec.py`
- Modify: `tests/pretrade/test_context_store.py`
- Modify: `tests/pretrade/test_frame_codec.py`

**Interfaces:**
- Consumes: 精简后的 `PretradeSnapshotRequest`、`SerializedFrame`、SQLAlchemy `Engine`。
- Produces: `write_ready_snapshot(request)`, `load_kernel_input(snapshot_id)`, `get_current_snapshot()`, `load_current_kernel_input()`, `publish_current(snapshot_id)`。

- [ ] **Step 1: 写失败测试，固定三表与单载荷形状**

```python
def test_prepare_schema_creates_only_three_pretrade_tables(engine) -> None:
    store = PretradeContextStore(engine)
    store.prepare_schema()

    assert set(inspect(engine).get_table_names()) == {
        "pretrade_snapshot",
        "pretrade_snapshot_dataset",
        "pretrade_snapshot_current",
    }
    assert inspect(engine).get_pk_constraint("pretrade_snapshot_current")["constrained_columns"] == [
        "pointer_id"
    ]

def test_ready_snapshot_stores_exactly_one_payload_per_dataset(engine, context_request) -> None:
    store = PretradeContextStore(engine)
    store.prepare_schema()
    snapshot_id = store.write_ready_snapshot(context_request)

    rows = engine.connect().execute(text(
        "SELECT dataset_code, length(payload) FROM pretrade_snapshot_dataset "
        "WHERE snapshot_id = :snapshot_id"
    ), {"snapshot_id": str(snapshot_id)}).all()
    assert len(rows) == 27
    assert all(size > 0 for _, size in rows)
```

再写入：`publish_current` 在 `archive_meta` 缺失、日期不同、快照非 `READY` 时失败；日期一致时将 `pointer_id=1` 指向该快照；`get_current_snapshot()` 在归档之后被其他进程切换到不同 `data_date` 时抛 `PretradeDataSyncError`。

- [ ] **Step 2: 运行测试，确认旧四表/分块实现失败**

Run:

```bash
/tmp/limitmonitor-pretrade-venv/bin/python -m pytest -q tests/pretrade/test_context_store.py tests/pretrade/test_frame_codec.py
```

Expected: FAIL；当前实现创建 chunk 表、要求 usage，且不能提供无参 current API。

- [ ] **Step 3: 实现最小三表 DDL 和读写路径**

将表字段固定为：

```python
PRETRADE_SNAPSHOT = Table(
    "pretrade_snapshot", PRETRADE_METADATA,
    Column("snapshot_id", String(36), primary_key=True),
    Column("data_date", String(10), nullable=False),
    Column("status", String(16), nullable=False),
    Column("regulatory_concentration_limit", Float, nullable=False),
    Column("code_commit", String(128), nullable=False),
    Column("input_hash", String(64), nullable=False),
    Column("created_at", DateTime, nullable=False),
    Column("ready_at", DateTime, nullable=True),
)
PRETRADE_SNAPSHOT_DATASET = Table(
    "pretrade_snapshot_dataset", PRETRADE_METADATA,
    Column("snapshot_id", String(36), ForeignKey("pretrade_snapshot.snapshot_id"), primary_key=True),
    Column("dataset_code", String(128), primary_key=True),
    Column("content_hash", String(64), nullable=False),
    Column("schema_json", Text, nullable=False),
    Column("row_count", BigInteger, nullable=False),
    Column("serializer_version", String(64), nullable=False),
    Column("payload", LargeBinary().with_variant(MYSQL_LONGBLOB(), "mysql"), nullable=False),
)
PRETRADE_SNAPSHOT_CURRENT = Table(
    "pretrade_snapshot_current", PRETRADE_METADATA,
    Column("pointer_id", Integer, primary_key=True),
    Column("snapshot_id", String(36), ForeignKey("pretrade_snapshot.snapshot_id"), nullable=False),
    Column("published_at", DateTime, nullable=False),
)
```

删除 `split_payload`、`join_payload`、`MAX_CHUNK_SIZE_BYTES` 及所有 chunk ordinal 校验。写入时每个 `SerializedFrame.payload` 直接写到 `pretrade_snapshot_dataset.payload`；读取时直接构造 `SerializedFrame`，其中 `payload_size_bytes=len(bytes(dataset["payload"]))`。保留现有类型化 object 编解码，不在本计划缩减其支持类型。

`publish_current(snapshot_id)` 只允许 `READY` 快照；它读取 `archive_meta.is_current=1` 的 `data_date` 并与快照比较，一致后 upsert `pointer_id=1`。`get_current_snapshot()` 通过 `pointer_id=1` 取快照并再次做同一日期检查。`load_current_kernel_input()` 只能调用 `get_current_snapshot()` 后的 `load_kernel_input()`。

`prepare_schema()` 只能 `create_all()`，不得再查询 `information_schema` 或执行 `ALTER TABLE`。

- [ ] **Step 4: 运行存储、编解码和故障注入测试**

Run:

```bash
/tmp/limitmonitor-pretrade-venv/bin/python -m pytest -q tests/pretrade/test_context_store.py tests/pretrade/test_frame_codec.py
```

Expected: PASS；输入/输出类型严格相等，任意数据集写入失败整体回滚，旧 current 保留，当前指针与归档日期不同则拒绝读取。

- [ ] **Step 5: 提交**

```bash
git add src/pretrade/context_store.py src/pretrade/frame_codec.py tests/pretrade/test_context_store.py tests/pretrade/test_frame_codec.py
git commit -m "refactor: collapse pretrade context to three tables"
```

### Task 3: 建立一次性、保留数据的数据库迁移

**Files:**
- Create: `scripts/migrate_pretrade_context_schema.py`
- Create: `tests/scripts/test_migrate_pretrade_context_schema.py`

**Interfaces:**
- Consumes: 旧四表 schema 的 `READY`/`LOADING` 快照和分块 payload。
- Produces: 目标三表 schema；每个旧数据集的拼接 payload、hash、schema、行数完全保留；单一 current 指针只在人工指定或旧表恰有一行时迁移。

- [ ] **Step 1: 写失败测试，固定迁移前置条件和保留规则**

```python
def test_migration_dry_run_never_executes_ddl_or_dml(engine_with_legacy_context) -> None:
    report = migrate_pretrade_context_schema(engine_with_legacy_context, apply=False)

    assert report.mode == "dry-run"
    assert report.snapshot_count == 1
    assert report.dataset_count == 27
    assert "pretrade_snapshot_dataset_chunk" in inspect(engine_with_legacy_context).get_table_names()

def test_migration_rejects_multiple_legacy_current_rows_without_choice(engine_with_two_currents) -> None:
    with pytest.raises(MigrationError, match="多个旧 current"):
        migrate_pretrade_context_schema(engine_with_two_currents, apply=True)

def test_migration_copies_joined_payload_and_preserves_hash(engine_with_legacy_context) -> None:
    report = migrate_pretrade_context_schema(engine_with_legacy_context, apply=True)

    assert report.snapshot_count == 1
    assert PretradeContextStore(engine_with_legacy_context).load_kernel_input(report.snapshot_ids[0])
```

- [ ] **Step 2: 运行测试，确认迁移脚本尚不存在**

Run:

```bash
/tmp/limitmonitor-pretrade-venv/bin/python -m pytest -q tests/scripts/test_migrate_pretrade_context_schema.py
```

Expected: FAIL；`migrate_pretrade_context_schema` 尚未定义。

- [ ] **Step 3: 实现仅显式触发的迁移命令**

实现：

```python
def migrate_pretrade_context_schema(
    engine: Engine, *, apply: bool, current_snapshot_id: str | None = None
) -> MigrationReport: ...
```

迁移顺序必须严格为：

1. 反射旧四表，读取所有快照、数据集元数据和按 `(snapshot_id, dataset_code, chunk_ordinal)` 排序的 chunks；拼接 payload 后验证旧 `content_hash` 与 `payload_size_bytes`；任一失败立即终止，未执行 DDL。
2. `apply=False` 只返回计数、候选 current 和每数据集 hash 校验结果，不写数据库。
3. `apply=True` 时，在显式维护窗口内为 `pretrade_snapshot_dataset` 增加 nullable `payload LONGBLOB`，逐行写入已校验 payload，再逐行重新读出并验证 hash。
4. 读取旧 current：0 行则新 current 保持空；1 行则迁移其 snapshot；超过 1 行时仅接受与旧行之一匹配的 `current_snapshot_id`，否则失败。不得擅自选择 DEV 或 PROD。
5. 只有全部 payload 已验证后，删除旧 `pretrade_snapshot_dataset_chunk`；删除 header 的 `usage`、来源清单、固定 engine/contract 版本字段；删除 dataset 的 `payload_size_bytes`；重建 `pretrade_snapshot_current` 为 `pointer_id=1` 的单行结构。
6. 用新 `PretradeContextStore.load_kernel_input()` 逐快照读回 27 项输入，并比较每项 `input_hash`。任一读回失败必须报告迁移失败，且禁止运行日常编排器；不得触碰既有归档表。

MySQL 的 DDL 会隐式提交，因此迁移不能声称整体事务回滚。脚本必须支持安全重跑：若发现 dataset 表已含 `payload`，只校验并补写 `payload IS NULL` 的行；只要 chunk 表仍存在就保留它；仅当所有历史数据集的单载荷 hash 都通过时才删除 chunk 表和旧列。每个阶段开始和结束都重新检查快照数、数据集数、payload hash；任一步中断后再次 `--dry-run` 必须能报告当前阶段，且不得调用日常编排器。

CLI 只接受：

```bash
python scripts/migrate_pretrade_context_schema.py --dry-run
python scripts/migrate_pretrade_context_schema.py --apply [--current-snapshot-id <uuid>]
```

`--apply` 前必须打印快照数、数据集数、旧 current 行数和候选 UUID；不得打印数据库凭据或 payload。

- [ ] **Step 4: 运行迁移单测与静态边界审计**

Run:

```bash
/tmp/limitmonitor-pretrade-venv/bin/python -m pytest -q tests/scripts/test_migrate_pretrade_context_schema.py tests/pretrade/test_context_store.py
rg -n "archive_meta.*(?:INSERT|UPDATE|DELETE)|ArchiveDB\.write_batch|display_snapshot|Wind" scripts/migrate_pretrade_context_schema.py src/pretrade
```

Expected: PASS；扫描没有旧归档写入、展示读取或 Wind 调用。

- [ ] **Step 5: 提交**

```bash
git add scripts/migrate_pretrade_context_schema.py tests/scripts/test_migrate_pretrade_context_schema.py
git commit -m "feat: add explicit pretrade context migration"
```

### Task 4: 收缩日常与冻结验收命令的运行时职责

**Files:**
- Modify: `scripts/run_daily_pipeline.py`
- Modify: `scripts/run_pretrade_context.py`
- Modify: `tests/scripts/test_run_daily_pipeline.py`
- Modify: `tests/scripts/test_run_pretrade_context.py`

**Interfaces:**
- Consumes: 精简 `build_ready_context()` 和 `publish_current()`。
- Produces: 日常顺序 `validate → runtime → build READY → archive → publish current → display`；冻结验收只写 READY 并重放，不发布。

- [ ] **Step 1: 写失败测试，删除环境/来源清单表面**

```python
def test_frozen_context_cli_has_no_usage_or_publish_surface() -> None:
    destinations = {action.dest for action in runner._build_parser()._actions}
    assert "usage" not in destinations
    assert destinations.isdisjoint({"publish", "wind", "database_url"})

def test_daily_pipeline_publishes_the_single_current_pointer(monkeypatch) -> None:
    calls = _install_dependencies(monkeypatch)
    assert daily.main(["--archive-date", "2026-07-16"]) == 0
    assert calls == ["validate", "runtime", "build", "archive", "publish_current", "display"]
```

- [ ] **Step 2: 运行脚本测试，确认旧 API 失败**

Run:

```bash
/tmp/limitmonitor-pretrade-venv/bin/python -m pytest -q tests/scripts/test_run_pretrade_context.py tests/scripts/test_run_daily_pipeline.py
```

Expected: FAIL；旧 CLI 暴露 `--usage`，日常调用 `publish(snapshot_id, "PROD")`，并计算来源文件 hash。

- [ ] **Step 3: 实现最小命令表面**

从 `run_daily_pipeline.py` 删除 `csv`、`sha256`、`KERNEL_SOURCE_FILE_NAMES`、`_sha256_file`、`_source_manifest` 及相关测试；保留 `_git_commit()`。调用形状固定为：

```python
snapshot_id = build_ready_context(runtime, store, code_commit=_git_commit())
if archive_to_db(args.archive_date) != 0:
    return 1
store.publish_current(snapshot_id)
```

从 `run_pretrade_context.py` 删除 `--usage` 参数、来源清单构造及 `usage="DEV"`；它只调用 `build_ready_context(..., code_commit=_git_commit())`、数据库读回和共同内核重放。命令输出称为“验收快照”，不能称为 DEV 快照。

- [ ] **Step 4: 运行脚本测试**

Run:

```bash
/tmp/limitmonitor-pretrade-venv/bin/python -m pytest -q tests/scripts/test_run_pretrade_context.py tests/scripts/test_run_daily_pipeline.py tests/pipeline/test_daily_runtime.py
```

Expected: PASS；归档失败不切 current，发布失败不生成展示快照，冻结验收永不切 current。

- [ ] **Step 5: 提交**

```bash
git add scripts/run_daily_pipeline.py scripts/run_pretrade_context.py tests/scripts/test_run_daily_pipeline.py tests/scripts/test_run_pretrade_context.py
git commit -m "refactor: simplify pretrade runtime publishing"
```

### Task 5: 更新权威文档并完成迁移前后验收

**Files:**
- Modify: `docs/PRETRADE_SHARED_CORE_SPEC.md`
- Modify: `docs/PRETRADE_DOCUMENT_STATUS.md`
- Create: `docs/evidence/pretrade-context-simplification-20260710.json`

**Interfaces:**
- Consumes: Task 1–4 的三表代码、迁移报告、现有 `data_source_0123` 金样。
- Produces: 可审计的简化契约和迁移验收结果；不实现服务、Wind 或页面。

- [ ] **Step 1: 更新规格，但不改业务章节**

将 `PRETRADE_SHARED_CORE_SPEC.md` 中四表、`DEV`/`PROD`、source manifest、分块和动态 LONGBLOB 迁移表述替换为本计划 Target Database Contract。明确：验证快照是“不发布的 READY 快照”，而非数据库环境；current 是唯一人工/日常可切换指针。保留 `archive_meta.data_date` 发布和读取保险。

- [ ] **Step 2: 在正式库先运行迁移 dry-run 并人工确认**

Run:

```bash
/tmp/limitmonitor-pretrade-venv/bin/python scripts/migrate_pretrade_context_schema.py --dry-run
```

Expected: 只输出旧快照数、27 数据集数、payload hash 检查、旧 current 行数和候选 UUID；不执行 DDL/DML。此处停止，等待人工确认后才允许 `--apply`。

- [ ] **Step 3: 获得明确授权后执行迁移并重放历史验收快照**

Run:

```bash
/tmp/limitmonitor-pretrade-venv/bin/python scripts/migrate_pretrade_context_schema.py --apply
/tmp/limitmonitor-pretrade-venv/bin/python - <<'PY'
from src.pretrade.context_build import replay_kernel_from_snapshot
from src.pretrade.context_store import PretradeContextStore
from src.utils.archive_db import ArchiveDB

snapshot_id = "15b9eec7-c20f-41d9-908c-2c07c240b112"
result = replay_kernel_from_snapshot(PretradeContextStore(ArchiveDB.from_env().engine), snapshot_id)
assert len(result.stage1_tables) == 35
assert len(result.stage2_tables) == 22
PY
```

Expected: 迁移后的历史快照仍可读取并重放 35/22 表；不移动唯一 current，既有 `archive_meta` 和 16 表不变。

- [ ] **Step 4: 用冻结数据创建新的未发布验收快照并做完整测试**

Run:

```bash
ENV=test LIMIT_MONITOR_PROFILE=local /tmp/limitmonitor-pretrade-venv/bin/python scripts/run_pretrade_context.py \
  --input-root /Users/dellawang/Desktop/LimitMonitorAutomation/data_source_0123 \
  --manifest config/test_manifests/data_source_0123-20260710-v1.json \
  --allow-output-root /Users/dellawang/Desktop/LimitMonitorAutomation-test-output \
  --output /Users/dellawang/Desktop/LimitMonitorAutomation-test-output/pretrade-context-simplified-20260710 \
  --note "simplified-context acceptance"
/tmp/limitmonitor-pretrade-venv/bin/python -m pytest -q
git diff --check
```

Expected: 新验收快照不切 current；35/22 重放与金样零差异；全量测试通过；工作树只有文档待提交。

- [ ] **Step 5: 写证据、更新状态并提交**

证据 JSON 固定包含：`baseline_commit`、`kernel_commit`、`business_date`、`legacy_snapshot_id`、`simplified_snapshot_id`、`dataset_count`、`stage1_table_count`、`stage2_table_count`、`logical_fingerprint`、`current_pointer_changed:false`、`legacy_archive_dml:false`。

Run:

```bash
git add docs/PRETRADE_SHARED_CORE_SPEC.md docs/PRETRADE_DOCUMENT_STATUS.md docs/evidence/pretrade-context-simplification-20260710.json
git commit -m "docs: record simplified pretrade context parity"
```

## Plan Self-Review

### Spec coverage

- 单库、单 current、人工判断、无 DEV/PROD：Tasks 1、2、4。
- 三表单载荷和删除分块：Tasks 2、3。
- 保留既有 READY 快照和不触碰归档表：Task 3、Task 5。
- 删除运行期文件哈希与冗余版本字段：Tasks 1、4。
- 27 输入、无损重放、哈希、日期保险和业务基线不变：Tasks 1、2、5。
- 不实现 Wind、服务或页面：Global Constraints、Task 5。

### Placeholder scan

本计划没有 TBD/TODO、模糊的“适当处理”步骤或未定义接口；迁移前的人工授权点明确限制在会产生 DDL/DML 的 `--apply` 命令。

### Type consistency

`PretradeSnapshotRequest` 不再含 usage/source manifest；`PretradeContextStore.publish_current(snapshot_id)` 是唯一发布接口；日常编排和未来服务都通过无参 `get_current_snapshot()` 读取唯一 current。`serializer_version` 仅属于 `SerializedFrame` 和数据集行，未在快照头或请求中重复存储。

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-16-pretrade-context-simplification.md`. Two execution options:

1. **Subagent-Driven** — 按任务派发并逐项复核；
2. **Inline Execution** — 在本会话按任务顺序执行，并在数据库迁移 `--apply` 前暂停等待明确授权。
