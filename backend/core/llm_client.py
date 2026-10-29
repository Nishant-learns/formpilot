"""OpenAI-compatible chat client for the candidate assistant.

The assistant is model-driven: the model receives the live application state
and a small set of tools, then decides what to say and which action to take.
No candidate intent is matched with hard-coded phrases.

Any OpenAI-compatible endpoint works (OpenAI, DeepSeek, Groq, OpenRouter,
Together, vLLM, Ollama's ``/v1`` shim).  Configuration is read from the
environment first and can be overridden from the in-app settings dialog, which
persists to ``data/llm_config.json``.
"""

from __future__ import annotations

import datetime
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from pydantic import BaseModel, Field

from . import settings


class LLMError(RuntimeError):
    """A model call failed; the message is safe to show to the operator."""

    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        code: str = "llm_error",
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "message": str(self),
            "status_code": self.status_code,
        }


class LLMConfig(BaseModel):
    api_key: str = ""
    base_url: str = settings.LLM_BASE_URL
    model: str = settings.LLM_MODEL
    timeout_seconds: int = settings.LLM_TIMEOUT_SECONDS
    temperature: float = 0.2


def _is_local(base_url: str) -> bool:
    value = str(base_url or "").lower()
    return "127.0.0.1" in value or "localhost" in value or "0.0.0.0" in value


class LLMClient:
    def __init__(
        self,
        config_path: Optional[str] = None,
        *,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        self.config_path = (
            Path(config_path) if config_path else settings.DATA_DIR / "llm_config.json"
        )
        self._transport = transport
        self.config = self.load_config()
        # Cumulative usage for this client instance.  The orchestrator snapshots
        # it at run start and stores the delta, so a long-lived process can
        # still report per-run cost.
        self.usage: Dict[str, Any] = {
            "calls": 0,
            "errors": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "token_reports": 0,
            "model": "",
            "last_at": None,
        }

    # ------------------------------------------------------------------ config

    def load_config(self) -> LLMConfig:
        data: Dict[str, Any] = {}
        if self.config_path.exists():
            try:
                data = json.loads(self.config_path.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        config = LLMConfig(**data)

        env_key = (
            os.getenv("FORMPILOT_LLM_API_KEY")
            or os.getenv("OPENAI_API_KEY")
            or settings.LLM_API_KEY
            or ""
        ).strip()
        if env_key:
            config.api_key = env_key
        if os.getenv("FORMPILOT_LLM_BASE_URL"):
            config.base_url = os.getenv("FORMPILOT_LLM_BASE_URL", config.base_url).rstrip("/")
        if os.getenv("FORMPILOT_LLM_MODEL"):
            config.model = os.getenv("FORMPILOT_LLM_MODEL", config.model)
        if os.getenv("FORMPILOT_LLM_TIMEOUT_SECONDS"):
            try:
                config.timeout_seconds = int(os.getenv("FORMPILOT_LLM_TIMEOUT_SECONDS", "45"))
            except ValueError:
                pass
        return config

    def save_config(self, config: LLMConfig, *, preserve_key: bool = True) -> LLMConfig:
        candidate = config.model_copy(deep=True)
        if preserve_key and candidate.api_key.strip() in {"", "***", "********"}:
            candidate.api_key = self.config.api_key
        candidate.base_url = (candidate.base_url or settings.LLM_BASE_URL).rstrip("/")
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
        return self.config

    @property
    def api_key(self) -> str:
        return (
            os.getenv("FORMPILOT_LLM_API_KEY")
            or os.getenv("OPENAI_API_KEY")
            or self.config.api_key
            or ""
        ).strip()

    @property
    def configured(self) -> bool:
        return bool(self.config.model and (self.api_key or _is_local(self.config.base_url)))

    # ------------------------------------------------------------------ usage

    def _record_usage(self, body: Any = None, *, error: bool = False) -> None:
        usage = self.usage
        usage["calls"] = int(usage.get("calls") or 0) + 1
        if error:
            usage["errors"] = int(usage.get("errors") or 0) + 1
        reported = body.get("usage") if isinstance(body, dict) else None
        if isinstance(reported, dict):
            prompt = reported.get("prompt_tokens")
            completion = reported.get("completion_tokens")
            total = reported.get("total_tokens")
            if prompt is not None:
                usage["prompt_tokens"] = int(usage.get("prompt_tokens") or 0) + int(prompt or 0)
            if completion is not None:
                usage["completion_tokens"] = int(usage.get("completion_tokens") or 0) + int(
                    completion or 0
                )
            if total is not None:
                usage["total_tokens"] = int(usage.get("total_tokens") or 0) + int(total or 0)
            usage["token_reports"] = int(usage.get("token_reports") or 0) + 1
        usage["model"] = self.config.model
        usage["last_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

    def usage_snapshot(self) -> Dict[str, Any]:
        return dict(self.usage)

    @staticmethod
    def usage_delta(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
        """The usage that happened between two snapshots."""
        keys = ("calls", "errors", "prompt_tokens", "completion_tokens", "total_tokens", "token_reports")
        delta = {
            key: int(after.get(key) or 0) - int(before.get(key) or 0) for key in keys
        }
        delta["model"] = after.get("model") or before.get("model") or ""
        return delta

    def public_config(self) -> Dict[str, Any]:
        return {
            "configured": self.configured,
            "model": self.config.model,
            "base_url": self.config.base_url,
            "api_key": "***" if self.api_key else "",
            "timeout_seconds": self.config.timeout_seconds,
            "local": _is_local(self.config.base_url),
        }

    # -------------------------------------------------------------------- call

    async def complete(
        self,
        messages: List[Dict[str, Any]],
        *,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: str = "auto",
    ) -> Dict[str, Any]:
        """Return ``choices[0].message`` from a chat-completions call."""
        if not self.configured:
            raise LLMError(
                "The AI assistant is not configured. Add a model key in Settings.",
                code="llm_not_configured",
            )

        payload: Dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        url = f"{self.config.base_url.rstrip('/')}/chat/completions"
        try:
            async with httpx.AsyncClient(
                timeout=self.config.timeout_seconds,
                transport=self._transport,
            ) as client:
                response = await client.post(url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            self._record_usage(error=True)
            raise LLMError(
                f"The assistant could not reach the model: {exc.__class__.__name__}.",
                code="llm_unreachable",
            ) from exc

        if response.status_code >= 400:
            detail = ""
            try:
                body = response.json()
                detail = str(
                    (body.get("error") or {}).get("message")
                    or body.get("message")
                    or body
                )[:300]
            except Exception:
                detail = response.text[:300]
            self._record_usage(error=True)
            raise LLMError(
                f"The model returned {response.status_code}: {detail}",
                status_code=response.status_code,
                code="llm_http_error",
            )

        try:
            body = response.json()
            message = body["choices"][0]["message"]
        except Exception as exc:
            self._record_usage(error=True)
            raise LLMError("The model returned an unexpected response.", code="llm_bad_response") from exc
        self._record_usage(body)
        return message
