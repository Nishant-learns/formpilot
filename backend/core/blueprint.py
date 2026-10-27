"""Structured DOM blueprint used by the action resolver.

The blueprint is a *normalized* view of one page observation.  It keeps the
information an executor needs to find and operate a control safely:

* a per-scan element id,
* the frame it belongs to,
* its role and accessible name,
* unique CSS / XPath locators,
* visibility, enabled, editable and interactability flags,
* a hit-test result (is another element covering it?),
* a stable element hash for drift detection.

It is deliberately independent of Playwright so it can be built and tested
without a browser.  ``DOMScanner`` produces the raw JSON; this module turns it
into typed objects and indexes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional


_GATEWAY_RE = re.compile(
    r"new\s*registration|account\s*creation|create\s*(?:an?\s*)?account|"
    r"create\s+your\s+account|register(?:\s*here)?|registration\b|new\s*user|"
    r"new\s*applicant|get\s*started|otr|apply\s*online|sign\s*up|signup|"
    r"candidate\s*login|sign\s*in|signin|login|log\s*in|already\s*registered|"
    r"returning\s*candidate|resume|continue\s+(?:my\s+)?application|"
    r"aadhaar|digilocker",
    re.IGNORECASE,
)
_NEXT_RE = re.compile(
    r"save\s*&\s*next|save\s*and\s*next|proceed|continue|next\s*step|\bnext\b|"
    r"submit|log\s*in|sign\s*in|register|create\s*(?:an?\s*)?account|"
    r"account\s*creation|verify|confirm|send\s*otp|get\s*otp|apply|pay|"
    r"checkout|finish|complete\s*(?:application|registration|profile)|save|update",
    re.IGNORECASE,
)
_BACK_RE = re.compile(r"\b(?:back|previous|cancel)\b", re.IGNORECASE)
_FIELD_TAGS = {"input", "select", "textarea"}


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


@dataclass
class BlueprintElement:
    """One meaningful DOM element in a page observation."""

    id: str
    frame: str = "main"
    frame_index: int = 0
    parent_id: Optional[str] = None
    depth: int = 0
    tag: str = ""
    role: str = ""
    name: str = ""
    text: str = ""
    attributes: Dict[str, Any] = field(default_factory=dict)
    css: str = ""
    css_unique: bool = False
    xpath: str = ""
    rect: Dict[str, float] = field(default_factory=dict)
    visible: bool = False
    in_viewport: bool = False
    enabled: bool = True
    editable: bool = False
    interactable: bool = False
    hover_only: bool = False
    covered_by: Optional[Dict[str, Any]] = None
    element_hash: str = ""
    options: List[Dict[str, Any]] = field(default_factory=list)
    children: List[str] = field(default_factory=list)
    shadow_host: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BlueprintElement":
        rect = data.get("rect") or {}
        covered = data.get("covered_by") or data.get("coveredBy")
        options = data.get("options") or []
        return cls(
            id=str(data.get("id") or ""),
            frame=str(data.get("frame") or "main"),
            frame_index=_as_int(data.get("frame_index") or data.get("frameIndex")),
            parent_id=(
                str(data.get("parent_id") or data.get("parentId"))
                if (data.get("parent_id") or data.get("parentId"))
                else None
            ),
            depth=_as_int(data.get("depth")),
            tag=str(data.get("tag") or data.get("tagName") or "").lower(),
            role=str(data.get("role") or "").lower(),
            name=str(data.get("name") or data.get("accessible_name") or ""),
            text=str(data.get("text") or ""),
            attributes=dict(data.get("attributes") or {}),
            css=str(data.get("css") or ""),
            css_unique=_as_bool(data.get("css_unique") or data.get("cssUnique")),
            xpath=str(data.get("xpath") or ""),
            rect={
                "x": _as_float(rect.get("x")),
                "y": _as_float(rect.get("y")),
                "width": _as_float(rect.get("width") or rect.get("w")),
                "height": _as_float(rect.get("height") or rect.get("h")),
            },
            visible=_as_bool(data.get("visible")),
            in_viewport=_as_bool(data.get("in_viewport") or data.get("inViewport")),
            enabled=_as_bool(data.get("enabled"), True),
            editable=_as_bool(data.get("editable")),
            interactable=_as_bool(data.get("interactable")),
            hover_only=_as_bool(data.get("hover_only") or data.get("hoverOnly")),
            covered_by=dict(covered) if isinstance(covered, dict) else None,
            element_hash=str(data.get("element_hash") or data.get("elementHash") or ""),
            options=[
                {
                    "text": str(option.get("text") or ""),
                    "value": str(option.get("value") or ""),
                    "index": _as_int(option.get("index"), index),
                }
                for index, option in enumerate(options)
                if isinstance(option, dict)
            ],
            children=[str(child) for child in (data.get("children") or [])],
            shadow_host=(
                str(data.get("shadow_host") or data.get("shadowHost"))
                if (data.get("shadow_host") or data.get("shadowHost"))
                else None
            ),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "frame": self.frame,
            "frame_index": self.frame_index,
            "parent_id": self.parent_id,
            "depth": self.depth,
            "tag": self.tag,
            "role": self.role,
            "name": self.name,
            "text": self.text,
            "attributes": dict(self.attributes),
            "css": self.css,
            "css_unique": self.css_unique,
            "xpath": self.xpath,
            "rect": dict(self.rect),
            "visible": self.visible,
            "in_viewport": self.in_viewport,
            "enabled": self.enabled,
            "editable": self.editable,
            "interactable": self.interactable,
            "hover_only": self.hover_only,
            "covered_by": dict(self.covered_by) if self.covered_by else None,
            "element_hash": self.element_hash,
            "options": [dict(option) for option in self.options],
            "children": list(self.children),
            "shadow_host": self.shadow_host,
        }

    @property
    def label(self) -> str:
        """Best human label for prompts and diagnostics."""
        if self.name:
            return self.name
        if self.text:
            return self.text
        for key in ("aria-label", "placeholder", "title", "alt", "name", "id"):
            value = self.attributes.get(key)
            if value:
                return str(value)
        return self.tag or "element"

    @property
    def is_field(self) -> bool:
        if self.tag in _FIELD_TAGS:
            return str(self.attributes.get("type") or "").lower() != "hidden"
        return str(self.attributes.get("contenteditable") or "").lower() in {"true", "plaintext-only"}

    @property
    def is_navigation(self) -> bool:
        return self.tag == "a" and bool(self.attributes.get("href"))

    @property
    def is_final_action(self) -> bool:
        haystack = _norm(f"{self.name} {self.text}")
        return bool(
            re.search(
                r"\b(?:submit|pay|payment|checkout|finish|complete\s+(?:application|registration)|proceed\s+to\s+pay)\b",
                haystack,
            )
        ) and not re.search(r"save\s*&\s*next|save\s+and\s+next", haystack)


class PageBlueprint:
    """Typed blueprint plus query helpers."""

    def __init__(
        self,
        *,
        scan_id: str,
        url: str,
        title: str,
        frames: Optional[List[Dict[str, Any]]] = None,
        elements: Optional[Iterable[BlueprintElement]] = None,
        roots: Optional[List[str]] = None,
        captured_at: str = "",
        truncated: bool = False,
        omitted_count: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.scan_id = scan_id
        self.url = url
        self.title = title
        self.frames = list(frames or [])
        self.elements: Dict[str, BlueprintElement] = {
            element.id: element for element in (elements or []) if element.id
        }
        self.roots = list(roots or [])
        self.captured_at = captured_at
        self.truncated = truncated
        self.omitted_count = omitted_count
        self.metadata = dict(metadata or {})

    # ------------------------------------------------------------------ build

    @classmethod
    def from_scan(
        cls,
        raw: Dict[str, Any],
        *,
        frames: Optional[List[Dict[str, Any]]] = None,
    ) -> "PageBlueprint":
        elements = [
            BlueprintElement.from_dict(item)
            for item in (raw.get("elements") or [])
            if isinstance(item, dict) and item.get("id")
        ]
        return cls(
            scan_id=str(raw.get("scan_id") or raw.get("scanId") or ""),
            url=str(raw.get("url") or ""),
            title=str(raw.get("title") or ""),
            frames=frames or raw.get("frames") or [],
            elements=elements,
            roots=[str(item) for item in (raw.get("roots") or [])],
            captured_at=str(raw.get("captured_at") or raw.get("capturedAt") or ""),
            truncated=_as_bool(raw.get("truncated")),
            omitted_count=_as_int(raw.get("omitted_count") or raw.get("omittedCount")),
            metadata={
                "ready_state": raw.get("ready_state") or raw.get("readyState"),
                "viewport": raw.get("viewport") or {},
                "scroll": raw.get("scroll") or {},
                "mutation_counter": raw.get("mutation_counter") or raw.get("mutationCounter"),
                "frameworks": raw.get("frameworks") or [],
            },
        )

    # ------------------------------------------------------------------ queries

    def get(self, element_id: Optional[str]) -> Optional[BlueprintElement]:
        if not element_id:
            return None
        return self.elements.get(str(element_id))

    def find(
        self,
        *,
        role: Optional[str] = None,
        name: Optional[str] = None,
        tag: Optional[str] = None,
        text: Optional[str] = None,
        visible: Optional[bool] = None,
        interactable: Optional[bool] = None,
        exact: bool = False,
    ) -> List[BlueprintElement]:
        role_norm = _norm(role) if role else None
        name_norm = _norm(name) if name else None
        tag_norm = _norm(tag) if tag else None
        text_norm = _norm(text) if text else None
        matches: List[BlueprintElement] = []
        for element in self.elements.values():
            if role_norm is not None and _norm(element.role) != role_norm:
                continue
            if tag_norm is not None and _norm(element.tag) != tag_norm:
                continue
            if visible is not None and element.visible is not visible:
                continue
            if interactable is not None and element.interactable is not interactable:
                continue
            if name_norm is not None:
                candidate = _norm(element.name)
                if (candidate != name_norm) if exact else (name_norm not in candidate):
                    continue
            if text_norm is not None:
                candidate = _norm(f"{element.text} {element.name}")
                if (candidate != text_norm) if exact else (text_norm not in candidate):
                    continue
            matches.append(element)
        return matches

    def interactables(self, *, visible_only: bool = True) -> List[BlueprintElement]:
        return [
            element
            for element in self.elements.values()
            if element.interactable and (element.visible or not visible_only)
        ]

    def fields(self, *, visible_only: bool = True) -> List[BlueprintElement]:
        return [
            element
            for element in self.elements.values()
            if element.is_field and (element.visible or not visible_only)
        ]

    def gateways(self) -> List[BlueprintElement]:
        return [
            element
            for element in self.interactables()
            if _GATEWAY_RE.search(f"{element.name} {element.text}")
        ]

    def next_candidates(self) -> List[BlueprintElement]:
        candidates = []
        for element in self.interactables():
            haystack = f"{element.name} {element.text}"
            if _BACK_RE.search(haystack):
                continue
            if _NEXT_RE.search(haystack):
                candidates.append(element)
        return candidates

    def by_role_name(self) -> Dict[str, List[BlueprintElement]]:
        index: Dict[str, List[BlueprintElement]] = {}
        for element in self.elements.values():
            key = f"{_norm(element.role)}:{_norm(element.name)}"
            index.setdefault(key, []).append(element)
        return index

    # ------------------------------------------------------------------ prompt

    def to_prompt_tree(self, max_nodes: int = 250, max_text: int = 120) -> str:
        """Compact HTML-like tree with ids for an AI planner.

        This is intentionally smaller than ``to_debug_json``.  The planner needs
        semantics and ids, not every attribute.
        """
        lines: List[str] = []
        emitted = 0
        visited = set()

        def render(element: BlueprintElement, indent: int) -> None:
            nonlocal emitted
            if emitted >= max_nodes or element.id in visited:
                return
            visited.add(element.id)
            emitted += 1
            attrs = [f'id="{element.id}"']
            if element.role:
                attrs.append(f'role="{_escape(element.role)}"')
            if element.name:
                attrs.append(f'name="{_escape(element.name[:max_text])}"')
            for key in ("type", "href", "placeholder", "aria-label", "value"):
                value = element.attributes.get(key)
                if value not in (None, "", True, False):
                    attrs.append(f'{key}="{_escape(str(value)[:max_text])}"')
            field_name = element.attributes.get("name")
            if field_name not in (None, "", True, False):
                attrs.append(f'field_name="{_escape(str(field_name)[:max_text])}"')
            if element.attributes.get("required"):
                attrs.append('required="true"')
            if element.attributes.get("disabled") or not element.enabled:
                attrs.append('disabled="true"')
            if not element.visible:
                attrs.append('visible="false"')
            if element.covered_by:
                attrs.append('covered="true"')
            if element.options:
                option_text = ", ".join(
                    _escape(str(option.get("text") or option.get("value") or ""))[:40]
                    for option in element.options[:20]
                )
                attrs.append(f'options="{option_text}"')
            text = (element.text or "").strip()
            if text and element.tag not in {"select", "option"}:
                attrs.append(f'text="{_escape(text[:max_text])}"')
            lines.append("  " * indent + f"<{element.tag or 'node'} {' '.join(attrs)}>")
            for child_id in element.children:
                child = self.elements.get(child_id)
                if child:
                    render(child, indent + 1)
            lines.append("  " * indent + f"</{element.tag or 'node'}>")

        for root_id in self.roots:
            root = self.elements.get(root_id)
            if root:
                render(root, 0)
        if not lines:
            for element in list(self.elements.values())[:max_nodes]:
                render(element, 0)
        if emitted >= max_nodes:
            lines.append(f"<!-- truncated at {max_nodes} nodes -->")
        return "\n".join(lines)

    # ------------------------------------------------------------------ debug

    def to_debug_json(self) -> Dict[str, Any]:
        return {
            "scan_id": self.scan_id,
            "url": self.url,
            "title": self.title,
            "frames": self.frames,
            "roots": self.roots,
            "captured_at": self.captured_at,
            "truncated": self.truncated,
            "omitted_count": self.omitted_count,
            "metadata": self.metadata,
            "elements": [element.to_dict() for element in self.elements.values()],
        }

    def summary(self) -> Dict[str, Any]:
        return {
            "scan_id": self.scan_id,
            "url": self.url,
            "title": self.title,
            "element_count": len(self.elements),
            "interactable_count": len(self.interactables()),
            "field_count": len(self.fields()),
            "frame_count": len(self.frames),
            "truncated": self.truncated,
            "omitted_count": self.omitted_count,
            "captured_at": self.captured_at,
        }

    # ------------------------------------------------------------------ legacy

    def enrich_legacy(self, dom: Dict[str, Any]) -> Dict[str, Any]:
        """Attach blueprint locators to the legacy scanner lists.

        The old form model and adapters read ``inputs``, ``gateways`` and
        ``nextButtons``.  Keeping those lists working while adding ids and
        locators lets us migrate the orchestrator incrementally.
        """
        for key in (
            "inputs",
            "gateways",
            "nextButtons",
            "captchaElements",
            "fileInputs",
            "otpInputs",
        ):
            for item in dom.get(key) or []:
                if not isinstance(item, dict):
                    continue
                element_id = item.get("elementId") or item.get("element_id")
                element = self.get(element_id)
                if not element:
                    continue
                item["element_id"] = element.id
                item["frame"] = element.frame
                item["role"] = element.role
                item["css"] = element.css
                item["css_unique"] = element.css_unique
                item["xpath"] = element.xpath
                item["element_hash"] = element.element_hash
                item["visible"] = element.visible
                item["interactable"] = element.interactable
                item["covered_by"] = element.covered_by
        return dom


def _escape(value: str) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
