# Pretrade Safe Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不连接数据库、不访问 Wind、不触碰生产归档目录且不改变任何业务计算代码的前提下，用冻结的 data_source_0123 完整运行 GitHub 上线基线 Stage0 → Stage1 → Stage2，并生成可重复比较的生产金样。

**Architecture:** 本阶段只增加测试编排层。Stage0Processor、Stage1Processor、Stage2Processor 保持字节级不变；外层负责冻结业务日输入、只读校验当前静态主体代码映射、在隔离目录重建显式零代码会话上下文、路径保护、macOS 文件沙箱、显式路径注入、顺序编排、受保护目录清单和逻辑内容指纹。共同内核、不可变数据库、Wind 落库和两个页面均不在本计划实现。

**Tech Stack:** Python 3.14、pandas、openpyxl、pytest、mdbtools、macOS sandbox-exec、现有 Stage0/Stage1/Stage2。

## Global Constraints

- 上线基线固定为 GitHub main 提交 579af695fb8727dec8249f66d07a8b0e723da137。
- 业务依据固定为 docs/PRETRADE_SHARED_CORE_SPEC.md。
- 输入清单固定为 data_source_0123-20260710-v1，业务日固定为 2026-07-10。
- `issuer_wind_code_mapping.csv` 属于无业务日期的静态运行依赖，按 `docs/PRETRADE_SHARED_CORE_SPEC.md` 2.1 直接只读使用当前表；不得混入12文件业务清单，也不得另建历史映射主表。
- 必须显式设置 ENV=test 与 LIMIT_MONITOR_PROFILE=local。
- 每一个输入文件都执行 realpath、普通文件、直接子文件、大小和 SHA-256 校验。
- 输出必须是外部白名单根下全新且不存在的唯一目录。
- 受限阶段只能读取全盘，只能写本次唯一输出根，默认禁止网络。
- 禁止调用 ArchiveDB、daily_archive、run_daily 或修改 current 指针。
- 合法空表是生产结果；缺输出文件、缺结果键或异常才是失败。
- 不修改 src/stage0、src/stage1、src/stage2、src/common、src/utils、config/settings.yaml 和 scripts/daily_archive.py。
- 所有行为先写失败测试，再写最小实现；每个任务独立提交。

## File Structure

- config/test_manifests/data_source_0123-20260710-v1.json
- config/test_manifests/frozen-baseline-macos.sb
- src/testing/__init__.py
- src/testing/frozen_manifest.py
- src/testing/current_issuer_resolver.py
- src/testing/legacy_local_compat.py
- src/testing/safe_paths.py
- src/testing/test_environment.py
- src/testing/frozen_config.py
- src/testing/output_fingerprint.py
- src/testing/protected_inventory.py
- src/pipeline/__init__.py
- src/pipeline/paths.py
- src/pipeline/execution.py
- scripts/run_frozen_baseline.py
- tests/testing/test_frozen_manifest.py
- tests/testing/test_current_issuer_resolver.py
- tests/testing/test_legacy_local_compat.py
- tests/testing/test_safe_paths.py
- tests/testing/test_test_environment.py
- tests/testing/test_frozen_config.py
- tests/testing/test_output_fingerprint.py
- tests/testing/test_protected_inventory.py
- tests/pipeline/test_paths.py
- tests/pipeline/test_execution.py
- tests/scripts/test_run_frozen_baseline.py
- tests/scripts/test_frozen_baseline_sandbox.py
- docs/evidence/pretrade-baseline-20260710.json

## Out of Scope

- 不提取或修改业务内核。
- 不创建、迁移或写入任何业务数据库表。
- 不调用 Wind，不写本地 Wind JSON。
- 不实时调用 Excel/Wind；当前映射只读校验后复制进本次隔离输出，显式零代码仅在隔离临时目录形成一次性会话结果。
- 不修改两个交易前页面或其他页面。
- 不运行现有 run_daily.sh、run_daily.bat 或 daily_archive.py。

### Task 1: Freeze and validate the exact source manifest

**Files:**

- Create: config/test_manifests/data_source_0123-20260710-v1.json
- Create: src/testing/__init__.py
- Create: src/testing/frozen_manifest.py
- Test: tests/testing/test_frozen_manifest.py

- [x] **Step 1: Write failing tests**

Tests cover:

- manifest_id and expected_business_date are mandatory;
- file names must be unique direct relative names;
- source directory entry names must equal the manifest exactly;
- file symlinks, directories, parent traversal and realpath escape fail;
- size or SHA-256 mismatch fails;
- success returns immutable resolved metadata.

~~~python
def test_validate_rejects_symlinked_manifest_file(tmp_path: Path) -> None:
    source = tmp_path / "source"
    outside = tmp_path / "outside.xlsx"
    source.mkdir()
    outside.write_bytes(b"outside")
    (source / "a.xlsx").symlink_to(outside)
    manifest = write_manifest_for(source_name="a.xlsx", payload=b"outside")

    with pytest.raises(ManifestValidationError, match="符号链接"):
        FrozenInputManifest.load(manifest).validate(source)
~~~

- [x] **Step 2: Confirm red**

~~~bash
/opt/homebrew/bin/python3 -m pytest -q tests/testing/test_frozen_manifest.py
~~~

Expected: import or implementation failure.

- [x] **Step 3: Add the exact JSON manifest**

The files array must contain these exact name, size and SHA-256 tuples:

