# 原始限额配置工作簿审计附件 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** 每份已发布交易前快照保存当日实际使用的 限额配置_当前.xlsx 原件，审计可按快照逐字节回查，且不改变 Stage0/1/2 业务计算及 Wind 不落库边界。

**Architecture:** 先统一 Stage1 的“系统参数”与其余配置 sheet 的路径，使其全部使用 Stage1Processor.config；这不改变任何限额算法。随后保持 27 份共同内核输入和三张原有 pretrade 计算表不变，新增一张与 pretrade_snapshot 一对一关联的 pretrade_config_workbook 表，保存原始 xlsx 字节、文件名和 SHA-256。该附件在同一事务写入、发布 current 前验证，但不传给共同内核。

**Tech Stack:** Python 3、hashlib、SQLAlchemy、MySQL/SQLite、pytest。

---

## 文件与职责

- Create: src/pretrade/config_workbook.py — 读取工作簿原件、计算 SHA-256、验证值对象。
- Modify: src/stage1/stage1_limit_detail.py、src/stage1/stage1_processor.py — 将监管集中度参数读取统一到 Stage1 已持有的 config 对象。
- Modify: src/pretrade/input_contract.py — PretradeSnapshotRequest 增加必填附件，27 项输入集合不变。
- Modify: src/pretrade/context_build.py — 从 runtime.stage1_processor.config 捕获原件。
- Modify: src/pretrade/context_store.py — 第四张附件表、事务写入、读回校验、发布前验证。
- Modify: tests/pretrade/conftest.py — 原件测试工厂。
- Create: tests/pretrade/test_config_workbook.py — 捕获单测。
- Modify: tests/pretrade/test_input_contract.py、tests/pretrade/test_context_build.py、tests/pretrade/test_context_store.py — 契约、构建、存储和回滚测试。
- Modify: scripts/run_pretrade_context.py、tests/scripts/test_run_pretrade_context.py — 冻结验收读回附件及摘要。
- Modify: docs/PRETRADE_SHARED_CORE_SPEC.md、docs/PRETRADE_DOCUMENT_STATUS.md、docs/evidence/pretrade-context-minimal-reset-20260710.json — 四表设计和正式验收记录。

不修改：archive_meta、16 张既有展示归档表、展示快照、前端、限额算法、Wind 查询与 Wind 落库。

### Task 0: 统一 Stage1 配置来源而不改变计算规则

**Files:**
- Modify: src/stage1/stage1_limit_detail.py
- Modify: src/stage1/stage1_processor.py
- Modify: tests/risk_core/test_stage1_limits_characterization.py

- [ ] **Step 1: 写失败测试**

将 test_stage1_adapter_resolves_regulatory_parameter_before_building_engine 的 FakeCalculator
替换为以下签名和断言：

~~~python
class FakeCalculator:
    def __init__(
        self,
        cache,
        regulatory_concentration_limit=None,
        config=None,
    ):
        constructor_values.append((regulatory_concentration_limit, config))

    def _load_regulatory_concentration_limit(self):
        return 0.16


calculator = stage1_processor._build_limit_calculator()

assert isinstance(calculator, FakeCalculator)
assert constructor_values == [
    (None, stage1_processor.config),
    (0.16, stage1_processor.config),
]
assert stage1_processor._runtime_regulatory_concentration_limit == 0.16
~~~

- [ ] **Step 2: 确认测试失败**

Run: pytest tests/risk_core/test_stage1_limits_characterization.py::test_stage1_adapter_resolves_regulatory_parameter_before_building_engine -q

Expected: FAIL，因为 Stage1 尚未向 LimitDetailCalculator 传入 config。

- [ ] **Step 3: 仅统一读取路径**

将 LimitDetailCalculator 构造函数改为：

