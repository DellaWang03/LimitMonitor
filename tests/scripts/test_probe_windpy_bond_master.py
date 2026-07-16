from __future__ import annotations

import json

import pandas as pd

from scripts import probe_windpy_bond_master as probe


def test_parser_requires_bond_code_and_accepts_repeated_fields() -> None:
    parser = probe._build_parser()

    assert probe.main(["--field", "sec_name"]) == 2
    parsed = parser.parse_args(
        [
            "--bond-code",
            "102480811.IB",
            "--field",
            "sec_name",
            "--field",
            "sccode",
        ]
    )

    assert parsed.bond_code == "102480811.IB"
    assert parsed.field == ["sec_name", "sccode"]
    assert parsed.execute is False


def test_probe_requires_execute_for_live_wind(monkeypatch, capsys) -> None:
    monkeypatch.setattr(probe, "_import_wind", lambda: (_ for _ in ()).throw(
        AssertionError("must not import")
    ))

    assert (
        probe.main(
            ["--bond-code", "102480811.IB", "--field", "sec_name"]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "executed": False,
        "bond_code": "102480811.IB",
        "fields": ["sec_name"],
    }


def test_probe_rejects_empty_field(capsys) -> None:
    assert probe.main(["--bond-code", "102480811.IB", "--field", ""]) == 2
    assert "--field 不能为空" in capsys.readouterr().err


def test_execute_reports_field_availability_without_returning_values(
    monkeypatch, capsys
) -> None:
    class Gateway:
        def start(self):
            return 0

        def wss(self, bond_code, fields, *, usedf):
            assert bond_code == "102480811.IB"
            assert fields == "sec_name,sccode"
            assert usedf is True
            return 0, pd.DataFrame(
                [{"SEC_NAME": "24冀中能源MTN004A", "SCCODE": "102480811"}]
            )

    monkeypatch.setattr(probe, "_import_wind", lambda: Gateway())

    assert (
        probe.main(
            [
                "--execute",
                "--bond-code",
                "102480811.IB",
                "--field",
                "sec_name",
                "--field",
                "sccode",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["executed"] is True
    assert payload["record_count"] == 1
    assert payload["fields"] == [
        {"field": "sec_name", "available": True, "raw_type": "str", "is_null": False},
        {"field": "sccode", "available": True, "raw_type": "str", "is_null": False},
    ]
    assert "24冀中能源MTN004A" not in json.dumps(payload, ensure_ascii=False)
