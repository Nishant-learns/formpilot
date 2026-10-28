"""Deterministic decisions for portal entry, login method and identity.

The agent is not allowed to infer whether a candidate is new or returning from
the URL, browser history or a recipe.  This module turns what the page actually
shows into explicit options.  If the page offers more than one valid path, the
orchestrator must ask the candidate.  If it offers exactly one path, following
that single path is not a guess.

The functions here are deliberately browser-free so they can be unit tested
against captured DOM dictionaries.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

# Entry types used by the scanner, form model and orchestrator.
NEW_REGISTRATION = "NEW_REGISTRATION"
LOGIN = "LOGIN"
RESUME = "RESUME"
ENTRY_TYPES = (NEW_REGISTRATION, LOGIN, RESUME)

MODE_BY_TYPE = {
    NEW_REGISTRATION: "register",
    LOGIN: "login",
    RESUME: "resume",
}
TYPE_BY_MODE = {value: key for key, value in MODE_BY_TYPE.items()}

# Login methods are *not* entry paths.  They are choices inside a login form.
MOBILE_OTP = "mobile_otp"
AADHAAR_OTP = "aadhaar_otp"
URN_PASSWORD = "urn_password"
EMAIL_PASSWORD = "email_password"
PASSWORD = "password"
DIGILOCKER = "digilocker"

LOGIN_METHOD_LABELS = {
    MOBILE_OTP: "Mobile number and OTP",
    AADHAAR_OTP: "Aadhaar and OTP",
    URN_PASSWORD: "URN and password",
    EMAIL_PASSWORD: "Email and password",
    PASSWORD: "Password",
    DIGILOCKER: "DigiLocker",
}

_AUTH_PATH_RE = re.compile(
    r"(?:^|/)(?:login|log-in|signin|sign-in|signup|sign-up|register|registration|"
    r"create-account|new-registration|account/create|resume|continue)(?:/|$|[?#])",
    re.IGNORECASE,
)
_RESUME_PATH_RE = re.compile(
    r"(?:resume|continue|track|status|saved[-_]?application)", re.IGNORECASE
)
_REGISTER_TEXT_RE = re.compile(
    r"new\s*registration|account\s*creation|create\s*(?:an?\s*)?account|"
    r"create\s+your\s+account|register(?:\s*here)?|registration\b|sign\s*up|signup|"
    r"new\s*user|new\s*applicant|first[-\s]*time|get\s*started|"
    r"\botr\b|apply\s*online|naya\s*account|nayi\s*registration",
    re.IGNORECASE,
)
_LOGIN_TEXT_RE = re.compile(
    r"candidate\s*login|log\s*in|login|sign\s*in|signin|already\s*registered|"
    r"returning\s*candidate|existing\s*(?:user|account|candidate)|"
    r"purana\s*account|account\s*mein\s*login",
    re.IGNORECASE,
)
_RESUME_TEXT_RE = re.compile(
    r"resume|continue\s+(?:my\s+)?application|already\s+started|"
    r"saved\s+application|track\s+(?:my\s+)?application|"
    r"application\s+status|adhi\s*application",
    re.IGNORECASE,
)
_HELP_TEXT_RE = re.compile(
    r"forgot|help|instruction|manual|faq|guideline|privacy|terms|contact|"
    r"download|notification|syllabus|result|admit\s*card",
    re.IGNORECASE,
)
_OTP_TEXT_RE = re.compile(r"\botp\b|one[-\s]?time|verification\s*code", re.IGNORECASE)
_CAPTCHA_TEXT_RE = re.compile(r"captcha|security\s*(?:check|code)", re.IGNORECASE)


def normalize_mode(value: Any) -> Optional[str]:
    """Map UI/chat labels to one of register, login or resume."""
    text = re.sub(r"[^a-z]+", "_", str(value or "").strip().lower()).strip("_")
    if text in {"register", "registration", "new_registration", "signup", "sign_up", "create_account"}:
        return "register"
    if text in {"login", "log_in", "signin", "sign_in"}:
        return "login"
    if text in {"resume", "continue", "continue_application"}:
        return "resume"
    return None


def normalize_entry_type(value: Any) -> Optional[str]:
    mode = normalize_mode(value)
    return TYPE_BY_MODE.get(mode) if mode else None


def _entry_type_from_path(href: str) -> Optional[str]:
    raw = str(href or "").strip()
    if not raw:
        return None
    try:
        path = urlsplit(raw).path
    except ValueError:
        path = raw
    path = f"/{path.strip('/')}/".lower()
    if _RESUME_PATH_RE.search(path):
        return RESUME
    if re.search(r"/(?:signup|sign-up|register|registration|create-account|new-registration|account/create)(?:/|$)", path):
        return NEW_REGISTRATION
    if re.search(r"/(?:login|log-in|signin|sign-in)(?:/|$)", path):
        return LOGIN
    return None


def classify_entry_control(
    text: str,
    href: str = "",
    *,
    inside_form: bool = False,
) -> Optional[str]:
    """Classify one clickable as an entry path, or ``None``.

    A form submit button is an action, not an entry path.  The exception is an
    anchor/button whose href explicitly points at a login or signup route.
    """
    label = re.sub(r"\s+", " ", str(text or "")).strip()
    if not label or len(label) > 140:
        return None
    if _HELP_TEXT_RE.search(label):
        return None

    path_type = _entry_type_from_path(href)
    if inside_form and not path_type:
        return None
    if path_type:
        return path_type

    register = bool(_REGISTER_TEXT_RE.search(label))
    login = bool(_LOGIN_TEXT_RE.search(label))
    resume = bool(_RESUME_TEXT_RE.search(label))

    # "Continue application" is a resume path, not a login button.
    if resume and not register:
        return RESUME
    if register and login:
        # Text such as "Create Account & Login" is ambiguous.  Without a
        # disambiguating href the agent must not choose either side.
        return None
    if register:
        return NEW_REGISTRATION
    if login:
        return LOGIN
    return None


def _safe_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"0", "false", "no", "off"}


def _option_from_gateway(gateway: Dict[str, Any], order: int) -> Optional[Dict[str, Any]]:
    text = str(gateway.get("text") or gateway.get("label") or "").strip()
    href = str(gateway.get("href") or "").strip()
    inside_form = bool(gateway.get("insideForm") or gateway.get("inside_form"))
    path_type = _entry_type_from_path(href)
    # A submit button inside a form is an action, not an entry path.  Only an
    # explicit auth href is allowed to escape that rule.
    if inside_form and not path_type:
        return None
    entry_type = normalize_entry_type(gateway.get("type"))
    if not entry_type:
        entry_type = classify_entry_control(text, href, inside_form=inside_form)
    if not entry_type:
        return None
    if not _safe_bool(gateway.get("visible"), True):
        return None
    if not _safe_bool(gateway.get("interactable"), True):
        return None
    if gateway.get("covered_by") or gateway.get("coveredBy"):
        return None
    return {
        "type": entry_type,
        "mode": MODE_BY_TYPE[entry_type],
        "text": text or _default_option_text(entry_type),
        "id": gateway.get("id"),
        "element_id": gateway.get("element_id") or gateway.get("elementId"),
        "href": href,
        "tagName": str(gateway.get("tagName") or gateway.get("tag") or "").lower(),
        "role": str(gateway.get("role") or "").lower(),
        "css": gateway.get("css"),
        "xpath": gateway.get("xpath"),
        "inside_form": inside_form,
        "source": "portal",
        "order": order,
    }


def _default_option_text(entry_type: str) -> str:
    if entry_type == NEW_REGISTRATION:
        return "Create a new account"
    if entry_type == LOGIN:
        return "Sign in to an existing account"
    return "Resume an application already started"


def _canonical_score(option: Dict[str, Any]) -> Tuple[int, int, int, int, int, int]:
    """Prefer the primary, explicit control for one intent.

    Multiple links that all mean "register" are equivalent for the purpose of
    the entry decision.  Choosing the most explicit one is not guessing the
    candidate's intent; the candidate still chooses register versus login.
    The page that is already open wins for its own entry type, so choosing
    "login" on a login page does not re-click a navigation link that may not
    change the page.
    """
    expected_path = {
        NEW_REGISTRATION: r"(?:signup|sign-up|register|registration|create-account|new-registration|account/create)",
        LOGIN: r"(?:login|log-in|signin|sign-in)",
        RESUME: r"(?:resume|continue|track|status)",
    }[option["type"]]
    href_match = 1 if re.search(expected_path, str(option.get("href") or ""), re.IGNORECASE) else 0
    is_current_page = 1 if option.get("source") == "current_page" else 0
    has_id = 1 if option.get("element_id") else 0
    is_button = 1 if option.get("tagName") in {"button", "input"} else 0
    outside_form = 0 if option.get("inside_form") else 1
    # Shorter labels are usually navigation/CTA labels, not long paragraphs.
    short_label = max(0, 140 - len(str(option.get("text") or "")))
    return (is_current_page, href_match, has_id, outside_form, is_button, short_label)


def _option_target(option: Dict[str, Any]) -> str:
    """Normalized destination used to deduplicate equivalent links.

    The origin is ignored so a current-page option and an absolute link to the
    same page collapse together.  Different paths or queries stay distinct.
    """
    href = str(option.get("href") or "").strip()
    if not href:
        return _norm(option.get("text"))
    try:
        parsed = urlsplit(href)
    except ValueError:
        return href.rstrip("/").lower()
    path = (parsed.path or "/").rstrip("/").lower() or "/"
    return f"{path}?{parsed.query.lower()}" if parsed.query else path


def current_page_entry_type(
    dom: Dict[str, Any],
    form_map: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Return the explicit entry mode of the page itself, if it has one.

    This is evidence from the rendered form (confirm-password field, login
    method selector, login/signup heading), not an inference from browser
    history.  It becomes a selectable option, never a silent default.
    """
    inputs = dom.get("inputs") or []
    # A page with no fields is a hub or a link list, never an entry form.  A
    # signed-in dashboard can be labelled "registration" by its links, but the
    # current page itself cannot be the registration path.
    if not inputs:
        return None

    page_type = str((form_map or {}).get("page_type") or "").lower()
    if page_type == "login":
        return LOGIN
    if page_type == "registration":
        return NEW_REGISTRATION
    if page_type in {"portal_entry", "application_form", "payment", "dashboard"}:
        return None

    combined = " ".join(
        str(value or "")
        for value in (
            dom.get("url"),
            dom.get("stepHeading"),
            dom.get("title"),
            (dom.get("visibleText") or "")[:1200],
        )
    ).lower()
    labels = " ".join(
        " ".join(
            str(item.get(key) or "")
            for key in ("label", "name", "id", "placeholder")
        )
        for item in inputs
    ).lower()
    password_fields = [
        item for item in inputs if str(item.get("type") or "").lower() == "password"
    ]
    confirm_password = bool(
        re.search(r"confirm|re-?enter|repeat|verify", labels)
        and password_fields
    )
    login_select = any(
        str(item.get("tagName") or "").lower() == "select"
        and re.search(r"login|method|type", f"{item.get('name') or ''} {item.get('id') or ''} {item.get('label') or ''}", re.IGNORECASE)
        and len(item.get("options") or []) >= 2
        for item in inputs
    )
    registration_text = bool(
        re.search(r"sign\s*up|signup|register|registration|create\s*(?:an?\s*)?account|new\s*user|new\s*applicant", combined)
    )
    login_text = bool(re.search(r"log\s*in|login|sign\s*in|signin|forgot\s*password", combined))

    if confirm_password or (registration_text and password_fields):
        return NEW_REGISTRATION
    if login_select or (login_text and password_fields):
        return LOGIN
    if login_select or (login_text and not registration_text):
        return LOGIN
    return None


