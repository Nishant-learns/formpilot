"""TinyFish integration.

Three real APIs are used:

* Search  - ``GET  https://api.search.tinyfish.ai?query=...&location=IN``
* Browser - ``POST https://api.browser.tinyfish.ai`` returns a CDP URL
* Fetch   - ``POST https://api.fetch.tinyfish.ai``

The cloud browser is metered, so the caller must explicitly opt in.  There is
no fake "managed tunnel": if a cloud session cannot be created the caller gets
a typed error and can choose the clearly-labelled local Playwright fallback.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Optional

import httpx
from pydantic import BaseModel, Field, field_validator

from . import settings


class TinyFishError(RuntimeError):
    """A non-success response from TinyFish, with enough detail to debug it."""

    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        code: str = "tinyfish_error",
        request_id: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.request_id = request_id


class EngineConfig(BaseModel):
    mode: str = "auto"  # auto | local | cloud
    headless: bool = True
    tinyfish_api_key: str = ""
    tinyfish_browser_api_url: str = settings.TINYFISH_BROWSER_URL
    tinyfish_search_api_url: str = settings.TINYFISH_SEARCH_URL
    tinyfish_fetch_api_url: str = settings.TINYFISH_FETCH_URL
    tinyfish_agent_api_url: str = settings.TINYFISH_AGENT_URL
    proxy_region: str = "in"
    adaptive_delay_ms: int = 500
    ntfy_topic: str = settings.NTFY_TOPIC
    timeout_seconds: int = settings.TINYFISH_TIMEOUT_SECONDS

    @field_validator("mode")
    @classmethod
    def _normalise_mode(cls, value: str) -> str:
        value = (value or "auto").strip().lower()
        if value in {"tinyfish", "cloud", "remote"}:
            return "cloud"
        if value in {"local", "playwright"}:
            return "local"
        return "auto"

    @field_validator("proxy_region")
    @classmethod
    def _normalise_region(cls, value: str) -> str:
        value = (value or "in").strip().lower()
        return value if len(value) == 2 else "in"


class TinyFishSession(BaseModel):
    session_id: str = ""
    cdp_url: str = ""
    base_url: str = ""
    proxy_node: str = ""
    country_code: str = "IN"
    created_at: float = Field(default_factory=time.time)
    is_cloud: bool = False
    fallback_reason: Optional[str] = None


class TinyFishClient:
    def __init__(
        self,
        config_path: Optional[str] = None,
        *,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        self.config_path = Path(config_path) if config_path else settings.ENGINE_CONFIG_FILE
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self._transport = transport
        self.config = self.load_config()
        self.active_session: Optional[TinyFishSession] = None

    # ------------------------------------------------------------------ config

    def load_config(self) -> EngineConfig:
        data: dict[str, Any] = {}
        if self.config_path.exists():
            try:
                data = json.loads(self.config_path.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        config = EngineConfig(**data)

        # Environment wins for deployments; the JSON file is a local-demo
        # convenience and is never the source of truth in production.
        env_key = (os.getenv("TINYFISH_API_KEY") or settings.TINYFISH_API_KEY or "").strip()
        if env_key:
            config.tinyfish_api_key = env_key
        if os.getenv("TINYFISH_MODE"):
            config.mode = EngineConfig._normalise_mode(os.getenv("TINYFISH_MODE", "auto"))
        if os.getenv("FORMPILOT_NTFY_TOPIC"):
            config.ntfy_topic = os.getenv("FORMPILOT_NTFY_TOPIC", config.ntfy_topic)
        return config

    def save_config(self, config: EngineConfig, *, preserve_key: bool = True) -> None:
        """Atomically persist config.  A redacted/blank key never wipes a key."""
        candidate = config.model_copy(deep=True)
        if preserve_key and candidate.tinyfish_api_key.strip() in {"", "***", "********"}:
            candidate.tinyfish_api_key = self.config.tinyfish_api_key
        self.config = candidate
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        payload = candidate.model_dump_json(indent=2) + "\n"
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{self.config_path.name}.", suffix=".tmp", dir=str(self.config_path.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, self.config_path)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

    @property
    def api_key(self) -> str:
        return (os.getenv("TINYFISH_API_KEY") or self.config.tinyfish_api_key or "").strip()

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def effective_mode(self, target_url: str = "") -> str:
        if self.config.mode == "local":
            return "local"
        if "127.0.0.1" in target_url or "localhost" in target_url:
            return "local"
        if self.config.mode in {"cloud", "auto"} and self.api_key:
            return "cloud"
        return "local"

    def key_preview(self) -> str:
        key = self.api_key
        return f"…{key[-4:]}" if len(key) >= 4 else ""

    def public_config(self) -> dict[str, Any]:
        data = self.config.model_dump()
        data["mode"] = self.effective_mode()
        data["tinyfish_api_key"] = "***" if self.is_configured else ""
        data["tinyfish_key_configured"] = self.is_configured
        data["effective_mode"] = self.effective_mode()
        # The browser profile and region are implementation details.
        data.pop("adaptive_delay_ms", None)
        data.pop("tinyfish_key_preview", None)
        return data

    # ------------------------------------------------------------------ helpers

    def _headers(self, api_key: Optional[str] = None) -> dict[str, str]:
        key = (api_key if api_key is not None else self.api_key).strip()
        if not key:
            raise TinyFishError(
                "No TinyFish API key configured.",
                code="missing_api_key",
            )
        return {"X-API-Key": key, "Content-Type": "application/json"}

    def _http(self, timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=timeout, transport=self._transport)

    @staticmethod
    def _error_from_response(response: httpx.Response, operation: str) -> TinyFishError:
        request_id = response.headers.get("x-request-id") or response.headers.get("request-id")
        detail = ""
        try:
            body = response.json()
            if isinstance(body, dict):
                detail = str(body.get("message") or body.get("error") or body.get("detail") or "")
        except Exception:
            detail = response.text[:300]
        message = f"TinyFish {operation} failed with HTTP {response.status_code}"
        if detail:
            message += f": {detail}"
        code = "unauthorized" if response.status_code in (401, 403) else "tinyfish_http_error"
        return TinyFishError(
            message,
            status_code=response.status_code,
            code=code,
            request_id=request_id,
        )

    # ------------------------------------------------------------------ browser

    async def create_cloud_browser_session(
        self,
        target_url: str,
        *,
        timeout_seconds: Optional[int] = None,
    ) -> TinyFishSession:
        """Create a real TinyFish Browser API session.

        Local URLs and ``mode=local`` never call the metered API.  For cloud
        targets a failure raises ``TinyFishError`` instead of pretending a
        local browser is a cloud session.
        """
        if self.effective_mode(target_url) == "local":
            reason = "Local URL" if ("127.0.0.1" in target_url or "localhost" in target_url) else "Local mode selected"
            session = TinyFishSession(
                session_id=f"local-{uuid.uuid4().hex[:10]}",
                cdp_url="",
                proxy_node="Local Chromium (no cloud browser)",
                country_code=self.config.proxy_region.upper(),
                is_cloud=False,
                fallback_reason=reason,
            )
            self.active_session = session
            return session

        headers = self._headers()
        payload: dict[str, Any] = {
            "url": target_url,
            "timeout_seconds": int(timeout_seconds or self.config.timeout_seconds),
        }
        region = self.config.proxy_region.upper()
        if len(region) == 2:
            payload["proxy_config"] = {"country_code": region}

        started = time.time()
        try:
            async with self._http(timeout=75.0) as client:
                response = await client.post(
                    self.config.tinyfish_browser_api_url,
                    headers=headers,
                    json=payload,
                )
        except httpx.HTTPError as exc:
            raise TinyFishError(
                f"Could not reach TinyFish Browser API: {exc}",
                code="network_error",
            ) from exc

        if response.status_code not in (200, 201):
            raise self._error_from_response(response, "Browser API")

        data = response.json() if response.content else {}
        cdp_url = str(data.get("cdp_url") or "")
        if not cdp_url:
            raise TinyFishError(
                "TinyFish Browser API returned no CDP URL.",
                status_code=response.status_code,
                code="invalid_browser_response",
            )

        session = TinyFishSession(
            session_id=str(data.get("session_id") or ""),
            cdp_url=cdp_url,
            base_url=str(data.get("base_url") or ""),
            proxy_node=f"TinyFish {region} cloud browser",
            country_code=region,
            created_at=started,
            is_cloud=True,
        )
        self.active_session = session
        return session

    async def terminate_session(self, session_id: Optional[str] = None) -> bool:
        session = self.active_session
        sid = session_id or (session.session_id if session else "")
        if not sid or (session and not session.is_cloud):
            self.active_session = None
            return True
        try:
            async with self._http(timeout=20.0) as client:
                response = await client.delete(
                    f"{self.config.tinyfish_browser_api_url.rstrip('/')}/{sid}",
                    headers={"X-API-Key": self.api_key},
                )
            return response.status_code in (200, 202, 204, 404)
        except httpx.HTTPError:
            return False
        finally:
            self.active_session = None

    # ------------------------------------------------------------------ search

    async def search(
        self,
        query: str,
        *,
        location: str = "IN",
        limit: int = 8,
        purpose: str = "",
        include_domains: Optional[list[str]] = None,
        api_key: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "query": query,
            "location": location,
            "language": "en",
        }
        if purpose:
            params["purpose"] = purpose
        if include_domains:
            params["include_domains"] = ",".join(include_domains)
        headers = self._headers(api_key)
        try:
            async with self._http(timeout=25.0) as client:
                response = await client.get(
                    self.config.tinyfish_search_api_url,
                    headers=headers,
                    params=params,
                )
        except httpx.HTTPError as exc:
            raise TinyFishError(f"Could not reach TinyFish Search API: {exc}", code="network_error") from exc

        if response.status_code != 200:
            raise self._error_from_response(response, "Search API")
        data = response.json() if response.content else {}
        results = data.get("results", data if isinstance(data, list) else [])
        return [item for item in results if isinstance(item, dict)][: max(1, limit)]

    # ------------------------------------------------------------------ fetch

    async def fetch_content(
        self,
        url: str,
        *,
        purpose: str = "",
        fmt: str = "markdown",
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "urls": [url],
            "format": fmt,
            "links": False,
            "image_links": False,
            "ttl": 3600,
            "per_url_timeout_ms": 45000,
        }
        if purpose:
            payload["purpose"] = purpose
        try:
            async with self._http(timeout=60.0) as client:
                response = await client.post(
                    self.config.tinyfish_fetch_api_url,
                    headers=self._headers(),
                    json=payload,
                )
        except httpx.HTTPError as exc:
            raise TinyFishError(f"Could not reach TinyFish Fetch API: {exc}", code="network_error") from exc

        if response.status_code not in (200, 201):
            raise self._error_from_response(response, "Fetch API")
        data = response.json() if response.content else {}
        results = data.get("results", data if isinstance(data, list) else [])
        if isinstance(results, list) and results:
            first = results[0]
            return first if isinstance(first, dict) else {"content": str(first)}
        return data if isinstance(data, dict) else {"content": str(data)}

    # ------------------------------------------------------------------ health

    async def test_connection(self, api_key: Optional[str] = None) -> dict[str, Any]:
        """Verify the key with a real (free) Search API call."""
        key = (api_key if api_key is not None else self.api_key).strip()
        if not key:
            return {
                "success": False,
                "status": "missing_key",
                "mode": self.effective_mode(),
                "message": "No TinyFish API key configured. Add one in Settings to enable live search and cloud browser sessions.",
                "proxy_region": self.config.proxy_region.upper(),
            }

        started = time.time()
        try:
            results = await self.search(
                "India government recruitment official notification",
                limit=1,
                purpose="Verify TinyFish API connectivity for FormPilot",
                api_key=key,
            )
            latency = int((time.time() - started) * 1000)
            return {
                "success": True,
                "status": "authenticated",
                "mode": self.effective_mode(),
                "message": f"TinyFish Search API authenticated in {latency} ms.",
                "latency_ms": latency,
                "proxy_region": self.config.proxy_region.upper(),
                "result_count": len(results),
            }
        except TinyFishError as exc:
            latency = int((time.time() - started) * 1000)
            return {
                "success": False,
                "status": exc.code,
                "mode": self.effective_mode(),
                "message": str(exc),
                "latency_ms": latency,
                "proxy_region": self.config.proxy_region.upper(),
            }
        except Exception as exc:  # defensive: never crash a settings modal
            return {
                "success": False,
                "status": "unexpected_error",
                "mode": self.effective_mode(),
                "message": f"TinyFish connection test failed: {exc}",
                "proxy_region": self.config.proxy_region.upper(),
            }

    async def get_wallet(self) -> dict[str, Any]:
        if not self.api_key:
            raise TinyFishError("No TinyFish API key configured.", code="missing_api_key")
        try:
            async with self._http(timeout=20.0) as client:
                response = await client.get(
                    f"{self.config.tinyfish_agent_api_url.rstrip('/')}/wallet",
                    headers={"X-API-Key": self.api_key},
                )
        except httpx.HTTPError as exc:
            raise TinyFishError(f"Could not reach TinyFish wallet: {exc}", code="network_error") from exc
        if response.status_code != 200:
            raise self._error_from_response(response, "Wallet API")
        data = response.json() if response.content else {}
        return data if isinstance(data, dict) else {"raw": data}
