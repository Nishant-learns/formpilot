"""Closed vocabulary for human gates.

A gate is a stop, not a chat message.  Two things must be stable across the
backend, the ledger, the chat and the cockpit:

* **why** it opened (a closed ``reason`` code, not prose), and
* **what happens while it is open** (the run clock pauses, the gate clock runs).

The gate's free-text ``why`` field remains the human explanation.  ``reason``
is the machine-readable code an evaluation harness, a metric and a UI label can
all agree on.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, Optional

from . import settings


class GateReason(str, Enum):
    ENTRY_PATH = "entry_path_choice"
    NEXT_STEP = "next_step_choice"
    ACCOUNT_CONFLICT = "account_conflict"
    LOGIN_METHOD = "login_method_choice"
    ACCOUNT_IDENTIFIER = "account_identifier_choice"
    MISSING_FACT = "missing_fact"
    UNKNOWN_FIELD = "unknown_field"
    INCOMPLETE_FILL = "incomplete_fill"
    SECTION_REVIEW = "section_review"
    CAPTCHA = "captcha_human_only"
    OTP = "otp_human_only"
    LIVE_PHOTO = "live_photo"
    FILE_UPLOAD = "file_upload"
    HUMAN_HANDOFF = "human_handoff"
    PRE_PAYMENT_REVIEW = "pre_payment_review"
    ERROR_DIAGNOSIS = "error_diagnosis"
    UNKNOWN = "unknown"


_REASON_BY_TYPE = {
    "GATEWAY_DECISION": GateReason.ENTRY_PATH,
    "ACCOUNT_CONFLICT": GateReason.ACCOUNT_CONFLICT,
    "LOGIN_METHOD": GateReason.LOGIN_METHOD,
    "ACCOUNT_IDENTIFIER": GateReason.ACCOUNT_IDENTIFIER,
    "MISSING_FIELD": GateReason.MISSING_FACT,
    "UNKNOWN_FIELD": GateReason.UNKNOWN_FIELD,
    "FILL_INCOMPLETE": GateReason.INCOMPLETE_FILL,
    "SECTION_APPROVAL": GateReason.SECTION_REVIEW,
    "CAPTCHA_SOLVE": GateReason.CAPTCHA,
    "OTP_RELAY": GateReason.OTP,
    "LIVE_PHOTO": GateReason.LIVE_PHOTO,
    "FILE_UPLOAD": GateReason.FILE_UPLOAD,
    "LIVE_HANDOFF": GateReason.HUMAN_HANDOFF,
    "PRE_PAYMENT_SAFETY_LOCK": GateReason.PRE_PAYMENT_REVIEW,
    "ERROR_DIAGNOSIS": GateReason.ERROR_DIAGNOSIS,
}

# Gates where the whole point is that the human chooses.  A recommendation
# here would be a guess wearing a badge.
_NO_RECOMMENDATION = {
    GateReason.ENTRY_PATH,
    GateReason.NEXT_STEP,
    GateReason.ACCOUNT_CONFLICT,
    GateReason.LOGIN_METHOD,
    GateReason.ACCOUNT_IDENTIFIER,
    GateReason.MISSING_FACT,
    GateReason.UNKNOWN_FIELD,
    GateReason.SECTION_REVIEW,
    GateReason.CAPTCHA,
    GateReason.OTP,
    GateReason.LIVE_PHOTO,
    GateReason.FILE_UPLOAD,
    GateReason.HUMAN_HANDOFF,
    GateReason.PRE_PAYMENT_REVIEW,
}


def gate_reason(gate: Dict[str, Any]) -> GateReason:
    """Map a gate to its closed reason code."""
    gate_type = str((gate or {}).get("gate_type") or "")
    if gate_type == "GATEWAY_DECISION" and (gate or {}).get("stage") == "next_step":
        return GateReason.NEXT_STEP
    return _REASON_BY_TYPE.get(gate_type, GateReason.UNKNOWN)


def gate_recommendation(gate: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """A safe suggestion, never a choice only the human can make.

    Only gates with an objectively safer first move carry a recommendation:
    recheck dropped fields, or read the portal message before retrying.  A
    gate that exists because the human must decide stays unmarked.
    """
    if not gate:
        return None
    if gate.get("requires_explicit_choice") or gate.get("no_default"):
        return None
    if isinstance(gate.get("recommended"), dict):
        return gate["recommended"]
    reason = gate_reason(gate)
    if reason in _NO_RECOMMENDATION:
        return None

    options = gate.get("options") or []
    marked = next((option for option in options if option.get("recommended")), None)
    if marked:
        return {
            "action": marked.get("action"),
            "value": marked.get("value"),
            "label": marked.get("label") or marked.get("text"),
            "reason": marked.get("recommendation_reason")
            or "This is the safer first step.",
        }

    if reason is GateReason.INCOMPLETE_FILL:
        recheck = next(
            (option for option in options if option.get("action") == "FILL_RECHECK"),
            None,
        )
        if recheck:
            return {
                "action": "FILL_RECHECK",
                "label": recheck.get("label") or "Recheck and fill again",
                "reason": "Fix the fields the portal did not keep before moving on.",
            }

    if reason is GateReason.ERROR_DIAGNOSIS:
        actions = [str(action) for action in (gate.get("suggested_actions") or []) if action]
        if actions:
            return {
                "label": actions[0],
                "reason": "Read the portal message before changing anything.",
            }
    return None


def apply_gate_metadata(
    gate: Dict[str, Any],
    *,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Stamp the closed reason, opening time, deadline and safe recommendation."""
    if not isinstance(gate, dict):
        return gate
    opened = now or datetime.now(timezone.utc)
    gate["reason"] = gate_reason(gate).value
    gate.setdefault("gate_opened_at", opened.isoformat())
    gate.setdefault("gate_timeout_seconds", settings.GATE_TIMEOUT_SECONDS)
    gate.setdefault(
        "gate_deadline_at",
        (opened + timedelta(seconds=settings.GATE_TIMEOUT_SECONDS)).isoformat(),
    )
    recommendation = gate_recommendation(gate)
    if recommendation:
        gate["recommended"] = recommendation
    else:
        gate.pop("recommended", None)
    return gate
