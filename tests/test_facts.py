"""Semantic fact tests: provenance, parts, scope, aliases and confirmation."""

from __future__ import annotations

import json

import pytest

from backend.core.facts import FactBook
from backend.core.page_brief import build_deterministic_brief
from backend.core.perception import Perception, PerceivedField
from backend.core.vault import CandidateVault


def _book(tmp_path, vault: CandidateVault | None = None) -> FactBook:
    class Manager:
        def __init__(self, profile):
            self.vault = profile

    return FactBook(str(tmp_path / "facts.json"), vault_manager=Manager(vault or CandidateVault()))


def _field(handle: str, label: str, **kwargs) -> PerceivedField:
    return PerceivedField(handle=handle, label_text=label, **kwargs)


def test_name_parts_are_derived_from_the_full_name(tmp_path):
    book = _book(tmp_path, CandidateVault(full_name="Aman Kumar Sharma"))

    first = book.resolve("first_name")
    middle = book.resolve("middle_name")
    last = book.resolve("last_name")

    assert (first.value, middle.value, last.value) == ("Aman", "Kumar", "Sharma")
    assert first.provenance == "derived"
    assert first.state == "known"


def test_an_explicit_fact_beats_a_derived_one(tmp_path):
    book = _book(tmp_path, CandidateVault(full_name="Aman Kumar Sharma"))

    book.set_fact("first_name", value="Nishant", provenance="explicit_user")
    resolution = book.resolve("first_name")

    assert resolution.value == "Nishant"
    assert resolution.source == "explicit"
    assert resolution.provenance == "explicit_user"


def test_no_middle_name_is_a_fact_not_an_unknown(tmp_path):
    book = _book(tmp_path, CandidateVault(full_name="Nishant Kumar"))
    book.set_fact(
        "full_name",
        value="Nishant Kumar",
        parts={
            "first": "Nishant",
            "middle": None,
            "middle_known_absent": True,
            "last": "Kumar",
        },
    )

    middle = book.resolve("middle_name")

    assert middle.state == "known_absent"
    assert middle.value is None
    assert middle.is_known is True


def test_portal_scope_wins_only_on_its_own_domain(tmp_path):
    book = _book(tmp_path)
    book.set_fact("mobile", value="9876543210")
    book.set_fact("mobile", value="9000000001", scope={"kind": "portal", "domain": "regn.example.gov.in"})

    on_portal = book.resolve("mobile", domain="regn.example.gov.in")
    elsewhere = book.resolve("mobile", domain="other.example.gov.in")

    assert on_portal.value == "9000000001"
    assert elsewhere.value == "9876543210"


def test_confirmation_fields_resolve_to_their_parent_fact(tmp_path):
    book = _book(tmp_path, CandidateVault(full_name="Aman Kumar Sharma"))

    confirmation = book.resolve("verify_full_name")

    assert confirmation.value == "Aman Kumar Sharma"
    assert confirmation.concept == "verify_full_name"


def test_name_as_matric_is_derived_but_needs_confirmation(tmp_path):
    book = _book(tmp_path, CandidateVault(full_name="Aman Kumar Sharma"))

    resolution = book.resolve("name_as_matric")

    assert resolution.value == "Aman Kumar Sharma"
    assert resolution.state == "needs_confirmation"
    assert resolution.provenance == "derived"
    assert resolution.verification == "unverified"


def test_unknown_concepts_are_rejected(tmp_path):
    book = _book(tmp_path)

    with pytest.raises(ValueError):
        book.set_fact("made_up_question", value="x")


def test_aliases_resolve_to_concepts(tmp_path):
    book = _book(tmp_path)
    book.set_fact("first_name", value="Nishant", aliases=["given name", "पहला नाम"])

    assert book.resolve_alias("Given Name") == "first_name"
    assert book.resolve_alias("पहला नाम") == "first_name"
    assert book.resolve_alias("date of birth") == "date_of_birth"
    assert book.resolve_alias("not a question") is None


def test_facts_persist_and_reload(tmp_path):
    path = str(tmp_path / "facts.json")
    first = FactBook(path)
    first.set_fact(
        "first_name",
        value="Nishant",
        aliases=["given name"],
        scope={"kind": "portal", "domain": "regn.example.gov.in"},
    )

    second = FactBook(path)
    fact = second.resolve("first_name", domain="regn.example.gov.in").fact

    assert fact is not None
    assert fact.value == "Nishant"
    assert fact.scope["domain"] == "regn.example.gov.in"
    assert fact.aliases == ["given name"]


def test_sensitive_values_are_masked_in_the_public_view(tmp_path):
    book = _book(tmp_path)
    book.set_fact("aadhaar_number", value="123456789012")

    public = book.resolve("aadhaar_number").fact.public()

    assert public["value"].endswith("9012")
    assert "12345678" not in public["value"]


def test_brief_questions_learn_whether_a_fact_exists(tmp_path):
    book = _book(tmp_path, CandidateVault(full_name="Nishant Kumar"))
    perception = Perception(
        page_signature="sha256:facts",
        url="https://regn.example.gov.in/apply",
        title="Personal Details",
        fields=[
            _field("fp-1", "First Name", required=True),
            _field("fp-2", "Middle Name"),
            _field("fp-3", "Name as printed on matric certificate"),
        ],
    )
    brief = build_deterministic_brief(perception)

    book.annotate_brief(brief, domain="regn.example.gov.in")
    by_handle = {question.handle: question for question in brief.questions}

    assert by_handle["fp-1"].fact_status == "known"
    assert by_handle["fp-2"].fact_status == "missing"
    assert by_handle["fp-3"].fact_status == "needs_confirmation"
    assert by_handle["fp-1"].fact_provenance == "derived"


def test_fact_summary_counts_provenance(tmp_path):
    book = _book(tmp_path, CandidateVault(full_name="Aman Kumar Sharma"))
    book.set_fact("first_name", value="Nishant")

    summary = book.summary()

    assert summary["total"] > 0
    assert summary["explicit"] >= 1
    assert summary["derived"] >= 1


def test_facts_are_stored_encrypted_when_a_key_is_present(tmp_path):
    import base64

    from backend.core.vault_crypto import VaultCipher

    cipher = VaultCipher(base64.b64encode(b"0" * 32).decode("ascii"))
    path = tmp_path / "facts.json"
    book = FactBook(str(path), cipher=cipher)
    book.set_fact("first_name", value="Nishant")

    raw = path.read_text(encoding="utf-8")
    assert "Nishant" not in raw
    envelope = json.loads(raw)
    assert envelope.get("encrypted") is True

    reopened = FactBook(str(path), cipher=cipher)
    assert reopened.resolve("first_name").value == "Nishant"


def test_every_field_registry_key_has_a_semantic_concept():
    from backend.core import concepts, field_registry

    missing = []
    for key, spec in field_registry.FIELD_SPECS.items():
        if concepts.concept_for_vault_key(key):
            continue
        if concepts.concept_for_vault_key(spec.path):
            continue
        missing.append(key)
    assert missing == []
