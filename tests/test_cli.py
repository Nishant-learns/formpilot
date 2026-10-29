"""Operator CLI: local reads, safe actions, and the human-only boundary."""

from __future__ import annotations

import json

import pytest

from backend import cli
from backend.core.run_store import RunStore


def _make_run(store: RunStore, run_id: str = "run-cli") -> str:
    store.start(run_id, {"query": "hpsc", "run_mode": "fill"})
    store.record_step(run_id, "run", output={"query": "hpsc"})
    store.record_step(run_id, "perceive", output={"page_type": "form", "field_count": 4})
    store.record_step(
        run_id,
        "fill",
        output={"attempted": 4, "verified": 3, "failed": 1, "skipped": 0},
    )
    store.record_step(run_id, "submit", status="waiting", output={"final_action": False})
    store.finish(run_id, "AWAITING_PAYMENT")
    return run_id


def test_runs_lists_a_run_from_the_local_journal(tmp_path, capsys):
    store = RunStore(tmp_path / "runs")
    _make_run(store)

    code = cli.main(["--runs-dir", str(tmp_path / "runs"), "runs"])

    output = capsys.readouterr().out
    assert code == 0
    assert "run-cli" in output
    assert "AWAITING_PAYMENT" in output


def test_show_answers_what_to_do_now(tmp_path, capsys):
    store = RunStore(tmp_path / "runs")
    _make_run(store)

    code = cli.main(["--runs-dir", str(tmp_path / "runs"), "show", "run-cli"])

    output = capsys.readouterr().out
    assert code == 0
    assert "DO THIS NOW: Complete the payment yourself" in output
    assert "the portal kept 3 of 4" in output


def test_show_json_is_machine_readable(tmp_path, capsys):
    store = RunStore(tmp_path / "runs")
    _make_run(store)

    code = cli.main(["--runs-dir", str(tmp_path / "runs"), "show", "run-cli", "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["run_id"] == "run-cli"
    assert payload["what_to_do_now"]["title"] == "Complete the payment yourself"


def test_report_writes_the_printable_page(tmp_path, capsys):
    store = RunStore(tmp_path / "runs")
    _make_run(store)
    out = tmp_path / "report.html"

    code = cli.main(
        ["--runs-dir", str(tmp_path / "runs"), "report", "run-cli", "--out", str(out)]
    )

    assert code == 0
    assert "What happened" in out.read_text(encoding="utf-8")


def test_a_missing_run_is_a_clean_error(tmp_path, capsys):
    code = cli.main(["--runs-dir", str(tmp_path / "runs"), "show", "run-missing"])

    assert code == cli.EXIT_USAGE
    assert "Run not found" in capsys.readouterr().err


# --------------------------------------------------------------- safe actions


@pytest.mark.parametrize(
    "action",
    ["OTP_SUBMIT", "CAPTCHA_SUBMIT", "PAY", "SUBMIT", "LIVE_PHOTO", "HANDOFF_COMPLETE"],
)
def test_the_terminal_refuses_human_only_actions(action, capsys):
    code = cli.main(["answer", action])

    assert code == cli.EXIT_USAGE
    assert "cockpit" in capsys.readouterr().err


def test_a_safe_action_is_posted_to_the_cockpit(monkeypatch, capsys):
    calls = []

    def fake_request(method, path, payload=None, **kwargs):
        calls.append((method, path, payload))
        return {"success": True}

    monkeypatch.setattr(cli, "_request", fake_request)

    code = cli.main(["answer", "FILL_RECHECK"])

    assert code == 0
    assert calls == [
        ("POST", "/api/agent/user-response", {"action": "FILL_RECHECK"})
    ]


def test_status_prints_the_open_checkpoint(monkeypatch, capsys):
    state = {
        "state": "WAITING_FOR_USER",
        "run_id": "run-1",
        "target_url": "https://portal.example/apply",
        "run_clock": {"started_at": "2026-10-29T00:00:00Z", "active_seconds": 42.0},
        "active_gate": {
            "gate_type": "FILL_INCOMPLETE",
            "reason": "incomplete_fill",
            "title": "Some fields were not kept",
            "recommended": {"label": "Recheck and fill again"},
            "options": [{"label": "Recheck and fill again", "action": "FILL_RECHECK"}],
        },
    }
    monkeypatch.setattr(cli, "_request", lambda *args, **kwargs: state)

    code = cli.main(["status"])

    output = capsys.readouterr().out
    assert code == 0
    assert "state:  WAITING_FOR_USER" in output
    assert "reason: incomplete_fill" in output
    assert "suggested first step: Recheck and fill again" in output
    assert "[FILL_RECHECK]" in output


def test_an_unreachable_cockpit_is_reported(monkeypatch, capsys):
    def boom(*args, **kwargs):
        raise cli.ApiError(
            "Cannot reach the cockpit at http://127.0.0.1:8000. Is the server running?"
        )

    monkeypatch.setattr(cli, "_request", boom)

    code = cli.main(["status"])

    assert code == cli.EXIT_SERVER
    assert "Is the server running?" in capsys.readouterr().err
