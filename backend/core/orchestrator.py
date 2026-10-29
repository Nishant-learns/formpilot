from __future__ import annotations

import asyncio
import base64
import datetime
import hashlib
import inspect
import json
import os
import re
import time
import traceback
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urljoin, urlparse

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    async_playwright,
)

from . import decision_policy, field_commit, field_registry, settings
from .action_resolver import ActionResolver, ActionResult
from .biometrics import BiometricCompressor
from .blueprint import BlueprintElement, PageBlueprint
from .dom_scanner import DOMScanner
from .failures import classify_failure
from .facts import FactBook
from .fill_plan import build_fill_plan
from .form_model import FormModel
from .gates import apply_gate_metadata, gate_reason
from .live_browser import LiveBrowserSession, live_sessions
from .navigator import ResilientNavigator
from .oracle import OracleResult, PortalOracle
from .page_brief import PageInterpreter
from .perception import Perception
from .portal_accounts import CONFLICT_CHOICES, PortalAccountStore, build_conflict_gate
from .portal_adapter import BasePortalAdapter, get_adapter
from .recipe import RecipeStore
from .run_store import RunStore
from .tinyfish_client import TinyFishClient, TinyFishError, TinyFishSession
from .vault import CandidateVault, VaultManager


class AgentRunError(RuntimeError):
    """A user-actionable failure.  Its message is safe to show in the UI."""


