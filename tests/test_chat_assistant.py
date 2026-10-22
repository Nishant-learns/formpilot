import asyncio
import pytest
import os
from backend.core.vault import VaultManager
from backend.core.tinyfish_client import TinyFishClient
from backend.core.chat_assistant import CyberBhaiyaChatAssistant

def test_chat_faq_fees():
    async def _run():
        vault_mgr = VaultManager.get_instance()
        tf_client = TinyFishClient()
        assistant = CyberBhaiyaChatAssistant(orchestrator=None, vault_mgr=vault_mgr, tinyfish_client=tf_client)
        
        resp = await assistant.handle_message("Bhaiya form ki fees kitni hai?")
        assert resp["action_taken"] == "FAQ_ANSWER"
        assert "₹500.00" in resp["reply"]
        assert "Pre-Payment Safety Lock" in resp["reply"]
    asyncio.run(_run())

def test_chat_faq_biometrics():
    async def _run():
        vault_mgr = VaultManager.get_instance()
        tf_client = TinyFishClient()
        assistant = CyberBhaiyaChatAssistant(orchestrator=None, vault_mgr=vault_mgr, tinyfish_client=tf_client)
        
        resp = await assistant.handle_message("Photo aur signature ka size kya chahiye?")
        assert resp["action_taken"] == "FAQ_ANSWER"
        assert "350x350" in resp["reply"]
        assert "140x60" in resp["reply"]
    asyncio.run(_run())

def test_chat_field_edit_and_vault_mutation():
    async def _run():
        vault_mgr = VaultManager.get_instance()
        tf_client = TinyFishClient()
        assistant = CyberBhaiyaChatAssistant(orchestrator=None, vault_mgr=vault_mgr, tinyfish_client=tf_client)
        
        resp = await assistant.handle_message("father name badal kar Shri Rajesh Kumar Sharma kar do")
        assert resp["action_taken"] == "FIELD_UPDATED"
        assert resp["new_value"] == "Shri Rajesh Kumar Sharma"
        assert vault_mgr.vault.father_name == "Shri Rajesh Kumar Sharma"
    asyncio.run(_run())

def test_chat_workflow_pause_and_resume():
    async def _run():
        vault_mgr = VaultManager.get_instance()
        tf_client = TinyFishClient()
        
        class DummyOrchestrator:
            def __init__(self):
                self._is_paused = False
                self.active_gate = None
        
        dummy_orch = DummyOrchestrator()
        assistant = CyberBhaiyaChatAssistant(orchestrator=dummy_orch, vault_mgr=vault_mgr, tinyfish_client=tf_client)
        
        pause_resp = await assistant.handle_message("Bhaiya ek minute ruko pause karo")
        assert pause_resp["action_taken"] == "PAUSED"
        assert dummy_orch._is_paused is True
        
        resume_resp = await assistant.handle_message("sab sahi hai resume karo aage chalo")
        assert resume_resp["action_taken"] == "RESUMED"
        assert dummy_orch._is_paused is False
    asyncio.run(_run())

def test_chat_tinyfish_live_search():
    async def _run():
        vault_mgr = VaultManager.get_instance()
        tf_client = TinyFishClient()
        assistant = CyberBhaiyaChatAssistant(orchestrator=None, vault_mgr=vault_mgr, tinyfish_client=tf_client)
        
        resp = await assistant.handle_message("latest rrb ntpc notification 2026 exam date")
        assert resp["action_taken"] == "TINYFISH_SEARCH"
        assert "TinyFish Live Search Result" in resp["reply"]
    asyncio.run(_run())
