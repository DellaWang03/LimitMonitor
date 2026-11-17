from __future__ import annotations

from dataclasses import dataclass, field
import importlib
import subprocess
import sys

import pandas as pd
import pytest

from src.pretrade import windpy_master
from src.pretrade.service_models import MasterSource
from src.pretrade.wind_excel_master import AnchorExcelValues, InitialExcelValues
from src.pretrade.windpy_master import DEFAULT_WIND_FIELDS, WindPyBondMasterProvider


DAY = pd.Timestamp("2026-07-10")


def _write_windpy_module(directory, marker: str) -> None:
    (directory / "WindPy.py").write_text(
        "class Gateway:\n"
        f"    marker = {marker!r}\n"
        "w = Gateway()\n",
        encoding="utf-8",
    )


def _clear_test_windpy_module(directory) -> object | None:
    importlib.invalidate_caches()
    original = sys.modules.pop("WindPy", None)
    directory_text = str(directory)
    while directory_text in sys.path:
        sys.path.remove(directory_text)
    return original


def _restore_test_windpy_module(original: object | None) -> None:
    sys.modules.pop("WindPy", None)
    if original is not None:
        sys.modules["WindPy"] = original


def test_provider_loads_windpy_from_configured_official_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _write_windpy_module(tmp_path, "configured-official-install")
    monkeypatch.setenv("LIMIT_MONITOR_WINDPY_PATH", str(tmp_path))
    original = _clear_test_windpy_module(tmp_path)

    try:
        gateway = WindPyBondMasterProvider._load_production_gateway()
        assert gateway is not None
        assert gateway.marker == "configured-official-install"
    finally:
        _restore_test_windpy_module(original)
        _clear_test_windpy_module(tmp_path)


def test_provider_loads_windpy_from_default_macos_official_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _write_windpy_module(tmp_path, "macos-official-install")
    monkeypatch.delenv("LIMIT_MONITOR_WINDPY_PATH", raising=False)
    monkeypatch.setattr(
        windpy_master, "_OFFICIAL_MACOS_WINDPY_PATH", tmp_path, raising=False
    )
    original = _clear_test_windpy_module(tmp_path)

    try:
        gateway = WindPyBondMasterProvider._load_production_gateway()
        assert gateway is not None
        assert gateway.marker == "macos-official-install"
    finally:
        _restore_test_windpy_module(original)
        _clear_test_windpy_module(tmp_path)


def _wind_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "SEC_NAME": "21台州01",
        "ISIN_CODE": "CND1000TEST1",
        "ISSUER": "原始权益人",
        "ISSUERUPDATED": "更新债务主体",
        "HOLDER_CONTROLLER": "原始实控人",
        "AGENCY_GUARANTOR": 0,
        "WINDL1TYPE": "中期票据",
        "WINDL2TYPE": "一般中期票据",
        "NATURE1": "地方国有企业",
        "MUNICIPALBONDWIND": "否",
    }
    row.update(overrides)
    return row


@dataclass
class FakeGateway:
    row: dict[str, object]
    start_result: object = 0
    calls: list[tuple[str, str, bool]] = field(default_factory=list)

    def start(self):
        return self.start_result

    def wss(self, bond_code: str, fields: str, *, usedf: bool):
        self.calls.append((bond_code, fields, usedf))
        return 0, pd.DataFrame([self.row])


@dataclass
class FakeExcelGateway:
    initial: InitialExcelValues
    anchor: AnchorExcelValues
    initial_calls: list[tuple[str, str | None, str | None]] = field(default_factory=list)
    anchor_calls: list[tuple[str, pd.Timestamp]] = field(default_factory=list)

    def resolve_initial(
        self, bond_code: str, *, issuer_name: str | None, guarantor_name: str | None
    ) -> InitialExcelValues:
        self.initial_calls.append((bond_code, issuer_name, guarantor_name))
        return self.initial

    def resolve_anchor_attributes(
        self, main_security_code: str, business_date: pd.Timestamp
    ) -> AnchorExcelValues:
        self.anchor_calls.append((main_security_code, business_date))
        return self.anchor


