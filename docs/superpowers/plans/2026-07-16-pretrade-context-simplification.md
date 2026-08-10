# Minimal Pretrade Context Reset Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重置尚未被任何服务使用的新增 `pretrade_` 验收表，并以最少三张表保存可精确重放上线共同内核的交易前输入。

**Architecture:** 日常运行将 27 项共同内核输入编码为每项一条 Parquet `LONGBLOB`，在同一数据库事务内写入快照头和全部数据集。既有归档成功后，唯一 current 指针在一次短事务内验证该快照可读、验证 `archive_meta.data_date` 一致，再切换到该快照。冻结验收命令只写未发布快照并重放；没有 DEV/PROD、来源文件清单、分块、状态机、独立迁移程序或第二套业务规则。

**Tech Stack:** Python 3.14、pandas、pyarrow、SQLAlchemy、PyMySQL/MySQL、pytest。

## Global Constraints

- 上线业务基线为 GitHub `main@579af695fb8727dec8249f66d07a8b0e723da137`；不得修改 Stage0/Stage1/Stage2 的业务规则、阈值、`fillna`、路由或字段含义。
- 共同内核的 10/35/22 表与逻辑指纹 `2efae81c46b55da9b8f6a6b848f71e6341b2584059e7f5108562e4cf9f554d85` 必须保持零差异。
- 快照输入固定为 `STAGE1_REQUIRED_FRAMES ∪ STAGE2_REQUIRED_FRAMES` 的 27 项按序去重并集；不得保存展示长表、内核输出、交易输入或 Wind 数据。
- 仅新增并重置 `pretrade_snapshot`、`pretrade_snapshot_dataset`、`pretrade_snapshot_current`；不得修改 `archive_meta`、既有 16 张归档表、展示快照和既有页面。
- 现有四张 `pretrade_` 表仅含 4 个 `DEV/READY` 验收快照且 current 为 0；用户已明确授权重置这些新增验收表。历史验收结论保留在 `docs/evidence/pretrade-db-context-20260710.json`，不迁移旧表内数据。
- 不设置 T-1/T-2 新鲜度限制；唯一日期检查是 current 发布/读取时快照 `data_date == archive_meta.is_current.data_date`。
- 一项数据集只写一条 `LONGBLOB`。已验证最大数据集 1,318,315 字节、总载荷 2,286,987 字节；若将来超过数据库可承载大小，直接失败并停止发布，不恢复 chunk 表。
- 保留每项 payload SHA-256、Parquet schema 元数据、业务日期和监管集中度参数；删除 status、ready time、整体输入 hash、行数、payload 长度、usage、code commit、来源清单和所有版本字段。
- 生产日常只在 current 切换前做一次数据库读回验证；冻结验收额外重放共同内核。任何读回、hash、27 输入集合或日期检查失败都不能切 current。
- 本计划不实现 Wind、单券/篮子服务或两个页面。

## Target Database Contract

```text
pretrade_snapshot
  snapshot_id PK, data_date, regulatory_concentration_limit, captured_at

pretrade_snapshot_dataset
  (snapshot_id, dataset_code) PK, schema_json, payload_hash, payload LONGBLOB

pretrade_snapshot_current
  pointer_id PK (= 1), snapshot_id FK
```

`schema_json` 是无损恢复 pandas dtype、index 名称和 object 编码列的必要元数据；其余类型信息由固定的 `parquet-arrow-v1` 编解码器承担。`data_date` 从快照头表取得，current 表不重复保存日期或发布时间。

## File Structure

