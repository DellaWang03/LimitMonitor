from __future__ import annotations

import ast
from pathlib import Path
import subprocess
import sys


RISK_CORE = Path(__file__).parents[2] / "src" / "risk_core"
REPOSITORY_ROOT = Path(__file__).parents[2]
FORBIDDEN_IMPORT_ROOTS = {
    "pathlib",
    "os",
    "requests",
    "urllib",
    "httpx",
    "sqlalchemy",
    "pyodbc",
}
FORBIDDEN_IMPORT_FRAGMENTS = {
    "config_loader",
    "limit_config_loader",
    "archive_db",
    "wind",
    "stage1_processor",
    "stage2_processor",
    "pretrade",
}
FORBIDDEN_CALL_NAMES = {"open", "Path"}
FORBIDDEN_ATTRIBUTE_CALLS = {
    "read_excel",
    "to_excel",
    "read_csv",
    "to_csv",
    "read_sql",
    "to_sql",
    "urlopen",
    "getenv",
}


def test_risk_core_exists_and_contains_only_pure_python_modules():
    assert RISK_CORE.is_dir()
    assert {path.name for path in RISK_CORE.glob("*.py")} >= {
        "__init__.py",
        "contracts.py",
        "kernel.py",
    }


def test_risk_core_has_no_file_database_network_config_or_processor_io():
    violations: list[str] = []
    for path in sorted(RISK_CORE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    if root in FORBIDDEN_IMPORT_ROOTS:
                        violations.append(f"{path.name}:{node.lineno}: import {alias.name}")
                    if any(fragment in alias.name.lower() for fragment in FORBIDDEN_IMPORT_FRAGMENTS):
                        violations.append(f"{path.name}:{node.lineno}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                root = module.split(".")[0]
                if root in FORBIDDEN_IMPORT_ROOTS:
                    violations.append(f"{path.name}:{node.lineno}: from {module}")
                if any(fragment in module.lower() for fragment in FORBIDDEN_IMPORT_FRAGMENTS):
                    violations.append(f"{path.name}:{node.lineno}: from {module}")
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_CALL_NAMES:
                    violations.append(f"{path.name}:{node.lineno}: call {node.func.id}")
                if isinstance(node.func, ast.Attribute) and node.func.attr in FORBIDDEN_ATTRIBUTE_CALLS:
                    violations.append(f"{path.name}:{node.lineno}: call .{node.func.attr}")

    assert violations == []


def test_importing_risk_core_does_not_transitively_load_io_modules():
    forbidden_modules = (
        "src.common.access_reader",
        "src.common.wind_code_resolver",
        "src.common.wind_code_excel_helper",
        "src.common.financial_tool_pool",
    )
    code = f"""
import sys
import src.risk_core

forbidden = {forbidden_modules!r}
loaded = sorted(name for name in forbidden if name in sys.modules)
if loaded:
    raise SystemExit("transitive I/O imports: " + ", ".join(loaded))
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