~~~text
债券持仓表.xlsx|66647566|a45641ca4588d9501c2828e223b65ba223a7ece50abc6be14d53f2be9b7eed44
净资产.xlsx|15891|b8a26866781d60cb5fa0da08294865d53616a7365a8d7e7d69c1a87f74f9bb7f
发行人类型调整表.xlsx|11721|ef509169d5c737c87b0a1f7302fadd8ed6b2d4e898493b641a46fdd9637a1edd
德勤-主体评级列表.xlsx|1026501|3767bba6af1affd2b2720e2918a699c511ecbec6b6e997d08fc5651a2f6b8e34
标准日期表.xlsx|2158468|2b90877b544707e387a2cc2038bc35d09b09177e41b07e8c422441b49ac30049
统计报表底稿1_债券.xlsx|9593195|dd5e34f661fe4168204795ae0c44504225f6e3584781df7bcf2fbe3e738d0944
统计报表底稿2_债券SPPI.xlsx|3475349|5c655f3b4cac75e12470dd055a4a6d4b21b7f55db399a00a0e47eef2cc4c6dde
金融工具池设置.xlsx|220604|7251130cf375644dc7d43dd8d130e2b7bac76feae731e45c599bb3c1a611f39d
限额监控_阶段0_指标设置.xlsx|4544549|039057aa5aef0faab355374705c14f590f9fd220b1bc2fc57d69b77b0a66e6b2
限额配置_当前.xlsx|29504|3b8afc3a84cca30c7a6966ec5e8892c44055ecc64c693ded89ab67509e318560
风控部债券池.accdb|283623424|d2ce9da9e193503d5e42c3e254e5494147e7fc322a89e522fd2713501c681348
风控部债券池_主体_虚拟添加.xlsx|26291|4253e258e03764765bb93a1a21e018bb95fa4904f494f4118a2f5caa068e2157
~~~

- [x] **Step 4: Implement immutable validation**

~~~python
@dataclass(frozen=True)
class FrozenFile:
    name: str
    size: int
    sha256: str


@dataclass(frozen=True)
class ValidatedInputManifest:
    manifest_id: str
    expected_business_date: date
    input_root: Path
    files: tuple[FrozenFile, ...]


class ManifestValidationError(RuntimeError):
    pass
~~~

Validation order:

1. resolve input root with strict=True;
2. compare exact directory entry names, including symlinks;
3. reject every entry for which is_symlink() is true;
4. resolve each entry with strict=True and require resolved.parent == input_root;
5. require is_file();
6. compare size;
7. stream SHA-256 in binary chunks;
8. return only after all 12 succeed.

- [x] **Step 5: Verify and commit**

~~~bash
/opt/homebrew/bin/python3 -m pytest -q tests/testing/test_frozen_manifest.py
git diff --check
git add config/test_manifests/data_source_0123-20260710-v1.json src/testing tests/testing/test_frozen_manifest.py
git commit -m "test: freeze pretrade baseline inputs"
~~~

### Task 2: Create fail-closed path and environment guards

**Files:**

- Create: src/testing/safe_paths.py
- Create: src/testing/test_environment.py
- Test: tests/testing/test_safe_paths.py
- Test: tests/testing/test_test_environment.py

- [x] **Step 1: Write failing path tests**

Tests reject:

- missing allow-root;
- allow-root inside project/data, project root, /Volumes or a configured forbidden root;
- existing output path, including an empty directory;
- input/output overlap;
- requested parent symlink escape;
- output resolving outside allow-root.

~~~python
def test_output_rejects_symlink_escape(
    tmp_path: Path,
    project_root: Path,
) -> None:
    allow = tmp_path / "allow"
    source = tmp_path / "source"
    outside = tmp_path / "outside"
    allow.mkdir()
    source.mkdir()
    outside.mkdir()
    (allow / "escape").symlink_to(outside, target_is_directory=True)

    with pytest.raises(UnsafeTestPath):
        create_unique_test_output(
            allow_root=allow,
            requested=allow / "escape" / "run",
            project_root=project_root,
            input_root=source,
        )
~~~

- [x] **Step 2: Write failing environment tests**

~~~python
@pytest.mark.parametrize(
    ("env_name", "profile_name"),
    [(None, "local"), ("prod", "local"), ("test", None), ("test", "migration")],
)
def test_environment_requires_test_and_local(env_name, profile_name) -> None:
    with pytest.raises(UnsafeTestEnvironment):
        assert_test_environment(env_name, profile_name)
~~~

- [x] **Step 3: Confirm red**

~~~bash
/opt/homebrew/bin/python3 -m pytest -q \
  tests/testing/test_safe_paths.py \
  tests/testing/test_test_environment.py
~~~

- [x] **Step 4: Implement guards**

create_unique_test_output must:

1. resolve existing allow-root, input root and project root;
2. reject production/shared roots;
3. require requested not to exist;
4. resolve requested.parent strictly;
5. require candidate to be under allow-root and disjoint from input;
6. mkdir mode 0700 with exist_ok=False;
7. resolve and re-check containment;
8. remove only the just-created empty directory if post-create validation fails.

Environment API:

~~~python
def assert_test_environment(
    env_name: str | None,
    profile_name: str | None,
) -> None:
    if (env_name or "").strip().lower() != "test":
        raise UnsafeTestEnvironment("ENV 必须为 test")
    if (profile_name or "").strip().lower() != "local":
        raise UnsafeTestEnvironment("LIMIT_MONITOR_PROFILE 必须为 local")
~~~

- [x] **Step 5: Verify and commit**

~~~bash
/opt/homebrew/bin/python3 -m pytest -q \
  tests/testing/test_safe_paths.py \
  tests/testing/test_test_environment.py
git diff --check
git add src/testing/safe_paths.py src/testing/test_environment.py tests/testing
git commit -m "test: fail closed on unsafe baseline environment"
~~~

