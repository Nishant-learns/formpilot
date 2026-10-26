"""Interactive live browser over CDP.

The preview is not a screenshot stream.  It is the *same* Chromium page the
agent is driving, streamed frame-by-frame through ``Page.startScreencast`` and
controlled by forwarding mouse, wheel and keyboard input back through CDP.

This is deliberately a small transport layer:

* frames flow one way (browser -> queue -> WebSocket)
* input flows the other way (WebSocket -> CDP)
* the agent's policy decides *when* the human may take control

There is no CAPTCHA solver and no token injection here.  A human solves
human-verification challenges in the real page.
"""

from __future__ import annotations

import asyncio
import base64
import datetime
import json
import re
import secrets
import time
import traceback
from typing import Any, Dict, Optional, Set
from urllib.parse import urlsplit

from playwright.async_api import Page


_SAFE_SCHEMES = {"http", "https"}
_KEY_CODES = {
    "Enter": 13,
    "Tab": 9,
    "Backspace": 8,
    "Escape": 27,
    "Esc": 27,
    "Delete": 46,
    "ArrowLeft": 37,
    "ArrowUp": 38,
    "ArrowRight": 39,
    "ArrowDown": 40,
    "Home": 36,
    "End": 35,
    "PageUp": 33,
    "PageDown": 34,
    " ": 32,
    "Space": 32,
    "Shift": 16,
    "Control": 17,
    "Alt": 18,
    "Meta": 91,
}
_SPECIAL_KEYS = {
    "Enter",
    "Tab",
    "Backspace",
    "Escape",
    "Esc",
    "Delete",
    "ArrowLeft",
    "ArrowUp",
    "ArrowRight",
    "ArrowDown",
    "Home",
    "End",
    "PageUp",
    "PageDown",
}
_MODIFIER_BITS = (("altKey", 1), ("ctrlKey", 2), ("metaKey", 4), ("shiftKey", 8))


def _safe_display_url(url: str) -> str:
    """Keep the route visible but never echo query strings that may hold tokens."""
    try:
        parts = urlsplit(str(url or ""))
        if not parts.scheme and not parts.netloc:
            return ""
        return f"{parts.scheme}://{parts.netloc}{parts.path}" + (f"#{parts.fragment}" if parts.fragment else "")
    except Exception:
        return ""


