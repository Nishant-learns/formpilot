"""Model-driven assistant: request shape, tool execution and safety rules."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from backend.core.chat_assistant import FormPilotChatAssistant
from backend.core.llm_client import LLMClient, LLMConfig, LLMError


class ScriptedLLM:
    """Stands in for LLMClient and replays scripted model turns."""

    configured = True

    def __init__(self, turns):
        self.turns = list(turns)
        self.calls = []

    async def complete(self, messages, *, tools=None, tool_choice="auto"):
        self.calls.append(
            {
                "messages": json.loads(json.dumps(messages)),
                "tools": [item["function"]["name"] for item in (tools or [])],
            }
        )
        if not self.turns:
            return {"role": "assistant", "content": "Done."}
        return self.turns.pop(0)


class RecordingOrchestrator:
    def __init__(self, gate=None):
        self.active_gate = gate
        self.paused = False
        self._is_paused = False
        self.page = None
        self.fill_summary = None
        self.fill_failures = []
        self.entry_calls = []
        self.responses = []
        self.entry_option_calls = []

    def pause(self):
        self.paused = self._is_paused = True

    def resume(self):
        self.paused = self._is_paused = False

    def choose_entry_mode(self, mode):
        self.entry_calls.append(mode)
        return {"success": True, "mode": mode, "message": "selected"}

    def choose_entry_option(self, option):
        self.entry_option_calls.append(option)
        self.responses.append({"action": "GATEWAY_CHOICE", **option})
        return {"success": True, "mode": option.get("mode"), "message": "selected"}

    def choose_login_method(self, method):
        return {"success": True, "method": method, "message": "selected"}

    def choose_account_identifier(self, key):
        return {"success": True, "identifier": key, "message": "selected"}

    def submit_user_response(self, data):
        self.responses.append(data)

    def get_state(self):
        return {
            "state": "WAITING_FOR_USER",
            "browser_open": True,
            "current_section": 1,
            "active_gate": self.active_gate,
            "fill_summary": self.fill_summary,
            "fill_failures": self.fill_failures,
            "form_map": {"url": "https://regn.hpsc.gov.in/frontend/user/dashboard"},
            "entry_options": [],
        }


def _assistant(vault_manager, llm, orchestrator=None):
    return FormPilotChatAssistant(
        orchestrator=orchestrator,
        vault_mgr=vault_manager,
        llm_client=llm,
    )


def _tool_call(name, arguments, call_id="call_1"):
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": call_id,
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": json.dumps(arguments),
                },
            }
        ],
    }


DASHBOARD_OPTIONS = [
    {
        "text": "Preview Universal Registration",
        "mode": "register",
        "type": "NEW_REGISTRATION",
        "href": "/frontend/user/dashboard/previewuniversal",
    },
    {
        "text": "Proceed for Universal Registration",
        "mode": "register",
        "type": "NEW_REGISTRATION",
        "href": "/frontend/user/dashboard/identity",
    },
]


# ------------------------------------------------------------------ LLMClient


def _client(handler, tmp_path):
    return LLMClient(
        config_path=str(tmp_path / "llm_config.json"),
        transport=httpx.MockTransport(handler),
    )


def test_llm_client_sends_tools_and_returns_the_message(tmp_path):
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "Choose Proceed.",
                            "tool_calls": [
                                {
                                    "id": "abc",
                                    "type": "function",
                                    "function": {
                                        "name": "choose_option",
                                        "arguments": '{"option": "Proceed"}',
                                    },
                                }
                            ],
                        }
                    }
                ]
            },
        )

    client = _client(handler, tmp_path)
    client.config.api_key = "test-key"
    message = asyncio.run(
        client.complete(
            [{"role": "user", "content": "hi"}],
            tools=[
                {
                    "type": "function",
                    "function": {"name": "choose_option", "parameters": {}},
                }
            ],
        )
    )

    assert seen["url"].endswith("/chat/completions")
    assert seen["auth"] == "Bearer test-key"
    assert seen["body"]["tools"][0]["function"]["name"] == "choose_option"
    assert seen["body"]["tool_choice"] == "auto"
    assert message["tool_calls"][0]["function"]["name"] == "choose_option"


def test_llm_client_refuses_to_call_without_a_key_or_local_endpoint(tmp_path):
    client = LLMClient(config_path=str(tmp_path / "llm_config.json"))
    client.config.api_key = ""
    client.config.base_url = "https://api.openai.com/v1"

    assert client.configured is False
    with pytest.raises(LLMError) as excinfo:
        asyncio.run(client.complete([{"role": "user", "content": "hi"}]))
    assert excinfo.value.code == "llm_not_configured"


def test_llm_client_accepts_a_local_endpoint_without_a_key(tmp_path):
    client = LLMClient(config_path=str(tmp_path / "llm_config.json"))
    client.config.api_key = ""
    client.config.base_url = "http://127.0.0.1:11434/v1"

    assert client.configured is True
    assert client.public_config()["local"] is True


def test_llm_client_surfaces_http_errors(tmp_path):
    def handler(request):
        return httpx.Response(401, json={"error": {"message": "bad key"}})

    client = _client(handler, tmp_path)
    client.config.api_key = "nope"

    with pytest.raises(LLMError) as excinfo:
        asyncio.run(client.complete([{"role": "user", "content": "hi"}]))
    assert excinfo.value.status_code == 401
    assert "bad key" in str(excinfo.value)


def test_llm_config_is_saved_and_blank_key_keeps_the_saved_one(tmp_path, monkeypatch):
    for name in (
        "FORMPILOT_LLM_API_KEY",
        "OPENAI_API_KEY",
        "FORMPILOT_LLM_BASE_URL",
        "FORMPILOT_LLM_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)
    client = LLMClient(config_path=str(tmp_path / "llm_config.json"))
    client.save_config(
        LLMConfig(api_key="secret-key", base_url="https://example.test/v1", model="m1")
    )
    assert (tmp_path / "llm_config.json").exists()

    client.save_config(
        LLMConfig(api_key="***", base_url="https://example.test/v1", model="m2"),
        preserve_key=True,
    )
    reloaded = LLMClient(config_path=str(tmp_path / "llm_config.json"))
    assert reloaded.config.model == "m2"
    assert reloaded.config.api_key == "secret-key"
    assert reloaded.public_config()["api_key"] == "***"


# ------------------------------------------------------------- assistant tools


def test_model_reply_is_used_verbatim_and_sees_the_live_gate(vault_manager):
    orchestrator = RecordingOrchestrator(
        gate={"gate_type": "GATEWAY_DECISION", "options": DASHBOARD_OPTIONS}
    )
    llm = ScriptedLLM([{"role": "assistant", "content": "You are on the dashboard."}])
    assistant = _assistant(vault_manager, llm, orchestrator)

    response = asyncio.run(assistant.handle_message("where am i?"))

    assert response["reply"] == "You are on the dashboard."
    assert response["action_taken"] == "AI_REPLY"
    system_prompt = llm.calls[0]["messages"][0]["content"]
    assert "Proceed for Universal Registration" in system_prompt
    assert "regn.hpsc.gov.in" in system_prompt
    assert "choose_option" in llm.calls[0]["tools"]


def test_ambiguous_typo_asks_which_option_instead_of_guessing(vault_manager):
    orchestrator = RecordingOrchestrator(
        gate={"gate_type": "GATEWAY_DECISION", "options": DASHBOARD_OPTIONS}
    )
    llm = ScriptedLLM(
        [
            _tool_call("choose_option", {"option": "universal registaration"}),
            {
                "role": "assistant",
                "content": "Two links match. Do you want Preview or Proceed?",
            },
        ]
    )
    assistant = _assistant(vault_manager, llm, orchestrator)

    response = asyncio.run(assistant.handle_message("clcik universal registaration"))

    assert orchestrator.entry_option_calls == []
    assert orchestrator.responses == []
    assert "Preview" in response["reply"] and "Proceed" in response["reply"]
    tool_result = json.loads(llm.calls[1]["messages"][-1]["content"])
    assert tool_result["ok"] is False
    assert tool_result["ambiguous"] is True
    assert len(tool_result["options"]) == 2


def test_a_distinct_typo_selects_the_exact_link(vault_manager):
    orchestrator = RecordingOrchestrator(
        gate={"gate_type": "GATEWAY_DECISION", "options": DASHBOARD_OPTIONS}
    )
    llm = ScriptedLLM(
        [
            _tool_call("choose_option", {"option": "preveiw universal registration"}),
            {"role": "assistant", "content": "Opening the preview page."},
        ]
    )
    assistant = _assistant(vault_manager, llm, orchestrator)

    response = asyncio.run(assistant.handle_message("open the preveiw universal registration page"))

    assert len(orchestrator.entry_option_calls) == 1
    assert (
        orchestrator.entry_option_calls[0]["text"] == "Preview Universal Registration"
    )
    assert response["action_taken"] == "ENTRY_MODE_SELECTED"
    assert response["reply"] == "Opening the preview page."


def test_human_only_checkpoints_cannot_be_answered_from_chat(vault_manager):
    orchestrator = RecordingOrchestrator(
        gate={
            "gate_type": "CAPTCHA_SOLVE",
            "options": [{"text": "Submit captcha"}],
        }
    )
    llm = ScriptedLLM(
        [
            _tool_call("choose_option", {"option": "Submit captcha"}),
            {"role": "assistant", "content": "Please type the characters yourself."},
        ]
    )
    assistant = _assistant(vault_manager, llm, orchestrator)

    response = asyncio.run(assistant.handle_message("submit the captcha"))

    assert orchestrator.responses == []
    tool_result = json.loads(llm.calls[1]["messages"][-1]["content"])
    assert tool_result["human_only"] is True
    assert tool_result["gate_type"] == "CAPTCHA_SOLVE"
    assert response["action_taken"] == "AI_REPLY"


def test_update_tool_changes_the_vault_and_reports_it(vault_manager):
    orchestrator = RecordingOrchestrator()
    llm = ScriptedLLM(
        [
            _tool_call(
                "update_saved_detail",
                {"key": "father_name", "value": "Rajesh Kumar Sharma"},
            ),
            {"role": "assistant", "content": "Updated your father's name."},
        ]
    )
    assistant = _assistant(vault_manager, llm, orchestrator)

    response = asyncio.run(
        assistant.handle_message("change my father's name to Rajesh Kumar Sharma")
    )

    assert vault_manager.vault.father_name == "Rajesh Kumar Sharma"
    assert response["field_updated"] == "Father's Name"
    assert response["new_value"] == "Rajesh Kumar Sharma"
    assert response["action_taken"] == "FIELD_UPDATED"


def test_status_tool_reads_state_without_inventing_verified_fields(vault_manager):
    orchestrator = RecordingOrchestrator()
    orchestrator.fill_summary = {
        "status": "PARTIAL",
        "attempted": 3,
        "verified": 2,
        "failed": 1,
        "skipped": 0,
    }
    llm = ScriptedLLM(
        [
            _tool_call("get_application_status", {}),
            {"role": "assistant", "content": "2 of 3 fields verified; 1 failed."},
        ]
    )
    assistant = _assistant(vault_manager, llm, orchestrator)

    asyncio.run(assistant.handle_message("how many fields are done?"))

    tool_result = json.loads(llm.calls[1]["messages"][-1]["content"])
    assert tool_result["ok"] is True
    assert tool_result["fill_summary"]["verified"] == 2
    assert tool_result["fill_summary"]["failed"] == 1


def test_unreachable_model_does_not_touch_the_application(vault_manager):
    class BrokenLLM:
        configured = True

        async def complete(self, *args, **kwargs):
            raise LLMError("The assistant could not reach the model.")

    orchestrator = RecordingOrchestrator()
    assistant = _assistant(vault_manager, BrokenLLM(), orchestrator)

    response = asyncio.run(assistant.handle_message("pause"))

    assert response["action_taken"] == "AI_UNAVAILABLE"
    assert orchestrator.paused is False
    assert "untouched" in response["reply"].lower()
