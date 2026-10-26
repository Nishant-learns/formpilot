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

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    async_playwright,
)

from . import field_registry, settings
from .biometrics import BiometricCompressor
from .dom_scanner import DOMScanner
from .navigator import ResilientNavigator
from .oracle import OracleResult, PortalOracle
from .portal_adapter import BasePortalAdapter, get_adapter
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

        self.is_running = False
        self.paused = False
        self._is_paused = False
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
        self.oracle_result: Optional[OracleResult] = None

        self._otp_cleared = False
        self._captcha_signature = ""
        self._last_error_signature = ""
        self._last_gateway_signature = ""
        self._last_scan_key = ""
        self._last_screenshot_at = 0.0
        self._idle_cycles = 0

    # ---------------------------------------------------------------- public API

    def get_state(self) -> Dict[str, Any]:
        return {
            "state": self.state,
            "is_running": self.is_running,
            "paused": self.paused or self._is_paused,
            "run_id": self.run_id,
            "query": self.query,
            "target_url": self.target_url,
            "mode": self.mode,
            "current_section": self.current_section,
            "active_gate": self.active_gate,
            "filled_audit": self._public_audit(),
            "last_error": self.last_error,
            "oracle": self.oracle_result.model_dump() if self.oracle_result else None,
        }

    async def start_application(self, query_or_url: str):
        if self.is_running:
            await self.emit_event("SENSE", "An application is already in progress.", "Ek application pehle se chal rahi hai.")
            return

        if self.browser or self.page:
            await self._cleanup()
        self.is_running = True
        self.paused = False
        self._is_paused = False
        self._pending_user_response = None
        self.filled_audit = []
        self.current_section = 1
        self.active_gate = None
        self.last_error = None
        self.query = (query_or_url or "").strip()
        self.target_url = ""
        self.oracle_result = None
        self._otp_cleared = False
        self._captcha_signature = ""
        self._last_error_signature = ""
        self._last_gateway_signature = ""
        self._last_scan_key = ""
        self._idle_cycles = 0
        self.run_id = f"run-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        self.state = "RESOLVING"
        self.run_store.start(self.run_id, {"query": self.query, "mode": self.mode})

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

            self.state = "RUNNING"
            await self._autonomous_drive_loop()

        except asyncio.CancelledError:
            self.state = "STOPPED"
            await self.emit_event("DECIDE", "Application stopped.", "Application stop ho gayi.")
        except AgentRunError as exc:
            self.state = "FAILED"
            self.last_error = str(exc)
            await self.emit_event(
                "DECIDE",
                str(exc),
                "Is portal ko verify nahi kar paye. Official notification link check karein.",
                force_screenshot=True,
            )
        except Exception:
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
            if self.state != "AWAITING_PAYMENT":
                await self._cleanup()
            self.run_store.finish(
                self.run_id or "unknown",
                self.state,
                {"error": self.last_error, "target_url": self.target_url},
            )

    async def stop(self):
        self.is_running = False
        self.state = "STOPPED"
        if self.active_event_future and not self.active_event_future.done():
            self.active_event_future.set_result({"action": "STOPPED"})
        self.active_event_future = None
        await self._cleanup()
        if self.run_id:
            self.run_store.finish(self.run_id, "STOPPED")
        await self.emit_event("DECIDE", "Application stopped.", "Application stop ho gayi.")

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

    async def _cleanup(self):
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
        if not self.page:
            raise AgentRunError("The browser page is no longer available.")
        try:
            return await self.page.evaluate(DOMScanner.DETECTION_JS)
        except Exception as exc:
            raise AgentRunError("The page is still loading. Please wait a moment and try again.") from exc

    async def _autonomous_drive_loop(self):
        while self.is_running:
            if self._is_paused:
                self.state = "PAUSED"
                await asyncio.sleep(0.4)
                continue
            self.state = "RUNNING"

            dom = await self._scan_dom()
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
            await self._handle_otp()
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
            key = (gateway.get("type"), gateway.get("text"))
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
                {"id": g.get("id"), "text": g.get("text"), "type": g.get("type")}
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
        selected_text = response.get("text")
        selected = None
        for gateway in unique:
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
        if not await self._safe_click(gateway):
            raise AgentRunError("The portal button could not be clicked. Please try again.")
        try:
            await self.page.wait_for_load_state("domcontentloaded", timeout=12000)
        except Exception:
            pass
        await self.page.wait_for_timeout(500)

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
                    "timestamp": record.get("timestamp"),
                }
            )
        return list(reversed(public))

    def _record_fill(self, item: Dict[str, Any], sem_key: str, value: str, method: str):
        key = item.get("id") or item.get("name") or sem_key
        display = field_registry.mask_value(sem_key, value) if sem_key != "photo_upload" and sem_key != "signature_upload" else os.path.basename(str(value))
        record = {
            "field_label": item.get("label") or sem_key,
            "vault_key": sem_key,
            "injected_value": display,
            "actual_value": str(value),
            "field_id": item.get("id") or "",
            "field_name": item.get("name") or "",
            "field_type": item.get("type") or "text",
            "method": method,
            "timestamp": datetime.datetime.now().strftime("%H:%M:%S"),
            "status": "FILLED",
            "_key": key,
        }
        for index, existing in enumerate(self.filled_audit):
            if existing.get("_key") == key:
                self.filled_audit[index] = record
                return
        self.filled_audit.append(record)

    async def _fill_form(self, dom: Dict[str, Any]) -> int:
        filled = 0
        vault = self.vault_mgr.vault
        for item in dom.get("inputs") or []:
            if not self.is_running:
                break
            if (item.get("type") or "").lower() in {"submit", "button", "reset", "image"}:
                continue

            sem_key, _is_verify = DOMScanner.classify_field(item)
            if not sem_key:
                continue

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

            try:
                result = await self.page.evaluate(DOMScanner.INJECTION_JS, [item, str(value)])
            except Exception:
                result = {"success": False, "reason": "The field could not be reached."}

            if result.get("success"):
                filled += 1
                self._record_fill(item, sem_key, str(value), result.get("method", "input"))
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
            "description": f"This portal asks for {label}. Add it once and FormPilot will reuse it in future applications.",
        }
        self.active_gate = gate
        self.state = "WAITING_FOR_USER"
        await self.emit_event(
            "DECIDE",
            f"Waiting for: {label}",
            "Aapke input ka intezaar hai.",
            gate,
            force_screenshot=True,
        )
        response = await self._wait_for_user_response()
        self.active_gate = None
        self.state = "RUNNING" if self.is_running else self.state
        if response.get("action") in {"STOPPED", "TIMEOUT", "DISMISS"}:
            if response.get("action") == "TIMEOUT":
                self.is_running = False
            return ""
        value = str(response.get("value") or response.get("text") or "").strip()
        if value:
            try:
                self.vault_mgr.set_semantic_field(sem_key, value)
            except Exception:
                self.vault_mgr.add_custom_field(sem_key, value)
        return value

    async def _handle_upload(self, item: Dict[str, Any], sem_key: str) -> bool:
        try:
            BiometricCompressor.generate_sample_assets()
        except Exception:
            pass

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
        if not candidate or not candidate.exists():
            candidate = fallback
        if not candidate or not candidate.exists():
            await self.emit_event(
                "SENSE",
                f"Please add a file for: {item.get('label') or sem_key}",
                f"{item.get('label') or sem_key} ke liye file add karein.",
            )
            return False

        try:
            locator = self.page.locator(f"#{item.get('id')}") if item.get("id") else self.page.locator(f"[name='{item.get('name')}']")
            if await locator.count() == 0:
                locator = self.page.locator("input[type='file']").first
            await locator.set_input_files(str(candidate), timeout=10000)
        except Exception:
            await self.emit_event(
                "SENSE",
                f"Could not upload {item.get('label') or sem_key}.",
                f"{item.get('label') or sem_key} upload nahi ho paya.",
            )
            return False

        self._record_fill(item, sem_key, str(candidate), "file")
        await self.emit_event(
            "ACT",
            f"Uploaded: {item.get('label') or sem_key}",
            f"{item.get('label') or sem_key} upload ho gaya.",
        )
        return True

    # ---------------------------------------------------------------- security checks

    async def _handle_otp(self):
        if self._otp_cleared or not self.page:
            return
        selector = "#btn-send-otp, button:has-text('Send OTP'), button:has-text('Get OTP')"
        try:
            button = self.page.locator(selector).first
            if await button.count() == 0 or not await button.is_visible():
                return
        except Exception:
            return

        await self.emit_event(
            "THINK",
            "The portal needs to verify your phone number.",
            "Portal phone number verify karna chahta hai.",
        )
        try:
            await button.click(timeout=8000)
        except Exception:
            return
        await self.page.wait_for_timeout(900)

        config = self.tinyfish_mgr.config
        gate = {
            "gate_type": "OTP_RELAY",
            "title": "Enter the verification code",
            "hindi_title": "Verification code enter karein",
            "hindi_audio_text": "Aapke phone par code bheja gaya hai. Woh code yahan enter karein.",
            "description": "We sent a 6-digit code to the phone number saved in your details. FormPilot never stores this code.",
            "recipient": self._masked_phone(self.vault_mgr.vault.mobile),
            "ntfy_topic": config.ntfy_topic,
            "ntfy_url": f"https://ntfy.sh/{config.ntfy_topic}",
        }
        if settings.DEMO_MODE:
            gate["demo_otp"] = settings.DEMO_OTP
            gate["description"] += f" Demo mode code: {settings.DEMO_OTP}."
        self.active_gate = gate
        self.state = "WAITING_FOR_USER"
        await self.emit_event(
            "DECIDE",
            "Waiting for the verification code.",
            "Verification code ka intezaar hai.",
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
        captcha = captchas[0]
        signature = f"{dom.get('url')}|{captcha.get('id')}|{captcha.get('tagName')}"
        if signature == self._captcha_signature:
            return

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
            "description": "Enter the characters shown in the image. This check is never solved automatically.",
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
            "description": "The portal did not accept the current details. Review the message, edit anything that is wrong, then continue.",
            "suggested_actions": ["Review the details", "Try again", "Stop and open the portal myself"],
        }
        self.active_gate = gate
        self.state = "WAITING_FOR_USER"
        await self.emit_event(
            "DECIDE",
            "Waiting for you to review the portal message.",
            "Portal message review karne ka intezaar hai.",
            gate,
            force_screenshot=True,
        )
        response = await self._wait_for_user_response()
        self.active_gate = None
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
            "description": "Please check the details on the form. Continue only if everything is correct.",
            "fields_filled": self._public_audit(),
        }
        self.active_gate = gate
        self.state = "WAITING_FOR_USER"
        await self.emit_event(
            "DECIDE",
            f"Section {step} is ready for your review.",
            f"Section {step} review ke liye ready hai.",
            gate,
            force_screenshot=True,
        )
        response = await self._wait_for_user_response()
        self.active_gate = None
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
        if not self.page:
            return False
        try:
            locator = None
            if button.get("id"):
                locator = self.page.locator(f"#{button['id']}").first
            if locator is None or await locator.count() == 0:
                text = str(button.get("text") or "").strip()
                if text:
                    locator = self.page.get_by_role("button", name=text, exact=True).first
                    if await locator.count() == 0:
                        locator = self.page.locator(f"text={text}").first
            if locator is None or await locator.count() == 0:
                return False
            await locator.scroll_into_view_if_needed(timeout=5000)
            await locator.click(timeout=8000)
            return True
        except Exception:
            return False

    async def _wait_for_user_response(self) -> Dict[str, Any]:
        if self._pending_user_response is not None:
            result = self._pending_user_response
            self._pending_user_response = None
            return result
        loop = asyncio.get_running_loop()
        self.active_event_future = loop.create_future()
        try:
            return await asyncio.wait_for(self.active_event_future, timeout=settings.GATE_TIMEOUT_SECONDS)
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