class FormPilotOrchestrator:
    """Guided form-filling agent with explicit human checkpoints."""

    def __init__(self, broadcast_fn: Optional[Callable[[Dict[str, Any]], Any]] = None):
        self.broadcast_fn = broadcast_fn
        self.vault_mgr = VaultManager.get_instance()
        self.tinyfish_mgr = TinyFishClient()
        self.run_store = RunStore()

        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self._adapter: Optional[BasePortalAdapter] = None
        self._session: Optional[TinyFishSession] = None
        self.live: Optional[LiveBrowserSession] = None

        self.is_running = False
        self.paused = False
        self._is_paused = False
        self._stop_requested = False
        self.active_gate: Optional[Dict[str, Any]] = None
        self.active_event_future: Optional[asyncio.Future] = None
        self._pending_user_response: Optional[Dict[str, Any]] = None
        # Browser takeover: the human owns the live page, the loop stays paused,
        # and control is only returned by an explicit "continue" step.
        self._takeover_active = False
        self._takeover_paused_run = False
        self._takeover_started_at: Optional[str] = None

        self.current_section = 1
        self.filled_audit: List[Dict[str, Any]] = []
        self.fill_summary: Optional[Dict[str, Any]] = None
        self.fill_failures: List[Dict[str, Any]] = []
        self._fill_targets: List[Dict[str, Any]] = []
        self._fill_skipped: List[Dict[str, Any]] = []
        self._last_upload_path = ""
        self._entry_mode: Optional[str] = None
        self._requested_entry_mode: Optional[str] = None
        self._entry_options: List[Dict[str, Any]] = []
        self._login_method: Optional[str] = None
        self._login_identifier: Optional[str] = None
        self._requested_login_method: Optional[str] = None
        self._requested_login_identifier: Optional[str] = None

        self.state = "IDLE"
        self.run_id: Optional[str] = None
        self.last_error: Optional[str] = None
        self.target_url = ""
        self.query = ""
        self.mode = "local"
        self.run_mode = "fill"
        self.oracle_result: Optional[OracleResult] = None
        self.form_map: Optional[Dict[str, Any]] = None
        self.page_brief: Optional[Dict[str, Any]] = None
        self.page_interpreter = PageInterpreter()
        self.blueprint: Optional[PageBlueprint] = None
        self._last_action_result: Optional[ActionResult] = None
        self.recipe_store = RecipeStore()
        self._recipe_status: Optional[Dict[str, Any]] = None
        self._last_form_fingerprint = ""
        self._last_recipe_event = ""
        self._pending_upload: Optional[Dict[str, Any]] = None
        self._session_values: Dict[str, str] = {}

        self._otp_cleared = False
        self._otp_signature = ""
        self._last_advance_signature = ""
        self._captcha_signature = ""
        self._last_error_signature = ""
        self._last_gateway_signature = ""
        self._last_scan_key = ""
        self._handled_conflicts: set = set()
        self._open_gate_step: Optional[str] = None
        self._open_gate_signature: str = ""
        # Frozen review snapshot: URL + field-value digest + audit hash.  A
        # changed page invalidates the human's pre-payment review.
        self._approval_snapshot: Optional[Dict[str, Any]] = None
        # Attended-time clock.  The run clock pauses while a gate is open; the
        # wall clock does not, so an absolute ceiling still applies.
        self._run_started_at: Optional[str] = None
        self._run_started_monotonic: Optional[float] = None
        self._gate_seconds = 0.0
        self._gate_opened_monotonic: Optional[float] = None
        self._last_screenshot_at = 0.0
        self._idle_cycles = 0

    # ---------------------------------------------------------------- public API

    def _engine_session_info(self) -> Optional[Dict[str, Any]]:
        """Safe, diagnostic view of the cloud/local browser session.

        The CDP URL is deliberately omitted: it is a live control channel, not
        status information.  ``fallback_reason`` carries the TinyFish error
        code (for example ``INSUFFICIENT_CREDITS``) when the cloud browser
        could not start and the run continued locally.
        """
        session = self._session
        if not session:
            return None
        return {
            "session_id": session.session_id,
            "is_cloud": session.is_cloud,
            "proxy_node": session.proxy_node,
            "country_code": session.country_code,
            "fallback_reason": session.fallback_reason,
        }

    def get_state(self) -> Dict[str, Any]:
        browser_open = False
        try:
            browser_open = bool(self.page and not self.page.is_closed())
        except Exception:
            browser_open = False
        return {
            "state": self.state,
            "is_running": self.is_running,
            "paused": self.paused or self._is_paused,
            "run_id": self.run_id,
            "query": self.query,
            "target_url": self.target_url,
            "mode": self.mode,
            "run_mode": self.run_mode,
            "browser_open": browser_open,
            "live_session": self.live.public_info() if self.live and not self.live.closed else None,
            "engine_session": self._engine_session_info(),
            "form_map": self.form_map,
            "page_brief": self.page_brief,
            "blueprint": self.blueprint.summary() if self.blueprint else None,
            "recipe": self._recipe_status,
            "current_section": self.current_section,
            "active_gate": self.active_gate
            if self.is_running or self.state in {"WAITING_FOR_USER", "PAUSED", "AWAITING_PAYMENT"}
            else None,
            "filled_audit": self._public_audit(),
            "fill_summary": self.fill_summary,
            "fill_failures": self.fill_failures,
            "entry_mode": self._entry_mode,
            "entry_options": decision_policy.entry_summary(self._entry_options),
            "login_method": self._login_method,
            "login_identifier": self._login_identifier,
            "last_error": self.last_error,
            "oracle": self.oracle_result.model_dump() if self.oracle_result else None,
            "takeover": self.takeover_state(),
            "portal_account": self._portal_account_summary(),
            "run_clock": self.run_clock(),
        }

    async def start_application(self, query_or_url: str, run_mode: str = "fill"):
        if self.is_running:
            await self.emit_event("SENSE", "An application is already in progress.", "Ek application pehle se chal rahi hai.")
            return
        if run_mode not in {"fill", "inspect"}:
            raise AgentRunError("Unknown run mode. Use 'fill' or 'inspect'.")

        if self.browser or self.page:
            await self._cleanup()
        self.is_running = True
        self.paused = False
        self._is_paused = False
        self._stop_requested = False
        self._pending_user_response = None
        self._pending_upload = None
        self.filled_audit = []
        self.fill_summary = None
        self.fill_failures = []
        self._fill_targets = []
        self._fill_skipped = []
        self._last_upload_path = ""
        self._entry_mode = None
        self._requested_entry_mode = None
        self._entry_options = []
        self._login_method = None
        self._login_identifier = None
        self._requested_login_method = None
        self._requested_login_identifier = None
        self.current_section = 1
        self.active_gate = None
        self.last_error = None
        self.query = (query_or_url or "").strip()
        self.target_url = ""
        self.oracle_result = None
        self.run_mode = run_mode
        self.form_map = None
        self.page_brief = None
        self._recipe_status = None
        self._last_form_fingerprint = ""
        self._last_recipe_event = ""
        self._session_values = {}
        self._otp_cleared = False
        self._otp_signature = ""
        self._last_advance_signature = ""
        self._captcha_signature = ""
        self._last_error_signature = ""
        self._last_gateway_signature = ""
        self._last_scan_key = ""
        self._handled_conflicts: set = set()
        self._open_gate_step: Optional[str] = None
        self._open_gate_signature: str = ""
        self._approval_snapshot = None
        self._run_started_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self._run_started_monotonic = time.monotonic()
        self._gate_seconds = 0.0
        self._gate_opened_monotonic = None
        self._idle_cycles = 0
        self.run_id = f"run-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        self.state = "RESOLVING"
        self.run_store.start(self.run_id, {"query": self.query, "mode": self.mode, "run_mode": self.run_mode})
        self._record_step(
            "run",
            output={"query": self.query, "mode": self.mode, "run_mode": self.run_mode},
        )

        try:
            await self.emit_event(
                "SENSE",
                "Looking up the official portal...",
                "Official portal check kar rahe hain...",
            )

            self.oracle_result = await PortalOracle.resolve_target_live(self.query, self.tinyfish_mgr)
            if not self.oracle_result.target_url:
                raise AgentRunError(self.oracle_result.advisory)

            self.target_url = self.oracle_result.target_url
            await self.emit_event(
                "THINK",
                f"Official portal found: {self.oracle_result.official_name}",
                self.oracle_result.hindi_advisory,
            )

            self.state = "CONNECTING"
            await self._open_browser(self.target_url)

            await self.emit_event(
                "ACT",
                "Opening the application page...",
                "Application page khol rahe hain...",
            )
            nav = await ResilientNavigator.navigate_safely(self.page, self.target_url)
            await self.emit_event(
                "SENSE",
                f"Page ready in {nav.get('elapsed_seconds', 0)}s.",
                "Page load ho gaya. Ab form ki details dekh rahe hain...",
            )

            await self._observe_page(force_emit=True)
            if self.run_mode == "inspect":
                await self._enter_inspect_mode()
                return

            self.state = "RUNNING"
            await self._autonomous_drive_loop()

        except asyncio.CancelledError:
            self.state = "STOPPED"
            await self.emit_event("DECIDE", "Application stopped.", "Application stop ho gayi.")
        except AgentRunError as exc:
            if self._stop_requested:
                self.state = "STOPPED"
            else:
                self.state = "FAILED"
                self.last_error = str(exc)
                await self.emit_event(
                    "DECIDE",
                    str(exc),
                    "Is portal ko verify nahi kar paye. Official notification link check karein.",
                    force_screenshot=True,
                )
        except Exception:
            if self._stop_requested:
                self.state = "STOPPED"
            else:
                self.state = "FAILED"
                self.last_error = "Something went wrong while filling this portal. Please try again or use the official portal directly."
                traceback.print_exc()
                await self.emit_event(
                    "DECIDE",
                    self.last_error,
                    "Kuch technical dikkat aa gayi. Dobara koshish karein ya official portal par khud apply karein.",
                    force_screenshot=True,
                )
        finally:
            self.is_running = False
            if self.state not in {"AWAITING_PAYMENT", "INSPECT_READY"}:
                await self._cleanup()
            self._record_step(
                "run",
                status="ok" if self.state in {"DONE", "AWAITING_PAYMENT", "INSPECT_READY"} else "failed",
                error_code=None if self.state in {"DONE", "AWAITING_PAYMENT", "INSPECT_READY"} else "internal_error",
                output={"state": self.state, "error": self.last_error},
            )
            self.run_store.finish(
                self.run_id or "unknown",
                self.state,
                {
                    "error": self.last_error,
                    "target_url": self.target_url,
                    "run_mode": self.run_mode,
                    "run_clock": self.run_clock(),
                },
            )

    async def stop(self):
        self._stop_requested = True
        self.is_running = False
        self.paused = False
        self._is_paused = False
        self._takeover_active = False
        self._takeover_paused_run = False
        self._takeover_started_at = None
        self.state = "STOPPED"
        if self.active_event_future and not self.active_event_future.done():
            self.active_event_future.set_result({"action": "STOPPED"})
        self.active_event_future = None
        self.active_gate = None
        await self._cleanup()
        if self.run_id:
            self.run_store.finish(self.run_id, "STOPPED")
        await self.emit_event("DECIDE", "Application stopped.", "Application stop ho gayi.")

    async def reset_session(self) -> bool:
        """Return a finished session to a clean launcher state.

        Only allowed when nothing is running; a live run must be stopped first
        so this can never silently discard an in-flight application.
        """
        if self.is_running:
            return False
        await self._cleanup()
        self.state = "IDLE"
        self.run_id = None
        self.query = ""
        self.target_url = ""
        self.oracle_result = None
        self.form_map = None
        self.page_brief = None
        self._recipe_status = None
        self.current_section = 1
        self.filled_audit = []
        self.fill_summary = None
        self.fill_failures = []
        self._fill_targets = []
        self._fill_skipped = []
        self._last_upload_path = ""
        self._entry_mode = None
        self._requested_entry_mode = None
        self._entry_options = []
        self._login_method = None
        self._login_identifier = None
        self._requested_login_method = None
        self._requested_login_identifier = None
        self.last_error = None
        self.active_gate = None
        self._pending_user_response = None
        self._stop_requested = False
        self.paused = False
        self._is_paused = False
        self._takeover_active = False
        self._takeover_paused_run = False
        self._takeover_started_at = None
        self._approval_snapshot = None
        self._run_started_at = None
        self._run_started_monotonic = None
        self._gate_seconds = 0.0
        self._gate_opened_monotonic = None
        self.run_mode = "fill"
        return True

    def pause(self):
        self._is_paused = True
        self.paused = True
        self.state = "PAUSED"

    def resume(self):
        self._is_paused = False
        self.paused = False
        if self.state == "PAUSED":
            self.state = "RUNNING"

    # ---------------------------------------------------------------- takeover

    def takeover_state(self) -> Dict[str, Any]:
        """Whether the human owns the browser right now.

        ``available`` says a live page exists to take.  ``active`` says the
        human has it.  ``paused_run`` records that FormPilot paused itself for
        the takeover, so resuming is an explicit human action.
        """
        live_open = bool(self.live and not self.live.closed)
        return {
            "available": live_open,
            "active": self._takeover_active,
            "paused_run": self._takeover_paused_run,
            "started_at": self._takeover_started_at,
            "control_enabled": bool(getattr(self.live, "_control_enabled", False))
            if live_open
            else False,
        }

    async def take_human_control(self) -> Dict[str, Any]:
        """Give the human exclusive control of the live page.

        Always available while a live browser is open.  If the agent was
        driving, the loop pauses first so the human and the operator never
        act on the same page at the same time.  If a checkpoint is already
        waiting, the checkpoint keeps the human in control and no extra pause
        is needed.
        """
        if not self.live or self.live.closed:
            return {
                "success": False,
                "message": "There is no live browser open to take over.",
                "takeover": self.takeover_state(),
            }
        if self._takeover_active:
            self.live.set_allow_control(
                True, "You have control of the live browser. FormPilot is paused."
            )
            return {
                "success": True,
                "already": True,
                "state": self.state,
                "takeover": self.takeover_state(),
            }
        if not self.is_running and self.state not in {"PAUSED", "INSPECT_READY"}:
            return {
                "success": False,
                "message": "There is no active application to take over.",
                "takeover": self.takeover_state(),
            }

        self._takeover_active = True
        self._takeover_started_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self._record_step("takeover", output={"event": "started", "state": self.state})
        waiting_at_gate = self.active_gate is not None or self.state in {
            "WAITING_FOR_USER",
            "AWAITING_PAYMENT",
        }
        if not waiting_at_gate and self.is_running:
            self.pause()
            self._takeover_paused_run = True
        self.live.set_allow_control(
            True, "You have control of the live browser. FormPilot is paused."
        )
        await self.emit_event(
            "DECIDE",
            "You have the browser. FormPilot is paused until you return control.",
            "Browser ab aapke paas hai. Jab tak aap control wapas nahi karenge, FormPilot ruka rahega.",
        )
        return {
            "success": True,
            "state": self.state,
            "takeover": self.takeover_state(),
        }

    async def return_human_control(self, *, refresh: bool = True) -> Dict[str, Any]:
        """Take the page back, re-read it, and stay paused for a human check.

        The page may have navigated or changed while the human was driving, so
        the operator's blueprint and the shared brief are rebuilt before the
        run can continue.  Control is not handed back to the loop automatically:
        the human reviews the fresh brief and presses Continue.
        """
        if not self._takeover_active:
            return {
                "success": False,
                "message": "The browser is not in human control.",
                "takeover": self.takeover_state(),
            }

        self._takeover_active = False
        self._record_step("takeover", output={"event": "returned", "state": self.state})
        if self.live and not self.live.closed:
            self.live.set_allow_control(
                False, "FormPilot is reading the page again. Control returns in a moment."
            )
        brief = self.page_brief
        refreshed = False
        if refresh and self.page and not self.page.is_closed():
            try:
                brief = await self.get_page_brief(refresh=True, adopt_blueprint=True)
                refreshed = True
            except Exception:
                traceback.print_exc()

        approval = await self._verify_approval_snapshot()

        # At a checkpoint the human is still expected to act, so control goes
        # back to them once the rescan is complete.  A paused driving run stays
        # with the operator until the human presses Continue.
        waiting_at_gate = self.active_gate is not None or self.state in {
            "WAITING_FOR_USER",
            "AWAITING_PAYMENT",
        }
        if self.live and not self.live.closed:
            if waiting_at_gate:
                self.live.set_allow_control(
                    True, "The checkpoint still needs you. FormPilot has re-read the page."
                )
            else:
                self.live.set_allow_control(
                    False,
                    "FormPilot is paused after your changes. Review the page, then continue.",
                )

        await self.emit_event(
            "SENSE",
            "You returned control. The page was re-read; FormPilot stays paused until you continue.",
            "Aapne control wapas diya. Page dobara padh liya; continue karne tak FormPilot ruka rahega.",
            force_screenshot=True,
        )
        self._takeover_paused_run = False
        self._takeover_started_at = None
        return {
            "success": True,
            "state": self.state,
            "paused": self.paused or self._is_paused,
            "refreshed": refreshed,
            "page_brief": brief,
            "approval": approval,
            "takeover": self.takeover_state(),
        }

    def _release_live_control(self, reason: str) -> None:
        """Give control back to the loop unless the human still owns it."""
        if not self.live or self.live.closed:
            return
        if self._takeover_active:
            # A gate may close while the human is still driving; returning
            # control stays an explicit step.
            return
        self.live.set_allow_control(False, reason)

    # ------------------------------------------------------------ portal memory

    def _current_domain(self) -> str:
        url = self.page.url if self.page else (self.target_url or "")
        return urlparse(str(url or "")).netloc.lower()

    def _remember_portal_account(self, **fields: Any) -> None:
        domain = self._current_domain()
        if not domain:
            return
        try:
            PortalAccountStore.get_instance().record(domain, **fields)
        except Exception:
            traceback.print_exc()

    # ---------------------------------------------------------------- ledger

    def _page_signature(self) -> str:
        if isinstance(self.form_map, dict):
            return str(self.form_map.get("fingerprint") or "")
        return ""

    def _record_step(
        self,
        kind: str,
        *,
        status: str = "ok",
        page_signature: str = "",
        input_digest: str = "",
        output: Optional[Dict[str, Any]] = None,
        error_code: Optional[str] = None,
        duration_ms: Optional[int] = None,
        attempt: int = 1,
    ) -> Optional[str]:
        """Write one row to the run ledger.  Never let bookkeeping break a run."""
        if not self.run_id:
            return None
        try:
            return self.run_store.record_step(
                self.run_id,
                kind,
                status=status,
                page_signature=page_signature or self._page_signature(),
                input_digest=input_digest,
                output=output,
                error_code=error_code,
                duration_ms=duration_ms,
                attempt=attempt,
            )
        except Exception:
            traceback.print_exc()
            return None

    def _open_step(self, kind: str, **kwargs: Any) -> Optional[str]:
        if not self.run_id:
            return None
        try:
            return self.run_store.start_step(self.run_id, kind, **kwargs)
        except Exception:
            traceback.print_exc()
            return None

    def _close_step(self, step_id: Optional[str], status: str, **kwargs: Any) -> None:
        if not step_id or not self.run_id:
            return
        try:
            self.run_store.finish_step(self.run_id, step_id, status, **kwargs)
        except Exception:
            traceback.print_exc()

    def _start_gate_step(self, gate: Dict[str, Any]) -> None:
        """Open a ledger row for a gate that is waiting on a human."""
        gate_type = str(gate.get("gate_type") or "GATE")
        signature = "|".join(
            [
                gate_type,
                str(gate.get("stage") or ""),
                str(gate.get("title") or ""),
                str(gate.get("field_key") or ""),
            ]
        )
        if signature == self._open_gate_signature:
            return
        if self._open_gate_step:
            self._close_gate_step("REPLACED")
        # A gate that is re-opened after a close gets a fresh opening time and
        # deadline; a re-emit of the same open gate keeps the original.
        gate.pop("gate_opened_at", None)
        gate.pop("gate_deadline_at", None)
        apply_gate_metadata(gate)
        self._open_gate_signature = signature
        if self._gate_opened_monotonic is None:
            self._gate_opened_monotonic = time.monotonic()
        self._open_gate_step = self._open_step(
            "gate",
            status="waiting",
            page_signature=self._page_signature(),
            detail={
                "gate_type": gate_type,
                "title": gate.get("title"),
                "reason": gate.get("reason"),
                "recommended": gate.get("recommended"),
            },
        )

    def _close_gate_step(self, action: str) -> None:
        if self._gate_opened_monotonic is not None:
            self._gate_seconds += max(0.0, time.monotonic() - self._gate_opened_monotonic)
            self._gate_opened_monotonic = None
        if not self._open_gate_step:
            return
        status = {
            "DISMISS": "dismissed",
            "STOPPED": "stopped",
            "TIMEOUT": "timed_out",
            "REPLACED": "replaced",
        }.get(str(action or ""), "resolved")
        self._close_step(
            self._open_gate_step,
            status,
            output={"action": action or "UNKNOWN"},
        )
        self._open_gate_step = None
        self._open_gate_signature = ""

    def run_clock(self) -> Dict[str, Any]:
        """Active work time, attended gate time, and the absolute wall clock."""
        if self._run_started_monotonic is None:
            return {
                "started_at": None,
                "wall_seconds": 0.0,
                "attended_seconds": 0.0,
                "active_seconds": 0.0,
                "ceiling_seconds": settings.RUN_CEILING_SECONDS,
                "wall_ceiling_seconds": settings.RUN_WALL_CEILING_SECONDS,
                "gate_open": self._gate_opened_monotonic is not None,
            }
        now = time.monotonic()
        wall = max(0.0, now - self._run_started_monotonic)
        open_gate = (
            max(0.0, now - self._gate_opened_monotonic)
            if self._gate_opened_monotonic is not None
            else 0.0
        )
        attended = self._gate_seconds + open_gate
        active = max(0.0, wall - attended)
        return {
            "started_at": self._run_started_at,
            "wall_seconds": round(wall, 1),
            "attended_seconds": round(attended, 1),
            "active_seconds": round(active, 1),
            "ceiling_seconds": settings.RUN_CEILING_SECONDS,
            "wall_ceiling_seconds": settings.RUN_WALL_CEILING_SECONDS,
            "gate_open": self._gate_opened_monotonic is not None,
        }

    def _run_ceiling_exceeded(self) -> bool:
        clock = self.run_clock()
        return (
            clock["active_seconds"] >= settings.RUN_CEILING_SECONDS
            or clock["wall_seconds"] >= settings.RUN_WALL_CEILING_SECONDS
        )

    def _portal_account_summary(self) -> Dict[str, Any]:
        domain = self._current_domain()
        if not domain:
            return {}
        try:
            return PortalAccountStore.get_instance().domain_summary(domain)
        except Exception:
            return {}

    def _set_login_method(self, method: str) -> None:
        self._login_method = str(method or "")
        if self._login_method:
            self._remember_portal_account(
                login_method=self._login_method, confirmed_by_human=True
            )

    def _set_login_identifier(self, key: str) -> None:
        self._login_identifier = str(key or "")
        if not self._login_identifier:
            return
        kind = self._login_identifier
        if kind not in {"mobile", "email", "urn", "aadhaar", "registration_id"}:
            kind = "unknown"
        value = ""
        try:
            value = str(self.vault_mgr.vault.find_field_value(self._login_identifier) or "")
        except Exception:
            value = ""
        self._remember_portal_account(
            identifier_type=kind,
            identifier_value=value,
            identifiers_seen=[kind],
            confirmed_by_human=True,
        )

    def submit_user_response(self, data: Dict[str, Any]):
        self._close_gate_step(str((data or {}).get("action") or ""))
        if self.active_event_future and not self.active_event_future.done():
            self.active_event_future.set_result(data)
        elif self.active_gate is not None:
            self._pending_user_response = data

    def choose_entry_mode(self, mode: str) -> Dict[str, Any]:
        """Select register/login/resume without guessing.

        Called by the chat assistant and by the cockpit.  When the entry gate is
        open the answer is delivered immediately.  Otherwise the choice is
        remembered and applied the next time the portal actually shows an
        entry page.  The choice is validated against the options the page
        offers; an unknown path is refused.
        """
        normalized = decision_policy.normalize_mode(mode)
        if not normalized:
            return {"success": False, "message": "Choose register, login or resume."}

        options = list(self._entry_options or [])
        gate = self.active_gate or {}
        if gate.get("gate_type") == "GATEWAY_DECISION":
            option = decision_policy.match_entry_response({"mode": normalized}, options)
            if not option:
                same_mode = [
                    item for item in options if item.get("mode") == normalized
                ]
                if len(same_mode) > 1:
                    labels = ", ".join(
                        f"'{item.get('text')}'" for item in same_mode
                    )
                    return {
                        "success": False,
                        "message": (
                            f"This page offers more than one {self._entry_label(normalized)} "
                            f"path: {labels}. Choose the exact option."
                        ),
                    }
                return {
                    "success": False,
                    "message": "The portal does not offer that entry path on this page.",
                }
            self._remember_portal_account(
                last_path_choice=normalized, confirmed_by_human=True
            )
            self.submit_user_response(
                {
                    "action": "GATEWAY_CHOICE",
                    "mode": normalized,
                    "type": option.get("type"),
                    "element_id": option.get("element_id"),
                    "text": option.get("text"),
                }
            )
            return {
                "success": True,
                "mode": normalized,
                "message": f"Selected {self._entry_label(normalized)}.",
            }

        if self._entry_mode == normalized:
            return {
                "success": True,
                "mode": normalized,
                "message": f"This session is already using {self._entry_label(normalized)}.",
            }
        if self._entry_mode and self._entry_mode not in {"manual", normalized}:
            return {
                "success": False,
                "message": (
                    "This session already chose a different entry path. "
                    "Start a new session to change it."
                ),
            }
        if options:
            option = decision_policy.match_entry_response({"mode": normalized}, options)
            if not option:
                return {
                    "success": False,
                    "message": "The portal does not offer that entry path on this page.",
                }
        self._requested_entry_mode = normalized
        self._remember_portal_account(
            last_path_choice=normalized, confirmed_by_human=True
        )
        return {
            "success": True,
            "mode": normalized,
            "message": f"I will open {self._entry_label(normalized)} when the portal shows the entry page.",
        }

    def choose_entry_option(self, option: Dict[str, Any]) -> Dict[str, Any]:
        """Select one exact option from the open gateway gate.

        Needed when a page offers two different links with the same entry type
        (for example "Preview ..." and "Proceed ..."), where a mode-only answer
        is ambiguous.
        """
        gate = self.active_gate or {}
        if gate.get("gate_type") != "GATEWAY_DECISION":
            return {"success": False, "message": "There is no entry choice open right now."}
        options = list(self._entry_options or [])
        query: Dict[str, Any] = {
            "element_id": option.get("element_id"),
            "text": option.get("text"),
            "href": option.get("href"),
        }
        if not option.get("text"):
            query["mode"] = option.get("mode") or option.get("type")
        selected = decision_policy.match_entry_response(query, options)
        if not selected:
            return {
                "success": False,
                "message": "That choice did not match an entry path on this page.",
            }
        self.submit_user_response(
            {
                "action": "GATEWAY_CHOICE",
                "mode": selected.get("mode"),
                "type": selected.get("type"),
                "element_id": selected.get("element_id"),
                "id": selected.get("id"),
                "href": selected.get("href"),
                "text": selected.get("text"),
            }
        )
        return {
            "success": True,
            "mode": selected.get("mode"),
            "message": f"Selected {selected.get('text')}.",
        }

    def choose_login_method(self, method: str) -> Dict[str, Any]:
        """Select a login method that the open gate actually offers."""
        normalized = str(method or "").strip()
        if not normalized:
            return {"success": False, "message": "Choose a sign-in method."}
        gate = self.active_gate or {}
        if gate.get("gate_type") == "LOGIN_METHOD":
            options = gate.get("options") or []
            match = next(
                (
                    option
                    for option in options
                    if normalized
                    in {
                        str(option.get("method") or ""),
                        str(option.get("value") or ""),
                        str(option.get("text") or ""),
                    }
                ),
                None,
            )
            if not match:
                return {
                    "success": False,
                    "message": "That sign-in method is not offered on this form.",
                }
            self.submit_user_response(
                {
                    "action": "LOGIN_METHOD_CHOICE",
                    "method": match.get("method"),
                    "value": match.get("value"),
                    "text": match.get("text"),
                }
            )
            return {
                "success": True,
                "method": match.get("method"),
                "message": f"Selected {match.get('label') or match.get('text')}.",
            }
        self._requested_login_method = normalized
        return {
            "success": True,
            "method": normalized,
            "message": "I will use that sign-in method when the login form asks for it.",
        }

    def choose_account_identifier(self, key: str) -> Dict[str, Any]:
        """Select which account identifier the login form should use."""
        normalized = str(key or "").strip()
        if not normalized:
            return {"success": False, "message": "Choose an account identifier."}
        gate = self.active_gate or {}
        if gate.get("gate_type") == "ACCOUNT_IDENTIFIER":
            options = gate.get("options") or []
            match = next(
                (
                    option
                    for option in options
                    if normalized
                    in {
                        str(option.get("key") or ""),
                        str(option.get("value") or ""),
                        str(option.get("text") or ""),
                    }
                ),
                None,
            )
            if not match:
                return {
                    "success": False,
                    "message": "That identifier is not offered on this login form.",
                }
            self.submit_user_response(
                {
                    "action": "ACCOUNT_IDENTIFIER_CHOICE",
                    "key": match.get("key"),
                    "value": match.get("key"),
                    "text": match.get("text"),
                }
            )
            return {
                "success": True,
                "identifier": match.get("key"),
                "message": f"Using {match.get('text')} to identify the account.",
            }
        self._requested_login_identifier = normalized
        return {
            "success": True,
            "identifier": normalized,
            "message": "I will use that identifier when the login form asks for it.",
        }

    @staticmethod
    def _entry_label(mode: str) -> str:
        return {
            "register": "account creation",
            "login": "sign in",
            "resume": "resume application",
        }.get(str(mode or ""), "that entry path")

    # ---------------------------------------------------------------- browser

    async def _open_browser(self, target_url: str):
        cfg = self.tinyfish_mgr.config
        if not self.playwright:
            self.playwright = await async_playwright().start()

        session: Optional[TinyFishSession] = None
        try:
            session = await self.tinyfish_mgr.create_cloud_browser_session(target_url)
        except TinyFishError as exc:
            reason_code = getattr(exc, "code", "") or "cloud_browser_error"
            await self.emit_event(
                "SENSE",
                f"The cloud browser is unavailable right now ({reason_code}). Continuing in this device's browser.",
                "Cloud browser abhi available nahi hai. Is device ke browser mein aage badh rahe hain.",
            )
            session = TinyFishSession(
                session_id=f"local-{uuid.uuid4().hex[:10]}",
                cdp_url="",
                proxy_node="This device",
                country_code=cfg.proxy_region.upper(),
                is_cloud=False,
                fallback_reason=str(exc),
            )

        self._session = session
        self.mode = "cloud" if session.is_cloud else "local"

        if session.is_cloud:
            try:
                self.browser = await self.playwright.chromium.connect_over_cdp(session.cdp_url, timeout=60000)
                self.context = self.browser.contexts[0] if self.browser.contexts else await self.browser.new_context(
                    viewport={"width": 1280, "height": 800}
                )
                self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
                await self.emit_event(
                    "ACT",
                    "Cloud browser connected.",
                    "Cloud browser connect ho gaya. Portal khol rahe hain...",
                )
            except Exception:
                traceback.print_exc()
                await self.emit_event(
                    "SENSE",
                    "Could not open the cloud browser. Continuing in this device's browser.",
                    "Cloud browser nahi khul paya. Is device ke browser mein aage badh rahe hain.",
                )
                try:
                    await self.tinyfish_mgr.terminate_session(session.session_id)
                except Exception:
                    pass
                session.is_cloud = False
                session.cdp_url = ""
                self.browser = None
                self.context = None
                self.page = None
                self.mode = "local"

        if not self.browser or not session.is_cloud:
            self.browser = await self.playwright.chromium.launch(headless=cfg.headless)
            self.context = await self.browser.new_context(viewport={"width": 1280, "height": 800})
            self.page = await self.context.new_page()
            await self.emit_event(
                "ACT",
                "Using this device's browser.",
                "Is device ke browser se portal khol rahe hain.",
            )

        if not self.page:
            raise AgentRunError("Could not open a browser page.")
        self._adapter = get_adapter(target_url)

        try:
            self.live = LiveBrowserSession(
                self.page,
                run_id=self.run_id or "",
                mode=self.mode,
                run_mode=self.run_mode,
            )
            await self.live.start()
            live_sessions.add(self.live)
            if self.run_mode == "inspect":
                self.live.set_allow_control(True, "Inspect mode: the browser is yours.")
            await self.emit_event(
                "ACT",
                "Live browser ready. You can see the real page and take over when asked.",
                "Live browser ready hai. Asli page dikh raha hai; zarurat par aap control le sakte hain.",
            )
        except Exception:
            traceback.print_exc()
            self.live = None
            await self.emit_event(
                "SENSE",
                "The live view could not start, but the application can continue.",
                "Live view shuru nahi ho paya, lekin application jaari rah sakti hai.",
            )

    async def _cleanup(self):
        if self.live:
            live_sessions.remove(self.live)
            try:
                await self.live.stop()
            except Exception:
                pass
            self.live = None
        try:
            if self.browser:
                await self.browser.close()
        except Exception:
            pass
        self.browser = None
        self.context = None
        self.page = None
        self.page_brief = None

        try:
            if self._session and self._session.is_cloud:
                await self.tinyfish_mgr.terminate_session(self._session.session_id)
        except Exception:
            pass
        self._session = None

        try:
            if self.playwright:
                await self.playwright.stop()
        except Exception:
            pass
        self.playwright = None

    # ---------------------------------------------------------------- events

    async def _screenshot(self, force: bool = False) -> str:
        if not self.page:
            return ""
        now = time.monotonic() * 1000
        if not force and now - self._last_screenshot_at < settings.SCREENSHOT_MIN_INTERVAL_MS:
            return ""
        try:
            frame = await ResilientNavigator.capture_high_res_screenshot(self.page)
            if frame:
                self._last_screenshot_at = now
                return f"data:image/jpeg;base64,{base64.b64encode(frame).decode('utf-8')}"
        except Exception:
            pass
        return ""

    async def emit_event(
        self,
        phase: str,
        message: str,
        hindi: str,
        active_gate: Optional[Dict[str, Any]] = None,
        *,
        force_screenshot: bool = False,
    ):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        screenshot_b64 = await self._screenshot(force=force_screenshot or bool(active_gate))
        payload = {
            "timestamp": timestamp,
            "phase": phase,
            "message": message,
            "hindi": hindi,
            "screenshot": screenshot_b64,
            "active_gate": active_gate or self.active_gate,
            "current_section": self.current_section,
            "filled_audit": self._public_audit(),
            "run_id": self.run_id,
            "state": self.state,
            "mode": self.mode,
            "run_mode": self.run_mode,
            "last_error": self.last_error,
            "live_session": self.live.public_info() if self.live and not self.live.closed else None,
            "engine_session": self._engine_session_info(),
            "form_map": self.form_map,
            "page_brief": self.page_brief,
            "blueprint": self.blueprint.summary() if self.blueprint else None,
            "recipe": self._recipe_status,
            "fill_summary": self.fill_summary,
            "fill_failures": self.fill_failures,
            "entry_mode": self._entry_mode,
            "entry_options": decision_policy.entry_summary(self._entry_options),
            "login_method": self._login_method,
            "login_identifier": self._login_identifier,
            "run_clock": self.run_clock(),
        }
        if phase == "DECIDE" and (active_gate or self.active_gate):
            try:
                self._start_gate_step(active_gate or self.active_gate or {})
            except Exception:
                traceback.print_exc()
        if self.broadcast_fn:
            try:
                result = self.broadcast_fn(payload)
                if inspect.isawaitable(result):
                    await result
            except Exception:
                traceback.print_exc()
        try:
            if self.run_id:
                self.run_store.append(
                    self.run_id,
                    {
                        "timestamp": timestamp,
                        "phase": phase,
                        "message": message,
                        "section": self.current_section,
                        "gate_type": (active_gate or self.active_gate or {}).get("gate_type"),
                        "state": self.state,
                    },
                )
        except Exception:
            pass

    # ---------------------------------------------------------------- loop

    async def _scan_dom(self) -> Dict[str, Any]:
        """Capture the page as a legacy DOM plus a typed blueprint.

        ``DOMScanner.scan`` stamps every meaningful element with a per-scan
        ``data-fp-id`` and builds the nested tree the resolver uses.  The
        legacy lists remain in the returned dict so existing callers keep
        working while they migrate to element ids.
        """
        if not self.page:
            raise AgentRunError("The browser page is no longer available.")
        try:
            dom, blueprint = await DOMScanner.scan(self.page)
        except Exception as exc:
            raise AgentRunError("The page is still loading. Please wait a moment and try again.") from exc
        self.blueprint = blueprint
        return dom

    def _action_resolver(self) -> Optional[ActionResolver]:
        if not self.page or not self.blueprint:
            return None
        return ActionResolver(self.page, self.blueprint)

    async def _rescan_blueprint(self) -> Optional[PageBlueprint]:
        try:
            await self._scan_dom()
        except Exception:
            return None
        return self.blueprint

    async def _observe_page(self, *, force_emit: bool = False) -> tuple[Dict[str, Any], Dict[str, Any]]:
        """Read the page, build the normalized form map, and compare it to memory."""
        dom = await self._scan_dom()
        try:
            form_map = FormModel.build_form_map(
                dom,
                self.page.url if self.page else self.target_url,
                vault=self.vault_mgr.vault,
            )
            if self.blueprint is not None:
                form_map["blueprint"] = self.blueprint.summary()
            recipe_status = self.recipe_store.match(form_map)
        except Exception:
            traceback.print_exc()
            form_map = {
                "url": self.page.url if self.page else self.target_url,
                "page_type": "unknown",
                "page_confidence": 0,
                "field_count": len(dom.get("inputs") or []),
                "fields": [],
                "error": "The form model could not be built for this page.",
            }
            recipe_status = {"status": "new", "confidence": 0, "recipe_id": None, "drift": None}

        self.form_map = form_map
        self._recipe_status = recipe_status
        self._record_step(
            "perceive",
            output={
                "page_type": form_map.get("page_type"),
                "field_count": form_map.get("field_count"),
                "confidence": form_map.get("page_confidence"),
                "recipe": recipe_status.get("status"),
            },
        )
        try:
            self._entry_options = decision_policy.entry_options(dom, form_map)
        except Exception:
            self._entry_options = []
        fingerprint = str(form_map.get("fingerprint") or "")
        recipe_event_key = f"{recipe_status.get('status')}:{fingerprint}:{recipe_status.get('recipe_id')}"

        should_emit = force_emit or fingerprint != self._last_form_fingerprint
        if should_emit and recipe_event_key != self._last_recipe_event:
            self._last_form_fingerprint = fingerprint
            self._last_recipe_event = recipe_event_key
            status = str(recipe_status.get("status") or "new")
            if status == "drift":
                drift = recipe_status.get("drift") or {}
                await self.emit_event(
                    "THINK",
                    f"Portal structure changed: {drift.get('summary') or 'the saved recipe no longer matches.'}",
                    "Portal ka structure badal gaya hai. Agent page ko dobara padh raha hai.",
                )
            elif status == "match":
                await self.emit_event(
                    "SENSE",
                    "Saved portal recipe matched this page. Reusing its field map and locators.",
                    "Is page ke liye saved recipe mil gayi. Field map aur locators reuse ho rahe hain.",
                )
            else:
                await self.emit_event(
                    "SENSE",
                    f"This is a new page in memory: {form_map.get('page_type')} with {form_map.get('field_count', 0)} fields.",
                    "Yeh page pehli baar dekh rahe hain. Form ko samajh rahe hain.",
                )
        return dom, form_map

    async def _enter_inspect_mode(self) -> None:
        """Stop before touching the form and leave the real browser open."""
        self.is_running = False
        self.state = "INSPECT_READY"
        if self.live:
            self.live.set_allow_control(True, "Inspect mode: the browser is yours. Nothing will be filled or submitted.")

        saved = None
        if self._has_replayable_structure(self.form_map or {}):
            try:
                saved = self.recipe_store.save_from_form_map(
                    self.form_map or {},
                    source="inspect",
                    status="draft",
                )
                if self._recipe_status is not None:
                    self._recipe_status["saved_recipe"] = RecipeStore.summary(saved)
            except Exception:
                traceback.print_exc()

        form_map = self.form_map or {}
        message = (
            f"Inspect only: {form_map.get('field_count', 0)} fields found on a "
            f"{form_map.get('page_type', 'unknown')} page. Nothing was filled, clicked, paid or submitted."
        )
        await self.emit_event(
            "INSPECT",
            message,
            "Inspect-only mode: form ka structure dekh liya. Kuch bhara ya submit nahi kiya.",
            force_screenshot=True,
        )

    @staticmethod
    def _has_replayable_structure(form_map: Dict[str, Any]) -> bool:
        """An empty SPA shell is not a useful recipe.

        A page with fields or gateway choices has replayable structure.  A
        loading shell with neither must not overwrite a good recipe.
        """
        return bool(form_map.get("fields")) or bool(form_map.get("gateways"))

    def _save_current_recipe(self, source: str = "agent") -> None:
        if not self.form_map or not self._has_replayable_structure(self.form_map):
            return
        try:
            saved = self.recipe_store.save_from_form_map(
                self.form_map,
                source=source,
                status="draft",
            )
            if self._recipe_status is not None:
                self._recipe_status["saved_recipe"] = RecipeStore.summary(saved)
        except Exception:
            traceback.print_exc()

    async def refresh_inspection(self) -> Dict[str, Any]:
        if not self.page:
            raise AgentRunError("There is no live browser to inspect. Open a portal first.")
        dom, form_map = await self._observe_page(force_emit=True)
        if self._has_replayable_structure(form_map):
            try:
                saved = self.recipe_store.save_from_form_map(
                    form_map, source="inspect", status="draft"
                )
                if self._recipe_status is not None:
                    self._recipe_status["saved_recipe"] = RecipeStore.summary(saved)
            except Exception:
                traceback.print_exc()
        self.state = "INSPECT_READY" if self.run_mode == "inspect" else self.state
        await self.emit_event(
            "INSPECT",
            f"Page rescanned: {form_map.get('field_count', 0)} fields on a {form_map.get('page_type', 'unknown')} page.",
            "Page dobara scan ho gaya.",
            force_screenshot=True,
        )
        return form_map

    async def get_page_brief(
        self, *, refresh: bool = False, adopt_blueprint: bool = False
    ) -> Dict[str, Any]:
        """Read the live page and return a human-readable brief.

        This is read-only.  It never fills, clicks, uploads or submits.  The
        scan is local to this call so an explicit refresh cannot replace the
        operator's current blueprint mid-action.  ``adopt_blueprint`` is only
        used after a human takeover, when the operator must deliberately adopt
        the page the human left behind.
        """
        if not self.page or self.page.is_closed():
            if self.page_brief and not refresh:
                return self.page_brief
            raise AgentRunError("There is no live browser to read. Open a portal first.")
        try:
            if adopt_blueprint:
                dom, blueprint = await self._scan_dom()
                self.blueprint = blueprint
            else:
                dom, blueprint = await DOMScanner.scan(self.page)
        except Exception as exc:
            raise AgentRunError(
                "The page is still loading. Please wait a moment and read it again."
            ) from exc
        perception = Perception.from_scan(dom, blueprint)
        brief = await self.page_interpreter.interpret(perception, force=refresh)
        domain = urlparse(brief.url).netloc
        fact_book = FactBook.get_instance()
        fact_book.annotate_brief(brief, domain=domain)
        self.page_brief = {
            **brief.model_dump(),
            "summary_line": brief.summary_line(),
            "fact_summary": fact_book.summary(domain=domain),
        }
        return self.page_brief

    async def inspect_login_options(self) -> Dict[str, Any]:
        """Read the visible login/recovery options without touching the page.

        This is the read-only inspection used when the candidate is not sure
        whether they registered.  It never submits a credential, requests an
        OTP or resets anything.
        """
        if not self.page or self.page.is_closed():
            raise AgentRunError("There is no live browser to inspect. Open a portal first.")
        try:
            dom, _blueprint = await DOMScanner.scan(self.page)
        except Exception as exc:
            raise AgentRunError(
                "The page is still loading. Please wait a moment and inspect it again."
            ) from exc
        inspection = PortalAccountStore.inspect_login_ui(dom).model_dump()
        inspection["account_memory"] = self._portal_account_summary()
        return inspection

    async def attach_upload(self, path: str, field_key: str) -> Dict[str, Any]:
        """Attach a user-provided file to the correct file input.

        The file is used only in the live portal session.  It is not copied
        into the vault and it is not reused for another portal.
        """
        if not self.page:
            return {"success": False, "message": "There is no live browser to upload to."}
        upload_path = Path(path)
        if not upload_path.is_file():
            return {"success": False, "message": "The uploaded file could not be found."}

        try:
            dom = await self._scan_dom()
        except Exception:
            dom = {"inputs": [], "fileInputs": []}

        target = None
        inputs = [item for item in (dom.get("inputs") or []) if str(item.get("type") or "").lower() == "file"]
        for item in inputs:
            sem_key, _ = DOMScanner.classify_field(item)
            if sem_key == field_key or item.get("name") == field_key or item.get("id") == field_key:
                target = item
                break
        if target is None:
            if len(inputs) == 1:
                target = inputs[0]
            elif inputs:
                # Never guess between a photo and a signature field.  A wrong
                # file would be sent to the portal under the user's name.
                return {
                    "success": False,
                    "message": (
                        "More than one file field is visible and none matched "
                        f"'{field_key}'. Attach the file in the live browser, then continue."
                    ),
                }

        try:
            if target and target.get("id"):
                locator = self.page.locator(f"#{target.get('id')}").first
            elif target and target.get("name"):
                locator = self.page.locator(f"[name='{target.get('name')}']").first
            elif target is not None:
                index = int(target.get("index") or 0)
                locator = self.page.locator("input[type='file']").nth(index)
            else:
                locator = self.page.locator("input[type='file']").first
            if await locator.count() == 0:
                return {"success": False, "message": "This page does not have a visible file input."}
            await locator.set_input_files(str(upload_path), timeout=15000)
            await self.page.wait_for_timeout(200)
            fresh = await self._scan_dom()
            if target:
                attached = self._file_attached(target, fresh)
            else:
                files = [
                    entry for entry in (fresh.get("fileInputs") or []) if entry.get("hasFile")
                ]
                attached = len(files) == 1
            if not attached:
                return {
                    "success": False,
                    "message": "The portal did not keep the attached file. Attach it in the live browser.",
                }
        except Exception as exc:
            return {"success": False, "message": f"The portal did not accept the file: {exc}"}

        self._record_fill(
            target or {"label": field_key, "type": "file"},
            field_key,
            str(upload_path),
            "file",
        )
        await self.emit_event(
            "ACT",
            f"Uploaded the file for {field_key.replace('_', ' ')}.",
            f"{field_key.replace('_', ' ')} ke liye file upload ho gayi.",
        )
        return {
            "success": True,
            "field_key": field_key,
            "message": "File attached to the live portal. It was not saved to your vault.",
        }


    async def _autonomous_drive_loop(self):
        while self.is_running:
            if self._run_ceiling_exceeded():
                clock = self.run_clock()
                raise AgentRunError(
                    "This run has reached its time limit "
                    f"({int(clock['active_seconds'])}s of active work). "
                    "Please continue from the portal yourself."
                )
            if self._is_paused:
                self.state = "PAUSED"
                await asyncio.sleep(0.4)
                continue
            self.state = "RUNNING"

            dom, _form_map = await self._observe_page()
            adapter = self._adapter or get_adapter(self.page.url if self.page else "")
            self._adapter = adapter
            step = adapter.current_step(self.page, dom)
            self.current_section = step

            if await self._account_conflict_checkpoint(dom):
                continue

            if adapter.is_payment_page(self.page, dom):
                await self._trigger_pre_payment_lock()
                return

            scan_key = f"{dom.get('url')}|{adapter.step_key(self.page, dom)}|{len(dom.get('inputs') or [])}"
            if scan_key != self._last_scan_key:
                self._last_scan_key = scan_key
                self._idle_cycles = 0
                await self.emit_event(
                    "SENSE",
                    f"Reading the page: {len(dom.get('inputs') or [])} fields found.",
                    "Page padh rahe hain. Form ke fields dekh rahe hain...",
                )

            gateways = dom.get("gateways") or []
            inputs = dom.get("inputs") or []

            # A chat request such as "I need to register first" is remembered
            # until the portal entry page is actually on screen.  It is applied
            # only to an explicit option that the page offers.
            if self._requested_entry_mode and decision_policy.is_entry_page(dom, self.form_map):
                requested = decision_policy.match_entry_response(
                    {"mode": self._requested_entry_mode},
                    self._entry_options,
                )
                self._requested_entry_mode = None
                if requested:
                    await self._apply_entry_option(requested)
                    continue

            # Entry mode is never inferred from the URL or history.  The first
            # entry page always asks when more than one path is visible.
            if not self._entry_mode and decision_policy.is_entry_page(dom, self.form_map):
                await self._gateway_checkpoint(dom, gateways)
                continue

            page_type = str((self.form_map or {}).get("page_type") or "")
            if self._entry_mode == "login" or page_type == "login":
                if await self._login_method_checkpoint(dom):
                    continue
                if await self._login_identifier_checkpoint(dom):
                    continue

            if not inputs:
                # A signed-in dashboard is a hub, not the end of the run.  Its
                # links open the real application; ask which one to use.
                if await self._dashboard_next_step(dom, gateways):
                    continue
                visible = str(dom.get("visibleText") or "").lower()
                if any(token in visible for token in ("dashboard", "registration id", "logged in", "sign out", "logout")):
                    self.state = "DONE"
                    self.is_running = False
                    await self.emit_event(
                        "DECIDE",
                        "You are signed in. There is no application form on this page.",
                        "Aap sign in ho gaye hain. Is page par koi application form nahi hai.",
                        force_screenshot=True,
                    )
                    return
                self._idle_cycles += 1
                if self._idle_cycles > 20:
                    raise AgentRunError("No application form was found on this page. Please check the portal link and try again.")
                await asyncio.sleep(0.7)
                continue

            await self._fill_form(dom)
            # A login form can show both a captcha and a "Send OTP" button.
            # The captcha owns the step: clicking Send OTP before it is solved
            # only produces a toastr and leaves the OTP boxes hidden.
            fresh = await self._scan_dom()
            captcha_pending = await self._handle_captcha(fresh)
            if captcha_pending:
                continue
            fresh = await self._scan_dom()
            otp_handled = await self._handle_otp(fresh)
            if otp_handled:
                # The OTP page has its own checkpoint.  Do not run section
                # approval or advance on an unverified form.
                continue
            fresh = await self._scan_dom()
            await self._handle_errors(fresh)

            fill_state = await self._fill_incomplete_checkpoint()
            if fill_state == "stop":
                return
            if fill_state == "recheck":
                continue

            approved = await self._section_checkpoint()
            if not approved:
                if self.state in {"STOPPED", "FAILED"} or not self.is_running:
                    return
                await asyncio.sleep(0.4)
                continue

            advanced = await self._advance(dom)
            self._record_step(
                "advance",
                status="ok" if advanced else "failed",
                error_code=None if advanced else "navigation_failure",
                output={"url": self.page.url if self.page else self.target_url},
            )
            if not advanced:
                fresh = await self._scan_dom()
                if adapter.is_payment_page(self.page, fresh):
                    await self._trigger_pre_payment_lock()
                    return
                if fresh.get("errors"):
                    await self._handle_errors(fresh)
                    continue
                raise AgentRunError("The portal did not move to the next step. Please review the page and try again.")
            await asyncio.sleep(0.3)

    # ---------------------------------------------------------------- gateways

    async def _dashboard_next_step(
        self,
        dom: Dict[str, Any],
        gateways: List[Dict[str, Any]],
    ) -> bool:
        """Follow a signed-in dashboard's application links instead of stopping.

        A dashboard has no form fields, so the old loop treated it as the end of
        the run.  But a dashboard is a hub: its links open the actual form.  When
        the page offers at least one explicit path, ask (or follow a single
        unambiguous one) and keep the run alive.
        """
        if not gateways:
            return False
        if not decision_policy.is_entry_page(dom, self.form_map):
            return False
        await self._gateway_checkpoint(dom, gateways, kind="next_step")
        return True

    async def _gateway_checkpoint(
        self,
        dom: Dict[str, Any],
        gateways: List[Dict[str, Any]],
        *,
        kind: str = "entry",
    ):
        """Ask for an explicit entry path, never infer one.

        ``decision_policy`` has already reduced the page to distinct targets.
        A single explicit option is followed; two or more options open a gate.
        A response that does not match exactly one option is rejected and the
        gate is shown again.
        """
        next_step = kind == "next_step"
        options = list(self._entry_options or [])
        if not options:
            try:
                options = decision_policy.entry_options(dom, self.form_map)
            except Exception:
                options = []
            self._entry_options = options

        if not options:
            await self._entry_handoff(gateways)
            return

        if len(options) == 1:
            await self._apply_entry_option(options[0])
            return

        signature = "|".join(
            sorted(
                f"{option.get('type')}:{option.get('element_id') or option.get('href') or option.get('text')}"
                for option in options
            )
        )
        if signature == self._last_gateway_signature:
            await asyncio.sleep(0.8)
            return
        self._last_gateway_signature = signature

        await self.emit_event(
            "THINK",
            "This dashboard offers more than one next step."
            if next_step
            else "This portal offers more than one way to start.",
            "Dashboard par aage badhne ke kai raste hain. Aap decide karein."
            if next_step
            else "Portal par do raste hain. Aap decide karein kaise shuru karna hai.",
        )
        gate = (
            decision_policy.build_next_step_gate(options)
            if next_step
            else decision_policy.build_entry_gate(options)
        )
        gate["live_session"] = self.live.public_info() if self.live and not self.live.closed else None
        gate["can_takeover"] = bool(self.live)
        try:
            domain = self._current_domain() or urlparse(str(dom.get("url") or "")).netloc
            store = PortalAccountStore.get_instance()
            gate["domain"] = domain
            gate["account_memory"] = store.domain_summary(domain)
            gate["account_answered"] = bool(
                gate["account_memory"].get("account_exists") != "unknown"
                or gate["account_memory"].get("confirmed")
            )
            gate["login_inspection"] = store.inspect_login_ui(dom).model_dump()
        except Exception:
            traceback.print_exc()

        while self.is_running:
            self.active_gate = gate
            self.state = "WAITING_FOR_USER"
            if self.live:
                self.live.set_allow_control(
                    True,
                    "Choose the next step here or in the live browser, then continue.",
                )
            await self.emit_event(
                "DECIDE",
                "Waiting for you to choose the next step."
                if next_step
                else "Waiting for you to choose how to start.",
                "Agle step ka intezaar hai."
                if next_step
                else "Aapke choice ka intezaar hai.",
                gate,
                force_screenshot=True,
            )
            response = await self._wait_for_user_response()
            self.active_gate = None
            if self.live:
                self._release_live_control("The agent is driving again.")
            if response.get("action") in {"STOPPED", "TIMEOUT"}:
                self.is_running = False
                return
            if response.get("action") == "DISMISS":
                # Dismissing the panel is not a choice.  Keep the decision
                # open instead of silently taking the first path.
                await self.emit_event(
                    "SENSE",
                    "The entry path is still open. Choose one of the listed options.",
                    "Shuru ka rasta abhi chuna nahi gaya. Options mein se ek chunein.",
                )
                continue

            if response.get("action") == "ACCOUNT_STATUS":
                value = str(response.get("account_exists") or "unknown")
                if value not in {"yes", "no", "unknown"}:
                    value = "unknown"
                self._remember_portal_account(
                    account_exists=value, confirmed_by_human=True
                )
                gate["account_memory"] = self._portal_account_summary()
                gate["account_answered"] = True
                await self.emit_event(
                    "SENSE",
                    "Thanks. I'll remember that for this portal.",
                    "Dhanyavaad. Is portal ke liye yaad rakhunga.",
                )
                continue

            selected = decision_policy.match_entry_response(response, options)
            if selected:
                self.state = "RUNNING"
                await self._apply_entry_option(selected)
                return
            await self.emit_event(
                "SENSE",
                "That choice did not match an entry path on this page. Please choose one of the listed options.",
                "Yeh choice is page ke kisi raste se match nahi hui. Options mein se ek chunein.",
            )

    async def _account_conflict_checkpoint(self, dom: Dict[str, Any]) -> bool:
        """Surface a portal "already registered" message instead of filling on.

        Only fires when the human previously said this was their first time on
        the portal.  The page is evidence that the earlier answer may be wrong,
        not proof of who owns the account, so the fact drops back to unknown
        and the human chooses how to continue.
        """
        domain = self._current_domain()
        if not domain:
            return False
        try:
            store = PortalAccountStore.get_instance()
            memory = store.domain_summary(domain)
            if memory.get("account_exists") != "no":
                return False
            conflict = store.detect_registration_conflict(dom)
            if not conflict:
                return False
            signature = f"{domain}|{conflict.get('signal')}|{conflict.get('evidence')}"
            if signature in self._handled_conflicts:
                return False
            self._handled_conflicts.add(signature)
            store.mark_conflict(domain, evidence=str(conflict.get("evidence") or ""))
        except Exception:
            traceback.print_exc()
            return False

        inspection = store.inspect_login_ui(dom)
        gate = build_conflict_gate(
            conflict,
            store.domain_summary(domain),
            domain=domain,
            live_session=self.live.public_info() if self.live and not self.live.closed else None,
            can_takeover=bool(self.live),
        )
        gate["login_inspection"] = inspection.model_dump()
        await self.emit_event(
            "THINK",
            "The portal says this identifier is already registered. Asking you before doing anything.",
            "Portal keh raha hai yeh number pehle se registered hai. Aap se pooch rahe hain.",
        )
        if self.live:
            self.live.set_allow_control(True, "Choose how to handle the existing account.")

        while self.is_running:
            self.active_gate = gate
            self.state = "WAITING_FOR_USER"
            await self.emit_event(
                "DECIDE",
                "The portal reports an existing account. Choose how to continue.",
                "Portal par account pehle se hai. Aage ka rasta aap chunein.",
                gate,
                force_screenshot=True,
            )
            response = await self._wait_for_user_response()
            self.active_gate = None
            if self.live:
                self._release_live_control("The agent is driving again.")
            if response.get("action") in {"STOPPED", "TIMEOUT"}:
                self.is_running = False
                return True
            if response.get("action") == "DISMISS":
                await self.emit_event(
                    "SENSE",
                    "The account conflict is still open. Choose one of the options.",
                    "Account ka sawaal abhi khula hai. Options mein se ek chunein.",
                )
                continue

            choice = str(response.get("choice") or response.get("value") or "").strip().lower()
            if response.get("action") != "ACCOUNT_CONFLICT" or choice not in {
                item["choice"] for item in CONFLICT_CHOICES
            }:
                await self.emit_event(
                    "SENSE",
                    "That choice did not match one of the account options. Please pick one.",
                    "Yeh choice account options se match nahi hui. Ek option chunein.",
                )
                continue

            if choice == "login":
                login_method = next(
                    (item for item in inspection.login_methods if item != "unknown"), "unknown"
                )
                self._remember_portal_account(
                    account_exists="yes",
                    login_method=login_method,
                    last_path_choice="login",
                    confirmed_by_human=True,
                )
                self._requested_entry_mode = "login"
                option = decision_policy.match_entry_response(
                    {"mode": "login"}, list(self._entry_options or [])
                )
                if option:
                    self.state = "RUNNING"
                    await self._apply_entry_option(option)
                    return True
                await self._conflict_handoff(
                    "Use the live browser to open the sign-in page, then continue.",
                    "Live browser mein sign-in page kholein, phir continue karein.",
                    inspection,
                )
                return True

            if choice == "recover":
                self._remember_portal_account(
                    account_exists="yes",
                    last_path_choice="recover",
                    confirmed_by_human=True,
                )
                paths = ", ".join(inspection.recovery_paths) or "the portal's recovery link"
                await self._conflict_handoff(
                    f"Recover the account in the live browser using {paths}, then continue. "
                    "I will not reset anything for you.",
                    "Live browser mein account recover karein, phir continue karein. Main kuch reset nahi karunga.",
                    inspection,
                )
                return True

            if choice == "register":
                self._remember_portal_account(
                    last_path_choice="register_other_identifier",
                    last_known_step="needs_other_identifier",
                    confirmed_by_human=True,
                )
                await self._conflict_handoff(
                    "Enter a different mobile number or email in the live browser, then continue. "
                    "I will not reuse an identifier the portal already rejected.",
                    "Live browser mein doosra number ya email daalein, phir continue karein.",
                    inspection,
                )
                return True

            self.is_running = False
            self.state = "STOPPED"
            await self.emit_event(
                "DECIDE",
                "Stopped at your request. The browser is left where it is.",
                "Aapke kehne par ruk gaya. Browser wahin khula hai.",
            )
            return True
        return True

    async def _conflict_handoff(
        self,
        english: str,
        hindi: str,
        inspection: Any = None,
    ) -> None:
        """Hand the browser to the human after a conflict choice, then rescan."""
        gate = {
            "gate_type": "LIVE_HANDOFF",
            "handoff_type": "account_conflict",
            "title": "This step needs you",
            "hindi_title": "Yeh step aapke liye hai",
            "description": english,
            "live_session": self.live.public_info() if self.live and not self.live.closed else None,
            "can_takeover": bool(self.live),
            "instructions": [
                "Use the live browser. It is the same page the agent is using.",
                "Nothing is submitted or reset for you.",
                "When the page shows what you need, click 'I completed this step'.",
            ],
            "solver_policy": "human_handoff_only",
        }
        if inspection is not None:
            gate["login_inspection"] = inspection.model_dump()
        if self.live:
            self.live.set_allow_control(True, "Finish this step in the live browser.")
        self.active_gate = gate
        self.state = "WAITING_FOR_USER"
        await self.emit_event("DECIDE", english, hindi, gate, force_screenshot=True)
        response = await self._wait_for_user_response()
        self.active_gate = None
        if self.live:
            self._release_live_control("The agent is driving again.")
        if response.get("action") in {"STOPPED", "TIMEOUT"}:
            self.is_running = False
            return
        self.state = "RUNNING" if self.is_running else self.state
        if response.get("action") in {"HANDOFF_COMPLETE", "CONTINUE"}:
            await self._rescan_blueprint()

    async def _apply_entry_option(self, option: Dict[str, Any]) -> None:
        mode = str(option.get("mode") or decision_policy.normalize_mode(option.get("type")) or "")
        if not mode:
            raise AgentRunError(
                "The portal's entry path could not be identified. Please choose it in the live browser."
            )
        self._entry_mode = mode
        self._remember_portal_account(last_path_choice=mode, confirmed_by_human=True)
        if option.get("source") == "current_page":
            await self.emit_event(
                "DECIDE",
                f"Continuing on this {self._entry_label(mode)} page. Nothing is assumed beyond what the page shows.",
                "Is page par aage badh rahe hain. Page jo dikha raha hai, usi ke hisaab se.",
            )
            return
        await self._click_gateway(option)

    async def _entry_handoff(self, gateways: List[Dict[str, Any]]) -> None:
        """Human handoff when the page has entry links we cannot classify."""
        labels = []
        seen = set()
        for gateway in gateways:
            text = str(gateway.get("text") or "").strip()
            if not text or text.lower() in seen:
                continue
            seen.add(text.lower())
            labels.append(text)
        if not labels:
            raise AgentRunError(
                "This page does not show a clear way to register, sign in or resume. "
                "Please open the portal and choose the path yourself."
            )
        if not self.live:
            raise AgentRunError(
                "This page's entry paths could not be identified. Please open the portal and choose the path yourself."
            )
        gate = {
            "gate_type": "LIVE_HANDOFF",
            "handoff_type": "entry_choice",
            "title": "Choose the entry path in the browser",
            "hindi_title": "Browser mein shuru ka rasta chunein",
            "description": (
                "The portal shows entry links that could not be classified safely. "
                "Use the live browser to choose register, sign in or resume yourself, then continue."
            ),
            "options": [{"text": label} for label in labels[:6]],
            "live_session": self.live.public_info() if not self.live.closed else None,
            "can_takeover": True,
            "instructions": [
                "Click the correct link in the live browser.",
                "Wait for the next page to load.",
                "Then click 'I completed this step'.",
            ],
        }
        self.active_gate = gate
        self.state = "WAITING_FOR_USER"
        self.live.set_allow_control(True, "Choose the correct entry path in the live browser.")
        await self.emit_event(
            "DECIDE",
            "Choose the entry path in the live browser, then continue.",
            "Live browser mein sahi rasta chunein, phir continue karein.",
            gate,
            force_screenshot=True,
        )
        response = await self._wait_for_user_response()
        self.active_gate = None
        self._release_live_control("The agent is driving again.")
        if response.get("action") in {"STOPPED", "TIMEOUT"}:
            self.is_running = False
            return
        if response.get("action") not in {"HANDOFF_COMPLETE", "CONTINUE"}:
            await self.emit_event(
                "SENSE",
                "The entry path is still open. Choose it in the live browser, then continue.",
                "Shuru ka rasta abhi chuna nahi gaya. Live browser mein chunein.",
            )
            return
        self._entry_mode = "manual"
        self._last_gateway_signature = ""
        await self.emit_event(
            "ACT",
            "Entry path completed in the live browser. Re-reading the page.",
            "Live browser mein rasta chun liya. Page dobara padh rahe hain.",
        )

    async def _click_gateway(self, gateway: Dict[str, Any]):
        self.state = "RUNNING"
        self._otp_cleared = False
        self._otp_signature = ""
        self._last_advance_signature = ""
        self._captcha_signature = ""
        self._last_error_signature = ""
        await self.emit_event(
            "ACT",
            f"Opening: {gateway.get('text') or 'the application form'}",
            "Chuni hui option khol rahe hain...",
        )
        before = await self._page_snapshot()
        before_url = str(before.get("url") or (self.page.url if self.page else ""))
        if not await self._safe_click(gateway):
            detail = self._last_action_result
            code = f" ({detail.error_code})" if detail and detail.error_code else ""
            raise AgentRunError(
                f"The portal button could not be clicked{code}. Please try again."
            )
        try:
            await self.page.wait_for_load_state("domcontentloaded", timeout=12000)
        except Exception:
            pass
        href = str(gateway.get("href") or "").strip()
        if href:
            try:
                await self.page.wait_for_url(
                    urljoin(before_url, href), timeout=8000, wait_until="domcontentloaded"
                )
            except Exception:
                pass
        if not await self._wait_for_page_change(before, timeout_ms=9000):
            raise AgentRunError(
                "The portal did not open the selected entry path. "
                "Please choose it directly in the live browser and continue."
            )
        # A new page owns its own gateway signature.  If the click did not
        # navigate, the signature stays so the loop cannot double-click it.
        self._last_gateway_signature = ""

    async def _page_snapshot(self) -> Dict[str, Any]:
        """Cheap identity of the current page for real change detection."""
        if not self.page:
            return {}
        try:
            snapshot = await self.page.evaluate(
                r"""() => {
                    const text = (document.body && document.body.innerText
                        ? document.body.innerText : '').replace(/\s+/g, ' ').trim();
                    const active = document.querySelector(
                        '.form-section.active, .section.active, [data-section].active'
                    );
                    const heading = document.querySelector(
                        '.form-section.active h2, .section.active h2, h1, h2'
                    );
                    let digest = 0;
                    for (let i = 0; i < text.length && i < 4000; i += 1) {
                        digest = ((digest << 5) - digest + text.charCodeAt(i)) | 0;
                    }
                    const visible = (el) => {
                        if (!el || el.getClientRects().length === 0) return false;
                        const style = window.getComputedStyle(el);
                        return style.visibility !== 'hidden' && style.display !== 'none';
                    };
                    const form = document.querySelector('form');
                    const fields = Array.from(document.querySelectorAll(
                        'input:not([type="hidden"]), select, textarea, [contenteditable="true"]'
                    )).filter(visible);
                    const fieldSignature = fields.map((el) => [
                        el.tagName.toLowerCase(),
                        el.getAttribute('name') || '',
                        el.id || '',
                        (el.getAttribute('type') || '').toLowerCase(),
                        el.getAttribute('maxlength') || '',
                        el.readOnly ? 'ro' : '',
                        el.disabled ? 'disabled' : '',
                    ].join(':')).join('|');
                    const buttons = Array.from(document.querySelectorAll(
                        'button, input[type="submit"], input[type="button"], a[role="button"]'
                    )).filter(visible);
                    return {
                        url: location.href,
                        title: document.title || '',
                        section: active ? (active.id || '') : '',
                        heading: heading ? (heading.innerText || '').trim().slice(0, 160) : '',
                        inputCount: fields.length,
                        buttonCount: buttons.length,
                        formAction: form ? (form.getAttribute('action') || '') : '',
                        fieldSignature: fieldSignature,
                        textDigest: String(digest),
                    };
                }"""
            )
            return snapshot if isinstance(snapshot, dict) else {}
        except Exception:
            return {"url": getattr(self.page, "url", ""), "title": "", "section": "", "heading": ""}

    async def _wait_for_page_change(
        self,
        before: Dict[str, Any],
        *,
        timeout_ms: int = 9000,
    ) -> bool:
        if not before:
            return False
        # A toast, a validation message or a spinner changing is not a step
        # change.  Require the page identity or its field structure to move.
        # ``textDigest`` is deliberately excluded: HPSC, for example, shows a
        # toastr error when OTP is empty and the old code counted that as a
        # successful "Section 1 saved".
        keys = (
            "url",
            "title",
            "section",
            "heading",
            "inputCount",
            "buttonCount",
            "formAction",
            "fieldSignature",
        )
        deadline = time.monotonic() + max(0.5, timeout_ms / 1000)
        while time.monotonic() < deadline:
            await asyncio.sleep(0.25)
            after = await self._page_snapshot()
            if any(str(before.get(key) or "") != str(after.get(key) or "") for key in keys):
                return True
        return False

    async def _select_login_method(
        self,
        field: Dict[str, Any],
        option: Dict[str, Any],
    ) -> None:
        result = await self._apply_field_value(field, str(option.get("value") or ""))
        if not result.get("success"):
            raise AgentRunError(
                "The login method could not be selected. Please choose it in the live browser and continue."
            )
        await self.page.wait_for_timeout(350)
        self._set_login_method(str(option.get("method") or ""))
        await self.emit_event(
            "ACT",
            f"Sign-in method selected: {option.get('label') or option.get('text')}.",
            "Sign-in ka tarika select ho gaya.",
        )

    async def _login_method_checkpoint(self, dom: Dict[str, Any]) -> bool:
        """Require an explicit choice when a login form offers several methods."""
        selection = decision_policy.login_method_options(dom)
        if not selection:
            return False
        options = selection.get("options") or []
        field = selection.get("field") or {}
        if not options:
            return False
        current_value = str(field.get("value") or "")
        current = next(
            (option for option in options if str(option.get("value") or "") == current_value),
            None,
        )

        requested = self._requested_login_method
        if requested:
            self._requested_login_method = None
            match = decision_policy.match_login_method_response(
                {"method": requested, "value": requested, "text": requested},
                selection,
            )
            if match:
                self._set_login_method(str(match.get("method") or ""))
                if current_value != str(match.get("value") or ""):
                    await self._select_login_method(field, match)
                    return True
                return False
            await self.emit_event(
                "SENSE",
                "That sign-in method is not offered on this form. Please choose one of its options.",
                "Yeh sign-in method is form par nahi hai. Form ke options mein se chunein.",
            )

        if self._login_method:
            match = next(
                (
                    option
                    for option in options
                    if str(option.get("method") or "") == self._login_method
                ),
                None,
            )
            if match:
                if current_value != str(match.get("value") or ""):
                    await self._select_login_method(field, match)
                    return True
                return False
            self._login_method = None

        if len(options) == 1:
            option = options[0]
            self._set_login_method(str(option.get("method") or ""))
            if current_value != str(option.get("value") or ""):
                await self._select_login_method(field, option)
                return True
            return False

        gate = decision_policy.build_login_method_gate(selection)
        gate["live_session"] = self.live.public_info() if self.live and not self.live.closed else None
        gate["can_takeover"] = bool(self.live)
        while self.is_running:
            self.active_gate = gate
            self.state = "WAITING_FOR_USER"
            if self.live:
                self.live.set_allow_control(
                    True,
                    "Choose the sign-in method here or in the live browser, then continue.",
                )
            await self.emit_event(
                "DECIDE",
                "Waiting for you to choose a sign-in method.",
                "Sign-in method ka intezaar hai.",
                gate,
                force_screenshot=True,
            )
            response = await self._wait_for_user_response()
            self.active_gate = None
            if self.live:
                self._release_live_control("The agent is driving again.")
            if response.get("action") in {"STOPPED", "TIMEOUT"}:
                self.is_running = False
                return True
            if response.get("action") == "DISMISS":
                await self.emit_event(
                    "SENSE",
                    "The sign-in method is still open. Choose one of the listed methods.",
                    "Sign-in method abhi chuna nahi gaya. Options mein se chunein.",
                )
                continue
            selected = decision_policy.match_login_method_response(response, selection)
            if selected:
                await self._select_login_method(field, selected)
                return True
            await self.emit_event(
                "SENSE",
                "That choice did not match a sign-in method on this form. Please choose one of the listed methods.",
                "Yeh choice kisi sign-in method se match nahi hui. Options mein se chunein.",
            )
        return True

    async def _login_identifier_checkpoint(self, dom: Dict[str, Any]) -> bool:
        """Require an explicit account identifier when several are visible."""
        selection = decision_policy.identifier_options(dom)
        if not selection:
            return False
        options = selection.get("options") or []
        if not options:
            return False

        if self._login_identifier and not any(
            str(option.get("key") or "") == self._login_identifier for option in options
        ):
            self._login_identifier = None

        requested = self._requested_login_identifier
        if requested:
            self._requested_login_identifier = None
            match = next(
                (option for option in options if str(option.get("key") or "") == requested),
                None,
            )
            if match:
                self._set_login_identifier(requested)
                await self.emit_event(
                    "THINK",
                    f"Using {match.get('label')} to identify this account.",
                    "Is account ko is detail se identify kar rahe hain.",
                )
                return False
            await self.emit_event(
                "SENSE",
                "That account identifier is not offered on this login form. Please choose one of its options.",
                "Yeh identifier is login form par nahi hai. Form ke options mein se chunein.",
            )

        if self._login_identifier:
            return False

        if len(options) == 1:
            self._set_login_identifier(str(options[0].get("key") or ""))
            return False

        gate = decision_policy.build_identifier_gate(selection)
        gate["live_session"] = self.live.public_info() if self.live and not self.live.closed else None
        gate["can_takeover"] = bool(self.live)
        while self.is_running:
            self.active_gate = gate
            self.state = "WAITING_FOR_USER"
            if self.live:
                self.live.set_allow_control(
                    True,
                    "Choose the account identifier here or in the live browser, then continue.",
                )
            await self.emit_event(
                "DECIDE",
                "Waiting for you to choose which detail identifies your account.",
                "Aapka account kis detail se khulta hai, iska intezaar hai.",
                gate,
                force_screenshot=True,
            )
            response = await self._wait_for_user_response()
            self.active_gate = None
            if self.live:
                self._release_live_control("The agent is driving again.")
            if response.get("action") in {"STOPPED", "TIMEOUT"}:
                self.is_running = False
                return True
            if response.get("action") == "DISMISS":
                await self.emit_event(
                    "SENSE",
                    "The account identifier is still open. Choose one of the listed options.",
                    "Account identifier abhi chuna nahi gaya. Options mein se chunein.",
                )
                continue
            selected = decision_policy.match_identifier_response(response, selection)
            if selected:
                self._set_login_identifier(str(selected.get("key") or ""))
                await self.emit_event(
                    "THINK",
                    f"Using {selected.get('label')} to identify this account.",
                    "Is account ko is detail se identify kar rahe hain.",
                )
                return False
            await self.emit_event(
                "SENSE",
                "That choice did not match an account identifier on this form. Please choose one of the listed options.",
                "Yeh choice kisi identifier se match nahi hui. Options mein se chunein.",
            )
        return True

    # ---------------------------------------------------------------- filling

    @staticmethod
    def _digest_field_values(values: List[Dict[str, Any]]) -> str:
        """A value digest for the review snapshot; the values themselves are not stored."""
        pairs = []
        for item in values or []:
            if not isinstance(item, dict):
                continue
            pairs.append(
                {
                    "id": str(item.get("id") or ""),
                    "name": str(item.get("name") or ""),
                    "value": str(item.get("value") or ""),
                    "selected": str(item.get("selectedText") or ""),
                    "checked": bool(item.get("checked")),
                }
            )
        pairs.sort(key=lambda item: (item["id"], item["name"], item["value"], item["selected"]))
        return hashlib.sha256(json.dumps(pairs, sort_keys=True).encode("utf-8")).hexdigest()

    @staticmethod
    def _mask_persisted_value(value: Any) -> Any:
        text = str(value or "")
        if not text or text == "provided by you":
            return value
        if len(text) <= 4:
            return "*" * len(text)
        return f"{'*' * (len(text) - 4)}{text[-4:]}"

    def _persisted_audit(self, audit: Dict[str, Any]) -> Dict[str, Any]:
        """The on-disk audit keeps masked values; the gate keeps the display copy."""
        records = [
            {
                **record,
                "vault_value": self._mask_persisted_value(record.get("vault_value")),
                "form_value": self._mask_persisted_value(record.get("form_value")),
            }
            for record in (audit.get("records") or [])
        ]
        return {
            **audit,
            "records": records,
            "values_masked": True,
            "persisted_records_hash": hashlib.sha256(
                json.dumps(records, sort_keys=True).encode("utf-8")
            ).hexdigest(),
        }

    async def _verify_approval_snapshot(self) -> Optional[Dict[str, Any]]:
        """Re-check the frozen review snapshot after the human returns control."""
        snapshot = self._approval_snapshot
        if not snapshot or not self.page or self.page.is_closed():
            return None
        at_gate = self.state == "AWAITING_PAYMENT" or (
            isinstance(self.active_gate, dict)
            and self.active_gate.get("gate_type") == "PRE_PAYMENT_SAFETY_LOCK"
        )
        if not at_gate:
            return None
        try:
            values = await self.page.evaluate(DOMScanner.EXTRACT_VALUES_JS, True)
        except Exception:
            values = []
        current_url = str(self.page.url or "")
        current_digest = self._digest_field_values(values)
        url_changed = current_url != str(snapshot.get("url") or "")
        fields_changed = current_digest != str(snapshot.get("field_digest") or "")
        if not url_changed and not fields_changed:
            return {
                "valid": not bool(snapshot.get("invalidated")),
                "reason": "already_invalidated" if snapshot.get("invalidated") else None,
                "url": current_url,
            }
        if snapshot.get("invalidated"):
            return {
                "valid": False,
                "reason": "already_invalidated",
                "url": current_url,
            }
        reason = "url_changed" if url_changed else "fields_changed"
        snapshot_url = str(snapshot.get("url") or "")
        self._record_step(
            "submit",
            status="invalidated",
            error_code="wrong_page" if url_changed else "field_not_held",
            output={
                "reason": reason,
                "snapshot_url": snapshot_url,
                "current_url": current_url,
                "snapshot_digest": snapshot.get("field_digest"),
                "current_digest": current_digest,
            },
        )
        if isinstance(self.active_gate, dict):
            self.active_gate["approval_valid"] = False
            self.active_gate["snapshot_changed"] = True
            self.active_gate["snapshot_reason"] = reason
        snapshot["invalidated"] = True
        snapshot["invalidated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        snapshot["url"] = current_url
        snapshot["field_digest"] = current_digest
        await self.emit_event(
            "SENSE",
            "The page changed after you reviewed it. Check the form again before you pay or submit.",
            "Aapke review ke baad page badal gaya. Payment ya final submit se pehle form dobara check karein.",
            force_screenshot=True,
        )
        return {
            "valid": False,
            "reason": reason,
            "url": current_url,
            "snapshot_url": snapshot_url,
        }

    def _public_audit(self) -> List[Dict[str, Any]]:
        public: List[Dict[str, Any]] = []
        seen = set()
        for record in reversed(self.filled_audit):
            key = record.get("field_id") or record.get("field_name") or record.get("vault_key")
            if key in seen:
                continue
            seen.add(key)
            public.append(
                {
                    "field_label": record.get("field_label"),
                    "vault_key": record.get("vault_key"),
                    "injected_value": record.get("injected_value"),
                    "field_id": record.get("field_id"),
                    "field_name": record.get("field_name"),
                    "field_type": record.get("field_type"),
                    "status": record.get("status", "FILLED"),
                    "provenance": record.get("provenance", "profile"),
                    "timestamp": record.get("timestamp"),
                }
            )
        return list(reversed(public))

    def _record_fill(self, item: Dict[str, Any], sem_key: str, value: str, method: str, *, custom: bool = False):
        key = item.get("id") or item.get("name") or sem_key
        if custom or sem_key.startswith(("custom_", "unknown_")):
            display = "provided by you"
        elif sem_key not in {"photo_upload", "signature_upload", "matric_cert_upload"}:
            display = field_registry.mask_value(sem_key, value)
        else:
            display = os.path.basename(str(value))
        record = {
            "field_label": item.get("label") or sem_key,
            "vault_key": sem_key,
            "injected_value": display,
            "actual_value": str(value),
            "field_id": item.get("id") or "",
            "field_name": item.get("name") or "",
            "field_type": item.get("type") or "text",
            "method": method,
            "provenance": "user-entered-now" if custom else "profile",
            "timestamp": datetime.datetime.now().strftime("%H:%M:%S"),
            "status": "FILLED",
            "_key": key,
        }
        for index, existing in enumerate(self.filled_audit):
            if existing.get("_key") == key:
                self.filled_audit[index] = record
                return
        self.filled_audit.append(record)

    async def _apply_field_value(self, item: Dict[str, Any], value: str) -> Dict[str, Any]:
        """Fill one field through the resolver, with the JS injector as fallback.

        The resolver is preferred because it validates the element identity and
        actionability before typing.  Radio groups, checkboxes and exotic
        widgets keep using the injector, which already knows how to select a
        group member by value.
        """
        element_id = str(item.get("element_id") or "")
        tag = str(item.get("tagName") or "input").lower()
        field_type = str(item.get("type") or "text").lower()
        resolver = self._action_resolver()

        if element_id and resolver and field_type not in {"checkbox", "radio", "file", "hidden"}:
            if tag == "select":
                resolved = await resolver.select(element_id, value)
            elif tag in {"input", "textarea"} or str(item.get("role") or "") == "textbox":
                resolved = await resolver.fill(element_id, value)
            else:
                resolved = None

            if resolved and resolved.ok:
                return {"success": True, "method": resolved.method, "value": value}
            if resolved and resolved.error_code in {"NOT_VISIBLE", "DISABLED", "NOT_EDITABLE"}:
                # Do not bypass a disabled or hidden field with a JS setter.
                return {"success": False, "reason": resolved.message}
            # Any other resolver failure falls through to the injector, which
            # uses name/id/index and can handle unusual widgets.
            if resolved and resolved.error_code:
                self._last_action_result = resolved

        try:
            return await self.page.evaluate(DOMScanner.INJECTION_JS, [item, value])
        except Exception:
            return {"success": False, "reason": "The field could not be reached."}

    @staticmethod
    def _is_security_code_field(item: Dict[str, Any]) -> bool:
        """OTP and CAPTCHA inputs have their own human-only checkpoints.

        They must not count as skipped form fields, otherwise every OTP page
        would be reported as an incomplete fill.
        """
        haystack = " ".join(
            str(item.get(key) or "")
            for key in ("label", "name", "id", "placeholder", "aria_label")
        ).lower()
        return bool(
            re.search(
                r"otp|one[-\s]?time\s*(?:password|code)|verification\s*code|"
                r"auth(?:entication)?\s*code|captcha|security\s*check",
                haystack,
            )
        )

    @staticmethod
    def _is_otp_field(item: Dict[str, Any]) -> bool:
        haystack = " ".join(
            str(item.get(key) or "")
            for key in ("label", "name", "id", "placeholder", "aria_label")
        ).lower()
        return bool(
            re.search(
                r"otp|one[-\s]?time\s*(?:password|code)|verification\s*code|"
                r"auth(?:entication)?\s*code",
                haystack,
            )
        )

    @classmethod
    def _is_otp_page(cls, dom: Dict[str, Any]) -> bool:
        """True when the page is a dedicated verification step.

        A full registration form can contain an optional OTP field (the
        practice portal keeps its phone-verification box inside section 1).
        That is not an OTP page: the agent still has to save the section.
        HPSC's post-signup page has only the code boxes and a ``validateotp``
        action, so advancing there would submit the wrong form.
        """
        inputs = [
            item
            for item in (dom.get("inputs") or [])
            if str(item.get("type") or "").lower() not in {"submit", "button", "hidden"}
        ]
        otp_fields = [item for item in inputs if cls._is_otp_field(item)]
        if not otp_fields:
            return False
        action = str(dom.get("formAction") or "").lower()
        if "validateotp" in action:
            return True
        return not [item for item in inputs if not cls._is_otp_field(item)]

    async def _fill_form(self, dom: Dict[str, Any]) -> int:
        """Fill fields, then verify every value against a fresh DOM scan.

        Nothing is recorded in ``filled_audit`` until the portal itself shows
        the expected value.  The UI reads ``fill_summary`` and therefore cannot
        claim a form was filled when the page is empty or the portal rejected a
        value.
        """
        targets: List[Dict[str, Any]] = []
        skipped: List[Dict[str, Any]] = []
        vault = self.vault_mgr.vault
        plan: Dict[str, Any] = {}
        try:
            perception = Perception.from_scan(dom, self.blueprint)
            domain = urlparse(
                str(dom.get("url") or (self.page.url if self.page else ""))
            ).netloc
            plan = build_fill_plan(
                perception,
                FactBook.get_instance(),
                vault=vault,
                domain=domain,
            )
        except Exception:
            # A page that cannot be perceived still fills through the registry
            # fast path; the semantic layer must never block a run.
            traceback.print_exc()
            plan = {}
        login_selection = decision_policy.login_method_options(dom)
        login_field = (login_selection or {}).get("field") or {}
        page_type = str((self.form_map or {}).get("page_type") or "").lower()
        login_page = self._entry_mode == "login" or page_type == "login"
        upload_keys = {"photo_upload", "signature_upload", "matric_cert_upload"}

        for item in dom.get("inputs") or []:
            if not self.is_running:
                break
            if (item.get("type") or "").lower() in {"submit", "button", "reset", "image", "hidden"}:
                continue
            if self._is_security_code_field(item):
                # Handled by _handle_otp / _handle_captcha, never by the fill
                # verifier.
                continue

            label = str(item.get("label") or item.get("name") or item.get("id") or "field")
            if login_field and self._same_field(item, login_field):
                # The method selector has its own explicit checkpoint.
                continue

            if login_page and self._login_identifier:
                identifier = decision_policy.classify_identifier(item)
                if identifier and identifier != self._login_identifier:
                    skipped.append(
                        {
                            "item": item,
                            "sem_key": identifier,
                            "label": label,
                            "reason": "Not the account identifier you chose.",
                        }
                    )
                    continue

            sem_key, _is_verify = DOMScanner.classify_field(item)
            custom_field = False
            if not sem_key:
                if not self._should_ask_unknown(item):
                    skipped.append(
                        {
                            "item": item,
                            "sem_key": "",
                            "label": label,
                            "reason": "No high-confidence match for this label.",
                        }
                    )
                    continue
                value = await self._ask_for_unknown_field(item)
                if not value:
                    skipped.append(
                        {
                            "item": item,
                            "sem_key": "",
                            "label": label,
                            "reason": "You skipped this field.",
                        }
                    )
                    continue
                sem_key = self._custom_key(item)
                custom_field = True
            else:
                if sem_key in upload_keys:
                    self._last_upload_path = ""
                    uploaded = await self._handle_upload(item, sem_key)
                    targets.append(
                        {
                            "item": item,
                            "sem_key": sem_key,
                            "label": label,
                            "value": self._last_upload_path or "attached by you",
                            "method": "file",
                            "custom": False,
                            "kind": "upload",
                            "apply_ok": bool(uploaded),
                            "reason": "" if uploaded else "The file was not attached.",
                        }
                    )
                    continue

                instruction = plan.get(str(item.get("elementId") or ""))
                if instruction is not None and instruction.state == "leave_blank":
                    skipped.append(
                        {
                            "item": item,
                            "sem_key": sem_key,
                            "label": label,
                            "reason": instruction.reason
                            or "You told me there is no value for this field.",
                        }
                    )
                    continue
                if instruction is not None and instruction.state == "fill":
                    # Meaning already decided the value; do not re-derive it
                    # from the framework name.
                    value = instruction.value or ""
                elif instruction is not None and instruction.state in {"ask_human", "confirm"}:
                    value = await self._ask_for_missing_field(
                        item, sem_key, concept=instruction.concept
                    )
                    if not value:
                        skipped.append(
                            {
                                "item": item,
                                "sem_key": sem_key,
                                "label": label,
                                "reason": (
                                    "This needs your confirmation."
                                    if instruction.state == "confirm"
                                    else "No value was available for this field."
                                ),
                            }
                        )
                        continue
                    vault = self.vault_mgr.vault
                else:
                    value = vault.find_field_value(sem_key)
                    if sem_key == "dob" and value:
                        value = vault.get_formatted_dob("DD/MM/YYYY")

                    if not value:
                        value = await self._ask_for_missing_field(item, sem_key)
                        if not value:
                            skipped.append(
                                {
                                    "item": item,
                                    "sem_key": sem_key,
                                    "label": label,
                                    "reason": "No value was available for this field.",
                                }
                            )
                            continue
                        vault = self.vault_mgr.vault

            # Portals commonly lock fields after a step succeeds (for example,
            # HPSC marks the mobile/email/password fields read-only once the
            # first signup step has sent the OTP).  A locked field that already
            # holds the expected value is filled, not a failure.  Re-typing it
            # would either fail or make the portal clear the value.
            if self._field_value_matches(item, str(value)):
                targets.append(
                    {
                        "item": item,
                        "sem_key": sem_key,
                        "label": label,
                        "value": str(value),
                        "method": "already_filled",
                        "custom": custom_field,
                        "kind": "field",
                        "apply_ok": True,
                        "reason": "",
                    }
                )
                continue

            if item.get("readOnly") or item.get("disabled"):
                reason = (
                    f"'{label}' is read-only."
                    if item.get("readOnly")
                    else f"'{label}' is disabled."
                )
                targets.append(
                    {
                        "item": item,
                        "sem_key": sem_key,
                        "label": label,
                        "value": str(value),
                        "method": "input",
                        "custom": custom_field,
                        "kind": "field",
                        "apply_ok": False,
                        "reason": reason,
                    }
                )
                continue

            result = await self._apply_field_value(item, str(value))
            targets.append(
                {
                    "item": item,
                    "sem_key": sem_key,
                    "label": label,
                    "value": str(value),
                    "method": result.get("method", "input"),
                    "custom": custom_field,
                    "kind": "field",
                    "apply_ok": bool(result.get("success")),
                    "reason": str(result.get("reason") or ""),
                }
            )
            await asyncio.sleep(0.08)

        return await self._verify_fill_targets(targets, skipped)

    @staticmethod
    def _same_field(left: Dict[str, Any], right: Dict[str, Any]) -> bool:
        for key in ("element_id", "id", "name"):
            left_value = str(left.get(key) or "")
            right_value = str(right.get(key) or "")
            if left_value and left_value == right_value:
                return True
        return False

    @staticmethod
    def _norm_exact(value: Any) -> str:
        return re.sub(r"\s+", " ", str(value or "")).strip()

    @classmethod
    def _values_match(
        cls,
        item: Dict[str, Any],
        expected: str,
        actual: str,
        raw_value: str,
    ) -> bool:
        """True when the field holds the value, allowing equivalent formats.

        The comparison rules live in ``field_commit`` so verification, the
        "already filled" check and the UI all agree on what "held" means.
        """
        kind = field_commit.kind_for(item)
        if field_commit.committed(
            field_commit.classify_commit(expected, actual, kind=kind)
        ):
            return True
        if raw_value and raw_value != expected:
            return field_commit.committed(
                field_commit.classify_commit(raw_value, actual, kind=kind)
            )
        return False

    @classmethod
    def _field_value_matches(cls, item: Dict[str, Any], expected: str) -> bool:
        """True when the scanned field already holds the value we would enter.

        This is intentionally based on the field's current DOM value, not on
        the presence of a green check or a portal-specific class.  A locked
        field with the right value can be verified without touching it; a
        locked empty field still needs a human.
        """
        field_type = str(item.get("type") or "text").lower()
        if field_type in {"checkbox", "radio"}:
            wanted = str(expected or "").strip().lower() not in {"", "no", "false", "0", "unchecked"}
            return bool(item.get("checked")) == wanted
        actual_values = [
            str(item.get("value") or ""),
            str(item.get("selectedText") or ""),
        ]
        return any(
            cls._values_match(item, expected, actual, expected)
            for actual in actual_values
            if actual
        )

    @staticmethod
    def _find_current_input(
        item: Dict[str, Any],
        dom: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        inputs = [entry for entry in (dom.get("inputs") or []) if isinstance(entry, dict)]
        frame = str(item.get("frame") or "")
        for key in ("id", "name"):
            value = str(item.get(key) or "")
            if not value:
                continue
            matches = [
                entry
                for entry in inputs
                if str(entry.get(key) or "") == value
                and (not frame or not entry.get("frame") or str(entry.get("frame")) == frame)
            ]
            if len(matches) == 1:
                return matches[0]
        try:
            index = int(item.get("index") or 0)
        except (TypeError, ValueError):
            return None
        matches = [
            entry
            for entry in inputs
            if int(entry.get("index") or -1) == index
            and (not frame or not entry.get("frame") or str(entry.get("frame")) == frame)
        ]
        return matches[0] if len(matches) == 1 else None

    @staticmethod
    def _file_attached(item: Dict[str, Any], dom: Dict[str, Any]) -> bool:
        frame = str(item.get("frame") or "")
        for key in ("id", "name"):
            value = str(item.get(key) or "")
            if not value:
                continue
            matches = [
                entry
                for entry in (dom.get("fileInputs") or [])
                if str(entry.get(key) or "") == value
                and (not frame or not entry.get("frame") or str(entry.get("frame")) == frame)
            ]
            if len(matches) == 1:
                return bool(matches[0].get("hasFile"))
        current = FormPilotOrchestrator._find_current_input(item, dom)
        if current:
            return bool(current.get("value") or current.get("fileCount"))
        files = [entry for entry in (dom.get("fileInputs") or []) if entry.get("hasFile")]
        return len(files) == 1

    def _drop_audit_for(self, item: Dict[str, Any], sem_key: str) -> None:
        item_id = str(item.get("id") or "")
        item_name = str(item.get("name") or "")
        kept: List[Dict[str, Any]] = []
        for record in self.filled_audit:
            same = False
            if item_id and str(record.get("field_id") or "") == item_id:
                same = True
            elif item_name and str(record.get("field_name") or "") == item_name:
                same = True
            elif not item_id and not item_name and str(record.get("vault_key") or "") == str(sem_key or ""):
                same = True
            if not same:
                kept.append(record)
        self.filled_audit = kept

    def _evaluate_fill_target(
        self,
        target: Dict[str, Any],
        fresh: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Compare one fill target against a fresh read of the page.

        Returns ``status`` (``VERIFIED``/``FAILED``), a human reason, the
        commit verdict when one applies, and whether a single retry is
        justified.  Uploads and checkboxes are never retried: re-attaching a
        file or toggling a box can undo a value the portal already accepted.
        """
        item = target.get("item") or {}
        if not target.get("apply_ok"):
            return {
                "status": "FAILED",
                "reason": str(target.get("reason") or "The portal did not accept this value."),
                "retryable": False,
            }

        if target.get("kind") == "upload":
            if self._file_attached(item, fresh):
                return {"status": "VERIFIED", "reason": "", "retryable": False}
            return {
                "status": "FAILED",
                "reason": "The portal did not keep the attached file.",
                "retryable": False,
            }

        current = self._find_current_input(item, fresh)
        if current is None:
            return {
                "status": "FAILED",
                "reason": "The field disappeared after it was filled.",
                "retryable": False,
            }

        field_type = str(item.get("type") or "text").lower()
        value = str(target.get("value") or "")
        if field_type in {"checkbox", "radio"}:
            wanted = value.strip().lower() not in {"", "no", "false", "0", "unchecked"}
            matches = bool(current.get("checked")) == wanted
            return {
                "status": "VERIFIED" if matches else "FAILED",
                "reason": "" if matches else "The portal did not keep this choice.",
                "retryable": False,
            }

        kind = field_commit.kind_for(item)
        verdict: Optional[Dict[str, Any]] = None
        actual_values = [
            str(current.get("value") or ""),
            str(current.get("selectedText") or ""),
        ]
        for actual in actual_values:
            candidate = field_commit.classify_commit(value, actual, kind=kind)
            if field_commit.committed(candidate):
                verdict = candidate
                break
            verdict = verdict or candidate

        if verdict is None:
            verdict = field_commit.classify_commit(value, "", kind=kind)

        ok = field_commit.committed(verdict)
        retryable = (
            field_commit.retryable(verdict)
            and kind not in {"select"}
            and str(item.get("tagName") or "").lower() != "select"
        )
        return {
            "status": "VERIFIED" if ok else "FAILED",
            "reason": "" if ok else str(verdict.get("reason") or "The portal did not keep the value that was entered."),
            "retryable": retryable,
            "commit": verdict,
        }

    async def _verify_fill_targets(
        self,
        targets: List[Dict[str, Any]],
        skipped: List[Dict[str, Any]],
    ) -> int:
        self._fill_targets = list(targets)
        self._fill_skipped = list(skipped)
        self.fill_failures = []
        verified = 0
        field_results: List[Dict[str, Any]] = []

        try:
            fresh = await self._scan_dom()
        except Exception:
            fresh = {"inputs": [], "fileInputs": []}

        results = [self._evaluate_fill_target(target, fresh) for target in targets]

        # One bounded retry, only for values the portal dropped or replaced.
        # This mirrors Skyvern's read-back rule: a silent rejection gets one
        # atomic re-entry, not a loop.
        retry_indexes = [index for index, result in enumerate(results) if result.get("retryable")]
        if retry_indexes and self.page:
            for index in retry_indexes:
                target = targets[index]
                try:
                    await self._apply_field_value(
                        target.get("item") or {}, str(target.get("value") or "")
                    )
                except Exception:
                    traceback.print_exc()
            await asyncio.sleep(0.15)
            try:
                second_read = await self._scan_dom()
            except Exception:
                second_read = None
            if second_read is not None:
                for index in retry_indexes:
                    results[index] = self._evaluate_fill_target(targets[index], second_read)
                    results[index]["retried"] = True
                await self.emit_event(
                    "ACT",
                    f"Re-entered {len(retry_indexes)} field(s) the portal had dropped, then read them back.",
                    f"Portal ne {len(retry_indexes)} field drop kar diye the; dobara bhar kar check kiya.",
                )

        for target, result in zip(targets, results):
            item = target.get("item") or {}
            sem_key = str(target.get("sem_key") or "")
            label = str(target.get("label") or sem_key or "field")
            if result.get("status") == "VERIFIED":
                verified += 1
                method = "file" if target.get("kind") == "upload" else str(target.get("method") or "input")
                self._record_fill(
                    item,
                    sem_key,
                    str(target.get("value") or ""),
                    method,
                    custom=bool(target.get("custom")),
                )
                entry = {"field_label": label, "vault_key": sem_key, "status": "VERIFIED"}
                if result.get("commit"):
                    entry["commit"] = result["commit"]["match"]
                field_results.append(entry)
                continue

            self._drop_audit_for(item, sem_key)
            failure = {
                "field_label": label,
                "vault_key": sem_key,
                "status": "FAILED",
                "reason": str(result.get("reason") or "The portal did not keep the value that was entered."),
            }
            if result.get("commit"):
                failure["commit"] = result["commit"]
            if result.get("retried"):
                failure["retried"] = True
            self.fill_failures.append(failure)
            entry = {"field_label": label, "vault_key": sem_key, "status": "FAILED"}
            if result.get("commit"):
                entry["commit"] = result["commit"]["match"]
            field_results.append(entry)

        for skip in skipped:
            item = skip.get("item") or {}
            sem_key = str(skip.get("sem_key") or "")
            label = str(skip.get("label") or sem_key or "field")
            self._drop_audit_for(item, sem_key)
            self.fill_failures.append(
                {
                    "field_label": label,
                    "vault_key": sem_key,
                    "status": "SKIPPED",
                    "reason": str(skip.get("reason") or "This field was skipped."),
                }
            )
            field_results.append(
                {"field_label": label, "vault_key": sem_key, "status": "SKIPPED"}
            )

        attempted = len(targets)
        skipped_count = len(skipped)
        failed_count = sum(1 for failure in self.fill_failures if failure.get("status") == "FAILED")
        reformatted_count = sum(
            1 for entry in field_results if entry.get("commit") == "reformatted"
        )
        if attempted == 0 and skipped_count == 0:
            status = "NO_FIELDS"
        elif verified == 0:
            status = "FAILED"
        elif failed_count == 0 and skipped_count == 0 and verified == attempted:
            status = "FILLED"
        else:
            status = "PARTIAL"

        self.fill_summary = {
            "status": status,
            "page_url": self.page.url if self.page else self.target_url,
            "section": self.current_section,
            "attempted": attempted,
            "verified": verified,
            "failed": failed_count,
            "skipped": skipped_count,
            "reformatted": reformatted_count,
            "retried": len(retry_indexes),
            "fields": field_results,
            "verified_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        self._record_step(
            "fill",
            status="ok" if status in {"FILLED", "NO_FIELDS"} else "partial" if status == "PARTIAL" else "failed",
            output={
                "status": status,
                "attempted": attempted,
                "verified": verified,
                "failed": failed_count,
                "skipped": skipped_count,
                "reformatted": reformatted_count,
                "retried": len(retry_indexes),
                "section": self.current_section,
            },
        )
        if verified:
            await self.emit_event(
                "ACT",
                f"Verified {verified} of {attempted} filled field(s) on this page.",
                f"Is page par {attempted} mein se {verified} field verify ho gaye.",
            )
        if self.fill_failures:
            all_labels = [
                str(failure.get("field_label") or "field")
                for failure in self.fill_failures
            ]
            shown = all_labels[:4]
            remaining = len(all_labels) - len(shown)
            labels = ", ".join(shown)
            if remaining:
                labels += f" and {remaining} more"
            await self.emit_event(
                "SENSE",
                f"{len(self.fill_failures)} field(s) need attention: {labels}.",
                f"{len(self.fill_failures)} field par dhyan dein: {labels}.",
            )
        if status == "NO_FIELDS":
            await self.emit_event(
                "SENSE",
                "No fillable fields were found on this page.",
                "Is page par bharne ke liye koi field nahi mila.",
            )
        return verified

    @staticmethod
    def _should_ask_unknown(item: Dict[str, Any]) -> bool:
        field_type = str(item.get("type") or "text").lower()
        if field_type in {"file", "checkbox", "radio", "hidden", "submit", "button", "reset", "image", "search"}:
            return False
        label = str(item.get("label") or "").strip()
        if len(label) < 2:
            return False
        if re.search(r"\b(?:search|filter|find|newsletter|subscribe|coupon|promo)\b", label, re.IGNORECASE):
            return False
        # CAPTCHA and OTP fields have their own checkpoints.  Asking for a
        # reusable "custom field" value here would be wrong and would leak a
        # one-time secret into the profile.
        haystack = " ".join(
            str(item.get(key) or "") for key in ("label", "name", "id", "placeholder")
        )
        if re.search(
            r"captcha|security\s*(?:check|code)|otp|one[-\s]?time|verification\s*code|auth(?:entication)?\s*code",
            haystack,
            re.IGNORECASE,
        ):
            return False
        return True

    @staticmethod
    def _custom_key(item: Dict[str, Any]) -> str:
        label = str(item.get("label") or item.get("name") or item.get("id") or "field")
        slug = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")[:48] or "field"
        return f"custom_{slug}"

    async def _ask_for_unknown_field(self, item: Dict[str, Any]) -> str:
        label = str(item.get("label") or item.get("name") or "this field")
        custom_key = self._custom_key(item)
        if custom_key in self._session_values:
            return self._session_values[custom_key]

        await self.emit_event(
            "THINK",
            f"The form asks for something new: {label}",
            f"Form mein ek nayi detail chahiye: {label}",
        )
        options = [
            {"text": str(option.get("text") or ""), "value": str(option.get("value") or "")}
            for option in (item.get("options") or [])[:60]
        ]
        gate = {
            "gate_type": "UNKNOWN_FIELD",
            "title": "The form asks for something new",
            "hindi_title": "Form mein nayi detail chahiye",
            "field_key": custom_key,
            "field_label": label,
            "input_type": item.get("type") or "text",
            "options": options,
            "required": bool(item.get("required")),
            "description": (
                "This label does not match a known field with enough confidence. "
                "FormPilot will not guess. Enter the value yourself, or skip if the form allows it."
            ),
            "why": "No high-confidence match in the field registry.",
            "can_skip": not bool(item.get("required")),
            "live_session": self.live.public_info() if self.live and not self.live.closed else None,
        }
        self.active_gate = gate
        self.state = "WAITING_FOR_USER"
        if self.live:
            self.live.set_allow_control(True, "Fill this new field in the live browser, or answer here.")
        await self.emit_event(
            "DECIDE",
            f"Waiting for: {label}",
            "Aapke input ka intezaar hai.",
            gate,
            force_screenshot=True,
        )
        response = await self._wait_for_user_response()
        self.active_gate = None
        if self.live:
            self._release_live_control("The agent is driving again.")
        self.state = "RUNNING" if self.is_running else self.state

        action = str(response.get("action") or "")
        if action in {"STOPPED", "TIMEOUT", "DISMISS", "SKIP"}:
            if action == "TIMEOUT":
                self.is_running = False
            return ""
        value = str(response.get("value") or response.get("text") or "").strip()
        if not value:
            return ""
        self._session_values[custom_key] = value
        try:
            self.vault_mgr.add_custom_field(custom_key, value)
        except Exception:
            pass
        await self.emit_event(
            "THINK",
            f"Saved '{label}' as a custom profile field for this account.",
            f"'{label}' ko custom profile field ke roop mein save kar diya.",
        )
        return value

    async def _ask_for_missing_field(
        self,
        item: Dict[str, Any],
        sem_key: str,
        *,
        concept: Optional[str] = None,
    ) -> str:
        label = item.get("label") or sem_key
        await self.emit_event(
            "THINK",
            f"One more detail is needed: {label}",
            f"Ek detail aur chahiye: {label}",
        )
        gate = {
            "gate_type": "MISSING_FIELD",
            "title": "One more detail is needed",
            "hindi_title": "Ek detail aur chahiye",
            "field_key": sem_key,
            "field_label": label,
            "input_type": item.get("type") or "text",
            "required": bool(item.get("required")),
            "can_skip": not bool(item.get("required")),
            "live_session": self.live.public_info() if self.live and not self.live.closed else None,
            "can_takeover": bool(self.live),
            "description": f"This portal asks for {label}. Add it once and FormPilot will reuse it in future applications.",
        }
        self.active_gate = gate
        self.state = "WAITING_FOR_USER"
        if self.live:
            self.live.set_allow_control(True, "Enter this detail in the live browser, or answer here.")
        await self.emit_event(
            "DECIDE",
            f"Waiting for: {label}",
            "Aapke input ka intezaar hai.",
            gate,
            force_screenshot=True,
        )
        response = await self._wait_for_user_response()
        self.active_gate = None
        if self.live:
            self._release_live_control("The agent is driving again.")
        self.state = "RUNNING" if self.is_running else self.state
        if response.get("action") in {"STOPPED", "TIMEOUT", "DISMISS", "SKIP"}:
            if response.get("action") == "TIMEOUT":
                self.is_running = False
            return ""
        if response.get("action") == "HANDOFF_COMPLETE":
            return ""
        value = str(response.get("value") or response.get("text") or "").strip()
        if value:
            stored_as_fact = False
            if concept:
                try:
                    FactBook.get_instance().set_fact(
                        concept,
                        value=value,
                        provenance="explicit_user",
                        verification="confirmed_by_human",
                        scope={"kind": "global"},
                    )
                    stored_as_fact = True
                except Exception:
                    traceback.print_exc()
            if not stored_as_fact:
                try:
                    self.vault_mgr.set_semantic_field(sem_key, value)
                except Exception:
                    self.vault_mgr.add_custom_field(sem_key, value)
        return value

    async def _handle_upload(self, item: Dict[str, Any], sem_key: str) -> bool:
        live_photo = bool(
            sem_key == "photo_upload"
            and (
                (self.form_map or {}).get("live_photo_required")
                or str(item.get("capture") or "").strip()
                or "live" in f"{item.get('label') or ''} {item.get('name') or ''}".lower()
            )
        )

        vault = self.vault_mgr.vault
        if sem_key == "photo_upload":
            path_value = vault.photo_path
            fallback = settings.UPLOADS_DIR / "candidate_photo.jpg"
        elif sem_key == "signature_upload":
            path_value = vault.signature_path
            fallback = settings.UPLOADS_DIR / "candidate_signature.jpg"
        else:
            path_value = vault.matric_cert_path
            fallback = None

        candidate = Path(path_value) if path_value else None
        if candidate and not candidate.is_absolute():
            candidate = settings.ROOT_DIR / candidate
        if (not candidate or not candidate.exists()) and settings.DEMO_MODE and getattr(self._adapter, "name", "") == "simulator":
            try:
                BiometricCompressor.generate_sample_assets()
            except Exception:
                pass
            candidate = fallback

        if live_photo or not candidate or not candidate.exists():
            if live_photo:
                return await self._upload_handoff(item, sem_key, live_photo=True)
            return await self._upload_handoff(item, sem_key, live_photo=False)

        try:
            locator = self.page.locator(f"#{item.get('id')}") if item.get("id") else self.page.locator(f"[name='{item.get('name')}']")
            if await locator.count() == 0:
                locator = self.page.locator("input[type='file']").first
            await locator.set_input_files(str(candidate), timeout=10000)
        except Exception:
            await self.emit_event(
                "SENSE",
                f"Could not upload {item.get('label') or sem_key}. Please attach it in the live browser.",
                f"{item.get('label') or sem_key} upload nahi ho paya. Live browser mein attach karein.",
            )
            return await self._upload_handoff(item, sem_key, live_photo=live_photo)

        self._last_upload_path = str(candidate)
        await self.emit_event(
            "ACT",
            f"Uploaded: {item.get('label') or sem_key}. Verifying the attachment.",
            f"{item.get('label') or sem_key} upload ho gaya. Attachment verify kar rahe hain.",
        )
        return True

    async def _upload_handoff(self, item: Dict[str, Any], sem_key: str, *, live_photo: bool) -> bool:
        label = str(item.get("label") or sem_key)
        gate_type = "LIVE_PHOTO" if live_photo else "FILE_UPLOAD"
        await self.emit_event(
            "SENSE",
            f"Please provide a file for: {label}",
            f"{label} ke liye file chahiye.",
        )
        gate = {
            "gate_type": gate_type,
            "handoff_type": "live_photo" if live_photo else "file_upload",
            "title": "Your camera or file is needed",
            "hindi_title": "Aapka photo ya file chahiye",
            "field_key": sem_key,
            "field_label": label,
            "accept": str(item.get("accept") or "image/*"),
            "max_size_mb": 5,
            "live_photo_required": live_photo,
            "live_session": self.live.public_info() if self.live and not self.live.closed else None,
            "description": (
                "This portal asks for a live photo. Capture it with your own camera or choose a recent photo. "
                "FormPilot never uses a stock image or another person's photo."
                if live_photo
                else f"This portal needs a file for {label}. Choose a file from your device."
            ),
            "instructions": (
                [
                    "Use your own front camera or a recent photo of yourself.",
                    "If the portal insists on its own live webcam step, do that step directly on the portal.",
                    "FormPilot attaches the file to this browser session only.",
                ]
                if live_photo
                else [
                    "Choose the exact document the portal asks for.",
                    "Check the format and size before uploading.",
                    "The file is attached to this browser session only.",
                ]
            ),
            "privacy_note": "The file is attached to the live portal and is not added to your saved profile.",
        }
        self.active_gate = gate
        self.state = "WAITING_FOR_USER"
        if self.live:
            self.live.set_allow_control(True, "Attach the requested file in the live browser.")
        await self.emit_event(
            "DECIDE",
            f"Waiting for: {label}",
            f"{label} ka intezaar hai.",
            gate,
            force_screenshot=True,
        )
        response = await self._wait_for_user_response()
        self.active_gate = None
        if self.live:
            self._release_live_control("The agent is driving again.")
        self.state = "RUNNING" if self.is_running else self.state

        action = response.get("action")
        if action in {"STOPPED", "TIMEOUT", "DISMISS"}:
            if action == "TIMEOUT":
                self.is_running = False
            return False
        if action not in {"UPLOAD_COMPLETE", "HANDOFF_COMPLETE", "CONTINUE"}:
            return False

        # The endpoint may have attached the file already.  Verify it, but
        # never pretend the upload worked if the input is still empty.
        try:
            dom = await self._scan_dom()
            file_inputs = [entry for entry in (dom.get("inputs") or []) if str(entry.get("type") or "").lower() == "file"]
            attached = any(bool(entry.get("value")) for entry in file_inputs)
            if not attached:
                attached = any(bool(entry.get("hasFile")) for entry in (dom.get("fileInputs") or []))
        except Exception:
            attached = False
        if attached:
            await self.emit_event(
                "ACT",
                f"File attached for {label}.",
                f"{label} ke liye file attach ho gayi.",
            )
            return True

        await self.emit_event(
            "SENSE",
            f"No file is attached for {label} yet. Attach it in the live browser, then continue.",
            f"{label} ke liye abhi file attach nahi hui. Live browser mein attach karein.",
        )
        return False


    # ---------------------------------------------------------------- security checks

    @staticmethod
    def _otp_signature_for(dom: Dict[str, Any]) -> str:
        fields = dom.get("otpInputs") or []
        names = "|".join(
            str(field.get("name") or field.get("id") or field.get("element_id") or "")
            for field in fields
        )
        return f"{dom.get('url') or ''}|{dom.get('formAction') or ''}|{names}"

    async def _enter_otp_code(self, dom: Dict[str, Any], otp: str) -> Dict[str, Any]:
        """Enter one code into a single input or a row of split OTP boxes.

        HPSC uses six one-character inputs with the same name.  Filling only
        the first input with the whole code leaves five boxes empty, so the
        portal never verifies anything.  A page with more than one distinct
        OTP group is handed back to the human instead of guessing which code
        belongs where.
        """
        items = [
            item
            for item in (dom.get("inputs") or [])
            if self._is_otp_field(item)
        ]
        if not items:
            return {"success": False, "reason": "The verification-code fields disappeared."}

        groups: Dict[str, List[Dict[str, Any]]] = {}
        for item in items:
            key = str(item.get("name") or item.get("id") or item.get("element_id") or "")
            groups.setdefault(key, []).append(item)
        if len(groups) > 1:
            return {
                "success": False,
                "reason": (
                    "This page has more than one verification-code group. "
                    "Enter the codes directly in the live browser."
                ),
            }

        if len(items) == 1:
            characters = [otp]
        else:
            if len(otp) != len(items):
                return {
                    "success": False,
                    "reason": f"The page expects {len(items)} digits, but the code has {len(otp)}.",
                }
            characters = list(otp)

        for item, character in zip(items, characters):
            selector = str(item.get("css") or "")
            if not selector and item.get("id"):
                selector = f"#{item['id']}"
            if not selector:
                return {"success": False, "reason": "A verification-code box could not be located."}
            try:
                box = self.page.locator(selector).first
                if await box.count() == 0:
                    return {
                        "success": False,
                        "reason": "A verification-code box disappeared before it could be filled.",
                    }
                await box.fill(character, timeout=5000)
                # HPSC's auto-advance listens for keyup; dispatching it keeps
                # the visible focus and the serialized form in sync.
                try:
                    await box.dispatch_event("keyup", {"key": character})
                except Exception:
                    pass
            except Exception as exc:
                return {"success": False, "reason": f"A verification-code box could not be filled: {exc}"}
        return {"success": True}

    async def _submit_otp_form(self, dom: Dict[str, Any]) -> Dict[str, Any]:
        """Submit only the OTP form, never a generic final-submit button."""
        if not self.page:
            return {"success": False, "reason": "The browser page is no longer available."}
        try:
            action = str(
                await self.page.evaluate(
                    "() => { const f = document.querySelector('form'); "
                    "return f ? (f.getAttribute('action') || '') : ''; }"
                )
                or ""
            )
        except Exception:
            action = str(dom.get("formAction") or "")
        lower_action = action.lower()

        button = None
        for selector in (
            "#btn-verify-otp",
            "#verify_otp_btn",
            "#signup_submit",
            "button[type='submit']",
            "input[type='submit']",
        ):
            try:
                candidate = self.page.locator(selector).first
                if await candidate.count() > 0 and await candidate.is_visible():
                    button = candidate
                    break
            except Exception:
                continue
        if button is None:
            names = ["Verify OTP", "Verify", "Confirm OTP", "Submit OTP"]
            if "validateotp" in lower_action:
                names.append("Create Account")
            for name in names:
                try:
                    candidate = self.page.get_by_role(
                        "button", name=re.compile(rf"^{re.escape(name)}$", re.IGNORECASE)
                    ).first
                    if await candidate.count() > 0 and await candidate.is_visible():
                        button = candidate
                        break
                except Exception:
                    continue
        if button is None:
            return {
                "success": False,
                "reason": "The page does not expose a button that submits the verification code.",
            }

        if "validateotp" not in lower_action:
            try:
                text = (await button.inner_text()).strip().lower()
            except Exception:
                text = ""
            if not re.search(r"verify|confirm|otp|validate", text):
                return {
                    "success": False,
                    "reason": "The only available button is not a verification button.",
                }

        before = await self._page_snapshot()
        try:
            await button.click(timeout=8000)
        except Exception as exc:
            return {"success": False, "reason": f"The verification form could not be submitted: {exc}"}

        changed = await self._wait_for_page_change(before, timeout_ms=15000)
        try:
            fresh = await self._scan_dom()
        except Exception:
            fresh = {}
        if not changed:
            # Some portals verify the code over AJAX and leave the page
            # structure alone, showing a persistent "verification complete"
            # state instead.  Accept that explicit success signal; a transient
            # toastr alone is still not enough.
            if await self._otp_verification_complete():
                return {"success": True}
            visible = str(fresh.get("visibleText") or "").lower()
            errors = [str(item) for item in (fresh.get("errors") or []) if str(item).strip()]
            reason = errors[0] if errors else ""
            for phrase in (
                "please enter mobile otp",
                "please enter email otp",
                "invalid otp",
                "incorrect otp",
                "wrong otp",
                "otp expired",
            ):
                if phrase in visible:
                    reason = phrase.capitalize() + "."
                    break
            return {
                "success": False,
                "reason": reason or "The portal did not confirm the verification code.",
            }

        if not (fresh.get("otpInputs") or []):
            return {"success": True}
        url = str(fresh.get("url") or "").lower()
        visible = str(fresh.get("visibleText") or "").lower()
        if "login" in url and "signup" not in url:
            return {"success": True}
        if self._otp_success_text(visible):
            return {"success": True}
        errors = [str(item) for item in (fresh.get("errors") or []) if str(item).strip()]
        return {
            "success": False,
            "reason": errors[0] if errors else "The portal did not confirm the verification code.",
        }

    @staticmethod
    def _otp_success_text(visible: str) -> bool:
        text = str(visible or "").lower()
        return any(
            token in text
            for token in (
                "account created",
                "registration successful",
                "verification successful",
                "verification complete",
                "otp verified",
                "phone verified",
                "mobile verified",
                "email verified",
                "login to continue",
            )
        )

    async def _otp_verification_complete(self) -> bool:
        try:
            fresh = await self._scan_dom()
        except Exception:
            return False
        if not (fresh.get("otpInputs") or []):
            return True
        url = str(fresh.get("url") or "").lower()
        if "login" in url and "signup" not in url:
            return True
        return self._otp_success_text(str(fresh.get("visibleText") or ""))

    async def _handle_otp(self, dom: Optional[Dict[str, Any]] = None) -> bool:
        """Relay a human-supplied OTP and verify that the portal accepted it.

        Returns True when the OTP checkpoint was handled (success, retry or
        stop), so the main loop rescans instead of continuing to the section
        approval and advance steps on an unverified page.
        """
        if not self.page:
            return False
        dom = dom or {}
        otp_inputs = dom.get("otpInputs") or []
        signature = self._otp_signature_for(dom)
        if self._otp_cleared:
            if signature == self._otp_signature:
                return False
            # A new OTP page (for example the login page after registration)
            # owns a new checkpoint.
            self._otp_cleared = False
            self._otp_signature = ""

        selector = "#btn-send-otp, button:has-text('Send OTP'), button:has-text('Get OTP'), button:has-text('Send code')"
        button = None
        try:
            candidate = self.page.locator(selector).first
            if await candidate.count() > 0 and await candidate.is_visible():
                button = candidate
        except Exception:
            button = None
        if button is None and not otp_inputs:
            return False

        await self.emit_event(
            "THINK",
            "The portal needs to verify your phone number.",
            "Portal phone number verify karna chahta hai.",
        )
        if button is not None and not otp_inputs:
            try:
                await button.click(timeout=8000)
            except Exception:
                pass
            await self.page.wait_for_timeout(900)
            try:
                dom = await self._scan_dom()
                otp_inputs = dom.get("otpInputs") or []
                signature = self._otp_signature_for(dom)
            except Exception:
                pass
            if not otp_inputs:
                # The send button did not reveal a code field (usually because
                # a captcha is still empty or the portal rejected the request).
                # Opening an OTP gate here would ask for a code that cannot be
                # entered anywhere, so leave the page to the captcha/error
                # checkpoints instead.
                await self.emit_event(
                    "SENSE",
                    "The portal did not show a verification-code field. Check the page and try again.",
                    "Portal ne verification code ka field nahi dikhaya. Page check karke dobara koshish karein.",
                )
                return False

        config = self.tinyfish_mgr.config
        base_description = (
            "Enter the code sent to the phone number saved in your details. "
            "FormPilot never stores this code."
        )
        gate = {
            "gate_type": "OTP_RELAY",
            "title": "Enter the verification code",
            "hindi_title": "Verification code enter karein",
            "hindi_audio_text": "Aapke phone par code bheja gaya hai. Woh code yahan enter karein.",
            "description": base_description,
            "recipient": self._masked_phone(self.vault_mgr.vault.mobile),
            "ntfy_topic": config.ntfy_topic,
            "ntfy_url": f"https://ntfy.sh/{config.ntfy_topic}",
            "live_session": self.live.public_info() if self.live and not self.live.closed else None,
            "can_takeover": bool(self.live),
            "instructions": [
                "You can type the code below, or enter it directly in the live portal.",
                "The code is used once and is never stored.",
            ],
        }
        # The practice portal exposes a fixed code; a real portal sends a real
        # code to the human's phone.  Never advertise the demo code on a live
        # portal, where it would only mislead the candidate.
        adapter_name = getattr(self._adapter, "name", "")
        portal_url = str(getattr(self.page, "url", "") or "")
        is_simulator = adapter_name == "simulator" or "gov-portal-demo" in portal_url
        if settings.DEMO_MODE and is_simulator:
            gate["demo_otp"] = settings.DEMO_OTP
            gate["description"] += f" Demo mode code: {settings.DEMO_OTP}."

        while self.is_running:
            self.active_gate = gate
            self.state = "WAITING_FOR_USER"
            if self.live:
                self.live.set_allow_control(True, "Enter the verification code in the live browser.")
            await self.emit_event(
                "DECIDE",
                "Waiting for the verification code.",
                "Verification code ka intezaar hai.",
                gate,
                force_screenshot=True,
            )
            response = await self._wait_for_user_response()
            self.active_gate = None
            if self.live:
                self._release_live_control("The agent is driving again.")
            self.state = "RUNNING" if self.is_running else self.state
            action = str(response.get("action") or "")
            if action in {"STOPPED", "TIMEOUT"}:
                self.is_running = False
                if action == "TIMEOUT":
                    self.last_error = "No response was received. The application was paused."
                return True
            if action == "DISMISS":
                await self.emit_event(
                    "SENSE",
                    "The verification code is still needed. Enter it below or in the live browser.",
                    "Verification code abhi bhi chahiye. Neeche ya live browser mein enter karein.",
                )
                continue
            if action == "HANDOFF_COMPLETE":
                if await self._otp_verification_complete():
                    self._otp_cleared = True
                    self._otp_signature = signature
                    await self.emit_event(
                        "ACT",
                        "Verification completed in the live browser.",
                        "Live browser mein verification pura ho gaya.",
                    )
                    return True
                await self.emit_event(
                    "SENSE",
                    "The code is entered but the portal has not verified it yet. Submit it in the live browser, then continue.",
                    "Code enter hai lekin portal ne verify nahi kiya. Live browser mein submit karein, phir continue karein.",
                )
                continue

            otp = re.sub(r"\D", "", str(response.get("otp") or response.get("code") or ""))
            if not otp:
                await self.emit_event(
                    "SENSE",
                    "Enter the verification code to continue.",
                    "Aage badhne ke liye verification code enter karein.",
                )
                continue

            entered = await self._enter_otp_code(dom, otp)
            if not entered.get("success"):
                await self.emit_event(
                    "SENSE",
                    str(entered.get("reason") or "The verification code could not be entered."),
                    "Verification code enter nahi ho paya. Dobara koshish karein.",
                )
                continue

            submitted = await self._submit_otp_form(dom)
            if submitted.get("success"):
                self._otp_cleared = True
                self._otp_signature = signature
                await self.emit_event(
                    "ACT",
                    "Verification code accepted.",
                    "Verification code accept ho gaya.",
                )
                return True

            reason = str(submitted.get("reason") or "The portal did not accept the code.")
            gate["description"] = f"{base_description} Last attempt: {reason}"
            await self.emit_event(
                "SENSE",
                f"The verification code was not accepted: {reason}",
                "Verification code accept nahi hua. Dobara check karke enter karein.",
            )
            try:
                dom = await self._scan_dom()
                signature = self._otp_signature_for(dom)
            except Exception:
                pass
        return True

    @staticmethod
    def _captcha_signature_for(dom: Dict[str, Any]) -> str:
        captchas = dom.get("captchaElements") or []
        kinds = sorted({str(captcha.get("kind") or "unknown") for captcha in captchas})
        return f"{dom.get('url')}|{'|'.join(kinds)}|" + "|".join(
            str(captcha.get("id") or captcha.get("tagName") or "") for captcha in captchas[:3]
        )

    @staticmethod
    def _captcha_input_target(captchas: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """The field where the human's answer is typed."""
        for item in captchas:
            if str(item.get("tagName") or "").lower() in {"input", "textarea"}:
                return item
        return captchas[0] if captchas else None

    @staticmethod
    def _captcha_preview_target(captchas: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """The challenge image, never the empty answer field."""
        for item in captchas:
            if str(item.get("tagName") or "").lower() in {"img", "canvas", "iframe"}:
                return item
        return None

    async def _handle_captcha(self, dom: Dict[str, Any]) -> bool:
        """Handle a security check; return True while it is still pending.

        ``True`` means the main loop must not click "Send OTP", approve a
        section or advance: the human has not cleared the challenge yet.
        """
        captchas = dom.get("captchaElements") or []
        if not captchas or not self.page:
            return False

        signature = self._captcha_signature_for(dom)
        if signature == self._captcha_signature:
            return False

        interactive = next(
            (
                captcha
                for captcha in captchas
                if str(captcha.get("kind") or "") in {"interactive", "slider", "drag", "unknown"}
                and str(captcha.get("tagName") or "").lower() in {"iframe", "div", "canvas", "img", "input"}
            ),
            None,
        )
        if interactive and self.live:
            await self._captcha_live_handoff(captchas, interactive, signature)
            return signature != self._captcha_signature

        # Text CAPTCHA (for example "hJ8ik)3") can be entered in the gate.
        # The scanner reports both the answer field and the challenge image as
        # "text"; the gate must preview the image and fill the input.
        captcha = self._captcha_input_target(captchas)
        preview = self._captcha_preview_target(captchas) or captcha
        image_b64 = ""
        if preview:
            selector = (
                f"#{preview.get('id')}"
                if preview.get("id")
                else str(preview.get("tagName") or "canvas")
            )
            try:
                element = self.page.locator(selector).first
                if await element.count() > 0:
                    image = await element.screenshot()
                    image_b64 = f"data:image/png;base64,{base64.b64encode(image).decode('utf-8')}"
            except Exception:
                pass

        await self.emit_event(
            "THINK",
            "The portal is asking for a security check.",
            "Portal ek security check maang raha hai.",
        )
        gate = {
            "gate_type": "CAPTCHA_SOLVE",
            "title": "Enter the security check",
            "hindi_title": "Security check enter karein",
            "captcha_image": image_b64,
            "captcha_kind": str(captcha.get("kind") or "text"),
            "description": "Enter the characters shown in the image. This check is never solved automatically.",
            "live_session": self.live.public_info() if self.live and not self.live.closed else None,
            "instructions": [
                "Read the characters in the live portal or in the image.",
                "Type them in the box below.",
                "FormPilot submits the text; a human still solves the challenge.",
            ],
        }
        self.active_gate = gate
        self.state = "WAITING_FOR_USER"
        if self.live:
            self.live.set_allow_control(
                True, "Enter the security check in the live browser or below."
            )
        await self.emit_event(
            "DECIDE",
            "Waiting for the security check.",
            "Security check ka intezaar hai.",
            gate,
            force_screenshot=True,
        )
        response = await self._wait_for_user_response()
        self.active_gate = None
        if self.live:
            self._release_live_control("The agent is driving again.")
        self.state = "RUNNING" if self.is_running else self.state
        if response.get("action") in {"STOPPED", "TIMEOUT", "DISMISS"}:
            if response.get("action") == "TIMEOUT":
                self.is_running = False
            return True
        if response.get("action") == "HANDOFF_COMPLETE":
            self._captcha_signature = signature
            return False

        code = str(response.get("code") or response.get("value") or "").strip()
        if not code:
            return True
        try:
            field = self.page.locator("input[id*='captcha' i]:visible, input[name*='captcha' i]:visible").first
            if await field.count() == 0:
                return True
            await field.fill(code, timeout=8000)
            await field.dispatch_event("change")
            self._captcha_signature = signature
            await self.emit_event(
                "ACT",
                "Security check completed.",
                "Security check complete ho gaya.",
            )
            return False
        except Exception:
            await self.emit_event(
                "SENSE",
                "The security check could not be submitted.",
                "Security check submit nahi ho paya.",
            )
            return True

    async def _captcha_live_handoff(
        self,
        captchas: List[Dict[str, Any]],
        captcha: Dict[str, Any],
        signature: str,
    ) -> None:
        """Pause and let the human solve the challenge in the real browser."""
        kind = str(captcha.get("kind") or "interactive")
        prompt = str(captcha.get("prompt") or "").strip()
        if self.live:
            self.live.set_allow_control(True, "Solve the security check in the live browser.")

        await self.emit_event(
            "THINK",
            "This page has a human-verification challenge. Automation is paused.",
            "Is page par human verification hai. Automation pause kar diya hai.",
        )
        gate = {
            "gate_type": "LIVE_HANDOFF",
            "handoff_type": "captcha",
            "title": "This step needs you",
            "hindi_title": "Yeh step aapke liye hai",
            "description": (
                "Solve the security check directly in the live browser. "
                "FormPilot will not click it, solve it, or inject a token."
            ),
            "captcha_kind": kind,
            "captcha_prompt": prompt[:200],
            "live_session": self.live.public_info() if self.live and not self.live.closed else None,
            "instructions": [
                "Use the live browser on the left. It is the same page the agent is using.",
                "Complete the checkbox, image grid, slider or puzzle yourself.",
                "When the portal shows success, click 'I completed this step'.",
            ],
            "solver_policy": "human_handoff_only",
            "detected_types": sorted({str(item.get("kind") or "unknown") for item in captchas}),
        }
        self.active_gate = gate
        self.state = "WAITING_FOR_USER"
        await self.emit_event(
            "DECIDE",
            "The live browser is yours. Complete the security check, then continue.",
            "Live browser aapka hai. Security check khud pura karein, phir continue karein.",
            gate,
            force_screenshot=True,
        )
        response = await self._wait_for_user_response()
        self.active_gate = None
        if self.live:
            self._release_live_control("The agent is driving again.")
        self.state = "RUNNING" if self.is_running else self.state

        action = response.get("action")
        if action in {"STOPPED", "TIMEOUT"}:
            self.is_running = False
            if action == "TIMEOUT":
                self.last_error = "The security check was left open, so the application paused."
            return
        if action == "DISMISS":
            await self.emit_event(
                "SENSE",
                "The security check is still open. Complete it in the live browser, then continue.",
                "Security check abhi khula hai. Live browser mein pura karein, phir continue karein.",
            )
            return
        if action not in {"HANDOFF_COMPLETE", "CONTINUE", "CAPTCHA_SUBMIT"}:
            return

        self._captcha_signature = signature
        try:
            fresh = await self._scan_dom()
            remaining = fresh.get("captchaElements") or []
            if remaining:
                await self.emit_event(
                    "SENSE",
                    "A security widget is still visible. If the portal accepted the challenge, continue; otherwise reopen the checkpoint.",
                    "Security widget abhi bhi dikh raha hai. Agar portal ne accept kar liya hai to continue karein.",
                )
            else:
                await self.emit_event(
                    "ACT",
                    "Security check cleared. Resuming the form.",
                    "Security check clear ho gaya. Form dobara shuru ho raha hai.",
                )
        except Exception:
            pass


    async def _handle_errors(self, dom: Dict[str, Any]):
        errors = [str(error).strip() for error in (dom.get("errors") or []) if str(error).strip()]
        if not errors:
            return
        signature = f"{dom.get('url')}|{'|'.join(errors[:2])}"
        if signature == self._last_error_signature:
            return
        self._last_error_signature = signature

        self._record_step(
            "error",
            status="failed",
            error_code=classify_failure(errors[0]).value,
            output={"message": errors[0][:300]},
        )
        await self.emit_event(
            "SENSE",
            f"The portal reported: {errors[0]}",
            f"Portal ne bataya: {errors[0]}",
        )
        gate = {
            "gate_type": "ERROR_DIAGNOSIS",
            "title": "The portal needs attention",
            "hindi_title": "Portal par dhyan dein",
            "error_text": errors[0],
            "description": "The portal did not accept the current details. Review the message, edit anything that is wrong in the live browser, then continue.",
            "suggested_actions": ["Review the details", "Try again", "Stop and open the portal myself"],
            "live_session": self.live.public_info() if self.live and not self.live.closed else None,
            "can_takeover": bool(self.live),
        }
        self.active_gate = gate
        self.state = "WAITING_FOR_USER"
        if self.live:
            self.live.set_allow_control(True, "Fix the highlighted field in the live browser.")
        await self.emit_event(
            "DECIDE",
            "Waiting for you to review the portal message.",
            "Portal message review karne ka intezaar hai.",
            gate,
            force_screenshot=True,
        )
        response = await self._wait_for_user_response()
        self.active_gate = None
        if self.live:
            self._release_live_control("The agent is driving again.")
        self.state = "RUNNING" if self.is_running else self.state
        if response.get("action") in {"STOPPED", "TIMEOUT"}:
            self.is_running = False

    # ---------------------------------------------------------------- review + advance

    async def _fill_incomplete_checkpoint(self) -> str:
        """Stop when the page did not keep every value.

        Returns ``recheck`` to rescan and fill again, ``continue`` when the
        human explicitly accepts the incomplete state, or ``stop``.
        """
        summary = self.fill_summary or {}
        if str(summary.get("status") or "") not in {"PARTIAL", "FAILED"}:
            return "continue"

        gate = {
            "gate_type": "FILL_INCOMPLETE",
            "title": "Some fields are not filled",
            "hindi_title": "Kuch fields nahi bhare",
            "section_number": self.current_section,
            "description": (
                "The portal did not keep every value FormPilot entered. "
                "The form is not fully filled. Recheck the fields, edit them in the live browser, "
                "or continue only after you have reviewed them yourself."
            ),
            "fill_summary": summary,
            "fill_failures": list(self.fill_failures),
            "fields_filled": self._public_audit(),
            "live_session": self.live.public_info() if self.live and not self.live.closed else None,
            "can_takeover": bool(self.live),
            "options": [
                {"action": "FILL_RECHECK", "label": "Recheck and fill again"},
                {"action": "CONTINUE", "label": "Continue after reviewing"},
            ],
        }
        while self.is_running:
            self.active_gate = gate
            self.state = "WAITING_FOR_USER"
            if self.live:
                self.live.set_allow_control(
                    True,
                    "Review the unfilled fields in the live browser, then choose recheck or continue.",
                )
            await self.emit_event(
                "DECIDE",
                "Some fields are not filled. Review them before continuing.",
                "Kuch fields nahi bhare. Aage badhne se pehle unhe check karein.",
                gate,
                force_screenshot=True,
            )
            response = await self._wait_for_user_response()
            self.active_gate = None
            if self.live:
                self._release_live_control("The agent is driving again.")
            action = str(response.get("action") or "")
            if action in {"STOPPED", "TIMEOUT"}:
                self.is_running = False
                self.state = "STOPPED" if action == "STOPPED" else "FAILED"
                if action == "TIMEOUT":
                    self.last_error = "No response was received. The application was paused."
                return "stop"
            if action in {"FILL_RECHECK", "RECHECK"}:
                await self.emit_event(
                    "ACT",
                    "Rechecking the form fields now.",
                    "Form ke fields dobara check kar rahe hain.",
                )
                return "recheck"
            if action in {"CONTINUE", "FILL_CONTINUE", "SECTION_APPROVAL"}:
                self.state = "RUNNING"
                return "continue"
            if action == "DISMISS":
                await self.emit_event(
                    "SENSE",
                    "The fill check is still open. Recheck the fields or continue after reviewing them.",
                    "Fill check abhi khula hai. Fields dobara check karein ya review ke baad continue karein.",
                )
                continue
        return "stop"

    async def _section_checkpoint(self) -> bool:
        step = self.current_section
        gate = {
            "gate_type": "SECTION_APPROVAL",
            "title": f"Review section {step}",
            "hindi_title": f"Section {step} review karein",
            "hindi_audio_text": f"Section {step} ready hai. Form par details check karein. Sab sahi ho to continue karein.",
            "section_number": step,
            "description": "Please check the details on the form. You can edit fields directly in the live browser, then continue.",
            "fields_filled": self._public_audit(),
            "fill_summary": self.fill_summary,
            "fill_failures": list(self.fill_failures),
            "live_session": self.live.public_info() if self.live and not self.live.closed else None,
            "can_takeover": bool(self.live),
        }
        self.active_gate = gate
        self.state = "WAITING_FOR_USER"
        if self.live:
            self.live.set_allow_control(True, "Review and edit the form in the live browser.")
        await self.emit_event(
            "DECIDE",
            f"Section {step} is ready for your review.",
            f"Section {step} review ke liye ready hai.",
            gate,
            force_screenshot=True,
        )
        response = await self._wait_for_user_response()
        self.active_gate = None
        if self.live:
            self._release_live_control("The agent is driving again.")
        if response.get("action") in {"STOPPED", "TIMEOUT"}:
            self.is_running = False
            self.state = "STOPPED" if response.get("action") == "STOPPED" else "FAILED"
            if response.get("action") == "TIMEOUT":
                self.last_error = "No response was received. The application was paused."
            return False
        self.state = "RUNNING"
        approved = bool(response.get("approved")) or response.get("action") in {"SECTION_APPROVAL", "CONTINUE"}
        if approved:
            self._remember_portal_account(
                registration_status="in_progress",
                last_known_step=f"section_{step}",
                confirmed_by_human=True,
            )
        if not approved:
            await self.emit_event(
                "THINK",
                "You asked to review the details before continuing.",
                "Aap details check karna chahte hain. Form edit kar sakte hain.",
            )
        return approved

    @staticmethod
    def _dom_signature(dom: Dict[str, Any]) -> str:
        fields = "|".join(
            f"{item.get('name') or item.get('id') or ''}:{item.get('type') or ''}"
            for item in (dom.get("inputs") or [])
        )
        return f"{dom.get('url') or ''}|{dom.get('formAction') or ''}|{fields}"

    async def _advance(self, dom: Dict[str, Any]) -> bool:
        adapter = self._adapter or get_adapter(self.page.url if self.page else "")
        # Field filling and the security checkpoints may have re-rendered the
        # page, so never click a button id from an older scan.  Take a fresh
        # blueprint immediately before the navigation action.
        try:
            dom = await self._scan_dom()
        except Exception:
            pass
        if self._is_otp_page(dom):
            await self.emit_event(
                "SENSE",
                "The verification code is still required before this step can continue.",
                "Aage badhne se pehle verification code zaroori hai.",
            )
            return False
        button = adapter.find_next_button(dom)
        if not button:
            if adapter.is_payment_page(self.page, dom):
                await self._trigger_pre_payment_lock()
                return True
            return False

        previous_step = self.current_section
        if self._is_final_action(button):
            await self._trigger_pre_payment_lock(final_action=True)
            return True
        before_signature = self._dom_signature(dom)
        before = await self._page_snapshot()
        await self.emit_event(
            "ACT",
            f"Saving section {previous_step}...",
            f"Section {previous_step} save kar rahe hain...",
        )
        self._save_current_recipe()
        if not await self._safe_click(button):
            return False

        changed = await self._wait_for_page_change(before)
        if not changed:
            await self.emit_event(
                "SENSE",
                "The portal did not move to the next step. Nothing was saved.",
                "Portal agle step par nahi gaya. Kuch save nahi hua.",
            )
            return False

        self._captcha_signature = ""
        self._last_error_signature = ""
        try:
            fresh = await self._scan_dom()
            fresh_signature = self._dom_signature(fresh)
            if fresh_signature == before_signature or fresh_signature == self._last_advance_signature:
                # A validation toast or a transient overlay can change the
                # page text without moving the form.  Never report a save
                # twice for the same form.
                await self.emit_event(
                    "SENSE",
                    "The portal is still showing the same step. Nothing was saved.",
                    "Portal abhi bhi wahi step dikha raha hai. Kuch save nahi hua.",
                )
                return False
            self._last_advance_signature = fresh_signature
            self.current_section = adapter.current_step(self.page, fresh)
            visible = str(fresh.get("visibleText") or "").lower()
            if any(token in visible for token in ("dashboard", "logged in", "sign out", "logout")):
                await self.emit_event(
                    "ACT",
                    "Signed in successfully.",
                    "Sign in ho gaya.",
                )
                return True
            if adapter.is_payment_page(self.page, fresh):
                await self.emit_event(
                    "THINK",
                    "The payment page is open. Stopping before any payment action.",
                    "Payment page khul gaya. Payment se pehle ruk rahe hain.",
                )
                return True
        except Exception:
            pass

        await self.emit_event(
            "ACT",
            f"Section {previous_step} saved and the next step is open.",
            f"Section {previous_step} save ho gaya aur agla step khul gaya.",
        )
        return True

    # ---------------------------------------------------------------- pre-payment

    _FINAL_ACTION_PATTERN = re.compile(
        r"\b(?:submit|pay|payment|checkout|finish|"
        r"complete\s+(?:application|registration)|proceed\s+to\s+pay)\b",
        re.IGNORECASE,
    )

    @classmethod
    def _is_final_action(cls, button: Dict[str, Any]) -> bool:
        """True for a button that would submit or pay for the application.

        Navigation labels such as "Save & Next: Pre-Payment Review" mention
        payment but only move to another section, so they are excluded.
        """
        text = str(button.get("text") or "").strip()
        if re.search(r"(?:save\s*&\s*next|save\s+and\s+next|next\s+step)", text, re.IGNORECASE):
            return False
        return bool(cls._FINAL_ACTION_PATTERN.search(text))

    @staticmethod
    def _masked_phone(value: str) -> str:
        text = str(value or "")
        if len(text) <= 4:
            return "your saved number"
        return f"{'*' * (len(text) - 4)}{text[-4:]}"

    @staticmethod
    def _normalise_value(value: Any) -> str:
        return " ".join(str(value or "").split()).strip().lower().replace("-", "/").replace(".", "/")

    async def _trigger_pre_payment_lock(self, *, final_action: bool = False):
        """Stop before payment or final submission, show an audit, and hand over."""
        self._save_current_recipe()
        if self.live:
            self.live.set_allow_control(
                True,
                "Payment and final submission are yours. FormPilot will not click them.",
            )
        try:
            reg_id = await self.page.evaluate(
                "() => { const el = document.getElementById('permanent-reg-id'); return el ? el.innerText.trim() : ''; }"
            )
            if reg_id and "PENDING" not in reg_id:
                self.vault_mgr.add_custom_field("otr_registration_id", reg_id)
                await self.emit_event(
                    "THINK",
                    f"Registration ID saved: {reg_id}",
                    f"Registration ID save ho gaya: {reg_id}",
                )
        except Exception:
            reg_id = ""

        try:
            current_values = await self.page.evaluate(DOMScanner.EXTRACT_VALUES_JS, True)
        except Exception:
            current_values = []

        by_id = {str(v.get("id")): v for v in current_values if v.get("id")}
        by_name = {str(v.get("name")): v for v in current_values if v.get("name")}

        records: List[Dict[str, Any]] = []
        mismatches = 0
        for item in self._public_audit():
            field_id = item.get("field_id") or ""
            field_name = item.get("field_name") or ""
            current = by_id.get(field_id) or by_name.get(field_name)
            form_values: List[str] = []
            if current:
                form_values = [
                    str(current.get("value") or ""),
                    str(current.get("selectedText") or ""),
                ]
            form_value = next((value for value in form_values if value), "")
            saved_display = str(item.get("injected_value") or "")
            if not form_value:
                status = "EMPTY"
                risk = 60
                mismatches += 1
            elif item.get("vault_key") in {"photo_upload", "signature_upload", "matric_cert_upload"}:
                status = "MATCH"
                risk = 0
            elif any(
                self._normalise_value(value) == self._normalise_value(saved_display)
                for value in form_values
                if value
            ):
                status = "MATCH"
                risk = 0
            else:
                # Masked values cannot be compared character-for-character.
                key = item.get("vault_key") or ""
                spec = field_registry.spec_for(key)
                if spec and spec.sensitive:
                    status = "MATCH"
                    risk = 0
                else:
                    status = "MISMATCH"
                    risk = 40
                    mismatches += 1

            records.append(
                {
                    "field": item.get("field_label"),
                    "vault_value": saved_display,
                    "form_value": field_registry.mask_value(item.get("vault_key") or "", form_value),
                    "status": status,
                    "risk_score": risk,
                }
            )

        audit_payload = {
            "run_id": self.run_id,
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "portal_url": self.page.url if self.page else self.target_url,
            "registration_id": reg_id,
            "records": records,
            "total_checked": len(records),
            "total_matched": len(records) - mismatches,
            "total_mismatches": mismatches,
            "audit_hash": hashlib.sha256(json.dumps(records, sort_keys=True).encode("utf-8")).hexdigest(),
            "disclaimer": (
                "FormPilot never clicks a payment button or a final submission button."
            ),
        }
        approval_snapshot = {
            "run_id": self.run_id,
            "url": audit_payload["portal_url"],
            "audit_hash": audit_payload["audit_hash"],
            "field_digest": self._digest_field_values(current_values),
            "captured_at": audit_payload["generated_at"],
        }
        self._approval_snapshot = approval_snapshot
        audit_payload["approval_snapshot"] = approval_snapshot
        if self.run_id:
            try:
                self.run_store.save_audit(self.run_id, self._persisted_audit(audit_payload))
            except Exception:
                pass

        fill_status = str((self.fill_summary or {}).get("status") or "")
        fill_incomplete = fill_status in {"PARTIAL", "FAILED"}
        safety_status = (
            "READY_FOR_REVIEW"
            if mismatches == 0 and not fill_incomplete
            else "NEEDS_REVIEW"
        )
        gate = {
            "gate_type": "PRE_PAYMENT_SAFETY_LOCK",
            "title": (
                "Review before final submission"
                if final_action
                else "Review before payment"
            ),
            "run_id": self.run_id,
            "final_action": "submission" if final_action else "payment",
            "hindi_title": (
                "Final submit se pehle review karein"
                if final_action
                else "Payment se pehle review karein"
            ),
            "hindi_audio_text": (
                "Final step aa gaya hai. Neeche di gayi details check karein. "
                "Final submit aap khud portal par karein."
                if final_action
                else "Payment step aa gaya hai. Neeche di gayi details check karein. "
                "Payment aap khud portal par karein."
            ),
            "description": (
                "This is the final step. FormPilot has stopped here. "
                "Check the details below, then complete the final submission yourself "
                "in the portal. Nothing is submitted automatically."
                if final_action
                else "The application fee page is open. FormPilot has stopped here. "
                "Check the details below, then complete the payment yourself in the portal. "
                "Nothing is submitted or paid automatically."
            ),
            "audit_diff": records,
            "total_verified_fields": len(records) - mismatches,
            "total_checked_fields": len(records),
            "total_mismatches": mismatches,
            "fill_summary": self.fill_summary,
            "fill_failures": list(self.fill_failures),
            "safety_status": safety_status,
            "registration_id": reg_id,
            "portal_url": self.page.url if self.page else self.target_url,
            "audit_hash": audit_payload["audit_hash"],
            "approval_snapshot": approval_snapshot,
            "approval_valid": True,
            "download_available": True,
            "live_session": self.live.public_info() if self.live and not self.live.closed else None,
            "can_takeover": bool(self.live),
            "human_action_required": "payment" if not final_action else "final_submission",
        }
        self.active_gate = gate
        self.state = "AWAITING_PAYMENT"
        self.is_running = False
        await self.emit_event(
            "DECIDE",
            (
                "Final step reached. FormPilot stopped before submitting anything."
                if final_action
                else "Payment page reached. FormPilot stopped before any payment action."
            ),
            (
                "Final step aa gaya. FormPilot ne submit karne se pehle ruk gaya. "
                "Ab aap khud final submit karein."
                if final_action
                else "Payment page aa gaya. FormPilot ne payment se pehle ruk gaya. "
                "Ab aap khud payment karein."
            ),
            gate,
            force_screenshot=True,
        )
        self._record_step(
            "submit",
            status="waiting",
            output={
                "final_action": bool(final_action),
                "gate_type": str((gate or {}).get("gate_type") or ""),
                "audit_hash": audit_payload.get("audit_hash"),
            },
        )
        if self.run_id:
            self.run_store.finish(
                self.run_id,
                self.state,
                {
                    "audit_hash": audit_payload["audit_hash"],
                    "target_url": self.target_url,
                    "run_clock": self.run_clock(),
                },
            )

    # ---------------------------------------------------------------- helpers

    async def _safe_click(self, button: Dict[str, Any]) -> bool:
        """Click a blueprint element, or a uniquely identified legacy control.

        A blueprint id is always tried first.  If the id is stale we re-scan
        once and re-identify the same control by its durable locators.  The
        legacy path is only used for controls that predate the blueprint and
        it refuses ambiguous matches instead of silently taking ``.first``.
        """
        self._last_action_result = None
        if not self.page:
            return False

        element_id = str(button.get("element_id") or "")
        resolver = self._action_resolver()
        if element_id and resolver:
            result = await resolver.click(element_id)
            if result.ok:
                self._last_action_result = result
                return True

            if result.error_code in {"NOT_FOUND", "STALE_SNAPSHOT", "FRAME_NOT_ACCESSIBLE"}:
                fresh_id = await self._find_fresh_element_id(button)
                if fresh_id and fresh_id != element_id:
                    resolver = self._action_resolver()
                    if resolver:
                        retry = await resolver.click(fresh_id)
                        if retry.ok:
                            self._last_action_result = retry
                            button["element_id"] = fresh_id
                            return True
                        result = retry

            self._last_action_result = result
            await self.emit_event(
                "SENSE",
                f"Could not click {button.get('text') or 'the control'} ({result.error_code}): {result.message}",
                f"{button.get('text') or 'Control'} click nahi ho paya. Page dobara scan kar rahe hain.",
            )
            return False

        return await self._legacy_click(button)

    async def _find_fresh_element_id(self, button: Dict[str, Any]) -> Optional[str]:
        """Re-identify a control after a re-scan using durable locators."""
        blueprint = await self._rescan_blueprint()
        if not blueprint:
            return None

        old_css = str(button.get("css") or "")
        old_xpath = str(button.get("xpath") or "")
        old_tag = str(button.get("tagName") or button.get("tag") or "").lower()
        old_role = str(button.get("role") or "").lower()
        old_name = str(button.get("text") or button.get("name") or "").strip().lower()
        old_id = str(button.get("id") or "")

        def unique(matches: List[BlueprintElement]) -> Optional[str]:
            return matches[0].id if len(matches) == 1 else None

        elements = list(blueprint.elements.values())
        if old_css:
            found = unique([element for element in elements if element.css == old_css])
            if found:
                return found
        if old_xpath:
            found = unique([element for element in elements if element.xpath == old_xpath])
            if found:
                return found
        if old_id:
            found = unique(
                [element for element in elements if str(element.attributes.get("id") or "") == old_id]
            )
            if found:
                return found
        if old_role and old_name:
            found = unique(
                [
                    element
                    for element in elements
                    if element.role == old_role
                    and str(element.name or "").strip().lower() == old_name
                    and (not old_tag or element.tag == old_tag)
                ]
            )
            if found:
                return found
        if old_name and old_tag:
            found = unique(
                [
                    element
                    for element in elements
                    if element.tag == old_tag
                    and str(element.name or "").strip().lower() == old_name
                ]
            )
            if found:
                return found
        return None

    async def _legacy_click(self, button: Dict[str, Any]) -> bool:
        """Last-resort click for controls without a blueprint element id.

        Every candidate must resolve to exactly one node.  A text that matches
        several nodes is rejected, because guessing the first one is what made
        the HPSC login link fail.
        """
        if not self.page:
            return False
        text = str(button.get("text") or "").strip()
        candidates = []
        if button.get("id"):
            candidates.append(self.page.locator(f"#{button['id']}"))
        if button.get("css"):
            candidates.append(self.page.locator(str(button["css"])))
        if button.get("xpath"):
            candidates.append(self.page.locator(f"xpath={button['xpath']}"))
        role = str(button.get("role") or "").strip()
        if role and text:
            candidates.append(self.page.get_by_role(role, name=text, exact=True))
        if text:
            for role_name in ("button", "link"):
                candidates.append(self.page.get_by_role(role_name, name=text, exact=True))
            tag = str(button.get("tagName") or "").lower()
            if tag:
                escaped = text.replace("\\", "\\\\").replace('"', '\\"')
                candidates.append(self.page.locator(f'{tag}:text-is("{escaped}")'))

        for locator in candidates:
            try:
                count = await locator.count()
            except Exception:
                continue
            if count != 1:
                continue
            try:
                await locator.scroll_into_view_if_needed(timeout=5000)
                if not await locator.is_visible():
                    continue
                await locator.click(timeout=8000)
                self._last_action_result = ActionResult(
                    ok=True,
                    action="click",
                    method="legacy_unique",
                    message=f"Clicked {text or 'the control'}.",
                    scan_id=self.blueprint.scan_id if self.blueprint else "",
                )
                return True
            except Exception as exc:
                self._last_action_result = ActionResult(
                    ok=False,
                    action="click",
                    error_code="CLICK_FAILED",
                    message=str(exc)[:200],
                    scan_id=self.blueprint.scan_id if self.blueprint else "",
                )
        return False

    def _stopped_gate_result(self) -> Dict[str, Any]:
        """Keep a stop request authoritative even if a gate opened mid-teardown."""
        self._close_gate_step("STOPPED")
        self.state = "STOPPED"
        self.active_gate = None
        return {"action": "STOPPED"}

    async def _wait_for_user_response(self) -> Dict[str, Any]:
        if self._stop_requested or not self.is_running:
            return self._stopped_gate_result()
        if self._pending_user_response is not None:
            result = self._pending_user_response
            self._pending_user_response = None
            return result
        loop = asyncio.get_running_loop()
        self.active_event_future = loop.create_future()
        # Close the race where stop() lands between the check above and the
        # future being created: either this check sees the stop request, or
        # stop() sees the future and resolves it.
        if self._stop_requested or not self.is_running:
            self.active_event_future = None
            return self._stopped_gate_result()
        try:
            result = await asyncio.wait_for(self.active_event_future, timeout=settings.GATE_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            self.active_event_future = None
            self._close_gate_step("TIMEOUT")
            await self.emit_event(
                "DECIDE",
                "No response was received, so the application was paused.",
                "Koi response nahi aaya, isliye application pause ho gayi.",
            )
            return {"action": "TIMEOUT"}
        finally:
            self.active_event_future = None
        if result.get("action") == "STOPPED":
            return self._stopped_gate_result()
        return result