def _clamp(value: Any, low: float, high: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return low
    return max(low, min(high, number))


def _modifiers(message: Dict[str, Any]) -> int:
    bits = 0
    for name, bit in _MODIFIER_BITS:
        if message.get(name):
            bits |= bit
    return bits if bits else int(message.get("modifiers") or 0)


class LiveBrowserSession:
    """A browser page that a human can see and operate in real time."""

    def __init__(
        self,
        page: Page,
        *,
        run_id: str = "",
        mode: str = "local",
        run_mode: str = "fill",
    ):
        self.page = page
        self.run_id = run_id
        self.mode = mode
        self.run_mode = run_mode
        self.session_id = f"live-{secrets.token_hex(8)}"
        self.access_token = secrets.token_urlsafe(24)
        self.created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

        self.cdp = None
        self._closed = False
        self._control_enabled = run_mode == "inspect"
        self._control_reason = (
            "Inspect mode: the browser is yours."
            if run_mode == "inspect"
            else "The agent is driving. You can take over when it pauses or asks for help."
        )
        self._subscribers: Set[asyncio.Queue] = set()
        self._tasks: Set[asyncio.Task] = set()
        self._latest_frame: str = ""
        self._latest_metadata: Dict[str, Any] = {}
        self._viewport = {"width": 1280, "height": 800}
        self._url = _safe_display_url(getattr(page, "url", "") or "")
        self._title = ""
        self._key_modes: Dict[str, str] = {}
        self._last_click: Dict[str, Any] = {}
        self.frames_sent = 0
        self.last_frame_at = 0.0

    # ------------------------------------------------------------------ lifecycle

    async def start(self) -> None:
        try:
            self._viewport = await self._read_viewport()
            self.cdp = await self.page.context.new_cdp_session(self.page)
            try:
                await self.cdp.send("Page.enable")
            except Exception:
                pass
            self.cdp.on("Page.screencastFrame", self._on_screencast_frame)
            self.page.on("framenavigated", self._on_frame_navigated)
            self.page.on("domcontentloaded", self._on_dom_content_loaded)
            await self._start_screencast()
            await self._publish_page()
        except Exception:
            traceback.print_exc()
            self._closed = True
            raise

    async def _start_screencast(self) -> None:
        if not self.cdp:
            return
        width = int(self._viewport.get("width") or 1280)
        height = int(self._viewport.get("height") or 800)
        params = {
            "format": "jpeg",
            "quality": 70,
            "maxWidth": max(640, min(1920, width)),
            "maxHeight": max(480, min(1200, height)),
            "everyNthFrame": 1,
        }
        try:
            await self.cdp.send("Page.startScreencast", params)
        except Exception:
            # Older Chromium builds may not accept maxWidth/maxHeight.
            await self.cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 65})

    async def stop(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._broadcast({"type": "closed", "message": "The live browser session ended."})
        for task in list(self._tasks):
            task.cancel()
        self._tasks.clear()
        try:
            if self.cdp:
                await self.cdp.send("Page.stopScreencast")
        except Exception:
            pass
        try:
            if self.cdp:
                await self.cdp.detach()
        except Exception:
            pass
        self.cdp = None
        for queue in list(self._subscribers):
            try:
                queue.put_nowait({"type": "closed", "message": "The live browser session ended."})
            except Exception:
                pass
        self._subscribers.clear()

    async def _read_viewport(self) -> Dict[str, int]:
        size = None
        try:
            size = self.page.viewport_size
        except Exception:
            size = None
        if not size:
            try:
                size = await self.page.evaluate(
                    "() => ({width: window.innerWidth, height: window.innerHeight})"
                )
            except Exception:
                size = None
        return {
            "width": int((size or {}).get("width") or 1280),
            "height": int((size or {}).get("height") or 800),
        }

    # ------------------------------------------------------------------ public info

    def public_info(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "run_id": self.run_id,
            "ws_path": f"/ws/live?session_id={self.session_id}&access_token={self.access_token}",
            "interactive": True,
            "control_enabled": self._control_enabled,
            "control_reason": self._control_reason,
            "url": self._url,
            "title": self._title,
            "viewport": dict(self._viewport),
            "mode": self.mode,
            "run_mode": self.run_mode,
            "created_at": self.created_at,
            "frames_sent": self.frames_sent,
        }

    @property
    def closed(self) -> bool:
        return self._closed

    def latest_screenshot(self) -> str:
        if not self._latest_frame:
            return ""
        return f"data:image/jpeg;base64,{self._latest_frame}"

    def latest_frame_base64(self) -> str:
        return self._latest_frame

    def set_allow_control(self, enabled: bool, reason: str = "") -> None:
        enabled = bool(enabled)
        if enabled == self._control_enabled and reason == self._control_reason:
            return
        self._control_enabled = enabled
        if reason:
            self._control_reason = reason
        self._broadcast(
            {
                "type": "control",
                "enabled": self._control_enabled,
                "reason": self._control_reason,
            }
        )

    # ------------------------------------------------------------------ subscribers

    def subscribe(self, maxsize: int = 8) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    def _broadcast(self, message: Dict[str, Any]) -> None:
        for queue in list(self._subscribers):
            try:
                if queue.full():
                    try:
                        queue.get_nowait()
                    except Exception:
                        pass
                queue.put_nowait(message)
            except Exception:
                self._subscribers.discard(queue)

    def _spawn(self, coro) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    # ------------------------------------------------------------------ frames

    def _on_screencast_frame(self, event: Dict[str, Any]) -> None:
        if self._closed:
            return
        try:
            self._spawn(self._handle_frame(event))
        except Exception:
            pass

    async def _handle_frame(self, event: Dict[str, Any]) -> None:
        session_id = event.get("sessionId")
        try:
            if self.cdp and session_id is not None:
                await self.cdp.send("Page.screencastFrameAck", {"sessionId": session_id})
        except Exception:
            pass

        data = event.get("data")
        if not data:
            return
        metadata = event.get("metadata") or {}
        self._latest_frame = data
        self._latest_metadata = metadata
        self.frames_sent += 1
        self.last_frame_at = time.time()
        self._broadcast(
            {
                "type": "frame",
                "data": data,
                "metadata": metadata,
                "viewport": dict(self._viewport),
                "url": self._url,
                "frames_sent": self.frames_sent,
            }
        )

    def _on_frame_navigated(self, frame) -> None:
        try:
            if frame != self.page.main_frame:
                return
            self._url = _safe_display_url(frame.url)
            self._spawn(self._publish_page())
        except Exception:
            pass

    def _on_dom_content_loaded(self, _page) -> None:
        self._spawn(self._publish_page())

    async def _publish_page(self) -> None:
        try:
            title = await asyncio.wait_for(self.page.title(), timeout=3)
        except Exception:
            title = self._title
        self._title = str(title or "")[:180]
        try:
            self._url = _safe_display_url(self.page.url)
        except Exception:
            pass
        self._broadcast(
            {
                "type": "page",
                "url": self._url,
                "title": self._title,
                "viewport": dict(self._viewport),
            }
        )

    # ------------------------------------------------------------------ input

    async def dispatch(self, message: Dict[str, Any]) -> Dict[str, Any]:
        if self._closed or not self.cdp:
            return {"ok": False, "error": "The live browser is not connected."}
        kind = str(message.get("type") or "").lower()
        if kind == "ping":
            return {"ok": True, "type": "pong"}
        if kind == "control_request":
            if not self._control_enabled:
                return {
                    "ok": False,
                    "error": self._control_reason,
                    "control_enabled": False,
                }
            self._broadcast(
                {
                    "type": "control",
                    "enabled": True,
                    "reason": "You have control of the live browser.",
                }
            )
            return {"ok": True, "control_enabled": True}
        if kind == "wheel":
            # Scrolling is always safe and helps the user inspect a long form.
            return await self._dispatch_wheel(message)
        if kind == "mouse":
            event = str(message.get("event") or "move").lower()
            if event != "move" and not self._control_enabled:
                return {"ok": False, "error": self._control_reason, "control_enabled": False}
            return await self._dispatch_mouse(message)
        if kind in {"key", "text", "paste"}:
            if not self._control_enabled:
                return {"ok": False, "error": self._control_reason, "control_enabled": False}
            if kind in {"text", "paste"}:
                return await self._dispatch_text(message)
            return await self._dispatch_key(message)
        if kind in {"navigate", "reload", "back", "forward", "resize"}:
            if not self._control_enabled:
                return {"ok": False, "error": self._control_reason, "control_enabled": False}
            return await self._dispatch_navigation(kind, message)
        return {"ok": False, "error": f"Unknown input type: {kind}"}

    async def _dispatch_mouse(self, message: Dict[str, Any]) -> Dict[str, Any]:
        x = _clamp(message.get("x", 0), 0, self._viewport["width"] - 1)
        y = _clamp(message.get("y", 0), 0, self._viewport["height"] - 1)
        event = str(message.get("event") or "move").lower()
        button = str(message.get("button") or "left").lower()
        if button not in {"left", "right", "middle", "none"}:
            button = "left"
        modifiers = _modifiers(message)
        buttons = int(message.get("buttons") or 0)
        if event == "move":
            cdp_type = "mouseMoved"
            if "buttons" not in message:
                buttons = 1 if self._last_click.get("down") else 0
        elif event == "down":
            cdp_type = "mousePressed"
            buttons |= {"left": 1, "right": 2, "middle": 4}.get(button, 1)
            self._last_click["down"] = True
            self._last_click["x"] = x
            self._last_click["y"] = y
        elif event == "up":
            cdp_type = "mouseReleased"
            buttons &= ~{"left": 1, "right": 2, "middle": 4}.get(button, 1)
            self._last_click["down"] = False
        else:
            return {"ok": False, "error": "Unknown mouse event."}

        click_count = 1
        if event == "down":
            now = time.monotonic()
            previous = self._last_click.get("at", 0)
            close = abs(x - self._last_click.get("last_x", -999)) < 6 and abs(y - self._last_click.get("last_y", -999)) < 6
            if close and now - previous < 0.45:
                click_count = 2
            self._last_click["at"] = now
            self._last_click["last_x"] = x
            self._last_click["last_y"] = y

        params = {
            "type": cdp_type,
            "x": x,
            "y": y,
            "button": button if button != "none" else "none",
            "buttons": buttons,
            "clickCount": int(message.get("clickCount") or click_count),
            "modifiers": modifiers,
            "pointerType": "mouse",
        }
        try:
            await self.cdp.send("Input.dispatchMouseEvent", params)
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    async def _dispatch_wheel(self, message: Dict[str, Any]) -> Dict[str, Any]:
        x = _clamp(message.get("x", 0), 0, self._viewport["width"] - 1)
        y = _clamp(message.get("y", 0), 0, self._viewport["height"] - 1)
        params = {
            "type": "mouseWheel",
            "x": x,
            "y": y,
            "deltaX": _clamp(message.get("deltaX", 0), -2000, 2000),
            "deltaY": _clamp(message.get("deltaY", 0), -2000, 2000),
            "modifiers": _modifiers(message),
            "pointerType": "mouse",
        }
        try:
            await self.cdp.send("Input.dispatchMouseEvent", params)
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    async def _dispatch_text(self, message: Dict[str, Any]) -> Dict[str, Any]:
        text = str(message.get("text") or "")
        if not text:
            return {"ok": False, "error": "No text supplied."}
        if len(text) > 4000:
            return {"ok": False, "error": "Paste is too large."}
        try:
            await self.cdp.send("Input.insertText", {"text": text})
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    async def _dispatch_key(self, message: Dict[str, Any]) -> Dict[str, Any]:
        event = str(message.get("event") or "down").lower()
        key = str(message.get("key") or "")
        code = str(message.get("code") or key)
        modifiers = _modifiers(message)
        if not key and not code:
            return {"ok": False, "error": "No key supplied."}
        mode_key = f"{key}:{code}"
        is_special = key in _SPECIAL_KEYS or key in _KEY_CODES or len(key) > 1

        if event == "up":
            if self._key_modes.get(mode_key) == "insert":
                self._key_modes.pop(mode_key, None)
                return {"ok": True}
            params = self._key_params(event="keyUp", key=key, code=code, modifiers=modifiers)
            try:
                await self.cdp.send("Input.dispatchKeyEvent", params)
                return {"ok": True}
            except Exception as exc:
                return {"ok": False, "error": str(exc)}

        text = message.get("text")
        if text is None and len(key) == 1 and not (modifiers & (1 | 2 | 4)):
            text = key
        text = str(text or "")

        # Non-ASCII input (Hindi, emoji, etc.) is inserted as text; Chrome's
        # key event path does not handle it reliably.
        if text and any(ord(char) > 127 for char in text):
            try:
                await self.cdp.send("Input.insertText", {"text": text})
                self._key_modes[mode_key] = "insert"
                return {"ok": True}
            except Exception as exc:
                return {"ok": False, "error": str(exc)}

        if text and not is_special and not (modifiers & (1 | 2 | 4)):
            params = self._key_params(
                event="keyDown",
                key=key,
                code=code,
                modifiers=modifiers,
                text=text,
            )
        else:
            params = self._key_params(
                event="rawKeyDown",
                key=key,
                code=code,
                modifiers=modifiers,
            )
        try:
            await self.cdp.send("Input.dispatchKeyEvent", params)
            self._key_modes[mode_key] = "dispatch"
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _key_params(
        self,
        *,
        event: str,
        key: str,
        code: str,
        modifiers: int,
        text: str = "",
    ) -> Dict[str, Any]:
        vk = _KEY_CODES.get(key)
        if vk is None and len(key) == 1:
            vk = ord(key.upper())
        if vk is None:
            vk = 0
        params: Dict[str, Any] = {
            "type": event,
            "key": key,
            "code": code,
            "windowsVirtualKeyCode": int(vk),
            "nativeVirtualKeyCode": int(vk),
            "modifiers": modifiers,
        }
        if text:
            params["text"] = text
            params["unmodifiedText"] = text
        if key == "Enter":
            params["text"] = "\r"
            params["unmodifiedText"] = "\r"
        return params

    async def _dispatch_navigation(self, kind: str, message: Dict[str, Any]) -> Dict[str, Any]:
        try:
            if kind == "reload":
                await self.page.reload(wait_until="domcontentloaded", timeout=45000)
            elif kind == "back":
                await self.page.go_back(wait_until="domcontentloaded", timeout=45000)
            elif kind == "forward":
                await self.page.go_forward(wait_until="domcontentloaded", timeout=45000)
            elif kind == "navigate":
                url = str(message.get("url") or "").strip()
                parts = urlsplit(url)
                if parts.scheme not in _SAFE_SCHEMES or not parts.netloc:
                    return {"ok": False, "error": "Only http(s) URLs can be opened in the live browser."}
                await self.page.goto(url, wait_until="domcontentloaded", timeout=45000)
            elif kind == "resize":
                width = int(_clamp(message.get("width", 1280), 800, 1920))
                height = int(_clamp(message.get("height", 800), 600, 1200))
                await self.page.set_viewport_size({"width": width, "height": height})
                self._viewport = {"width": width, "height": height}
                try:
                    await self.cdp.send("Page.stopScreencast")
                except Exception:
                    pass
                await self._start_screencast()
            await asyncio.sleep(0.15)
            await self._publish_page()
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}


class LiveSessionRegistry:
    """Process-local registry of live browser sessions."""

    def __init__(self) -> None:
        self._sessions: Dict[str, LiveBrowserSession] = {}

    def add(self, session: LiveBrowserSession) -> None:
        self._sessions[session.session_id] = session

    def get(self, session_id: str) -> Optional[LiveBrowserSession]:
        session = self._sessions.get(session_id or "")
        if session and session.closed:
            self._sessions.pop(session_id, None)
            return None
        return session

    def remove(self, session: Optional[LiveBrowserSession]) -> None:
        if not session:
            return
        self._sessions.pop(session.session_id, None)

    def active(self) -> list[Dict[str, Any]]:
        return [session.public_info() for session in self._sessions.values() if not session.closed]

    def all_sessions(self) -> list[LiveBrowserSession]:
        return [session for session in self._sessions.values() if not session.closed]


live_sessions = LiveSessionRegistry()


def decode_frame_data_url(data_url: str) -> bytes:
    """Small helper used by tests and fallback screenshot paths."""
    if not data_url:
        return b""
    if "," in data_url:
        data_url = data_url.split(",", 1)[1]
    return base64.b64decode(data_url, validate=False)
