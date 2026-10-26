"""Transport-level tests for the interactive CDP live browser.

No real Chromium is needed here: the fake page/CDP pair checks that control
gating, input forwarding, frame broadcasting and URL safety work independently
of any portal.
"""

from __future__ import annotations

import asyncio

from backend.core.live_browser import (
    LiveBrowserSession,
    LiveSessionRegistry,
    decode_frame_data_url,
)


class FakeCDP:
    def __init__(self):
        self.sent = []
        self.handlers = {}

    def on(self, name, callback):
        self.handlers[name] = callback

    async def send(self, method, params=None):
        self.sent.append((method, params or {}))
        return {}

    async def detach(self):
        self.sent.append(("detach", {}))


class FakeContext:
    def __init__(self):
        self.cdp = FakeCDP()

    async def new_cdp_session(self, page):
        return self.cdp


class FakePage:
    def __init__(self):
        self.context = FakeContext()
        self.viewport_size = {"width": 1280, "height": 800}
        self.url = "https://example.gov.in/apply?token=abc"
        self.handlers = {}

    def on(self, name, callback):
        self.handlers[name] = callback

    async def title(self):
        return "Recruitment Application"

    def is_closed(self):
        return False

    async def goto(self, url, wait_until="domcontentloaded", timeout=45000):
        self.url = url

    async def reload(self, wait_until="domcontentloaded", timeout=45000):
        return None

    async def go_back(self, wait_until="domcontentloaded", timeout=45000):
        return None

    async def go_forward(self, wait_until="domcontentloaded", timeout=45000):
        return None

    async def set_viewport_size(self, size):
        self.viewport_size = size


def run(coro):
    return asyncio.run(coro)


def test_public_info_never_echoes_query_tokens():
    async def scenario():
        page = FakePage()
        session = LiveBrowserSession(page, run_id="run-1", run_mode="fill")
        await session.start()
        info = session.public_info()

        assert info["interactive"] is True
        assert info["control_enabled"] is False
        assert info["url"] == "https://example.gov.in/apply"
        assert "access_token=" in info["ws_path"]
        assert "token=abc" not in info["ws_path"]
        assert "token=abc" not in str(info)
        assert info["viewport"] == {"width": 1280, "height": 800}
        await session.stop()

    run(scenario())


def test_frames_are_acknowledged_and_broadcast():
    async def scenario():
        page = FakePage()
        session = LiveBrowserSession(page)
        await session.start()
        queue = session.subscribe()

        await session._handle_frame({"data": "YWJj", "metadata": {"x": 1}, "sessionId": 7})
        message = await asyncio.wait_for(queue.get(), timeout=1)

        assert message["type"] == "frame"
        assert message["data"] == "YWJj"
        assert message["metadata"] == {"x": 1}
        assert message["frames_sent"] == 1
        assert session.frames_sent == 1
        assert decode_frame_data_url(session.latest_screenshot()) == b"abc"
        assert ("Page.screencastFrameAck", {"sessionId": 7}) in page.context.cdp.sent
        await session.stop()

    run(scenario())


def test_input_is_blocked_while_the_agent_drives():
    async def scenario():
        page = FakePage()
        session = LiveBrowserSession(page, run_mode="fill")
        await session.start()
        cdp = page.context.cdp

        click = await session.dispatch({"type": "mouse", "event": "down", "x": 10, "y": 20})
        key = await session.dispatch({"type": "key", "event": "down", "key": "a", "code": "KeyA"})
        text = await session.dispatch({"type": "text", "text": "Aman"})

        assert click["ok"] is False
        assert click["control_enabled"] is False
        assert key["ok"] is False
        assert text["ok"] is False
        assert not any(method == "Input.dispatchMouseEvent" for method, _ in cdp.sent)

        # Scrolling is safe and remains available even while the agent drives.
        wheel = await session.dispatch({"type": "wheel", "x": 10, "y": 20, "deltaY": 300})
        assert wheel["ok"] is True
        assert any(method == "Input.dispatchMouseEvent" and params["type"] == "mouseWheel" for method, params in cdp.sent)
        await session.stop()

    run(scenario())


