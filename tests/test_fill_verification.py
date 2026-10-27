"""The UI must only report a form as filled when the portal kept the values."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from backend.core.orchestrator import FormPilotOrchestrator

from tests.browser_helpers import run_with_page


class FakeVault:
    def __init__(self, values=None):
        self.values = values or {}

    def find_field_value(self, key):
        return self.values.get(key)

    def get_formatted_dob(self, fmt):
        return self.values.get("dob")


def _orchestrator(page, values=None):
    orchestrator = FormPilotOrchestrator()
    orchestrator.page = page
    orchestrator.target_url = page.url
    orchestrator.is_running = True
    orchestrator.vault_mgr = SimpleNamespace(vault=FakeVault(values))
    return orchestrator


def test_fill_is_recorded_only_after_a_fresh_scan_verifies_it():
    async def scenario(page):
        await page.set_content(
            """
            <html><body>
              <label for="full_name">Full Name</label>
              <input id="full_name" name="full_name" type="text">
            </body></html>
            """
        )
        orchestrator = _orchestrator(page, {"full_name": "Nishant Kumar"})
        dom = await orchestrator._scan_dom()

        verified = await orchestrator._fill_form(dom)

        assert verified == 1
        assert await page.input_value("#full_name") == "Nishant Kumar"
        assert orchestrator.fill_summary["status"] == "FILLED"
        assert orchestrator.fill_summary["verified"] == 1
        assert orchestrator.fill_summary["attempted"] == 1
        assert len(orchestrator.filled_audit) == 1
        assert orchestrator.fill_failures == []

    run_with_page(scenario)


def test_a_value_cleared_by_the_portal_is_reported_as_failed():
    async def scenario(page):
        await page.set_content(
            """
            <html><body>
              <label for="full_name">Full Name</label>
              <input id="full_name" name="full_name" type="text"
                     oninput="setTimeout(() => { this.value = ''; }, 20)">
            </body></html>
            """
        )
        orchestrator = _orchestrator(page, {"full_name": "Nishant Kumar"})
        dom = await orchestrator._scan_dom()

        verified = await orchestrator._fill_form(dom)

        assert verified == 0
        assert orchestrator.fill_summary["status"] == "FAILED"
        assert orchestrator.fill_summary["verified"] == 0
        assert orchestrator.fill_summary["failed"] == 1
        assert orchestrator.filled_audit == []
        assert orchestrator.fill_failures[0]["field_label"].startswith("Full Name")
        assert orchestrator.fill_failures[0]["status"] == "FAILED"

    run_with_page(scenario)


def test_fill_incomplete_gate_rechecks_instead_of_continuing():
    async def scenario():
        orchestrator = FormPilotOrchestrator()
        orchestrator.is_running = True
        orchestrator.state = "RUNNING"
        orchestrator.fill_summary = {
            "status": "PARTIAL",
            "attempted": 2,
            "verified": 1,
            "failed": 1,
            "skipped": 0,
        }
        orchestrator.fill_failures = [
            {
                "field_label": "Email",
                "vault_key": "email",
                "status": "FAILED",
                "reason": "The portal did not keep the value that was entered.",
            }
        ]

        async def respond():
            await asyncio.sleep(0.05)
            assert orchestrator.active_gate["gate_type"] == "FILL_INCOMPLETE"
            orchestrator.submit_user_response({"action": "FILL_RECHECK"})

        responder = asyncio.create_task(respond())
        state = await asyncio.wait_for(orchestrator._fill_incomplete_checkpoint(), timeout=3)
        await responder

        assert state == "recheck"
        assert orchestrator.active_gate is None

    asyncio.run(scenario())


def test_fill_incomplete_gate_requires_a_choice_not_a_dismissal():
    async def scenario():
        orchestrator = FormPilotOrchestrator()
        orchestrator.is_running = True
        orchestrator.state = "RUNNING"
        orchestrator.fill_summary = {
            "status": "FAILED",
            "attempted": 1,
            "verified": 0,
            "failed": 1,
            "skipped": 0,
        }
        orchestrator.fill_failures = [
            {"field_label": "Full Name", "vault_key": "full_name", "status": "FAILED"}
        ]

        async def respond():
            await asyncio.sleep(0.05)
            orchestrator.submit_user_response({"action": "DISMISS"})
            await asyncio.sleep(0.05)
            orchestrator.submit_user_response({"action": "CONTINUE"})

        responder = asyncio.create_task(respond())
        state = await asyncio.wait_for(orchestrator._fill_incomplete_checkpoint(), timeout=3)
        await responder

        assert state == "continue"
        assert orchestrator.active_gate is None

    asyncio.run(scenario())
