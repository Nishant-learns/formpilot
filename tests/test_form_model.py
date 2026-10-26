"""Normalized form maps and structural fingerprints."""

from __future__ import annotations

from backend.core.form_model import FormModel


def sample_dom():
    return {
        "title": "Recruitment Application",
        "visibleText": "New Registration Candidate Login Personal Details",
        "frameworks": ["React"],
        "inputs": [
            {
                "index": 0,
                "tagName": "input",
                "type": "text",
                "id": "full_name",
                "name": "full_name",
                "label": "Full Name",
                "required": True,
                "value": "",
                "options": [],
                "rect": {"top": 10, "left": 20, "width": 300, "height": 32},
            },
            {
                "index": 1,
                "tagName": "input",
                "type": "date",
                "id": "dob",
                "name": "date_of_birth",
                "label": "Date of Birth",
                "required": True,
                "value": "",
                "options": [],
            },
            {
                "index": 2,
                "tagName": "input",
                "type": "text",
                "id": "apar_id",
                "name": "apar_id",
                "label": "APAR ID",
                "required": False,
                "value": "",
                "options": [],
            },
            {
                "index": 3,
                "tagName": "select",
                "type": "select-one",
                "id": "category",
                "name": "category",
                "label": "Category",
                "required": True,
                "value": "",
                "options": [
                    {"text": "General", "value": "GEN"},
                    {"text": "OBC-NCL", "value": "OBC"},
                ],
            },
            {
                "index": 4,
                "tagName": "input",
                "type": "file",
                "id": "photo",
                "name": "photo",
                "label": "Photograph",
                "required": True,
                "accept": "image/jpeg",
                "capture": "",
            },
        ],
        "gateways": [],
        "captchaElements": [
            {
                "tagName": "canvas",
                "kind": "text",
                "id": "captchaCanvas",
                "prompt": "Enter the security code",
            }
        ],
        "errors": [],
        "nextButtons": [
            {"id": "next", "text": "Save & Next"},
            {"id": "submit", "text": "Final Submit"},
        ],
        "paymentSignals": 0,
        "hasPaymentButton": False,
        "formCount": 1,
        "activeSectionId": "sec-1",
        "stepHeading": "Personal Details",
        "fileInputs": [{"id": "photo", "name": "photo", "label": "Photograph", "hasFile": False}],
        "livePhotoRequired": False,
        "otpInputs": [],
        "formAction": "/apply",
    }


def build_map():
    return FormModel.build_form_map(sample_dom(), "https://example.gov.in/apply?token=secret")


def test_form_map_normalizes_fields_and_locators():
    form_map = build_map()

    assert form_map["portal"] == "example.gov.in"
    assert form_map["display_url"] == "https://example.gov.in/apply"
    assert "token" not in form_map["display_url"]
    assert form_map["page_type"] == "application_form"
    assert form_map["page_confidence"] == 72
    assert form_map["field_count"] == 5
    assert form_map["known_field_count"] >= 3
    assert form_map["unknown_field_count"] == 1

    fields = {field["key"]: field for field in form_map["fields"]}
    name_field = fields["full_name"]
    assert name_field["value_source"] == "missing"
    assert name_field["needs_user_input"] is True
    assert name_field["ask_reason"] == "missing_value"
    assert name_field["required"] is True
    assert {"strategy": "id", "value": "full_name"} in name_field["locators"]
    assert {"strategy": "name", "value": "full_name"} in name_field["locators"]
    assert {"strategy": "label", "value": "Full Name"} in name_field["locators"]
    assert any(locator["strategy"] == "role" and locator["role"] == "textbox" for locator in name_field["locators"])

    unknown = fields["unknown_apar_id"]
    assert unknown["semantic_key"] is None
    assert unknown["value_source"] == "unknown"
    assert unknown["ask_reason"] == "unknown_field"
    assert unknown["needs_user_input"] is True

    category = fields["category"]
    assert category["option_count"] == 2
    assert category["options"][1]["text"] == "OBC-NCL"


def test_form_map_marks_captcha_as_human_only():
    form_map = build_map()

    assert form_map["captcha"]["present"] is True
    assert form_map["captcha"]["kinds"] == ["text"]
    assert form_map["captcha"]["solver_policy"] == "human_handoff_only"
    assert form_map["challenge"] == "captcha"


