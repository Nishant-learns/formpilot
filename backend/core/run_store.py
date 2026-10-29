"""Small, dependency-free run journal for auditability and support.

A run is a directory:

* ``meta.json`` — query, mode, state, timestamps, error code, summary
* ``events.jsonl`` — the human-readable stream (phase, message, gate)
* ``steps.json`` — the structured ledger: one row per phase
* ``audit.json`` — the filled-field audit written at the end

The ledger exists because a log is not a record.  A log says what was said; a
step says what was attempted, against which page, with what result and how
long it took.  That is what makes a run reconstructable after a restart, a
retry auditable as its own row, and the evaluation harness able to assert on
outcomes instead of prose.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from . import settings
from .failures import classify_failure, is_retryable


_RUN_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

# Anything whose key looks like a secret is stored as a marker, never a value.
_SENSITIVE_KEY_RE = re.compile(
    r"(password|passwd|otp|totp|token|secret|aadhaar|pan\b|identifier_value|credential|authorization)",
    re.IGNORECASE,
)

_MAX_TEXT = 500


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_time(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def redact(value: Any, depth: int = 0) -> Any:
    """Strip secrets from anything written to the ledger.

    Keys are the signal, not values: a value we do not recognise must not be
    guessed at, and a value under a secret-looking key must never be stored.
    Long text is truncated so a page dump cannot bloat the journal.
    """
    if depth > 6:
        return "…"
    if isinstance(value, dict):
        return {
            str(key): ("***" if _SENSITIVE_KEY_RE.search(str(key)) else redact(item, depth + 1))
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(item, depth + 1) for item in list(value)[:50]]
    if isinstance(value, str):
        return value if len(value) <= _MAX_TEXT else value[:_MAX_TEXT] + "…"
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return redact(str(value), depth + 1)


class RunStore:
    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = Path(root or settings.RUNS_DIR)
        self.root.mkdir(parents=True, exist_ok=True)

    def _dir(self, run_id: str) -> Path:
        if not _RUN_ID_RE.match(run_id or ""):
            raise ValueError("Invalid run id")
        path = self.root / run_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _atomic_write(path: Path, payload: str) -> None:
        fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, path)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

    # ------------------------------------------------------------------ run

    def start(self, run_id: str, meta: dict[str, Any]) -> None:
        directory = self._dir(run_id)
        payload = {"run_id": run_id, "started_at": _now(), **redact(meta)}
        self._atomic_write(directory / "meta.json", json.dumps(payload, indent=2, default=str))

    def append(self, run_id: str, event: dict[str, Any]) -> None:
        directory = self._dir(run_id)
        line = json.dumps({"run_id": run_id, "logged_at": _now(), **redact(event)}, default=str) + "\n"
        with open(directory / "events.jsonl", "a", encoding="utf-8") as handle:
            handle.write(line)

    def finish(self, run_id: str, state: str, extra: Optional[dict[str, Any]] = None) -> None:
        directory = self._dir(run_id)
        meta_path = directory / "meta.json"
        meta: dict[str, Any] = {}
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                meta = {}
        finished_at = _now()
        started = _parse_time(meta.get("started_at"))
        finished = _parse_time(finished_at)
        duration_ms = int((finished - started).total_seconds() * 1000) if started and finished else None
        steps = self.read_steps(run_id)
        error = (extra or {}).get("error") or meta.get("error")
        meta.update(
            {
                "state": state,
                "finished_at": finished_at,
                "duration_ms": duration_ms,
                "steps": len(steps),
                **(extra or {}),
            }
        )
        if error and not meta.get("error_code"):
            meta["error_code"] = classify_failure(str(error)).value
        self._atomic_write(meta_path, json.dumps(redact(meta), indent=2, default=str))

    def save_audit(self, run_id: str, audit: dict[str, Any]) -> None:
        directory = self._dir(run_id)
        self._atomic_write(directory / "audit.json", json.dumps(redact(audit), indent=2, default=str))

    # ------------------------------------------------------------------ steps

    def read_steps(self, run_id: str) -> list[dict[str, Any]]:
        path = self._dir(run_id) / "steps.json"
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []
        return data if isinstance(data, list) else []

    def _write_steps(self, run_id: str, steps: list[dict[str, Any]]) -> None:
        directory = self._dir(run_id)
        self._atomic_write(
            directory / "steps.json",
            json.dumps(redact(steps), indent=2, default=str),
        )

    def start_step(
        self,
        run_id: str,
        kind: str,
        *,
        status: str = "started",
        page_signature: str = "",
        input_digest: str = "",
        attempt: int = 1,
        detail: Optional[dict[str, Any]] = None,
    ) -> str:
        """Open a step row and return its id.

        ``attempt`` is 1 for the first try and increments when the same phase
        is retried, so a retry is visible as its own row instead of
        overwriting the failure.
        """
        steps = self.read_steps(run_id)
        seq = len(steps) + 1
        step_id = f"stp-{seq:04d}"
        steps.append(
            {
                "step_id": step_id,
                "seq": seq,
                "kind": str(kind or "step")[:40],
                "status": str(status or "started"),
                "page_signature": str(page_signature or "")[:120],
                "input_digest": str(input_digest or "")[:120],
                "attempt": max(1, int(attempt or 1)),
                "started_at": _now(),
                "finished_at": None,
                "duration_ms": None,
                "output": redact(detail) if detail else None,
                "error_code": None,
                "retryable": False,
            }
        )
        self._write_steps(run_id, steps)
        return step_id

    def finish_step(
        self,
        run_id: str,
        step_id: str,
        status: str,
        *,
        output: Optional[dict[str, Any]] = None,
        error_code: Optional[str] = None,
        retryable: Optional[bool] = None,
        duration_ms: Optional[int] = None,
    ) -> Optional[dict[str, Any]]:
        steps = self.read_steps(run_id)
        target = next((step for step in steps if step.get("step_id") == step_id), None)
        if target is None:
            return None
        finished_at = _now()
        started = _parse_time(target.get("started_at"))
        finished = _parse_time(finished_at)
        if duration_ms is None and started and finished:
            duration_ms = int((finished - started).total_seconds() * 1000)
        target.update(
            {
                "status": str(status or "ok"),
                "finished_at": finished_at,
                "duration_ms": duration_ms,
                "output": redact(output) if output is not None else target.get("output"),
            }
        )
        if error_code:
            target["error_code"] = str(error_code)
            target["retryable"] = (
                is_retryable(error_code) if retryable is None else bool(retryable)
            )
        elif retryable is not None:
            target["retryable"] = bool(retryable)
        self._write_steps(run_id, steps)
        return target

    def record_step(
        self,
        run_id: str,
        kind: str,
        *,
        status: str = "ok",
        page_signature: str = "",
        input_digest: str = "",
        attempt: int = 1,
        output: Optional[dict[str, Any]] = None,
        error_code: Optional[str] = None,
        duration_ms: Optional[int] = None,
    ) -> str:
        """Record a step that begins and ends in the same breath."""
        step_id = self.start_step(
            run_id,
            kind,
            status="started",
            page_signature=page_signature,
            input_digest=input_digest,
            attempt=attempt,
        )
        self.finish_step(
            run_id,
            step_id,
            status,
            output=output,
            error_code=error_code,
            duration_ms=duration_ms,
        )
        return step_id

    def step_summary(self, run_id: str) -> dict[str, Any]:
        steps = self.read_steps(run_id)
        by_kind: dict[str, int] = {}
        by_status: dict[str, int] = {}
        error_codes: dict[str, int] = {}
        for step in steps:
            kind = str(step.get("kind") or "step")
            status = str(step.get("status") or "unknown")
            by_kind[kind] = by_kind.get(kind, 0) + 1
            by_status[status] = by_status.get(status, 0) + 1
            code = step.get("error_code")
            if code:
                error_codes[str(code)] = error_codes.get(str(code), 0) + 1
        return {
            "steps": len(steps),
            "by_kind": by_kind,
            "by_status": by_status,
            "error_codes": error_codes,
            "duration_ms": sum(int(step.get("duration_ms") or 0) for step in steps),
            "retried": sum(1 for step in steps if int(step.get("attempt") or 1) > 1),
        }

    # ------------------------------------------------------------------ reading

    def read_events(self, run_id: str) -> list[dict[str, Any]]:
        path = self._dir(run_id) / "events.jsonl"
        if not path.exists():
            return []
        events = []
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return events

    def read_audit(self, run_id: str) -> Optional[dict[str, Any]]:
        path = self._dir(run_id) / "audit.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def read_meta(self, run_id: str) -> Optional[dict[str, Any]]:
        path = self._dir(run_id) / "meta.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def run_detail(self, run_id: str) -> Optional[dict[str, Any]]:
        meta = self.read_meta(run_id)
        if not meta:
            return None
        return {
            "meta": meta,
            "steps": self.read_steps(run_id),
            "summary": self.step_summary(run_id),
            "events": self.read_events(run_id),
            "audit": self.read_audit(run_id),
        }

    def list_runs(self, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        runs: list[dict[str, Any]] = []
        for child in self.root.iterdir():
            if not child.is_dir() or not _RUN_ID_RE.match(child.name):
                continue
            meta = self.read_meta(child.name) or {}
            steps = self.read_steps(child.name)
            runs.append(
                {
                    "run_id": child.name,
                    "state": meta.get("state", "UNKNOWN"),
                    "started_at": meta.get("started_at"),
                    "finished_at": meta.get("finished_at"),
                    "duration_ms": meta.get("duration_ms"),
                    "query": meta.get("query"),
                    "run_mode": meta.get("run_mode"),
                    "target_url": meta.get("target_url"),
                    "error_code": meta.get("error_code"),
                    "steps": len(steps),
                    "mtime": child.stat().st_mtime,
                }
            )
        runs.sort(key=lambda item: item.get("mtime", 0), reverse=True)
        start = max(0, int(offset or 0))
        return runs[start : start + max(1, limit)]
