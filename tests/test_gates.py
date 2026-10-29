"""Typed gate reasons and attended-time accounting."""

from __future__ import annotations

import time

import pytest

from backend.core import settings
from backend.core.decision_policy import (
    build_entry_gate,
    build_identifier_gate,
    build_login_method_gate,
)
from backend.core.gates import GateReason, apply_gate_metadata, gate_reason
from backend.core.orchestrator import FormPilotOrchestrator
from backend.core.run_store import RunStore


ALL_GATE_TYPES = [
    "GATEWAY_DECISION",
    "ACCOUNT_CONFLICT",
    "LOGIN_METHOD",
    "ACCOUNT_IDENTIFIER",
    "MISSING_FIELD",
    "UNKNOWN_FIELD",
    "FILL_INCOMPLETE",
    "SECTION_APPROVAL",
    "CAPTCHA_SOLVE",
    "OTP_RELAY",
    "LIVE_PHOTO",
    "FILE_UPLOAD",
    "LIVE_HANDOFF",
    "PRE_PAYMENT_SAFETY_LOCK",
    "ERROR_DIAGNOSIS",
]


@pytest.mark.parametrize("gate_type", ALL_GATE_TYPES)
def test_every_gate_type_has_a_closed_reason(gate_type):
    gate = apply_gate_metadata({"gate_type": gate_type})

    assert gate["reason"] in {reason.value for reason in GateReason}
    assert gate["reason"] != GateReason.UNKNOWN.value


def test_an_unknown_gate_type_is_explicitly_unknown():
    gate = apply_gate_metadata({"gate_type": "SOMETHING_NEW"})

    assert gate["reason"] == GateReason.UNKNOWN.value


def test_a_next_step_gate_is_not_an_entry_path_gate():
    gate = apply_gate_metadata(
        {"gate_type": "GATEWAY_DECISION", "stage": "next_step", "title": "Next"}
    )

    assert gate_reason(gate) is GateReason.NEXT_STEP


def test_metadata_stamps_opening_time_and_a_deadline():
    gate = apply_gate_metadata({"gate_type": "OTP_RELAY"})

    assert gate["gate_opened_at"]
    assert gate["gate_deadline_at"]
    assert gate["gate_timeout_seconds"] == settings.GATE_TIMEOUT_SECONDS


def test_choice_gates_never_recommend_a_choice():
    gates = [
        build_entry_gate(
            [
                {"text": "Register", "type": "button", "mode": "register"},
                {"text": "Sign in", "type": "button", "mode": "login"},
            ]
        ),
        build_login_method_gate(
            {
                "field": {"label": "Login method"},
                "options": [
                    {"value": "otp", "text": "OTP", "method": "otp"},
                    {"value": "password", "text": "Password", "method": "password"},
                ],
            }
        ),
        build_identifier_gate(
            {
                "options": [
                    {"key": "mobile", "label": "Mobile"},
                    {"key": "email", "label": "Email"},
                ]
            }
        ),
    ]

    for gate in gates:
        stamped = apply_gate_metadata(gate)
        assert "recommended" not in stamped


def test_incomplete_fill_recommends_a_recheck_not_continuing():
    gate = apply_gate_metadata(
        {
            "gate_type": "FILL_INCOMPLETE",
            "options": [
                {"action": "FILL_RECHECK", "label": "Recheck and fill again"},
                {"action": "CONTINUE", "label": "Continue after reviewing"},
            ],
        }
    )

    assert gate["recommended"]["action"] == "FILL_RECHECK"
    assert gate["recommended"]["label"] == "Recheck and fill again"


def test_error_diagnosis_recommends_reading_before_retrying():
    gate = apply_gate_metadata(
        {
            "gate_type": "ERROR_DIAGNOSIS",
            "suggested_actions": ["Review the details", "Try again", "Stop"],
        }
    )

    assert gate["recommended"]["label"] == "Review the details"


def test_a_ten_minute_human_pause_does_not_expire_the_gate():
    assert settings.GATE_TIMEOUT_SECONDS >= 600


# ------------------------------------------------------------------- clock


def test_the_run_clock_pauses_while_a_gate_is_open(monkeypatch):
    monkeypatch.setattr(settings, "RUN_CEILING_SECONDS", 600)
    monkeypatch.setattr(settings, "RUN_WALL_CEILING_SECONDS", 7200)
    orchestrator = FormPilotOrchestrator()
    orchestrator._run_started_monotonic = time.monotonic() - 700
    orchestrator._gate_opened_monotonic = time.monotonic() - 650

    clock = orchestrator.run_clock()

    assert clock["gate_open"] is True
    assert clock["attended_seconds"] >= 649
    assert clock["active_seconds"] <= 51
    # 700s wall time, but only ~50s of active work: the active budget is safe.
    assert orchestrator._run_ceiling_exceeded() is False


def test_the_absolute_wall_ceiling_still_applies_during_a_gate(monkeypatch):
    monkeypatch.setattr(settings, "RUN_CEILING_SECONDS", 10**6)
    monkeypatch.setattr(settings, "RUN_WALL_CEILING_SECONDS", 600)
    orchestrator = FormPilotOrchestrator()
    orchestrator._run_started_monotonic = time.monotonic() - 700
    orchestrator._gate_opened_monotonic = time.monotonic() - 650

    assert orchestrator._run_ceiling_exceeded() is True


def test_active_work_over_budget_is_detected(monkeypatch):
    monkeypatch.setattr(settings, "RUN_CEILING_SECONDS", 600)
    monkeypatch.setattr(settings, "RUN_WALL_CEILING_SECONDS", 7200)
    orchestrator = FormPilotOrchestrator()
    orchestrator._run_started_monotonic = time.monotonic() - 700
    orchestrator._gate_opened_monotonic = None
    orchestrator._gate_seconds = 0.0

    assert orchestrator._run_ceiling_exceeded() is True


# ------------------------------------------------------------------ ledger


def test_a_gate_step_carries_its_reason_and_measures_dwell(tmp_path):
    orchestrator = FormPilotOrchestrator()
    orchestrator.run_id = "run-gate"
    orchestrator.run_store = RunStore(tmp_path / "runs")
    gate = {"gate_type": "OTP_RELAY", "title": "Enter the code"}

    orchestrator._start_gate_step(gate)

    assert gate["reason"] == GateReason.OTP.value
    assert orchestrator.run_clock()["gate_open"] is True
    step = orchestrator.run_store.read_steps("run-gate")[0]
    assert step["kind"] == "gate"
    assert step["status"] == "waiting"
    assert step["output"]["reason"] == GateReason.OTP.value

    orchestrator._gate_opened_monotonic = time.monotonic() - 5
    orchestrator._close_gate_step("OTP_SUBMIT")

    assert orchestrator.run_clock()["gate_open"] is False
    assert orchestrator._gate_seconds >= 5
    step = orchestrator.run_store.read_steps("run-gate")[0]
    assert step["status"] == "resolved"
    assert step["output"] == {"action": "OTP_SUBMIT"}


def test_a_gate_that_times_out_closes_its_row(tmp_path):
    orchestrator = FormPilotOrchestrator()
    orchestrator.run_id = "run-gate"
    orchestrator.run_store = RunStore(tmp_path / "runs")
    orchestrator._start_gate_step({"gate_type": "MISSING_FIELD", "title": "Need a value"})

    orchestrator._close_gate_step("TIMEOUT")

    step = orchestrator.run_store.read_steps("run-gate")[0]
    assert step["status"] == "timed_out"
    assert orchestrator.run_clock()["gate_open"] is False