### Task 3: Inject frozen input and isolated Access export paths

**Files:**

- Create: src/testing/frozen_config.py
- Create: src/pipeline/__init__.py
- Create: src/pipeline/paths.py
- Test: tests/testing/test_frozen_config.py
- Test: tests/pipeline/test_paths.py

- [x] **Step 1: Write failing tests**

FrozenInputConfig tests prove:

- get delegates threshold/config values to the normal ConfigLoader;
- every data file resolves only through the validated manifest;
- migration environment variables cannot redirect files;
- get_data_file_path_without_override returns the validated ACCDB;
- get_data_config_source_dir returns this run's isolated access_export;
- access_export outside the pipeline root is rejected.

PipelinePaths tests prove:

- root exists, is resolved, non-symlink and empty;
- exact children stage0, stage1, stage2, logs, access_export, tmp and home are created once;
- repeated creation and non-empty root fail.

- [x] **Step 2: Confirm red**

~~~bash
/opt/homebrew/bin/python3 -m pytest -q \
  tests/testing/test_frozen_config.py \
  tests/pipeline/test_paths.py
~~~

- [x] **Step 3: Implement explicit paths**

~~~python
@dataclass(frozen=True)
class PipelinePaths:
    root: Path
    stage0: Path
    stage1: Path
    stage2: Path
    logs: Path
    access_export: Path
    tmp: Path
    home: Path
~~~

FrozenInputConfig has this complete path API:

~~~python
def get_data_dir(self) -> Path:
    return self._manifest.input_root

def get_data_file_path(self, file_name: str) -> Path:
    if file_name not in self._allowed_names:
        raise FrozenConfigError(f"文件不在冻结清单中: {file_name}")
    return self._manifest.input_root / file_name

def get_data_file_path_without_override(self, file_name: str) -> Path:
    return self.get_data_file_path(file_name)

def get_data_config_source_dir(self) -> Path:
    return self._access_export_dir
~~~

Constructor signature is:

~~~python
class FrozenInputConfig:
    def __init__(
        self,
        base: ConfigLoader,
        manifest: ValidatedInputManifest,
        pipeline_root: Path,
        access_export_dir: Path,
    ) -> None: ...

    @property
    def manifest(self) -> ValidatedInputManifest: ...
~~~

It resolves `pipeline_root` and `access_export_dir`, requires `access_export_dir.is_relative_to(pipeline_root)`, and exposes the same immutable manifest instance through `manifest`.

- [x] **Step 4: Verify and commit**

~~~bash
/opt/homebrew/bin/python3 -m pytest -q \
  tests/testing/test_frozen_config.py \
  tests/pipeline/test_paths.py
git diff --check
git add src/testing/frozen_config.py src/pipeline tests/testing/test_frozen_config.py tests/pipeline/test_paths.py
git commit -m "test: inject frozen pretrade pipeline paths"
~~~

### Task 4: Orchestrate the untouched production processors

**Files:**

- Create: `src/pipeline/execution.py`
- Test: `tests/pipeline/test_execution.py`

**Interfaces:**

- Consumes: `ValidatedInputManifest`, `FrozenInputConfig` and `PipelinePaths` from Tasks 1–3.
- Produces: `BaselineRunRequest`, `StageRunResult`, `BaselineRunResult` and `run_frozen_pipeline(request)`.

- [x] **Step 1: Write failing constructor and order tests**

Patch only the processor classes in the test module. Assert the exact constructor arguments and call order:

~~~python
def test_run_uses_production_processors_in_exact_order(
    monkeypatch: pytest.MonkeyPatch,
    request: BaselineRunRequest,
) -> None:
    calls: list[tuple[str, object]] = []

    class FakeStage0:
        def __init__(self, data_dir, output_dir, config, target_date):
            calls.append(("stage0_init", (data_dir, output_dir, config, target_date)))

        def process_all(self):
            calls.append(("stage0_run", None))
            return write_fake_result(request.paths.stage0, "s0")

    class FakeStage1:
        def __init__(self, data_dir, output_dir, stage0_output_dir, config):
            calls.append(("stage1_init", (data_dir, output_dir, stage0_output_dir, config)))

        def process_all(self):
            calls.append(("stage1_run", None))
            return write_fake_result(request.paths.stage1, "s1")

    class FakeStage2:
        def __init__(self, data_dir, output_dir, stage0_output_dir, stage1_output_dir, config):
            calls.append(("stage2_init", (data_dir, output_dir, stage0_output_dir, stage1_output_dir, config)))

        def process_all(self):
            calls.append(("stage2_run", None))
            return write_fake_result(request.paths.stage2, "s2")

    monkeypatch.setattr(execution, "Stage0Processor", FakeStage0)
    monkeypatch.setattr(execution, "Stage1Processor", FakeStage1)
    monkeypatch.setattr(execution, "Stage2Processor", FakeStage2)

    result = run_frozen_pipeline(request)

    assert [name for name, _ in calls] == [
        "stage0_init", "stage0_run",
        "stage1_init", "stage1_run",
        "stage2_init", "stage2_run",
    ]
    assert result.business_date == date(2026, 7, 10)
~~~

`write_fake_result` writes one real `name.xlsx` and returns `{name: pd.DataFrame()}`. This intentionally proves that a legal empty table passes.

- [x] **Step 2: Write failing result-contract tests**

Each stage must fail closed when:

- `process_all()` does not return a mapping;
- a key is not a non-empty string;
- a value is not a `pandas.DataFrame`;
- `<stage output>/<key>.xlsx` is missing or is not a regular non-symlink file;
- a processor raises an exception.