def test_human_takeover_forwards_mouse_keys_paste_and_navigation():
    async def scenario():
        page = FakePage()
        session = LiveBrowserSession(page, run_mode="fill")
        await session.start()
        queue = session.subscribe()
        session.set_allow_control(True, "Solve the security check.")
        control = await asyncio.wait_for(queue.get(), timeout=1)
        assert control["type"] == "control"
        assert control["enabled"] is True

        click = await session.dispatch(
            {"type": "mouse", "event": "down", "x": 100, "y": 200, "button": "left"}
        )
        assert click["ok"] is True
        method, params = page.context.cdp.sent[-1]
        assert method == "Input.dispatchMouseEvent"
        assert params["type"] == "mousePressed"
        assert params["x"] == 100
        assert params["y"] == 200

        await session.dispatch({"type": "mouse", "event": "up", "x": 100, "y": 200})
        assert page.context.cdp.sent[-1][1]["type"] == "mouseReleased"

        await session.dispatch({"type": "key", "event": "down", "key": "Enter", "code": "Enter"})
        assert page.context.cdp.sent[-1][0] == "Input.dispatchKeyEvent"
        assert page.context.cdp.sent[-1][1]["type"] == "rawKeyDown"
        await session.dispatch({"type": "key", "event": "up", "key": "Enter", "code": "Enter"})
        assert page.context.cdp.sent[-1][1]["type"] == "keyUp"

        await session.dispatch({"type": "key", "event": "down", "key": "क", "code": "KeyK"})
        assert page.context.cdp.sent[-1] == ("Input.insertText", {"text": "क"})

        await session.dispatch({"type": "paste", "text": "Aman Kumar"})
        assert page.context.cdp.sent[-1] == ("Input.insertText", {"text": "Aman Kumar"})

        rejected = await session.dispatch({"type": "navigate", "url": "javascript:alert(1)"})
        assert rejected["ok"] is False
        assert "http(s)" in rejected["error"]

        navigated = await session.dispatch({"type": "navigate", "url": "https://example.gov.in/login"})
        assert navigated["ok"] is True
        assert page.url == "https://example.gov.in/login"

        resized = await session.dispatch({"type": "resize", "width": 900, "height": 700})
        assert resized["ok"] is True
        assert page.viewport_size == {"width": 900, "height": 700}
        assert session.public_info()["viewport"] == {"width": 900, "height": 700}
        await session.stop()

    run(scenario())


def test_inspect_mode_starts_with_control_and_closes_cleanly():
    async def scenario():
        page = FakePage()
        session = LiveBrowserSession(page, run_mode="inspect")
        await session.start()
        assert session.public_info()["control_enabled"] is True

        click = await session.dispatch({"type": "mouse", "event": "down", "x": 5, "y": 6})
        assert click["ok"] is True

        await session.stop()
        assert session.closed is True
        assert ("Page.stopScreencast", {}) in page.context.cdp.sent
        assert ("detach", {}) in page.context.cdp.sent

    run(scenario())


def test_live_session_registry_removes_closed_sessions():
    async def scenario():
        registry = LiveSessionRegistry()
        first = LiveBrowserSession(FakePage(), run_mode="inspect")
        await first.start()
        registry.add(first)

        assert registry.get(first.session_id) is first
        assert len(registry.active()) == 1
        assert registry.all_sessions() == [first]

        await first.stop()
        assert registry.get(first.session_id) is None
        assert registry.active() == []
        registry.remove(first)
        assert registry.all_sessions() == []

    run(scenario())


def test_frame_decoder_accepts_plain_base64_and_data_urls():
    assert decode_frame_data_url("YWJj") == b"abc"
    assert decode_frame_data_url("data:image/jpeg;base64,YWJj") == b"abc"
    assert decode_frame_data_url("") == b""
