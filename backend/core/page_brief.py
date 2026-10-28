"""The interpreter: turn a page perception into a human-readable brief.

The brief is the shared source of truth for the chat, the page panel and the
operator.  It answers one question in plain language: *what is this page, what
does it ask for, and which paths does it offer?*

Two implementations live here:

* ``build_deterministic_brief`` - a fast, offline-safe interpretation based on
  the concept dictionary.  It is the fallback and the test oracle.
* ``PageInterpreter`` - one model call per page signature, validated against
  the perception, with the deterministic brief as the safety net.

The model may explain and group.  It may not invent fields, values or handles.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from . import concepts
from .llm_client import LLMClient, LLMError
from .perception import Perception, PerceivedAction, PerceivedField

PAGE_TYPES = {
    "FORM",
    "SECTION_FORM",
    "DASHBOARD",
    "LANDING",
    "LISTING",
    "LOGIN",
    "REGISTER",
    "OTP",
    "CAPTCHA",
    "PAYMENT",
    "ERROR",
    "UNKNOWN",
}

PATH_KINDS = {"application_action", "informational", "navigation", "account_action", "unknown"}


class BriefQuestion(BaseModel):
    question_id: str = ""
    asked: str = ""
    concept: Optional[str] = None
    concept_label: str = ""
    concept_confidence: float = 0.0
    answer_type: str = "text"
    expected_format: Optional[str] = None
    required: bool = False
    handle: str = ""
    group_heading: str = ""
    evidence: List[str] = Field(default_factory=list)
    constraints: Dict[str, Any] = Field(default_factory=dict)
    human_only: bool = False
    reason: str = ""
    # Fact availability is filled in by the fact book after interpretation.
    # The brief never carries the value itself; it only says whether a fact
    # exists, where it came from and whether a human confirmed it.
    fact_status: str = "missing"
    fact_provenance: str = ""
    fact_verification: str = ""


class BriefSection(BaseModel):
    section_id: str = ""
    heading: str = ""
    confidence: float = 0.0
    questions: List[BriefQuestion] = Field(default_factory=list)


class BriefPath(BaseModel):
    path_id: str = ""
    label: str = ""
    handle: str = ""
    kind: str = "unknown"
    needs_human_choice: bool = False
    evidence: List[str] = Field(default_factory=list)


class BriefInformation(BaseModel):
    label: str = ""
    value: str = ""
    kind: str = "text"


class BriefAmbiguity(BaseModel):
    ambiguity_id: str = ""
    description: str = ""
    question_ids: List[str] = Field(default_factory=list)
    resolution: str = "unresolved"
    confidence: float = 0.0


class PageBrief(BaseModel):
    brief_id: str = ""
    page_signature: str = ""
    url: str = ""
    title: str = ""
    page_type: str = "UNKNOWN"
    purpose: str = ""
    confidence: float = 0.0
    sections: List[BriefSection] = Field(default_factory=list)
    information: List[BriefInformation] = Field(default_factory=list)
    paths: List[BriefPath] = Field(default_factory=list)
    human_only: List[str] = Field(default_factory=list)
    ambiguities: List[BriefAmbiguity] = Field(default_factory=list)
    source: str = "deterministic"
    model: Optional[str] = None
    cache: Dict[str, Any] = Field(default_factory=dict)
    perception: Dict[str, Any] = Field(default_factory=dict)

    @property
    def questions(self) -> List[BriefQuestion]:
        return [question for section in self.sections for question in section.questions]

    def question_count(self) -> int:
        return len(self.questions)

    def needs_human(self) -> List[str]:
        needs: List[str] = []
        for question in self.questions:
            if question.human_only:
                needs.append(question.asked or "human-only step")
            elif not question.concept:
                needs.append(question.asked or "unknown question")
        for path in self.paths:
            if path.needs_human_choice:
                needs.append(f"choose: {path.label}")
        return needs

    def summary_line(self) -> str:
        label = self.title or self.url or "This page"
        if self.page_type in {"FORM", "SECTION_FORM"}:
            count = self.question_count()
            return f"{label} · {self.page_type.lower()} · {count} question{'s' if count != 1 else ''}"
        if self.page_type in {"DASHBOARD", "LANDING", "LISTING"}:
            return f"{label} · {self.page_type.lower()} · {len(self.paths)} path{'s' if len(self.paths) != 1 else ''}"
        return f"{label} · {self.page_type.lower()}"


class PageBriefCache:
    """Small in-memory cache keyed by page signature."""

    def __init__(self, max_entries: int = 32) -> None:
        self.max_entries = max_entries
        self._items: Dict[str, PageBrief] = {}
        self._order: List[str] = []

    def get(self, signature: str) -> Optional[PageBrief]:
        item = self._items.get(signature)
        if item is None:
            return None
        if signature in self._order:
            self._order.remove(signature)
        self._order.append(signature)
        return item.model_copy(deep=True)

    def put(self, signature: str, brief: PageBrief) -> None:
        self._items[signature] = brief.model_copy(deep=True)
        if signature in self._order:
            self._order.remove(signature)
        self._order.append(signature)
        while len(self._order) > self.max_entries:
            oldest = self._order.pop(0)
            self._items.pop(oldest, None)

    def invalidate(self, signature: Optional[str] = None) -> None:
        if signature is None:
            self._items.clear()
            self._order.clear()
            return
        self._items.pop(signature, None)
        if signature in self._order:
            self._order.remove(signature)

    def __len__(self) -> int:
        return len(self._items)


# --------------------------------------------------------------------------- deterministic


def build_deterministic_brief(perception: Perception) -> PageBrief:
    page_type = classify_page(perception)
    sections = _build_sections(perception)
    questions = [question for section in sections for question in section.questions]
    paths = _build_paths(perception, page_type)
    information = _build_information(perception)
    human_only = _human_only(perception)
    ambiguities = _ambiguities(perception, sections)
    confidence = _overall_confidence(page_type, questions, perception)
    title = perception.title.strip() or _title_from_url(perception.url)
    purpose = _purpose(page_type, title, questions, paths)
    signature = perception.page_signature
    return PageBrief(
        brief_id="brief-" + hashlib.sha256(f"{signature}:deterministic".encode("utf-8")).hexdigest()[:16],
        page_signature=signature,
        url=perception.url,
        title=title,
        page_type=page_type,
        purpose=purpose,
        confidence=confidence,
        sections=sections,
        information=information,
        paths=paths,
        human_only=human_only,
        ambiguities=ambiguities,
        source="deterministic",
        cache={"created_at": _now(), "invalidated_by": None},
        perception=perception.summary(),
    )


def classify_page(perception: Perception) -> str:
    signals = perception.signals or {}
    fields = perception.fields
    actions = perception.actions
    text = " ".join(
        [
            perception.title or "",
            perception.visible_text or "",
            " ".join(str(item.get("text") or "") for item in perception.headings),
        ]
    ).lower()

    action_kinds = {action.kind_hint for action in actions}
    has_login = "login" in action_kinds
    has_register = "register" in action_kinds
    has_resume = "resume" in action_kinds

    if _error_page(text, signals, fields):
        return "ERROR"
    if signals.get("otp") and (len(fields) <= 3 or "otp" in text):
        return "OTP"
    if signals.get("captcha") and len(fields) <= 1:
        return "CAPTCHA"
    if signals.get("payment") and not fields:
        return "PAYMENT"

    if fields:
        if has_login and has_register and len(fields) <= 1:
            return "LANDING"
        if any(field.input_type == "password" for field in fields) and has_login:
            return "LOGIN"
        if has_register and not has_login and len(fields) >= 3:
            return "REGISTER"
        if len(fields) >= 2:
            if _is_section_form(text, actions):
                return "SECTION_FORM"
            return "FORM"
        if len(fields) == 1 and signals.get("has_form"):
            return "FORM"

    if has_login or has_register or has_resume:
        if has_login and has_register:
            return "LANDING"
        if has_register:
            return "REGISTER"
        if has_login:
            return "LOGIN"
        if has_resume:
            return "LANDING"

    if _looks_signed_in(text, actions) and not fields:
        return "DASHBOARD"
    if not fields and len([action for action in actions if action.role == "link"]) >= 8:
        return "LISTING"
    if not fields and actions:
        return "LANDING"
    return "UNKNOWN"


def _error_page(text: str, signals: Dict[str, Any], fields: List[PerceivedField]) -> bool:
    if fields:
        return False
    error_words = r"\b404\b|not\s*found|something\s*went\s*wrong|server\s*error|access\s*denied|session\s*(expired|timed\s*out)|page\s*not\s*available"
    return bool(re.search(error_words, text)) or bool(signals.get("errors"))


def _is_section_form(text: str, actions: List[PerceivedAction]) -> bool:
    if re.search(r"save\s*&\s*next|save\s*and\s*next|next\s*step", text):
        return True
    return any(re.search(r"save\s*&\s*next|save\s*and\s*next", action.text, re.I) for action in actions)


def _looks_signed_in(text: str, actions: List[PerceivedAction]) -> bool:
    labels = " ".join(action.text for action in actions).lower()
    if re.search(r"log\s*out|logout|sign\s*out|dashboard|my\s*application|application\s*status", f"{text} {labels}"):
        return True
    if re.search(r"registration\s*(id|no|number)|application\s*(id|no|number)|\botr\b", text):
        return True
    return False


def _build_sections(perception: Perception) -> List[BriefSection]:
    grouped: Dict[str, List[BriefQuestion]] = {}
    order: List[str] = []
    for index, field in enumerate(perception.fields, start=1):
        question = _question_for(field, index)
        heading = (field.group_heading or "").strip() or perception.title.strip() or "Page"
        if heading not in grouped:
            grouped[heading] = []
            order.append(heading)
        grouped[heading].append(question)

    sections: List[BriefSection] = []
    for heading in order:
        questions = grouped[heading]
        confidence = _average([question.concept_confidence for question in questions if question.concept])
        sections.append(
            BriefSection(
                section_id="sec-" + _slug(heading)[:40] + "-" + str(len(sections) + 1),
                heading=heading,
                confidence=round(confidence, 2),
                questions=questions,
            )
        )
    return sections


def _question_for(field: PerceivedField, index: int) -> BriefQuestion:
    match = concepts.match_question(
        field.label_text,
        placeholder=field.placeholder,
        helper_text=field.helper_text,
        group_heading=field.group_heading,
        input_type=field.input_type,
        tag=field.tag,
    )
    asked = _asked_text(field)
    constraints: Dict[str, Any] = {}
    if match.verify:
        constraints["confirmation"] = True
    if field.options:
        constraints["options"] = [option.get("text") for option in field.options][:50]
    return BriefQuestion(
        question_id=f"q-{index}",
        asked=asked,
        concept=match.concept,
        concept_label=concepts.concept_label(match.concept),
        concept_confidence=round(float(match.confidence), 2),
        answer_type=match.answer_type,
        expected_format=match.expected_format,
        required=field.required,
        handle=field.handle,
        group_heading=field.group_heading,
        evidence=match.evidence,
        constraints=constraints,
        human_only=match.human_only,
        reason=match.reason,
    )


def _asked_text(field: PerceivedField) -> str:
    label = (field.label_text or "").strip()
    if label:
        return label
    name = (field.accessible_name or "").strip()
    placeholder = (field.placeholder or "").strip()
    if name and name.lower() not in {placeholder.lower(), (field.label_text or "").lower()}:
        return name
    helper = (field.helper_text or "").strip()
    if helper:
        return helper
    group = (field.group_heading or "").strip()
    if group:
        return f"Untitled question in {group}"
    return "Untitled question"


def _build_paths(perception: Perception, page_type: str) -> List[BriefPath]:
    paths: List[BriefPath] = []
    seen: set[Tuple[str, str]] = set()
    for action in perception.actions:
        kind = _path_kind(action, page_type)
        if kind is None:
            continue
        label = (action.text or action.name).strip()
        if not label:
            continue
        key = (label.lower(), action.handle)
        if key in seen:
            continue
        seen.add(key)
        paths.append(
            BriefPath(
                path_id="p-" + str(len(paths) + 1),
                label=label[:200],
                handle=action.handle,
                kind=kind,
                needs_human_choice=False,
                evidence=[f"action: {label[:120]}"] + ([f"href: {action.href}"] if action.href else []),
            )
        )
    if page_type in {"DASHBOARD", "LANDING", "LISTING", "LOGIN", "REGISTER"}:
        choice_paths = [
            path for path in paths if path.kind in {"account_action", "application_action"}
        ]
        if page_type == "DASHBOARD":
            # A preview is not a dead link; it is a genuine alternative to
            # proceeding, so the human chooses between them.
            preview_paths = [path for path in paths if path.kind == "informational"]
            if preview_paths and choice_paths:
                for path in choice_paths + preview_paths:
                    path.needs_human_choice = True
            elif len(choice_paths) > 1:
                for path in choice_paths:
                    path.needs_human_choice = True
        elif len(choice_paths) > 1:
            for path in choice_paths:
                path.needs_human_choice = True
        elif page_type == "LANDING" and len(choice_paths) == 1:
            choice_paths[0].needs_human_choice = True
    return paths[:16]


def _path_kind(action: PerceivedAction, page_type: str) -> Optional[str]:
    hint = action.kind_hint
    if hint in {"login", "register", "resume"}:
        return "account_action"
    if hint == "payment":
        return "application_action"
    if hint == "next":
        # On a dashboard "proceed" starts an application; on a form it moves
        # to the next section.  Everywhere else a next control is navigation.
        if page_type in {"FORM", "SECTION_FORM", "PAYMENT", "DASHBOARD"}:
            return "application_action"
        return "navigation"
    if page_type in {"FORM", "SECTION_FORM", "LOGIN", "REGISTER", "OTP", "CAPTCHA", "PAYMENT"}:
        return None
    text = action.text.lower()
    if re.search(r"preview|view|details|instructions|syllabus|notification", text):
        return "informational"
    if re.search(r"proceed|apply|start|continue|register|new\s*application", text):
        return "application_action"
    if action.role == "link":
        return "navigation"
    return None


def _build_information(perception: Perception) -> List[BriefInformation]:
    text = perception.visible_text or ""
    found: List[BriefInformation] = []
    seen: set[str] = set()
    patterns = [
        (
            r"(registration|regn|application|app|otr)\s*(id|no|number)?\s*[:\-]\s*([A-Z0-9][A-Z0-9\-\/]{4,})",
            "Registration / application ID",
            "identifier",
        ),
        (r"(status)\s*[:\-]\s*([A-Za-z][A-Za-z0-9 _\-]{2,60})", "Application status", "status"),
    ]
    for pattern, label, kind in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            value = (match.group(3) if match.lastindex and match.lastindex >= 3 else match.group(2)).strip()
            key = f"{label}:{value}".lower()
            if not value or key in seen:
                continue
            seen.add(key)
            found.append(BriefInformation(label=label, value=value[:200], kind=kind))
    return found[:5]


def _human_only(perception: Perception) -> List[str]:
    signals = perception.signals or {}
    items: List[str] = []
    if signals.get("captcha"):
        items.append("captcha")
    if signals.get("otp"):
        items.append("otp")
    if signals.get("live_photo"):
        items.append("live_photo")
    if signals.get("payment"):
        items.append("payment")
    items.append("final_submit")
    return items


def _ambiguities(perception: Perception, sections: List[BriefSection]) -> List[BriefAmbiguity]:
    questions = [question for section in sections for question in section.questions]
    ambiguities: List[BriefAmbiguity] = []

    by_placeholder: Dict[str, List[BriefQuestion]] = {}
    for field, question in zip(perception.fields, questions):
        placeholder = (field.placeholder or "").strip().lower()
        if placeholder and concepts.expected_date_format(placeholder):
            by_placeholder.setdefault(placeholder, []).append(question)
    for placeholder, group in by_placeholder.items():
        if len(group) < 2:
            continue
        unresolved = [question for question in group if not question.concept]
        ambiguities.append(
            BriefAmbiguity(
                ambiguity_id=f"amb-{len(ambiguities) + 1}",
                description=(
                    f"{len(group)} fields share the placeholder {placeholder!r}. "
                    "The placeholder is a format hint, so the labels and group headings decide the meaning."
                ),
                question_ids=[question.question_id for question in group],
                resolution="resolved_by_label" if not unresolved else "unresolved",
                confidence=0.9 if not unresolved else 0.4,
            )
        )

    unknown = [question for question in questions if not question.concept and not question.human_only]
    for question in unknown[:6]:
        ambiguities.append(
            BriefAmbiguity(
                ambiguity_id=f"amb-{len(ambiguities) + 1}",
                description=f"The question {question.asked!r} does not match a known concept yet.",
                question_ids=[question.question_id],
                resolution="ask_human_to_confirm_concept",
                confidence=question.concept_confidence,
            )
        )
    return ambiguities[:10]


def _overall_confidence(
    page_type: str,
    questions: List[BriefQuestion],
    perception: Perception,
) -> float:
    if page_type == "UNKNOWN":
        return 0.2
    if questions:
        matched = [question.concept_confidence for question in questions if question.concept]
        base = _average(matched) if matched else 0.35
        coverage = len(matched) / max(1, len(questions))
        return round(min(0.99, base * (0.6 + 0.4 * coverage)), 2)
    if page_type in {"DASHBOARD", "LANDING", "LISTING"} and perception.actions:
        return 0.75
    return 0.5


def _purpose(
    page_type: str,
    title: str,
    questions: List[BriefQuestion],
    paths: List[BriefPath],
) -> str:
    label = title or "this page"
    if page_type in {"FORM", "SECTION_FORM"}:
        required = sum(1 for question in questions if question.required)
        return (
            f"{label} collects {len(questions)} details for this application"
            + (f", {required} of them required." if required else ".")
        )
    if page_type == "DASHBOARD":
        return "This is a signed-in dashboard. It shows the candidate's status and the next application paths."
    if page_type == "LANDING":
        return "This is a public entry page. It offers account and application paths, so the candidate must choose one."
    if page_type == "LOGIN":
        return "This page signs an existing candidate in."
    if page_type == "REGISTER":
        return "This page creates a new candidate account."
    if page_type == "OTP":
        return "This page verifies a one-time code. The code is entered by the human."
    if page_type == "CAPTCHA":
        return "This page asks for a human security check."
    if page_type == "PAYMENT":
        return "This page collects a payment. The human approves it."
    if page_type == "ERROR":
        return "The portal returned an error page."
    if page_type == "LISTING":
        return "This page lists results or links."
    return "The page could not be classified confidently. Nothing should be filled yet."


def _average(values: List[float]) -> float:
    if not values:
        return 0.0
    return sum(float(value) for value in values) / len(values)


def _title_from_url(url: str) -> str:
    from urllib.parse import urlparse

    parsed = urlparse(url or "")
    if parsed.netloc:
        return parsed.netloc
    return url or "This page"


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-") or "section"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------- interpreter


class PageInterpreter:
    """Model-first interpretation with a deterministic safety net."""

    def __init__(
        self,
        llm_client: Optional[Any] = None,
        cache: Optional[PageBriefCache] = None,
    ) -> None:
        self._llm = llm_client
        self.cache = cache or PageBriefCache()

    async def interpret(self, perception: Perception, *, force: bool = False) -> PageBrief:
        if not force:
            cached = self.cache.get(perception.page_signature)
            if cached is not None:
                cached.source = "cache"
                cached.cache = {
                    **(cached.cache or {}),
                    "served_at": _now(),
                    "hit": True,
                }
                return cached

        deterministic = build_deterministic_brief(perception)
        llm = self._llm or self._default_llm()
        if llm is not None and getattr(llm, "configured", False):
            try:
                brief = await self._interpret_with_model(llm, perception, deterministic)
            except (LLMError, ValueError, TypeError, KeyError, json.JSONDecodeError):
                brief = deterministic
            except Exception:
                brief = deterministic
        else:
            brief = deterministic

        self.cache.put(perception.page_signature, brief)
        return brief

    def _default_llm(self) -> Optional[LLMClient]:
        try:
            return LLMClient()
        except Exception:
            return None

    async def _interpret_with_model(
        self,
        llm: Any,
        perception: Perception,
        deterministic: PageBrief,
    ) -> PageBrief:
        payload = _model_payload(perception)
        messages = [
            {"role": "system", "content": _system_prompt()},
            {
                "role": "user",
                "content": (
                    "Read this page perception and return the page brief as one JSON object. "
                    "No markdown fences, no commentary.\n\n"
                    + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
                ),
            },
        ]
        message = await llm.complete(messages)
        content = str(message.get("content") or "").strip()
        data = _parse_json_object(content)
        if not isinstance(data, dict):
            raise ValueError("The model did not return a JSON object.")
        return _merge_model_brief(
            data,
            perception,
            deterministic,
            model=str(getattr(getattr(llm, "config", None), "model", "") or ""),
        )


def _model_payload(perception: Perception) -> Dict[str, Any]:
    return {
        "url": perception.url,
        "title": perception.title,
        "headings": perception.headings,
        "visible_text": (perception.visible_text or "")[:3000],
        "fields": [
            {
                "handle": field.handle,
                "label": field.label_text,
                "accessible_name": field.accessible_name,
                "placeholder": field.placeholder,
                "helper": field.helper_text,
                "group": field.group_heading,
                "tag": field.tag,
                "type": field.input_type,
                "required": field.required,
                "options": [option.get("text") for option in field.options][:40],
            }
            for field in perception.fields
        ],
        "actions": [
            {
                "handle": action.handle,
                "text": action.text,
                "role": action.role,
                "href": action.href,
                "hint": action.kind_hint,
            }
            for action in perception.actions
        ],
        "signals": perception.signals,
        "concepts": [
            {"key": item.key, "label": item.label, "answer_type": item.answer_type}
            for item in concepts.CONCEPTS.values()
        ],
    }


def _system_prompt() -> str:
    return (
        "You are the interpreter of a form-filling cockpit. You see a page the way a "
        "human sees it: headings, questions, labels, helper text, groups and actions. "
        "You never see or use framework field names as meaning.\n\n"
        "Return exactly one JSON object with this shape:\n"
        "{\n"
        '  "page_type": "FORM|SECTION_FORM|DASHBOARD|LANDING|LISTING|LOGIN|REGISTER|OTP|CAPTCHA|PAYMENT|ERROR|UNKNOWN",\n'
        '  "title": "short human title",\n'
        '  "purpose": "one or two plain sentences",\n'
        '  "confidence": 0.0,\n'
        '  "sections": [{"heading": "...", "confidence": 0.0, "questions": [\n'
        '    {"handle": "fp-...", "asked": "the question as a human reads it",\n'
        '     "concept": "one concept key or null", "concept_confidence": 0.0,\n'
        '     "answer_type": "text|date|select|file|email|tel|password|checkbox|radio|textarea|number",\n'
        '     "expected_format": "DD-MM-YYYY or null", "required": true,\n'
        '     "evidence": ["label: ...", "group: ..."]}\n'
        "  ]}],\n"
        '  "information": [{"label": "...", "value": "...", "kind": "identifier|status|text"}],\n'
        '  "paths": [{"handle": "fp-...", "label": "...", "kind": "application_action|account_action|informational|navigation", "needs_human_choice": true}],\n'
        '  "ambiguities": [{"description": "...", "question_ids": [], "resolution": "..."}]\n'
        "}\n\n"
        "Rules:\n"
        "1. Every question.handle must be a handle that exists in the perception. Never invent a field.\n"
        "2. A placeholder is a format hint, never the field's identity. 'DD-MM-YYYY' is a format, not a question.\n"
        "3. Match meaning, not strings: DOB, date of birth, birthday and 'when were you born' are date_of_birth.\n"
        "4. Distinguish first, middle and last name, and name_as_matric when the page asks for the name as printed on the matric certificate.\n"
        "5. Never ask the human to classify the page or explain a label. The human only answers facts and choices only they know.\n"
        "6. Only real page actions become paths. Mark a path needs_human_choice when the page offers a genuine choice between account or application paths.\n"
        "7. If a question is unclear, set concept to null and explain why. Do not guess.\n"
        "8. Evidence must cite the label, helper text, group heading or another human-visible source.\n"
    )


def _parse_json_object(content: str) -> Dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("No JSON object found in the model response.")
    return json.loads(text[start : end + 1])


def _merge_model_brief(
    data: Dict[str, Any],
    perception: Perception,
    deterministic: PageBrief,
    *,
    model: str = "",
) -> PageBrief:
    valid_handles = {field.handle for field in perception.fields}
    valid_actions = {action.handle for action in perception.actions}
    deterministic_by_handle = {
        question.handle: question for question in deterministic.questions
    }

    page_type = str(data.get("page_type") or "").upper()
    if page_type not in PAGE_TYPES:
        page_type = deterministic.page_type

    sections: List[BriefSection] = []
    covered: set[str] = set()
    for raw_section in data.get("sections") or []:
        if not isinstance(raw_section, dict):
            continue
        questions: List[BriefQuestion] = []
        for raw in raw_section.get("questions") or []:
            if not isinstance(raw, dict):
                continue
            handle = str(raw.get("handle") or "")
            if handle not in valid_handles or handle in covered:
                continue
            base = deterministic_by_handle.get(handle) or _empty_question(handle)
            merged = _merge_question(base, raw)
            questions.append(merged)
            covered.add(handle)
        if questions:
            sections.append(
                BriefSection(
                    section_id="sec-" + _slug(str(raw_section.get("heading") or "section"))[:40] + "-" + str(len(sections) + 1),
                    heading=str(raw_section.get("heading") or "Page")[:200],
                    confidence=_clamp(raw_section.get("confidence"), _average([q.concept_confidence for q in questions])),
                    questions=questions,
                )
            )

    missing = [question for question in deterministic.questions if question.handle not in covered]
    if missing:
        sections.append(
            BriefSection(
                section_id="sec-more-" + str(len(sections) + 1),
                heading="More questions on this page",
                confidence=_average([q.concept_confidence for q in missing if q.concept]),
                questions=missing,
            )
        )

    if not sections:
        sections = deterministic.sections

    paths: List[BriefPath] = []
    for raw in data.get("paths") or []:
        if not isinstance(raw, dict):
            continue
        handle = str(raw.get("handle") or "")
        if handle not in valid_actions:
            continue
        kind = str(raw.get("kind") or "unknown")
        if kind not in PATH_KINDS:
            kind = "unknown"
        label = str(raw.get("label") or "").strip()
        if not label:
            action = next((item for item in perception.actions if item.handle == handle), None)
            label = (action.text or action.name) if action else ""
        if not label:
            continue
        if _HUMAN_ONLY_PATH_RE.search(label):
            # Sending a code, verifying an OTP or solving a CAPTCHA is a
            # human-only step, never a path the agent may take.
            continue
        paths.append(
            BriefPath(
                path_id="p-" + str(len(paths) + 1),
                label=label[:200],
                handle=handle,
                kind=kind,
                needs_human_choice=bool(raw.get("needs_human_choice")),
                evidence=[f"action: {label[:120]}"],
            )
        )
    if not paths:
        paths = deterministic.paths

    information = deterministic.information
    raw_information = data.get("information")
    if isinstance(raw_information, list) and raw_information:
        information = [
            BriefInformation(
                label=str(item.get("label") or "")[:120],
                value=str(item.get("value") or "")[:300],
                kind=str(item.get("kind") or "text")[:40],
            )
            for item in raw_information
            if isinstance(item, dict) and str(item.get("label") or "").strip()
        ][:8]

    human_only = deterministic.human_only
    raw_human = data.get("human_only")
    if isinstance(raw_human, list) and raw_human:
        human_only = sorted({str(item).strip().lower() for item in raw_human if str(item).strip()})
        if "final_submit" not in human_only:
            human_only.append("final_submit")

    ambiguities = deterministic.ambiguities
    raw_ambiguities = data.get("ambiguities")
    if isinstance(raw_ambiguities, list) and raw_ambiguities:
        ambiguities = [
            BriefAmbiguity(
                ambiguity_id=f"amb-{index + 1}",
                description=str(item.get("description") or "")[:500],
                question_ids=[str(value) for value in (item.get("question_ids") or [])][:20],
                resolution=str(item.get("resolution") or "unresolved")[:120],
                confidence=_clamp(item.get("confidence"), 0.5),
            )
            for index, item in enumerate(raw_ambiguities)
            if isinstance(item, dict)
            and str(item.get("description") or "").strip()
            and not _HUMAN_ONLY_AMBIGUITY_RE.search(str(item.get("description") or ""))
        ][:10]

    questions = [question for section in sections for question in section.questions]
    title = str(data.get("title") or deterministic.title)[:200]
    purpose = str(data.get("purpose") or deterministic.purpose)[:800]
    confidence = _clamp(data.get("confidence"), _overall_confidence(page_type, questions, perception))
    signature = perception.page_signature
    return PageBrief(
        brief_id="brief-" + hashlib.sha256(f"{signature}:{model}".encode("utf-8")).hexdigest()[:16],
        page_signature=signature,
        url=perception.url,
        title=title,
        page_type=page_type,
        purpose=purpose,
        confidence=confidence,
        sections=sections,
        information=information,
        paths=paths,
        human_only=human_only,
        ambiguities=ambiguities,
        source="model",
        model=model or None,
        cache={"created_at": _now(), "invalidated_by": None},
        perception=perception.summary(),
    )


def _empty_question(handle: str) -> BriefQuestion:
    return BriefQuestion(question_id="q-" + handle, handle=handle)


def _merge_question(base: BriefQuestion, raw: Dict[str, Any]) -> BriefQuestion:
    raw_concept = raw.get("concept")
    if raw_concept is not None:
        raw_concept = str(raw_concept).strip() or None
    if raw_concept and raw_concept not in concepts.CONCEPTS:
        raw_concept = None
    base_confidence = float(base.concept_confidence or 0.0)
    model_confidence = _clamp(raw.get("concept_confidence"), base_confidence)

    # Evidence wins.  A confirmation field is the same fact repeated, and a
    # high-confidence label match is not overridden by a lower-confidence model
    # guess.
    if base.concept and (
        base.constraints.get("confirmation")
        or model_confidence < base_confidence
    ):
        concept = base.concept
        concept_confidence = base_confidence
    elif raw_concept:
        concept = raw_concept
        concept_confidence = model_confidence
    else:
        concept = base.concept
        concept_confidence = base_confidence

    # A format extracted from the page is stronger than a model guess.
    expected_format = base.expected_format
    if not expected_format and raw.get("expected_format"):
        expected_format = str(raw.get("expected_format"))[:40]

    return BriefQuestion(
        question_id=base.question_id,
        asked=str(raw.get("asked") or base.asked)[:400],
        concept=concept,
        concept_label=concepts.concept_label(concept),
        concept_confidence=round(concept_confidence, 2),
        answer_type=str(raw.get("answer_type") or base.answer_type)[:30],
        expected_format=expected_format,
        required=bool(raw.get("required", base.required)),
        handle=base.handle,
        group_heading=base.group_heading,
        evidence=[
            str(item)[:300]
            for item in (raw.get("evidence") or base.evidence)
            if str(item).strip()
        ][:8],
        constraints=dict(base.constraints),
        human_only=base.human_only,
        reason=str(raw.get("reason") or base.reason)[:500],
    )


_HUMAN_ONLY_PATH_RE = re.compile(
    r"\botp\b|one[-\s]?time|send\s*(?:demo\s*)?code|verify\s*(?:otp|code)|"
    r"captcha|security\s*code|resend\s*(?:otp|code)",
    re.IGNORECASE,
)
_HUMAN_ONLY_AMBIGUITY_RE = re.compile(
    r"\botp\b|one[-\s]?time|captcha",
    re.IGNORECASE,
)


def _clamp(value: Any, fallback: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return round(float(fallback or 0.0), 2)
    return round(max(0.0, min(1.0, number)), 2)
