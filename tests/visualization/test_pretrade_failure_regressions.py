"""Exercise real Streamlit reruns at the integrated service/UI boundary."""

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest


def _unavailable_snapshot_app(page_name):
    import importlib
    from types import SimpleNamespace
    from unittest.mock import patch
    from src.pretrade.pretrade_service import PretradeRiskService
    from src.pretrade.context_store import PretradeContextStoreError

    class Store:
        def get_current_snapshot(self):
            raise PretradeContextStoreError("internal connection details")

    page = importlib.import_module(f"src.visualization.pages.{page_name}")
    service = PretradeRiskService(store=Store(), wind_provider=None)
    with patch.object(page, "get_pretrade_risk_service", return_value=service):
        page.render({}, SimpleNamespace(target_date=None))


@pytest.mark.parametrize("page_name", ["page8_bond_quota", "page10_basket_pretrade"])
def test_snapshot_pointer_failure_is_a_page_message_not_an_exception(page_name):
    app = AppTest.from_function(_unavailable_snapshot_app, args=(page_name,)).run()
    assert not app.exception
    assert [item.value for item in app.error] == [
        "当前交易前快照暂不可用，请稍后重试或联系系统管理员。"
    ]


def _basket_retry_app():
    from types import SimpleNamespace
    from unittest.mock import patch
    import streamlit as st
    from src.pretrade.pretrade_service import PretradeServiceError
    from src.visualization.pages import page10_basket_pretrade as page

    class Service:
        def available_accounts(self):
            return ("自营部交易性",)

        def check_basket(self, lines):
            st.session_state.setdefault("seen_orders", []).append(
                [(line.bond_code, line.pr_wan) for line in lines]
            )
            failure = st.session_state.pop("fail_next", None)
            if failure:
                raise {"snapshot": PretradeServiceError, "input": ValueError,
                       "unexpected": RuntimeError}[failure]("temporary failure")
            return SimpleNamespace(snapshot_data_date="2026-11-13")

    with patch.object(page, "get_pretrade_risk_service", return_value=Service()), patch.object(
        page, "_render_result", side_effect=lambda *_args, **_kwargs: st.write("calculated")
    ):
        page.render({}, SimpleNamespace(target_date=None))


@pytest.mark.parametrize("failure", ["snapshot", "input", "unexpected"])
def test_modified_basket_survives_a_failed_submission_and_retry(failure):
    app = AppTest.from_function(_basket_retry_app)
    app.session_state["page10_pretrade_submitted_lines"] = pd.DataFrame([{
        "债券代码": "1980082.IB", "拟买金额(万)_PR": "100",
        "拟买入账户": "自营部交易性", "拟买全价成本(万)": "",
    }])
    app.run()
    assert not app.exception
    editor_delta = {
        "edited_rows": {0: {"拟买金额(万)_PR": "200"}},
        "added_rows": [], "deleted_rows": [],
    }
    app.session_state["page10_pretrade_lines"] = editor_delta
    app.session_state["fail_next"] = failure
    app.button(key="page10_pretrade_calculate").click().run()
    assert not app.exception
    assert len(app.error) == 1
    # AppTest has no data_editor widget driver; resend the browser's unchanged
    # delta on the next submission. Its original input frame must still exist.
    assert app.session_state["page10_pretrade_submitted_lines"].iloc[0]["拟买金额(万)_PR"] == "100"
    app.session_state["page10_pretrade_lines"] = editor_delta
    app.button(key="page10_pretrade_calculate").click().run()
    assert not app.exception
    assert not app.error
    assert app.session_state["seen_orders"] == [
        [("1980082.IB", 200.0)], [("1980082.IB", 200.0)],
    ]
    assert app.session_state["page10_pretrade_submitted_lines"].iloc[0]["拟买金额(万)_PR"] == "200"
    app.button(key="page10_pretrade_modify").click().run()
    assert not app.exception
    assert app.dataframe[0].value.iloc[0]["拟买金额(万)_PR"] == "200"
    app.button(key="page10_pretrade_clear").click().run()
    assert not app.exception
    assert app.dataframe[0].value.iloc[0]["债券代码"] == ""
