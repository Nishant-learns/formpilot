"""Normalized, replayable description of a form page.

The raw DOM is not memory.  It is large, it contains values and session
tokens, and it changes on every render.  This module turns one observation
into a small structure:

* a page classification with evidence and confidence
* a canonical field list with multiple locator strategies
* a structural fingerprint that ignores CSRF tokens and random ids
* explicit provenance for every value: vault, missing or unknown

No field values are copied into the fingerprint or the recipe.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlsplit

from . import field_registry
from .dom_scanner import DOMScanner


_RANDOM_TOKEN_RE = re.compile(r"(?<![a-z])(?:[a-f0-9]{12,}|\d{8,})(?![a-z])", re.IGNORECASE)
_MULTISPACE_RE = re.compile(r"\s+")
_SAFE_KEY_RE = re.compile(r"[^a-z0-9_]+")

# These are never profile values.  They are one-time human inputs and must not
# be treated as an unknown field that FormPilot could remember or guess.
_CAPTCHA_HINT_RE = re.compile(r"captcha|security\s*(?:check|code)", re.IGNORECASE)
_OTP_HINT_RE = re.compile(
    r"\botp\b|one[-\s]?time\s*(?:password|code|pin)|verification\s*code|auth(?:entication)?\s*code",
    re.IGNORECASE,
)


def _norm_text(value: Any) -> str:
    text = str(value or "").lower()
    text = _RANDOM_TOKEN_RE.sub("#", text)
    text = re.sub(r"[^a-z0-9#]+", " ", text)
    return _MULTISPACE_RE.sub(" ", text).strip()


def _norm_name(value: Any) -> str:
    text = str(value or "").lower()
    text = _RANDOM_TOKEN_RE.sub("#", text)
    return re.sub(r"[^a-z0-9#]+", "_", text).strip("_")


def _slug(value: Any, fallback: str) -> str:
    text = _SAFE_KEY_RE.sub("_", str(value or "").lower()).strip("_")
    return text[:48] or fallback


def _safe_json_list(values: Iterable[Any], limit: int = 60) -> List[Any]:
    return list(values)[:limit]


class FormModel:
    """Builds a stable form map from one DOMScanner observation."""

    PAGE_TYPES = {
        "portal_entry",
        "login",
        "registration",
        "application_form",
        "payment",
        "form_error",
        "dashboard",
        "captcha",
        "unknown",
    }

    # ------------------------------------------------------------------ public

    @classmethod
    def build_form_map(
        cls,
        dom: Dict[str, Any],
        url: str,
        *,
        vault: Any = None,
        recipe: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        page = cls.classify_page(dom, url)
        fields = [
            cls.build_field(item, vault=vault)
            for item in (dom.get("inputs") or [])
            if str(item.get("type") or "").lower() not in {"submit", "button", "reset", "image"}
        ]
        fingerprint, signature = cls.fingerprint(dom, url)

        known = [field for field in fields if field["semantic_key"]]
        human = [field for field in fields if field.get("challenge")]
        unknown = [
            field for field in fields if not field["semantic_key"] and not field.get("challenge")
        ]
        missing = [field for field in known if field["value_source"] == "missing"]
        sensitive = [field for field in fields if field["sensitive"]]

        form_map: Dict[str, Any] = {
            "url": url,
            "display_url": cls.display_url(url),
            "title": str(dom.get("title") or "")[:240],
            "portal": cls.portal(url),
            "page_type": page["page_type"],
            "page_confidence": page["confidence"],
            "page_scores": page["scores"],
            "page_evidence": page["evidence"],
            "challenge": page["challenge"],
            "fingerprint": fingerprint,
            "fingerprint_short": fingerprint[:12],
            "structural_signature": signature,
            "frameworks": list(dom.get("frameworks") or [])[:8],
            "step_heading": str(dom.get("stepHeading") or "")[:180],
            "active_section_id": str(dom.get("activeSectionId") or "")[:120],
            "field_count": len(fields),
            "known_field_count": len(known),
            "unknown_field_count": len(unknown),
            "human_field_count": len(human),
            "human_fields": [
                {"key": field["key"], "label": field["label"], "challenge": field["challenge"]}
                for field in human
            ],
            "missing_value_count": len(missing),
            "sensitive_field_count": len(sensitive),
            "fields": fields,
            "gateways": cls._gateways(dom),
            "captcha": cls._captcha(dom),
            "errors": [str(error)[:500] for error in (dom.get("errors") or [])[:6]],
            "next_actions": cls._next_actions(dom),
            "file_inputs": list(dom.get("fileInputs") or [])[:12],
            "live_photo_required": bool(dom.get("livePhotoRequired")),
            "otp_inputs": list(dom.get("otpInputs") or [])[:8],
            "form_action": str(dom.get("formAction") or "")[:500],
            "payment_signals": int(dom.get("paymentSignals") or 0),
            "has_payment_button": bool(dom.get("hasPaymentButton")),
            "form_count": int(dom.get("formCount") or 0),
        }
        if recipe is not None:
            form_map["recipe"] = recipe
        return form_map

    @classmethod
    def build_field(cls, item: Dict[str, Any], *, vault: Any = None) -> Dict[str, Any]:
        field_type = str(item.get("type") or "text").lower()
        tag = str(item.get("tagName") or "input").lower()
        label = str(item.get("label") or "").strip()[:240]
        name = str(item.get("name") or "").strip()[:180]
        field_id = str(item.get("id") or "").strip()[:180]

        challenge = cls.human_challenge(item)
        if challenge:
            # A CAPTCHA or OTP is completed by the human at its own checkpoint.
            # It is not a profile value and it must not become an unknown field.
            semantic_key = None
            is_verify = False
            suggestion = None
            confidence = 96
            value_source = "human"
            sensitive = True
        else:
            semantic_key, is_verify = DOMScanner.classify_field(item)
            confidence = 94 if semantic_key else 0
            suggestion = None
            if not semantic_key:
                suggestion, suggestion_confidence = cls._suggest_key(label, name, field_type)
                if suggestion:
                    confidence = suggestion_confidence

            if semantic_key:
                value = field_registry.resolve_value(vault, semantic_key) if vault is not None else None
                if value not in (None, ""):
                    value_source = "vault"
                else:
                    value_source = "missing"
                spec = field_registry.spec_for(semantic_key)
                sensitive = bool(spec and spec.sensitive)
            else:
                value_source = "unknown"
                sensitive = bool(
                    re.search(r"aadhaar|passport|bank|account|card|cvv|password|otp|captcha", f"{label} {name}", re.I)
                )

        if challenge:
            generated_key = f"human_{challenge}_{int(item.get('index') or 0)}"
        else:
            generated_key = semantic_key or f"unknown_{_slug(name or label or f'field_{item.get('index', 0)}', 'field')}"
        options = [
            {"text": str(option.get("text") or "")[:160], "value": str(option.get("value") or "")[:160]}
            for option in (item.get("options") or [])[:60]
        ]

        return {
            "index": int(item.get("index") or 0),
            "semantic_key": semantic_key,
            "suggested_key": suggestion,
            "key": generated_key,
            "label": label or name or f"Field {int(item.get('index') or 0) + 1}",
            "name": name,
            "id": field_id,
            "element_id": item.get("element_id"),
            "frame": item.get("frame"),
            "role": item.get("role"),
            "css": item.get("css"),
            "css_unique": bool(item.get("css_unique")),
            "xpath": item.get("xpath"),
            "element_hash": item.get("element_hash"),
            "visible": bool(item.get("visible", True)),
            "interactable": bool(item.get("interactable", True)),
            "covered_by": item.get("covered_by"),
            "tag": tag,
            "type": field_type,
            "required": bool(item.get("required")),
            "options": options,
            "option_count": len(options),
            "has_value": bool(str(item.get("value") or "").strip()),
            "value_source": value_source,
            "challenge": challenge,
            "sensitive": sensitive,
            "requires_confirmation": bool(sensitive or is_verify),
            "confidence": confidence,
            "needs_user_input": value_source in {"missing", "unknown", "human"},
            "ask_reason": (
                "human_challenge"
                if value_source == "human"
                else "unknown_field"
                if value_source == "unknown"
                else "missing_value"
                if value_source == "missing"
                else None
            ),
            "locators": cls.locators(item),
            "rect": item.get("rect") or {},
        }

    @staticmethod
    def human_challenge(item: Dict[str, Any]) -> Optional[str]:
        """Return 'captcha' or 'otp' for fields only a human may fill."""
        field_type = str(item.get("type") or "text").lower()
        if field_type in {"hidden", "file", "submit", "button", "reset", "image"}:
            return None
        hint = " ".join(
            str(item.get(key) or "")
            for key in ("label", "name", "id", "placeholder")
        )
        if not hint.strip():
            return None
        if _CAPTCHA_HINT_RE.search(hint):
            # "Card security code" is a payment detail, not a CAPTCHA.
            if re.search(r"\b(?:card|cvv|cvc|debit|credit)\b", hint, re.IGNORECASE):
                return None
            return "captcha"
        if _OTP_HINT_RE.search(hint):
            return "otp"
        return None

    @classmethod
    def locators(cls, item: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Return locators in the order the executor should try them.

        The per-scan blueprint id is first because it is the only locator that
        was validated as unique when the page was observed.  It is not stored
        in a recipe; durable CSS/XPath/role/label strategies follow it.
        """
        field_type = str(item.get("type") or "text").lower()
        tag = str(item.get("tagName") or "input").lower()
        label = str(item.get("label") or "").strip()
        name = str(item.get("name") or "").strip()
        field_id = str(item.get("id") or "").strip()
        element_id = str(item.get("element_id") or "").strip()
        css = str(item.get("css") or "").strip()
        xpath = str(item.get("xpath") or "").strip()
        role = str(item.get("role") or "").strip()
        locators: List[Dict[str, Any]] = []
        if element_id:
            locators.append({"strategy": "blueprint_id", "value": element_id})
        if css:
            locators.append({"strategy": "css", "value": css, "unique": bool(item.get("css_unique"))})
        if xpath:
            locators.append({"strategy": "xpath", "value": xpath})
        if field_id:
            locators.append({"strategy": "id", "value": field_id})
        if name:
            locators.append({"strategy": "name", "value": name})
        if label:
            locators.append({"strategy": "label", "value": label[:180]})
            inferred_role = role or (
                "combobox"
                if tag == "select"
                else "checkbox"
                if field_type == "checkbox"
                else "radio"
                if field_type == "radio"
                else "textbox"
            )
            locators.append({"strategy": "role", "role": inferred_role, "name": label[:180]})
        elif role and item.get("name"):
            locators.append(
                {"strategy": "role", "role": role, "name": str(item.get("name"))[:180]}
            )
        if tag == "select":
            locators.append({"strategy": "css", "value": "select"})
        elif tag == "textarea":
            locators.append({"strategy": "css", "value": "textarea"})
        elif field_type == "file":
            locators.append({"strategy": "css", "value": "input[type=file]"})
        else:
            locators.append({"strategy": "css", "value": f"{tag}[type='{field_type}']"})
        locators.append({"strategy": "index", "value": int(item.get("index") or 0)})
        return locators

    # ------------------------------------------------------------------ page type

    @classmethod
    def classify_page(cls, dom: Dict[str, Any], url: str) -> Dict[str, Any]:
        text = str(dom.get("visibleText") or "").lower()
        inputs = dom.get("inputs") or []
        gateways = dom.get("gateways") or []
        errors = dom.get("errors") or []
        captcha_elements = dom.get("captchaElements") or []
        scores: Dict[str, int] = {}
        evidence: List[str] = []

        gateway_types = {str(g.get("type") or "") for g in gateways}
        if "NEW_REGISTRATION" in gateway_types and "LOGIN" in gateway_types:
            scores["portal_entry"] = 95
            evidence.append("Both New Registration and Candidate Login are visible.")
        elif "LOGIN" in gateway_types:
            scores["login"] = 88
            evidence.append("A candidate login option is visible.")
        elif "NEW_REGISTRATION" in gateway_types:
            scores["registration"] = 86
            evidence.append("A new-registration option is visible.")

        password_input = any(str(item.get("type") or "").lower() == "password" for item in inputs)
        if password_input:
            scores["login"] = max(scores.get("login", 0), 92)
            evidence.append("The page has a password field.")

        if dom.get("hasPaymentButton") or int(dom.get("paymentSignals") or 0) >= 3:
            scores["payment"] = 96
            evidence.append("Payment controls or fee language are present.")

        if errors and inputs:
            scores["form_error"] = 82
            evidence.append("The portal is showing validation errors.")
        elif errors:
            scores["form_error"] = 70
            evidence.append("The portal is showing an error message.")

        if any(token in text for token in ("dashboard", "sign out", "logout", "registration id", "logged in")):
            scores["dashboard"] = 78
            evidence.append("Dashboard or signed-in language is visible.")

        if captcha_elements and not inputs:
            scores["captcha"] = 84
            evidence.append("A security challenge is visible without a form.")

        if inputs:
            scores["application_form"] = 72
            evidence.append(f"{len(inputs)} visible input field(s) were found.")

        if "new registration" in text and "login" in text and not inputs:
            scores["portal_entry"] = max(scores.get("portal_entry", 0), 88)
            evidence.append("The page text offers registration and login paths.")

        if not scores:
            scores["unknown"] = 40
            evidence.append("No reliable form or portal signal was found.")

        page_type = max(scores, key=lambda key: (scores[key], key == "application_form"))
        challenge = None
        if captcha_elements:
            challenge = "captcha"
        elif any(token in text for token in ("verify otp", "one-time password", "verification code")):
            challenge = "otp"

        return {
            "page_type": page_type,
            "confidence": int(scores.get(page_type, 0)),
            "scores": scores,
            "evidence": evidence[:8],
            "challenge": challenge,
        }

    # ------------------------------------------------------------------ fingerprint

    @classmethod
    def fingerprint(cls, dom: Dict[str, Any], url: str) -> tuple[str, str]:
        """Return (sha256, human-readable signature).

        Values, hidden inputs, CSRF tokens and long random identifiers are
        excluded.  Labels, input types, required flags, headings and navigation
        button labels are included because those are what a recipe depends on.
        """
        parts = cls.display_url(url)
        form_count = int(dom.get("formCount") or 0)
        parts += f"|forms={form_count}"

        fields = []
        for item in dom.get("inputs") or []:
            field_type = str(item.get("type") or "text").lower()
            if field_type in {"hidden", "submit", "button", "reset", "image"}:
                continue
            fields.append(
                "|".join(
                    [
                        str(item.get("tagName") or "input").lower(),
                        field_type,
                        _norm_name(item.get("name")),
                        _norm_text(item.get("label")),
                        "req" if item.get("required") else "opt",
                    ]
                )
            )
        for field in sorted(fields):
            parts += f"|field:{field}"

        headings = [str(dom.get("stepHeading") or "")]
        for heading in headings:
            if heading:
                parts += f"|heading:{_norm_text(heading)}"

        # Two steps can show identical fields under the same generic heading.
        # The active section and the form-action path keep their fingerprints
        # distinct.  Query strings are ignored because they carry session data.
        active_section = str(dom.get("activeSectionId") or "").strip()
        if active_section:
            parts += f"|section:{_norm_text(active_section)}"
        action_raw = str(dom.get("formAction") or "").strip()
        if action_raw:
            try:
                action_path = urlsplit(action_raw).path
            except ValueError:
                action_path = ""
            if action_path and action_path != "/":
                parts += f"|action:{_norm_text(action_path)}"

        button_labels = sorted(
            {_norm_text(button.get("text")) for button in (dom.get("nextButtons") or []) if button.get("text")}
        )
        for button in button_labels:
            parts += f"|button:{button}"

        gateways = sorted(
            {f"{gateway.get('type')}:{_norm_text(gateway.get('text'))}" for gateway in (dom.get("gateways") or [])}
        )
        for gateway in gateways:
            parts += f"|gateway:{gateway}"

        digest = hashlib.sha256(parts.encode("utf-8")).hexdigest()
        return digest, parts

    # ------------------------------------------------------------------ misc

    @classmethod
    def portal(cls, url: str) -> str:
        try:
            return (urlsplit(str(url or "")).netloc or "").lower()
        except Exception:
            return ""

    @classmethod
    def display_url(cls, url: str) -> str:
        try:
            parts = urlsplit(str(url or ""))
            base = f"{parts.scheme}://{parts.netloc}{parts.path}"
            return base + (f"#{parts.fragment}" if parts.fragment else "")
        except Exception:
            return ""

    @classmethod
    def _gateways(cls, dom: Dict[str, Any]) -> List[Dict[str, Any]]:
        unique: List[Dict[str, Any]] = []
        seen = set()
        for gateway in dom.get("gateways") or []:
            key = (
                str(gateway.get("type") or ""),
                _norm_text(gateway.get("text")),
                gateway.get("element_id") or gateway.get("css") or gateway.get("id"),
            )
            if key in seen:
                continue
            seen.add(key)
            unique.append(
                {
                    "type": str(gateway.get("type") or "UNKNOWN"),
                    "text": str(gateway.get("text") or "")[:180],
                    "id": gateway.get("id"),
                    "name": gateway.get("name"),
                    "tag": str(gateway.get("tagName") or "")[:40],
                    "role": str(gateway.get("role") or "")[:40],
                    "href": str(gateway.get("href") or "")[:500],
                    "element_id": gateway.get("element_id"),
                    "frame": gateway.get("frame"),
                    "css": gateway.get("css"),
                    "css_unique": bool(gateway.get("css_unique")),
                    "xpath": gateway.get("xpath"),
                    "element_hash": gateway.get("element_hash"),
                    "visible": gateway.get("visible"),
                    "interactable": gateway.get("interactable"),
                    "covered_by": gateway.get("covered_by"),
                    "requires_user_choice": True,
                }
            )
        return unique[:12]

    @classmethod
    def _captcha(cls, dom: Dict[str, Any]) -> Dict[str, Any]:
        elements = dom.get("captchaElements") or []
        kinds = sorted({str(element.get("kind") or "unknown") for element in elements})
        return {
            "present": bool(elements),
            "kinds": kinds,
            "count": len(elements),
            "requires_human": bool(elements),
            "solver_policy": "human_handoff_only",
            "elements": [
                {
                    "kind": str(element.get("kind") or "unknown"),
                    "tag": str(element.get("tagName") or ""),
                    "id": element.get("id"),
                    "prompt": str(element.get("prompt") or "")[:180],
                }
                for element in elements[:6]
            ],
        }

    @classmethod
    def _next_actions(cls, dom: Dict[str, Any]) -> List[Dict[str, Any]]:
        actions: List[Dict[str, Any]] = []
        for button in dom.get("nextButtons") or []:
            text = str(button.get("text") or "").strip()
            if not text:
                continue
            blocked = bool(
                re.search(
                    r"\b(?:submit|pay|payment|checkout|complete\s+(?:application|registration)|proceed\s+to\s+pay)\b",
                    text,
                    re.IGNORECASE,
                )
            ) and not re.search(r"save\s*&\s*next|save\s+and\s+next", text, re.IGNORECASE)
            actions.append(
                {
                    "text": text[:180],
                    "id": button.get("id"),
                    "element_id": button.get("element_id"),
                    "tag": str(button.get("tagName") or "")[:40],
                    "role": str(button.get("role") or "")[:40],
                    "frame": button.get("frame"),
                    "css": button.get("css"),
                    "xpath": button.get("xpath"),
                    "kind": "final_action" if blocked else "navigation",
                    "blocked": blocked,
                    "reason": "FormPilot never clicks payment or final submission." if blocked else None,
                }
            )
        return actions[:12]

    @classmethod
    def _suggest_key(cls, label: str, name: str, field_type: str) -> tuple[Optional[str], int]:
        """Fuzzy suggestion only; the engine still asks before using it."""
        haystack = _norm_text(f"{label} {name}")
        if not haystack:
            return None, 0
        best_key = None
        best_score = 0.0
        for key, spec in field_registry.FIELD_SPECS.items():
            if field_type == "file" and spec.kind != "file":
                continue
            if field_type != "file" and spec.kind == "file":
                continue
            spec_tokens = set(_norm_text(spec.label).split())
            hay_tokens = set(haystack.split())
            if not spec_tokens or not hay_tokens:
                continue
            overlap = len(spec_tokens & hay_tokens)
            score = overlap / max(1, len(spec_tokens))
            if score > best_score:
                best_score = score
                best_key = key
        if best_score >= 0.66:
            return best_key, int(50 + best_score * 35)
        return None, 0

    @classmethod
    def compact_for_recipe(cls, form_map: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Strip values and positions; keep only replayable structure."""
        compact: List[Dict[str, Any]] = []
        for field in form_map.get("fields") or []:
            # Scan ids are intentionally excluded: they are only valid for one
            # observation.  Recipes keep durable locators and element hashes.
            durable_locators = [
                locator
                for locator in (field.get("locators") or [])
                if locator.get("strategy") not in {"blueprint_id", "index"}
            ]
            compact.append(
                {
                    "key": field.get("semantic_key") or field.get("key"),
                    "suggested_key": field.get("suggested_key"),
                    "label": field.get("label"),
                    "name": field.get("name"),
                    "type": field.get("type"),
                    "required": bool(field.get("required")),
                    "challenge": field.get("challenge"),
                    "options": _safe_json_list(field.get("options") or [], limit=60),
                    "locators": _safe_json_list(durable_locators, limit=8),
                    "role": field.get("role"),
                    "css": field.get("css"),
                    "xpath": field.get("xpath"),
                    "element_hash": field.get("element_hash"),
                    "confidence": int(field.get("confidence") or 0),
                    "sensitive": bool(field.get("sensitive")),
                }
            )
        return compact
