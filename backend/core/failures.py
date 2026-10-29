"""A small, stable failure taxonomy.

Skyvern classifies failures after the fact (``failure_classifier.py``) so a
retry policy and a support engineer can talk about the same thing.  FormPilot
needs the same vocabulary, but much smaller: our failures happen on one form
flow with a human watching.

A code is recorded on a run step.  It is descriptive, not causal: it says what
went wrong, not why the portal did it.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Optional


class FailureCode(str, Enum):
    NAVIGATION = "navigation_failure"
    AUTH = "auth_failure"
    ANTI_BOT = "anti_bot"
    ELEMENT_NOT_FOUND = "element_not_found"
    FIELD_NOT_HELD = "field_not_held"
    WRONG_PAGE = "wrong_page"
    TIMEOUT = "timeout"
    BUDGET = "budget_exceeded"
    PORTAL_ERROR = "portal_error"
    INTERNAL = "internal_error"


# Ordered rules: the first match wins, so specific codes come before generic
# ones.  Keep the vocabulary closed; an unknown failure is INTERNAL.
_RULES = (
    (FailureCode.ANTI_BOT, r"captcha|security\s*check|anti[-\s]?bot|blocked|robot"),
    (FailureCode.AUTH, r"login|sign[-\s]?in|password|credential|unauthori[sz]ed|otp"),
    (FailureCode.FIELD_NOT_HELD, r"did not keep|not held|empty after|dropped the value"),
    (FailureCode.ELEMENT_NOT_FOUND, r"not found|could not be reached|disappeared|no such element"),
    (FailureCode.NAVIGATION, r"did not move|navigation|did not advance|wrong step"),
    (FailureCode.WRONG_PAGE, r"unexpected page|wrong page|not the .* page"),
    (FailureCode.TIMEOUT, r"timed? ?out|timeout|too long"),
    (FailureCode.BUDGET, r"stalled|no progress|budget|too many (?:steps|attempts)"),
    (FailureCode.PORTAL_ERROR, r"portal (?:reported|error|rejected)|server error|validation"),
)

_RETRYABLE = {
    FailureCode.NAVIGATION,
    FailureCode.ELEMENT_NOT_FOUND,
    FailureCode.TIMEOUT,
    FailureCode.PORTAL_ERROR,
}


def classify_failure(message: Optional[str], *, default: FailureCode = FailureCode.INTERNAL) -> FailureCode:
    """Map a human-readable failure message to a stable code."""
    text = str(message or "").strip().lower()
    if not text:
        return default
    for code, pattern in _RULES:
        if re.search(pattern, text):
            return code
    return default


def is_retryable(code: FailureCode | str) -> bool:
    """Whether another attempt could plausibly succeed without a human."""
    try:
        return FailureCode(code) in _RETRYABLE
    except ValueError:
        return False
