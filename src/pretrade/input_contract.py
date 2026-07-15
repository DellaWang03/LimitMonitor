"""交易前共同内核输入的最小、固定契约。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
import json

from src.risk_core import (
    STAGE1_REQUIRED_FRAMES,
    STAGE2_REQUIRED_FRAMES,
    ProductionKernelInput,
)

from .frame_codec import serialize_frame


INPUT_CONTRACT_VERSION = "pretrade-input-v1"
KERNEL_INPUT_DATASETS = tuple(dict.fromkeys(STAGE1_REQUIRED_FRAMES + STAGE2_REQUIRED_FRAMES))
ALLOWED_USAGES = frozenset({"DEV", "PROD"})


class PretradeInputContractError(ValueError):
    """交易前输入未满足共同内核重放契约。"""


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    except (TypeError, ValueError) as exc:
        raise PretradeInputContractError("来源清单不可序列化") from exc


def _sha256_text(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _validate_frames(kernel_input: ProductionKernelInput) -> None:
    actual = set(kernel_input.frames)
    expected = set(KERNEL_INPUT_DATASETS)
    missing = tuple(name for name in KERNEL_INPUT_DATASETS if name not in actual)
    extra = tuple(sorted(actual - expected))
    if missing:
        raise PretradeInputContractError(f"缺少共同内核输入: {', '.join(missing)}")
    if extra:
        raise PretradeInputContractError(f"存在未注册输入: {', '.join(extra)}")


def _validate_source_manifest(source_manifest: Mapping[str, object]) -> None:
    if not isinstance(source_manifest, Mapping):
        raise PretradeInputContractError("来源清单必须是映射")
    required = ("files", "static_issuer_mapping", "captured_at")
    missing = [name for name in required if name not in source_manifest]
    if missing:
        raise PretradeInputContractError(f"来源清单缺少字段: {', '.join(missing)}")


def _build_input_hash(kernel_input: ProductionKernelInput) -> str:
    """按固定表顺序散列 27 张表，调用方字典的插入顺序不会影响结果。"""

    frame_hashes = [
        {
            "dataset_code": dataset_code,
            "content_hash": serialize_frame(kernel_input.frames[dataset_code]).content_hash,
        }
        for dataset_code in KERNEL_INPUT_DATASETS
    ]
    payload = {
        "business_date": str(kernel_input.business_date.date()),
        "parameters": {
            "regulatory_concentration_limit": kernel_input.parameters.regulatory_concentration_limit,
        },
        "frames": frame_hashes,
    }
    return _sha256_text(_canonical_json(payload))


@dataclass(frozen=True)
class PretradeSnapshotRequest:
    """一次待持久化交易前上下文的不可变描述。"""

    usage: str
    kernel_input: ProductionKernelInput
    code_commit: str
    engine_version: str
    input_contract_version: str
    source_manifest: Mapping[str, object]
    source_manifest_hash: str
    input_hash: str

    @classmethod
    def build(
        cls,
        *,
        usage: str,
        kernel_input: ProductionKernelInput,
        source_manifest: Mapping[str, object],
        code_commit: str = "",
        engine_version: str = "risk-core-v1",
        input_contract_version: str = INPUT_CONTRACT_VERSION,
    ) -> "PretradeSnapshotRequest":
        if usage not in ALLOWED_USAGES:
            raise PretradeInputContractError("usage 仅允许 DEV 或 PROD")
        if not isinstance(kernel_input, ProductionKernelInput):
            raise PretradeInputContractError("kernel_input 必须是 ProductionKernelInput")
        _validate_frames(kernel_input)
        _validate_source_manifest(source_manifest)
        canonical_manifest = _canonical_json(source_manifest)
        return cls(
            usage=usage,
            kernel_input=kernel_input,
            code_commit=code_commit,
            engine_version=engine_version,
            input_contract_version=input_contract_version,
            source_manifest=json.loads(canonical_manifest),
            source_manifest_hash=_sha256_text(canonical_manifest),
            input_hash=_build_input_hash(kernel_input),
        )

    @classmethod
    def from_kernel_input(
        cls,
        kernel_input: ProductionKernelInput,
        *,
        usage: str,
        source_manifest: Mapping[str, object],
        code_commit: str = "",
        engine_version: str = "risk-core-v1",
        input_contract_version: str = INPUT_CONTRACT_VERSION,
    ) -> "PretradeSnapshotRequest":
        """以直观名称创建请求；保留为后续调用方的唯一入口。"""

        return cls.build(
            usage=usage,
            kernel_input=kernel_input,
            source_manifest=source_manifest,
            code_commit=code_commit,
            engine_version=engine_version,
            input_contract_version=input_contract_version,
        )