- Modify: `src/pretrade/frame_codec.py` — 删除分块、长度/行数/版本持久化字段；保留 Parquet、schema 与单载荷 hash。
- Modify: `src/pretrade/input_contract.py` — 只校验 27 输入集合并创建只含 `kernel_input` 的写入请求。
- Modify: `src/pretrade/context_store.py` — 三表 DDL、单载荷事务写入、唯一 current、读回与日期守卫。
- Modify: `src/pretrade/context_build.py` — 只捕获、写入和验收读回；不接受环境、来源或版本参数。
- Modify: `scripts/run_daily_pipeline.py` — 删除来源 hash/commit/usage，归档成功后调用 `publish_current`。
- Modify: `scripts/run_pretrade_context.py` — 删除 `--usage`、source manifest 与 DEV 文案；只创建未发布验收快照并重放。
- Modify: `tests/pretrade/test_frame_codec.py` — 固定单载荷和实际 object 类型的失败关闭边界。
- Modify: `tests/pretrade/test_input_contract.py` — 固定精简请求和 27 输入契约。
- Modify: `tests/pretrade/test_context_store.py` — 固定三表、单 current、事务回滚和日期守卫。
- Modify: `tests/pretrade/test_context_build.py` — 固定一次读回验证和共同内核重放。
- Modify: `tests/scripts/test_run_daily_pipeline.py` — 固定日常发布顺序。
- Modify: `tests/scripts/test_run_pretrade_context.py` — 删除环境 CLI 表面。
- Modify: `docs/PRETRADE_SHARED_CORE_SPEC.md` — 用本计划三表最小契约替换四表/环境/来源清单叙述。
- Modify: `docs/PRETRADE_DOCUMENT_STATUS.md` — 登记重置和精简后的唯一 current 模型。
- Create: `docs/evidence/pretrade-context-minimal-reset-20260710.json` — 重置后冻结数据验收成功才写入。

### Task 1: 固定最小输入和单载荷编解码契约

**Files:**
- Modify: `src/pretrade/frame_codec.py`
- Modify: `src/pretrade/input_contract.py`
- Modify: `tests/pretrade/test_frame_codec.py`
- Modify: `tests/pretrade/test_input_contract.py`

**Interfaces:**
- Consumes: `ProductionKernelInput`、27 项 `KERNEL_INPUT_DATASETS`、pandas DataFrame。
- Produces: `SerializedFrame(payload, payload_hash, schema_json)` 和 `PretradeSnapshotRequest(kernel_input)`。

- [ ] **Step 1: 写失败测试，固定不含环境和审计冗余字段的请求**

```python
def test_snapshot_request_contains_only_validated_kernel_input() -> None:
    request = PretradeSnapshotRequest.from_kernel_input(make_kernel_input())

    assert request.kernel_input.business_date.isoformat() == "2026-07-10T00:00:00"
    assert not hasattr(request, "usage")
    assert not hasattr(request, "input_hash")
    assert not hasattr(request, "source_manifest")

def test_snapshot_request_rejects_missing_or_extra_dataset() -> None:
    missing = make_all_kernel_frames()
    missing.pop(KERNEL_INPUT_DATASETS[-1])
    with pytest.raises(PretradeInputContractError, match="缺少共同内核输入"):
        PretradeSnapshotRequest.from_kernel_input(make_kernel_input(missing))

    extra = make_all_kernel_frames()
    extra["展示长表"] = pd.DataFrame({"值": [1]})
    with pytest.raises(PretradeInputContractError, match="未注册输入"):
        PretradeSnapshotRequest.from_kernel_input(make_kernel_input(extra))
```

为 object 列写测试：`str`、`int`、`float`、`bool`、`None`、`pd.NA`、`pd.NaT` 往返严格相等；`Decimal("1.2")` 和 `datetime.time(9, 0)` 必须抛 `FrameCodecError`，不得静默转换。

- [ ] **Step 2: 运行测试，确认旧接口失败**

Run:

```bash
/tmp/limitmonitor-pretrade-venv/bin/python -m pytest -q tests/pretrade/test_input_contract.py tests/pretrade/test_frame_codec.py
```

Expected: FAIL；旧请求仍要求 usage/source manifest，旧 `SerializedFrame` 仍带行数、长度和版本字段。

- [ ] **Step 3: 实现最小请求和编解码形状**

将请求固定为：

```python
@dataclass(frozen=True)
class PretradeSnapshotRequest:
    kernel_input: ProductionKernelInput

    @classmethod
    def from_kernel_input(cls, kernel_input: ProductionKernelInput) -> "PretradeSnapshotRequest":
        if not isinstance(kernel_input, ProductionKernelInput):
            raise PretradeInputContractError("kernel_input 必须是 ProductionKernelInput")
        _validate_frames(kernel_input)
        return cls(kernel_input=kernel_input)
```