def test_otp_and_captcha_inputs_are_human_only_not_unknown():
    dom = sample_dom()
    dom["inputs"] += [
        {
            "index": 5,
            "tagName": "input",
            "type": "text",
            "id": "mobileOtp",
            "name": "mobileOtp",
            "label": "Enter 6-digit OTP",
        },
        {
            "index": 6,
            "tagName": "input",
            "type": "text",
            "id": "captcha_code",
            "name": "captcha_code",
            "label": "Security code",
        },
        {
            "index": 7,
            "tagName": "input",
            "type": "text",
            "id": "card_cvv",
            "name": "card_cvv",
            "label": "Card security code",
        },
    ]
    form_map = FormModel.build_form_map(dom, "https://example.gov.in/apply")
    fields = {field["key"]: field for field in form_map["fields"]}

    otp = fields["human_otp_5"]
    assert otp["challenge"] == "otp"
    assert otp["value_source"] == "human"
    assert otp["semantic_key"] is None
    assert otp["ask_reason"] == "human_challenge"
    assert otp["sensitive"] is True

    captcha = fields["human_captcha_6"]
    assert captcha["challenge"] == "captcha"
    assert captcha["value_source"] == "human"

    # A card security code is a payment detail, not a CAPTCHA, so it stays a
    # normal unknown field and is never auto-filled.
    assert fields["unknown_card_cvv"]["challenge"] is None
    assert fields["unknown_card_cvv"]["value_source"] == "unknown"

    assert form_map["human_field_count"] == 2
    assert {entry["challenge"] for entry in form_map["human_fields"]} == {"otp", "captcha"}
    assert form_map["unknown_field_count"] == 2

    compact = {field["key"]: field for field in FormModel.compact_for_recipe(form_map)}
    assert compact["human_otp_5"]["challenge"] == "otp"
    assert "value" not in compact["human_otp_5"]


def test_form_map_blocks_final_actions_but_allows_navigation():
    actions = {action["text"]: action for action in build_map()["next_actions"]}

    assert actions["Save & Next"]["blocked"] is False
    assert actions["Save & Next"]["kind"] == "navigation"
    assert actions["Final Submit"]["blocked"] is True
    assert actions["Final Submit"]["kind"] == "final_action"
    assert "never clicks" in actions["Final Submit"]["reason"]


def test_fingerprint_ignores_values_and_random_hidden_tokens():
    first = build_map()
    dom = sample_dom()
    dom["inputs"][0]["value"] = "Aman Kumar Sharma"
    dom["inputs"][0]["id"] = "full_name_9f3c2a7b1d4e"
    dom["inputs"].append(
        {
            "index": 99,
            "tagName": "input",
            "type": "hidden",
            "name": "csrf_token",
            "label": "",
            "value": "abc123def456ghi789",
        }
    )
    second = FormModel.build_form_map(dom, "https://example.gov.in/apply?token=another")

    assert first["fingerprint"] == second["fingerprint"]
    assert first["fingerprint_short"] == second["fingerprint_short"]


def test_fingerprint_changes_when_a_label_changes():
    first = build_map()
    dom = sample_dom()
    dom["inputs"][0]["label"] = "Candidate Full Name"
    second = FormModel.build_form_map(dom, "https://example.gov.in/apply")

    assert first["fingerprint"] != second["fingerprint"]


def test_fingerprint_separates_steps_with_identical_fields():
    first = build_map()
    dom = sample_dom()
    dom["activeSectionId"] = "sec-2"
    dom["formAction"] = "/apply/address?session=secret"
    second = FormModel.build_form_map(dom, "https://example.gov.in/apply")

    assert first["fingerprint"] != second["fingerprint"]
    assert first["fingerprint_short"] != second["fingerprint_short"]


def test_page_classification_recognizes_payment_and_login():
    dom = sample_dom()
    dom["hasPaymentButton"] = True
    dom["paymentSignals"] = 4
    payment = FormModel.build_form_map(dom, "https://example.gov.in/pay")
    assert payment["page_type"] == "payment"
    assert payment["page_confidence"] == 96

    login_dom = sample_dom()
    login_dom["inputs"] = [
        {
            "index": 0,
            "tagName": "input",
            "type": "password",
            "id": "password",
            "name": "password",
            "label": "Password",
        }
    ]
    login = FormModel.build_form_map(login_dom, "https://example.gov.in/login")
    assert login["page_type"] == "login"


def test_page_classification_recognizes_registration_gateway():
    dom = sample_dom()
    dom["inputs"] = []
    dom["gateways"] = [
        {"type": "NEW_REGISTRATION", "text": "New Registration", "id": "new"},
        {"type": "LOGIN", "text": "Candidate Login", "id": "login"},
    ]
    form_map = FormModel.build_form_map(dom, "https://example.gov.in/")

    assert form_map["page_type"] == "portal_entry"
    assert form_map["page_confidence"] == 95
    assert len(form_map["gateways"]) == 2


def test_recipe_compaction_contains_no_values_or_pii():
    dom = sample_dom()
    dom["inputs"][0]["value"] = "Aman Kumar Sharma"
    form_map = FormModel.build_form_map(dom, "https://example.gov.in/apply")
    compact = FormModel.compact_for_recipe(form_map)
    serialized = str(compact)

    assert "Aman" not in serialized
    assert "value_source" not in serialized
    assert "has_value" not in serialized
    assert "rect" not in serialized
    assert all("value" not in field for field in compact)
    assert compact[0]["locators"]
