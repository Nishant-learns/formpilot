"""The run ledger: steps, attempts, redaction and the read API."""

from __future__ import annotations

import json
from types import SimpleNamespace

from backend.core.failures import FailureCode, classify_failure, is_retryable
from backend.core.run_store import RunStore
from backend.core.orchestrator import FormPilotOrchestrator

from tests.browser_helpers import run_with_page


def _store(tmp_path) -> RunStore:
    return RunStore(tmp_path / "runs")


# ------------------------------------------------------------------ steps


def test_a_step_records_kind_status_output_and_duration(tmp_path):
    store = _store(tmp_path)
    store.start("run-1", {"query": "hpsc", "mode": "fill"})

    store.record_step(
        "run-1",
        "fill",
        output={"attempted": 3, "verified": 3},
        duration_ms=42,
    )

    steps = store.read_steps("run-1")
    assert len(steps) == 1
    step = steps[0]
    assert step["step_id"] == "stp-0001"
    assert step["seq"] == 1
    assert step["kind"] == "fill"
    assert step["status"] == "ok"
    assert step["output"] == {"attempted": 3, "verified": 3}
    assert step["duration_ms"] == 42
    assert step["attempt"] == 1


def test_a_retry_is_its_own_row_not_an_overwrite(tmp_path):
    store = _store(tmp_path)

    first = store.start_step("run-1", "fill", attempt=1)
    store.finish_step("run-1", first, "failed", error_code="field_not_held")
    second = store.start_step("run-1", "fill", attempt=2)
    store.finish_step("run-1", second, "ok", output={"verified": 1})

    steps = store.read_steps("run-1")
    assert [step["attempt"] for step in steps] == [1, 2]
    assert [step["status"] for step in steps] == ["failed", "ok"]
    assert steps[0]["error_code"] == "field_not_held"
    assert steps[0]["retryable"] is False
    assert store.step_summary("run-1")["retried"] == 1


def test_a_waiting_gate_becomes_resolved_without_storing_the_answer(tmp_path):
    store = _store(tmp_path)

    step_id = store.start_step(
        "run-1",
        "gate",
        status="waiting",
        detail={"gate_type": "OTP_RELAY", "title": "Enter the code"},
    )
    store.finish_step("run-1", step_id, "resolved", output={"action": "OTP_SUBMIT"})

    steps = store.read_steps("run-1")
    assert steps[0]["status"] == "resolved"
    assert steps[0]["output"] == {"action": "OTP_SUBMIT"}


def test_secrets_are_never_written_to_the_ledger(tmp_path):
    store = _store(tmp_path)

    store.record_step(
        "run-1",
        "gate",
        output={
            "action": "OTP_SUBMIT",
            "otp": "123456",
            "password": "hunter2",
            "identifier_value": "9876543210",
            "nested": {"token": "abc", "field": "mobile"},
        },
    )

    raw = (tmp_path / "runs" / "run-1" / "steps.json").read_text(encoding="utf-8")
    assert "123456" not in raw
    assert "hunter2" not in raw
    assert "9876543210" not in raw
    assert '"abc"' not in raw
    assert '"field": "mobile"' in raw


def test_long_text_is_truncated_in_the_ledger(tmp_path):
    store = _store(tmp_path)

    store.record_step("run-1", "error", output={"message": "x" * 2000})

    step = store.read_steps("run-1")[0]
    assert len(step["output"]["message"]) <= 501
    assert step["output"]["message"].endswith("…")


def test_the_ledger_survives_a_new_store_instance(tmp_path):
    store = _store(tmp_path)
    store.record_step("run-1", "perceive", output={"page_type": "form"})

    reopened = RunStore(tmp_path / "runs")

    assert reopened.read_steps("run-1")[0]["output"] == {"page_type": "form"}


def test_finish_adds_duration_steps_and_a_failure_code(tmp_path):
    store = _store(tmp_path)
    store.start("run-1", {"query": "hpsc"})
    store.record_step("run-1", "perceive")
    store.finish("run-1", "FAILED", {"error": "The portal did not move to the next step."})

    meta = store.read_meta("run-1")
    assert meta["state"] == "FAILED"
    assert meta["steps"] == 1
    assert meta["error_code"] == FailureCode.NAVIGATION.value
    assert meta["duration_ms"] is not None and meta["duration_ms"] >= 0


def test_run_detail_and_list_are_enough_to_reconstruct_a_run(tmp_path):
    store = _store(tmp_path)
    store.start("run-1", {"query": "hpsc", "run_mode": "fill"})
    store.append("run-1", {"phase": "SENSE", "message": "reading"})
    store.record_step("run-1", "fill", output={"verified": 2})
    store.save_audit("run-1", {"records": []})
    store.finish("run-1", "DONE")

    detail = store.run_detail("run-1")
    assert detail["meta"]["state"] == "DONE"
    assert detail["steps"][0]["kind"] == "fill"
    assert detail["summary"]["steps"] == 1
    assert detail["events"][0]["phase"] == "SENSE"
    assert detail["audit"] == {"records": []}

    listed = store.list_runs(limit=10)
    assert listed[0]["run_id"] == "run-1"
    assert listed[0]["steps"] == 1
    assert listed[0]["run_mode"] == "fill"


