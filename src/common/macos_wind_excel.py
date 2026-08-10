"""macOS 上通过可见 Excel/Wind 会话计算预写公式。

macOS 的 Excel Apple Event 在写入 Wind UDF 时可能一直阻塞。这里先用
openpyxl 把公式写入临时工作簿，再只通过系统辅助功能发送计算、复制和关闭
操作。Windows 生产环境继续使用原有 xlwings 路径。
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import csv
from io import StringIO
import platform
from pathlib import Path
import subprocess
import tempfile
import threading
import time
from typing import Sequence
from uuid import uuid4

from loguru import logger
from openpyxl import Workbook


# 查询窗口状态的 Apple Event 应当秒回；而关闭工作簿或退出应用会等待
# Excel 走完保存询问、Wind 加载项收尾等动作，装了 Wind 的 Excel 在刚跑完
# WSS 之后经常需要几十秒才响应，共用一个紧超时会让关闭必然失败。
_QUERY_TIMEOUT_SECONDS = 10.0
_TEARDOWN_TIMEOUT_SECONDS = 90.0
_QUIT_SETTLE_TIMEOUT_SECONDS = 20.0
_COLD_START_GRACE_SECONDS = 15.0

_EXCEL_PROCESS_NAME = "Microsoft Excel"


class MacOSWindExcelAutomationError(RuntimeError):
    """macOS Excel/Wind 自动化未能返回完整结果。"""


class MacOSWindExcelPermissionError(MacOSWindExcelAutomationError):
    """当前终端没有获得 macOS 辅助功能或自动化权限。"""


class _ExcelSessionState:
    """跨嵌套调用共享的 Excel 应用生命周期。

    整套自动化靠抢占 Excel 前台窗口和系统剪贴板完成，两路并发会互相污染
    取数结果，也会让先结束的一方退掉另一方还在用的 Excel。因此会话本身就
    是互斥量：同一线程可重入，不同线程串行等待。
    """

    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.depth = 0
        self.started_by_us = False

    def enter(self) -> None:
        self.lock.acquire()
        if self.depth == 0:
            self.started_by_us = not excel_is_running()
        self.depth += 1

    def exit(self) -> None:
        try:
            self.depth -= 1
            if self.depth > 0:
                return
            should_quit = self.started_by_us
            self.started_by_us = False
            if should_quit:
                quit_excel_best_effort()
        finally:
            self.lock.release()


_SESSION_STATE = _ExcelSessionState()


@contextmanager
def excel_session() -> Iterator[None]:
    """在一段连续的 Wind 取数期间复用同一个 Excel 应用实例。

    嵌套进入只记引用计数；只有最外层退出、且 Excel 是被本次调用拉起来的
    时候，才会退出 Excel，避免关掉用户自己开着的表格。
    """

    _SESSION_STATE.enter()
    try:
        yield
    finally:
        _SESSION_STATE.exit()


def excel_is_running() -> bool:
    try:
        result = subprocess.run(
            ["pgrep", "-x", _EXCEL_PROCESS_NAME],
            check=False,
            capture_output=True,
            text=True,
            timeout=_QUERY_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        # 探测不到就按“已在运行”处理，宁可留下 Excel 也不误关用户的表格。
        return True
    return result.returncode == 0 and bool(result.stdout.strip())


def quit_excel_best_effort() -> None:
    """退出本次调用拉起的 Excel；失败只记日志，不影响业务结果。"""

    if not excel_is_running():
        return
    try:
        _run_osascript(
            f'tell application "{_EXCEL_PROCESS_NAME}" to quit saving no',
            timeout=_TEARDOWN_TIMEOUT_SECONDS,
        )
    except MacOSWindExcelAutomationError as exc:
        logger.warning(f"退出 Excel 的 Apple Event 未成功: {exc}")

    deadline = time.monotonic() + _QUIT_SETTLE_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if not excel_is_running():
            logger.info("Wind 取数结束，已退出本次拉起的 Excel")
            return
        time.sleep(0.5)
    # 不强杀：强制终止会触发 Excel 崩溃报告和下次启动的文档恢复面板。
    logger.error(
        "Excel 在 Wind 取数结束后仍未退出，可能有对话框在等待响应，"
        "请手动检查并关闭 Excel"
    )


class MacOSWindExcelFormulaRunner:
    """在一个临时工作簿中批量计算 Wind Excel 公式。"""

    def __init__(
        self,
        *,
        open_timeout_seconds: float = 30.0,
        poll_interval_seconds: float = 3.0,
        calculation_timeout_seconds: float | None = None,
    ) -> None:
        self._open_timeout_seconds = open_timeout_seconds
        self._poll_interval_seconds = poll_interval_seconds
        self._calculation_timeout_seconds = calculation_timeout_seconds

    def evaluate(
        self,
        formulas: Sequence[str],
        *,
        labels: Sequence[str] | None = None,
    ) -> list[str]:
        if platform.system() != "Darwin":
            raise MacOSWindExcelAutomationError("该执行器仅支持 macOS")
        if not formulas:
            return []
        row_labels = list(labels or (f"result_{index}" for index in range(len(formulas))))
        if len(row_labels) != len(formulas):
            raise ValueError("labels 与 formulas 数量不一致")

        self._assert_accessibility_ready()
        previous_clipboard = self._read_clipboard()
        with excel_session(), tempfile.TemporaryDirectory(
            prefix="limit-monitor-wind-excel-"
        ) as directory:
            workbook_path = (
                Path(directory)
                / f"limit_monitor_wind_query_{uuid4().hex[:8]}.xlsx"
            )
            self._write_workbook(workbook_path, row_labels, formulas)
            opened = False
            try:
                self._open_workbook(workbook_path)
                opened = True
                self._ensure_workbook_front(workbook_path)
                self._send_key_code(101)  # F9
                values = self._wait_for_results(
                    workbook_path.stem,
                    expected_rows=len(formulas),
                )
                # 大批量复制会让 Excel 保持“复制模式”。若直接关闭，
                # Excel 会在“不保存”之后再弹出“大量剪贴板信息”警告，
                # 导致自动关闭等待超时。结果此时已解析进 Python，可安全
                # 退出复制模式并恢复用户原剪贴板，再关闭临时工作簿。
                self._leave_copy_mode(previous_clipboard)
            finally:
                # 结果此时已经在 values 里，关闭只做尽力而为：关不掉是运维
                # 问题，不该把已经取到的 Wind 数据一起丢掉。同时这一步必须
                # 赶在临时目录随 with 退出被删除之前，否则 Excel 会留下一个
                # 指向已删文件、并一直攥着 ~$ 锁文件的孤儿窗口。
                if opened:
                    self._close_workbook_best_effort(workbook_path)
                self._restore_clipboard(previous_clipboard)
            return values

    @staticmethod
    def _write_workbook(
        workbook_path: Path,
        labels: Sequence[str],
        formulas: Sequence[str],
    ) -> None:
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Wind自动化查询"
        sheet.append(["查询项", "Wind结果"])
        for label, formula in zip(labels, formulas, strict=True):
            sheet.append([label, formula])
        workbook.calculation.fullCalcOnLoad = True
        workbook.calculation.forceFullCalc = True
        workbook.calculation.calcMode = "auto"
        workbook.save(workbook_path)

    @staticmethod
    def _open_workbook(workbook_path: Path) -> None:
        try:
            subprocess.run(
                ["open", "-a", "Microsoft Excel", str(workbook_path)],
                check=True,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            raise MacOSWindExcelAutomationError("无法启动 Microsoft Excel") from exc

    def _ensure_workbook_front(self, workbook_path: Path) -> None:
        """确保 LaunchServices 不只把文件加入 Excel 的“最近使用”。"""

        # Excel 冷启动还要加载 Wind 加载项，几秒内往往还没建好窗口。这时抢着
        # 走下面的对话框路径，只会在真正的工作簿之上再叠一个“转到/打开”窗口，
        # 反过来把后续的关闭动作堵死，所以冷启动要给足宽限。
        if _SESSION_STATE.started_by_us:
            launch_grace_seconds = _COLD_START_GRACE_SECONDS
        else:
            launch_grace_seconds = min(
                5.0,
                max(1.0, self._open_timeout_seconds / 4),
            )
        opened, _ = self._try_wait_until_front(
            workbook_path.stem,
            timeout_seconds=launch_grace_seconds,
        )
        if opened:
            return

        # Excel 停在 macOS DocStage 起始页时，`open -a Excel file.xlsx`
        # 可能只更新“最近使用”列表，并不真正创建工作簿窗口。此时改走
        # Excel 自身的打开文件对话框；临时文件仍由本执行器创建和销毁。
        self._open_workbook_via_dialog(workbook_path)
        self._wait_until_front(workbook_path.stem)

    @staticmethod
    def _open_workbook_via_dialog(workbook_path: Path) -> None:
        escaped_path = _escape_applescript_string(str(workbook_path.resolve()))
        _run_osascript(
            'tell application "System Events"\n'
            'tell process "Microsoft Excel"\n'
            "set frontmost to true\n"
            'keystroke "o" using command down\n'
            "delay 1\n"
            'keystroke "g" using {command down, shift down}\n'
            "delay 0.5\n"
            'keystroke "a" using command down\n'
            f'keystroke "{escaped_path}"\n'
            "delay 0.2\n"
            "key code 36\n"
            "delay 0.7\n"
            "key code 36\n"
            "end tell\n"
            "end tell"
        )

    def _wait_until_front(self, expected_window: str) -> None:
        opened, last_error = self._try_wait_until_front(
            expected_window,
            timeout_seconds=self._open_timeout_seconds,
        )
        if opened:
            return
        error = MacOSWindExcelAutomationError(
            f"Excel 未在限定时间内打开临时工作簿: {expected_window}"
        )
        if last_error is not None:
            raise error from last_error
        raise error

    def _try_wait_until_front(
        self,
        expected_window: str,
        *,
        timeout_seconds: float,
    ) -> tuple[bool, MacOSWindExcelAutomationError | None]:
        deadline = time.monotonic() + timeout_seconds
        last_error: MacOSWindExcelAutomationError | None = None
        while time.monotonic() < deadline:
            try:
                self._set_excel_frontmost()
                if _window_name_matches(self._front_window_name(), expected_window):
                    return True, last_error
                actual_name = self._find_window_name(expected_window)
                if actual_name is not None:
                    self._raise_window(actual_name)
                    if _window_name_matches(
                        self._front_window_name(), expected_window
                    ):
                        return True, last_error
            except MacOSWindExcelPermissionError:
                raise
            except MacOSWindExcelAutomationError as exc:
                # Excel 冷启动时进程可能已经存在，但尚未创建可查询的窗口。
                last_error = exc
            time.sleep(0.5)
        return False, last_error

    def _wait_for_results(
        self,
        expected_window: str,
        *,
        expected_rows: int,
    ) -> list[str]:
        timeout = self._calculation_timeout_seconds
        if timeout is None:
            timeout = max(60.0, min(900.0, 30.0 + expected_rows * 0.6))
        deadline = time.monotonic() + timeout
        last_complete_values: tuple[str, ...] | None = None
        while time.monotonic() < deadline:
            self._assert_front_window(expected_window)
            self._send_keystroke("a", command_down=True)
            self._send_keystroke("c", command_down=True)
            time.sleep(0.5)
            values = _parse_copied_results(
                self._read_clipboard(),
                expected_rows=expected_rows,
            )
            if values is not None and all(
                _is_complete_wind_excel_value(value) for value in values
            ):
                normalized_values = tuple(str(value).strip() for value in values)
                # WSS 冷启动会先显示非空的 Excel 错误占位；真实结果也可能
                # 在一次复制后继续刷新。只有连续两次取得相同有效值才返回。
                if normalized_values == last_complete_values:
                    return values
                last_complete_values = normalized_values
            else:
                last_complete_values = None
            time.sleep(self._poll_interval_seconds)
        raise MacOSWindExcelAutomationError(
            f"Wind Excel 公式在 {timeout:.0f} 秒内未返回完整结果"
        )

    def _close_without_saving(self, expected_window: str) -> None:
        workbook_name = _escape_applescript_string(f"{expected_window}.xlsx")
        _run_osascript(
            f'tell application "{_EXCEL_PROCESS_NAME}" to close '
            f'workbook "{workbook_name}" saving no',
            timeout=_TEARDOWN_TIMEOUT_SECONDS,
        )
        self._wait_until_window_closed(expected_window)

    def _leave_copy_mode(self, previous_clipboard: str) -> None:
        self._send_key_code(53)  # Escape
        self._restore_clipboard(previous_clipboard)

    def _close_workbook_best_effort(self, workbook_path: Path) -> None:
        """逐级降级关闭临时工作簿，每一级失败都留痕。"""

        expected_window = workbook_path.stem
        try:
            self._close_without_saving(expected_window)
            return
        except MacOSWindExcelAutomationError as exc:
            logger.warning(f"关闭 Wind 临时工作簿失败，准备重试: {exc}")

        # Excel 可能停在“转到/打开”对话框或保存询问上，这类模态会让上面的
        # Apple Event 一直排队。先退掉模态再关一次。
        try:
            self._send_key_code(53)  # Escape
            self._close_without_saving(expected_window)
            return
        except MacOSWindExcelAutomationError as exc:
            logger.warning(f"退出模态后关闭 Wind 临时工作簿仍失败: {exc}")

        if not self._workbook_window_present(expected_window):
            logger.info(f"Wind 临时工作簿已不在 Excel 窗口列表中: {expected_window}")
            return

        if _SESSION_STATE.started_by_us:
            logger.error(
                f"Wind 临时工作簿 {expected_window} 无法关闭，"
                "退出本次拉起的 Excel 以避免残留孤儿窗口"
            )
            quit_excel_best_effort()
            return
        logger.error(
            f"Wind 临时工作簿 {expected_window} 无法关闭；Excel 是你自己打开的，"
            "不会自动退出应用，请手动关闭该临时窗口并选择“不保存”"
        )

    def _workbook_window_present(self, expected_window: str) -> bool:
        try:
            return self._find_window_name(expected_window) is not None
        except MacOSWindExcelAutomationError as exc:
            logger.warning(f"无法确认 Excel 窗口状态，按仍存在处理: {exc}")
            return True

    def _find_window_name(self, expected_window: str) -> str | None:
        """返回 Excel 里实际的窗口标题，兼容是否显示 .xlsx 扩展名。"""

        for name in self._window_names():
            if _window_name_matches(name, expected_window):
                return name
        return None

    def _wait_until_window_closed(self, expected_window: str) -> None:
        deadline = time.monotonic() + self._open_timeout_seconds
        while time.monotonic() < deadline:
            if self._find_window_name(expected_window) is None:
                return
            time.sleep(0.5)
        raise MacOSWindExcelAutomationError(
            f"Excel 未能关闭临时工作簿: {expected_window}"
        )

    def _assert_front_window(self, expected_window: str) -> None:
        self._set_excel_frontmost()
        actual = self._front_window_name()
        if not _window_name_matches(actual, expected_window):
            raise MacOSWindExcelAutomationError(
                f"Excel 前台工作簿被切换，期望 {expected_window}，实际 {actual or '无'}"
            )

    @staticmethod
    def _assert_accessibility_ready() -> None:
        enabled = _run_osascript(
            'tell application "System Events" to UI elements enabled'
        ).strip()
        if enabled != "true":
            raise MacOSWindExcelPermissionError(
                "当前终端未获得辅助功能权限；请在“系统设置 → 隐私与安全性 "
                "→ 辅助功能”中启用 Terminal（或当前使用的终端）"
            )

    @staticmethod
    def _set_excel_frontmost() -> None:
        _run_osascript(
            'tell application "System Events" to tell process '
            '"Microsoft Excel" to set frontmost to true'
        )

    @staticmethod
    def _front_window_name() -> str:
        return _run_osascript(
            'tell application "System Events" to tell process '
            '"Microsoft Excel" to get name of front window'
        ).strip()

    @staticmethod
    def _window_names() -> list[str]:
        output = _run_osascript(
            'tell application "System Events" to tell process '
            '"Microsoft Excel" to get name of every window'
        )
        return [name.strip() for name in output.split(",") if name.strip()]

    @staticmethod
    def _raise_window(window_name: str) -> None:
        escaped_name = _escape_applescript_string(window_name)
        _run_osascript(
            'tell application "System Events" to tell process '
            '"Microsoft Excel" to perform action "AXRaise" of '
            f'(first window whose name is "{escaped_name}")'
        )

    @staticmethod
    def _send_key_code(key_code: int) -> None:
        _run_osascript(
            'tell application "System Events" to tell process '
            f'"Microsoft Excel" to key code {key_code}'
        )

    @staticmethod
    def _send_keystroke(key: str, *, command_down: bool = False) -> None:
        suffix = " using command down" if command_down else ""
        _run_osascript(
            'tell application "System Events" to tell process '
            f'"Microsoft Excel" to keystroke "{key}"{suffix}'
        )

    @staticmethod
    def _read_clipboard() -> str:
        result = subprocess.run(
            ["pbpaste", "-Prefer", "txt"],
            check=False,
            capture_output=True,
            text=True,
        )
        return result.stdout

    @staticmethod
    def _restore_clipboard(value: str) -> None:
        try:
            subprocess.run(
                ["pbcopy"],
                check=False,
                input=value,
                text=True,
                capture_output=True,
            )
        except OSError:
            pass


def _run_osascript(
    script: str,
    *,
    timeout: float = _QUERY_TIMEOUT_SECONDS,
) -> str:
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or "").strip()
        if "-1743" in detail or "不允许" in detail or "not authorized" in detail:
            message = (
                "当前终端没有控制 System Events/Excel 的权限；请在"
                "“系统设置 → 隐私与安全性”中启用当前终端的"
                "“辅助功能”，并在“自动化”中允许 System Events"
            )
            raise MacOSWindExcelPermissionError(message) from exc
        else:
            message = f"macOS 暂时无法读取 Excel 窗口状态: {detail or exc}"
            raise MacOSWindExcelAutomationError(message) from exc
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise MacOSWindExcelAutomationError(
            f"macOS 控制 Microsoft Excel 失败: {type(exc).__name__}"
        ) from exc
    return result.stdout


def _escape_applescript_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _window_name_matches(actual: object, expected_stem: str) -> bool:
    """Excel 窗口标题是否带 .xlsx 取决于系统的扩展名显示设置。"""

    name = str(actual or "").strip()
    return name in {expected_stem, f"{expected_stem}.xlsx"}


def _is_complete_wind_excel_value(value: object) -> bool:
    text = str(value).strip()
    if not text or text.startswith("#"):
        return False
    normalized = text.casefold().replace(" ", "")
    pending_markers = (
        "requestingdata",
        "loading",
        "正在计算",
        "正在请求",
        "数据获取中",
    )
    return not any(marker in normalized for marker in pending_markers)


def _parse_copied_results(
    clipboard_text: str,
    *,
    expected_rows: int,
) -> list[str] | None:
    rows = list(csv.reader(StringIO(clipboard_text), delimiter="\t"))
    if len(rows) != expected_rows + 1:
        return None
    if len(rows[0]) < 2 or rows[0][:2] != ["查询项", "Wind结果"]:
        return None
    if any(len(row) < 2 for row in rows[1:]):
        return None
    return [row[1] for row in rows[1:]]
