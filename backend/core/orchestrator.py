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
from urllib.parse import urljoin

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    async_playwright,
)

from . import field_registry, settings
from .action_resolver import ActionResolver, ActionResult
from .biometrics import BiometricCompressor
from .blueprint import BlueprintElement, PageBlueprint
from .dom_scanner import DOMScanner
from .form_model import FormModel
from .live_browser import LiveBrowserSession, live_sessions
from .navigator import ResilientNavigator
from .oracle import OracleResult, PortalOracle
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

        self.current_section = 1
        self.filled_audit: List[Dict[str, Any]] = []

        self.state = "IDLE"
        self.run_id: Optional[str] = None
        self.last_error: Optional[str] = None
        self.target_url = ""
        self.query = ""
        self.mode = "local"
        self.run_mode = "fill"
        self.oracle_result: Optional[OracleResult] = None
        self.form_map: Optional[Dict[str, Any]] = None
        self.blueprint: Optional[PageBlueprint] = None
        self._last_action_result: Optional[ActionResult] = None
        self.recipe_store = RecipeStore()
        self._recipe_status: Optional[Dict[str, Any]] = None
        self._last_form_fingerprint = ""
        self._last_recipe_event = ""
        self._pending_upload: Optional[Dict[str, Any]] = None
        self._session_values: Dict[str, str] = {}

        self._otp_cleared = False
        self._captcha_signature = ""
        self._last_error_signature = ""
        self._last_gateway_signature = ""
        self._last_scan_key = ""
        self._last_screenshot_at = 0.0
        self._idle_cycles = 0

    # ---------------------------------------------------------------- public API

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
            "form_map": self.form_map,
            "blueprint": self.blueprint.summary() if self.blueprint else None,
            "recipe": self._recipe_status,
            "current_section": self.current_section,
            "active_gate": self.active_gate if self.is_running or self.state in {"WAITING_FOR_USER", "PAUSED"} else None,
            "filled_audit": self._public_audit(),
            "last_error": self.last_error,
            "oracle": self.oracle_result.model_dump() if self.oracle_result else None,
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
        self.current_section = 1
        self.active_gate = None
        self.last_error = None
        self.query = (query_or_url or "").strip()
        self.target_url = ""
        self.oracle_result = None
        self.run_mode = run_mode
        self.form_map = None
        self._recipe_status = None
        self._last_form_fingerprint = ""
        self._last_recipe_event = ""
        self._session_values = {}
        self._otp_cleared = False
        self._captcha_signature = ""
        self._last_error_signature = ""
        self._last_gateway_signature = ""
        self._last_scan_key = ""
        self._idle_cycles = 0
        self.run_id = f"run-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        self.state = "RESOLVING"
        self.run_store.start(self.run_id, {"query": self.query, "mode": self.mode, "run_mode": self.run_mode})

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
            self.run_store.finish(
                self.run_id or "unknown",
                self.state,
                {"error": self.last_error, "target_url": self.target_url, "run_mode": self.run_mode},
            )

    async def stop(self):
        self._stop_requested = True
        self.is_running = False
        self.paused = False
        self._is_paused = False
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
        self._recipe_status = None
        self.current_section = 1
        self.filled_audit = []
        self.last_error = None
        self.active_gate = None
        self._pending_user_response = None
        self._stop_requested = False
        self.paused = False
        self._is_paused = False
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

    def submit_user_response(self, data: Dict[str, Any]):
        if self.active_event_future and not self.active_event_future.done():
            self.active_event_future.set_result(data)
        elif self.active_gate is not None:
            self._pending_user_response = data

    # ---------------------------------------------------------------- browser

    async def _open_browser(self, target_url: str):
        cfg = self.tinyfish_mgr.config
        if not self.playwright:
            self.playwright = await async_playwright().start()

        session: Optional[TinyFishSession] = None
        try:
            session = await self.tinyfish_mgr.create_cloud_browser_session(target_url)
        except TinyFishError as exc:
            await self.emit_event(
                "SENSE",
                "The cloud browser is unavailable right now. Continuing in this device's browser.",
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
            "form_map": self.form_map,
            "blueprint": self.blueprint.summary() if self.blueprint else None,
            "recipe": self._recipe_status,
        }
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

            if gateways and not inputs:
                await self._gateway_checkpoint(dom, gateways)
                continue

            if not inputs:
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
            await self._handle_otp(dom)
            fresh = await self._scan_dom()
            await self._handle_captcha(fresh)
            fresh = await self._scan_dom()
            await self._handle_errors(fresh)

            approved = await self._section_checkpoint()
            if not approved:
                if self.state in {"STOPPED", "FAILED"} or not self.is_running:
                    return
                await asyncio.sleep(0.4)
                continue

            advanced = await self._advance(dom)
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

    async def _gateway_checkpoint(self, dom: Dict[str, Any], gateways: List[Dict[str, Any]]):
        signature = "|".join(sorted(f"{g.get('type')}:{g.get('id')}:{g.get('text')}" for g in gateways))
        if signature == self._last_gateway_signature:
            await asyncio.sleep(1)
            return
        self._last_gateway_signature = signature

        unique: List[Dict[str, Any]] = []
        seen = set()
        for gateway in gateways:
            key = (
                gateway.get("type"),
                gateway.get("text"),
                gateway.get("element_id") or gateway.get("css") or gateway.get("id"),
            )
            if key in seen:
                continue
            seen.add(key)
            unique.append(gateway)

        if len(unique) == 1:
            await self._click_gateway(unique[0])
            return

        await self.emit_event(
            "THINK",
            "This portal offers more than one way to start.",
            "Portal par do raste hain. Aap decide karein kaise shuru karna hai.",
        )
        gate = {
            "gate_type": "GATEWAY_DECISION",
            "title": "How would you like to start?",
            "hindi_title": "Shuru kaise karein?",
            "description": "Choose one option. You can review the next screen before any details are filled.",
            "options": [
                {
                    "id": g.get("id"),
                    "element_id": g.get("element_id"),
                    "text": g.get("text"),
                    "type": g.get("type"),
                }
                for g in unique
            ],
        }
        self.active_gate = gate
        self.state = "WAITING_FOR_USER"
        await self.emit_event(
            "DECIDE",
            "Waiting for you to choose how to start.",
            "Aapke choice ka intezaar hai.",
            gate,
            force_screenshot=True,
        )
        response = await self._wait_for_user_response()
        self.active_gate = None
        if response.get("action") in {"STOPPED", "TIMEOUT"}:
            self.is_running = False
            return

        selected_id = response.get("id")
        selected_element_id = response.get("element_id")
        selected_text = response.get("text")
        selected = None
        for gateway in unique:
            if selected_element_id and gateway.get("element_id") == selected_element_id:
                selected = gateway
                break
            if selected_id and gateway.get("id") == selected_id:
                selected = gateway
                break
        if not selected and selected_text:
            selected = next((g for g in unique if g.get("text") == selected_text), None)
        if not selected:
            selected = unique[0]
        await self._click_gateway(selected)

    async def _click_gateway(self, gateway: Dict[str, Any]):
        self.state = "RUNNING"
        self._otp_cleared = False
        self._captcha_signature = ""
        self._last_error_signature = ""
        await self.emit_event(
            "ACT",
            f"Opening: {gateway.get('text') or 'the application form'}",
            "Chuni hui option khol rahe hain...",
        )
        before_url = self.page.url
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
        await self.page.wait_for_timeout(500)
        if self.page.url != before_url:
            # A new page owns its own gateway signature.  If the click did not
            # navigate, keep the old signature so the loop cannot double-click
            # the same gateway.
            self._last_gateway_signature = ""

    # ---------------------------------------------------------------- filling

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

    async def _fill_form(self, dom: Dict[str, Any]) -> int:
        filled = 0
        vault = self.vault_mgr.vault
        for item in dom.get("inputs") or []:
            if not self.is_running:
                break
            if (item.get("type") or "").lower() in {"submit", "button", "reset", "image"}:
                continue

            sem_key, _is_verify = DOMScanner.classify_field(item)
            custom_field = False
            if not sem_key:
                if not self._should_ask_unknown(item):
                    continue
                value = await self._ask_for_unknown_field(item)
                if not value:
                    continue
                sem_key = self._custom_key(item)
                custom_field = True
            else:
                if sem_key in {"photo_upload", "signature_upload", "matric_cert_upload"}:
                    if await self._handle_upload(item, sem_key):
                        filled += 1
                    continue

                value = vault.find_field_value(sem_key)
                if sem_key == "dob" and value:
                    value = vault.get_formatted_dob("DD/MM/YYYY")

                if not value:
                    value = await self._ask_for_missing_field(item, sem_key)
                    if not value:
                        continue
                    vault = self.vault_mgr.vault

            result = await self._apply_field_value(item, str(value))

            if result.get("success"):
                filled += 1
                self._record_fill(item, sem_key, str(value), result.get("method", "input"), custom=custom_field)
                await self.emit_event(
                    "ACT",
                    f"Filled: {item.get('label') or sem_key}",
                    f"{item.get('label') or sem_key} bhar diya hai.",
                )
            else:
                await self.emit_event(
                    "SENSE",
                    f"Could not fill {item.get('label') or sem_key}: {result.get('reason', 'unknown reason')}",
                    f"{item.get('label') or sem_key} fill nahi ho paya. Aap ise manually check kar sakte hain.",
                )
            await asyncio.sleep(0.08)
        return filled

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
            self.live.set_allow_control(False, "The agent is driving again.")
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

    async def _ask_for_missing_field(self, item: Dict[str, Any], sem_key: str) -> str:
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
            self.live.set_allow_control(False, "The agent is driving again.")
        self.state = "RUNNING" if self.is_running else self.state
        if response.get("action") in {"STOPPED", "TIMEOUT", "DISMISS", "SKIP"}:
            if response.get("action") == "TIMEOUT":
                self.is_running = False
            return ""
        if response.get("action") == "HANDOFF_COMPLETE":
            return ""
        value = str(response.get("value") or response.get("text") or "").strip()
        if value:
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

        self._record_fill(item, sem_key, str(candidate), "file")
        await self.emit_event(
            "ACT",
            f"Uploaded: {item.get('label') or sem_key}",
            f"{item.get('label') or sem_key} upload ho gaya.",
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
            self.live.set_allow_control(False, "The agent is driving again.")
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

    async def _handle_otp(self, dom: Optional[Dict[str, Any]] = None):
        if self._otp_cleared or not self.page:
            return
        dom = dom or {}
        otp_inputs = dom.get("otpInputs") or []
        selector = "#btn-send-otp, button:has-text('Send OTP'), button:has-text('Get OTP'), button:has-text('Send code')"
        button = None
        try:
            candidate = self.page.locator(selector).first
            if await candidate.count() > 0 and await candidate.is_visible():
                button = candidate
        except Exception:
            button = None
        if button is None and not otp_inputs:
            return

        await self.emit_event(
            "THINK",
            "The portal needs to verify your phone number.",
            "Portal phone number verify karna chahta hai.",
        )
        if button is not None:
            try:
                await button.click(timeout=8000)
            except Exception:
                pass
            await self.page.wait_for_timeout(900)

        config = self.tinyfish_mgr.config
        gate = {
            "gate_type": "OTP_RELAY",
            "title": "Enter the verification code",
            "hindi_title": "Verification code enter karein",
            "hindi_audio_text": "Aapke phone par code bheja gaya hai. Woh code yahan enter karein.",
            "description": "Enter the 6-digit code sent to the phone number saved in your details. FormPilot never stores this code.",
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
        if settings.DEMO_MODE:
            gate["demo_otp"] = settings.DEMO_OTP
            gate["description"] += f" Demo mode code: {settings.DEMO_OTP}."
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
            self.live.set_allow_control(False, "The agent is driving again.")
        self.state = "RUNNING" if self.is_running else self.state
        if response.get("action") in {"STOPPED", "TIMEOUT", "DISMISS"}:
            if response.get("action") == "TIMEOUT":
                self.is_running = False
            return
        if response.get("action") == "HANDOFF_COMPLETE":
            self._otp_cleared = True
            await self.emit_event(
                "ACT",
                "Verification completed in the live browser.",
                "Live browser mein verification pura ho gaya.",
            )
            return

        otp = str(response.get("otp") or response.get("code") or "").strip()
        if not otp:
            return
        try:
            otp_input = self.page.locator("input[id*='otp' i]:visible, input[name*='otp' i]:visible").first
            if await otp_input.count() == 0:
                return
            await otp_input.fill(otp, timeout=8000)
            verify = self.page.locator("#btn-verify-otp, button:has-text('Verify OTP'), button:has-text('Verify')").first
            if await verify.count() > 0 and await verify.is_visible():
                await verify.click(timeout=8000)
            await self.page.wait_for_timeout(700)
            self._otp_cleared = True
            await self.emit_event(
                "ACT",
                "Verification code submitted.",
                "Verification code submit ho gaya.",
            )
        except Exception:
            await self.emit_event(
                "SENSE",
                "The verification code could not be submitted. Please check it and try again.",
                "Verification code submit nahi ho paya. Dobara koshish karein.",
            )

    async def _handle_captcha(self, dom: Dict[str, Any]):
        captchas = dom.get("captchaElements") or []
        if not captchas or not self.page:
            return

        kinds = sorted({str(captcha.get("kind") or "unknown") for captcha in captchas})
        signature = f"{dom.get('url')}|{'|'.join(kinds)}|" + "|".join(
            str(captcha.get("id") or captcha.get("tagName") or "") for captcha in captchas[:3]
        )
        if signature == self._captcha_signature:
            return

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
            return

        # Text CAPTCHA (for example "hJ8ik)3") can be entered in the gate.
        captcha = next(
            (item for item in captchas if str(item.get("kind") or "") == "text"),
            captchas[0],
        )
        selector = f"#{captcha.get('id')}" if captcha.get("id") else str(captcha.get("tagName") or "canvas")
        image_b64 = ""
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
        await self.emit_event(
            "DECIDE",
            "Waiting for the security check.",
            "Security check ka intezaar hai.",
            gate,
            force_screenshot=True,
        )
        response = await self._wait_for_user_response()
        self.active_gate = None
        self.state = "RUNNING" if self.is_running else self.state
        if response.get("action") in {"STOPPED", "TIMEOUT", "DISMISS"}:
            if response.get("action") == "TIMEOUT":
                self.is_running = False
            return
        if response.get("action") == "HANDOFF_COMPLETE":
            self._captcha_signature = signature
            return

        code = str(response.get("code") or response.get("value") or "").strip()
        if not code:
            return
        try:
            field = self.page.locator("input[id*='captcha' i]:visible, input[name*='captcha' i]:visible").first
            if await field.count() == 0:
                return
            await field.fill(code, timeout=8000)
            await field.dispatch_event("change")
            self._captcha_signature = signature
            await self.emit_event(
                "ACT",
                "Security check completed.",
                "Security check complete ho gaya.",
            )
        except Exception:
            await self.emit_event(
                "SENSE",
                "The security check could not be submitted.",
                "Security check submit nahi ho paya.",
            )

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
            self.live.set_allow_control(False, "The agent is driving again.")
        self.state = "RUNNING" if self.is_running else self.state

        action = response.get("action")
        if action in {"STOPPED", "TIMEOUT"}:
            self.is_running = False
            if action == "TIMEOUT":
                self.last_error = "The security check was left open, so the application paused."
            return
        if action == "DISMISS":
            self._captcha_signature = signature
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
            self.live.set_allow_control(False, "The agent is driving again.")
        self.state = "RUNNING" if self.is_running else self.state
        if response.get("action") in {"STOPPED", "TIMEOUT"}:
            self.is_running = False

    # ---------------------------------------------------------------- review + advance

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
            self.live.set_allow_control(False, "The agent is driving again.")
        if response.get("action") in {"STOPPED", "TIMEOUT"}:
            self.is_running = False
            self.state = "STOPPED" if response.get("action") == "STOPPED" else "FAILED"
            if response.get("action") == "TIMEOUT":
                self.last_error = "No response was received. The application was paused."
            return False
        self.state = "RUNNING"
        approved = bool(response.get("approved")) or response.get("action") in {"SECTION_APPROVAL", "CONTINUE"}
        if not approved:
            await self.emit_event(
                "THINK",
                "You asked to review the details before continuing.",
                "Aap details check karna chahte hain. Form edit kar sakte hain.",
            )
        return approved

    async def _advance(self, dom: Dict[str, Any]) -> bool:
        adapter = self._adapter or get_adapter(self.page.url if self.page else "")
        # Field filling and the security checkpoints may have re-rendered the
        # page, so never click a button id from an older scan.  Take a fresh
        # blueprint immediately before the navigation action.
        try:
            dom = await self._scan_dom()
        except Exception:
            pass
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
        await self.emit_event(
            "ACT",
            f"Saving section {previous_step}...",
            f"Section {previous_step} save kar rahe hain...",
        )
        self._save_current_recipe()
        if not await self._safe_click(button):
            return False

        changed = await adapter.wait_for_step_change(self.page, previous_step)
        if not changed:
            return False

        self._captcha_signature = ""
        self._last_error_signature = ""
        try:
            fresh = await self._scan_dom()
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
            f"Section {previous_step} saved.",
            f"Section {previous_step} save ho gaya.",
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
        if self.run_id:
            try:
                self.run_store.save_audit(self.run_id, audit_payload)
            except Exception:
                pass

        safety_status = "READY_FOR_REVIEW" if mismatches == 0 else "NEEDS_REVIEW"
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
            "safety_status": safety_status,
            "registration_id": reg_id,
            "portal_url": self.page.url if self.page else self.target_url,
            "audit_hash": audit_payload["audit_hash"],
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
        if self.run_id:
            self.run_store.finish(
                self.run_id,
                self.state,
                {"audit_hash": audit_payload["audit_hash"], "target_url": self.target_url},
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

