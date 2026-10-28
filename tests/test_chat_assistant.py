"""Candidate-facing assistant behaviour."""

from __future__ import annotations

import asyncio

from backend.core.chat_assistant import FormPilotChatAssistant
from backend.core.tinyfish_client import TinyFishError


class FakeTinyFish:
    is_configured = True

    def __init__(self, results=None, error=None):
        self.results = results or []
        self.error = error

    async def search(self, *args, **kwargs):
        if self.error:
            raise self.error
        return self.results


class FakeOrchestrator:
    def __init__(self):
        self._is_paused = False
        self.paused = False
        self.page = None
        self.active_gate = None

    def pause(self):
        self._is_paused = True
        self.paused = True

    def resume(self):
        self._is_paused = False
        self.paused = False

    async def stop(self):
        self.stopped = True

    def get_state(self):
        return {
            "state": "RUNNING",
            "current_section": 2,
            "filled_audit": [{"field": "full_name"}],
            "active_gate": None,
        }


def _assistant(vault_manager, tinyfish=None, orchestrator=None):
    return FormPilotChatAssistant(
        orchestrator=orchestrator,
        vault_mgr=vault_manager,
        tinyfish_client=tinyfish or FakeTinyFish(),
    )


def test_fee_question_is_answered_without_claiming_to_pay(vault_manager):
    assistant = _assistant(vault_manager)

    response = asyncio.run(assistant.handle_message("What is the application fee?"))

    assert response["action_taken"] == "FAQ_ANSWER"
    assert "fee depends" in response["reply"].lower()
    assert "payment yourself" in response["reply"].lower()
    assert "₹" not in response["reply"]


def test_document_size_question_uses_common_ranges(vault_manager):
    assistant = _assistant(vault_manager)

    response = asyncio.run(assistant.handle_message("photo aur signature ka size kya chahiye?"))

    assert response["action_taken"] == "FAQ_ANSWER"
    assert "350×350" in response["reply"]
    assert "140×60" in response["reply"]
    assert "20–50 KB" in response["reply"]


def test_identity_question_is_honest_about_government_status(vault_manager):
    assistant = _assistant(vault_manager)

    response = asyncio.run(assistant.handle_message("Are you a government website?"))

    assert response["action_taken"] == "FAQ_ANSWER"
    assert "not a government website" in response["reply"].lower()
    assert "independent application assistant" in response["reply"].lower()


def test_field_edit_updates_vault_and_confirmation_field(vault_manager):
    assistant = _assistant(vault_manager)

    response = asyncio.run(
        assistant.handle_message("change my father's name to Rajesh Kumar Sharma")
    )

    assert response["action_taken"] == "FIELD_UPDATED"
    assert response["new_value"] == "Rajesh Kumar Sharma"
    assert vault_manager.vault.father_name == "Rajesh Kumar Sharma"
    assert vault_manager.vault.verify_father_name == "Rajesh Kumar Sharma"


def test_sensitive_edit_is_masked_in_the_reply(vault_manager):
    assistant = _assistant(vault_manager)

    response = asyncio.run(
        assistant.handle_message("change my aadhaar number to 1234 5678 9012")
    )

    assert response["action_taken"] == "FIELD_UPDATED"
    assert response["new_value"] == "********9012"
    assert "1234 5678 9012" not in response["reply"]
    assert vault_manager.vault.aadhaar_number == "123456789012"


def test_pause_resume_and_status_workflow(vault_manager):
    orchestrator = FakeOrchestrator()
    assistant = _assistant(vault_manager, orchestrator=orchestrator)

    paused = asyncio.run(assistant.handle_message("pause kar do"))
    assert paused["action_taken"] == "PAUSED"
    assert orchestrator.paused is True

    resumed = asyncio.run(assistant.handle_message("resume"))
    assert resumed["action_taken"] == "RESUMED"
    assert orchestrator.paused is False

    status = asyncio.run(assistant.handle_message("what is my status?"))
    assert status["action_taken"] == "STATUS_REPORT"
    assert "Current status" in status["reply"]
    assert "never submits" in status["reply"].lower()


def test_stop_does_not_claim_anything_was_submitted(vault_manager):
    orchestrator = FakeOrchestrator()
    assistant = _assistant(vault_manager, orchestrator=orchestrator)

    response = asyncio.run(assistant.handle_message("stop please"))

    assert response["action_taken"] == "STOPPED"
    assert orchestrator.stopped is True
    assert "nothing was submitted" in response["reply"].lower()


