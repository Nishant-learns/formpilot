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
