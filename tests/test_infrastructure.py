"""Run journal and portal adapter behaviour."""

from __future__ import annotations

import pytest

from backend.core.portal_adapter import BasePortalAdapter, SimulatorAdapter, get_adapter
from backend.core.run_store import RunStore


def test_run_store_records_and_lists_runs(tmp_path):
    store = RunStore(root=tmp_path / "runs")
    store.start("run_123", {"query": "practice"})
    store.append("run_123", {"phase": "SENSE", "message": "Reading the page"})
    store.save_audit("run_123", {"matches": 3, "total": 3})
    store.finish("run_123", "AWAITING_PAYMENT")

    meta = store.read_meta("run_123")
    assert meta["state"] == "AWAITING_PAYMENT"
    assert meta["query"] == "practice"
    assert store.read_events("run_123")[0]["phase"] == "SENSE"
    assert store.read_audit("run_123")["matches"] == 3

    runs = store.list_runs()
    assert [run["run_id"] for run in runs] == ["run_123"]
    assert runs[0]["state"] == "AWAITING_PAYMENT"


def test_run_store_rejects_unsafe_run_ids(tmp_path):
    store = RunStore(root=tmp_path / "runs")

    for run_id in ("../escape", "a/b", "", "x" * 65):
        with pytest.raises(ValueError):
            store.start(run_id, {})


def test_simulator_adapter_reads_steps_and_payment():
    adapter = SimulatorAdapter()

    assert adapter.current_step(None, {"activeSectionId": "sec-3"}) == 3
    assert adapter.current_step_from_dom({"activeSectionId": "sec-2"}) == 2
    assert adapter.is_payment_page(None, {"activeSectionId": "sec-4"}) is True
    assert adapter.is_payment_page(None, {"activeSectionId": "sec-2"}) is False


def test_simulator_adapter_picks_the_expected_next_button():
    adapter = SimulatorAdapter()
    dom = {
        "activeSectionId": "sec-2",
        "nextButtons": [
            {"id": "btn-save-next-1", "text": "Save & Next"},
            {"id": "btn-save-next-2", "text": "Save & Next"},
        ],
    }

    button = adapter.find_next_button(dom)

    assert button["id"] == "btn-save-next-2"


def test_adapter_selection_is_url_based():
    assert isinstance(get_adapter("http://127.0.0.1:8000/gov-portal-demo"), SimulatorAdapter)
    assert isinstance(get_adapter("https://ssc.gov.in/"), BasePortalAdapter)


def test_generic_adapter_finds_gateways():
    adapter = BasePortalAdapter()
    dom = {"gateways": [{"type": "NEW_REGISTRATION", "id": "new"}]}

    assert adapter.find_gateway(dom, "NEW_REGISTRATION")["id"] == "new"
    assert adapter.find_gateway(dom, "LOGIN") is None