def _excel(
    *,
    main_code: object = "2180399.IB",
    industry: object = "公用事业",
    province: object = "浙江省",
    issuer_code: object = "F1000001.00",
    guarantor_code: object = None,
    main_name: object = "21台州债01",
    balance: object = 100.0,
) -> FakeExcelGateway:
    return FakeExcelGateway(
        InitialExcelValues(
            main_security_code=main_code,
            wind_industry=industry,
            province=province,
            issuer_wind_code=issuer_code,
            guarantor_wind_code=guarantor_code,
        ),
        AnchorExcelValues(
            main_security_name=main_name,
            outstanding_balance_yi=balance,
        ),
    )


def test_provider_constructs_source_shaped_master_for_ordinary_bond() -> None:
    gateway = FakeGateway(_wind_row())
    excel = _excel()

    result = WindPyBondMasterProvider(
        gateway=gateway,
        excel_gateway=excel,
        issuer_wind_code_mapping={"更新债务主体": "F0999999.00"},
        field_mapping_verified=True,
    ).resolve("184072.SH", DAY)

    assert result.source is MasterSource.WIND
    assert result.wind_data_date == "2026-07-10"
    assert result.wind_fetched_at is not None
    assert result.master is not None
    assert result.master.input_code == "184072.SH"
    assert result.master.asset_name == "21台州01"
    assert result.master.main_security_code == "2180399.IB"
    assert result.master.main_security_name == "21台州债01"
    assert result.master.outstanding_balance_yi == 100.0
    assert result.master.issuer_name == "更新债务主体"
    assert result.master.issuer_wind_code == "F0999999.00"
    assert result.master.controller_name is None
    assert "HOLDER_CONTROLLER" not in DEFAULT_WIND_FIELDS.split(",")
    assert result.master.guarantor_name == "0"
    assert result.master.guarantor_wind_code is None
    assert result.master.bond_classification == "信用债"
    assert result.master.bond_type == "中期票据"
    assert result.master.issuer_type == "国企"
    assert result.master.bond_category == "国企债"
    assert result.master.isin_code is None
    assert excel.initial_calls == [("184072.SH", None, None)]
    assert excel.anchor_calls == [("2180399.IB", DAY)]
    assert gateway.calls == [("184072.SH", DEFAULT_WIND_FIELDS, True)]


def test_provider_marks_rate_bond_credit_identity_fields_not_applicable() -> None:
    gateway = FakeGateway(
        _wind_row(
            SEC_NAME="26广东债06",
            ISSUERUPDATED="广东省人民政府",
            HOLDER_CONTROLLER=None,
            WINDL1TYPE="地方政府债",
            WINDL2TYPE="地方政府债",
            NATURE1=None,
        )
    )
    excel = _excel(
        main_code="2605080.IB",
        industry="000000",
        province="广东省",
        issuer_code="F1000598.00",
        main_name="26广东债06",
        balance=193.7,
    )

    result = WindPyBondMasterProvider(
        gateway=gateway,
        excel_gateway=excel,
        field_mapping_verified=True,
    ).resolve("2605080.IB", DAY)

    assert result.source is MasterSource.WIND
    assert result.master is not None
    assert result.master.bond_classification == "利率债"
    assert result.master.bond_category == "利率债"
    assert result.master.issuer_type is None
    assert result.master.controller_name is None
    assert result.master.main_security_code == "2605080.IB"
    assert result.master.outstanding_balance_yi == 193.7


def test_provider_still_requires_nature_for_credit_bond() -> None:
    result = WindPyBondMasterProvider(
        gateway=FakeGateway(_wind_row(NATURE1=None)),
        excel_gateway=_excel(),
        field_mapping_verified=True,
    ).resolve("X.IB", DAY)

    assert result.source is MasterSource.MISSING_MASTER
    assert result.master is None
    assert result.reason == "Wind 主数据缺少发行人类型原始值"


def test_provider_uses_issuer_only_for_exact_asset_backed_type2() -> None:
    result = WindPyBondMasterProvider(
        gateway=FakeGateway(_wind_row(WINDL2TYPE="资产支持证券")),
        excel_gateway=_excel(),
        field_mapping_verified=True,
    ).resolve("X.IB", DAY)

    assert result.master is not None
    assert result.master.issuer_name == "原始权益人"


def test_provider_keeps_issuerupdated_for_non_exact_abs_type2() -> None:
    result = WindPyBondMasterProvider(
        gateway=FakeGateway(_wind_row(WINDL2TYPE="证监会主管ABS")),
        excel_gateway=_excel(),
        field_mapping_verified=True,
    ).resolve("159636.SH", DAY)

    assert result.master is not None
    assert result.master.issuer_name == "更新债务主体"
    assert result.master.bond_classification == "信用债"


