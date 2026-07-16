from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from src.common.access_reader import AccessDatabaseReader


def test_mdb_export_streams_stdout_directly_to_csv(monkeypatch, tmp_path: Path):
    """Large Access tables must not be buffered in process memory before writing."""
    accdb_path = tmp_path / "source.accdb"
    accdb_path.touch()
    export_dir = tmp_path / "exports"
    calls: list[dict[str, object]] = []

    def fake_run(command, *, stdout, stderr, text, timeout):
        calls.append(
            {
                "command": command,
                "stdout": stdout,
                "stderr": stderr,
                "text": text,
                "timeout": timeout,
            }
        )
        stdout.write("日期,代码\\n2026-01-01,TEST.IB\\n")
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr("src.common.access_reader.subprocess.run", fake_run)
    reader = AccessDatabaseReader(accdb_path)

    assert reader._try_mdb_export("风控部债券池", accdb_path, export_dir) is True
    assert (export_dir / "风控部债券池.csv").read_text(encoding="utf-8") == (
        "日期,代码\\n2026-01-01,TEST.IB\\n"
    )
    assert calls == [
        {
            "command": ["mdb-export", str(accdb_path), "风控部债券池"],
            "stdout": calls[0]["stdout"],
            "stderr": -1,
            "text": True,
            "timeout": 600,
        }
    ]

