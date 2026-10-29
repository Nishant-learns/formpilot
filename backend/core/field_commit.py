"""Field commit verdicts.

A fill is not successful because the action returned without an error.  It is
successful when a fresh read shows the value the portal actually kept.  This
module draws the same line Skyvern's ``taskv3/field_commit.py`` draws:

* ``OK`` — the portal holds the value (exactly or in an equivalent format),
* ``DID_NOT_COMMIT`` — the portal dropped, truncated or replaced the value,
* ``UNVERIFIED`` — the field could not be read, so no claim is made.

The distinction matters because portals silently reformat dates, strip the
leading ``+91`` from a mobile number, uppercase a name, or keep only the first
few characters of a long value.  Treating all of those as failure produces
noise; treating all of them as success produces false claims.  A reformat is
equivalent; a truncation is not.
"""

from __future__ import annotations

import re
import unicodedata
from enum import Enum
from typing import Any, Dict, Optional, Tuple

TEXT_KINDS = {"text", "multiline", "password", "email", "digits", "date", "select"}


class CommitStatus(str, Enum):
    OK = "ok"
    DID_NOT_COMMIT = "did_not_commit"
    UNVERIFIED = "unverified"


class EntryMatch(str, Enum):
    SAME = "same"
    REFORMATTED = "reformatted"
    NOT_HELD = "not_held"
    DIFFERENT = "different"


def kind_for(item: Optional[Dict[str, Any]]) -> str:
    """Map a scanned field to the comparison rules it needs.

    The input type is authoritative when it is specific.  Plain text inputs
    still need help: a "Date of Birth" text box that receives ``2003-08-15``
    and shows ``15/08/2003`` is a date, and a "Mobile Number" text box that
    adds ``+91`` is a number.  The label and semantic key decide those.
    """
    item = item or {}
    field_type = str(item.get("type") or "text").lower()
    tag = str(item.get("tagName") or "").lower()
    if field_type == "password":
        return "password"
    if tag == "select":
        return "select"
    if field_type == "date":
        return "date"
    if field_type in {"tel", "number"}:
        return "digits"
    if field_type == "email":
        return "email"
    if tag == "textarea":
        return "multiline"

    haystack = " ".join(
        str(item.get(key) or "")
        for key in ("semantic_key", "label", "name", "id", "placeholder", "aria_label")
    ).lower()
    if re.search(r"\b(?:dob|d\.o\.b|date\s*of\s*birth|birth\s*date)\b", haystack):
        return "date"
    if re.search(r"\b(?:mobile|phone|whatsapp|contact\s*number)\b", haystack):
        return "digits"
    if "email" in haystack:
        return "email"
    return "text"


