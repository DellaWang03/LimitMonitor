"""Per-run output paths for an isolated Stage0/1/2 execution."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class PipelinePathError(RuntimeError):
    """The pipeline root cannot safely host a fresh isolated run."""


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

    @property
    def children(self) -> tuple[Path, ...]:
        return (
            self.stage0,
            self.stage1,
            self.stage2,
            self.logs,
            self.access_export,
            self.tmp,
            self.home,
        )

    @classmethod
    def create(cls, root: Path | str) -> "PipelinePaths":
        raw_root = Path(root)
        if raw_root.is_symlink():
            raise PipelinePathError(f"流水线根目录不得为符号链接: {raw_root}")
        try:
            resolved = raw_root.resolve(strict=True)
        except OSError as exc:
            raise PipelinePathError(f"流水线根目录不存在: {raw_root}") from exc
        if not resolved.is_dir():
            raise PipelinePathError(f"流水线根路径不是目录: {resolved}")
        if any(resolved.iterdir()):
            raise PipelinePathError(f"流水线根目录必须为空: {resolved}")

        names = ("stage0", "stage1", "stage2", "logs", "access_export", "tmp", "home")
        created: list[Path] = []
        try:
            for name in names:
                path = resolved / name
                path.mkdir(mode=0o700, parents=False, exist_ok=False)
                created.append(path.resolve(strict=True))
        except Exception:
            for path in reversed(created):
                try:
                    path.rmdir()
                except OSError:
                    pass
            raise

        return cls(root=resolved, **dict(zip(names, created, strict=True)))
