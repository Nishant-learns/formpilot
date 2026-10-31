"""Behaviour that must hold on any portal, not only the HPSC form.

These tests cover the generic-portal hardening: one-time secrets never become
profile facts, declarations are asked instead of skipped, ambiguous save
buttons only stop on the last step, and option synonyms are matched safely.
"""

from __future__ import annotations

from backend.core.fill_plan import _match_option, build_fill_plan
from backend.core.facts import FactBook
from backend.core.orchestrator import FormPilotOrchestrator
from backend.core.perception import Perception, PerceivedField
from backend.core.vault import CandidateVault


class _Manager:
    def __init__(self, profile):
        self.vault = profile


def _book(tmp_path, profile: CandidateVault) -> FactBook:
    return FactBook(str(tmp_path / "facts.json"), vault_manager=_Manager(profile))


def _perception(*fields: PerceivedField) -> Perception:
    return Perception(
        page_signature="sha256:generic-portal",
        url="https://apply.example.gov.in/apply",
        title="Application",
        fields=list(fields),
    )


# --------------------------------------------------------------- secrets


def test_otp_and_captcha_fields_are_never_profile_facts():
    for label, name in (
        ("Enter OTP", "otp"),
        ("Verification code", "code"),
        ("Verification PIN", "pin"),
        ("Security code", "security"),
        ("Passcode", "passcode"),
        ("Enter the code", "SignupForm[code]"),
        ("CAPTCHA", "captcha"),
    ):
        assert FormPilotOrchestrator._is_security_code_field(
            {"label": label, "name": name}
        ), label


def test_ordinary_codes_are_not_treated_as_secrets():
    for label in (
        "PIN code",
        "Postal code",
        "Course code",
        "Registration code",
        "Coupon code",
        "Area code",
    ):
        assert not FormPilotOrchestrator._is_security_code_field(
            {"label": label, "name": "field"}
        ), label


def test_a_bare_code_box_next_to_a_challenge_is_a_secret():
    item = {"label": "Code", "name": "SignupForm[code]"}

    assert FormPilotOrchestrator._looks_like_generic_secret(
        item, {"otpInputs": [{"id": "code"}]}
    )
    assert not FormPilotOrchestrator._looks_like_generic_secret(item, {"otpInputs": []})


# --------------------------------------------------------------- declarations


def test_declaration_checkboxes_are_recognised():
    for label in (
        "I hereby declare that the information given is true",
        "I agree to the Terms and Conditions",
        "I accept the privacy policy",
        "Declaration",
    ):
        assert FormPilotOrchestrator._is_declaration(
            {"type": "checkbox", "label": label}
        ), label


def test_preference_checkboxes_are_not_declarations():
    for label in ("Remember me", "Subscribe to newsletter", "Notify me about updates"):
        assert not FormPilotOrchestrator._is_declaration(
            {"type": "checkbox", "label": label}
        ), label
    assert not FormPilotOrchestrator._is_declaration({"type": "text", "label": "I agree"})


# --------------------------------------------------------------- dates


def test_date_format_is_read_from_the_field():
    assert (
        FormPilotOrchestrator._date_format_for({"type": "date"}) == "YYYY-MM-DD"
    )
    assert (
        FormPilotOrchestrator._date_format_for(
            {"type": "text", "placeholder": "DD-MM-YYYY"}
        )
        == "DD-MM-YYYY"
    )
    assert (
        FormPilotOrchestrator._date_format_for(
            {"type": "text", "placeholder": "MM/DD/YYYY"}
        )
        == "MM/DD/YYYY"
    )
    assert FormPilotOrchestrator._date_format_for(
        {"type": "text", "label": "Date of Birth"}
    ) == ""


# --------------------------------------------------------------- final action


def test_ambiguous_save_is_final_only_on_the_last_step():
    assert not FormPilotOrchestrator._is_final_action({"text": "Save"})
    assert FormPilotOrchestrator._is_final_action({"text": "Save"}, last_step=True)
    assert FormPilotOrchestrator._is_final_action(
        {"text": "Confirm & Continue"}, last_step=True
    )
    assert not FormPilotOrchestrator._is_final_action(
        {"text": "Save & Next"}, last_step=True
    )
    assert FormPilotOrchestrator._is_final_action({"text": "Submit Application"})


def test_a_declaration_page_marks_an_ambiguous_save_as_final():
    preview = {"visibleText": "Preview your application", "inputs": []}
    assert FormPilotOrchestrator._page_looks_final(preview, {"text": "Save"})

    declaration = {
        "visibleText": "Personal details",
        "inputs": [
            {
                "type": "checkbox",
                "label": "I agree to the terms and conditions",
            }
        ],
    }
    assert FormPilotOrchestrator._page_looks_final(declaration, {"text": "Confirm"})
    assert not FormPilotOrchestrator._page_looks_final(
        {"visibleText": "Personal details", "inputs": []}, {"text": "Confirm"}
    )


# --------------------------------------------------------------- options


def test_option_synonyms_are_matched():
    assert _match_option("Male", [{"value": "M", "text": "M"}]) == "M"
    assert _match_option("Female", [{"value": "F", "text": "F"}]) == "F"
    assert (
        _match_option("Single", [{"value": "UNMARRIED", "text": "Unmarried"}])
        == "UNMARRIED"
    )
    assert _match_option("UR", [{"value": "GEN", "text": "General"}]) == "GEN"
    assert (
        _match_option(
            "OBC-NCL",
            [{"value": "OBC-NCL", "text": "OBC (Non-Creamy Layer)"}],
        )
        == "OBC-NCL"
    )


def test_a_long_label_matches_by_containment():
    assert _match_option("General", [{"value": "G", "text": "General (UR)"}]) == "G"


def test_ambiguous_options_are_not_guessed():
    options = [{"value": "1", "text": "SC"}, {"value": "2", "text": "sc"}]

    assert _match_option("SC", options) is None


def test_a_category_is_not_widened_or_narrowed():
    assert _match_option("OBC", [{"value": "OBC-NCL", "text": "OBC-NCL"}]) is None
    assert (
        _match_option("General", [{"value": "GEN-EWS", "text": "General-EWS"}])
        is None
    )


def test_a_select_fact_matches_a_short_option(tmp_path):
    book = _book(tmp_path, CandidateVault(gender="Male"))
    perception = _perception(
        PerceivedField(
            handle="fp-1",
            label_text="Gender",
            tag="select",
            input_type="select",
            options=[{"text": "F", "value": "F"}, {"text": "M", "value": "M"}],
        )
    )

    plan = build_fill_plan(perception, book)

    assert plan["fp-1"].state == "fill"
    assert plan["fp-1"].value == "M"