def test_provider_uses_excel_code_only_when_static_issuer_mapping_misses() -> None:
    excel = _excel(issuer_code="F1000001.00", guarantor_code=0)
    result = WindPyBondMasterProvider(
        gateway=FakeGateway(_wind_row(AGENCY_GUARANTOR="测试担保人")),
        excel_gateway=excel,
        issuer_wind_code_mapping={},
        field_mapping_verified=True,
    ).resolve("X.IB", DAY)

    assert result.master is not None
    assert result.master.issuer_wind_code == "F1000001.00"
    assert result.master.guarantor_name == "测试担保人"
    assert result.master.guarantor_wind_code is None
    assert excel.initial_calls == [("X.IB", "更新债务主体", "测试担保人")]


def test_provider_preserves_zero_main_name_and_balance_without_input_fallback() -> None:
    excel = _excel(main_code="UULB.SG", main_name=0, balance=0)
    result = WindPyBondMasterProvider(
        gateway=FakeGateway(_wind_row(SEC_NAME="26大华银行债01")),
        excel_gateway=excel,
        field_mapping_verified=True,
    ).resolve("292680009.IB", DAY)

    assert result.master is not None
    assert result.master.main_security_code == "UULB.SG"
    assert result.master.main_security_name == "0"
    assert result.master.outstanding_balance_yi == 0.0
    assert excel.anchor_calls == [("UULB.SG", DAY)]


def test_provider_returns_missing_for_true_required_wind_or_anchor_absence() -> None:
    missing_issuer = WindPyBondMasterProvider(
        gateway=FakeGateway(_wind_row(ISSUERUPDATED=None)),
        excel_gateway=_excel(),
        field_mapping_verified=True,
    ).resolve("X.IB", DAY)
    missing_anchor = WindPyBondMasterProvider(
        gateway=FakeGateway(_wind_row()),
        excel_gateway=_excel(main_code=None),
        field_mapping_verified=True,
    ).resolve("X.IB", DAY)

    assert missing_issuer.source is MasterSource.MISSING_MASTER
    assert missing_anchor.source is MasterSource.MISSING_MASTER


def test_provider_returns_missing_when_wind_start_fails() -> None:
    result = WindPyBondMasterProvider(
        gateway=FakeGateway(_wind_row(), start_result=-1),
        excel_gateway=_excel(),
        field_mapping_verified=True,
    ).resolve("X.IB", DAY)

    assert result.source is MasterSource.MISSING_MASTER
    assert result.master is None


def test_provider_uses_bounded_windpy_start_and_skips_connected_session() -> None:
    class StartAwareGateway:
        def __init__(self, *, connected: bool) -> None:
            self.connected = connected
            self.start_wait_times: list[int] = []

        def isconnected(self) -> bool:
            return self.connected

        def start(self, *, waitTime: int) -> int:
            self.start_wait_times.append(waitTime)
            return 0

        def wss(self, _bond_code: str, _fields: str, *, usedf: bool):
            assert usedf is True
            return 0, pd.DataFrame([_wind_row()])

    disconnected = StartAwareGateway(connected=False)
    connected = StartAwareGateway(connected=True)

    for gateway in (disconnected, connected):
        result = WindPyBondMasterProvider(
            gateway=gateway,
            excel_gateway=_excel(),
            field_mapping_verified=True,
        ).resolve("X.IB", DAY)
        assert result.source is MasterSource.WIND

    assert disconnected.start_wait_times == [windpy_master._WINDPY_START_WAIT_SECONDS]
    assert connected.start_wait_times == []


def test_macos_production_provider_uses_isolated_windpy_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def isolated_query(bond_code: str):
        calls.append(bond_code)
        return windpy_master._WindQueryResult(0, [_wind_row()], None)

    def forbidden_parent_import():
        raise AssertionError("macOS Streamlit 进程不得直接加载 WindPy")

    monkeypatch.setattr(windpy_master, "_IS_MACOS", True)
    monkeypatch.setattr(
        windpy_master, "_query_production_windpy_isolated", isolated_query
    )
    monkeypatch.setattr(
        WindPyBondMasterProvider,
        "_load_production_gateway",
        staticmethod(forbidden_parent_import),
    )

    result = WindPyBondMasterProvider(
        excel_gateway=_excel(),
        field_mapping_verified=True,
    ).resolve("184072.SH", DAY)

    assert result.source is MasterSource.WIND
    assert calls == ["184072.SH"]


