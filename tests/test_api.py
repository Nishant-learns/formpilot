"""API-level tests for the public demo contract."""

from __future__ import annotations

import json

import pytest

from backend.core import settings


@pytest.fixture(autouse=True)
def clean_practice_registrations():
    path = settings.DATA_DIR / "portal_registrations.json"
    path.unlink(missing_ok=True)
    yield
    path.unlink(missing_ok=True)


def test_health_reports_the_demo_configuration(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["app"] == "FormPilot"
    assert payload["demo_mode"] is True
    assert payload["simulator_enabled"] is True
    assert "tinyfish_configured" in payload


def test_oracle_endpoint_uses_the_registry(client):
    response = client.get("/api/oracle/search", params={"q": "railway", "live": "false"})

    assert response.status_code == 200
    payload = response.json()
    assert "rrbapply.gov.in" in payload["target_url"]
    assert payload["official_verified"] is True


def test_oracle_directory_is_available(client):
    response = client.get("/api/oracle/directory")

    assert response.status_code == 200
    entries = response.json()
    assert isinstance(entries, list)
    assert any("railway" in entry["keywords"] for entry in entries)


def test_vault_can_be_read_masked_and_updated(client):
    masked = client.get("/api/vault", params={"masked": "true"})
    assert masked.status_code == 200
    payload = masked.json()
    assert payload["full_name"] == "Aman Kumar Sharma"
    assert payload["aadhaar_number"].endswith("9012")
    assert "123456789012" not in json.dumps(payload)

    updated = client.post("/api/vault", json={"father_name": "Rajesh Kumar Sharma"})
    assert updated.status_code == 200
    assert updated.json()["success"] is True

    custom = client.post(
        "/api/vault/custom-field",
        data={"field_name": "apaar_id", "field_value": "9999-8888-7777"},
    )
    assert custom.status_code == 200
    assert custom.json()["vault"]["custom_fields"]["apaar_id"] == "9999-8888-7777"

    reset = client.post("/api/vault/reset")
    assert reset.status_code == 200
    assert reset.json()["vault"]["father_name"] == "Rajesh Kumar Sharma"


def test_engine_config_is_redacted(client):
    response = client.get("/api/engine/config")

    assert response.status_code == 200
    payload = response.json()
    assert payload["tinyfish_api_key"] in {"", "***"}
    assert "browser_profile" not in payload
    assert "proxy_type" not in payload
    assert "stealth_active" not in payload


def test_engine_config_save_does_not_persist_a_redacted_key(client):
    response = client.post(
        "/api/engine/config",
        json={
            "mode": "local",
            "headless": True,
            "tinyfish_api_key": "***",
            "proxy_region": "in",
            "ntfy_topic": "formpilot_test_otp",
            "timeout_seconds": 90,
        },
    )

    assert response.status_code == 200
    payload = response.json()["config"]
    assert payload["tinyfish_api_key"] in {"", "***"}


def test_connection_test_without_a_key_does_not_call_the_network(client):
    response = client.post("/api/engine/test-tinyfish", json={})

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert payload["status"] == "missing_key"


def test_wallet_without_a_key_returns_a_clear_error(client):
    response = client.get("/api/engine/wallet")

    assert response.status_code == 502
    assert "No TinyFish API key configured" in response.json()["detail"]


def test_chat_endpoint_answers_a_document_question(client):
    response = client.post(
        "/api/chat/message",
        json={"message": "Which documents should I keep ready?"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["action_taken"] == "FAQ_ANSWER"
    assert "documents" in payload["reply"].lower()
    assert "FormPilot" in payload["reply"] or "official portal" in payload["reply"]

    history = client.get("/api/chat/history")
    assert history.status_code == 200
    assert len(history.json()) == 2  # candidate message + assistant reply


def test_practice_portal_is_clearly_labelled_as_a_demo(client):
    response = client.get("/gov-portal-demo")

    assert response.status_code == 200
    assert "not a government website" in response.text
    assert "Practice portal" in response.text
    assert ("sar" "kari") not in response.text.lower()


def test_practice_registration_and_login_flow(client):
    registration = client.post(
        "/api/portal/register",
        json={
            "full_name": "Aman Kumar Sharma",
            "father_name": "Rajesh Kumar Sharma",
            "mother_name": "Sunita Devi",
            "dob": "15/08/2003",
            "gender": "Male",
            "category": "OBC-NCL",
            "mobile": "9876543210",
            "email": "demo.candidate@example.com",
            "aadhaar": "123456789012",
            "matric_board": "CBSE",
            "matric_roll": "24108842",
        },
    )

    assert registration.status_code == 200
    record = registration.json()
    assert record["success"] is True
    assert record["registration_id"].startswith("FP-2026-")

    login = client.post(
        "/api/portal/login",
        json={
            "registration_id": record["registration_id"],
            "password": record["password"],
        },
    )
    assert login.status_code == 200
    assert login.json()["success"] is True

    bad_login = client.post(
        "/api/portal/login",
        json={"registration_id": record["registration_id"], "password": "wrong"},
    )
    assert bad_login.status_code == 200
    assert bad_login.json()["success"] is False


def test_biometrics_preview_generates_in_spec_assets(client):
    response = client.get("/api/biometrics/preview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["photo"]["in_spec"] is True
    assert payload["signature"]["in_spec"] is True
    assert payload["photo"]["target_spec"].startswith("20KB")
    assert payload["signature"]["target_spec"].startswith("10KB")


def test_biometrics_rejects_non_images(client):
    response = client.post(
        "/api/biometrics/compress-photo",
        files={"file": ("notes.txt", b"not an image", "text/plain")},
    )

    assert response.status_code == 415


def test_biometrics_rejects_corrupt_images(client):
    response = client.post(
        "/api/biometrics/compress-signature",
        files={"file": ("broken.jpg", b"not really a jpeg", "image/jpeg")},
    )

    assert response.status_code == 400
    assert "Could not read that image" in response.json()["detail"]


def test_run_list_starts_empty_in_a_clean_demo(client):
    response = client.get("/api/runs")

    assert response.status_code == 200
    assert response.json()["runs"] == []


def test_unknown_run_is_404(client):
    response = client.get("/api/runs/not-a-real-run")

    assert response.status_code == 404