def _looks_like_auth_form(dom: Dict[str, Any]) -> bool:
    inputs = dom.get("inputs") or []
    if not inputs:
        return False
    for item in inputs:
        field_type = str(item.get("type") or "").lower()
        haystack = " ".join(
            str(item.get(key) or "") for key in ("label", "name", "id", "placeholder")
        ).lower()
        if field_type == "password":
            return True
        if _OTP_TEXT_RE.search(haystack) or _CAPTCHA_TEXT_RE.search(haystack):
            return True
        if re.search(r"login|sign\s*in|mobile|email|urn|user\s*id", haystack):
            return True
    return False


def entry_options(
    dom: Dict[str, Any],
    form_map: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Return the distinct explicit paths the page offers.

    Duplicates that point at the same target (for example a header "Register"
    link and a body "Register" button with the same href) collapse into one
    option.  Two links with different targets stay separate even when they share
    an entry type: "Preview Universal Registration" and "Proceed for Universal
    Registration" are genuinely different next steps and must be asked about.
    """
    candidates: List[Dict[str, Any]] = []
    for order, gateway in enumerate(dom.get("gateways") or []):
        if not isinstance(gateway, dict):
            continue
        option = _option_from_gateway(gateway, order)
        if option:
            candidates.append(option)

    current = current_page_entry_type(dom, form_map)
    if current:
        candidates.append(
            {
                "type": current,
                "mode": MODE_BY_TYPE[current],
                "text": _default_option_text(current),
                "id": None,
                "element_id": None,
                "href": str(dom.get("url") or ""),
                "tagName": "",
                "role": "",
                "css": None,
                "xpath": None,
                "inside_form": False,
                "source": "current_page",
                "order": len(candidates),
            }
        )

    grouped: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for option in candidates:
        grouped.setdefault((option["type"], _option_target(option)), []).append(option)

    result: List[Dict[str, Any]] = []
    for entry_type in ENTRY_TYPES:
        groups = [
            group
            for (group_type, _target), group in grouped.items()
            if group_type == entry_type
        ]
        for group in groups:
            group.sort(key=_canonical_score, reverse=True)
            chosen = dict(group[0])
            chosen["alternate_count"] = max(0, len(group) - 1)
            result.append(chosen)

    # Preserve the page order for the first occurrence of each target, but put
    # the synthetic current-page option where the page itself appears.
    result.sort(key=lambda option: option.get("order", 0))
    return result


def is_entry_page(
    dom: Dict[str, Any],
    form_map: Optional[Dict[str, Any]] = None,
) -> bool:
    """True when the page is asking how to enter, not an application form."""
    options = entry_options(dom, form_map)
    if not options:
        return False
    inputs = dom.get("inputs") or []
    page_type = str((form_map or {}).get("page_type") or "").lower()
    if not inputs:
        return True
    if page_type in {"login", "registration", "portal_entry"}:
        return True
    if page_type == "application_form":
        return False
    return _looks_like_auth_form(dom)


def build_entry_gate(options: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build the human checkpoint for an entry-path decision."""
    return {
        "gate_type": "GATEWAY_DECISION",
        "title": "How would you like to start?",
        "hindi_title": "Shuru kaise karein?",
        "description": (
            "This portal offers more than one way to start. FormPilot will not choose "
            "for you. Pick the path that matches your situation: create a new account, "
            "sign in to an existing account, or resume an application you already started."
        ),
        "why": "The page shows more than one explicit entry path.",
        "requires_explicit_choice": True,
        "no_default": True,
        "options": [
            {
                "id": option.get("id"),
                "element_id": option.get("element_id"),
                "text": option.get("text"),
                "type": option.get("type"),
                "mode": option.get("mode"),
                "href": option.get("href"),
                "source": option.get("source"),
            }
            for option in options
        ],
    }


def build_next_step_gate(options: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build the checkpoint for a signed-in page that links to the real form."""
    return {
        "gate_type": "GATEWAY_DECISION",
        "stage": "next_step",
        "title": "What would you like to do next?",
        "hindi_title": "Ab aage kya karna hai?",
        "description": (
            "You are signed in. This page is a dashboard, not the application form — "
            "it lists links that open the real application. FormPilot will not pick one "
            "for you. Choose the next step you want."
        ),
        "why": "The signed-in page lists more than one explicit next step.",
        "requires_explicit_choice": True,
        "no_default": True,
        "options": [
            {
                "id": option.get("id"),
                "element_id": option.get("element_id"),
                "text": option.get("text"),
                "type": option.get("type"),
                "mode": option.get("mode"),
                "href": option.get("href"),
                "source": option.get("source"),
                "description": f"Open: {option.get('text')}",
            }
            for option in options
        ],
    }


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def match_entry_response(
    response: Dict[str, Any],
    options: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Match a human/chat response to exactly one option.

    Returns ``None`` when the response is missing or ambiguous.  There is no
    ``options[0]`` fallback anywhere in this path.
    """
    if not response or not options:
        return None
    selected_element = str(response.get("element_id") or "")
    selected_id = str(response.get("id") or "")
    selected_mode = normalize_mode(response.get("mode") or response.get("type"))
    selected_text = _norm(response.get("text") or response.get("label"))
    selected_href = _norm(response.get("href"))

    if selected_element:
        matches = [option for option in options if str(option.get("element_id") or "") == selected_element]
        return matches[0] if len(matches) == 1 else None
    if selected_id:
        matches = [option for option in options if str(option.get("id") or "") == selected_id]
        return matches[0] if len(matches) == 1 else None
    if selected_mode:
        matches = [option for option in options if option.get("mode") == selected_mode]
        return matches[0] if len(matches) == 1 else None
    if selected_text:
        matches = [option for option in options if _norm(option.get("text")) == selected_text]
        return matches[0] if len(matches) == 1 else None
    if selected_href:
        matches = [option for option in options if _norm(option.get("href")) == selected_href]
        return matches[0] if len(matches) == 1 else None
    return None


def classify_login_method(text: str, value: str = "") -> Optional[str]:
    haystack = f"{text or ''} {value or ''}".lower()
    if not haystack.strip():
        return None
    if "digilocker" in haystack:
        return DIGILOCKER
    has_otp = bool(_OTP_TEXT_RE.search(haystack))
    has_password = "password" in haystack
    if has_otp and "aadhaar" in haystack:
        return AADHAAR_OTP
    if has_otp and ("mobile" in haystack or "phone" in haystack or "contact" in haystack):
        return MOBILE_OTP
    if has_otp:
        return MOBILE_OTP
    if "urn" in haystack and has_password:
        return URN_PASSWORD
    if ("email" in haystack or "e-mail" in haystack) and has_password:
        return EMAIL_PASSWORD
    if has_password:
        return PASSWORD
    if "aadhaar" in haystack:
        return AADHAAR_OTP
    return None


def login_method_options(dom: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Find a login-method selector and its explicit options."""
    inputs = dom.get("inputs") or []
    for item in inputs:
        if str(item.get("tagName") or "").lower() != "select":
            continue
        field_hint = " ".join(
            str(item.get(key) or "") for key in ("label", "name", "id")
        ).lower()
        options: List[Dict[str, Any]] = []
        for option in item.get("options") or []:
            method = classify_login_method(
                str(option.get("text") or ""),
                str(option.get("value") or ""),
            )
            if not method:
                continue
            options.append(
                {
                    "value": str(option.get("value") or ""),
                    "text": str(option.get("text") or ""),
                    "method": method,
                    "label": LOGIN_METHOD_LABELS.get(method, method.replace("_", " ").title()),
                    "element_id": item.get("element_id"),
                }
            )
        if options and (
            len({option["method"] for option in options}) >= 2
            or re.search(r"login|method|type", field_hint)
        ):
            return {"field": item, "options": options}
    return None


def build_login_method_gate(selection: Dict[str, Any]) -> Dict[str, Any]:
    field = selection.get("field") or {}
    return {
        "gate_type": "LOGIN_METHOD",
        "title": "How do you sign in?",
        "hindi_title": "Aap kaise sign in karna chahte hain?",
        "description": (
            "This login form supports more than one sign-in method. FormPilot will not "
            "pick one for you because the right method depends on the account you hold."
        ),
        "why": "The login form has a method selector with multiple valid choices.",
        "requires_explicit_choice": True,
        "no_default": True,
        "field_key": "login_method",
        "field_label": str(field.get("label") or "Login method"),
        "options": [
            {
                "value": option.get("value"),
                "text": option.get("text"),
                "method": option.get("method"),
                "label": option.get("label"),
            }
            for option in selection.get("options") or []
        ],
    }


def match_login_method_response(
    response: Dict[str, Any],
    selection: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    options = selection.get("options") or []
    if not response or not options:
        return None
    value = str(response.get("value") or "")
    method = str(response.get("method") or "")
    text = _norm(response.get("text") or response.get("label"))
    if value:
        matches = [option for option in options if str(option.get("value") or "") == value]
        return matches[0] if len(matches) == 1 else None
    if method:
        matches = [option for option in options if str(option.get("method") or "") == method]
        return matches[0] if len(matches) == 1 else None
    if text:
        matches = [
            option
            for option in options
            if _norm(option.get("text")) == text or _norm(option.get("label")) == text
        ]
        return matches[0] if len(matches) == 1 else None
    return None


_IDENTIFIER_RULES: Tuple[Tuple[str, re.Pattern[str]], ...] = (
    ("aadhaar_number", re.compile(r"aadhaar|aadhar", re.IGNORECASE)),
    ("registration_id", re.compile(r"registration|reg\s*(?:id|no|number)|\burn\b|application\s*(?:id|no|number)", re.IGNORECASE)),
    ("mobile", re.compile(r"mobile|phone|contact\s*(?:no|number)?", re.IGNORECASE)),
    ("email", re.compile(r"e-?mail|mail\s*(?:id|address)?", re.IGNORECASE)),
    ("username", re.compile(r"user\s*(?:id|name)|login\s*id", re.IGNORECASE)),
)


def classify_identifier(item: Dict[str, Any]) -> Optional[str]:
    field_type = str(item.get("type") or "text").lower()
    if field_type not in {"text", "email", "tel", "number", "search"}:
        return None
    haystack = " ".join(
        str(item.get(key) or "") for key in ("label", "name", "id", "placeholder")
    )
    if _OTP_TEXT_RE.search(haystack) or _CAPTCHA_TEXT_RE.search(haystack):
        return None
    if re.search(r"password|search|filter|otp|captcha", haystack, re.IGNORECASE):
        return None
    for key, pattern in _IDENTIFIER_RULES:
        if pattern.search(haystack):
            return key
    return None


def identifier_options(dom: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Find multiple visible account identifiers on a login form."""
    found: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for item in dom.get("inputs") or []:
        key = classify_identifier(item)
        if not key or key in seen:
            continue
        seen.add(key)
        found.append(
            {
                "key": key,
                "label": str(item.get("label") or key.replace("_", " ").title()),
                "element_id": item.get("element_id"),
                "field": item,
            }
        )
    if len(found) < 2:
        return None
    return {"options": found}


def build_identifier_gate(selection: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "gate_type": "ACCOUNT_IDENTIFIER",
        "title": "Which detail identifies your account?",
        "hindi_title": "Aapka account kis detail se khulta hai?",
        "description": (
            "This login form shows more than one account identifier. FormPilot will not "
            "guess which one belongs to you. Choose the identifier your account uses."
        ),
        "why": "Multiple visible identifier fields could open different accounts.",
        "requires_explicit_choice": True,
        "no_default": True,
        "options": [
            {
                "value": option.get("key"),
                "text": option.get("label"),
                "key": option.get("key"),
                "element_id": option.get("element_id"),
            }
            for option in selection.get("options") or []
        ],
    }


def match_identifier_response(
    response: Dict[str, Any],
    selection: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    options = selection.get("options") or []
    if not response or not options:
        return None
    key = str(response.get("value") or response.get("key") or "")
    element_id = str(response.get("element_id") or "")
    if key:
        matches = [option for option in options if option.get("key") == key]
        return matches[0] if len(matches) == 1 else None
    if element_id:
        matches = [option for option in options if str(option.get("element_id") or "") == element_id]
        return matches[0] if len(matches) == 1 else None
    return None


def entry_summary(options: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Safe public summary for state/events; no page values are included."""
    return [
        {
            "type": option.get("type"),
            "mode": option.get("mode"),
            "text": option.get("text"),
            "element_id": option.get("element_id"),
            "href": option.get("href"),
            "source": option.get("source"),
            "alternate_count": option.get("alternate_count", 0),
        }
        for option in options
    ]