Do **not** reject an empty DataFrame if its workbook exists. This distinguishes a legal empty production result from Stage0's swallowed-query failure.

~~~python
def test_missing_workbook_rejects_stage0_swallowed_failure(request, monkeypatch):
    monkeypatch.setattr(
        execution.Stage0Processor,
        "process_all",
        lambda self: {"风控部债券池": pd.DataFrame()},
    )
    with pytest.raises(BaselineExecutionError, match="缺少输出工作簿"):
        run_frozen_pipeline(request)
~~~

- [x] **Step 3: Confirm red**

~~~bash
/opt/homebrew/bin/python3 -m pytest -q tests/pipeline/test_execution.py
~~~

Expected: import or implementation failure.

- [x] **Step 4: Implement the request and result contracts**

~~~python
@dataclass(frozen=True)
class BaselineRunRequest:
    manifest: ValidatedInputManifest
    config: FrozenInputConfig
    paths: PipelinePaths
    business_date: date


@dataclass(frozen=True)
class StageRunResult:
    stage: str
    output_dir: Path
    table_names: tuple[str, ...]


@dataclass(frozen=True)
class BaselineRunResult:
    business_date: date
    stages: tuple[StageRunResult, StageRunResult, StageRunResult]
~~~

`BaselineRunRequest.__post_init__` requires `business_date == manifest.expected_business_date`, `config` to wrap the same manifest, and all paths to belong to one `PipelinePaths.root`.

Instantiate only the deployed classes and call only their existing `process_all()` methods:

~~~python
stage0 = Stage0Processor(
    data_dir=request.manifest.input_root,
    output_dir=request.paths.stage0,
    config=request.config,
    target_date=request.business_date.isoformat(),
)
stage1 = Stage1Processor(
    data_dir=request.manifest.input_root,
    output_dir=request.paths.stage1,
    stage0_output_dir=request.paths.stage0,
    config=request.config,
)
stage2 = Stage2Processor(
    data_dir=request.manifest.input_root,
    output_dir=request.paths.stage2,
    stage0_output_dir=request.paths.stage0,
    stage1_output_dir=request.paths.stage1,
    config=request.config,
)
~~~

After each `process_all()`, validate the mapping and workbook contract before constructing the next processor. Do not import or call `ArchiveDB`, `daily_archive`, `run_daily`, pretrade code, Wind clients or UI code.

- [x] **Step 5: Verify and commit**

~~~bash
/opt/homebrew/bin/python3 -m pytest -q tests/pipeline/test_execution.py
git diff --check
git add src/pipeline/execution.py tests/pipeline/test_execution.py
git commit -m "test: orchestrate frozen production baseline"
~~~

### Task 5: Produce deterministic logical fingerprints and protected inventories

**Files:**

- Create: `src/testing/output_fingerprint.py`
- Create: `src/testing/protected_inventory.py`
- Test: `tests/testing/test_output_fingerprint.py`
- Test: `tests/testing/test_protected_inventory.py`

**Interfaces:**

- Produces: `canonical_scalar(value)`, `fingerprint_file(path, *, relative_to)`, `fingerprint_tree(root)` and `inventory_tree(root)`.
- The runner in Task 6 serializes these return values directly to JSON.

- [x] **Step 1: Write failing canonical-value tests**

Cover distinct encodings for all supported values:

- null values: `None`, `pd.NA`, `pd.NaT`, floating NaN;
- `pd.Timestamp`, `numpy.datetime64`, `datetime`, `date`, `time`, `timedelta`;
- `Decimal`;
- `bool`, Python and NumPy integers, finite Python and NumPy floats;
- `str`.

Reject positive/negative infinity and unsupported objects. Test bool before int, because `bool` subclasses `int`.

~~~python
def test_canonical_scalar_preserves_semantic_type() -> None:
    assert canonical_scalar(date(2026, 7, 10)) == "date:2026-07-10"
    assert canonical_scalar(datetime(2026, 7, 10, 9, 30)) == "datetime:2026-07-10T09:30:00"
    assert canonical_scalar(1) == "int:1"
    assert canonical_scalar(1.0) == "float:1"
    assert canonical_scalar(True) == "bool:true"
~~~

- [x] **Step 2: Write failing workbook and tree tests**

Tests prove:

- two `.xlsx` files with identical sheet order, cell coordinates, cell value types and values have the same logical SHA despite different ZIP metadata;
- changing a sheet name, cell coordinate, type or value changes the logical SHA;
- CSV fingerprints include ordered rows and fields using UTF-8 with BOM tolerance;
- other files use byte SHA-256 as their logical content hash;
- a tree hash uses only normalized relative path, entry kind and logical content SHA;
- physical byte size and physical SHA are reported beside each file but are **not** included in the tree logical hash.

~~~python
def test_tree_logical_hash_excludes_physical_xlsx_size(tmp_path: Path) -> None:
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    write_equivalent_workbooks_with_different_zip_metadata(left / "a.xlsx", right / "a.xlsx")

    left_fp = fingerprint_tree(left)
    right_fp = fingerprint_tree(right)

    assert left_fp["logical_sha256"] == right_fp["logical_sha256"]
~~~

- [x] **Step 3: Write failing protected-inventory tests**

`inventory_tree(root)` must record, in sorted relative-path order:

- path existence or an explicit missing-root sentinel;
- entry type (`file`, `directory`, `symlink`, `other`);
- POSIX mode;
- symlink target without following it;
- file size and streaming SHA-256.

The before/after JSON objects must compare equal when untouched and unequal for content, mode, entry, symlink-target or existence changes.