将序列化结果固定为：

```python
@dataclass(frozen=True)
class SerializedFrame:
    payload: bytes
    payload_hash: str
    schema_json: str
```

删除 `split_payload`、`join_payload`、`MAX_CHUNK_SIZE_BYTES`、`row_count`、`payload_size_bytes` 和 `serializer_version`。`deserialize_frame` 必须先以 SHA-256 校验 `payload_hash`，再用固定 `parquet-arrow-v1` 解码。schema JSON 只保存 `columns`、`dtypes`、`index_name`、`tagged_object_column_positions`；删除未使用的 `index_dtype` 和 `object_cell_encoding`。

`_encode_object_cell` 只接受上述七类值；其他 object 单元格抛 `FrameCodecError`。这不会改变当前冻结输入：实际数据库验收样本的 object 单元格只有 `str`、`int`、`float`。

- [ ] **Step 4: 运行单元测试**

Run:

```bash
/tmp/limitmonitor-pretrade-venv/bin/python -m pytest -q tests/pretrade/test_input_contract.py tests/pretrade/test_frame_codec.py
```

Expected: PASS；27 输入集合不变，所有允许类型严格往返，未知 object 类型失败关闭。

- [ ] **Step 5: 提交**

```bash
git add src/pretrade/frame_codec.py src/pretrade/input_contract.py tests/pretrade/test_frame_codec.py tests/pretrade/test_input_contract.py
git commit -m "refactor: minimize pretrade input codec"
```

### Task 2: 实现三表快照、单 current 与一次发布前读回

**Files:**
- Modify: `src/pretrade/context_store.py`
- Modify: `src/pretrade/context_build.py`
- Modify: `tests/pretrade/test_context_store.py`
- Modify: `tests/pretrade/test_context_build.py`

**Interfaces:**
- Consumes: `PretradeSnapshotRequest`、`SerializedFrame`、SQLAlchemy `Engine`。
- Produces: `write_snapshot(request) -> UUID`、`load_kernel_input(snapshot_id)`、`publish_current(snapshot_id)`、`get_current_snapshot()`、`load_current_kernel_input()`。

- [ ] **Step 1: 写失败测试，固定三表和唯一指针**

```python
def test_prepare_schema_creates_only_the_minimal_three_tables(engine) -> None:
    PretradeContextStore(engine).prepare_schema()
    assert set(inspect(engine).get_table_names()) == {
        "pretrade_snapshot",
        "pretrade_snapshot_dataset",
        "pretrade_snapshot_current",
    }
    assert inspect(engine).get_pk_constraint("pretrade_snapshot_current")["constrained_columns"] == [
        "pointer_id"
    ]

def test_write_snapshot_stores_one_payload_for_each_input(engine, context_request) -> None:
    store = PretradeContextStore(engine)
    store.prepare_schema()
    snapshot_id = store.write_snapshot(context_request)
    rows = engine.connect().execute(text(
        "SELECT dataset_code, length(payload) FROM pretrade_snapshot_dataset "
        "WHERE snapshot_id = :snapshot_id"
    ), {"snapshot_id": str(snapshot_id)}).all()

    assert len(rows) == 27
    assert all(size > 0 for _, size in rows)
    _assert_kernel_input_equal(store.load_kernel_input(snapshot_id), context_request.kernel_input)
```

再写入测试：任一第 N 个数据集插入失败时 header 与 dataset 行都回滚；`publish_current` 会先读回 27 输入，且仅在 `archive_meta.is_current=1` 日期相等时更新 `pointer_id=1`；读取 current 时日期不同抛 `PretradeDataSyncError`。

- [ ] **Step 2: 运行测试，确认旧状态/分块模型失败**

Run:

```bash
/tmp/limitmonitor-pretrade-venv/bin/python -m pytest -q tests/pretrade/test_context_store.py tests/pretrade/test_context_build.py
```

Expected: FAIL；旧实现在四表中写 chunk、要求 usage，并暴露 status/READY API。

- [ ] **Step 3: 实现最小存储 API**

DDL 固定为：

