"""Deterministic entry/login decisions: never guess, always ask."""

from __future__ import annotations

from backend.core import decision_policy


def _gateway(text, href="", **extra):
    item = {
        "text": text,
        "href": href,
        "type": "",
        "visible": True,
        "interactable": True,
        "insideForm": False,
    }
    item.update(extra)
    return item


def _dom(gateways=None, inputs=None, url="https://example.gov.in/"):
    return {
        "url": url,
        "title": "",
        "visibleText": "",
        "gateways": gateways or [],
        "inputs": inputs or [],
    }


def test_classify_entry_control_uses_text_and_href():
    assert decision_policy.classify_entry_control("Account Creation", "/frontend/site/signup") == "NEW_REGISTRATION"
    assert decision_policy.classify_entry_control("Get Started", "") == "NEW_REGISTRATION"
    assert decision_policy.classify_entry_control("Login", "/frontend/site/login") == "LOGIN"
    assert decision_policy.classify_entry_control("Resume application", "") == "RESUME"
    assert decision_policy.classify_entry_control("Help", "/help") is None
    assert decision_policy.classify_entry_control("Create Account & Login", "") is None


def test_form_submit_is_not_an_entry_path():
    gateway = _gateway("Create Account", "", type="NEW_REGISTRATION", insideForm=True)
    assert decision_policy.entry_options(_dom([gateway])) == []


def test_two_register_links_collapse_to_one_explicit_option():
    dom = _dom(
        [
            _gateway("Account Creation", "/frontend/site/signup"),
            _gateway("Get Started", "/frontend/site/signup"),
            _gateway("Login", "/frontend/site/login"),
        ]
    )
    options = decision_policy.entry_options(dom)

    assert [option["mode"] for option in options] == ["register", "login"]
    assert options[0]["alternate_count"] == 1
    assert options[0]["element_id"] is None


def test_login_page_with_signup_link_offers_both_paths():
    dom = _dom(
        gateways=[_gateway("Create Account", "/signup")],
        inputs=[
            {
                "index": 0,
                "tagName": "input",
                "type": "password",
                "id": "password",
                "name": "password",
                "label": "Password",
            }
        ],
        url="https://example.gov.in/login",
    )
    form_map = {"page_type": "login"}
    options = decision_policy.entry_options(dom, form_map)

    assert [option["mode"] for option in options] == ["register", "login"]
    login = options[1]
    assert login["source"] == "current_page"
    assert login["element_id"] is None
    assert decision_policy.build_entry_gate(options)["no_default"] is True


def test_login_page_prefers_the_open_page_over_its_own_login_link():
    dom = _dom(
        gateways=[
            _gateway("Login", "/frontend/site/login"),
            _gateway("Account Creation", "/frontend/site/signup"),
        ],
        inputs=[
            {
                "index": 0,
                "tagName": "input",
                "type": "password",
                "id": "password",
                "name": "password",
                "label": "Password",
            }
        ],
        url="https://example.gov.in/frontend/site/login",
    )
    form_map = {"page_type": "login"}
    options = decision_policy.entry_options(dom, form_map)

    login = next(option for option in options if option["mode"] == "login")
    assert login["source"] == "current_page"
    assert login["element_id"] is None
    assert login["alternate_count"] == 1



def test_entry_response_requires_an_exact_match():
    options = [
        {"type": "NEW_REGISTRATION", "mode": "register", "text": "Create Account"},
        {"type": "LOGIN", "mode": "login", "text": "Login"},
    ]

    assert decision_policy.match_entry_response({"mode": "register"}, options)["mode"] == "register"
    assert decision_policy.match_entry_response({"mode": "login"}, options)["mode"] == "login"
    assert decision_policy.match_entry_response({"mode": "resume"}, options) is None
    assert decision_policy.match_entry_response({"text": "Something else"}, options) is None
    assert decision_policy.match_entry_response({}, options) is None


def test_entry_options_ignore_covered_or_hidden_controls():
    dom = _dom(
        [
            _gateway("Login", "/login", covered_by="cookie-banner"),
            _gateway("Register", "/signup", visible=False),
            _gateway("Resume", "/resume"),
        ]
    )
    options = decision_policy.entry_options(dom)

    assert [option["mode"] for option in options] == ["resume"]


def test_login_method_selector_requires_an_explicit_choice():
    dom = _dom(
        inputs=[
            {
                "index": 0,
                "tagName": "select",
                "type": "select",
                "id": "loginform-login_type",
                "name": "loginform-login_type",
                "label": "Login type",
                "options": [
                    {"text": "Mobile & OTP", "value": "mobile_otp"},
                    {"text": "URN & Password", "value": "urn_password"},
                    {"text": "Email & Password", "value": "email_password"},
                ],
            }
        ]
    )
    selection = decision_policy.login_method_options(dom)

    assert selection is not None
    assert [option["method"] for option in selection["options"]] == [
        "mobile_otp",
        "urn_password",
        "email_password",
    ]
    gate = decision_policy.build_login_method_gate(selection)
    assert gate["no_default"] is True

    assert (
        decision_policy.match_login_method_response(
            {"method": "mobile_otp"}, selection
        )["method"]
        == "mobile_otp"
    )
    assert decision_policy.match_login_method_response({"method": "password"}, selection) is None


def test_multiple_identifiers_require_an_explicit_choice():
    dom = _dom(
        inputs=[
            {
                "index": 0,
                "tagName": "input",
                "type": "text",
                "id": "mobile",
                "name": "mobile",
                "label": "Mobile number",
            },
            {
                "index": 1,
                "tagName": "input",
                "type": "email",
                "id": "email",
                "name": "email",
                "label": "Email address",
            },
        ]
    )
    selection = decision_policy.identifier_options(dom)

    assert selection is not None
    assert [option["key"] for option in selection["options"]] == ["mobile", "email"]
    gate = decision_policy.build_identifier_gate(selection)
    assert gate["no_default"] is True
    assert (
        decision_policy.match_identifier_response(
            {"key": "email"}, selection
        )["key"]
        == "email"
    )
    assert decision_policy.match_identifier_response({"key": "aadhaar_number"}, selection) is None


def test_single_identifier_is_not_a_question():
    dom = _dom(
        inputs=[
            {
                "index": 0,
                "tagName": "input",
                "type": "text",
                "id": "mobile",
                "name": "mobile",
                "label": "Mobile number",
            }
        ]
    )
    assert decision_policy.identifier_options(dom) is None