def test_list_runs_supports_offset(tmp_path):
    store = _store(tmp_path)
    for index in range(3):
        store.start(f"run-{index}", {"query": str(index)})

    assert len(store.list_runs(limit=2)) == 2
    assert len(store.list_runs(limit=2, offset=2)) == 1


# ------------------------------------------------------------------ failures


def test_failure_codes_are_classified_from_the_message():
    assert classify_failure("The portal did not move to the next step.") is FailureCode.NAVIGATION
    assert classify_failure("The field disappeared after it was filled.") is FailureCode.ELEMENT_NOT_FOUND
    assert classify_failure("The portal did not keep the value.") is FailureCode.FIELD_NOT_HELD
    assert classify_failure("A security check is visible.") is FailureCode.ANTI_BOT
    assert classify_failure("The request timed out.") is FailureCode.TIMEOUT
    assert classify_failure("") is FailureCode.INTERNAL
    assert classify_failure("something strange") is FailureCode.INTERNAL


def test_only_transient_codes_are_retryable():
    assert is_retryable(FailureCode.TIMEOUT) is True
    assert is_retryable(FailureCode.NAVIGATION) is True
    assert is_retryable(FailureCode.AUTH) is False
    assert is_retryable(FailureCode.FIELD_NOT_HELD) is False
    assert is_retryable("not_a_code") is False


# ------------------------------------------------------------------ orchestrator


def test_the_orchestrator_records_a_fill_step_without_values(tmp_path):
    async def scenario(page):
        await page.set_content(
            """
            <html><body>
              <label for="full_name">Full Name</label>
              <input id="full_name" name="full_name" type="text">
            </body></html>
            """
        )
        orchestrator = FormPilotOrchestrator()
        orchestrator.page = page
        orchestrator.target_url = page.url
        orchestrator.is_running = True
        orchestrator.run_id = "run-fill"
        orchestrator.run_store = RunStore(tmp_path / "runs")
        orchestrator.vault_mgr = SimpleNamespace(
            vault=SimpleNamespace(
                values={"full_name": "Nishant Kumar"},
                find_field_value=lambda key: "Nishant Kumar",
                get_formatted_dob=lambda fmt: None,
            )
        )
        dom = await orchestrator._scan_dom()

        await orchestrator._fill_form(dom)

        steps = orchestrator.run_store.read_steps("run-fill")
        fill_steps = [step for step in steps if step["kind"] == "fill"]
        assert fill_steps
        assert fill_steps[-1]["status"] == "ok"
        assert fill_steps[-1]["output"]["verified"] == 1
        raw = json.dumps(steps)
        assert "Nishant Kumar" not in raw

    run_with_page(scenario)


def test_a_gate_is_one_row_from_waiting_to_resolved(tmp_path):
    orchestrator = FormPilotOrchestrator()
    orchestrator.run_id = "run-gate"
    orchestrator.run_store = RunStore(tmp_path / "runs")

    orchestrator._start_gate_step({"gate_type": "OTP_RELAY", "title": "Enter the code"})
    orchestrator._start_gate_step({"gate_type": "OTP_RELAY", "title": "Enter the code"})
    orchestrator.submit_user_response({"action": "OTP_SUBMIT", "otp": "123456"})

    steps = orchestrator.run_store.read_steps("run-gate")
    assert len(steps) == 1
    assert steps[0]["status"] == "resolved"
    assert steps[0]["output"] == {"action": "OTP_SUBMIT"}
    assert "123456" not in json.dumps(steps)


def test_the_api_lists_and_reads_a_run_with_its_steps(client):
    import shutil

    from backend.main import run_store

    run_id = "api-run-ledger"
    try:
        run_store.start(run_id, {"query": "hpsc", "run_mode": "fill"})
        run_store.record_step(run_id, "perceive", output={"page_type": "form"})
        run_store.record_step(run_id, "fill", output={"verified": 2})
        run_store.finish(run_id, "DONE")

        listing = client.get("/api/runs")
        assert listing.status_code == 200
        assert any(item["run_id"] == run_id for item in listing.json()["runs"])

        detail = client.get(f"/api/runs/{run_id}")
        assert detail.status_code == 200
        payload = detail.json()
        assert payload["meta"]["state"] == "DONE"
        assert [step["kind"] for step in payload["steps"]] == ["perceive", "fill"]
        assert payload["summary"]["steps"] == 2

        steps = client.get(f"/api/runs/{run_id}/steps")
        assert steps.status_code == 200
        assert steps.json()["summary"]["by_kind"] == {"perceive": 1, "fill": 1}
    finally:
        shutil.rmtree(run_store.root / run_id, ignore_errors=True)
