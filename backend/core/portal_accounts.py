"""Portal account memory.

"Have you registered on this portal before?" is a fact about a portal, not
about the candidate's global profile.  It is stored per ``(domain,
identifier_type, identifier_value)`` with a domain-level summary, so FormPilot
can remember an in-progress application without guessing which identifier it
belongs to.

Two rules:

* **Read-only inspection first.**  When the answer is unknown, the operator may
  look at the visible login/recovery options.  It never submits credentials,
  requests an OTP or resets anything to discover whether an account exists.
* **The human confirms.**  A record is only ``confirmed_by_human`` when the
  candidate said so or chose the matching path.  Unknown stays unknown.
"""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .perception import Perception
from .vault_crypto import VaultCipher, VaultCryptoError, cipher_from_env, decode_envelope


ACCOUNT_EXISTS = {"yes", "no", "unknown"}
REGISTRATION_STATUS = {"not_started", "in_progress", "submitted", "unknown"}
LOGIN_METHODS = {
    "mobile_otp",
    "urn_password",
    "email_otp",
    "aadhaar_otp",
    "password",
    "unknown",
}
IDENTIFIER_TYPES = {"mobile", "email", "urn", "aadhaar", "registration_id", "unknown"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_path() -> Path:
    data_dir = Path(
        os.getenv("FORMPILOT_DATA_DIR", Path(__file__).resolve().parents[2] / "data")
    )
    return data_dir / "portal_accounts.json"


def _domain(value: str) -> str:
    return str(value or "").strip().lower()


def _key(domain: str, identifier_type: str, identifier_value: str) -> str:
    return "portal:{domain}:{kind}:{value}".format(
        domain=_domain(domain),
        kind=identifier_type or "unknown",
        value=identifier_value or "",
    )


class PortalAccount(BaseModel):
    account_id: str = ""
    domain: str = ""
    identifier_type: str = "unknown"
    identifier_value: str = ""
    account_exists: str = "unknown"
    identifiers_seen: List[str] = Field(default_factory=list)
    login_method: str = "unknown"
    registration_status: str = "unknown"
    last_known_step: str = ""
    last_path_choice: str = ""
    confirmed_by_human_at: Optional[str] = None
    updated_at: str = ""

    @property
    def key(self) -> str:
        return _key(self.domain, self.identifier_type, self.identifier_value)

    def public(self, *, mask: bool = True) -> Dict[str, Any]:
        data = self.model_dump()
        if mask and data.get("identifier_value"):
            value = str(data["identifier_value"])
            data["identifier_value"] = (
                value if len(value) <= 4 else "*" * (len(value) - 4) + value[-4:]
            )
        return data


class LoginInspection(BaseModel):
    """What the visible page offers, without touching it."""

    domain: str = ""
    login_methods: List[str] = Field(default_factory=list)
    recovery_paths: List[str] = Field(default_factory=list)
    has_otp: bool = False
    has_password: bool = False
    hints: List[str] = Field(default_factory=list)
    read_only: bool = True
    inspected_at: str = ""


class PortalAccountStore:
    _instance: Optional["PortalAccountStore"] = None
    _instance_path: Optional[str] = None

    def __init__(self, file_path: Optional[str] = None, *, cipher: Optional[VaultCipher] = None):
        self.file_path = Path(file_path) if file_path else _default_path()
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self._cipher = cipher if cipher is not None else cipher_from_env()
        self._accounts: List[PortalAccount] = []
        self.load()

    @classmethod
    def get_instance(cls) -> "PortalAccountStore":
        path = str(_default_path())
        if cls._instance is None or cls._instance_path != path:
            cls._instance = PortalAccountStore(path)
            cls._instance_path = path
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        cls._instance = None
        cls._instance_path = None

    # ------------------------------------------------------------------ storage

    def load(self) -> List[PortalAccount]:
        self._accounts = []
        if not self.file_path.exists():
            return self._accounts
        try:
            raw = self.file_path.read_text(encoding="utf-8")
            is_encrypted, payload = decode_envelope(raw)
            if is_encrypted:
                if not self._cipher:
                    raise VaultCryptoError(
                        "Portal accounts are encrypted but FORMPILOT_VAULT_KEY is not set."
                    )
                raw = self._cipher.decrypt_bytes(payload)  # type: ignore[arg-type]
            data = json.loads(raw)
        except VaultCryptoError:
            raise
        except Exception as exc:  # pragma: no cover - corrupt file is rare
            print(f"[PortalAccountStore] Could not read accounts, starting empty: {exc}")
            return self._accounts
        items = data.get("accounts") if isinstance(data, dict) else data
        for item in items or []:
            if not isinstance(item, dict):
                continue
            try:
                self._accounts.append(PortalAccount(**item))
            except Exception:
                continue
        return self._accounts

    def save(self) -> None:
        payload = {
            "version": 1,
            "updated_at": _now(),
            "accounts": [account.model_dump() for account in self._accounts],
        }
        plaintext = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        if self._cipher:
            envelope = self._cipher.encrypt_bytes(plaintext)
            output = json.dumps(envelope, indent=2).encode("utf-8")
        else:
            output = plaintext
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{self.file_path.name}.", suffix=".tmp", dir=str(self.file_path.parent)
        )
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(output)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, self.file_path)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

    # ------------------------------------------------------------------ writing

    def record(
        self,
        domain: str,
        *,
        identifier_type: str = "unknown",
        identifier_value: str = "",
        account_exists: Optional[str] = None,
        identifiers_seen: Optional[List[str]] = None,
        login_method: Optional[str] = None,
        registration_status: Optional[str] = None,
        last_known_step: Optional[str] = None,
        last_path_choice: Optional[str] = None,
        confirmed_by_human: bool = False,
    ) -> PortalAccount:
        domain = _domain(domain)
        if not domain:
            raise ValueError("A portal account needs a domain.")
        if account_exists is not None and account_exists not in ACCOUNT_EXISTS:
            raise ValueError(f"Unknown account_exists value {account_exists!r}.")
        if registration_status is not None and registration_status not in REGISTRATION_STATUS:
            raise ValueError(f"Unknown registration status {registration_status!r}.")
        if login_method is not None and login_method not in LOGIN_METHODS:
            raise ValueError(f"Unknown login method {login_method!r}.")
        identifier_type = identifier_type if identifier_type in IDENTIFIER_TYPES else "unknown"
        key = _key(domain, identifier_type, identifier_value)
        existing = next((item for item in self._accounts if item.key == key), None)
        account = existing or PortalAccount(
            account_id="acct-"
            + uuid.uuid5(uuid.NAMESPACE_URL, f"formpilot:{key}").hex[:16],
            domain=domain,
            identifier_type=identifier_type,
            identifier_value=identifier_value,
        )
        if account_exists is not None:
            account.account_exists = account_exists
        if login_method is not None:
            account.login_method = login_method
        if registration_status is not None:
            account.registration_status = registration_status
        if last_known_step is not None:
            account.last_known_step = last_known_step
        if last_path_choice is not None:
            account.last_path_choice = last_path_choice
        if identifiers_seen:
            for item in identifiers_seen:
                if item and item not in account.identifiers_seen:
                    account.identifiers_seen.append(item)
        if confirmed_by_human:
            account.confirmed_by_human_at = _now()
        account.updated_at = _now()
        if existing is None:
            self._accounts.append(account)
        self.save()
        return account

    def delete(self, domain: str, *, identifier_type: str = "unknown", identifier_value: str = "") -> bool:
        key = _key(_domain(domain), identifier_type, identifier_value)
        before = len(self._accounts)
        self._accounts = [item for item in self._accounts if item.key != key]
        changed = len(self._accounts) != before
        if changed:
            self.save()
        return changed

    # ------------------------------------------------------------------ reading

    def get(
        self,
        domain: str,
        *,
        identifier_type: str = "unknown",
        identifier_value: str = "",
    ) -> Optional[PortalAccount]:
        domain = _domain(domain)
        exact = next(
            (
                item
                for item in self._accounts
                if item.domain == domain
                and item.identifier_type == (identifier_type or "unknown")
                and item.identifier_value == (identifier_value or "")
            ),
            None,
        )
        if exact is not None:
            return exact.model_copy(deep=True)
        return next(
            (
                item.model_copy(deep=True)
                for item in self._accounts
                if item.domain == domain
                and item.identifier_type == "unknown"
                and not item.identifier_value
            ),
            None,
        )

    def accounts_for(self, domain: str) -> List[PortalAccount]:
        domain = _domain(domain)
        return [
            item.model_copy(deep=True)
            for item in sorted(self._accounts, key=lambda account: account.updated_at)
            if item.domain == domain
        ]

    def all_accounts(self) -> List[PortalAccount]:
        return [item.model_copy(deep=True) for item in self._accounts]

    def domain_summary(self, domain: str) -> Dict[str, Any]:
        accounts = self.accounts_for(domain)
        known_exists = [item for item in accounts if item.account_exists != "unknown"]
        return {
            "domain": _domain(domain),
            "accounts": len(accounts),
            "account_exists": (
                "yes"
                if any(item.account_exists == "yes" for item in known_exists)
                else "no"
                if known_exists
                else "unknown"
            ),
            "registration_status": next(
                (
                    item.registration_status
                    for item in reversed(accounts)
                    if item.registration_status != "unknown"
                ),
                "unknown",
            ),
            "last_known_step": next(
                (item.last_known_step for item in reversed(accounts) if item.last_known_step),
                "",
            ),
            "identifiers": [
                {
                    "type": item.identifier_type,
                    "value": item.public()["identifier_value"],
                }
                for item in accounts
                if item.identifier_value
            ],
            "confirmed": any(item.confirmed_by_human_at for item in accounts),
            "updated_at": accounts[-1].updated_at if accounts else None,
        }

    # ------------------------------------------------------------------ inspection

    @staticmethod
    def inspect_login_ui(source: Any) -> LoginInspection:
        """Describe the visible login/recovery options.  Read-only by design."""
        if isinstance(source, Perception):
            from urllib.parse import urlparse

            domain = _domain(urlparse(source.url).netloc)
            text = " ".join(
                [
                    source.title or "",
                    source.visible_text or "",
                    " ".join(field.label_text or "" for field in source.fields),
                    " ".join(action.text or "" for action in source.actions),
                    " ".join(str(action.href or "") for action in source.actions),
                ]
            )
            actions = [action.text or "" for action in source.actions]
            fields = source.fields
        else:
            dom = source or {}
            from urllib.parse import urlparse

            domain = _domain(urlparse(str(dom.get("url") or "")).netloc)
            gateways = dom.get("gateways") or []
            inputs = dom.get("inputs") or []
            text = " ".join(
                [
                    str(dom.get("title") or ""),
                    str(dom.get("visibleText") or ""),
                    " ".join(str(item.get("text") or "") for item in gateways),
                    " ".join(str(item.get("label") or "") for item in inputs),
                ]
            )
            actions = [str(item.get("text") or "") for item in gateways]
            fields = []

        lowered = text.lower()
        methods: List[str] = []
        if "otp" in lowered or "one-time" in lowered or "one time" in lowered:
            if "aadhaar" in lowered:
                methods.append("aadhaar_otp")
            if "email" in lowered:
                methods.append("email_otp")
            if "mobile" in lowered or not methods:
                methods.append("mobile_otp")
        if "password" in lowered:
            methods.append("urn_password" if "urn" in lowered else "password")
        if "email" in lowered and "email_otp" not in methods:
            methods.append("email_otp")
        if not methods:
            methods.append("unknown")

        recovery = [
            label
            for label in actions
            if any(word in label.lower() for word in ("forgot", "recover", "reset", "retrieve"))
        ]
        hints: List[str] = []
        if "forgot" in lowered or "reset" in lowered:
            hints.append("A password-recovery path is visible.")
        if "register" in lowered or "new" in lowered:
            hints.append("A new-registration path is visible.")
        if "urn" in lowered:
            hints.append("The portal mentions a URN.")

        has_otp = "otp" in lowered or any(getattr(field, "input_type", "") == "text" and "otp" in (getattr(field, "label_text", "") or "").lower() for field in fields)
        has_password = any(getattr(field, "input_type", "") == "password" for field in fields) or "password" in lowered
        return LoginInspection(
            domain=domain,
            login_methods=list(dict.fromkeys(methods)),
            recovery_paths=list(dict.fromkeys(recovery)),
            has_otp=has_otp,
            has_password=has_password,
            hints=hints,
            inspected_at=_now(),
        )