```python
PRETRADE_SNAPSHOT = Table(
    "pretrade_snapshot", PRETRADE_METADATA,
    Column("snapshot_id", String(36), primary_key=True),
    Column("data_date", String(10), nullable=False),
    Column("regulatory_concentration_limit", Float, nullable=False),
    Column("captured_at", DateTime, nullable=False),
)
PRETRADE_SNAPSHOT_DATASET = Table(
    "pretrade_snapshot_dataset", PRETRADE_METADATA,
    Column("snapshot_id", String(36), ForeignKey("pretrade_snapshot.snapshot_id"), primary_key=True),
    Column("dataset_code", String(128), primary_key=True),
    Column("schema_json", Text, nullable=False),
    Column("payload_hash", String(64), nullable=False),
    Column("payload", LargeBinary().with_variant(MYSQL_LONGBLOB(), "mysql"), nullable=False),
)
PRETRADE_SNAPSHOT_CURRENT = Table(
    "pretrade_snapshot_current", PRETRADE_METADATA,
    Column("pointer_id", Integer, primary_key=True),
    Column("snapshot_id", String(36), ForeignKey("pretrade_snapshot.snapshot_id"), nullable=False),
)
```

`write_snapshot` 先在内存中序列化 27 帧，再在一个 `engine.begin()` 中插入一个 header 与 27 个 dataset 行；失败时整个事务回滚。`load_kernel_input` 必须精确验证 27 dataset code、每项 payload hash、schema 和 Parquet 可读性，再创建 `ProductionKernelInput`。

`publish_current(snapshot_id)` 必须在同一个 `engine.begin()` 内依次：调用 `_load_kernel_input(conn, snapshot_id)`、读取 `archive_meta.is_current=1`、比较 data date、upsert `pointer_id=1`。若数据库读回或日期校验失败，不移动 pointer。`get_current_snapshot()` 与 `load_current_kernel_input()` 也必须再次执行日期守卫。

`build_ready_context` 只捕获和调用 `write_snapshot`；冻结验收命令显式读回和重放。日常发布前的唯一读回由 `publish_current` 完成。删除 `prepare_schema()` 中的 `information_schema` 查询和所有 `ALTER TABLE`。

- [ ] **Step 4: 运行存储、重放和故障注入测试**

Run:

```bash
/tmp/limitmonitor-pretrade-venv/bin/python -m pytest -q tests/pretrade/test_context_store.py tests/pretrade/test_context_build.py
```

Expected: PASS；任一输入不完整或被篡改不能发布，日期错配不能读取，重放逻辑未修改。

- [ ] **Step 5: 提交**

```bash
git add src/pretrade/context_store.py src/pretrade/context_build.py tests/pretrade/test_context_store.py tests/pretrade/test_context_build.py
git commit -m "refactor: minimize pretrade snapshot store"
```

### Task 3: 收缩日常与冻结验收命令

**Files:**
- Modify: `scripts/run_daily_pipeline.py`
- Modify: `scripts/run_pretrade_context.py`
- Modify: `tests/scripts/test_run_daily_pipeline.py`
- Modify: `tests/scripts/test_run_pretrade_context.py`

**Interfaces:**
- Consumes: `build_ready_context(runtime, store) -> UUID` 与 `store.publish_current(snapshot_id)`。
- Produces: 日常顺序 `validate → runtime → write snapshot → archive → verify/publish current → display`；冻结验收只写入、读回、重放。

- [ ] **Step 1: 写失败测试，删除多余 CLI 和来源 hash**

```python
def test_frozen_context_cli_has_no_environment_or_publish_surface() -> None:
    destinations = {action.dest for action in runner._build_parser()._actions}
    assert "usage" not in destinations
    assert destinations.isdisjoint({"publish", "wind", "database_url"})

def test_daily_pipeline_publishes_the_single_current_pointer(monkeypatch) -> None:
    calls = _install_dependencies(monkeypatch)
    assert daily.main(["--archive-date", "2026-07-16"]) == 0
    assert calls == ["validate", "runtime", "build", "archive", "publish_current", "display"]
```

- [ ] **Step 2: 运行测试，确认旧运行表面失败**

Run:

