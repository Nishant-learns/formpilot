"""Semantic facts: the labeled, sourced values behind the vault.

The vault stores the candidate's profile.  A ``Fact`` is the meaning of one
value: which concept it answers, where it came from, whether a human confirmed
it, and which portal (if any) it belongs to.

Two rules drive this module:

* **Explicit beats derived.**  A value the candidate stated is never replaced
  by a value inferred from another field.  Derived facts are still available,
  but they are labelled and lose to an explicit fact.
* **Absence is a fact.**  "I have no middle name" is stored as
  ``middle_known_absent`` and is different from "not known yet".

The vault remains the storage for the profile.  This module adds the semantic
overlay: explicit facts (in ``facts.json``), derived facts, aliases, provenance,
verification and portal scope.
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

from . import concepts, field_registry
from .vault import CandidateVault, VaultManager
from .vault_crypto import VaultCipher, VaultCryptoError, cipher_from_env, decode_envelope


PROVENANCES = {"explicit_user", "derived", "portal_confirmed", "imported"}
VERIFICATIONS = {"unverified", "confirmed_by_human", "verified_on_page"}
FACT_STATES = {"known", "known_absent", "needs_confirmation", "missing"}

# A confirmation field asks the human to repeat an existing fact.  It keeps
# its own concept on the page, but it resolves to the parent fact instead of
# being stored twice.
CONFIRMATION_PARENTS: Dict[str, str] = {
    "verify_full_name": "full_name",
    "verify_father_name": "father_name",
    "verify_mother_name": "mother_name",
}

# Values that a portal derives mechanically from another fact.  A confirmation
# copy is not a guess, so it is usable without asking.
_MECHANICAL_DERIVATIONS: Dict[str, str] = {
    "confirm_email": "email",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_facts_path() -> Path:
    data_dir = Path(os.getenv("FORMPILOT_DATA_DIR", Path(__file__).resolve().parents[2] / "data"))
    return data_dir / "facts.json"


def _scope_key(scope: Dict[str, Any]) -> str:
    if (scope or {}).get("kind") != "portal":
        return "global"
    return "portal:{domain}:{identifier_type}:{identifier_value}".format(
        domain=str(scope.get("domain") or "").lower(),
        identifier_type=str(scope.get("identifier_type") or ""),
        identifier_value=str(scope.get("identifier_value") or ""),
    )


def _clean_scope(scope: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    scope = dict(scope or {})
    if scope.get("kind") != "portal":
        return {"kind": "global"}
    return {
        "kind": "portal",
        "domain": str(scope.get("domain") or "").lower(),
        "identifier_type": scope.get("identifier_type"),
        "identifier_value": scope.get("identifier_value"),
    }


class Fact(BaseModel):
    fact_id: str = ""
    concept: str
    label: str = ""
    value: str = ""
    value_type: str = "text"
    parts: Optional[Dict[str, Any]] = None
    aliases: List[str] = Field(default_factory=list)
    provenance: str = "explicit_user"
    verification: str = "confirmed_by_human"
    verified_at: Optional[str] = None
    scope: Dict[str, Any] = Field(default_factory=lambda: {"kind": "global"})
    constraints: Dict[str, Any] = Field(default_factory=dict)
    notes: Optional[str] = None
    known_absent: bool = False
    updated_at: str = ""

    def public(self, *, mask: bool = True) -> Dict[str, Any]:
        data = self.model_dump()
        if mask:
            data["value"] = field_registry.mask_value(self.concept, self.value)
        return data


class FactResolution(BaseModel):
    concept: str
    label: str = ""
    state: str = "missing"
    value: Optional[str] = None
    provenance: str = "missing"
    verification: str = "unverified"
    scope: Dict[str, Any] = Field(default_factory=lambda: {"kind": "global"})
    source: str = "none"  # explicit | derived | vault | none
    parts: Optional[Dict[str, Any]] = None
    fact: Optional[Fact] = None

    @property
    def is_known(self) -> bool:
        return self.state in {"known", "known_absent"}

    @property
    def needs_confirmation(self) -> bool:
        return self.state == "needs_confirmation" or self.verification == "unverified"


class FactBook:
    """Explicit facts plus a semantic view over the candidate's vault."""

    _instance: Optional["FactBook"] = None
    _instance_path: Optional[str] = None

    def __init__(
        self,
        file_path: Optional[str] = None,
        *,
        cipher: Optional[VaultCipher] = None,
        vault_manager: Optional[VaultManager] = None,
    ) -> None:
        self.file_path = Path(file_path) if file_path else _default_facts_path()
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self._cipher = cipher if cipher is not None else cipher_from_env()
        self._vault_manager = vault_manager
        self._facts: List[Fact] = []
        self.load()

    # ------------------------------------------------------------------ storage

    @classmethod
    def get_instance(cls) -> "FactBook":
        path = str(_default_facts_path())
        if cls._instance is None or cls._instance_path != path:
            cls._instance = FactBook(path)
            cls._instance_path = path
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        cls._instance = None
        cls._instance_path = None

    def load(self) -> List[Fact]:
        self._facts = []
        if not self.file_path.exists():
            return self._facts
        try:
            raw = self.file_path.read_text(encoding="utf-8")
            is_encrypted, payload = decode_envelope(raw)
            if is_encrypted:
                if not self._cipher:
                    raise VaultCryptoError(
                        "Facts are encrypted but FORMPILOT_VAULT_KEY is not set."
                    )
                raw = self._cipher.decrypt_bytes(payload)  # type: ignore[arg-type]
            data = json.loads(raw)
        except VaultCryptoError:
            raise
        except Exception as exc:  # pragma: no cover - corrupt file is rare
            print(f"[FactBook] Could not read facts, starting empty: {exc}")
            return self._facts
        items = data.get("facts") if isinstance(data, dict) else data
        for item in items or []:
            if not isinstance(item, dict):
                continue
            try:
                self._facts.append(Fact(**item))
            except Exception:
                continue
        return self._facts

    def save(self) -> None:
        payload = {
            "version": 1,
            "updated_at": _now(),
            "facts": [fact.model_dump() for fact in self._facts],
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

    def set_fact(
        self,
        concept: str,
        *,
        value: Optional[str] = None,
        label: Optional[str] = None,
        value_type: Optional[str] = None,
        parts: Optional[Dict[str, Any]] = None,
        aliases: Optional[List[str]] = None,
        provenance: str = "explicit_user",
        verification: str = "confirmed_by_human",
        scope: Optional[Dict[str, Any]] = None,
        constraints: Optional[Dict[str, Any]] = None,
        notes: Optional[str] = None,
        known_absent: bool = False,
    ) -> Fact:
        concept = (concept or "").strip()
        if concept not in concepts.CONCEPTS:
            raise ValueError(
                f"Unknown concept {concept!r}. A new concept must be confirmed before it is stored."
            )
        if provenance not in PROVENANCES:
            raise ValueError(f"Unknown provenance {provenance!r}.")
        if verification not in VERIFICATIONS:
            raise ValueError(f"Unknown verification {verification!r}.")
        spec = concepts.CONCEPTS[concept]
        clean_scope = _clean_scope(scope)
        if clean_scope["kind"] == "portal" and not clean_scope.get("domain"):
            raise ValueError("A portal-scoped fact needs a domain.")

        fact = Fact(
            fact_id=self._fact_id(concept, clean_scope),
            concept=concept,
            label=(label or spec.label).strip(),
            value="" if known_absent else str(value if value is not None else ""),
            value_type=(value_type or spec.answer_type or "text"),
            parts=parts,
            aliases=list(aliases or []),
            provenance=provenance,
            verification=verification,
            verified_at=_now() if verification != "unverified" else None,
            scope=clean_scope,
            constraints=dict(constraints or {}),
            notes=notes,
            known_absent=bool(known_absent),
            updated_at=_now(),
        )
        self._facts = [
            item
            for item in self._facts
            if not (item.concept == concept and _scope_key(item.scope) == _scope_key(clean_scope))
        ]
        self._facts.append(fact)
        self.save()
        return fact

    def delete_fact(self, concept: str, *, scope: Optional[Dict[str, Any]] = None) -> bool:
        target = _scope_key(_clean_scope(scope))
        before = len(self._facts)
        self._facts = [
            item
            for item in self._facts
            if not (item.concept == concept and _scope_key(item.scope) == target)
        ]
        changed = len(self._facts) != before
        if changed:
            self.save()
        return changed

    def reset(self) -> None:
        self._facts = []
        self.save()

    # ------------------------------------------------------------------ reading

    @property
    def explicit_facts(self) -> List[Fact]:
        return [fact.model_copy(deep=True) for fact in self._facts]

    def _fact_id(self, concept: str, scope: Dict[str, Any]) -> str:
        return "fact-" + uuid.uuid5(
            uuid.NAMESPACE_URL, f"formpilot:{concept}:{_scope_key(scope)}"
        ).hex[:16]

    def _best_explicit(self, concept: str, domain: Optional[str]) -> Optional[Fact]:
        domain = (domain or "").lower()
        portal = None
        global_fact = None
        for fact in self._facts:
            if fact.concept != concept:
                continue
            kind = (fact.scope or {}).get("kind")
            if kind == "portal" and domain and str(fact.scope.get("domain") or "").lower() == domain:
                portal = fact
            elif kind != "portal":
                global_fact = fact
        return portal or global_fact

    def _vault(self, vault: Optional[CandidateVault]) -> CandidateVault:
        if vault is not None:
            return vault
        if self._vault_manager is not None:
            return self._vault_manager.vault
        return VaultManager.get_instance().vault

    def resolve(
        self,
        concept: str,
        *,
        domain: Optional[str] = None,
        vault: Optional[CandidateVault] = None,
    ) -> FactResolution:
        concept = (concept or "").strip()
        if concept in CONFIRMATION_PARENTS:
            parent = self.resolve(CONFIRMATION_PARENTS[concept], domain=domain, vault=vault)
            return parent.model_copy(
                update={
                    "concept": concept,
                    "label": concepts.concept_label(concept),
                    "parts": parent.parts,
                }
            )
        spec = concepts.CONCEPTS.get(concept)
        label = spec.label if spec else concept.replace("_", " ")

        explicit = self._best_explicit(concept, domain)
        if explicit is not None:
            return FactResolution(
                concept=concept,
                label=explicit.label or label,
                state="known_absent" if explicit.known_absent else "known",
                value=None if explicit.known_absent else explicit.value,
                provenance=explicit.provenance,
                verification=explicit.verification,
                scope=dict(explicit.scope),
                source="explicit",
                parts=explicit.parts,
                fact=explicit,
            )

        derived = self._derive(concept, domain=domain, vault=vault)
        if derived is not None:
            return derived

        profile = self._vault(vault)
        vault_key = concepts.vault_key_for(concept) or concept
        raw = field_registry.resolve_value(profile, vault_key)
        if raw in (None, "") and hasattr(profile, "find_field_value"):
            # Small test doubles and older adapters expose only this method.
            raw = profile.find_field_value(vault_key)
        if raw not in (None, ""):
            return FactResolution(
                concept=concept,
                label=label,
                state="known",
                value=str(raw),
                provenance="explicit_user",
                verification="confirmed_by_human",
                scope={"kind": "global"},
                source="vault",
            )
        return FactResolution(concept=concept, label=label, state="missing")

    def _derive(
        self,
        concept: str,
        *,
        domain: Optional[str],
        vault: Optional[CandidateVault],
    ) -> Optional[FactResolution]:
        if concept in {"first_name", "middle_name", "last_name"}:
            parts = self._name_parts(domain=domain, vault=vault)
            if parts is None:
                return None
            key = {"first_name": "first", "middle_name": "middle", "last_name": "last"}[concept]
            value = parts.get(key)
            if concept == "middle_name" and parts.get("middle_known_absent"):
                return FactResolution(
                    concept=concept,
                    label=concepts.concept_label(concept),
                    state="known_absent",
                    value=None,
                    provenance="explicit_user",
                    verification="confirmed_by_human",
                    source="derived",
                    parts=parts,
                )
            if value in (None, ""):
                return None
            return FactResolution(
                concept=concept,
                label=concepts.concept_label(concept),
                state="known",
                value=str(value),
                provenance="derived",
                verification="confirmed_by_human",
                source="derived",
                parts=parts,
            )

        if concept == "name_as_matric":
            full = self.resolve("full_name", domain=domain, vault=vault)
            if full.state != "known" or not full.value:
                return None
            # The certificate may print the name differently.  The value is
            # available, but a human confirms it before it is used.
            return FactResolution(
                concept=concept,
                label=concepts.concept_label(concept),
                state="needs_confirmation",
                value=full.value,
                provenance="derived",
                verification="unverified",
                source="derived",
            )

        parent = _MECHANICAL_DERIVATIONS.get(concept)
        if parent:
            source = self.resolve(parent, domain=domain, vault=vault)
            if source.state == "known" and source.value:
                return FactResolution(
                    concept=concept,
                    label=concepts.concept_label(concept),
                    state="known",
                    value=source.value,
                    provenance="derived",
                    verification=source.verification,
                    source="derived",
                )
        return None

    def _name_parts(
        self,
        *,
        domain: Optional[str],
        vault: Optional[CandidateVault],
    ) -> Optional[Dict[str, Any]]:
        full_fact = self._best_explicit("full_name", domain)
        if full_fact is not None and isinstance(full_fact.parts, dict) and any(
            value not in (None, "") for key, value in full_fact.parts.items() if key != "middle_known_absent"
        ):
            return dict(full_fact.parts)

        full = self.resolve("full_name", domain=domain, vault=vault)
        if full.state != "known" or not full.value:
            return None
        tokens = [token for token in str(full.value).split() if token]
        if not tokens:
            return None
        if len(tokens) == 1:
            return {"first": tokens[0], "middle": None, "last": None, "middle_known_absent": True}
        middle = " ".join(tokens[1:-1]) or None
        return {
            "first": tokens[0],
            "middle": middle,
            "last": tokens[-1],
            # A two-token name has no middle name.  Treat that as "known
            # absent" instead of "unknown", otherwise every two-part name
            # opens a checkpoint asking the candidate to invent one.
            "middle_known_absent": middle is None,
        }

    def all_facts(
        self,
        *,
        domain: Optional[str] = None,
        vault: Optional[CandidateVault] = None,
    ) -> List[Fact]:
        profile = self._vault(vault)
        seen: set[str] = set()
        result: List[Fact] = []
        for concept in concepts.CONCEPTS:
            if concept in CONFIRMATION_PARENTS:
                continue
            resolution = self.resolve(concept, domain=domain, vault=profile)
            seen.add(concept)
            if resolution.state == "missing":
                continue
            result.append(
                Fact(
                    fact_id=self._fact_id(concept, resolution.scope),
                    concept=concept,
                    label=resolution.label,
                    value="" if resolution.value is None else str(resolution.value),
                    value_type=concepts.CONCEPTS[concept].answer_type,
                    parts=resolution.parts,
                    provenance=resolution.provenance,
                    verification=resolution.verification,
                    scope=resolution.scope,
                    known_absent=resolution.state == "known_absent",
                )
            )
        for fact in self._facts:
            if fact.concept in seen:
                continue
            if fact.concept in CONFIRMATION_PARENTS:
                continue
            seen.add(fact.concept)
            result.append(fact.model_copy(deep=True))
        return sorted(result, key=lambda item: item.label.lower())

    def resolve_alias(self, text: str) -> Optional[str]:
        """Resolve a human phrase to a concept using facts and the dictionary."""
        wanted = concepts.normalize(text)
        if not wanted:
            return None
        for fact in self._facts:
            for alias in fact.aliases:
                if concepts.normalize(alias) == wanted:
                    return fact.concept
        for concept in concepts.CONCEPTS.values():
            if concepts.normalize(concept.label) == wanted:
                return concept.key
            for alias in concept.aliases:
                if concepts.normalize(alias) == wanted:
                    return concept.key
        return None

    def annotate_brief(
        self,
        brief: Any,
        *,
        domain: Optional[str] = None,
        vault: Optional[CandidateVault] = None,
    ) -> Any:
        """Attach fact availability to every question in a PageBrief.

        The brief keeps its meaning-only shape; these fields are the bridge to
        the vault.  No value is copied into the brief.
        """
        profile = self._vault(vault)
        for question in getattr(brief, "questions", []):
            if getattr(question, "human_only", False):
                question.fact_status = "human_only"
                continue
            concept = getattr(question, "concept", None)
            if not concept:
                question.fact_status = "missing"
                continue
            resolution = self.resolve(concept, domain=domain, vault=profile)
            question.fact_status = resolution.state
            question.fact_provenance = resolution.provenance
            question.fact_verification = resolution.verification
        return brief

    def summary(
        self,
        *,
        domain: Optional[str] = None,
        vault: Optional[CandidateVault] = None,
    ) -> Dict[str, Any]:
        facts = self.all_facts(domain=domain, vault=vault)
        return {
            "domain": domain,
            "total": len(facts),
            "explicit": sum(1 for fact in facts if fact.provenance != "derived"),
            "derived": sum(1 for fact in facts if fact.provenance == "derived"),
            "unverified": sum(1 for fact in facts if fact.verification == "unverified"),
            "known_absent": sum(1 for fact in facts if fact.known_absent),
        }
