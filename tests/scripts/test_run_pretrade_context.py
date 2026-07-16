from __future__ import annotations

import pytest

from scripts import run_pretrade_context as runner


def test_cli_accepts_only_the_frozen_acceptance_surface() -> None:
    parser = runner._build_parser()
    destinations = {action.dest for action in parser._actions}

    assert {"input_root", "manifest", "allow_output_root", "output", "note"} <= destinations
    assert destinations.isdisjoint(
        {
            "publish",
            "data_date",
            "archive_date",
            "wind",
            "database_url",
            "reference",
            "usage",
        }
    )


def test_cli_rejects_removed_usage_option() -> None:
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
                "--usage=DEV",
            ]
        )

    assert exc_info.value.code == 2
