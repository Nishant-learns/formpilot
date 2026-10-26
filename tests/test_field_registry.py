"""Contract tests for the field registry, vault resolution, and DOM scanner."""

from __future__ import annotations

from backend.core import field_registry
from backend.core.dom_scanner import DOMScanner
from backend.core.vault import CandidateVault


SAMPLE_FIELDS = [
    {"id": "candidateName", "label": "Candidate Full Name"},
    {"id": "verifyCandidateName", "label": "Verify Candidate Name"},
    {"id": "fatherName", "label": "Father's Name"},
    {"id": "confirmFatherName", "label": "Re-enter Father's Name"},
    {"id": "motherName", "label": "Mother's Name"},
    {"id": "dob", "label": "Date of Birth"},
    {"name": "gender", "label": "Gender"},
    {"name": "marital_status", "label": "Marital Status"},
    {"name": "religion", "label": "Religion"},
    {"name": "nationality", "label": "Nationality"},
    {"name": "category", "label": "Social Category"},
    {"name": "sub_caste", "label": "Sub Caste"},
    {"name": "domicile", "label": "Domicile State"},
    {"name": "pwd", "label": "Differently Abled"},
    {"name": "ex_serviceman", "label": "Ex-Serviceman"},
    {"name": "mobile", "label": "Mobile Number"},
    {"name": "alternate_mobile", "label": "Alternate Mobile"},
    {"name": "email", "label": "Email Address"},
    {"name": "confirmEmail", "label": "Confirm Email Address"},
    {"name": "aadhaar", "label": "Aadhaar Number"},
    {"name": "apaar_id", "label": "APAAR ID"},
    {"name": "digilocker_id", "label": "DigiLocker ID"},
    {"name": "height", "label": "Height (cm)"},
    {"name": "chest", "label": "Chest (cm)"},
    {"name": "reg_id", "label": "Registration Number"},
    {"name": "password", "label": "Password"},
    {"name": "pincode", "label": "PIN Code"},
    {"name": "present_district", "label": "Present District"},
    {"name": "present_state", "label": "Present State"},
    {"name": "present_address", "label": "Present Address"},
    {"name": "village", "label": "Village / Town"},
    {"name": "district", "label": "District"},
    {"name": "state", "label": "State"},
    {"name": "address_line_2", "label": "Address Line 2"},
    {"name": "address", "label": "Permanent Address"},
    {"name": "identification_mark_1", "label": "Identification Mark 1"},
    {"name": "identification_mark_2", "label": "Identification Mark 2"},
    {"name": "photo", "type": "file", "label": "Passport Photograph"},
    {"name": "signature", "type": "file", "label": "Signature"},
    {"name": "matric_marksheet", "type": "file", "label": "10th Marksheet"},
    {"name": "matric_board", "label": "10th Board"},
    {"name": "matric_roll", "label": "10th Roll Number"},
    {"name": "matric_year", "label": "10th Passing Year"},
    {"name": "matric_percentage", "label": "10th Percentage"},
    {"name": "intermediate_board", "label": "12th Board"},
    {"name": "intermediate_roll", "label": "12th Roll Number"},
    {"name": "intermediate_stream", "label": "12th Stream"},
    {"name": "intermediate_year", "label": "12th Passing Year"},
    {"name": "intermediate_college", "label": "12th College"},
    {"name": "graduation_roll", "label": "Graduation Roll Number"},
    {"name": "graduation_university", "label": "Graduation University"},
    {"name": "graduation_year", "label": "Graduation Passing Year"},
    {"name": "graduation_percentage", "label": "Graduation Percentage"},
    {"name": "mother_tongue", "label": "Mother Tongue"},
    {"name": "employment_status", "label": "Employment Status"},
    {"name": "criminal_case", "label": "Criminal Case Pending"},
    {"name": "debarred", "label": "Debarred From Exam"},
]


def test_every_classified_key_exists_in_the_registry():
    missing = []
    for meta in SAMPLE_FIELDS:
        key, _ = DOMScanner.classify_field(meta)
        if key is not None and field_registry.spec_for(key) is None:
            missing.append((meta, key))
    assert not missing, f"DOM scanner emitted unregistered keys: {missing}"


def test_classifier_recognises_core_portal_fields():
    assert DOMScanner.classify_field({"id": "candidateName", "label": "Candidate Full Name"}) == (
        "full_name",
        False,
    )
    assert DOMScanner.classify_field(
        {"id": "verifyCandidateName", "label": "Verify Candidate Name"}
    ) == ("verify_full_name", True)
    assert DOMScanner.classify_field({"name": "mobile", "label": "Mobile Number"}) == (
        "mobile",
        False,
    )
    assert DOMScanner.classify_field({"name": "confirmEmail", "label": "Confirm Email"}) == (
        "confirm_email",
        True,
    )
    assert DOMScanner.classify_field({"name": "matric_roll", "label": "10th Roll No"}) == (
        "matric_roll_number",
        False,
    )


def test_one_time_codes_are_never_auto_filled():
    assert DOMScanner.classify_field({"name": "otp", "label": "Enter OTP"}) == (None, False)
    assert DOMScanner.classify_field(
        {"name": "captcha", "label": "Enter the code shown above"}
    ) == (None, False)


def test_vault_resolution_handles_aliases_and_nested_fields():
    vault = CandidateVault()

    assert field_registry.resolve_value(vault, "candidate_name") == vault.full_name
    assert field_registry.resolve_value(vault, "10th_roll") == vault.matric.roll_number
    assert field_registry.resolve_value(vault, "matric.board") == vault.matric.board
    assert field_registry.resolve_value(vault, "email_id") == vault.email
    assert field_registry.resolve_value(vault, "apaar_id") == vault.custom_fields["apaar_id"]
    assert field_registry.resolve_value(vault, "does_not_exist") is None


def test_sensitive_values_are_masked_for_public_views():
    assert field_registry.mask_value("aadhaar_number", "123456789012") == "********9012"
    assert field_registry.mask_value("account_password", "Practice@123") == "********@123"
    assert field_registry.mask_value("full_name", "Aman Kumar Sharma") == "Aman Kumar Sharma"
    assert field_registry.mask_value("aadhaar_number", None) is None
