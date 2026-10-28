"""Turn a page plus the candidate's facts into a per-field fill plan.

The plan is the bridge between meaning and typing.  It answers one question
for every visible field: *do we know this, and may we type it?*

States:

* ``fill`` - a fact exists and is safe to type,
* ``leave_blank`` - the human said there is no value (for example, no middle
  name), so the field stays empty and is not treated as missing,
* ``confirm`` - only a derived value exists and a human must confirm it first,
* ``ask_human`` - no fact exists, or a select has no matching option,
* ``human_only`` - OTP, CAPTCHA, live photo, payment,
* ``upload`` - a document upload, handled by the upload pipeline,
* ``fallback`` - the question is not in the concept dictionary; the operator's
  existing fast path decides.

Nothing here touches a browser.  It is pure and testable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from . import concepts
from .facts import FactBook
from .page_brief import build_deterministic_brief
from .perception import Perception, PerceivedField


@dataclass
class FillInstruction:
    handle: str
    asked: str
    concept: Optional[str]
    state: str
    value: Optional[str] = None
    expected_format: Optional[str] = None
    answer_type: str = "text"
    reason: str = ""


_DATE_RE = re.compile(r"^\s*(\d{1,4})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{1,4})\s*$")


def parse_date(value: str) -> Optional[tuple[int, int, int]]:
    """Parse the common portal date shapes into ``(year, month, day)``."""
    match = _DATE_RE.match(str(value or ""))
    if not match:
        return None
    first, second, third = (int(part) for part in match.groups())
    if first > 31:
        year, month, day = first, second, third
    elif third > 31:
        year, month, day = third, second, first
    else:
        return None
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    return year, month, day


def format_date_value(value: str, expected_format: Optional[str]) -> str:
    """Render a date in the format the page asks for.

    ``expected_format`` comes from the page (label or helper text), never from
    a guess.  Unknown shapes are returned unchanged.
    """
    text = str(value or "").strip()
    if not expected_format:
        return text
    parsed = parse_date(text)
    if parsed is None:
        return text
    year, month, day = parsed
    result = expected_format.upper()
    result = re.sub(r"YYYY", f"{year:04d}", result)
    result = re.sub(r"YY", f"{year % 100:02d}", result)
    result = re.sub(r"MM", f"{month:02d}", result)
    result = re.sub(r"DD", f"{day:02d}", result)
    return result


def format_value(
    value: str,
    *,
    expected_format: Optional[str] = None,
    answer_type: str = "text",
) -> str:
    text = str(value or "").strip()
    if expected_format and answer_type in {"date", "text", "tel", "number"}:
        return format_date_value(text, expected_format)
    return text


def _match_option(value: str, options: List[Dict[str, Any]]) -> Optional[str]:
    target = concepts.normalize(value)
    if not target:
        return None
    for option in options:
        text = concepts.normalize(str(option.get("text") or ""))
        option_value = concepts.normalize(str(option.get("value") or ""))
        if target in {text, option_value}:
            return str(option.get("value") or option.get("text") or "")
    return None


def build_fill_plan(
    perception: Perception,
    fact_book: FactBook,
    *,
    vault: Any = None,
    domain: Optional[str] = None,
) -> Dict[str, FillInstruction]:
    """Build one instruction per perceived field, keyed by its handle."""
    brief = build_deterministic_brief(perception)
    fact_book.annotate_brief(brief, domain=domain, vault=vault)
    plan: Dict[str, FillInstruction] = {}
    for question in brief.questions:
        field = perception.field_by_handle(question.handle)
        if field is None:
            continue
        plan[question.handle] = _instruction(question, field, fact_book, domain=domain, vault=vault)
    return plan


def _instruction(
    question: Any,
    field: PerceivedField,
    fact_book: FactBook,
    *,
    domain: Optional[str],
    vault: Any,
) -> FillInstruction:
    base = FillInstruction(
        handle=field.handle,
        asked=question.asked,
        concept=question.concept,
        state="fallback",
        expected_format=question.expected_format,
        answer_type=question.answer_type,
    )
    if question.human_only:
        return _with(base, "human_only", reason="This step belongs to the human.")
    if field.input_type == "file" or question.answer_type == "file":
        return _with(base, "upload", reason="This is a document upload.")
    if not question.concept:
        return _with(base, "fallback", reason="This question is not in the concept dictionary yet.")

    resolution = fact_book.resolve(question.concept, domain=domain, vault=vault)
    if resolution.state == "known_absent":
        return _with(
            base,
            "leave_blank",
            value="",
            reason=f"You told me there is no {concepts.concept_label(question.concept).lower()}.",
        )
    if resolution.state == "missing":
        return _with(base, "ask_human", reason="No fact answers this question yet.")
    if resolution.state == "needs_confirmation":
        proposed = format_value(
            resolution.value or "",
            expected_format=question.expected_format,
            answer_type=question.answer_type,
        )
        return _with(
            base,
            "confirm",
            value=proposed,
            reason="This value is derived, so a human confirms it once.",
        )

    value = format_value(
        resolution.value or "",
        expected_format=question.expected_format,
        answer_type=question.answer_type,
    )
    if question.answer_type == "select" and field.options:
        matched = _match_option(value, field.options)
        if matched is None:
            return _with(
                base,
                "ask_human",
                reason=f"The page does not offer an option matching {value!r}.",
            )
        value = matched
    if not value:
        return _with(base, "ask_human", reason="The fact is empty.")
    return _with(base, "fill", value=value, reason="")


def _with(instruction: FillInstruction, state: str, *, value: Optional[str] = None, reason: str = "") -> FillInstruction:
    instruction.state = state
    instruction.value = value
    instruction.reason = reason
    return instruction
