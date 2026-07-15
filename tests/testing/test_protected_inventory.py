import os
from pathlib import Path

from src.testing.protected_inventory import inventory_tree


def test_missing_root_has_explicit_stable_sentinel(tmp_path: Path) -> None:
    missing = tmp_path / "missing"

    before = inventory_tree(missing)
    after = inventory_tree(missing)

    assert before == after
    assert before["exists"] is False
    assert before["root_type"] == "missing"
    assert before["entries"] == []


def test_unchanged_inventory_is_equal(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "a.txt").write_text("same", encoding="utf-8")

    assert inventory_tree(root) == inventory_tree(root)


def test_content_or_mode_change_changes_inventory(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    file = root / "a.txt"
    file.write_text("before", encoding="utf-8")
    before = inventory_tree(root)

    file.write_text("after", encoding="utf-8")
    os.chmod(file, 0o600)
    after = inventory_tree(root)

    assert before != after
    entry = after["entries"][0]
    assert entry["type"] == "file"
    assert entry["mode"] == "0600"
    assert entry["size"] == len(b"after")
    assert len(entry["sha256"]) == 64


def test_symlink_target_is_recorded_without_following(tmp_path: Path) -> None:
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (outside / "secret").write_text("outside", encoding="utf-8")
    (root / "link").symlink_to(outside, target_is_directory=True)

    inventory = inventory_tree(root)

    assert inventory["entries"] == [
        {
            "path": "link",
            "type": "symlink",
            "mode": inventory["entries"][0]["mode"],
            "target": str(outside),
        }
    ]
    assert all(entry["path"] != "link/secret" for entry in inventory["entries"])


def test_new_entry_or_root_creation_changes_inventory(tmp_path: Path) -> None:
    root = tmp_path / "root"
    before = inventory_tree(root)
    root.mkdir()
    (root / "new.txt").write_text("new", encoding="utf-8")

    assert before != inventory_tree(root)
