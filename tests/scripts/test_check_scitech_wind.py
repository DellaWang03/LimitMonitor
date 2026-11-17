import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

from scripts import check_scitech_wind as probe


def response(values, codes=probe.ALL_CODES):
    return SimpleNamespace(ErrorCode=0, Fields=["SCITECHBONDORNOT"], Codes=list(codes), Data=[values])


def test_null_is_not_false_and_missing_codes_cannot_pass():
    values = ["是"] * 21 + [None]
    parsed = probe.parse_response(response(values), "scitechbondornot")
    summary = probe.summarize_query(parsed)
    assert not summary["complete"]
    assert not summary["sample_check_passed"]
    assert summary["comparisons"][-1]["normalized_for_comparison"] is None
    partial = probe.parse_response(response(["是"], [probe.ALL_CODES[0]]), "scitechbondornot")
    assert not probe.summarize_query(partial)["complete"]


def test_compare_by_returned_code_and_preserve_raw_types():
    parsed = probe.parse_response(response([False] + [True] * 21, tuple(reversed(probe.ALL_CODES))), "candidate")
    assert probe.summarize_query(parsed)["sample_check_passed"]
    assert parsed["records"][0]["raw_type"] == "bool"
    assert parsed["records"][0]["raw_value"] is False


def test_nan_serializes_to_null_without_losing_field_diagnostics(capsys):
    parsed = probe.parse_response(response([float("nan")] + ["是"] * 20 + ["否"]), "candidate")
    probe.emit("query_result", **parsed)
    saved = json.loads(capsys.readouterr().out.removeprefix(probe.PREFIX))
    assert saved["raw_data"][0][0] is None
    assert saved["records"][0]["raw_type"] == "float"
    assert saved["records"][0]["is_missing"]
    assert not probe.summarize_query(saved)["sample_check_passed"]


def test_malformed_shape_and_duplicates_cannot_pass():
    parsed = probe.parse_response(response(["是"]), "candidate")
    assert parsed["shape_error"]
    assert not probe.summarize_query(parsed)["sample_check_passed"]
    parsed = probe.parse_response(response(["是"] * 22, [probe.ALL_CODES[0]] * 22), "candidate")
    assert not probe.summarize_query(parsed)["complete"]


def test_dry_run_has_no_wind_import_or_files(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(probe, "load_wind", lambda _: (_ for _ in ()).throw(AssertionError("no Wind")))
    assert probe.main(["--dry-run", "--output-dir", str(tmp_path / "absent")]) == 0
    assert json.loads(capsys.readouterr().out)["executed"] is False
    assert not (tmp_path / "absent").exists()


def run_fake(tmp_path, module, *extra):
    sdk = tmp_path / "fake_sdk"
    sdk.mkdir()
    (sdk / "WindPy.py").write_text(module, encoding="utf-8")
    output = tmp_path / "reports"
    result = subprocess.run(
        [sys.executable, str(Path(probe.__file__)), "--windpy-path", str(sdk),
         "--output-dir", str(output), *extra],
        capture_output=True, text=True, timeout=15,
    )
    report = json.loads(next(output.glob("*/wind_probe_report.json")).read_text(encoding="utf-8"))
    return result, report


def test_standalone_probe_reports_field_error_and_success_without_pandas(tmp_path):
    result, report = run_fake(tmp_path, '''
from types import SimpleNamespace
class W:
    def isconnected(self): return True
    def start(self, **kwargs): raise AssertionError("already connected")
    def wss(self, codes, field):
        codes = codes.split(",")
        if field.startswith("b_info_"):
            return SimpleNamespace(ErrorCode=-40522007, Fields=[], Codes=[], Data=[["unsupported"]])
        values = ["name"] * len(codes) if field == "sec_name" else ["否" if c == "010706.SH" else "是" for c in codes]
        return SimpleNamespace(ErrorCode=0, Fields=[field.upper()], Codes=codes, Data=[values])
w=W()
''')
    assert result.returncode == 0, result.stdout + result.stderr
    assert report["passed_fields"] == ["scitechbondornot"]
    assert report["summaries"][0]["error_code"] == -40522007
    assert report["summaries"][1]["comparisons"][-1]["raw_value"] == "否"


def test_timeout_writes_partial_report_and_returns_failure(tmp_path):
    result, report = run_fake(tmp_path, '''
import time
class W:
    def isconnected(self): return False
    def start(self, **kwargs): time.sleep(30)
w=W()
''', "--timeout", "1")
    assert result.returncode == 1
    assert report["timed_out"]
    assert not report["sample_check_passed"]
    assert report["last_step"] == "start_begin"
