"""Small, dependency-free run journal for auditability and support."""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from . import settings


_RUN_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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

    def start(self, run_id: str, meta: dict[str, Any]) -> None:
        directory = self._dir(run_id)
        payload = {"run_id": run_id, "started_at": _now(), **meta}
        self._atomic_write(directory / "meta.json", json.dumps(payload, indent=2, default=str))

    def append(self, run_id: str, event: dict[str, Any]) -> None:
        directory = self._dir(run_id)
        line = json.dumps({"run_id": run_id, "logged_at": _now(), **event}, default=str) + "\n"
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
        meta.update({"state": state, "finished_at": _now(), **(extra or {})})
        self._atomic_write(meta_path, json.dumps(meta, indent=2, default=str))

    def save_audit(self, run_id: str, audit: dict[str, Any]) -> None:
        directory = self._dir(run_id)
        self._atomic_write(directory / "audit.json", json.dumps(audit, indent=2, default=str))

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

    def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        runs: list[dict[str, Any]] = []
        for child in self.root.iterdir():
            if not child.is_dir() or not _RUN_ID_RE.match(child.name):
                continue
            meta = self.read_meta(child.name) or {}
            runs.append(
                {
                    "run_id": child.name,
                    "state": meta.get("state", "UNKNOWN"),
                    "started_at": meta.get("started_at"),
                    "finished_at": meta.get("finished_at"),
                    "query": meta.get("query"),
                    "mtime": child.stat().st_mtime,
                }
            )
        runs.sort(key=lambda item: item.get("mtime", 0), reverse=True)
        return runs[: max(1, limit)]