- [x] **Step 4: Confirm red**

~~~bash
/opt/homebrew/bin/python3 -m pytest -q \
  tests/testing/test_output_fingerprint.py \
  tests/testing/test_protected_inventory.py
~~~

- [x] **Step 5: Implement canonical logical serialization**

`canonical_scalar` returns a tagged UTF-8 string. Use ISO-8601 for temporal values, `Decimal.normalize()` for decimals and `format(float(value), ".17g")` for finite floats. Normalize floating negative zero to `float:0`. Null detection must occur only after explicit temporal handling so `pd.NaT` becomes `null` rather than a timestamp.

For `.xlsx`, open with `openpyxl.load_workbook(read_only=True, data_only=False, keep_links=False)` and hash this sequence:

~~~text
workbook:v1
sheet:<sheet-index>:<utf8-sheet-name>
cell:<coordinate>:<canonical-scalar>
end-sheet
end-workbook
~~~

Include every non-empty cell in row-major order. Do not hash ZIP member timestamps, workbook creator/modification properties, file size or physical bytes.

For `.csv`, open with `encoding="utf-8-sig"`, `newline=""`; feed every ordered field from `csv.reader` as a length-prefixed UTF-8 string. For other suffixes, the logical content SHA equals the physical SHA.

Return shape:

~~~python
{
    "relative_path": "stage1/example.xlsx",
    "kind": "xlsx",
    "logical_sha256": "...",
    "physical_sha256": "...",
    "physical_size": 12345,
}
~~~

`fingerprint_tree` rejects symlinks and unrecognized non-file entries. Its `logical_sha256` hashes only `relative_path`, `kind` and per-file `logical_sha256` in sorted path order.

- [x] **Step 6: Implement non-following protected inventories**

Use `Path.lstat()` and `os.scandir()` with `follow_symlinks=False`. Never traverse a symlink. A missing root is a valid recorded state so a newly created protected directory is detectable after the run.

- [x] **Step 7: Verify and commit**

~~~bash
/opt/homebrew/bin/python3 -m pytest -q \
  tests/testing/test_output_fingerprint.py \
  tests/testing/test_protected_inventory.py
git diff --check
git add src/testing/output_fingerprint.py src/testing/protected_inventory.py tests/testing
git commit -m "test: fingerprint frozen baseline outputs"
~~~

### Task 6: Enforce the run with a macOS sandboxed two-stage CLI

**Files:**

- Create: `config/test_manifests/frozen-baseline-macos.sb`
- Create: `scripts/run_frozen_baseline.py`
- Test: `tests/scripts/test_run_frozen_baseline.py`
- Test: `tests/scripts/test_frozen_baseline_sandbox.py`

**Interfaces:**

- Parent command accepts `--input-root`, `--manifest`, `--issuer-mapping-file`, `--zero-result-source`, `--allow-output-root`, `--output-name`, `--project-root` and repeated `--protected-root`.
- Parent creates the unique output root and invokes the same script with private `--sandboxed-child` arguments.
- Child writes `<output-root>/baseline_evidence.json` atomically and returns 0 only after all contracts pass.

- [x] **Step 1: Add the static sandbox policy**

~~~scheme
(version 1)
(deny default)
(allow process*)
(allow file-read*)
(allow sysctl-read)
(allow file-write* (literal "/dev/null"))
(allow file-write* (subpath (param "OUTPUT_ROOT")))
~~~

The profile allows process execution and read access required by Python libraries and `mdb-export`; `sysctl-read` is the minimum macOS permission required by NumPy's import-time `os.uname()` call. The real Xcode Git binary requires `/dev/null`, a non-persistent device, for read/write; no other external write path is allowed. All persistent file writes remain limited to the unique output root. Because no network rule is allowed, all network operations remain denied by default.

- [x] **Step 2: Write failing parent-launcher tests**

Patch `subprocess.run` and assert that the parent:

1. calls `assert_test_environment` and manifest validation before creating output;
2. rejects a dirty Git worktree;
3. creates the unique root with `create_unique_test_output` and exact `PipelinePaths` children;
4. executes `/usr/bin/sandbox-exec` with `-D OUTPUT_ROOT=<resolved-root>` and the checked-in profile;
5. executes `/opt/homebrew/bin/python3`, this script and `--sandboxed-child`;
6. sets `HOME=<root>/home`, `TMPDIR=<root>/tmp`, `PYTHONDONTWRITEBYTECODE=1`, `ENV=test`, `LIMIT_MONITOR_PROFILE=local`, `GIT_OPTIONAL_LOCKS=0`, and `PATH=/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin`;
7. forwards every protected root and propagates a non-zero child exit status;
8. never exposes a database URL, archive flag or Wind option.

~~~python
def test_parent_launches_only_the_sandboxed_child(monkeypatch, cli_fixture):
    completed = subprocess.CompletedProcess(args=[], returncode=0)
    run = Mock(return_value=completed)
    monkeypatch.setattr(subprocess, "run", run)

    assert main(cli_fixture.parent_args) == 0

    argv = run.call_args.args[0]
    assert argv[:3] == [
        "/usr/bin/sandbox-exec",
        "-D",
        f"OUTPUT_ROOT={cli_fixture.output_root}",
    ]
    assert "/opt/homebrew/bin/python3" in argv
    assert "--sandboxed-child" in argv
~~~

- [x] **Step 3: Write failing child and evidence tests**

The child rejects direct execution outside the sandbox by performing live probes before reading business input:

- create/delete a probe inside output: must succeed;
- create a probe in the existing allow-output parent, immediately outside this unique output root: must fail with `PermissionError`/`EPERM`;
- bind an IPv4 TCP socket to `127.0.0.1:0`: must fail with `PermissionError`/`EPERM`;
- run `mdb-export --version`: must return 0.

Patch probes in unit tests, but run the real profile in `test_frozen_baseline_sandbox.py`. The integration test launches a small child mode that proves output write succeeds, outside write fails and loopback bind fails without executing Stage0/1/2. Mark it skipped only when `platform.system() != "Darwin"`; on macOS, missing `/usr/bin/sandbox-exec` is a failure.

Evidence tests require this complete structure:

~~~python
{
    "schema_version": 1,
    "status": "success",
    "manifest": {"id": "data_source_0123-20260710-v1", "business_date": "2026-07-10", "files": [...]},
    "git": {"head": "...", "baseline": "579af695...", "baseline_is_ancestor": True, "worktree_clean_before": True},
    "runtime": {
        "python_executable": "/opt/homebrew/bin/python3",
        "python_version": "...",
        "platform": "...",
        "environment": "test",
        "profile": "local",
        "dependencies": {"pandas": "...", "openpyxl": "...", "numpy": "...", "pyyaml": "...", "loguru": "..."},
        "mdb_export": {"path": "...", "version": "...", "binary_sha256": "..."},
    },
    "code": {
        "settings_sha256": "...",
        "runner_sha256": "...",
        "sandbox_profile_sha256": "...",
        "production_scope_diff_is_empty": True,
    },
    "sandbox_probes": {"inside_write": "allowed", "outside_write": "denied", "loopback_bind": "denied"},
    "protected_before": {...},
    "protected_after": {...},
    "protected_unchanged": True,
    "stages": [...],
    "output_fingerprint": {...},
}
~~~

`dependencies` comes from `importlib.metadata.version`; `mdb_export.path` comes from `shutil.which` resolved strictly. Hash the resolved binary, `config/settings.yaml`, runner and sandbox profile. Write evidence to a temporary file inside output, `fsync`, then `os.replace` to `baseline_evidence.json`.

Each evidence `stages` entry contains only stage name, sorted table names, table count, per-table row/column summaries and logical fingerprint. It must not contain the absolute output directory, so two fresh runs can compare exactly.

- [x] **Step 4: Confirm red**

~~~bash
/opt/homebrew/bin/python3 -m pytest -q \
  tests/scripts/test_run_frozen_baseline.py \
  tests/scripts/test_frozen_baseline_sandbox.py
~~~

- [x] **Step 5: Implement the parent path**

The parent performs only validation, output creation and sandbox launch. The Git clean check is:

~~~python
status = subprocess.run(
    [
        "git", "-c", "core.fsmonitor=false", "-c", "core.untrackedCache=false",
        "status", "--porcelain=v1", "--untracked-files=all", "--no-ahead-behind",
    ],
    cwd=project_root,
    check=True,
    capture_output=True,
    text=True,
)
if status.stdout:
    raise UnsafeTestEnvironment("基线运行要求干净工作树")
~~~

Create the output root before `sandbox-exec`; pass all resolved roots to the child. Do not delete a failed output because it is diagnostic evidence. Refuse an existing output name rather than overwriting it.

If the outside-write probe unexpectedly succeeds, delete only that uniquely named probe immediately and then fail the run. This probe occurs before protected inventories and may never delete or modify any pre-existing path.

- [x] **Step 6: Implement the sandboxed child path**

Child order is fixed:

1. re-check `ENV=test`, `LIMIT_MONITOR_PROFILE=local`, Git HEAD and clean state;
2. resolve all paths, require output already exists and is contained by allow-output root;
3. validate the static sandbox-profile SHA received from the parent;
4. run the four live probes;
5. validate the exact input manifest again;
6. inventory input and every protected root;
7. construct `FrozenInputConfig` and `BaselineRunRequest`;
8. call `run_frozen_pipeline` once;
9. fingerprint Stage0/1/2 output trees;
10. inventory protected roots again and require exact equality;
11. require Git clean state again;
12. atomically write success evidence.

On failure, atomically write `baseline_failure.json` inside output with exception class, message and completed guard states, then return non-zero. Never serialize environment variables or secrets.

- [x] **Step 7: Verify and commit**

~~~bash
/opt/homebrew/bin/python3 -m pytest -q \
  tests/scripts/test_run_frozen_baseline.py \
  tests/scripts/test_frozen_baseline_sandbox.py
git diff --check
git add config/test_manifests/frozen-baseline-macos.sb scripts/run_frozen_baseline.py tests/scripts
git commit -m "test: enforce sandboxed frozen baseline run"
~~~

### Task 6A: Use the current static issuer mapping without creating a historical copy

**Files:**

- Create: `src/testing/current_issuer_resolver.py`
- Modify: `scripts/run_frozen_baseline.py`
- Test: `tests/testing/test_current_issuer_resolver.py`
- Test: `tests/scripts/test_run_frozen_baseline.py`

- [x] **Step 1: Freeze the approved boundary**

`issuer_wind_code_mapping.csv` is a non-dated identifier resolver. The runner accepts the current file through `--issuer-mapping-file`, records its size/SHA/row count and copies it only into the isolated Stage0 output. It does not create another historical mapping master.

For deployed zero-result semantics, `--zero-result-source` points to the current `风控部债券池_主体.xlsx`. The guard reads only `发行人名称` and `发行人wind代码`, selects exact numeric zero rows and creates `tmp/temp/wind_codes_result.xlsx` inside the unique sandbox output. Date, pool category and every other column are ignored.

- [x] **Step 2: Validate fail-closed behavior**

Tests prove:

