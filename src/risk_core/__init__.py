"""Pure production risk-calculation boundary.

This package accepts already-loaded pandas frames.  File, database, network,
configuration and processor adapters intentionally live outside this package.
"""

from .contracts import (
    STAGE1_REQUIRED_FRAMES,
    STAGE2_REQUIRED_FRAMES,
    STAGE2_REQUIRED_STAGE1_TABLES,
    MissingKernelFramesError,
    ProductionKernelInput,
    ProductionKernelParameters,
    ProductionKernelResult,
)
from .kernel import ProductionRiskKernel

__all__ = [
    "STAGE1_REQUIRED_FRAMES",
    "STAGE2_REQUIRED_FRAMES",
    "STAGE2_REQUIRED_STAGE1_TABLES",
    "MissingKernelFramesError",
    "ProductionKernelInput",
    "ProductionKernelParameters",
    "ProductionKernelResult",
    "ProductionRiskKernel",
]
