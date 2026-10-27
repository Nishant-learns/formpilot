"""Orchestrator state and the opt-in full practice-portal flow."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from backend.core.orchestrator import FormPilotOrchestrator

ROOT = Path(__file__).resolve().parents[1]


def test_orchestrator_starts_idle_and_can_pause():
    orchestrator = FormPilotOrchestrator()

    state = orchestrator.get_state()
    assert state["state"] == "IDLE"
    assert state["is_running"] is False
    assert state["filled_audit"] == []
    assert state["oracle"] is None

    orchestrator.pause()
    assert orchestrator.get_state()["paused"] is True
    orchestrator.resume()
    assert orchestrator.get_state()["paused"] is False


def test_orchestrator_holds_a_candidate_response_until_a_gate_is_read():
    orchestrator = FormPilotOrchestrator()
    orchestrator.active_gate = {"gate_type": "SECTION_APPROVAL"}

    orchestrator.submit_user_response({"action": "SECTION_APPROVAL", "approved": True})

    assert orchestrator._pending_user_response == {
        "action": "SECTION_APPROVAL",
        "approved": True,
    }


def test_stop_wins_a_race_with_a_gate_opening():
    """A stop request must not leave the run waiting at a freshly opened gate."""
    import asyncio

    async def scenario():
        orchestrator = FormPilotOrchestrator()
        orchestrator.is_running = True
        orchestrator.state = "RUNNING"
        orchestrator.active_gate = {"gate_type": "SECTION_APPROVAL"}
        waiter = asyncio.create_task(orchestrator._wait_for_user_response())
        await asyncio.sleep(0)
        await orchestrator.stop()
        result = await asyncio.wait_for(waiter, timeout=2)
        return orchestrator, result

    orchestrator, result = asyncio.run(scenario())

    assert result == {"action": "STOPPED"}
    assert orchestrator.state == "STOPPED"
    assert orchestrator.active_gate is None
    assert orchestrator.get_state()["active_gate"] is None


def test_final_submit_and_payment_buttons_trigger_a_safety_stop():
    orchestrator = FormPilotOrchestrator()

    for label in (
        "Submit Application",
        "Final Submit",
        "Pay Now",
        "Proceed to Pay",
        "Complete Registration",
    ):
        assert orchestrator._is_final_action({"text": label}) is True, label

    for label in ("Save & Next", "Continue", "Verify OTP", "Candidate Login"):
        assert orchestrator._is_final_action({"text": label}) is False, label

    assert orchestrator._is_final_action({"text": "Save & Next: Pre-Payment Review"}) is False
    assert orchestrator._is_final_action({"text": "Review and Submit"}) is True


def test_empty_spa_shell_is_not_remembered_as_a_recipe():
    orchestrator = FormPilotOrchestrator()

    assert orchestrator._has_replayable_structure({"fields": [], "gateways": []}) is False
    assert orchestrator._has_replayable_structure({"fields": [], "gateways": None}) is False
    assert orchestrator._has_replayable_structure({"fields": [{"key": "full_name"}]}) is True
    assert orchestrator._has_replayable_structure(
        {"fields": [], "gateways": [{"type": "LOGIN", "text": "Login"}]}
    ) is True


def test_unknown_field_gate_skips_captcha_and_one_time_codes():
    orchestrator = FormPilotOrchestrator()

    for item in (
        {"label": "Captcha Code", "name": "captcha_code", "type": "text"},
        {"label": "Enter OTP", "name": "otp_code", "type": "text"},
        {"label": "One-time password", "name": "code", "type": "text"},
        {"label": "Verification Code", "name": "verification_code", "type": "text"},
        {"label": "Security check", "name": "security_check", "type": "text"},
        {"label": "", "name": "otp", "id": "otp-input", "type": "text"},
    ):
        assert orchestrator._should_ask_unknown(item) is False, item

    for item in (
        {"label": "APAR ID", "name": "apar_id", "type": "text"},
        {"label": "Father's Name", "name": "father_name", "type": "text"},
        {"label": "Roll Number", "name": "roll_number", "type": "text"},
    ):
        assert orchestrator._should_ask_unknown(item) is True, item

    assert orchestrator._should_ask_unknown({"label": "Search", "type": "search"}) is False
    assert orchestrator._should_ask_unknown({"label": "Upload photo", "type": "file"}) is False


@pytest.mark.e2e
@pytest.mark.parametrize(
    ("route", "expected"),
    [([], "STOPPED BEFORE PAYMENT"), (["--login"], "FINAL STATE: DONE")],
    ids=["new-registration", "returning-candidate"],
)
def test_full_practice_flow(route, expected):
    """Run the real browser flow when a practice server URL is provided.

    Start the app with ``./run.sh`` and then run::

        FORMPILOT_E2E_URL=http://127.0.0.1:8000/gov-portal-demo pytest -m e2e
    """
    url = os.getenv("FORMPILOT_E2E_URL")
    if not url:
        pytest.skip("Set FORMPILOT_E2E_URL to run the browser-based practice flow.")

    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "e2e_demo.py"), url, *route],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )

    output = completed.stdout + completed.stderr
    assert completed.returncode == 0, output
    assert expected in output
    assert "Traceback" not in output
    assert "Future exception was never retrieved" not in output
