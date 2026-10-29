"""Model usage metering: per call, per run, and in the report."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from backend.core import settings
from backend.core.llm_client import LLMClient
from backend.core.orchestrator import FormPilotOrchestrator
from backend.core.run_report import build_run_report
from backend.core.run_store import RunStore


def _client(tmp_path, payload=None) -> LLMClient:
    body = payload or {
        "choices": [{"message": {"role": "assistant", "content": "hi"}}],
        "usage": {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    client = LLMClient(
        str(tmp_path / "llm.json"),
        transport=httpx.MockTransport(handler),
    )
    client.config.api_key = "test"
    client.config.model = "test-model"
    return client


def test_a_successful_call_records_tokens(tmp_path):
    client = _client(tmp_path)

    asyncio.run(client.complete([{"role": "user", "content": "hello"}]))

    usage = client.usage_snapshot()
    assert usage["calls"] == 1
    assert usage["errors"] == 0
    assert usage["prompt_tokens"] == 120
    assert usage["completion_tokens"] == 30
    assert usage["total_tokens"] == 150
    assert usage["token_reports"] == 1
    assert usage["model"] == "test-model"


def test_a_provider_without_usage_still_counts_the_call(tmp_path):
    client = _client(
        tmp_path,
        {"choices": [{"message": {"role": "assistant", "content": "hi"}}]},
    )

    asyncio.run(client.complete([{"role": "user", "content": "hello"}]))

    usage = client.usage_snapshot()
    assert usage["calls"] == 1
    assert usage["token_reports"] == 0
    assert usage["total_tokens"] == 0


def test_a_failed_call_is_counted_as_an_error(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": {"message": "boom"}})

    client = LLMClient(str(tmp_path / "llm.json"), transport=httpx.MockTransport(handler))
    client.config.api_key = "test"
    client.config.model = "test-model"

    with pytest.raises(Exception):
        asyncio.run(client.complete([{"role": "user", "content": "hello"}]))

    usage = client.usage_snapshot()
    assert usage["calls"] == 1
    assert usage["errors"] == 1


def test_the_delta_is_what_happened_between_two_snapshots():
    before = {"calls": 2, "errors": 0, "prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110}
    after = {
        "calls": 5,
        "errors": 1,
        "prompt_tokens": 400,
        "completion_tokens": 40,
        "total_tokens": 440,
        "model": "m",
    }

    delta = LLMClient.usage_delta(before, after)

    assert delta["calls"] == 3
    assert delta["errors"] == 1
    assert delta["prompt_tokens"] == 300
    assert delta["total_tokens"] == 330
    assert delta["model"] == "m"


class FakeInterpreter:
    def __init__(self, usage):
        self._usage = usage

    def usage_snapshot(self):
        return dict(self._usage)


def test_the_run_meters_only_its_own_calls():
    orchestrator = FormPilotOrchestrator()
    orchestrator._llm_usage_start = {
        "calls": 4,
        "errors": 0,
        "prompt_tokens": 1000,
        "completion_tokens": 100,
        "total_tokens": 1100,
        "model": "m",
    }
    orchestrator.page_interpreter = FakeInterpreter(
        {
            "calls": 7,
            "errors": 0,
            "prompt_tokens": 2500,
            "completion_tokens": 250,
            "total_tokens": 2750,
            "model": "m",
        }
    )

    usage = orchestrator.llm_usage()

    assert usage["calls"] == 3
    assert usage["total_tokens"] == 1650


def test_cost_is_only_estimated_when_prices_are_configured(monkeypatch):
    orchestrator = FormPilotOrchestrator()
    orchestrator._llm_usage_start = {}
    orchestrator.page_interpreter = FakeInterpreter(
        {
            "calls": 1,
            "errors": 0,
            "prompt_tokens": 1_000_000,
            "completion_tokens": 1_000_000,
            "total_tokens": 2_000_000,
        }
    )

    monkeypatch.setattr(settings, "LLM_PRICE_INPUT_PER_MTOK", 0.0)
    monkeypatch.setattr(settings, "LLM_PRICE_OUTPUT_PER_MTOK", 0.0)
    assert "estimated_cost_usd" not in orchestrator.llm_usage()

    monkeypatch.setattr(settings, "LLM_PRICE_INPUT_PER_MTOK", 1.5)
    monkeypatch.setattr(settings, "LLM_PRICE_OUTPUT_PER_MTOK", 3.0)
    assert orchestrator.llm_usage()["estimated_cost_usd"] == 4.5


def test_the_report_shows_model_calls_and_tokens(tmp_path):
    store = RunStore(tmp_path / "runs")
    run_id = "run-usage"
    store.start(run_id, {"query": "hpsc", "run_mode": "fill"})
    store.record_step(run_id, "perceive", output={"page_type": "form", "field_count": 3})
    store.finish(
        run_id,
        "DONE",
        {
            "llm_usage": {
                "calls": 2,
                "errors": 0,
                "prompt_tokens": 1200,
                "completion_tokens": 150,
                "total_tokens": 1350,
                "estimated_cost_usd": 0.0023,
            }
        },
    )

    report = build_run_report(store.run_detail(run_id))

    assert report["stats"]["model_calls"] == 2
    assert report["stats"]["total_tokens"] == 1350
    assert any("called 2 times" in line for line in report["what_happened"])
    assert any("1,350 tokens" in line for line in report["what_happened"])
