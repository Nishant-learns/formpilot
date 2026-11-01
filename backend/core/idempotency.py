"""Distributed Idempotency Engine for FormPilot.

Guarantees exactly-once execution semantics for state-mutating API operations
(e.g., /api/agent/start, /api/agent/user-response, /api/vault updates), preventing
accidental double-submissions, duplicate form fills, or redundant gateway requests.
"""

from __future__ import annotations

import asyncio
import re
import time
from collections import OrderedDict
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional, Tuple

_VALID_KEY_RE = re.compile(r"^[A-Za-z0-9_\-\.]{4,256}$")


class IdempotencyStatus(str, Enum):
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class IdempotencyConflictError(Exception):
    """Raised when a concurrent request with the identical idempotency key is already running."""

    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(f"Operation with idempotency key '{key}' is already in progress.")


@dataclass
class IdempotencyEntry:
    key: str
    status: IdempotencyStatus
    status_code: int = 200
    response_body: Any = None
    response_headers: Optional[Dict[str, str]] = None
    created_at: float = 0.0
    expires_at: float = 0.0
    error_detail: Optional[str] = None

    def is_expired(self) -> bool:
        return time.monotonic() >= self.expires_at


class IdempotencyEngine:
    """Thread-safe and async-safe LRU Idempotency Engine."""

    def __init__(self, max_entries: int = 5000, default_ttl_seconds: int = 86400) -> None:
        self.max_entries = max_entries
        self.default_ttl = default_ttl_seconds
        self._entries: OrderedDict[str, IdempotencyEntry] = OrderedDict()
        self._lock = asyncio.Lock()

    @staticmethod
    def is_valid_key(key: str) -> bool:
        if not key or not isinstance(key, str):
            return False
        return bool(_VALID_KEY_RE.match(key.strip()))

    async def acquire(self, key: str, ttl_seconds: Optional[int] = None) -> Tuple[bool, Optional[IdempotencyEntry]]:
        """Attempt to acquire execution lease for an idempotency key.
        
        Returns:
            (True, None) -> Lease acquired; proceed to execute operation.
            (False, entry) -> Cached completed response available; replay result.
            
        Raises:
            IdempotencyConflictError -> When operation is currently running.
            ValueError -> When key format is invalid.
        """
        if not self.is_valid_key(key):
            raise ValueError(f"Invalid idempotency key format: '{key}'")

        key = key.strip()
        now = time.monotonic()
        ttl = ttl_seconds or self.default_ttl

        async with self._lock:
            # Check existing entry
            if key in self._entries:
                entry = self._entries[key]
                if entry.is_expired():
                    del self._entries[key]
                elif entry.status == IdempotencyStatus.COMPLETED:
                    # Move to end (most recently accessed)
                    self._entries.move_to_end(key)
                    return False, entry
                elif entry.status == IdempotencyStatus.IN_PROGRESS:
                    raise IdempotencyConflictError(key)
                elif entry.status == IdempotencyStatus.FAILED:
                    # Previous execution failed, allow re-acquisition
                    del self._entries[key]

            # Enforce LRU capacity limit
            while len(self._entries) >= self.max_entries:
                self._entries.popitem(last=False)

            # Record new IN_PROGRESS entry
            new_entry = IdempotencyEntry(
                key=key,
                status=IdempotencyStatus.IN_PROGRESS,
                created_at=now,
                expires_at=now + ttl,
            )
            self._entries[key] = new_entry
            return True, None

    async def complete(
        self,
        key: str,
        status_code: int,
        response_body: Any,
        headers: Optional[Dict[str, str]] = None,
    ) -> None:
        """Mark an idempotency key as COMPLETED with cached response data."""
        key = key.strip()
        async with self._lock:
            if key in self._entries:
                entry = self._entries[key]
                entry.status = IdempotencyStatus.COMPLETED
                entry.status_code = status_code
                entry.response_body = response_body
                entry.response_headers = headers or {}
                self._entries.move_to_end(key)

    async def fail(self, key: str, error_detail: str) -> None:
        """Mark an idempotency key as FAILED or release it for retry."""
        key = key.strip()
        async with self._lock:
            if key in self._entries:
                entry = self._entries[key]
                entry.status = IdempotencyStatus.FAILED
                entry.error_detail = error_detail

    async def get(self, key: str) -> Optional[IdempotencyEntry]:
        """Fetch active idempotency entry if exists and not expired."""
        key = key.strip()
        async with self._lock:
            if key in self._entries:
                entry = self._entries[key]
                if entry.is_expired():
                    del self._entries[key]
                    return None
                return entry
            return None

    async def clear(self) -> None:
        """Clear all stored idempotency entries."""
        async with self._lock:
            self._entries.clear()

    def size(self) -> int:
        return len(self._entries)


# Global singleton instance
idempotency_engine = IdempotencyEngine()