def test_live_search_formats_results_and_adds_a_disclaimer(vault_manager):
    tinyfish = FakeTinyFish(
        results=[
            {
                "title": "SSC notice",
                "url": "https://ssc.gov.in/notice",
                "snippet": "The official notice is available.",
            }
        ]
    )
    assistant = _assistant(vault_manager, tinyfish=tinyfish)

    response = asyncio.run(assistant.handle_message("latest ssc exam date notification"))

    assert response["action_taken"] == "LIVE_SEARCH"
    assert "Live web results" in response["reply"]
    assert "https://ssc.gov.in/notice" in response["reply"]
    assert "not an official confirmation" in response["reply"]
    assert response["source_url"] == "https://ssc.gov.in/notice"


def test_live_search_failure_is_graceful(vault_manager):
    assistant = _assistant(
        vault_manager,
        tinyfish=FakeTinyFish(error=TinyFishError("network unavailable")),
    )

    response = asyncio.run(assistant.handle_message("latest exam date notification"))

    assert response["action_taken"] == "SEARCH_UNAVAILABLE"
    assert "couldn't reach live web search" in response["reply"].lower()


def test_empty_message_prompts_for_input(vault_manager):
    assistant = _assistant(vault_manager)

    response = asyncio.run(assistant.handle_message("   "))

    assert response["action_taken"] == "CONVERSATION"
    assert "type a question" in response["reply"].lower()


class DecisionOrchestrator(FakeOrchestrator):
    """Minimal orchestrator that records explicit decision calls."""

    def __init__(self):
        super().__init__()
        self.entry_calls = []
        self.method_calls = []
        self.identifier_calls = []
        self.responses = []
        self.fill_summary = None
        self.fill_failures = []
        self._entry_mode = None
        self._login_method = None
        self._login_identifier = None

    def choose_entry_mode(self, mode):
        self.entry_calls.append(mode)
        self._entry_mode = mode
        return {"success": True, "mode": mode, "message": "selected"}

    def choose_login_method(self, method):
        self.method_calls.append(method)
        self._login_method = method
        return {"success": True, "method": method, "message": "selected"}

    def choose_account_identifier(self, key):
        self.identifier_calls.append(key)
        self._login_identifier = key
        return {"success": True, "identifier": key, "message": "selected"}

    def submit_user_response(self, data):
        self.responses.append(data)

    def get_state(self):
        state = super().get_state()
        state.update(
            {
                "fill_summary": self.fill_summary,
                "fill_failures": self.fill_failures,
                "entry_mode": self._entry_mode,
                "login_method": self._login_method,
                "login_identifier": self._login_identifier,
            }
        )
        return state


def test_chat_selects_registration_when_the_entry_gate_is_open(vault_manager):
    orchestrator = DecisionOrchestrator()
    orchestrator.active_gate = {
        "gate_type": "GATEWAY_DECISION",
        "options": [
            {"text": "Account Creation", "mode": "register", "type": "NEW_REGISTRATION"},
            {"text": "Login", "mode": "login", "type": "LOGIN"},
        ],
    }
    assistant = _assistant(vault_manager, orchestrator=orchestrator)

    response = asyncio.run(assistant.handle_message("hey i need to register first"))

    assert response["action_taken"] == "ENTRY_MODE_SELECTED"
    assert response["entry_mode"] == "register"
    assert orchestrator.entry_calls == ["register"]
    assert "Account Creation" in response["reply"]


def test_chat_remembers_an_entry_request_before_the_entry_page(vault_manager):
    orchestrator = DecisionOrchestrator()
    assistant = _assistant(vault_manager, orchestrator=orchestrator)

    response = asyncio.run(assistant.handle_message("I need to create a new account"))

    assert response["action_taken"] == "ENTRY_MODE_REQUESTED"
    assert orchestrator.entry_calls == ["register"]
    assert "will not guess" in response["reply"].lower()


def test_chat_selects_a_login_method_without_defaulting(vault_manager):
    orchestrator = DecisionOrchestrator()
    orchestrator.active_gate = {
        "gate_type": "LOGIN_METHOD",
        "options": [
            {"method": "mobile_otp", "value": "mobile_otp", "label": "Mobile number and OTP"},
            {"method": "urn_password", "value": "urn_password", "label": "URN and password"},
        ],
    }
    assistant = _assistant(vault_manager, orchestrator=orchestrator)

    response = asyncio.run(assistant.handle_message("use mobile OTP please"))

    assert response["action_taken"] == "LOGIN_METHOD_SELECTED"
    assert orchestrator.method_calls == ["mobile_otp"]
    assert "Mobile number and OTP" in response["reply"]


