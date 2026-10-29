"""No-progress detection: shadow first, stop only at the high threshold."""

from __future__ import annotations

import asyncio
import time

import pytest

from backend.core import settings
from backend.core.failures import classify_failure, is_retryable
from backend.core.orchestrator import FormPilotOrchestrator
from backend.core.progress import ProgressTracker, ProgressVerdict


class FakeClock:
    def __init__(self, start: float = 1000.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def tick(self, seconds: float = 60.0) -> None:
        self.now += seconds


def _tracker(**kwargs) -> ProgressTracker:
    """A count-only tracker: the time gate is tested separately."""
    kwargs.setdefault("clock", FakeClock())
    kwargs.setdefault("min_shadow_seconds", 0)
    kwargs.setdefault("min_stall_seconds", 0)
    return ProgressTracker(**kwargs)
from backend.core.run_store import RunStore


# ------------------------------------------------------------------- tracker


def test_a_changing_page_is_always_progress():
    tracker = _tracker()

    for index in range(10):
        verdict = tracker.observe(f"page-{index}", f"fields-{index}")
        assert verdict is ProgressVerdict.PROGRESS

    assert tracker.stalls == 0
    assert tracker.shadow_stalls == 0
    assert tracker.observations == 10


def test_the_low_threshold_only_shadows():
    tracker = _tracker(repeat_threshold=3, stall_threshold=6)

    verdicts = [tracker.observe("page", "fields") for _ in range(5)]

    assert verdicts[0] is ProgressVerdict.PROGRESS
    assert verdicts[1] is ProgressVerdict.REPEAT
    assert verdicts[2] is ProgressVerdict.SHADOW_STALL
    assert verdicts[3] is ProgressVerdict.SHADOW_STALL
    assert verdicts[4] is ProgressVerdict.SHADOW_STALL
    # One episode, counted once, even though three cycles were in it.
    assert tracker.shadow_stalls == 1
    assert tracker.stalls == 0


def test_the_high_threshold_stops_the_run():
    tracker = _tracker(repeat_threshold=3, stall_threshold=6)

    verdicts = [tracker.observe("page", "fields") for _ in range(6)]

    assert verdicts[-1] is ProgressVerdict.STALL
    assert tracker.stalls == 1


def test_a_value_change_is_progress_even_on_the_same_page():
    clock = FakeClock()
    tracker = ProgressTracker(
        repeat_threshold=2,
        stall_threshold=4,
        clock=clock,
        min_shadow_seconds=1,
        min_stall_seconds=2,
    )

    def observe(fields):
        clock.tick(1)
        return tracker.observe("page", fields)

    assert observe("empty") is ProgressVerdict.PROGRESS
    assert observe("empty") is ProgressVerdict.SHADOW_STALL
    assert observe("filled") is ProgressVerdict.PROGRESS
    assert observe("filled") is ProgressVerdict.SHADOW_STALL
    assert observe("filled") is ProgressVerdict.SHADOW_STALL
    assert observe("filled") is ProgressVerdict.STALL


def test_a_revisit_without_a_change_is_not_progress():
    tracker = _tracker(repeat_threshold=2, stall_threshold=4)

    tracker.observe("page-a", "same")
    tracker.observe("page-b", "same")
    tracker.observe("page-a", "same")  # a revisit: the key changed, so progress
    assert tracker.observe("page-a", "same") is ProgressVerdict.SHADOW_STALL


def test_a_human_answer_resets_the_budget():
    tracker = _tracker(repeat_threshold=2, stall_threshold=4)

    tracker.observe("page", "fields")
    tracker.observe("page", "fields")
    tracker.observe("page", "fields")
    assert tracker.shadow_stalls == 1

    tracker.reset("human_answer")

    assert tracker.observe("page", "fields") is ProgressVerdict.PROGRESS
    assert tracker.resets == 1
    assert tracker.last_reset_reason == "human_answer"


def test_shadow_off_stops_at_the_low_threshold():
    tracker = _tracker(repeat_threshold=2, stall_threshold=6, shadow=False)

    tracker.observe("page", "fields")
    verdict = tracker.observe("page", "fields")

    assert verdict is ProgressVerdict.STALL
    assert tracker.shadow_stalls == 0


def test_the_snapshot_is_json_safe():
    tracker = _tracker()
    tracker.observe("page", "fields")
    tracker.observe("page", "fields")

    snapshot = tracker.snapshot()

    assert snapshot["observations"] == 2
    assert snapshot["repeats"] == 1
    assert snapshot["shadow"] is True


# ------------------------------------------------------------------ taxonomy


def test_no_progress_is_its_own_failure_code():
    code = classify_failure("The page has not changed after 6 attempts.")

    assert code.value == "no_progress"
    assert is_retryable(code) is False


# ------------------------------------------------------------------- wiring


def _orchestrator(tmp_path) -> FormPilotOrchestrator:
    orchestrator = FormPilotOrchestrator()
    orchestrator.run_id = "run-progress"
    orchestrator.run_store = RunStore(tmp_path / "runs")
    orchestrator.run_store.start("run-progress", {"query": "hpsc"})
    orchestrator.is_running = True
    orchestrator.state = "RUNNING"
    # The wiring tests count cycles; the time gate is unit-tested above.
    orchestrator._progress = ProgressTracker(min_shadow_seconds=0, min_stall_seconds=0)
    return orchestrator


def _dom(url="https://portal.example/form", value="Aman") -> dict:
    return {
        "url": url,
        "inputs": [{"id": "name", "name": "name", "value": value}],
    }


def test_a_changing_page_writes_no_stall_rows(tmp_path):
    orchestrator = _orchestrator(tmp_path)

    for index in range(8):
        asyncio.run(
            orchestrator._observe_progress(_dom(value=f"Aman {index}"), "step-1")
        )

    assert orchestrator.run_store.read_steps("run-progress") == []
    assert orchestrator._progress.stalls == 0


def test_shadow_mode_records_one_evidence_row_and_does_not_stop(tmp_path):
    orchestrator = _orchestrator(tmp_path)

    for _ in range(4):
        stopped = asyncio.run(orchestrator._observe_progress(_dom(), "step-1"))
        assert stopped is False

    steps = orchestrator.run_store.read_steps("run-progress")
    stalls = [step for step in steps if step["kind"] == "stall"]
    assert len(stalls) == 1
    assert stalls[0]["status"] == "shadow"
    assert stalls[0]["output"]["repeat_run"] == 3
    assert orchestrator.is_running is True


def test_the_high_threshold_opens_a_checkpoint_and_resets(tmp_path, monkeypatch):
    orchestrator = _orchestrator(tmp_path)
    seen = {}

    async def fake_wait():
        seen["state"] = orchestrator.state
        seen["gate"] = orchestrator.active_gate
        return {"action": "CONTINUE"}

    monkeypatch.setattr(orchestrator, "_wait_for_user_response", fake_wait)

    stopped = False
    for _ in range(6):
        stopped = asyncio.run(orchestrator._observe_progress(_dom(), "step-1"))

    assert stopped is True
    assert seen["state"] == "WAITING_FOR_USER"
    assert seen["gate"]["gate_type"] == "ERROR_DIAGNOSIS"
    assert "not changed" in seen["gate"]["error_text"]
    errors = [
        step
        for step in orchestrator.run_store.read_steps("run-progress")
        if step["kind"] == "error"
    ]
    assert errors and errors[-1]["error_code"] == "no_progress"
    # The checkpoint consumed a human answer, so the next cycle is progress.
    assert orchestrator._progress.repeat_run == 0
    assert asyncio.run(orchestrator._observe_progress(_dom(), "step-1")) is False


def test_a_stop_at_the_stall_checkpoint_stops_the_run(tmp_path, monkeypatch):
    orchestrator = _orchestrator(tmp_path)

    async def fake_wait():
        return {"action": "STOPPED"}

    monkeypatch.setattr(orchestrator, "_wait_for_user_response", fake_wait)

    for _ in range(6):
        asyncio.run(orchestrator._observe_progress(_dom(), "step-1"))

    assert orchestrator.is_running is False


# ---------------------------------------------------------------- time gates


def test_a_slow_page_is_not_a_stall_after_three_fast_reads():
    clock = FakeClock()
    tracker = ProgressTracker(
        repeat_threshold=3,
        stall_threshold=6,
        clock=clock,
        min_shadow_seconds=15,
        min_stall_seconds=45,
    )

    verdicts = []
    for _ in range(5):
        clock.tick(1)  # five quick re-reads, five seconds total
        verdicts.append(tracker.observe("loading", ""))

    assert ProgressVerdict.SHADOW_STALL not in verdicts
    assert ProgressVerdict.STALL not in verdicts
    assert tracker.shadow_stalls == 0


def test_a_page_that_stays_unchanged_long_enough_stalls():
    clock = FakeClock()
    tracker = ProgressTracker(
        repeat_threshold=3,
        stall_threshold=6,
        clock=clock,
        min_shadow_seconds=15,
        min_stall_seconds=45,
    )

    verdicts = []
    for _ in range(6):
        clock.tick(10)  # ten seconds between reads
        verdicts.append(tracker.observe("loading", ""))

    assert ProgressVerdict.SHADOW_STALL in verdicts
    assert verdicts[-1] is ProgressVerdict.STALL


def test_the_snapshot_reports_how_long_the_page_has_been_unchanged():
    clock = FakeClock()
    tracker = ProgressTracker(clock=clock, min_shadow_seconds=0, min_stall_seconds=0)
    tracker.observe("page", "fields")
    clock.tick(12)

    assert tracker.snapshot()["unchanged_seconds"] == 12.0
