"""TinyFish client tests. No real network calls are made."""

from __future__ import annotations

import asyncio
import json

import httpx

from backend.core.tinyfish_client import EngineConfig, TinyFishClient


def test_public_config_never_exposes_the_api_key(monkeypatch, tmp_path):
    monkeypatch.setenv("TINYFISH_API_KEY", "test-secret-key-1234")
    client = TinyFishClient(config_path=str(tmp_path / "engine_config.json"))

    public = client.public_config()

    assert public["tinyfish_api_key"] == "***"
    assert public["tinyfish_key_configured"] is True
    assert "test-secret-key-1234" not in json.dumps(public)
    assert "browser_profile" not in public
    assert "proxy_type" not in public
    assert "stealth_active" not in public


def test_blank_or_redacted_save_keeps_the_existing_key(tmp_path):
    client = TinyFishClient(config_path=str(tmp_path / "engine_config.json"))
    client.save_config(EngineConfig(tinyfish_api_key="real-test-key"))
    assert client.api_key == "real-test-key"

    client.save_config(EngineConfig(tinyfish_api_key="***"))
    assert client.api_key == "real-test-key"

    client.save_config(EngineConfig(tinyfish_api_key=""))
    assert client.api_key == "real-test-key"


def test_mode_selection_is_predictable(tmp_path):
    local = TinyFishClient(config_path=str(tmp_path / "local.json"))
    local.config.mode = "local"
    assert local.effective_mode("https://example.com") == "local"

    auto = TinyFishClient(config_path=str(tmp_path / "auto.json"))
    auto.config.mode = "auto"
    auto.config.tinyfish_api_key = ""
    assert auto.effective_mode("https://example.com") == "local"
    auto.config.tinyfish_api_key = "key"
    assert auto.effective_mode("https://example.com") == "cloud"
    assert auto.effective_mode("http://127.0.0.1:8000/gov-portal-demo") == "local"


def test_connection_without_key_is_offline(tmp_path):
    client = TinyFishClient(config_path=str(tmp_path / "engine_config.json"))

    result = asyncio.run(client.test_connection())

    assert result["success"] is False
    assert result["status"] == "missing_key"


def test_search_parses_results(tmp_path):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["query"] = request.url.params.get("query")
        seen["key"] = request.headers.get("x-api-key")
        return httpx.Response(
            200,
            json={"results": [{"title": "SSC", "url": "https://ssc.gov.in", "snippet": "Notice"}]},
        )

    client = TinyFishClient(
        config_path=str(tmp_path / "engine_config.json"),
        transport=httpx.MockTransport(handler),
    )
    results = asyncio.run(client.search("ssc notice", api_key="test-key"))

    assert seen["query"] == "ssc notice"
    assert seen["key"] == "test-key"
    assert results == [{"title": "SSC", "url": "https://ssc.gov.in", "snippet": "Notice"}]


def test_fetch_returns_the_first_result(tmp_path, monkeypatch):
    monkeypatch.setenv("TINYFISH_API_KEY", "test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["urls"] == ["https://ssc.gov.in/notice"]
        return httpx.Response(200, json={"results": [{"url": "https://ssc.gov.in/notice", "content": "Hi"}]})

    client = TinyFishClient(
        config_path=str(tmp_path / "engine_config.json"),
        transport=httpx.MockTransport(handler),
    )
    result = asyncio.run(client.fetch_content("https://ssc.gov.in/notice"))

    assert result["content"] == "Hi"


def test_cloud_browser_session_and_termination(tmp_path, monkeypatch):
    monkeypatch.setenv("TINYFISH_API_KEY", "test-key")
    monkeypatch.setenv("TINYFISH_MODE", "auto")
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, str(request.url)))
        if request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "session_id": "session-123",
                    "cdp_url": "wss://browser.example/session-123",
                    "base_url": "https://browser.example",
                },
            )
        return httpx.Response(204)

    client = TinyFishClient(
        config_path=str(tmp_path / "engine_config.json"),
        transport=httpx.MockTransport(handler),
    )
    session = asyncio.run(
        client.create_cloud_browser_session("https://ssc.gov.in/apply")
    )

    assert session.is_cloud is True
    assert session.session_id == "session-123"
    assert session.cdp_url.startswith("wss://")
    assert "TinyFish" in session.proxy_node
    assert not hasattr(session, "stealth_active")

    assert asyncio.run(client.terminate_session()) is True
    assert calls[0][0] == "POST"
    assert calls[-1][0] == "DELETE"


def test_local_targets_never_call_the_cloud_browser(tmp_path, monkeypatch):
    monkeypatch.setenv("TINYFISH_API_KEY", "test-key")

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("local targets must not use the metered Browser API")

    client = TinyFishClient(
        config_path=str(tmp_path / "engine_config.json"),
        transport=httpx.MockTransport(handler),
    )
    session = asyncio.run(
        client.create_cloud_browser_session("http://127.0.0.1:8000/gov-portal-demo")
    )

    assert session.is_cloud is False
    assert "Local" in session.proxy_node