```bash
/tmp/limitmonitor-pretrade-venv/bin/python -m pytest -q tests/scripts/test_run_pretrade_context.py tests/scripts/test_run_daily_pipeline.py
```

Expected: FAIL；旧命令仍暴露 `--usage`、source manifest hash 和 `publish(snapshot_id, "PROD")`。

- [ ] **Step 3: 实现最小运行表面**

从 `run_daily_pipeline.py` 删除 `csv`、`sha256`、`KERNEL_SOURCE_FILE_NAMES`、`_sha256_file`、`_source_manifest`、`_git_commit` 及其测试。日常核心调用只能是：

```python
snapshot_id = build_ready_context(runtime, store)
if archive_to_db(args.archive_date) != 0:
    return 1
store.publish_current(snapshot_id)
```

从 `run_pretrade_context.py` 删除 `--usage` 和 source manifest 构造；它必须调用 `build_ready_context(runtime, store)`、`verify_rehydrated_context`、`replay_kernel_from_snapshot`、`assert_replay_matches_runtime`，但不得发布 current。输出统一称为“验收快照”。

- [ ] **Step 4: 运行命令与运行期测试**

Run:

```bash
/tmp/limitmonitor-pretrade-venv/bin/python -m pytest -q tests/scripts/test_run_pretrade_context.py tests/scripts/test_run_daily_pipeline.py tests/pipeline/test_daily_runtime.py
```

Expected: PASS；归档失败不切 current，发布验证失败不生成展示快照，冻结验收永不切 current。

- [ ] **Step 5: 提交**

```bash
git add scripts/run_daily_pipeline.py scripts/run_pretrade_context.py tests/scripts/test_run_daily_pipeline.py tests/scripts/test_run_pretrade_context.py
git commit -m "refactor: minimize pretrade runtime flow"
```

### Task 4: 重置新增表、重新验收并更新权威文档

**Files:**
- Modify: `docs/PRETRADE_SHARED_CORE_SPEC.md`
- Modify: `docs/PRETRADE_DOCUMENT_STATUS.md`
- Create: `docs/evidence/pretrade-context-minimal-reset-20260710.json`

**Interfaces:**
- Consumes: Task 1–3 的代码、现有 `data_source_0123` 冻结金样、用户已授权的新增表重置。
- Produces: 新三表中的未发布验收快照、35/22 零差异重放证据；不建立 current，不运行正式归档。

- [ ] **Step 1: 更新权威文档，不修改业务口径**

将 `PRETRADE_SHARED_CORE_SPEC.md` 第 4.2–4.3、5.4、6.5 的四表、分块、usage、source manifest、版本和动态 DDL 描述替换为本计划 Target Database Contract。明确 current 是唯一指针，冻结验收快照不发布；发布/读取仍需 `archive_meta.data_date` 一致。将旧 DEV snapshot ID 标注为“重置前验收记录，仅以证据 JSON 追溯”。

- [ ] **Step 2: 重置前只读确认**

Run:

```bash
/tmp/limitmonitor-pretrade-venv/bin/python - <<'PY'
import os, re
from pathlib import Path
from sqlalchemy import text
from src.utils.archive_db import ArchiveDB

values = {}
for line in Path('/Users/dellawang/Desktop/LimitMonitorBackup/new.txt').read_text(encoding='utf-8').splitlines():
    match = re.fullmatch(r'\s*(?:export\s+|set\s+)?(DB_[A-Z]+)\s*=\s*(.*?)\s*', line)
    if match:
        values[match.group(1)] = match.group(2).strip('"\'')
os.environ.update(values)
with ArchiveDB.from_env().engine.connect() as conn:
    print({
        'snapshot_count': conn.execute(text('SELECT COUNT(*) FROM pretrade_snapshot')).scalar_one(),
        'current_count': conn.execute(text('SELECT COUNT(*) FROM pretrade_snapshot_current')).scalar_one(),
    })
PY
```

Expected: `snapshot_count=4`、`current_count=0`。若任一数值不同，停止，不执行重置。

- [ ] **Step 3: 执行仅针对新增表的授权重置**

Run:

