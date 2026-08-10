from __future__ import annotations

import sys
import threading
import time

import pandas as pd
import pytest

from src.common.wind_code_excel_helper import WindCodeExcelHelper
import src.common.macos_wind_excel as macos_wind_excel
import src.pretrade.wind_excel_master as wind_excel_master
from src.pretrade.wind_excel_master import XlwingsFormulaEvaluator


class _StopAfterFormula(RuntimeError):
    pass


class _FakeRange:
    def __init__(self, *, stop_after_formula: bool = False, values=None) -> None:
        self.stop_after_formula = stop_after_formula
        self.values = values
        self.resize_args: tuple[int, int] | None = None
        self.formula_value = None
        self.written_value = None

    def resize(self, rows: int, columns: int):
        self.resize_args = (rows, columns)
        return self

    def options(self, *_args, **_kwargs):
        return self

    @property
    def formula(self):
        return self.formula_value

    @formula.setter
    def formula(self, value) -> None:
        self.formula_value = value
        if self.stop_after_formula:
            raise _StopAfterFormula()

    @property
    def value(self):
        return self.values

    @value.setter
    def value(self, value) -> None:
        self.written_value = value


class _FakeSheet:
    def __init__(self, *, stop_after_formula: bool = False, values=None) -> None:
        self.stop_after_formula = stop_after_formula
        self.values = values
        self.ranges: dict[str, _FakeRange] = {}

    def range(self, address: str) -> _FakeRange:
        if address not in self.ranges:
            self.ranges[address] = _FakeRange(
                stop_after_formula=(address == "B2" and self.stop_after_formula),
                values=self.values if address == "A1" else None,
            )
        return self.ranges[address]


class _FakeBook:
    def __init__(self, sheet: _FakeSheet) -> None:
        self.sheets = [sheet]
        self.closed = False

    def close(self) -> None:
        self.closed = True

    def save(self, _path) -> None:
        pass


class _FakeBooks:
    def __init__(self, book: _FakeBook) -> None:
        self.book = book

    def add(self) -> _FakeBook:
        return self.book


class _FakeApp:
    def __init__(self, *, visible: bool, add_book: bool, book: _FakeBook) -> None:
        self.visible = visible
        self.add_book = add_book
        self.books = _FakeBooks(book)
        self.display_alerts = True
        self.calculated = False
        self.quit_called = False

    def calculate(self) -> None:
        self.calculated = True

    def quit(self) -> None:
        self.quit_called = True


class _FakeXlwings:
    def __init__(self, *, stop_after_formula: bool = False, values=None) -> None:
        self.sheet = _FakeSheet(
            stop_after_formula=stop_after_formula,
            values=values,
        )
        self.book = _FakeBook(self.sheet)
        self.apps: list[_FakeApp] = []

    def App(self, *, visible: bool, add_book: bool) -> _FakeApp:
        app = _FakeApp(visible=visible, add_book=add_book, book=self.book)
        self.apps.append(app)
        return app


