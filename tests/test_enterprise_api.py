"""End-to-end API integration tests for enterprise security, resilience, and audit features."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.core import settings
from backend.core.idempotency import idempotency_engine
from backend.core.run_store import RunStore
from backend.main import app


@pytest.fixture(autouse=True)
def clean_idempotency_store():
    import asyncio
    asyncio.run(idempotency_engine.clear())
    yield
    asyncio.run(idempotency_engine.clear())


def test_deep_system_health_endpoint(client):
    response = client.get("/api/system/health/deep")
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "healthy"
    assert data["security"]["ssrf_guard_active"] is True
    assert data["security"]["cloud_metadata_protection"] == "ACTIVE"
    assert data["security"]["pii_sanitization"] == "ACTIVE"
    assert "circuit_breakers" in data["resilience"]


def test_circuit_breakers_telemetry_endpoint(client):
    response = client.get("/api/system/circuit-breakers")
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "ok"
    assert isinstance(data["breakers"], dict)


def test_ssrf_protection_blocks_malicious_start_agent_url(client):
    # Attempt SSRF attack targeting cloud provider metadata
    response = client.post(
        "/api/agent/start",
        json={"query_or_url": "http://169.254.169.254/latest/meta-data/", "mode": "fill"},
    )
    assert response.status_code == 400
    assert "SSRF Protection Guard" in response.json()["detail"]


def test_idempotency_key_replay_behavior(client, monkeypatch):
    import backend.main as main_mod

    # Make orchestrator start a no-op fake run for test safety
    test_run_id = "test-run-idempotent-001"
    monkeypatch.setattr(main_mod.orchestrator, "is_running", False)
    monkeypatch.setattr(main_mod.orchestrator, "run_id", test_run_id)

    async def fake_start(*args, **kwargs):
        pass

    monkeypatch.setattr(main_mod.orchestrator, "start_application", fake_start)

    idempotency_key = "idemp-key-test-9999"
    headers = {"X-Idempotency-Key": idempotency_key}

    # 1. First execution
    res1 = client.post(
        "/api/agent/start",
        json={"query_or_url": "upsc", "mode": "fill"},
        headers=headers,
    )
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["success"] is True

    # 2. Replay with identical idempotency key should return cached response with X-Cache header
    res2 = client.post(
        "/api/agent/start",
        json={"query_or_url": "upsc", "mode": "fill"},
        headers=headers,
    )
    assert res2.status_code == 200
    assert res2.headers.get("x-cache") == "HIT-IDEMPOTENCY"
    data2 = res2.json()
    assert data2 == data1


def test_audit_chain_endpoint_returns_verified_merkle_chain(client):
    # Create a dummy run in run_store
    store = RunStore()
    run_id = "audit-merkle-test-run"
    store.start(run_id, {"query": "gate_2026", "mode": "fill"})
    step_id = store.start_step(run_id, "NAVIGATE", status="started")
    store.finish_step(run_id, step_id, "ok")
    store.save_audit(run_id, {"records": [{"field": "name", "value": "Aman"}]})

    response = client.get(f"/api/runs/{run_id}/audit-chain")
    assert response.status_code == 200
    chain_data = response.json()

    assert chain_data["run_id"] == run_id
    assert chain_data["verified"] is True
    assert chain_data["total_entries"] == 3
    assert chain_data["head_hash"] is not None
    assert len(chain_data["chain"]) == 3
    assert chain_data["chain"][0]["event_type"] == "RUN_INITIALIZED"
    assert chain_data["chain"][1]["event_type"] == "STEP_RECORDED"
    assert chain_data["chain"][2]["event_type"] == "FINAL_AUDIT_SEALED"


def test_audit_chain_endpoint_returns_404_for_unknown_run(client):
    response = client.get("/api/runs/non-existent-run-xyz/audit-chain")
    assert response.status_code == 404
