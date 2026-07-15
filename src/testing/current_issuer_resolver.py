"""Validate current static issuer identifiers and stage them for an isolated run."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import stat

import pandas as pd

from ..pipeline.paths import PipelinePaths


class CurrentIssuerResolverError(RuntimeError):
    """Current issuer resolver sources are unsafe or internally inconsistent."""


@dataclass(frozen=True)
class ValidatedCurrentIssuerResolver:
    mapping_file: Path
    zero_result_source: Path
    mapping_size: int
    mapping_sha256: str
    zero_result_source_size: int
    zero_result_source_sha256: str
    mapping_row_count: int
    zero_results: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class StagedCurrentIssuerResolver:
    mapping_file: Path
    result_file: Path


def validate_current_issuer_resolver(
    mapping_file: Path | str,
    zero_result_source: Path | str,
) -> ValidatedCurrentIssuerResolver:
    """Read only the current mapping and explicit zero identifier results."""

    mapping = _resolve_file(
        Path(mapping_file),
        "当前 issuer_wind_code_mapping.csv",
        expected_name="issuer_wind_code_mapping.csv",
    )
    zero_source = _resolve_file(
        Path(zero_result_source),
        "当前风控部债券池_主体.xlsx",
        expected_name="风控部债券池_主体.xlsx",
    )
    mapping_hash_before = _sha256_file(mapping)
    zero_hash_before = _sha256_file(zero_source)
    try:
        mapping_frame = pd.read_csv(mapping, dtype=str, keep_default_na=False)
    except Exception as exc:
        raise CurrentIssuerResolverError(f"当前主体代码映射无法读取: {exc}") from exc
    if list(mapping_frame.columns) != ["发行人", "wind代码"]:
        raise CurrentIssuerResolverError(
            "当前主体代码映射列必须严格为 发行人、wind代码"
        )
    mapping_frame["发行人"] = mapping_frame["发行人"].astype(str).str.strip()
    mapping_frame["wind代码"] = mapping_frame["wind代码"].astype(str).str.strip()
    if mapping_frame.empty:
        raise CurrentIssuerResolverError("当前主体代码映射为空")
    if mapping_frame[["发行人", "wind代码"]].eq("").any().any():
        raise CurrentIssuerResolverError("当前主体代码映射包含空名称或空代码")
    if mapping_frame["发行人"].duplicated(keep=False).any():
        duplicates = sorted(
            mapping_frame.loc[
                mapping_frame["发行人"].duplicated(keep=False), "发行人"
            ].unique()
        )
        raise CurrentIssuerResolverError(
            f"当前主体代码映射包含重复发行人: {duplicates[:20]}"
        )

    try:
        zero_frame = pd.read_excel(zero_source, dtype=object)
    except Exception as exc:
        raise CurrentIssuerResolverError(f"当前主体池输出无法读取: {exc}") from exc
    required = {"发行人名称", "发行人wind代码"}
    missing = required - set(zero_frame.columns)
    if missing:
        raise CurrentIssuerResolverError(
            f"当前主体池输出缺少列: {sorted(missing)}"
        )
    names = zero_frame["发行人名称"].fillna("").astype(str).str.strip()
    numeric_codes = pd.to_numeric(zero_frame["发行人wind代码"], errors="coerce")
    zero_names = names[numeric_codes.eq(0) & names.ne("")]
    if zero_names.empty:
        raise CurrentIssuerResolverError("当前主体池输出没有明确 Wind代码=0 的记录")
    if zero_names.duplicated(keep=False).any():
        duplicates = sorted(zero_names[zero_names.duplicated(keep=False)].unique())
        raise CurrentIssuerResolverError(
            f"当前主体池零代码结果包含重复发行人: {duplicates[:20]}"
        )
    zero_results = tuple((name, "0") for name in zero_names.tolist())

    mapping_hash_after = _sha256_file(mapping)
    zero_hash_after = _sha256_file(zero_source)
    if mapping_hash_before != mapping_hash_after or zero_hash_before != zero_hash_after:
        raise CurrentIssuerResolverError("校验期间当前主体解析源文件发生变化")
    return ValidatedCurrentIssuerResolver(
        mapping_file=mapping,
        zero_result_source=zero_source,
        mapping_size=mapping.stat().st_size,
        mapping_sha256=mapping_hash_after,
        zero_result_source_size=zero_source.stat().st_size,
        zero_result_source_sha256=zero_hash_after,
        mapping_row_count=len(mapping_frame),
        zero_results=zero_results,
    )


def stage_current_issuer_resolver(
    resolver: ValidatedCurrentIssuerResolver,
    paths: PipelinePaths,
) -> StagedCurrentIssuerResolver:
    """Copy current mapping and build only the isolated To_WindCode session result."""

    mapping_target = paths.stage0 / "issuer_wind_code_mapping.csv"
    temp_target_dir = paths.tmp / "temp"
    result_target = temp_target_dir / "wind_codes_result.xlsx"
    if mapping_target.exists() or mapping_target.is_symlink():
        raise CurrentIssuerResolverError(f"主体解析目标已存在: {mapping_target}")
    if temp_target_dir.exists() or temp_target_dir.is_symlink():
        raise CurrentIssuerResolverError(f"主体解析目标已存在: {temp_target_dir}")
    if _sha256_file(resolver.mapping_file) != resolver.mapping_sha256:
        raise CurrentIssuerResolverError("当前主体代码映射在复制前发生变化")
    if (
        _sha256_file(resolver.zero_result_source)
        != resolver.zero_result_source_sha256
    ):
        raise CurrentIssuerResolverError("当前主体池零代码来源在生成前发生变化")

    created: list[Path] = []
    try:
        temp_target_dir.mkdir(mode=0o700, parents=False, exist_ok=False)
        created.append(temp_target_dir)
        _copy_verified(
            resolver.mapping_file,
            mapping_target,
            expected_size=resolver.mapping_size,
            expected_sha256=resolver.mapping_sha256,
        )
        created.append(mapping_target)
        pd.DataFrame(
            resolver.zero_results,
            columns=["发行人名称", "Wind代码"],
        ).to_excel(result_target, index=False, sheet_name="Wind代码查询")
        created.append(result_target)
        result_frame = pd.read_excel(result_target, dtype=str, keep_default_na=False)
        actual = tuple(
            (str(row["发行人名称"]).strip(), str(row["Wind代码"]).strip())
            for _, row in result_frame.iterrows()
        )
        if actual != resolver.zero_results:
            raise CurrentIssuerResolverError("隔离 To_WindCode 会话结果回读不一致")
        if (
            _sha256_file(resolver.zero_result_source)
            != resolver.zero_result_source_sha256
        ):
            raise CurrentIssuerResolverError("生成期间当前主体池零代码来源发生变化")
    except Exception:
        for path in reversed(created):
            try:
                path.unlink() if path.is_file() else path.rmdir()
            except OSError:
                pass
        raise
    return StagedCurrentIssuerResolver(
        mapping_file=mapping_target.resolve(strict=True),
        result_file=result_target.resolve(strict=True),
    )


def _resolve_file(path: Path, label: str, *, expected_name: str) -> Path:
    if path.name != expected_name:
        raise CurrentIssuerResolverError(
            f"{label}文件名必须为 {expected_name}: {path.name}"
        )
    if path.is_symlink():
        raise CurrentIssuerResolverError(f"{label}不得为符号链接: {path}")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise CurrentIssuerResolverError(f"{label}不存在: {path}") from exc
    if not resolved.is_file():
        raise CurrentIssuerResolverError(f"{label}不是普通文件: {resolved}")
    return resolved


def _copy_verified(
    source: Path,
    target: Path,
    *,
    expected_size: int,
    expected_sha256: str,
) -> None:
    source_fd: int | None = None
    target_fd: int | None = None
    digest = hashlib.sha256()
    total = 0
    try:
        source_fd = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        metadata = os.fstat(source_fd)
        if not stat.S_ISREG(metadata.st_mode):
            raise CurrentIssuerResolverError(f"映射源不再是普通文件: {source}")
        target_fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        while True:
            chunk = os.read(source_fd, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            total += len(chunk)
            view = memoryview(chunk)
            while view:
                written = os.write(target_fd, view)
                view = view[written:]
        os.fsync(target_fd)
    except FileExistsError as exc:
        raise CurrentIssuerResolverError(f"主体解析目标已存在: {target}") from exc
    except OSError as exc:
        raise CurrentIssuerResolverError(f"复制当前主体映射失败: {exc}") from exc
    finally:
        if source_fd is not None:
            os.close(source_fd)
        if target_fd is not None:
            os.close(target_fd)
    if total != expected_size or digest.hexdigest() != expected_sha256:
        try:
            target.unlink()
        except OSError:
            pass
        raise CurrentIssuerResolverError("复制期间当前主体代码映射发生变化")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    descriptor: int | None = None
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise CurrentIssuerResolverError(f"哈希目标不再是普通文件: {path}")
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = None
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise CurrentIssuerResolverError(f"无法哈希主体解析源文件: {path}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
    return digest.hexdigest()
