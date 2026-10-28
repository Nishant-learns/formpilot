"""Perception: the page as a human sees it, with stable operator handles.

The operator captures one ``Perception`` per page observation.  It is evidence,
not meaning: headings, questions, helper text, placeholders, groups, options,
visible text and stable handles.  The interpreter turns it into a
``PageBrief``.

This module deliberately keeps three things separate:

* ``label_text`` - the human label, never a placeholder or a framework name,
* ``placeholder`` - a format hint such as ``DD-MM-YYYY``,
* ``handle`` - the operator's stable id for this observation.

Conflating them is what made the old scanner announce date fields as
``DD-MM-YYYY``.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from .blueprint import BlueprintElement, PageBlueprint
from .dom_scanner import DOMScanner


class PerceivedField(BaseModel):
    handle: str = ""
    frame: str = "main"
    tag: str = "input"
    input_type: str = "text"
    role: str = ""
    label_text: str = ""
    accessible_name: str = ""
    placeholder: str = ""
    helper_text: str = ""
    group_heading: str = ""
    required: bool = False
    disabled: bool = False
    readonly: bool = False
    options: List[Dict[str, Any]] = Field(default_factory=list)
    value: str = ""
    rect: Dict[str, float] = Field(default_factory=dict)


class PerceivedAction(BaseModel):
    handle: str = ""
    frame: str = "main"
    tag: str = ""
    role: str = ""
    name: str = ""
    text: str = ""
    href: Optional[str] = None
    enabled: bool = True
    kind_hint: str = "other"


class Perception(BaseModel):
    perception_id: str = ""
    captured_at: str = ""
    url: str = ""
    title: str = ""
    page_signature: str = ""
    visible_text: str = ""
    headings: List[Dict[str, Any]] = Field(default_factory=list)
    fields: List[PerceivedField] = Field(default_factory=list)
    actions: List[PerceivedAction] = Field(default_factory=list)
    signals: Dict[str, Any] = Field(default_factory=dict)
    frames: List[Dict[str, Any]] = Field(default_factory=list)
    screenshot_ref: Optional[str] = None

    def field_by_handle(self, handle: str) -> Optional[PerceivedField]:
        return next((field for field in self.fields if field.handle == handle), None)

    def summary(self) -> Dict[str, Any]:
        return {
            "perception_id": self.perception_id,
            "page_signature": self.page_signature,
            "url": self.url,
            "title": self.title,
            "field_count": len(self.fields),
            "action_count": len(self.actions),
            "captured_at": self.captured_at,
            "screenshot_ref": self.screenshot_ref,
        }

    @classmethod
    async def capture(cls, page) -> "Perception":
        if page is None:
            raise ValueError("A live page is required to perceive it.")
        dom, blueprint = await DOMScanner.scan(page)
        return cls.from_scan(dom, blueprint)

    @classmethod
    def from_scan(
        cls,
        dom: Dict[str, Any],
        blueprint: Optional[PageBlueprint] = None,
    ) -> "Perception":
        dom = dom or {}
        elements = list(blueprint.elements.values()) if blueprint else []
        values = _legacy_values(dom)
        headings = _headings(elements)
        fields = _fields(elements, values, dom)
        actions = _actions(elements)
        signals = _signals(dom, fields)
        signature = page_signature(
            url=str(dom.get("url") or ""),
            title=str(dom.get("title") or ""),
            headings=headings,
            fields=fields,
            actions=actions,
            form_action=str(dom.get("formAction") or ""),
        )
        captured_at = str(dom.get("captured_at") or "")
        if not captured_at:
            captured_at = datetime.now(timezone.utc).isoformat()
        perception_id = "per-" + hashlib.sha256(
            f"{signature}:{captured_at}".encode("utf-8")
        ).hexdigest()[:16]
        return cls(
            perception_id=perception_id,
            captured_at=captured_at,
            url=str(dom.get("url") or ""),
            title=str(dom.get("title") or ""),
            page_signature=signature,
            visible_text=str(dom.get("visibleText") or "")[:8000],
            headings=headings,
            fields=fields,
            actions=actions,
            signals=signals,
            frames=list(dom.get("frames") or []),
        )


def page_signature(
    *,
    url: str,
    title: str,
    headings: Iterable[Dict[str, Any]],
    fields: Iterable[PerceivedField],
    actions: Iterable[PerceivedAction],
    form_action: str = "",
) -> str:
    """Stable identity of a page shape, ignoring values and volatile tokens.

    The signature covers the URL path, title, headings, field inventory and
    action labels.  It intentionally excludes typed values, timestamps,
    session tokens and query strings so a filled field does not invalidate the
    cached brief.
    """
    path = urlparse(url or "").path or "/"
    payload = {
        "path": path,
        "title": re.sub(r"\s+", " ", title or "").strip().lower(),
        "headings": [
            {
                "level": item.get("level"),
                "text": re.sub(r"\s+", " ", str(item.get("text") or "")).strip().lower(),
            }
            for item in headings
        ],
        "fields": [
            {
                "tag": field.tag,
                "type": field.input_type,
                "label": re.sub(r"\s+", " ", field.label_text).strip().lower(),
                "placeholder": field.placeholder.strip().lower(),
                "group": field.group_heading.strip().lower(),
                "required": field.required,
                "options": len(field.options),
            }
            for field in fields
        ],
        "actions": [
            {
                "text": re.sub(r"\s+", " ", action.text or action.name).strip().lower(),
                "href": (action.href or "").split("?")[0],
                "role": action.role,
            }
            for action in actions
        ],
        "form_action": (form_action or "").split("?")[0],
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _legacy_values(dom: Dict[str, Any]) -> Dict[str, str]:
    values: Dict[str, str] = {}
    for item in dom.get("inputs") or []:
        if not isinstance(item, dict):
            continue
        element_id = str(item.get("elementId") or "")
        if element_id:
            values[element_id] = str(item.get("value") or "")
    return values


def _headings(elements: List[BlueprintElement]) -> List[Dict[str, Any]]:
    headings: List[Dict[str, Any]] = []
    seen: set[tuple[int, str]] = set()
    for element in elements:
        if not element.visible:
            continue
        tag = element.tag.lower()
        text = (element.text or element.name or "").strip()
        if not text:
            continue
        level = 0
        if re.fullmatch(r"h[1-6]", tag):
            level = int(tag[1])
        elif element.role == "heading":
            level = 0
        elif tag == "legend":
            level = 0
        else:
            continue
        key = (level, re.sub(r"\s+", " ", text).lower())
        if key in seen:
            continue
        seen.add(key)
        headings.append({"level": level, "text": text[:300], "handle": element.id})
    return headings[:40]


def _field_like(element: BlueprintElement) -> bool:
    tag = element.tag.lower()
    if tag in {"input", "select", "textarea"}:
        return True
    return element.role == "textbox" and str(element.attributes.get("contenteditable") or "").lower() in {
        "true",
        "",
    } and tag not in {"body", "html"}


def _fields(
    elements: List[BlueprintElement],
    values: Dict[str, str],
    dom: Dict[str, Any],
) -> List[PerceivedField]:
    by_id = {element.id: element for element in elements}
    default_heading = str(dom.get("stepHeading") or "").strip()
    fields: List[PerceivedField] = []
    for element in elements:
        if not element.visible or not _field_like(element):
            continue
        tag = element.tag.lower()
        input_type = str(
            element.attributes.get("type")
            or ("select" if tag == "select" else "textarea" if tag == "textarea" else "text")
        ).lower()
        if tag == "input" and input_type in {"hidden", "submit", "button", "reset", "image"}:
            continue
        label_text = (element.label_text or "").strip()
        required = (
            element.attributes.get("required") is not None
            or str(element.attributes.get("aria-required") or "").lower() == "true"
            or "*" in label_text
        )
        group_heading = _group_heading(element, by_id) or default_heading
        fields.append(
            PerceivedField(
                handle=element.id,
                frame=element.frame,
                tag=tag,
                input_type=input_type,
                role=element.role,
                label_text=label_text[:300],
                accessible_name=(element.name or "").strip()[:300],
                placeholder=str(element.attributes.get("placeholder") or "").strip()[:120],
                helper_text=(element.helper_text or "").strip()[:500],
                group_heading=group_heading[:200],
                required=required,
                disabled=not element.enabled or element.attributes.get("disabled") is not None,
                readonly=element.attributes.get("readonly") is not None,
                options=[
                    {"text": str(option.get("text") or ""), "value": str(option.get("value") or "")}
                    for option in element.options
                    if str(option.get("text") or "").strip()
                ],
                value=values.get(element.id, ""),
                rect={key: float(value or 0) for key, value in element.rect.items()},
            )
        )
    return fields


def _group_heading(
    element: BlueprintElement,
    by_id: Dict[str, BlueprintElement],
) -> str:
    parent_id = element.parent_id
    visited = 0
    while parent_id and visited < 12:
        parent = by_id.get(parent_id)
        if parent is None:
            break
        tag = parent.tag.lower()
        if tag == "fieldset":
            for child_id in parent.children:
                child = by_id.get(child_id)
                if child is not None and child.tag.lower() == "legend":
                    text = (child.text or child.name or "").strip()
                    if text:
                        return text
        if tag == "legend" or re.fullmatch(r"h[1-6]", tag) or parent.role == "heading":
            text = (parent.text or parent.name or "").strip()
            if text:
                return text
        parent_id = parent.parent_id
        visited += 1
    return ""


def _actions(elements: List[BlueprintElement]) -> List[PerceivedAction]:
    actions: List[PerceivedAction] = []
    seen: set[tuple[str, str]] = set()
    for element in elements:
        if not element.visible or not element.enabled:
            continue
        role = (element.role or "").lower()
        tag = element.tag.lower()
        if role not in {"button", "link", "menuitem", "tab"} and tag not in {"button", "a", "summary"}:
            continue
        text = (element.text or element.name or "").strip()
        if not text:
            continue
        href = element.attributes.get("href")
        href = str(href) if href else None
        key = (re.sub(r"\s+", " ", text).lower(), href or "")
        if key in seen:
            continue
        seen.add(key)
        actions.append(
            PerceivedAction(
                handle=element.id,
                frame=element.frame,
                tag=tag,
                role=role,
                name=(element.name or "").strip()[:300],
                text=text[:300],
                href=href[:500] if href else None,
                enabled=element.enabled,
                kind_hint=_action_kind(text, href, role),
            )
        )
    return actions[:80]


_LOGIN_RE = re.compile(r"log\s*in|login|sign\s*in|signin|already\s*registered|returning", re.I)
_REGISTER_RE = re.compile(r"new\s*registration|account\s*creation|create\s*(an?\s*)?account|register(?:\s*here)?|sign\s*up|signup|new\s*user|new\s*applicant|\botr\b|apply\s*online", re.I)
_RESUME_RE = re.compile(r"resume|continue\s+(my\s+)?application|saved\s+application|track", re.I)
_PAYMENT_RE = re.compile(r"\bpay\b|payment|checkout|fee", re.I)
_NEXT_RE = re.compile(r"save\s*&\s*next|save\s*and\s*next|next|continue|proceed|submit|verify|confirm|finish|complete", re.I)


def _action_kind(text: str, href: Optional[str], role: str) -> str:
    value = f"{text} {href or ''}"
    if _PAYMENT_RE.search(text):
        return "payment"
    if _RESUME_RE.search(value):
        return "resume"
    if _REGISTER_RE.search(value):
        return "register"
    if _LOGIN_RE.search(value):
        return "login"
    if _NEXT_RE.search(text) and role in {"button", "menuitem"}:
        return "next"
    if role == "link" or href:
        return "navigation"
    return "other"


def _signals(dom: Dict[str, Any], fields: List[PerceivedField]) -> Dict[str, Any]:
    captcha = list(dom.get("captchaElements") or [])
    otp = list(dom.get("otpInputs") or [])
    file_inputs = list(dom.get("fileInputs") or [])
    alerts = [str(item) for item in (dom.get("alerts") or []) if str(item).strip()]
    errors = [str(item) for item in (dom.get("errors") or []) if str(item).strip()]
    return {
        "has_form": bool(dom.get("formCount")),
        "form_count": int(dom.get("formCount") or 0),
        "captcha": bool(captcha),
        "captcha_kinds": sorted({str(item.get("kind") or "unknown") for item in captcha if isinstance(item, dict)}),
        "otp": bool(otp),
        "otp_fields": [
            {
                "handle": item.get("elementId"),
                "label": item.get("label"),
            }
            for item in otp
            if isinstance(item, dict)
        ],
        "payment": bool(dom.get("hasPaymentButton")) or int(dom.get("paymentSignals") or 0) >= 2,
        "live_photo": bool(dom.get("livePhotoRequired")),
        "file_uploads": len(file_inputs),
        "password_fields": sum(1 for field in fields if field.input_type == "password"),
        "alerts": alerts[:20],
        "errors": errors[:20],
        "dialogs": [
            {
                "name": item.get("name"),
                "text": item.get("text"),
            }
            for item in (dom.get("dialogs") or [])
            if isinstance(item, dict)
        ][:5],
        "frameworks": list(dom.get("frameworks") or []),
    }
