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
    """完整原始文件及其逐字节校验值。"""

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
    """从 Stage1 已使用的配置对象取得限额工作簿原件。"""

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
