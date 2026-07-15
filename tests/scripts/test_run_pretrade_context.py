from __future__ import annotations

import pytest

from scripts import run_pretrade_context as runner


def test_cli_accepts_only_the_explicit_dev_surface() -> None:
    parser = runner._build_parser()
    destinations = {action.dest for action in parser._actions}

    assert {"input_root", "manifest", "allow_output_root", "output", "usage", "note"} <= destinations
    assert destinations.isdisjoint(
        {"publish", "data_date", "archive_date", "wind", "database_url", "reference"}
    )


def test_cli_rejects_prod_usage_before_any_runtime_or_database_work() -> None:
    with pytest.raises(SystemExit) as exc_info:
        runner._build_parser().parse_args(
            [
                "--input-root",
                "/tmp/input",
                "--manifest",
                "/tmp/manifest.json",
                "--allow-output-root",
                "/tmp/output",
                "--output",
                "/tmp/output/new",
                "--usage",
                "PROD",
            ]
        )

    assert exc_info.value.code == 2


def test_cli_defaults_to_dev() -> None:
    args = runner._build_parser().parse_args(
        [
            "--input-root",
            "/tmp/input",
            "--manifest",
            "/tmp/manifest.json",
            "--allow-output-root",
            "/tmp/output",
            "--output",
            "/tmp/output/new",
        ]
    )

    assert args.usage == "DEV"
