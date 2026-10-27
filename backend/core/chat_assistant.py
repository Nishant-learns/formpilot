"""Candidate-facing chat assistant for FormPilot.

The assistant answers common application questions, updates saved details when
the candidate asks for a correction, and can apply that correction to the form
that is currently open.  Replies are written for candidates: no internal
architecture, automation tricks, or implementation details are exposed.
"""

from __future__ import annotations

import datetime
import re
from typing import Any, Dict, List, Optional, Tuple

from . import decision_policy, field_registry
from .dom_scanner import DOMScanner
from .tinyfish_client import TinyFishClient, TinyFishError
from .vault import VaultManager


class FormPilotChatAssistant:
    """Conversational helper for candidates using the FormPilot cockpit."""

    sender = "FormPilot"

    def __init__(self, orchestrator=None, vault_mgr=None, tinyfish_client=None):
        self.orchestrator = orchestrator
        self.vault_mgr = vault_mgr or VaultManager.get_instance()
        self.tinyfish_client = tinyfish_client or TinyFishClient()
        self.chat_history: List[Dict[str, str]] = []

    # ------------------------------------------------------------------ entry

    async def handle_message(self, user_msg: str) -> Dict[str, Any]:
        text = (user_msg or "").strip()
        timestamp = datetime.datetime.now().strftime("%H:%M")
        self.chat_history.append({"sender": "Candidate", "text": text, "time": timestamp})

        if not text:
            return self._reply(
                "Please type a question or tell me which detail you want to change.",
                "CONVERSATION",
                timestamp,
            )

        edit = await self._try_field_edit(text)
        if edit:
            return self._remember(edit, timestamp)

        entry = await self._try_entry_action(text)
        if entry:
            return self._remember(entry, timestamp)

        workflow = await self._try_workflow_action(text)
        if workflow:
            return self._remember(workflow, timestamp)

        faq = self._try_faq(text)
        if faq:
            return self._remember(faq, timestamp)

        search = await self._try_live_search(text)
        if search:
            return self._remember(search, timestamp)

        name = self._first_name()
        return self._remember(
            {
                "reply": (
                    f"Hi {name}, I can help with this form. You can ask me to update a saved "
                    "detail (for example, \"change my father's name to Rajesh Sharma\"), "
                    "explain a document requirement, pause the application, or show your "
                    "current status."
                ),
                "action_taken": "CONVERSATION",
                "timestamp": timestamp,
            },
            timestamp,
        )

    # -------------------------------------------------------------- utilities

    def _reply(self, text: str, action: str, timestamp: Optional[str] = None) -> Dict[str, Any]:
        return {
            "reply": text,
            "action_taken": action,
            "field_updated": None,
            "new_value": None,
            "timestamp": timestamp or datetime.datetime.now().strftime("%H:%M"),
        }

    def _remember(self, result: Dict[str, Any], timestamp: str) -> Dict[str, Any]:
        result.setdefault("timestamp", timestamp)
        self.chat_history.append(
            {
                "sender": self.sender,
                "text": result.get("reply", ""),
                "time": result.get("timestamp", timestamp),
            }
        )
        return result

    def _first_name(self) -> str:
        full_name = (getattr(self.vault_mgr.vault, "full_name", "") or "").strip()
        return full_name.split()[0] if full_name else "there"

    @staticmethod
    def _portable_value(key: str, value: str) -> str:
        """Keep dates and categories in the format portals normally expect."""
        value = re.sub(r"\s+", " ", value).strip(" .,;:-")
        if key == "dob":
            return FormPilotChatAssistant._normalise_dob(value)
        if key == "category":
            upper = value.upper().replace("_", "-").replace(" ", "-")
            if upper in {"OBCNCL", "OBC-NCL"}:
                return "OBC-NCL"
            if upper in {"GENERAL", "GEN"}:
                return "UR"
            return upper
        if key == "aadhaar_number":
            digits = re.sub(r"\D", "", value)
            return digits if len(digits) == 12 else value
        return value

    @staticmethod
    def _normalise_dob(raw: str) -> str:
        parts = re.split(r"[/.-]", raw.strip())
        if len(parts) == 3 and all(part.isdigit() for part in parts):
            if len(parts[0]) == 4:
                return f"{parts[0]}-{parts[1].zfill(2)}-{parts[2].zfill(2)}"
            return f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
        return raw.strip()

    @staticmethod
    def _mask_if_needed(key: str, value: str) -> str:
        spec = field_registry.spec_for(key)
        if spec and spec.sensitive:
            return field_registry.mask_value(key, value)
        return value

    # ------------------------------------------------------------- field edits

    _EDIT_WORDS = (
        r"change|update|set|edit|modify|correct|badal(?:o|do|na)?|"
        r"karo|kardo|kar\s*do|rakho|likho|dal(?:o|do)"
    )

    _FIELD_TERMS: List[Tuple[str, str]] = [
        ("verify_full_name", r"(?:verify\s+(?:candidate\s+)?(?:full\s+)?name|confirm\s+(?:candidate\s+)?name)"),
        ("father_name", r"(?:father(?:'s)?\s*name|father|pitaji|papa)"),
        ("mother_name", r"(?:mother(?:'s)?\s*name|mother|mataji|mummy)"),
        ("full_name", r"(?:candidate\s+(?:full\s+)?name|full\s+name|my\s+name|apna\s+naam|naam)"),
        ("dob", r"(?:date\s+of\s+birth|dob|janam\s*tithi)"),
        ("mobile", r"(?:mobile(?:\s*(?:no|number))?|phone(?:\s*(?:no|number))?|contact(?:\s*(?:no|number))?)"),
        ("email", r"(?:e-?mail(?:\s*(?:id|address))?|mail)"),
        ("category", r"(?:social\s+category|category|caste|jaati|community)"),
        ("aadhaar_number", r"(?:aadhaar|aadhar)(?:\s*(?:no|number))?"),
        ("apaar_id", r"(?:apaar)(?:\s*id)?"),
        ("matric_roll_number", r"(?:(?:10th|matric|high\s*school)\s*(?:roll|roll\s*no|roll\s*number))"),
        ("intermediate_roll_number", r"(?:(?:12th|intermediate|inter)\s*(?:roll|roll\s*no|roll\s*number))"),
        ("graduation_roll_number", r"(?:(?:graduation|grad|college)\s*(?:roll|roll\s*no|roll\s*number))"),
        ("pincode", r"(?:pin\s*code|pincode|postal\s*code)"),
        ("address_line_1", r"(?:address|permanent\s+address)"),
        ("registration_id", r"(?:registration\s*(?:id|no|number)|registration|reg\s*(?:id|no|number)|application\s*(?:id|no|number))"),
        ("gender", r"(?:gender|sex)"),
        ("nationality", r"(?:nationality|citizenship)"),
        ("religion", r"(?:religion|dharm)"),
        ("marital_status", r"(?:marital\s+status|married)"),
        ("domicile_state", r"(?:domicile|home\s+state)"),
        ("district", r"(?:district|zila)"),
        ("state", r"(?:state|rajya)"),
        ("village_town_city", r"(?:village|town|city|shehar)"),
        ("matric_board", r"(?:10th|matric)\s*(?:board)"),
        ("matric_passing_year", r"(?:10th|matric)\s*(?:passing\s*year|year)"),
        ("matric_percentage", r"(?:10th|matric)\s*(?:percentage|percent|marks)"),
        ("intermediate_board", r"(?:12th|intermediate|inter)\s*(?:board)"),
        ("intermediate_passing_year", r"(?:12th|intermediate|inter)\s*(?:passing\s*year|year)"),
        ("intermediate_percentage", r"(?:12th|intermediate|inter)\s*(?:percentage|percent|marks)"),
    ]

    _VALUE_PATTERNS: Dict[str, str] = {
        "full_name": r"[A-Za-z][A-Za-z.'\- ]{2,59}",
        "verify_full_name": r"[A-Za-z][A-Za-z.'\- ]{2,59}",
        "father_name": r"[A-Za-z][A-Za-z.'\- ]{2,59}",
        "mother_name": r"[A-Za-z][A-Za-z.'\- ]{2,59}",
        "dob": r"\d{1,4}[/.-]\d{1,2}[/.-]\d{1,4}",
        "mobile": r"(?:\+91[\s-]?)?[6-9]\d{9}",
        "email": r"[A-Za-z0-9_.+\-]+@[A-Za-z0-9\-]+\.[A-Za-z0-9.\-]+",
        "category": r"(?:OBC[\s-]?NCL|OBC|General|GEN|UR|EWS|SC|ST)",
        "aadhaar_number": r"\d{4}\s?\d{4}\s?\d{4}",
        "apaar_id": r"[A-Za-z0-9\-]{8,24}",
        "matric_roll_number": r"\d{6,12}",
        "intermediate_roll_number": r"\d{6,12}",
        "graduation_roll_number": r"[A-Za-z0-9\-/]{4,24}",
        "pincode": r"\d{6}",
        "address_line_1": r".{5,160}",
        "registration_id": r"[A-Za-z0-9][A-Za-z0-9\-/]{3,29}",
        "gender": r"(?:Male|Female|Other|Transgender)",
        "nationality": r"[A-Za-z ]{3,30}",
        "religion": r"[A-Za-z ]{3,30}",
        "marital_status": r"(?:Unmarried|Married|Divorced|Widowed|Single)",
        "domicile_state": r"[A-Za-z ]{3,30}",
        "district": r"[A-Za-z .'\-]{2,40}",
        "state": r"[A-Za-z .'\-]{2,40}",
        "village_town_city": r"[A-Za-z .'\-]{2,40}",
        "matric_board": r"[A-Za-z0-9 .,'\-]{2,60}",
        "matric_passing_year": r"(?:19|20)\d{2}",
        "matric_percentage": r"\d{1,3}(?:\.\d{1,2})?\s*%?",
        "intermediate_board": r"[A-Za-z0-9 .,'\-]{2,60}",
        "intermediate_passing_year": r"(?:19|20)\d{2}",
        "intermediate_percentage": r"\d{1,3}(?:\.\d{1,2})?\s*%?",
    }

    _COMMAND_WORDS = (
        r"karo|kardo|kar\s*do|kar\s*dena|kar|karke|kar\s*ke|badlo|badal\s*do|"
        r"rakho|rakh\s*do|please|plz|sir|madam|bhaiya|ji|thanks|thank\s*you"
    )

    @classmethod
    def _clean_value(cls, value: str, key: str) -> str:
        value = value.strip(" \t\r\n.,;:-'\"")
        value = re.sub(rf"\s+(?:{cls._COMMAND_WORDS})\b.*$", "", value, flags=re.IGNORECASE)
        value = re.sub(rf"^(?:{cls._COMMAND_WORDS})\b\s*", "", value, flags=re.IGNORECASE)
        value = re.sub(r"\s+", " ", value).strip(" .,;:-")
        if not value or re.fullmatch(rf"(?:{cls._COMMAND_WORDS})", value, flags=re.IGNORECASE):
            return ""
        return value

    @classmethod
    def _extract_after_field(cls, text: str, field_match: re.Match, key: str) -> str:
        tail = text[field_match.end() : field_match.end() + 200]
        tail = re.sub(r"^[\s,;:'\"\-]+", "", tail)
        connector = r"(?:ko|ka|ki|ke|mein|me|to|as|is|equals?|=|:)"
        for _ in range(4):
            cleaned = re.sub(rf"^(?:{connector})\b[\s,;:'\"\-]*", "", tail, flags=re.IGNORECASE)
            cleaned = re.sub(
                rf"^(?:please\s+)?(?:{cls._EDIT_WORDS})\b[\s,;:'\"\-]*",
                "",
                cleaned,
                flags=re.IGNORECASE,
            )
            if cleaned == tail:
                break
            tail = cleaned

        pattern = cls._VALUE_PATTERNS.get(key)
        if not pattern:
            return ""
        match = re.search(pattern, tail, re.IGNORECASE)
        if not match:
            return ""
        return cls._clean_value(match.group(0), key)

    async def _try_field_edit(self, text: str) -> Optional[Dict[str, Any]]:
        text_lower = text.lower()
        has_edit_word = bool(re.search(rf"\b(?:{self._EDIT_WORDS})\b", text_lower))
        has_assignment = bool(re.search(r"(?:=|:)", text))
        if not has_edit_word and not has_assignment:
            return None

        for key, term in self._FIELD_TERMS:
            field_match = re.search(rf"\b(?:{term})\b", text, re.IGNORECASE)
            if not field_match:
                continue

            value = self._extract_after_field(text, field_match, key)
            if not value:
                continue

            value = self._portable_value(key, value)
            if key in {"full_name", "father_name", "mother_name", "email"} and len(value) < 2:
                continue
            if key == "email" and "@" not in value:
                continue
            if key == "mobile" and len(re.sub(r"\D", "", value)) < 10:
                continue

            try:
                self.vault_mgr.set_semantic_field(key, value)
                self._sync_confirmation_field(key, value)
            except Exception:
                return {
                    "reply": "I couldn't save that change. Please try again in a moment.",
                    "action_taken": "UPDATE_FAILED",
                    "field_updated": None,
                    "new_value": None,
                    "timestamp": datetime.datetime.now().strftime("%H:%M"),
                }

            updated_on_form = await self._update_open_form(key, value)
            spec = field_registry.spec_for(key)
            label = spec.label if spec else key.replace("_", " ").title()
            display_value = self._mask_if_needed(key, value)
            shown_value = f"**{value}**" if display_value == value else display_value

            reply = f"Done — I've updated **{label}** to {shown_value} in your saved details."
            if updated_on_form:
                reply += " The open form has also been updated. Please check the field before continuing."
            elif self.orchestrator and getattr(self.orchestrator, "page", None):
                reply += " The form is open, but I couldn't find that field on the current page. You can edit it directly if needed."
            else:
                reply += " It will be used the next time this detail is filled."

            return {
                "reply": reply,
                "action_taken": "FIELD_UPDATED",
                "field_updated": label,
                "new_value": display_value,
                "updated_on_form": updated_on_form,
                "timestamp": datetime.datetime.now().strftime("%H:%M"),
            }

        return None

    def _sync_confirmation_field(self, key: str, value: str) -> None:
        """Keep common confirmation fields in step with the primary value."""
        confirmation = {
            "full_name": "verify_full_name",
            "father_name": "verify_father_name",
            "mother_name": "verify_mother_name",
            "email": "confirm_email",
        }.get(key)
        if not confirmation:
            return
        try:
            self.vault_mgr.set_semantic_field(confirmation, value)
        except Exception:
            pass

    async def _update_open_form(self, key: str, value: str) -> bool:
        """Apply an edit to the currently open page, when that field is present."""
        page = getattr(self.orchestrator, "page", None) if self.orchestrator else None
        if not page:
            return False

        targets = {key}
        confirmation = {
            "full_name": "verify_full_name",
            "father_name": "verify_father_name",
            "mother_name": "verify_mother_name",
            "email": "confirm_email",
        }.get(key)
        if confirmation:
            targets.add(confirmation)

        updated = False
        try:
            dom = await self.orchestrator._scan_dom()
            for item in dom.get("inputs") or []:
                semantic_key, _ = DOMScanner.classify_field(item)
                if semantic_key not in targets:
                    continue
                try:
                    result = await page.evaluate(DOMScanner.INJECTION_JS, [item, value])
                    if isinstance(result, dict) and result.get("success"):
                        updated = True
                except Exception:
                    continue
        except Exception:
            return False

        if updated:
            try:
                await self.orchestrator.emit_event(
                    "ACT",
                    "A detail was updated at your request. Please review the field.",
                    "Aapke kehne par ek detail update ki gayi hai. Field check kar lein.",
                    force_screenshot=True,
                )
            except Exception:
                pass
        return updated

    # ----------------------------------------------------------- entry + login

    _REGISTER_INTENT_RE = re.compile(
        r"\b(?:register|registration|sign\s*up|signup|create\s+(?:an?\s+)?account|"
        r"new\s+account|new\s+user|first\s*time|account\s+creation|"
        r"naya\s+account|nayi\s+registration)\b",
        re.IGNORECASE,
    )
    _LOGIN_INTENT_RE = re.compile(
        r"\b(?:log\s*in|login|sign\s*in|signin|existing\s+account|"
        r"already\s+registered|returning\s+candidate|purana\s+account)\b",
        re.IGNORECASE,
    )
    _RESUME_INTENT_RE = re.compile(
        r"\b(?:resume|continue)\s+(?:my\s+)?(?:application|registration|form)\b|"
        r"\balready\s+started\b|\bsaved\s+application\b|"
        r"\btrack\s+(?:my\s+)?application\b|\bapplication\s+status\b",
        re.IGNORECASE,
    )

    @classmethod
    def _entry_mode_from_text(cls, text: str) -> Optional[str]:
        register = bool(cls._REGISTER_INTENT_RE.search(text))
        login = bool(cls._LOGIN_INTENT_RE.search(text))
        resume = bool(cls._RESUME_INTENT_RE.search(text))
        if resume and not register and not login:
            return "resume"
        if register and login:
            return None
        if register:
            return "register"
        if login:
            return "login"
        return None

    @staticmethod
    def _match_gate_option(text: str, options: List[Dict[str, Any]], keys: Tuple[str, ...]) -> Optional[Dict[str, Any]]:
        wanted = re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()
        if not wanted:
            return None
        for option in options:
            for key in keys:
                value = re.sub(
                    r"[^a-z0-9]+", " ", str(option.get(key) or "").lower()
                ).strip()
                if value and (value == wanted or value in wanted or wanted in value):
                    return option
        return None

    def _entry_help(self, gate: Dict[str, Any]) -> Dict[str, Any]:
        options = gate.get("options") or []
        if not options:
            return {
                "reply": (
                    "I need your explicit choice before opening an entry path. "
                    "Use the live browser to choose register, sign in or resume, then continue."
                ),
                "action_taken": "ENTRY_CHOICE_NEEDED",
            }
        lines = ["I need one explicit choice before opening a path:"]
        for option in options:
            mode = str(option.get("mode") or "").replace("_", " ").title()
            lines.append(f"• **{option.get('text')}**" + (f" — {mode}" if mode else ""))
        lines.append(
            "\nReply with **register**, **login** or **resume**, or use the checkpoint panel."
        )
        return {"reply": "\n".join(lines), "action_taken": "ENTRY_CHOICE_NEEDED"}

    def _login_help(self, gate: Dict[str, Any]) -> Dict[str, Any]:
        options = gate.get("options") or []
        lines = ["This login form supports more than one sign-in method. Which one is yours?"]
        for option in options:
            lines.append(f"• **{option.get('label') or option.get('text')}**")
        lines.append("\nTell me the method, for example \"mobile OTP\" or \"email password\".")
        return {"reply": "\n".join(lines), "action_taken": "LOGIN_METHOD_NEEDED"}

    def _identifier_help(self, gate: Dict[str, Any]) -> Dict[str, Any]:
        options = gate.get("options") or []
        lines = ["Which detail identifies your account on this login form?"]
        for option in options:
            lines.append(f"• **{option.get('text') or option.get('key')}**")
        lines.append("\nTell me the detail, for example \"mobile number\" or \"registration ID\".")
        return {"reply": "\n".join(lines), "action_taken": "ACCOUNT_IDENTIFIER_NEEDED"}

    async def _try_entry_action(self, text: str) -> Optional[Dict[str, Any]]:
        """Turn a chat sentence into a real entry/login decision.

        This runs before the generic workflow so phrases such as
        "I need to register first" cannot fall through to a greeting.
        """
        if not self.orchestrator:
            return None
        gate = getattr(self.orchestrator, "active_gate", None) or {}
        gate_type = str(gate.get("gate_type") or "")

        if gate_type == "GATEWAY_DECISION":
            options = gate.get("options") or []
            option_match = re.search(r"\boption\s*(\d+)\b", text, re.IGNORECASE)
            selected = None
            if option_match:
                index = int(option_match.group(1)) - 1
                if 0 <= index < len(options):
                    selected = options[index]
            if not selected:
                selected = self._match_gate_option(text, options, ("text", "mode", "type"))
            if not selected:
                mode = self._entry_mode_from_text(text)
                if mode:
                    selected = next(
                        (option for option in options if option.get("mode") == mode),
                        None,
                    )
            if not selected:
                return self._entry_help(gate)
            result = self.orchestrator.choose_entry_mode(
                str(selected.get("mode") or selected.get("type") or "")
            )
            if result.get("success"):
                return {
                    "reply": (
                        f"Done — I selected **{selected.get('text')}**. "
                        "The portal will open that path; review the next screen before any details are filled."
                    ),
                    "action_taken": "ENTRY_MODE_SELECTED",
                    "entry_mode": result.get("mode"),
                }
            return {
                "reply": result.get("message") or "I could not select that entry path.",
                "action_taken": "ENTRY_MODE_FAILED",
            }

        if gate_type == "LOGIN_METHOD":
            options = gate.get("options") or []
            selected = self._match_gate_option(
                text, options, ("method", "label", "text", "value")
            )
            method = str(selected.get("method") or "") if selected else decision_policy.classify_login_method(text)
            if not method:
                return self._login_help(gate)
            result = self.orchestrator.choose_login_method(method)
            if result.get("success"):
                label = (
                    selected.get("label")
                    if selected
                    else decision_policy.LOGIN_METHOD_LABELS.get(
                        method, method.replace("_", " ").title()
                    )
                )
                return {
                    "reply": f"Done — I selected **{label}** for this login.",
                    "action_taken": "LOGIN_METHOD_SELECTED",
                    "login_method": result.get("method"),
                }
            return {
                "reply": result.get("message") or "I could not select that sign-in method.",
                "action_taken": "LOGIN_METHOD_FAILED",
            }

        if gate_type == "ACCOUNT_IDENTIFIER":
            options = gate.get("options") or []
            selected = self._match_gate_option(text, options, ("key", "text", "value"))
            key = str(selected.get("key") or "") if selected else self._identifier_from_text(text)
            if not key:
                return self._identifier_help(gate)
            result = self.orchestrator.choose_account_identifier(key)
            if result.get("success"):
                label = selected.get("text") if selected else key.replace("_", " ").title()
                return {
                    "reply": f"Done — I will use **{label}** to identify the account.",
                    "action_taken": "ACCOUNT_IDENTIFIER_SELECTED",
                    "login_identifier": result.get("identifier"),
                }
            return {
                "reply": result.get("message") or "I could not select that account identifier.",
                "action_taken": "ACCOUNT_IDENTIFIER_FAILED",
            }

        mode = self._entry_mode_from_text(text)
        if not mode:
            return None
        result = self.orchestrator.choose_entry_mode(mode)
        if result.get("success"):
            return {
                "reply": (
                    f"Understood — {self._entry_phrase(mode)}. "
                    "I will apply that choice only when the portal actually shows that entry path; "
                    "I will not guess from the URL or history."
                ),
                "action_taken": "ENTRY_MODE_REQUESTED",
                "entry_mode": result.get("mode"),
            }
        return {
            "reply": result.get("message") or "I could not use that entry path.",
            "action_taken": "ENTRY_MODE_FAILED",
        }

    @staticmethod
    def _identifier_from_text(text: str) -> Optional[str]:
        lower = text.lower()
        if re.search(r"aadhaar|aadhar", lower):
            return "aadhaar_number"
        if re.search(r"registration|reg\s*(?:id|no|number)|\burn\b|application\s*(?:id|no|number)", lower):
            return "registration_id"
        if re.search(r"e-?mail|mail\s*(?:id|address)?", lower):
            return "email"
        if re.search(r"mobile|phone|contact\s*(?:no|number)?", lower):
            return "mobile"
        if re.search(r"user\s*(?:id|name)|login\s*id", lower):
            return "username"
        return None

    @staticmethod
    def _entry_phrase(mode: str) -> str:
        return {
            "register": "you need to create a new account first",
            "login": "you already have an account and want to sign in",
            "resume": "you want to resume an application you already started",
        }.get(mode, "that is the entry path you want")

    # --------------------------------------------------------------- workflow

    async def _try_workflow_action(self, text: str) -> Optional[Dict[str, Any]]:
        text_lower = text.lower()
        now = datetime.datetime.now().strftime("%H:%M")
        gate = (getattr(self.orchestrator, "active_gate", None) or {}) if self.orchestrator else {}
        gate_type = str(gate.get("gate_type") or "")

        if gate_type == "FILL_INCOMPLETE":
            if re.search(r"\b(recheck|retry|try\s+again|dobara|phir\s+se)\b", text_lower):
                self.orchestrator.submit_user_response({"action": "FILL_RECHECK"})
                return {
                    "reply": "Rechecking the form now. I will verify every field again before asking you to continue.",
                    "action_taken": "FILL_RECHECK",
                    "timestamp": now,
                }
            if re.search(r"\b(continue|proceed|aage|ignore|skip)\b", text_lower):
                self.orchestrator.submit_user_response({"action": "CONTINUE"})
                return {
                    "reply": (
                        "Continuing after your review. The fill check is recorded as incomplete, "
                        "so the form is not marked as fully filled."
                    ),
                    "action_taken": "FILL_CONTINUE",
                    "timestamp": now,
                }
            summary = (getattr(self.orchestrator, "fill_summary", None) or {})
            return {
                "reply": (
                    f"Some fields are not filled: {summary.get('verified', 0)} verified, "
                    f"{summary.get('failed', 0)} failed, {summary.get('skipped', 0)} skipped. "
                    "Say **recheck** to try again, or **continue** after reviewing the form yourself."
                ),
                "action_taken": "FILL_INCOMPLETE",
                "timestamp": now,
            }

        if re.search(r"\b(stop|cancel|band\s*karo|rok\s*do|exit)\b", text_lower):
            if self.orchestrator:
                try:
                    await self.orchestrator.stop()
                except Exception:
                    pass
            return {
                "reply": "The application has been stopped. Nothing was submitted or paid.",
                "action_taken": "STOPPED",
                "timestamp": now,
            }

        if re.search(r"\b(pause|rok\s*do|ruko|wait|thoda\s*ruk)\b", text_lower):
            if self.orchestrator:
                self.orchestrator.pause()
            return {
                "reply": "Paused. Take your time to review the details. Say \"resume\" when you're ready to continue.",
                "action_taken": "PAUSED",
                "timestamp": now,
            }

        if re.search(r"\b(continue|resume|aage\s*badho|chalo|shuru\s*karo|next)\b", text_lower):
            if self.orchestrator:
                self.orchestrator.resume()
                gate = getattr(self.orchestrator, "active_gate", None) or {}
                if gate.get("gate_type") == "SECTION_APPROVAL":
                    self.orchestrator.submit_user_response(
                        {"action": "SECTION_APPROVAL", "approved": True}
                    )
            return {
                "reply": "Resumed. I'll continue with the next step and stop again at the next review point.",
                "action_taken": "RESUMED",
                "timestamp": now,
            }

        if re.search(r"\b(status|progress|kya\s*chal\s*raha|kya\s*ho\s*raha|kitna\s*hua|screen\s*check)\b", text_lower):
            state = self.orchestrator.get_state() if self.orchestrator else {}
            section = state.get("current_section") or 1
            filled = len(state.get("filled_audit") or [])
            summary = state.get("fill_summary") or {}
            fill_status = str(summary.get("status") or "")
            gate = state.get("active_gate") or {}
            gate_title = gate.get("title") or "No review is pending"
            phase = state.get("state") or "READY"
            entry_mode = state.get("entry_mode") or "not chosen yet"

            if fill_status == "FILLED":
                fill_line = (
                    f"• Fields verified on this page: {summary.get('verified', 0)} "
                    f"of {summary.get('attempted', 0)}"
                )
            elif fill_status == "PARTIAL":
                fill_line = (
                    f"• Fields verified: {summary.get('verified', 0)} of "
                    f"{summary.get('attempted', 0)} — "
                    f"{summary.get('failed', 0)} failed, {summary.get('skipped', 0)} skipped"
                )
            elif fill_status == "FAILED":
                fill_line = (
                    f"• Fill failed: 0 of {summary.get('attempted', 0)} attempted fields verified"
                )
            elif fill_status == "NO_FIELDS":
                fill_line = "• No fillable fields were found on the current page"
            else:
                fill_line = "• Fill has not been verified yet"

            gate_lines = ""
            options = gate.get("options") or []
            if options:
                gate_lines = "\n• Choices open: " + ", ".join(
                    str(option.get("text") or option.get("label") or option.get("key") or "")
                    for option in options[:6]
                )

            return {
                "reply": (
                    f"**Current status**\n"
                    f"• Stage: {phase.replace('_', ' ').title()}\n"
                    f"• Entry path: {entry_mode}\n"
                    f"• Section: {section}\n"
                    f"{fill_line}\n"
                    f"• Details verified in the saved audit: {filled}\n"
                    f"• Waiting for you: {gate_title}{gate_lines}\n\n"
                    "FormPilot stops before payment or final submission and never submits an application on your behalf."
                ),
                "action_taken": "STATUS_REPORT",
                "timestamp": now,
            }

        return None

    # -------------------------------------------------------------------- FAQ

    def _try_faq(self, text: str) -> Optional[Dict[str, Any]]:
        text_lower = text.lower()
        now = datetime.datetime.now().strftime("%H:%M")

        if re.search(r"\b(who\s+are\s+you|what\s+is\s+formpilot|are\s+you\s+(a\s+)?government|official\s+(website|portal))\b", text_lower):
            return {
                "reply": (
                    "FormPilot is an independent application assistant. It is not a government "
                    "website and it does not issue certificates or accept payments. It helps you "
                    "fill an official portal accurately, then hands control back to you."
                ),
                "action_taken": "FAQ_ANSWER",
                "timestamp": now,
            }

        if re.search(r"\b(otp|one[- ]time\s*password|verification\s*code)\b", text_lower):
            return {
                "reply": (
                    "OTP codes are used only for the current step. FormPilot does not save them "
                    "or send them anywhere else. You will always enter the code yourself."
                ),
                "action_taken": "FAQ_ANSWER",
                "timestamp": now,
            }

        if re.search(r"\b(fee|fees|kitne\s*paise|charge|paisa|cost|payment)\b", text_lower):
            return {
                "reply": (
                    "The fee depends on the portal and your category. The official fee page shows "
                    "the exact amount before payment. FormPilot stops at that page — you review the "
                    "details and complete any payment yourself."
                ),
                "action_taken": "FAQ_ANSWER",
                "timestamp": now,
            }

        if re.search(r"\b(photo|photograph|signature|sign|size|dimension|pixel|kb)\b", text_lower):
            return {
                "reply": (
                    "**Common document sizes**\n"
                    "• Photograph: recent passport-style JPEG, usually 20–50 KB and about 350×350 px.\n"
                    "• Signature: JPEG, usually 10–20 KB and about 140×60 px, on a plain background.\n\n"
                    "These are common ranges, not a guarantee. Always follow the exact specifications "
                    "shown on the portal you are using."
                ),
                "action_taken": "FAQ_ANSWER",
                "timestamp": now,
            }

        if re.search(r"\b(obc|ncl|caste|category|reservation|certificate|praman\s*patra|ews)\b", text_lower):
            return {
                "reply": (
                    "**OBC-NCL / EWS certificates**\n"
                    "Many public recruitment forms ask for an OBC Non-Creamy Layer certificate for "
                    "the current financial year. It is usually issued by the SDM, Tehsildar, or "
                    "District Magistrate. Check the portal's notification for the exact validity "
                    "dates before you apply."
                ),
                "action_taken": "FAQ_ANSWER",
                "timestamp": now,
            }

        if re.search(r"\b(apaar|digilocker|abc\s*id|student\s*id)\b", text_lower):
            return {
                "reply": (
                    "**APAAR / DigiLocker**\n"
                    "APAAR is a 12-digit student ID linked to your academic records. DigiLocker "
                    "stores verified digital documents. If a form asks for either, enter the ID "
                    "exactly as shown in your account and keep the source document ready for "
                    "verification."
                ),
                "action_taken": "FAQ_ANSWER",
                "timestamp": now,
            }

        if re.search(r"\b(document|documents|kagaz|kya\s*chahiye|checklist)\b", text_lower):
            return {
                "reply": (
                    "**Documents to keep ready**\n"
                    "1. Matric / 10th marksheet and certificate\n"
                    "2. Aadhaar or another accepted photo ID\n"
                    "3. Category certificate, if applicable\n"
                    "4. Domicile certificate, if the portal asks for it\n"
                    "5. Passport photograph and signature in the required size\n\n"
                    "The official portal always has the final checklist. Upload only documents "
                    "that belong to you and match your details."
                ),
                "action_taken": "FAQ_ANSWER",
                "timestamp": now,
            }

        return None

    # ----------------------------------------------------------------- search

    async def _try_live_search(self, text: str) -> Optional[Dict[str, Any]]:
        text_lower = text.lower()
        if not re.search(
            r"\b(exam\s*date|last\s*date|kab\s*(?:aayega|hoga|hai)|syllabus|notification|"
            r"vacancy|cut\s*off|result|admit\s*card|answer\s*key|news)\b",
            text_lower,
        ):
            return None

        now = datetime.datetime.now().strftime("%H:%M")
        try:
            results = await self.tinyfish_client.search(text, location="IN", limit=4)
        except TinyFishError:
            return {
                "reply": (
                    "I couldn't reach live web search just now. Please check the official portal "
                    "directly, or try again in a moment."
                ),
                "action_taken": "SEARCH_UNAVAILABLE",
                "timestamp": now,
            }

        if not results:
            return {
                "reply": (
                    "I didn't find a reliable live result for that. Try a more specific query, "
                    "or check the official portal's notification page."
                ),
                "action_taken": "SEARCH_EMPTY",
                "timestamp": now,
            }

        lines = ["**Live web results**"]
        for item in results[:3]:
            title = (item.get("title") or "Untitled result").strip()
            url = (item.get("url") or "").strip()
            snippet = re.sub(r"\s+", " ", (item.get("snippet") or item.get("description") or "")).strip()
            if snippet:
                snippet = snippet[:220].rstrip() + ("…" if len(snippet) > 220 else "")
            if url:
                lines.append(f"• [{title}]({url})\n  {snippet}")
            else:
                lines.append(f"• **{title}**\n  {snippet}")

        lines.append(
            "\nThese are search results, not an official confirmation. Verify dates and "
            "eligibility on the official portal before acting."
        )
        top_url = (results[0].get("url") or "").strip()
        return {
            "reply": "\n".join(lines),
            "action_taken": "LIVE_SEARCH",
            "source_url": top_url,
            "timestamp": now,
        }
