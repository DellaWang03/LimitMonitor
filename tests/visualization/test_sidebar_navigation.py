from __future__ import annotations

import ast
from pathlib import Path


def _sidebar_page_names() -> list[str]:
    source_path = Path("src/visualization/components/sidebar.py")
    tree = ast.parse(source_path.read_text(encoding="utf-8"))

    pages_assignment = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "pages" for target in node.targets)
    )
    pages = ast.literal_eval(pages_assignment.value)
    return [name for name, _emoji in pages]


def test_sidebar_hides_full_regulatory_concentration_page() -> None:
    """暂时隐藏全量债券监管集中度页面的侧边栏入口。"""

    assert "全量债券监管集中度" not in _sidebar_page_names()
