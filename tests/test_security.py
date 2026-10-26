"""Security behaviour: auth gate, headers, uploads, and response hygiene."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from backend.core import settings
from backend.main import app


def _auth_client(monkeypatch, token="test-token-with-enough-entropy"):
    monkeypatch.setattr(settings, "AUTH_TOKEN", token)
    monkeypatch.setattr(settings, "AUTH_REQUIRED", True)
    return TestClient(app)


def test_auth_gate_protects_api_and_uploads(monkeypatch):
    with _auth_client(monkeypatch) as client:
        assert client.get("/api/vault").status_code == 401
        assert client.get("/uploads/missing.jpg").status_code == 401
        assert client.get("/api/health").status_code == 200
        assert client.get("/gov-portal-demo").status_code == 200

        assert client.get("/api/vault", headers={"X-API-Token": "wrong"}).status_code == 401
        assert (
            client.get("/api/vault", headers={"X-API-Token": "test-token-with-enough-entropy"}).status_code
            == 200
        )
        assert (
            client.get(
                "/api/vault",
                headers={"Authorization": "Bearer test-token-with-enough-entropy"},
            ).status_code
            == 200
        )
        assert (
            client.get("/api/vault", params={"token": "test-token-with-enough-entropy"}).status_code
            == 200
        )


def test_security_headers_are_present(client):
    response = client.get("/api/health")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["X-Frame-Options"] == "SAMEORIGIN"
    # Same-origin camera is required for the live-photo checkpoint. The
    # microphone and geolocation stay disabled.
    assert (
        response.headers["Permissions-Policy"]
        == "camera=(self), microphone=(), geolocation=()"
    )
    assert response.headers["X-Request-ID"]


def test_sensitive_api_responses_are_not_cached(client):
    response = client.get("/api/vault", params={"masked": "true"})

    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Pragma"] == "no-cache"


def test_upload_path_traversal_is_blocked(client):
    response = client.get("/uploads/%2e%2e%2fdata%2fcandidate_vault.json")

    assert response.status_code == 404
    assert "Aman Kumar Sharma" not in response.text
    assert "aadhaar" not in response.text.lower()


def test_unknown_api_route_does_not_echo_a_traceback(client):
    response = client.get("/api/does-not-exist")

    assert response.status_code == 404
    assert "Traceback" not in response.text


def test_vault_masking_can_be_enabled_globally(monkeypatch, client):
    monkeypatch.setattr(settings, "MASK_PII", True)

    response = client.get("/api/vault")

    assert response.status_code == 200
    payload = response.json()
    assert payload["aadhaar_number"].endswith("9012")
    assert "123456789012" not in json.dumps(payload)
    assert payload["mobile"].endswith("3210")


def test_auth_token_compare_rejects_empty_values(monkeypatch):
    from backend.main import _safe_compare

    monkeypatch.setattr(settings, "AUTH_TOKEN", "expected")
    assert _safe_compare("") is False
    assert _safe_compare("wrong") is False
    assert _safe_compare("expected") is True
