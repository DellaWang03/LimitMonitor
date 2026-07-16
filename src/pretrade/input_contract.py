"""交易前共同内核输入的最小、固定契约。"""

from __future__ import annotations

from dataclasses import dataclass

from src.risk_core import (
    STAGE1_REQUIRED_FRAMES,
    STAGE2_REQUIRED_FRAMES,
    ProductionKernelInput,
)

KERNEL_INPUT_DATASETS = tuple(dict.fromkeys(STAGE1_REQUIRED_FRAMES + STAGE2_REQUIRED_FRAMES))


class PretradeInputContractError(ValueError):
    """交易前输入未满足共同内核重放契约。"""


def _validate_frames(kernel_input: ProductionKernelInput) -> None:
    actual = set(kernel_input.frames)
    expected = set(KERNEL_INPUT_DATASETS)
    missing = tuple(name for name in KERNEL_INPUT_DATASETS if name not in actual)
    extra = tuple(sorted(actual - expected))
    if missing:
        raise PretradeInputContractError(f"缺少共同内核输入: {', '.join(missing)}")
    if extra:
        raise PretradeInputContractError(f"存在未注册输入: {', '.join(extra)}")


@dataclass(frozen=True)
class PretradeSnapshotRequest:
    """一次待持久化交易前上下文的不可变描述。"""

    kernel_input: ProductionKernelInput

    @classmethod
    def from_kernel_input(
        cls, kernel_input: ProductionKernelInput
    ) -> "PretradeSnapshotRequest":
        """校验共同内核唯一的 27 项外部输入。"""

        if not isinstance(kernel_input, ProductionKernelInput):
            raise PretradeInputContractError("kernel_input 必须是 ProductionKernelInput")
        _validate_frames(kernel_input)
        return cls(kernel_input=kernel_input)