- both sources are ordinary non-symlink files with exact expected names;
- mapping columns are exactly `发行人,wind代码`, values are non-empty and issuer names are unique;
- the zero source contains the two required columns and at least one explicit numeric zero;
- both hashes are stable across validation and staging;
- staged targets are fixed under `stage0` and `tmp/temp` and refuse pre-existing targets;
- source bytes remain unchanged;
- evidence contains hashes/counts/names but no absolute source path.

- [x] **Step 3: Verify and commit**

~~~bash
/opt/homebrew/bin/python3 -m pytest -q \
  tests/testing/test_current_issuer_resolver.py \
  tests/scripts/test_run_frozen_baseline.py
git diff --check
git add docs src/testing/current_issuer_resolver.py scripts/run_frozen_baseline.py tests
git commit -m "test: use current static issuer resolver"
~~~

### Task 6B: Recreate the deployed nested ConfigLoader path without changing production code

**Root cause evidence:** `LimitDetailCalculator._load_regulatory_concentration_limit()` creates a new `ConfigLoader()` and therefore reads `project_root/data_source_0123/限额配置_当前.xlsx`. The isolated worktree intentionally has no `data_source_0123`, while all other Stage1 configuration reads use `FrozenInputConfig` correctly.

**Files:**

- Create: `src/testing/legacy_local_compat.py`
- Modify: `scripts/run_frozen_baseline.py`
- Test: `tests/testing/test_legacy_local_compat.py`
- Test: `tests/scripts/test_run_frozen_baseline.py`

- [x] **Step 1: Reproduce the missing deployed path**

The first current-mapping full run reached Stage1 and failed at `限额明细_单一债券` with `project_root/data_source_0123/限额配置_当前.xlsx` missing. Stage0 had already reached 100% issuer-code coverage. The failed output remains external diagnostic evidence and is not gold.

- [x] **Step 2: Implement one-file compatibility staging**

The parent copies only the already-hashed frozen `限额配置_当前.xlsx` to the exact ignored local path before launching the sandbox. The child validates its expected relative path and SHA, includes it in protected before/after inventories and records compact evidence. A `finally` cleanup removes it only when the file hash is unchanged and the created directory contains no other entry.

The production processor, `LimitDetailCalculator`, `ConfigLoader`, settings and limit formulas remain byte-identical to `579af695...`.

- [x] **Step 3: Verify**

~~~bash
/opt/homebrew/bin/python3 -m pytest -q \
  tests/testing/test_legacy_local_compat.py \
  tests/scripts/test_run_frozen_baseline.py
ENV=test LIMIT_MONITOR_PROFILE=local /opt/homebrew/bin/python3 -m pytest -q
test ! -e data_source_0123
git diff --exit-code 579af695fb8727dec8249f66d07a8b0e723da137 -- \
  src/stage0 src/stage1 src/stage2 src/common src/utils \
  config/settings.yaml scripts/daily_archive.py
~~~

### Task 7: Run and independently seal the 2026-07-10 production gold sample

Execution record: the formal repeatability pair is `pretrade-baseline-20260710-compat3`
and `pretrade-baseline-20260710-compat4`, both produced from Git HEAD
`b10fd6e115d5963bb91cb9513703e5cc7d5fec5f`. `compat2` is retained as a failed
diagnostic run: all three processors completed, but the original protected inventory
correctly refused to seal evidence after macOS rewrote `.DS_Store`. The inventory now
excludes only that platform metadata file and continues to hash every business artifact.

**Files:**

- Create: `docs/evidence/pretrade-baseline-20260710.json`
- Verify only: `src/stage0/**`, `src/stage1/**`, `src/stage2/**`, `src/common/**`, `src/utils/**`, `config/settings.yaml`, `scripts/daily_archive.py`

- [x] **Step 1: Verify ancestry and zero production-scope drift**

~~~bash
git merge-base --is-ancestor 579af695fb8727dec8249f66d07a8b0e723da137 HEAD
git diff --exit-code 579af695fb8727dec8249f66d07a8b0e723da137 -- \
  src/stage0 src/stage1 src/stage2 src/common src/utils \
  config/settings.yaml scripts/daily_archive.py
git status --short
~~~

Expected: both Git checks exit 0; the production-scope diff and status are empty. If either fails, stop. Do not bless the output.

- [x] **Step 2: Run all tests before the full calculation**

~~~bash
ENV=test LIMIT_MONITOR_PROFILE=local \
  /opt/homebrew/bin/python3 -m pytest -q
~~~

Expected: all tests pass; only documented dependency/platform skips are permitted.

- [x] **Step 3: Create the external allow-root and run once**

~~~bash
mkdir -p /Users/dellawang/Desktop/LimitMonitorAutomation-test-output
ENV=test LIMIT_MONITOR_PROFILE=local \
  /opt/homebrew/bin/python3 scripts/run_frozen_baseline.py \
  --input-root /Users/dellawang/Desktop/LimitMonitorAutomation/data_source_0123 \
  --manifest config/test_manifests/data_source_0123-20260710-v1.json \
  --issuer-mapping-file /Users/dellawang/Desktop/LimitMonitorAutomation/data/current/stage0_output/issuer_wind_code_mapping.csv \
  --zero-result-source /Users/dellawang/Desktop/LimitMonitorAutomation/data/current/stage0_output/风控部债券池_主体.xlsx \
  --allow-output-root /Users/dellawang/Desktop/LimitMonitorAutomation-test-output \
  --output-name pretrade-baseline-20260710-compat3 \
  --project-root "$PWD" \
  --protected-root /Users/dellawang/Desktop/LimitMonitorAutomation/data/current \
  --protected-root /Users/dellawang/Desktop/LimitMonitorAutomation/data/archive \
  --protected-root "$PWD/data/current" \
  --protected-root "$PWD/data/archive"
