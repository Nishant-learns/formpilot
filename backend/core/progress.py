"""Detect a run that is spinning without making progress.

A page that never changes is the most expensive failure mode: the loop keeps
re-reading, re-filling and re-asking while the human waits.  Time limits catch
it eventually, but only after the budget is gone.

This module is the guard.  It is pure: the loop feeds it an observation and it
returns a verdict.  Two thresholds, deliberately different:

* ``repeat_threshold`` — the point where we *believe* the run is stuck.  In
  shadow mode this only records evidence; it does not act.
* ``stall_threshold`` — the point where we stop and ask the human.

Both need time as well as cycles.  A slow page that renders in ten seconds
must not be called a stall after three fast re-reads, so a key also has to
stay unchanged for ``min_shadow_seconds`` / ``min_stall_seconds``.

Shadow-first is the point: a false positive at the low threshold is measured,
not inflicted.  Only the high threshold changes behaviour.

Progress means the page changed or the visible values changed.  Re-reading the
same page is not progress, and a revisit alone is not progress either.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple


class ProgressVerdict(str, Enum):
    PROGRESS = "progress"
    REPEAT = "repeat"
    SHADOW_STALL = "shadow_stall"
    STALL = "stall"


@dataclass(frozen=True)
class ProgressObservation:
    """What the loop saw in one cycle.

    ``page`` is the page identity (URL + step + field count) and ``fields`` is
    a digest of the visible values.  If neither changed, the cycle produced
    nothing the human would notice.
    """

    page: str
    fields: str = ""

    def key(self) -> Tuple[str, str]:
        return (self.page, self.fields)


@dataclass
class ProgressTracker:
    repeat_threshold: int = 3
    stall_threshold: int = 6
    shadow: bool = True
    min_shadow_seconds: float = 15.0
    min_stall_seconds: float = 45.0
    clock: Callable[[], float] = time.monotonic
    observations: int = 0
    repeats: int = 0
    shadow_stalls: int = 0
    stalls: int = 0
    resets: int = 0
    last_key: Optional[Tuple[str, str]] = None
    key_since: Optional[float] = None
    last_verdict: str = ""
    repeat_run: int = 0
    seen_pages: List[str] = field(default_factory=list)
    last_reset_reason: str = ""

    def observe(self, page: str, fields: str = "") -> ProgressVerdict:
        """Record one cycle and return what it means."""
        observation = ProgressObservation(page=page, fields=fields)
        key = observation.key()
        now = self.clock()
        self.observations += 1
        self.last_verdict = ProgressVerdict.PROGRESS.value

        if key == self.last_key:
            self.repeat_run += 1
            self.repeats += 1
            attempts = self.repeat_run + 1
            elapsed = now - (self.key_since if self.key_since is not None else now)
            # The counters count *episodes* (entering the state), not cycles,
            # so a long stall is one data point rather than dozens.
            if (
                attempts >= max(1, self.stall_threshold)
                and elapsed >= self.min_stall_seconds
            ):
                if attempts == max(1, self.stall_threshold):
                    self.stalls += 1
                self.last_verdict = ProgressVerdict.STALL.value
                return ProgressVerdict.STALL
            if (
                attempts >= max(1, self.repeat_threshold)
                and elapsed >= self.min_shadow_seconds
            ):
                if self.shadow:
                    if attempts == max(1, self.repeat_threshold):
                        self.shadow_stalls += 1
                    self.last_verdict = ProgressVerdict.SHADOW_STALL.value
                    return ProgressVerdict.SHADOW_STALL
                if attempts == max(1, self.repeat_threshold):
                    self.stalls += 1
                self.last_verdict = ProgressVerdict.STALL.value
                return ProgressVerdict.STALL
            return ProgressVerdict.REPEAT

        # A new key is progress.  A revisit of an old page still counts only
        # because the page or the visible values changed.
        if page and page not in self.seen_pages:
            self.seen_pages.append(page)
            if len(self.seen_pages) > 50:
                self.seen_pages = self.seen_pages[-50:]
        self.last_key = key
        self.key_since = now
        self.repeat_run = 0
        return ProgressVerdict.PROGRESS

    def reset(self, reason: str = "") -> None:
        """Start a fresh budget after a human acted or the run moved on."""
        self.last_key = None
        self.key_since = None
        self.repeat_run = 0
        self.resets += 1
        self.last_reset_reason = reason

    def snapshot(self) -> Dict[str, Any]:
        return {
            "observations": self.observations,
            "repeats": self.repeats,
            "shadow_stalls": self.shadow_stalls,
            "stalls": self.stalls,
            "resets": self.resets,
            "repeat_run": self.repeat_run,
            "last_verdict": self.last_verdict,
            "last_reset_reason": self.last_reset_reason,
            "repeat_threshold": self.repeat_threshold,
            "stall_threshold": self.stall_threshold,
            "shadow": self.shadow,
            "min_shadow_seconds": self.min_shadow_seconds,
            "min_stall_seconds": self.min_stall_seconds,
            "unchanged_seconds": round(
                (self.clock() - self.key_since) if self.key_since is not None else 0.0,
                1,
            ),
        }
