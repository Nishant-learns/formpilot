"""Always-available browser takeover: exclusive control and return-and-rescan."""

from __future__ import annotations

import asyncio

from backend.core.orchestrator import FormPilotOrchestrator


class FakeLive:
    """Minimal stand-in for the live browser control channel."""

    def __init__(self):
        self.session_id = "live-test"
        self.closed = False
        self.control_enabled = False
        self.control_reason = ""

    async def stop(self):
        self.closed = True

    def set_allow_control(self, enabled, reason=""):
        self.control_enabled = bool(enabled)
        if reason:
            self.control_reason = reason

    def public_info(self):
        return {
            "session_id": "live-test",
            "control_enabled": self.control_enabled,
            "control_reason": self.control_reason,
        }


class FakePage:
    def __init__(self, closed=False):
        self._closed = closed

    def is_closed(self):
        return self._closed


def _orchestrator(*, live=True):
    orchestrator = FormPilotOrchestrator()
    orchestrator.is_running = True
    orchestrator.state = "RUNNING"
    orchestrator.live = FakeLive() if live else None
    return orchestrator


def test_takeover_pauses_a_driving_run_and_gives_exclusive_control():
    orchestrator = _orchestrator()

    result = asyncio.run(orchestrator.take_human_control())

    assert result["success"] is True
    assert orchestrator.state == "PAUSED"
    assert orchestrator.paused is True
    assert orchestrator.live.control_enabled is True
    assert result["takeover"]["active"] is True
    assert result["takeover"]["paused_run"] is True


def test_takeover_is_refused_without_a_live_browser():
    orchestrator = _orchestrator(live=False)

    result = asyncio.run(orchestrator.take_human_control())

    assert result["success"] is False
    assert "no live browser" in result["message"].lower()
    assert orchestrator.state == "RUNNING"


def test_takeover_is_idempotent_while_the_human_owns_the_page():
    orchestrator = _orchestrator()
    asyncio.run(orchestrator.take_human_control())

    again = asyncio.run(orchestrator.take_human_control())

    assert again["success"] is True
    assert again["already"] is True
    assert orchestrator.live.control_enabled is True


def test_returning_control_rescans_the_page_and_stays_paused():
    orchestrator = _orchestrator()
    asyncio.run(orchestrator.take_human_control())
    orchestrator.page = FakePage()
    calls = {}

    async def fake_brief(*, refresh=False, adopt_blueprint=False):
        calls["refresh"] = refresh
        calls["adopt_blueprint"] = adopt_blueprint
        return {"summary_line": "fresh brief"}

    orchestrator.get_page_brief = fake_brief

    result = asyncio.run(orchestrator.return_human_control())

    assert result["success"] is True
    assert result["refreshed"] is True
    assert result["page_brief"] == {"summary_line": "fresh brief"}
    assert calls == {"refresh": True, "adopt_blueprint": True}
    # The operator adopts the page the human left behind, but does not act.
    assert orchestrator.live.control_enabled is False
    assert result["paused"] is True
    assert orchestrator.state == "PAUSED"
    assert result["takeover"]["active"] is False


def test_returning_control_is_refused_when_the_human_does_not_have_it():
    orchestrator = _orchestrator()

    result = asyncio.run(orchestrator.return_human_control())

    assert result["success"] is False
    assert "not in human control" in result["message"].lower()


def test_a_checkpoint_keeps_the_human_in_control_and_does_not_double_pause():
    orchestrator = _orchestrator()
    orchestrator.state = "WAITING_FOR_USER"
    orchestrator.active_gate = {"gate_type": "GATEWAY_DECISION"}

    result = asyncio.run(orchestrator.take_human_control())

    assert result["success"] is True
    assert orchestrator.paused is False
    assert orchestrator.state == "WAITING_FOR_USER"
    assert result["takeover"]["paused_run"] is False


def test_a_gate_closing_does_not_steal_control_from_the_human():
    orchestrator = _orchestrator()
    asyncio.run(orchestrator.take_human_control())

    orchestrator._release_live_control("The agent is driving again.")

    assert orchestrator.live.control_enabled is True


def test_stop_clears_takeover_state():
    orchestrator = _orchestrator()
    asyncio.run(orchestrator.take_human_control())

    asyncio.run(orchestrator.stop())

    assert orchestrator.takeover_state()["active"] is False
    assert orchestrator.takeover_state()["paused_run"] is False


def test_takeover_endpoints_take_and_return_control(client, monkeypatch):
    from backend import main

    orchestrator = main.orchestrator
    live = FakeLive()
    monkeypatch.setattr(orchestrator, "live", live)
    monkeypatch.setattr(orchestrator, "is_running", True)
    monkeypatch.setattr(orchestrator, "state", "RUNNING")
    monkeypatch.setattr(orchestrator, "page", None)
    monkeypatch.setattr(orchestrator, "paused", False)
    monkeypatch.setattr(orchestrator, "_is_paused", False)
    monkeypatch.setattr(orchestrator, "_takeover_active", False)
    monkeypatch.setattr(orchestrator, "_takeover_paused_run", False)

    taken = client.post("/api/agent/takeover").json()

    assert taken["success"] is True
    assert taken["takeover"]["active"] is True
    assert live.control_enabled is True

    returned = client.post("/api/agent/takeover/return").json()

    assert returned["success"] is True
    assert returned["takeover"]["active"] is False
    assert returned["paused"] is True
    assert live.control_enabled is False


def test_returning_control_at_a_checkpoint_keeps_the_human_able_to_act():
    orchestrator = _orchestrator()
    orchestrator.state = "WAITING_FOR_USER"
    orchestrator.active_gate = {"gate_type": "GATEWAY_DECISION"}
    asyncio.run(orchestrator.take_human_control())

    result = asyncio.run(orchestrator.return_human_control())

    assert result["success"] is True
    assert result["state"] == "WAITING_FOR_USER"
    # The checkpoint still needs an answer, so the human keeps the page.
    assert orchestrator.live.control_enabled is True
    assert "checkpoint" in orchestrator.live.control_reason.lower()