~~~

Expected: exit 0 and exactly one new output root. No database service, Wind service or existing archive is needed.

- [x] **Step 4: Audit the generated evidence before copying it**

~~~bash
/opt/homebrew/bin/python3 - <<'PY'
import json
from pathlib import Path

p = Path("/Users/dellawang/Desktop/LimitMonitorAutomation-test-output/pretrade-baseline-20260710-compat3/baseline_evidence.json")
d = json.loads(p.read_text(encoding="utf-8"))
assert d["status"] == "success"
assert d["manifest"]["id"] == "data_source_0123-20260710-v1"
assert d["manifest"]["business_date"] == "2026-07-10"
assert d["git"]["baseline_is_ancestor"] is True
assert d["code"]["production_scope_diff_is_empty"] is True
assert d["sandbox_probes"] == {
    "inside_write": "allowed",
    "outside_write": "denied",
    "loopback_bind": "denied",
}
assert d["protected_unchanged"] is True
assert [s["stage"] for s in d["stages"]] == ["stage0", "stage1", "stage2"]
assert all(s["table_count"] > 0 for s in d["stages"])
print(d["output_fingerprint"]["logical_sha256"])
PY
~~~

Expected: assertions pass and one logical SHA-256 is printed. Manually inspect `baseline_failure.json` only when the command fails; never convert a failed run into gold.

- [x] **Step 5: Prove repeatability with a second fresh output**

Repeat Step 3 with `--output-name pretrade-baseline-20260710-compat4`, then compare:

~~~bash
/opt/homebrew/bin/python3 - <<'PY'
import json
from pathlib import Path

root = Path("/Users/dellawang/Desktop/LimitMonitorAutomation-test-output")
a = json.loads((root / "pretrade-baseline-20260710-compat3/baseline_evidence.json").read_text(encoding="utf-8"))
b = json.loads((root / "pretrade-baseline-20260710-compat4/baseline_evidence.json").read_text(encoding="utf-8"))

def logical_stage(stage):
    return {
        "stage": stage["stage"],
        "table_count": stage["table_count"],
        "tables": stage["tables"],
        "logical_sha256": stage["logical_fingerprint"]["logical_sha256"],
        "entries": [
            {key: entry[key] for key in ("relative_path", "kind", "logical_sha256")}
            for entry in stage["logical_fingerprint"]["entries"]
        ],
    }

assert a["git"]["head"] == b["git"]["head"]
assert a["output_fingerprint"] == b["output_fingerprint"]
assert [logical_stage(stage) for stage in a["stages"]] == [
    logical_stage(stage) for stage in b["stages"]
]
print("repeatable")
PY
~~~

Expected: `repeatable`. Physical `.xlsx` SHA or size may differ and is not a failure when logical fingerprints match.

- [x] **Step 6: Copy only compact evidence and independently review it**

Copy run1's evidence JSON to `docs/evidence/pretrade-baseline-20260710.json`. Replace absolute output-root fields with the literal `<external-output-root>` only; do not change hashes, row counts, schema, runtime facts or guard results.

~~~bash
/opt/homebrew/bin/python3 - <<'PY'
import json
from pathlib import Path

source_root = Path("/Users/dellawang/Desktop/LimitMonitorAutomation-test-output/pretrade-baseline-20260710-compat3")
source = source_root / "baseline_evidence.json"
target = Path("docs/evidence/pretrade-baseline-20260710.json")

def redact(value):
    if isinstance(value, dict):
        return {key: redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return value.replace(str(source_root), "<external-output-root>")
    return value

payload = redact(json.loads(source.read_text(encoding="utf-8")))
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(
    json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
    encoding="utf-8",
)
PY
~~~

Review checklist:

- every manifest file hash matches the frozen manifest;
- baseline ancestry and zero production-scope drift are true;
- runtime executable and dependency versions are present;
- sandbox profile, runner, settings and mdb-export hashes are present;
- all protected before/after inventories match;
- both runs have the same logical tree hash and table summaries;
- no DB URL, credentials, environment dump or personal secret appears;
- Stage0/1/2 output directories remain outside Git and are not committed.

- [x] **Step 7: Run the final verification and commit**

~~~bash
ENV=test LIMIT_MONITOR_PROFILE=local \
  /opt/homebrew/bin/python3 -m pytest -q
git diff --check
git status --short
git add docs/evidence/pretrade-baseline-20260710.json
git commit -m "test: seal pretrade production gold sample"
~~~

Expected: all tests pass and the commit contains only compact evidence.

## Completion Gate

This plan is complete only when all of the following are true:

- GitHub deployed baseline ancestry is proven and production calculation scope has zero diff.
- Exact 12-file manifest and business date 2026-07-10 are verified twice.
- Current static issuer mapping and explicit-zero source are hashed, read-only, separately evidenced and unchanged across both runs.
- Stage0 → Stage1 → Stage2 run through the deployed processor classes without archive/database/Wind/UI code.
- A real macOS sandbox proves writes are restricted to the unique output and network is denied.
- Legal empty tables are accepted; swallowed failures and missing workbooks fail closed.
- Input, current, archive and worktree business-artifact inventories are byte-for-byte
  unchanged; macOS `.DS_Store` metadata is explicitly excluded.
- Two fresh runs have identical logical fingerprints and stage summaries.
- Compact evidence is independently reviewed and committed.
- Only after this gate may the shared business kernel implementation plan begin.
