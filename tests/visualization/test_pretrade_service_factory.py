from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.pretrade.pretrade_service import PretradeServiceError
from src.visualization import pretrade_service


def _capture_field_mapping_flag(monkeypatch, value: str | None) -> bool:
    captured: dict[str, bool] = {}
    if value is None:
        monkeypatch.delenv("LIMIT_MONITOR_WIND_FIELD_MAPPING_VERIFIED", raising=False)
    else:
        monkeypatch.setenv("LIMIT_MONITOR_WIND_FIELD_MAPPING_VERIFIED", value)

    monkeypatch.setattr(
        pretrade_service.ArchiveDB,
        "from_env",
        staticmethod(lambda: SimpleNamespace(engine="engine")),
    )
    monkeypatch.setattr(
        pretrade_service,
        "PretradeContextStore",
        lambda engine: SimpleNamespace(engine=engine),
    )

    def _provider(*, field_mapping_verified: bool):
        captured["verified"] = field_mapping_verified
        return SimpleNamespace()

    monkeypatch.setattr(pretrade_service, "WindPyBondMasterProvider", _provider)
    monkeypatch.setattr(
        pretrade_service,
        "PretradeRiskService",
        lambda **kwargs: SimpleNamespace(**kwargs),
    )

    pretrade_service.get_pretrade_risk_service()
    return captured["verified"]


def test_wind_field_mapping_is_fail_closed_by_default(monkeypatch) -> None:
    assert _capture_field_mapping_flag(monkeypatch, None) is False


def test_wind_field_mapping_can_be_enabled_after_real_acceptance(monkeypatch) -> None:
    assert _capture_field_mapping_flag(monkeypatch, "true") is True


def test_factory_wraps_missing_database_configuration(monkeypatch) -> None:
    monkeypatch.setattr(
        pretrade_service.ArchiveDB,
        "from_env",
        staticmethod(lambda: (_ for _ in ()).throw(KeyError("DB_HOST"))),
    )

    with pytest.raises(PretradeServiceError, match="交易前数据库"):
        pretrade_service.get_pretrade_risk_service()