~~~python
def __init__(
    self,
    cache: Mapping[str, pd.DataFrame],
    regulatory_concentration_limit: float | None = None,
    config=None,
):
    super().__init__(
        cache,
        0.0 if regulatory_concentration_limit is None
        else regulatory_concentration_limit,
    )
    self.cache = cache
    self._regulatory_concentration_limit_override = regulatory_concentration_limit
    self._config = config
~~~

将 _load_regulatory_concentration_limit 中的 config = ConfigLoader() 改为：

~~~python
config = self._config if self._config is not None else ConfigLoader()
~~~

将 Stage1Processor._build_limit_calculator 改为：

~~~python
resolver = LimitDetailCalculator(self.cache, config=self.config)
regulatory_limit = resolver._load_regulatory_concentration_limit()
self._runtime_regulatory_concentration_limit = float(regulatory_limit)
return LimitDetailCalculator(
    self.cache,
    regulatory_concentration_limit=regulatory_limit,
    config=self.config,
)
~~~

不要修改 Stage1LimitEngine、计算公式、限额值解析、既有不传 config 的兼容调用。

- [ ] **Step 4: 验证并提交**

Run:

~~~bash
pytest tests/risk_core/test_stage1_limits_characterization.py tests/test_stage_high_yield_and_specific_controller.py -q
~~~

Expected: PASS。

~~~bash
git add src/stage1/stage1_limit_detail.py src/stage1/stage1_processor.py tests/risk_core/test_stage1_limits_characterization.py
git commit -m "fix: use stage config for regulatory limit"
~~~

### Task 1: 原件值对象和读取入口

**Files:**
- Create: src/pretrade/config_workbook.py
- Modify: tests/pretrade/conftest.py
- Create: tests/pretrade/test_config_workbook.py

- [ ] **Step 1: 写失败测试**

~~~python
from hashlib import sha256

import pytest

from src.pretrade.config_workbook import (
    LIMIT_CONFIG_WORKBOOK_NAME,
    PretradeConfigWorkbookError,
    capture_config_workbook,
)


def test_capture_reads_exact_stage1_config_bytes(tmp_path) -> None:
    payload = b"PK\x03\x04fixture-xlsx"
    source = tmp_path / LIMIT_CONFIG_WORKBOOK_NAME
    source.write_bytes(payload)

    class Config:
        def get_data_file_path(self, name):
            assert name == LIMIT_CONFIG_WORKBOOK_NAME
            return source

    workbook = capture_config_workbook(Config())

    assert workbook.file_name == LIMIT_CONFIG_WORKBOOK_NAME
    assert workbook.payload == payload
    assert workbook.payload_hash == sha256(payload).hexdigest()


def test_capture_rejects_missing_workbook(tmp_path) -> None:
    class Config:
        def get_data_file_path(self, name):
            return tmp_path / name

    with pytest.raises(PretradeConfigWorkbookError, match="无法读取"):
        capture_config_workbook(Config())
~~~

- [ ] **Step 2: 确认测试失败**

Run: pytest tests/pretrade/test_config_workbook.py -q

Expected: FAIL，提示 src.pretrade.config_workbook 不存在。

- [ ] **Step 3: 写最小实现**