def test_chat_selects_an_account_identifier_without_defaulting(vault_manager):
    orchestrator = DecisionOrchestrator()
    orchestrator.active_gate = {
        "gate_type": "ACCOUNT_IDENTIFIER",
        "options": [
            {"key": "mobile", "text": "Mobile number"},
            {"key": "email", "text": "Email address"},
        ],
    }
    assistant = _assistant(vault_manager, orchestrator=orchestrator)

    response = asyncio.run(assistant.handle_message("use my email address"))

    assert response["action_taken"] == "ACCOUNT_IDENTIFIER_SELECTED"
    assert orchestrator.identifier_calls == ["email"]
    assert "Email address" in response["reply"]


def test_chat_rechecks_an_incomplete_fill(vault_manager):
    orchestrator = DecisionOrchestrator()
    orchestrator.active_gate = {"gate_type": "FILL_INCOMPLETE"}
    orchestrator.fill_summary = {
        "status": "PARTIAL",
        "attempted": 3,
        "verified": 2,
        "failed": 1,
        "skipped": 0,
    }
    assistant = _assistant(vault_manager, orchestrator=orchestrator)

    response = asyncio.run(assistant.handle_message("recheck the fields"))

    assert response["action_taken"] == "FILL_RECHECK"
    assert orchestrator.responses == [{"action": "FILL_RECHECK"}]


def test_status_report_never_claims_an_incomplete_fill(vault_manager):
    orchestrator = DecisionOrchestrator()
    orchestrator._entry_mode = "register"
    orchestrator.fill_summary = {
        "status": "PARTIAL",
        "attempted": 3,
        "verified": 2,
        "failed": 1,
        "skipped": 0,
    }
    assistant = _assistant(vault_manager, orchestrator=orchestrator)

    response = asyncio.run(assistant.handle_message("what is my status?"))

    assert response["action_taken"] == "STATUS_REPORT"
    assert "2 of 3" in response["reply"]
    assert "1 failed" in response["reply"]
    assert "Entry path: register" in response["reply"]



def test_saved_detail_reads_a_derived_name_part(vault_manager):
    assistant = _assistant(vault_manager)

    result = assistant._tool_get_saved("middle_name")

    assert result["ok"] is True
    assert result["value"] == "Kumar"
    assert result["provenance"] == "derived"


def test_editing_a_name_part_stores_an_explicit_fact(vault_manager):
    from backend.core.facts import FactBook

    assistant = _assistant(vault_manager)

    response = asyncio.run(assistant.apply_field_update("first_name", "Nishant"))

    assert response["action_taken"] == "FIELD_UPDATED"
    assert response["field_updated"] == "first_name"
    assert FactBook.get_instance().resolve("first_name").value == "Nishant"
    # The profile itself is not rewritten; the explicit fact wins instead.
    assert vault_manager.vault.full_name == "Aman Kumar Sharma"


def test_status_context_and_page_tool_include_the_page_brief(vault_manager):
    class BriefOrchestrator(FakeOrchestrator):
        def get_state(self):
            state = super().get_state()
            state["page_brief"] = {
                "summary_line": "Personal Details · section_form · 1 question",
                "page_type": "SECTION_FORM",
                "purpose": "Collect identity details.",
                "confidence": 0.9,
                "sections": [
                    {
                        "heading": "Personal Details",
                        "questions": [
                            {
                                "asked": "First Name",
                                "concept": "first_name",
                                "required": True,
                                "fact_status": "known",
                                "fact_provenance": "derived",
                            }
                        ],
                    }
                ],
                "paths": [
                    {"label": "Save & Next", "kind": "application_action", "needs_human_choice": False}
                ],
                "human_only": ["final_submit"],
                "ambiguities": [],
                "fact_summary": {"total": 3, "explicit": 1, "derived": 2, "unverified": 0},
            }
            return state

    assistant = _assistant(vault_manager, orchestrator=BriefOrchestrator())

    context = assistant._state_context()
    page = assistant._tool_page()

    assert context["page_brief"]["page_type"] == "SECTION_FORM"
    assert context["page_brief"]["questions"][0]["fact_status"] == "known"
    assert page["brief"]["paths"][0]["label"] == "Save & Next"


def test_system_prompt_uses_the_shared_brief_without_asking_the_human_to_classify(vault_manager):
    assistant = _assistant(vault_manager)

    prompt = assistant._system_prompt()

    assert "page brief" in prompt.lower()
    assert "needs_confirmation" in prompt
    assert "known_absent" in prompt
    assert "Never ask the candidate to classify the page" in prompt