def test_wind_code_helper_keeps_existing_windows_xlwings_behavior(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    fake_xlwings = _FakeXlwings(stop_after_formula=True)
    monkeypatch.setitem(sys.modules, "xlwings", fake_xlwings)
    helper = WindCodeExcelHelper(temp_dir=tmp_path)
    helper.system = "Windows"

    with pytest.raises(_StopAfterFormula):
        helper._get_via_xlwings(["甲公司", "乙公司"])

    assert fake_xlwings.apps[0].visible is False
    formula_range = fake_xlwings.sheet.ranges["B2"]
    assert formula_range.resize_args is None
    assert formula_range.formula_value == "=To_WindCode(A2)"


def test_wind_code_helper_uses_macos_automation_by_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    helper = WindCodeExcelHelper(temp_dir=tmp_path)
    helper.system = "Darwin"
    expected = {"发行人名称": ["甲公司"], "Wind代码": ["F1000001.00"]}
    monkeypatch.setattr(
        helper,
        "_get_via_xlwings",
        lambda _issuers: (_ for _ in ()).throw(AssertionError("不应调用 xlwings")),
    )
    monkeypatch.setattr(
        helper,
        "_get_via_macos_excel",
        lambda _issuers: __import__("pandas").DataFrame(expected),
    )
    monkeypatch.setattr(
        helper,
        "_get_via_template",
        lambda _issuers: (_ for _ in ()).throw(AssertionError("不应进入人工模板")),
    )

    result = helper.batch_get_wind_codes(["甲公司"])

    assert result.to_dict(orient="list") == expected


def test_wind_code_helper_uses_staged_result_in_frozen_candidate(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    pd.DataFrame(
        {"发行人名称": ["甲公司"], "Wind代码": ["0"]}
    ).to_excel(tmp_path / "wind_codes_result.xlsx", index=False)
    helper = WindCodeExcelHelper(temp_dir=tmp_path)
    helper.system = "Darwin"
    monkeypatch.setenv("LIMIT_MONITOR_FROZEN_WIND_RESULT", "1")
    monkeypatch.setenv("ENV", "test")
    monkeypatch.setenv("LIMIT_MONITOR_PROFILE", "local")
    monkeypatch.setattr(
        helper,
        "_get_via_macos_excel",
        lambda _issuers: (_ for _ in ()).throw(
            AssertionError("冻结候选不得启动 Excel")
        ),
    )

    result = helper.batch_get_wind_codes(["甲公司"])

    assert result.to_dict("records") == [
        {"发行人名称": "甲公司", "Wind代码": 0}
    ]


def test_staged_wind_result_is_rejected_outside_test_profile(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    helper = WindCodeExcelHelper(temp_dir=tmp_path)
    monkeypatch.setenv("LIMIT_MONITOR_FROZEN_WIND_RESULT", "1")
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("LIMIT_MONITOR_PROFILE", "windows")

    with pytest.raises(RuntimeError, match="仅允许测试环境"):
        helper.batch_get_wind_codes(["甲公司"])


def test_master_formula_evaluator_uses_hidden_windows_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_xlwings = _FakeXlwings(values=["主证券", "行业"])
    monkeypatch.setitem(sys.modules, "xlwings", fake_xlwings)
    monkeypatch.setattr(wind_excel_master.platform, "system", lambda: "Windows")

    result = XlwingsFormulaEvaluator().evaluate(
        {"main_security_code": "=b_info_anchorbond(\"X.IB\")", "industry": "=b_issuer_windindustry(\"X.IB\",4)"}
    )

    assert fake_xlwings.apps[0].visible is False
    assert fake_xlwings.sheet.ranges["A1"].formula_value == [
        ["=b_info_anchorbond(\"X.IB\")"],
        ["=b_issuer_windindustry(\"X.IB\",4)"],
    ]
    assert result == {"main_security_code": "主证券", "industry": "行业"}


def test_master_formula_evaluator_uses_macos_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    class FakeMacOSRunner:
        def evaluate(self, formulas, *, labels=None):
            calls.append((formulas, labels))
            return ["2180399.IB", "公用事业"]

    monkeypatch.setattr(wind_excel_master.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(
        macos_wind_excel,
        "MacOSWindExcelFormulaRunner",
        FakeMacOSRunner,
    )

    result = XlwingsFormulaEvaluator().evaluate(
        {
            "main_security_code": '=b_info_anchorbond("X.IB")',
            "industry": '=b_issuer_windindustry("X.IB",4)',
        }
    )

    assert result == {
        "main_security_code": "2180399.IB",
        "industry": "公用事业",
    }
    assert calls == [
        (
            [
                '=WSS("X.IB","b_info_anchorbond")',
                '=WSS("X.IB","b_issuer_windindustry","industryType=4")',
            ],
            ["main_security_code", "industry"],
        )
    ]


def test_parse_copied_macos_excel_results() -> None:
    assert macos_wind_excel._parse_copied_results(
        "查询项\tWind结果\r\nissuer\tF1000001.00\r\nbalance\t0\r\n",
        expected_rows=2,
    ) == ["F1000001.00", "0"]


def test_parse_copied_macos_excel_results_rejects_incomplete_table() -> None:
    assert (
        macos_wind_excel._parse_copied_results(
            "查询项\tWind结果\r\nissuer\t\r\n",
            expected_rows=2,
        )
        is None
    )


def test_macos_runner_retries_while_excel_window_is_starting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = macos_wind_excel.MacOSWindExcelFormulaRunner(
        open_timeout_seconds=1,
    )
    attempts = 0

    def front_window_name() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise macos_wind_excel.MacOSWindExcelAutomationError(
                "Excel 尚未创建窗口"
            )
        return "limit_monitor_wind_query_test"

    monkeypatch.setattr(runner, "_set_excel_frontmost", lambda: None)
    monkeypatch.setattr(runner, "_front_window_name", front_window_name)
    monkeypatch.setattr(macos_wind_excel.time, "monotonic", lambda: 0.0)
    monkeypatch.setattr(macos_wind_excel.time, "sleep", lambda _seconds: None)

    runner._wait_until_front("limit_monitor_wind_query_test")

    assert attempts == 2


def test_macos_runner_raises_existing_workbook_hidden_behind_login_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = macos_wind_excel.MacOSWindExcelFormulaRunner(
        open_timeout_seconds=1,
    )
    expected = "limit_monitor_wind_query_test"
    front_windows = iter(["Login", expected])
    raised = []

    monkeypatch.setattr(runner, "_set_excel_frontmost", lambda: None)
    monkeypatch.setattr(runner, "_front_window_name", lambda: next(front_windows))
    monkeypatch.setattr(
        runner,
        "_window_names",
        lambda: ["Microsoft Excel", "Login", expected],
    )
    monkeypatch.setattr(
        runner,
        "_raise_window",
        lambda window_name: raised.append(window_name),
    )
    monkeypatch.setattr(macos_wind_excel.time, "monotonic", lambda: 0.0)

    opened, error = runner._try_wait_until_front(
        expected,
        timeout_seconds=1,
    )

    assert opened is True
    assert error is None
    assert raised == [expected]


def test_macos_runner_uses_excel_open_dialog_when_launchservices_only_updates_recents(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    runner = macos_wind_excel.MacOSWindExcelFormulaRunner()
    workbook_path = tmp_path / "limit_monitor_wind_query_test.xlsx"
    calls = []

    monkeypatch.setattr(
        runner,
        "_try_wait_until_front",
        lambda expected_window, *, timeout_seconds: (False, None),
    )
    monkeypatch.setattr(
        runner,
        "_open_workbook_via_dialog",
        lambda path: calls.append(("dialog", path)),
    )
    monkeypatch.setattr(
        runner,
        "_wait_until_front",
        lambda expected_window: calls.append(("wait", expected_window)),
    )

    runner._ensure_workbook_front(workbook_path)

    assert calls == [
        ("dialog", workbook_path),
        ("wait", "limit_monitor_wind_query_test"),
    ]


def test_macos_runner_does_not_open_dialog_when_workbook_window_exists(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    runner = macos_wind_excel.MacOSWindExcelFormulaRunner()
    workbook_path = tmp_path / "limit_monitor_wind_query_test.xlsx"

    monkeypatch.setattr(
        runner,
        "_try_wait_until_front",
        lambda expected_window, *, timeout_seconds: (True, None),
    )
    monkeypatch.setattr(
        runner,
        "_open_workbook_via_dialog",
        lambda _path: (_ for _ in ()).throw(AssertionError("不应打开文件对话框")),
    )

    runner._ensure_workbook_front(workbook_path)


def test_macos_open_dialog_targets_exact_temporary_workbook(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    workbook_path = tmp_path / 'limit_monitor_"wind"_query.xlsx'
    scripts = []
    monkeypatch.setattr(
        macos_wind_excel,
        "_run_osascript",
        lambda script: scripts.append(script) or "",
    )

    macos_wind_excel.MacOSWindExcelFormulaRunner._open_workbook_via_dialog(
        workbook_path
    )

    assert 'keystroke "o" using command down' in scripts[0]
    assert 'keystroke "g" using {command down, shift down}' in scripts[0]
    assert 'keystroke "a" using command down' in scripts[0]
    assert '\\"wind\\"' in scripts[0]
    assert scripts[0].count("key code 36") == 2


def test_macos_runner_leaves_large_copy_mode_before_closing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = macos_wind_excel.MacOSWindExcelFormulaRunner()
    calls = []
    monkeypatch.setattr(
        runner,
        "_send_key_code",
        lambda key_code: calls.append(("key", key_code)),
    )
    monkeypatch.setattr(
        runner,
        "_restore_clipboard",
        lambda value: calls.append(("clipboard", value)),
    )

    runner._leave_copy_mode("原剪贴板")

    assert calls == [
        ("key", 53),
        ("clipboard", "原剪贴板"),
    ]


def test_macos_runner_closes_exact_temporary_workbook_without_saving(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = macos_wind_excel.MacOSWindExcelFormulaRunner()
    scripts = []
    closed = []
    monkeypatch.setattr(
        macos_wind_excel,
        "_run_osascript",
        lambda script, **kwargs: scripts.append((script, kwargs)) or "",
    )
    monkeypatch.setattr(
        runner,
        "_wait_until_window_closed",
        lambda expected: closed.append(expected),
    )

    runner._close_without_saving("limit_monitor_wind_query_test")

    script, kwargs = scripts[0]
    assert 'workbook "limit_monitor_wind_query_test.xlsx"' in script
    assert "saving no" in script
    assert closed == ["limit_monitor_wind_query_test"]
    # 关闭要等 Excel 走完 Wind 加载项收尾，不能沿用查询用的紧超时。
    assert kwargs["timeout"] == macos_wind_excel._TEARDOWN_TIMEOUT_SECONDS
    assert kwargs["timeout"] > macos_wind_excel._QUERY_TIMEOUT_SECONDS


def test_macos_runner_cleanup_does_not_reopen_failed_temporary_workbook(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    runner = macos_wind_excel.MacOSWindExcelFormulaRunner()
    workbook_path = tmp_path / "limit_monitor_wind_query_test.xlsx"
    calls = []
    monkeypatch.setattr(
        runner,
        "_open_workbook",
        lambda _path: (_ for _ in ()).throw(AssertionError("清理时不得重新打开")),
    )
    monkeypatch.setattr(
        runner,
        "_close_without_saving",
        lambda expected: calls.append(("close", expected)),
    )

    runner._close_workbook_best_effort(workbook_path)

    assert calls == [("close", "limit_monitor_wind_query_test")]


def test_macos_runner_retries_close_after_dismissing_modal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    runner = macos_wind_excel.MacOSWindExcelFormulaRunner()
    workbook_path = tmp_path / "limit_monitor_wind_query_test.xlsx"
    calls: list[object] = []
    attempts = iter([macos_wind_excel.MacOSWindExcelAutomationError("超时"), None])

    def _close(expected: str) -> None:
        calls.append(("close", expected))
        outcome = next(attempts)
        if outcome is not None:
            raise outcome

    monkeypatch.setattr(runner, "_close_without_saving", _close)
    monkeypatch.setattr(
        runner, "_send_key_code", lambda code: calls.append(("key", code))
    )
    monkeypatch.setattr(
        macos_wind_excel,
        "quit_excel_best_effort",
        lambda: calls.append("quit"),
    )

    runner._close_workbook_best_effort(workbook_path)

    assert calls == [
        ("close", "limit_monitor_wind_query_test"),
        ("key", 53),
        ("close", "limit_monitor_wind_query_test"),
    ]


def test_macos_runner_quits_excel_when_orphan_window_cannot_be_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    runner = macos_wind_excel.MacOSWindExcelFormulaRunner()
    workbook_path = tmp_path / "limit_monitor_wind_query_test.xlsx"
    quits: list[str] = []

    def _always_fail(_expected: str) -> None:
        raise macos_wind_excel.MacOSWindExcelAutomationError("Excel 无响应")

    monkeypatch.setattr(runner, "_close_without_saving", _always_fail)
    monkeypatch.setattr(runner, "_send_key_code", lambda _code: None)
    monkeypatch.setattr(
        runner,
        "_window_names",
        lambda: ["limit_monitor_wind_query_test.xlsx"],
    )
    monkeypatch.setattr(
        macos_wind_excel,
        "quit_excel_best_effort",
        lambda: quits.append("quit"),
    )
    monkeypatch.setattr(
        macos_wind_excel._SESSION_STATE, "started_by_us", True, raising=False
    )

    runner._close_workbook_best_effort(workbook_path)

    assert quits == ["quit"]


def test_macos_runner_keeps_user_excel_alive_when_close_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    runner = macos_wind_excel.MacOSWindExcelFormulaRunner()
    workbook_path = tmp_path / "limit_monitor_wind_query_test.xlsx"
    quits: list[str] = []

    def _always_fail(_expected: str) -> None:
        raise macos_wind_excel.MacOSWindExcelAutomationError("Excel 无响应")

    monkeypatch.setattr(runner, "_close_without_saving", _always_fail)
    monkeypatch.setattr(runner, "_send_key_code", lambda _code: None)
    monkeypatch.setattr(
        runner,
        "_window_names",
        lambda: ["limit_monitor_wind_query_test"],
    )
    monkeypatch.setattr(
        macos_wind_excel,
        "quit_excel_best_effort",
        lambda: quits.append("quit"),
    )
    monkeypatch.setattr(
        macos_wind_excel._SESSION_STATE, "started_by_us", False, raising=False
    )

    runner._close_workbook_best_effort(workbook_path)

    # Excel 是用户自己打开的，未保存的表格不能被我们顺手关掉。
    assert quits == []


@pytest.mark.parametrize(
    "window_names",
    [[], ["其它工作簿.xlsx"]],
)
def test_macos_runner_treats_missing_window_as_closed(
    monkeypatch: pytest.MonkeyPatch,
    window_names: list[str],
) -> None:
    runner = macos_wind_excel.MacOSWindExcelFormulaRunner()
    monkeypatch.setattr(runner, "_window_names", lambda: window_names)

    runner._wait_until_window_closed("limit_monitor_wind_query_test")


@pytest.mark.parametrize(
    "window_name",
    ["limit_monitor_wind_query_test", "limit_monitor_wind_query_test.xlsx"],
)
def test_macos_runner_detects_open_window_with_or_without_extension(
    monkeypatch: pytest.MonkeyPatch,
    window_name: str,
) -> None:
    runner = macos_wind_excel.MacOSWindExcelFormulaRunner(open_timeout_seconds=0.05)
    monkeypatch.setattr(runner, "_window_names", lambda: [window_name])
    monkeypatch.setattr(macos_wind_excel.time, "sleep", lambda _seconds: None)

    # 系统是否显示扩展名不该影响“工作簿还开着”的判断。
    assert runner._workbook_window_present("limit_monitor_wind_query_test")
    with pytest.raises(macos_wind_excel.MacOSWindExcelAutomationError):
        runner._wait_until_window_closed("limit_monitor_wind_query_test")


def test_macos_runner_returns_values_even_when_close_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = macos_wind_excel.MacOSWindExcelFormulaRunner()
    monkeypatch.setattr(macos_wind_excel.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(runner, "_assert_accessibility_ready", lambda: None)
    monkeypatch.setattr(runner, "_read_clipboard", lambda: "原剪贴板")
    monkeypatch.setattr(runner, "_restore_clipboard", lambda _value: None)
    monkeypatch.setattr(runner, "_open_workbook", lambda _path: None)
    monkeypatch.setattr(runner, "_ensure_workbook_front", lambda _path: None)
    monkeypatch.setattr(runner, "_send_key_code", lambda _code: None)
    monkeypatch.setattr(runner, "_leave_copy_mode", lambda _clipboard: None)
    monkeypatch.setattr(
        runner,
        "_wait_for_results",
        lambda _window, *, expected_rows: ["2605080.IB"],
    )
    monkeypatch.setattr(
        runner,
        "_close_without_saving",
        lambda _window: (_ for _ in ()).throw(
            macos_wind_excel.MacOSWindExcelAutomationError("Excel 无响应")
        ),
    )
    monkeypatch.setattr(runner, "_window_names", lambda: [])
    monkeypatch.setattr(macos_wind_excel, "excel_is_running", lambda: True)

    values = runner.evaluate(['=WSS("x","b_info_name")'], labels=["main"])

    # 关闭只是收尾动作；关不掉是运维问题，不该把已取到的 Wind 结果一起丢掉。
    assert values == ["2605080.IB"]


@pytest.mark.parametrize(
    ("started_by_us", "expected_grace"),
    [(True, macos_wind_excel._COLD_START_GRACE_SECONDS), (False, 5.0)],
)
def test_macos_runner_gives_cold_start_excel_a_longer_grace_period(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    started_by_us: bool,
    expected_grace: float,
) -> None:
    runner = macos_wind_excel.MacOSWindExcelFormulaRunner(open_timeout_seconds=30.0)
    grace: list[float] = []
    monkeypatch.setattr(
        macos_wind_excel._SESSION_STATE,
        "started_by_us",
        started_by_us,
        raising=False,
    )
    monkeypatch.setattr(
        runner,
        "_try_wait_until_front",
        lambda _window, *, timeout_seconds: (
            grace.append(timeout_seconds) or (True, None)
        ),
    )
    monkeypatch.setattr(
        runner,
        "_open_workbook_via_dialog",
        lambda _path: pytest.fail("已在前台时不得再走打开对话框"),
    )

    runner._ensure_workbook_front(tmp_path / "limit_monitor_wind_query_test.xlsx")

    assert grace == [expected_grace]


def test_excel_session_quits_only_the_excel_it_started(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        macos_wind_excel, "_SESSION_STATE", macos_wind_excel._ExcelSessionState()
    )
    quits: list[str] = []
    monkeypatch.setattr(macos_wind_excel, "excel_is_running", lambda: False)
    monkeypatch.setattr(
        macos_wind_excel,
        "quit_excel_best_effort",
        lambda: quits.append("quit"),
    )

    with macos_wind_excel.excel_session():
        assert quits == []

    assert quits == ["quit"]


def test_excel_session_leaves_preexisting_excel_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        macos_wind_excel, "_SESSION_STATE", macos_wind_excel._ExcelSessionState()
    )
    quits: list[str] = []
    monkeypatch.setattr(macos_wind_excel, "excel_is_running", lambda: True)
    monkeypatch.setattr(
        macos_wind_excel,
        "quit_excel_best_effort",
        lambda: quits.append("quit"),
    )

    with macos_wind_excel.excel_session():
        pass

    assert quits == []


def test_excel_session_quits_once_after_outermost_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        macos_wind_excel, "_SESSION_STATE", macos_wind_excel._ExcelSessionState()
    )
    quits: list[str] = []
    monkeypatch.setattr(macos_wind_excel, "excel_is_running", lambda: False)
    monkeypatch.setattr(
        macos_wind_excel,
        "quit_excel_best_effort",
        lambda: quits.append("quit"),
    )

    # 一揽子里每笔非持仓债都会各自进入会话，Excel 只应在最外层退出一次。
    with macos_wind_excel.excel_session():
        with macos_wind_excel.excel_session():
            with macos_wind_excel.excel_session():
                pass
            assert quits == []
        assert quits == []

    assert quits == ["quit"]


def test_excel_session_serializes_concurrent_wind_lookups(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        macos_wind_excel, "_SESSION_STATE", macos_wind_excel._ExcelSessionState()
    )
    monkeypatch.setattr(macos_wind_excel, "excel_is_running", lambda: True)
    monkeypatch.setattr(macos_wind_excel, "quit_excel_best_effort", lambda: None)

    overlaps: list[bool] = []
    inside = threading.Event()
    release = threading.Event()

    def _hold() -> None:
        with macos_wind_excel.excel_session():
            inside.set()
            release.wait(timeout=5)

    def _contend() -> None:
        # 另一路查询必须等前一路交还 Excel，否则会抢走前台窗口和剪贴板。
        overlaps.append(release.is_set())
        with macos_wind_excel.excel_session():
            overlaps.append(release.is_set())

    holder = threading.Thread(target=_hold)
    holder.start()
    assert inside.wait(timeout=5)

    contender = threading.Thread(target=_contend)
    contender.start()
    time.sleep(0.1)
    release.set()
    holder.join(timeout=5)
    contender.join(timeout=5)

    assert overlaps == [False, True]


def test_macos_runner_waits_past_excel_error_until_values_are_stable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = macos_wind_excel.MacOSWindExcelFormulaRunner(
        calculation_timeout_seconds=30,
        poll_interval_seconds=0,
    )
    clipboards = iter(
        [
            "查询项\tWind结果\nmain\t#VALUE!\n",
            "查询项\tWind结果\nmain\t2605080.IB\n",
            "查询项\tWind结果\nmain\t2605080.IB\n",
        ]
    )
    clock = iter(range(100))

    monkeypatch.setattr(runner, "_assert_front_window", lambda _expected: None)
    monkeypatch.setattr(
        runner,
        "_send_keystroke",
        lambda _key, *, command_down=False: None,
    )
    monkeypatch.setattr(runner, "_read_clipboard", lambda: next(clipboards))
    monkeypatch.setattr(macos_wind_excel.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(macos_wind_excel.time, "sleep", lambda _seconds: None)

    assert runner._wait_for_results("query", expected_rows=1) == ["2605080.IB"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("#VALUE!", False),
        ("#NAME?", False),
        ("Requesting Data...", False),
        ("正在计算", False),
        ("", False),
        ("0", True),
        ("000000", True),
        ("广东省", True),
    ],
)
def test_macos_wind_excel_completion_marker(value: str, expected: bool) -> None:
    assert macos_wind_excel._is_complete_wind_excel_value(value) is expected