~~~python
"""交易前快照所附的原始限额配置工作簿。"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

LIMIT_CONFIG_WORKBOOK_NAME = "限额配置_当前.xlsx"


class PretradeConfigWorkbookError(ValueError):
    """无法取得可审计的原始限额配置工作簿。"""


@dataclass(frozen=True)
class PretradeConfigWorkbook:
    file_name: str
    payload: bytes
    payload_hash: str

    def __post_init__(self) -> None:
        if self.file_name != LIMIT_CONFIG_WORKBOOK_NAME:
            raise PretradeConfigWorkbookError("配置工作簿文件名不符合契约")
        if not isinstance(self.payload, bytes) or not self.payload:
            raise PretradeConfigWorkbookError("配置工作簿原始字节为空或非法")
        if self.payload_hash != sha256(self.payload).hexdigest():
            raise PretradeConfigWorkbookError("配置工作簿 SHA-256 不一致")


def capture_config_workbook(config: Any) -> PretradeConfigWorkbook:
    resolver = getattr(config, "get_data_file_path", None)
    if not callable(resolver):
        raise PretradeConfigWorkbookError("Stage1 配置对象不能解析限额配置路径")
    try:
        payload = Path(resolver(LIMIT_CONFIG_WORKBOOK_NAME)).read_bytes()
    except (OSError, TypeError, ValueError) as exc:
        raise PretradeConfigWorkbookError(
            "无法读取当次实际使用的限额配置工作簿"
        ) from exc
    return PretradeConfigWorkbook(
        file_name=LIMIT_CONFIG_WORKBOOK_NAME,
        payload=payload,
        payload_hash=sha256(payload).hexdigest(),
    )
~~~

在 tests/pretrade/conftest.py 增加：

~~~python
def make_config_workbook(
    payload: bytes = b"PK\x03\x04fixture-xlsx",
) -> PretradeConfigWorkbook:
    return PretradeConfigWorkbook(
        file_name=LIMIT_CONFIG_WORKBOOK_NAME,
        payload=payload,
        payload_hash=sha256(payload).hexdigest(),
    )
~~~

在 tests/pretrade/test_context_store.py 的 context_request fixture 中改为：

~~~python
@pytest.fixture
def context_request():
    return PretradeSnapshotRequest.from_kernel_input(
        make_kernel_input(),
        make_config_workbook(),
    )
~~~

- [ ] **Step 4: 验证并提交**

Run: pytest tests/pretrade/test_config_workbook.py tests/pretrade/test_frame_codec.py -q

Expected: PASS。

~~~bash
git add src/pretrade/config_workbook.py tests/pretrade/conftest.py tests/pretrade/test_config_workbook.py
git commit -m "feat: capture raw pretrade config workbook"
~~~

### Task 2: 快照请求和构建路径

**Files:**
- Modify: src/pretrade/input_contract.py
- Modify: src/pretrade/context_build.py
- Modify: tests/pretrade/test_input_contract.py
- Modify: tests/pretrade/test_context_build.py

- [ ] **Step 1: 写失败测试**

~~~python
def test_snapshot_request_requires_config_workbook() -> None:
    with pytest.raises(TypeError, match="config_workbook"):
        PretradeSnapshotRequest.from_kernel_input(make_kernel_input(), None)


def test_build_captures_workbook_from_stage1_config(tmp_path) -> None:
    source = tmp_path / "限额配置_当前.xlsx"
    source.write_bytes(b"PK\x03\x04runtime-config")
    runtime = _runtime(
        config=SimpleNamespace(get_data_file_path=lambda name: source)
    )
    store = PretradeContextStore(
        create_engine("sqlite+pysqlite:///:memory:", future=True)
    )
    store.prepare_schema()

    snapshot_id = build_ready_context(runtime, store)

    assert store.load_config_workbook(snapshot_id).payload == b"PK\x03\x04runtime-config"
~~~

- [ ] **Step 2: 确认测试失败**

Run: pytest tests/pretrade/test_input_contract.py tests/pretrade/test_context_build.py -q

Expected: FAIL，因为请求没有 config_workbook，构建函数尚未读取 Stage1 配置。

- [ ] **Step 3: 实现最小接线**

将 PretradeSnapshotRequest 定义改为：

~~~python
@dataclass(frozen=True)
class PretradeSnapshotRequest:
    kernel_input: ProductionKernelInput
    config_workbook: PretradeConfigWorkbook

    @classmethod
    def from_kernel_input(
        cls,
        kernel_input: ProductionKernelInput,
        config_workbook: PretradeConfigWorkbook,
    ) -> "PretradeSnapshotRequest":
        if not isinstance(kernel_input, ProductionKernelInput):
            raise PretradeInputContractError(
                "kernel_input 必须是 ProductionKernelInput"
            )
        if not isinstance(config_workbook, PretradeConfigWorkbook):
            raise TypeError("config_workbook 必须是 PretradeConfigWorkbook")
        _validate_frames(kernel_input)
        return cls(kernel_input, config_workbook)
~~~

在 build_ready_context 中、创建请求前加入：

~~~python
stage1_config = getattr(stage1, "config", None)
config_workbook = capture_config_workbook(stage1_config)
request = PretradeSnapshotRequest.from_kernel_input(
    kernel_input,
    config_workbook,
)
~~~

测试的 _runtime 工厂增加 config 参数并设置 stage1_processor.config。不得修改 KERNEL_INPUT_DATASETS，不得让 ProductionRiskKernel 接受工作簿。

既有 test_build_writes_an_unpublished_snapshot 必须增加 tmp_path 参数，并传入一个真实临时
配置文件：

~~~python
source = tmp_path / "限额配置_当前.xlsx"
source.write_bytes(b"PK\x03\x04default-runtime-config")
runtime = _runtime(
    config=SimpleNamespace(get_data_file_path=lambda name: source)
)
~~~

- [ ] **Step 4: 验证并提交**

Run: pytest tests/pretrade/test_input_contract.py tests/pretrade/test_context_build.py -q

Expected: PASS，既有构建测试继续断言内核输入为 27 份。

~~~bash
git add src/pretrade/input_contract.py src/pretrade/context_build.py tests/pretrade/test_input_contract.py tests/pretrade/test_context_build.py
git commit -m "feat: attach config workbook to pretrade request"
~~~

### Task 3: 附件表、事务、完整性和发布检查

**Files:**
- Modify: src/pretrade/context_store.py
- Modify: tests/pretrade/test_context_store.py

- [ ] **Step 1: 写失败测试**

将 schema 测试的表集合改为四张，并新增：

~~~python
def test_config_workbook_round_trips_byte_for_byte(engine, context_request) -> None:
    store = PretradeContextStore(engine)
    store.prepare_schema()
    snapshot_id = store.write_snapshot(context_request)

    assert store.load_config_workbook(snapshot_id) == context_request.config_workbook


def test_corrupt_config_workbook_hash_is_rejected(engine, context_request) -> None:
    store = PretradeContextStore(engine)
    store.prepare_schema()
    snapshot_id = store.write_snapshot(context_request)
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE pretrade_config_workbook SET payload_hash = :hash "
                "WHERE snapshot_id = :snapshot_id"
            ),
            {"hash": "0" * 64, "snapshot_id": str(snapshot_id)},
        )

    with pytest.raises(PretradeContextIntegrityError, match="配置工作簿"):
        store.load_config_workbook(snapshot_id)


def test_publish_rejects_snapshot_without_config_workbook(
    engine, context_request
) -> None:
    store = PretradeContextStore(engine)
    store.prepare_schema()
    snapshot_id = store.write_snapshot(context_request)
    _create_current_archive(engine, "2026-07-10")
    with engine.begin() as conn:
        conn.execute(
            text(
                "DELETE FROM pretrade_config_workbook "
                "WHERE snapshot_id = :snapshot_id"
            ),
            {"snapshot_id": str(snapshot_id)},
        )

    with pytest.raises(PretradePublishError, match="配置工作簿"):
        store.publish_current(snapshot_id)
~~~

同时扩展已有回滚测试：调用 write_snapshot(context_request, fail_after_config_workbook=True)，断言三张原表和附件表都没有新增行，原 current 不变。

- [ ] **Step 2: 确认测试失败**

Run: pytest tests/pretrade/test_context_store.py -q

Expected: FAIL，因为 pretrade_config_workbook 和读取接口尚不存在。

- [ ] **Step 3: 实现第四张表和存储方法**

在 PRETRADE_METADATA 增加：

~~~python
PRETRADE_CONFIG_WORKBOOK = Table(
    "pretrade_config_workbook",
    PRETRADE_METADATA,
    Column(
        "snapshot_id",
        String(36),
        ForeignKey("pretrade_snapshot.snapshot_id"),
        primary_key=True,
    ),
    Column("file_name", String(255), nullable=False),
    Column("payload_hash", String(64), nullable=False),
    Column(
        "payload",
        LargeBinary().with_variant(MYSQL_LONGBLOB(), "mysql"),
        nullable=False,
    ),
)
~~~

实现内部读取和公开读取：

~~~python
def _load_config_workbook(
    self, conn: Connection, snapshot_id: UUID
) -> PretradeConfigWorkbook:
    row = conn.execute(
        select(PRETRADE_CONFIG_WORKBOOK).where(
            PRETRADE_CONFIG_WORKBOOK.c.snapshot_id == str(snapshot_id)
        )
    ).mappings().one_or_none()
    if row is None:
        raise PretradeContextIntegrityError(
            "交易前快照缺少原始配置工作簿"
        )
    try:
        return PretradeConfigWorkbook(
            file_name=str(row["file_name"]),
            payload=bytes(row["payload"]),
            payload_hash=str(row["payload_hash"]),
        )
    except PretradeConfigWorkbookError as exc:
        raise PretradeContextIntegrityError(
            "原始配置工作簿完整性校验失败"
        ) from exc


def load_config_workbook(
    self, snapshot_id: UUID | str
) -> PretradeConfigWorkbook:
    normalized_snapshot_id = _as_uuid(snapshot_id)
    with self._engine.connect() as conn:
        return self._load_config_workbook(conn, normalized_snapshot_id)
~~~

write_snapshot 在 27 个 dataset insert 结束后、同一个 self._engine.begin() 中插入 request.config_workbook。函数签名增加 fail_after_config_workbook: bool = False；插入附件后该参数为真时抛 RuntimeError("injected config workbook failure")。publish_current 在切指针前调用 _load_config_workbook(conn, normalized_snapshot_id)。异常转换沿用现有 PretradeContextIntegrityError 和 PretradePublishError 语义。附件绝不进入 pretrade_snapshot_dataset，后者仍必须精确等于 27 个 dataset。

- [ ] **Step 4: 验证并提交**

Run: pytest tests/pretrade/test_context_store.py tests/pretrade/test_context_build.py -q

Expected: PASS；fresh SQLite schema 恰有 4 张 pretrade 表，成功快照有 27 个 dataset 和 1 个 SHA-256 可校验附件。

~~~bash
git add src/pretrade/context_store.py tests/pretrade/test_context_store.py
git commit -m "feat: store config workbook with pretrade snapshots"
~~~

### Task 4: 冻结验收、文档和正式检查

**Files:**
- Modify: scripts/run_pretrade_context.py
- Modify: tests/scripts/test_run_pretrade_context.py
- Modify: docs/PRETRADE_SHARED_CORE_SPEC.md
- Modify: docs/PRETRADE_DOCUMENT_STATUS.md
- Modify: docs/evidence/pretrade-context-minimal-reset-20260710.json

- [ ] **Step 1: 写冻结摘要的失败测试**

~~~python
assert summary["config_workbook"]["file_name"] == "限额配置_当前.xlsx"
assert len(summary["config_workbook"]["payload_hash"]) == 64
assert summary["config_workbook"]["byte_count"] > 0
assert summary["replay"]["passed"] is True
~~~

- [ ] **Step 2: 确认测试失败**

Run: pytest tests/scripts/test_run_pretrade_context.py -q

Expected: FAIL，因为冻结摘要尚未包含 config_workbook。

- [ ] **Step 3: 实现冻结附件核验**

在 scripts/run_pretrade_context.py 的 build_ready_context 后加入：

~~~python
from hashlib import sha256

workbook = store.load_config_workbook(snapshot_id)
if workbook.payload_hash != sha256(workbook.payload).hexdigest():
    raise RuntimeError("冻结验收配置工作簿摘要不一致")
~~~

在 summary 顶层加入：

~~~python
"config_workbook": {
    "file_name": workbook.file_name,
    "payload_hash": workbook.payload_hash,
    "byte_count": len(workbook.payload),
},
~~~

不得改变 verify_rehydrated_context、replay_kernel_from_snapshot、assert_replay_matches_runtime 的顺序，也不得将附件传给 ProductionRiskKernel。

- [ ] **Step 4: 定向与完整测试**

Run:

~~~bash
pytest tests/pretrade tests/scripts/test_run_pretrade_context.py tests/scripts/test_run_daily_pipeline.py -q
pytest -q
~~~

Expected: 全部 PASS，既有 Stage0/1/2 冻结指纹保持不变。

- [ ] **Step 5: 正式冻结验收**

Run:

~~~bash
source /Users/dellawang/Desktop/LimitMonitorBackup/new.txt
python scripts/run_pretrade_context.py \
  --input-root /Users/dellawang/Desktop/LimitMonitorAutomation/data_source_0123 \
  --manifest config/test_manifests/data_source_0123-20260710-v1.json \
  --allow-output-root /Users/dellawang/Desktop/LimitMonitorAutomation-test-output \
  --output /Users/dellawang/Desktop/LimitMonitorAutomation-test-output/pretrade-config-workbook-20260710 \
  --note "raw config workbook audit attachment"
~~~

Expected: 只创建未发布验收快照；正式库有 4 张 pretrade 表；目标快照有 27 条 dataset、1 条 config_workbook；Stage0/1/2 指纹与 docs/evidence/pretrade-baseline-20260710.json 完全一致。

- [ ] **Step 6: 更新证据、文档和提交**

将真实 snapshot ID、data_date、附件 SHA-256、附件字节数、四表清单、27 数据集计数及既有指纹写入 docs/evidence/pretrade-context-minimal-reset-20260710.json，且不写数据库凭据。

在 docs/PRETRADE_SHARED_CORE_SPEC.md 和 docs/PRETRADE_DOCUMENT_STATUS.md 明确：

~~~markdown
- 交易前持久化由 3 张计算上下文表和 1 张审计附件表构成；
- pretrade_config_workbook 保存每日实际使用的 限额配置_当前.xlsx 原件；
- 原件不属于 27 份共同内核输入，不参与计算或重放；
- 非持仓债 Wind 主数据仍 on-the-fly，不落库；
- 历史快照不回填；只有带附件的新快照可发布为 current。
~~~

Run:

~~~bash
rg -n "pretrade_config_workbook|限额配置_当前.xlsx" src/pretrade scripts/run_pretrade_context.py docs/PRETRADE_SHARED_CORE_SPEC.md docs/PRETRADE_DOCUMENT_STATUS.md
rg -n "Wind|wind" src/pretrade scripts/run_pretrade_context.py
git diff --check
pytest -q
~~~

Expected: 附件仅出现在 pretrade 捕获、存储、验收和文档；没有 Wind 数据写入；无空白错误；测试全绿。

~~~bash
git add scripts/run_pretrade_context.py tests/scripts/test_run_pretrade_context.py docs/PRETRADE_SHARED_CORE_SPEC.md docs/PRETRADE_DOCUMENT_STATUS.md docs/evidence/pretrade-context-minimal-reset-20260710.json
git commit -m "test: verify pretrade config workbook attachment"
git status --short
~~~

Expected: 工作树干净；不创建 DEV/TEST 账号，不改既有归档结构。

## 计划自检

- 原件保存、SHA-256、单事务、读回、发布前验证、历史不回填、共同内核不变、Wind 不落库均由 Task 1–4 覆盖。
- 27 个共同内核数据集保持严格为 27；原始 xlsx 只写入独立附件表。
- 未新增前端、展示归档表、16 张重复配置表或第二套限额计算逻辑。