```bash
/tmp/limitmonitor-pretrade-venv/bin/python - <<'PY'
import os, re
from pathlib import Path
from sqlalchemy import text
from src.utils.archive_db import ArchiveDB

values = {}
for line in Path('/Users/dellawang/Desktop/LimitMonitorBackup/new.txt').read_text(encoding='utf-8').splitlines():
    match = re.fullmatch(r'\s*(?:export\s+|set\s+)?(DB_[A-Z]+)\s*=\s*(.*?)\s*', line)
    if match:
        values[match.group(1)] = match.group(2).strip('"\'')
os.environ.update(values)
with ArchiveDB.from_env().engine.begin() as conn:
    for table_name in (
        'pretrade_snapshot_current',
        'pretrade_snapshot_dataset_chunk',
        'pretrade_snapshot_dataset',
        'pretrade_snapshot',
    ):
        conn.execute(text(f'DROP TABLE IF EXISTS `{table_name}`'))
PY
```

Expected: 只删除四张新增 `pretrade_` 表；不读取、不写 `archive_meta` 或既有归档表。随后由 `run_pretrade_context.py` 的 `prepare_schema()` 创建目标三表。

- [ ] **Step 4: 用冻结数据创建未发布验收快照并运行全量测试**

Run:

```bash
ENV=test LIMIT_MONITOR_PROFILE=local /tmp/limitmonitor-pretrade-venv/bin/python scripts/run_pretrade_context.py \
  --input-root /Users/dellawang/Desktop/LimitMonitorAutomation/data_source_0123 \
  --manifest config/test_manifests/data_source_0123-20260710-v1.json \
  --allow-output-root /Users/dellawang/Desktop/LimitMonitorAutomation-test-output \
  --output /Users/dellawang/Desktop/LimitMonitorAutomation-test-output/pretrade-context-minimal-20260710 \
  --note "minimal-context reset acceptance"
/tmp/limitmonitor-pretrade-venv/bin/python -m pytest -q
git diff --check
```

Expected: 创建一个新的、未发布的三表验收快照；数据库重放 Stage1/Stage2 为 35/22 表且零差异；全量测试通过；`pretrade_snapshot_current` 仍为 0 行。

- [ ] **Step 5: 写证据、更新状态并提交**

证据 JSON 必须包含：`baseline_commit`、`kernel_commit`、`business_date`、`reset_authorized:true`、`dataset_count:27`、`stage1_table_count:35`、`stage2_table_count:22`、`logical_fingerprint`、`current_pointer_changed:false`、`legacy_archive_dml:false`。

Run:

```bash
git add docs/PRETRADE_SHARED_CORE_SPEC.md docs/PRETRADE_DOCUMENT_STATUS.md docs/evidence/pretrade-context-minimal-reset-20260710.json
git commit -m "test: record minimal pretrade context reset parity"
```

## Plan Self-Review

### Spec coverage

- 单库、单 current、无 DEV/PROD：Tasks 2–3。
- 仅三张新增表、无分块/状态/来源哈希/版本冗余：Tasks 1–2。
- 27 项输入、无损解码、交易前业务内核不变：Tasks 1–2、Task 4。
- 数据库 readback 与 `archive_meta` 日期保险：Task 2。
- 已授权的新增表重置、重新冻结验收、旧归档保护：Task 4。
- Wind、服务、页面不在本阶段：Global Constraints。

### Placeholder scan

本计划没有 TBD/TODO、通用迁移程序或未定义接口。唯一破坏性命令已精确限定为用户已授权的四张 `pretrade_` 新增表，且前置计数必须为 4 个验收快照、0 个 current。

### Type consistency

`PretradeSnapshotRequest` 只承载 `ProductionKernelInput`；`SerializedFrame` 只承载 `payload`、`payload_hash`、`schema_json`；`PretradeContextStore.publish_current(snapshot_id)` 是唯一发布 API；日常与未来服务均只通过无参 `get_current_snapshot()` 获取唯一 current。

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-16-pretrade-context-simplification.md`. Execute inline in this session, task by task. The only destructive step is Task 4 Step 3, which is already authorized but must still be preceded by the exact read-only count check in Task 4 Step 2.