def _collapse(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    return " ".join(text.split())


def _casefold(value: Any) -> str:
    return _collapse(value).casefold()


def _digits(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _date_parts(value: Any) -> Optional[Tuple[int, int, int]]:
    """Parse a date into ``(year, month, day)`` without guessing the order.

    Only unambiguous shapes are accepted: an 8-digit date whose first four
    digits look like a year is ``YYYYMMDD``; otherwise it is ``DDMMYYYY``.
    Anything else returns ``None`` so the comparison stays conservative.
    """
    digits = _digits(value)
    if len(digits) != 8:
        return None
    head = int(digits[:4])
    if 1900 <= head <= 2100:
        year, month, day = int(digits[:4]), int(digits[4:6]), int(digits[6:8])
    else:
        day, month, year = int(digits[:2]), int(digits[2:4]), int(digits[4:8])
    if not (1900 <= year <= 2100 and 1 <= month <= 12 and 1 <= day <= 31):
        return None
    return year, month, day


def compare_entry(expected: Any, actual: Any, kind: str = "text") -> EntryMatch:
    """Classify how the portal's value relates to the value we entered."""
    expected_text = str(expected or "")
    actual_text = str(actual or "")
    kind = kind if kind in TEXT_KINDS else "text"

    if kind == "password":
        if not actual_text:
            return EntryMatch.NOT_HELD
        return EntryMatch.SAME if expected_text == actual_text else EntryMatch.DIFFERENT

    if not actual_text.strip():
        return EntryMatch.NOT_HELD

    if kind == "digits":
        wanted = _digits(expected_text)
        held = _digits(actual_text)
        if not held:
            return EntryMatch.NOT_HELD
        if wanted == held:
            return EntryMatch.REFORMATTED if expected_text.strip() != actual_text.strip() else EntryMatch.SAME
        # A country code or short suffix added by the portal is a reformat,
        # not a different number.
        if 0 < len(held) - len(wanted) <= 4 and (
            held.endswith(wanted) or held.startswith(wanted)
        ):
            return EntryMatch.REFORMATTED
        if len(held) >= 4 and wanted.endswith(held):
            return EntryMatch.NOT_HELD
        if len(held) >= 4 and wanted.startswith(held):
            return EntryMatch.NOT_HELD
        return EntryMatch.DIFFERENT

    if kind == "date":
        wanted_parts = _date_parts(expected_text)
        held_parts = _date_parts(actual_text)
        if wanted_parts and held_parts:
            if wanted_parts != held_parts:
                return EntryMatch.DIFFERENT
            if expected_text.strip() == actual_text.strip():
                return EntryMatch.SAME
            return EntryMatch.REFORMATTED
        if _collapse(expected_text) == _collapse(actual_text):
            return EntryMatch.SAME
        return EntryMatch.DIFFERENT

    if kind == "select":
        return (
            EntryMatch.SAME
            if _casefold(expected_text) == _casefold(actual_text)
            else EntryMatch.DIFFERENT
        )

    if kind == "email":
        return (
            EntryMatch.SAME
            if _casefold(expected_text) == _casefold(actual_text)
            else EntryMatch.DIFFERENT
        )

    wanted = _casefold(expected_text)
    held = _casefold(actual_text)
    if wanted == held:
        return EntryMatch.SAME
    if len(held) >= 3 and len(held) < len(wanted) and wanted.startswith(held):
        return EntryMatch.NOT_HELD
    if len(held) >= 3 and len(wanted) < len(held) and held.startswith(wanted):
        # The portal appended something (a suffix, a unit, a country code in
        # a free-text field).  The entered value is still held.
        return EntryMatch.REFORMATTED
    return EntryMatch.DIFFERENT


_REASONS = {
    EntryMatch.SAME: "The portal kept the value exactly.",
    EntryMatch.REFORMATTED: "The portal reformatted the value; it is equivalent.",
    EntryMatch.NOT_HELD: "The portal did not keep the whole value.",
    EntryMatch.DIFFERENT: "The portal kept a different value.",
}


def classify_commit(
    expected: Any,
    actual: Any,
    *,
    kind: str = "text",
    readable: bool = True,
) -> Dict[str, Any]:
    """Return a commit verdict for one field.

    ``readable`` is False when the field disappeared or could not be read; the
    verdict is then ``UNVERIFIED`` and the caller must not claim success.
    """
    if not readable:
        return {
            "status": CommitStatus.UNVERIFIED.value,
            "match": None,
            "kind": kind,
            "reason": "The field could not be read back, so the value is unverified.",
        }
    match = compare_entry(expected, actual, kind)
    status = (
        CommitStatus.OK
        if match in {EntryMatch.SAME, EntryMatch.REFORMATTED}
        else CommitStatus.DID_NOT_COMMIT
    )
    reason = _REASONS[match]
    if match is EntryMatch.NOT_HELD and not str(actual or "").strip():
        reason = "The field is empty after the fill."
    return {
        "status": status.value,
        "match": match.value,
        "kind": kind,
        "reason": reason,
    }


def committed(verdict: Optional[Dict[str, Any]]) -> bool:
    return bool(verdict) and verdict.get("status") == CommitStatus.OK.value


def retryable(verdict: Optional[Dict[str, Any]]) -> bool:
    """A dropped or replaced value is worth exactly one more attempt.

    Selects, checkboxes and uploads are excluded by the caller: re-applying a
    selection can toggle a widget the portal already accepted.
    """
    return bool(verdict) and verdict.get("match") in {
        EntryMatch.NOT_HELD.value,
        EntryMatch.DIFFERENT.value,
    }
