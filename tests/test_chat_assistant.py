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