def test_windows_production_provider_uses_isolated_windpy_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def isolated_query(bond_code: str):
        calls.append(bond_code)
        return windpy_master._WindQueryResult(0, [_wind_row()], None)

    def forbidden_parent_import():
        raise AssertionError("Windows Streamlit 进程不得直接加载 WindPy")

    monkeypatch.setattr(windpy_master, "_IS_MACOS", False)
    monkeypatch.setattr(windpy_master.sys, "platform", "win32")
    monkeypatch.setattr(
        windpy_master, "_query_production_windpy_isolated", isolated_query
    )
    monkeypatch.setattr(
        WindPyBondMasterProvider,
        "_load_production_gateway",
        staticmethod(forbidden_parent_import),
    )

    result = WindPyBondMasterProvider(
        excel_gateway=_excel(),
        field_mapping_verified=True,
    ).resolve("184072.SH", DAY)

    assert result.source is MasterSource.WIND
    assert calls == ["184072.SH"]


def test_isolated_windpy_query_is_fail_closed_on_hard_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(
            cmd=["python", "-m", "src.pretrade.windpy_worker"],
            timeout=windpy_master._WINDPY_SUBPROCESS_TIMEOUT_SECONDS,
        )

    monkeypatch.setattr(windpy_master.subprocess, "run", timeout)

    result = windpy_master._query_production_windpy_isolated("2605080.IB")

    assert result.error_code != 0
    assert result.rows == []
    assert result.reason is not None
    assert "超时" in result.reason


def test_isolated_windpy_query_parses_only_prefixed_worker_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stdout = "\n".join(
        [
            "Welcome to use Wind Quant API for Python (WindPy)!",
            (
                windpy_master._WINDPY_WORKER_RESULT_PREFIX
                + '{"error_code": 0, "rows": [{"SEC_NAME": "26广东债06"}]}'
            ),
        ]
    )
    completed = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout=stdout,
        stderr="",
    )
    monkeypatch.setattr(
        windpy_master.subprocess, "run", lambda *_args, **_kwargs: completed
    )

    result = windpy_master._query_production_windpy_isolated("2605080.IB")

    assert result.error_code == 0
    assert result.rows == [{"SEC_NAME": "26广东债06"}]
    assert result.reason is None


def test_isolated_windpy_query_executes_worker_with_configured_fake_module(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    (tmp_path / "WindPy.py").write_text(
        "import pandas as pd\n"
        "class Gateway:\n"
        "    def isconnected(self):\n"
        "        return False\n"
        "    def start(self, *, waitTime):\n"
        "        assert waitTime == 20\n"
        "        print('fake WindPy welcome')\n"
        "        return 0\n"
        "    def wss(self, bond_code, fields, *, usedf):\n"
        "        assert bond_code == '2605080.IB'\n"
        "        assert usedf is True\n"
        "        return 0, pd.DataFrame([{'SEC_NAME': '26广东债06'}])\n"
        "w = Gateway()\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("LIMIT_MONITOR_WINDPY_PATH", str(tmp_path))

    result = windpy_master._query_production_windpy_isolated("2605080.IB")

    assert result.error_code == 0
    assert result.rows == [{"SEC_NAME": "26广东债06"}]
    assert result.reason is None


def test_provider_is_fail_closed_until_real_field_mapping_is_verified() -> None:
    gateway = FakeGateway(_wind_row())

    result = WindPyBondMasterProvider(
        gateway=gateway,
        excel_gateway=_excel(),
    ).resolve("X.IB", DAY)

    assert result.source is MasterSource.MISSING_MASTER
    assert result.master is None
    assert result.reason and "字段映射" in result.reason
    assert gateway.calls == []


def test_provider_constructor_does_not_read_data_current_implicitly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_is_file(_path) -> bool:
        raise AssertionError("在线服务不得读取 data/current")

    monkeypatch.setattr(windpy_master.Path, "is_file", forbidden_is_file)

    WindPyBondMasterProvider()


def test_verified_provider_rejects_missing_required_master_field() -> None:
    result = WindPyBondMasterProvider(
        gateway=FakeGateway(_wind_row()),
        excel_gateway=_excel(province=None),
        field_mapping_verified=True,
    ).resolve("X.IB", DAY)

    assert result.source is MasterSource.MISSING_MASTER
    assert result.master is None
    assert result.reason and "province" in result.reason
