"""Small async-browser harness for blueprint and resolver tests."""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Optional, TypeVar

import pytest

T = TypeVar("T")


def run_with_page(
    scenario: Callable[[Any], Awaitable[T]],
    *,
    html: Optional[str] = None,
    url: Optional[str] = None,
) -> T:
    """Run ``scenario(page)`` in Chromium and always close the browser.

    Chromium is optional.  The test skips only when the driver or browser is
    unavailable, matching the existing real-DOM tests.
    """
    async_api = pytest.importorskip("playwright.async_api")

    async def runner() -> T:
        playwright = await async_api.async_playwright().start()
        browser = None
        try:
            try:
                browser = await playwright.chromium.launch(headless=True)
            except Exception as exc:  # pragma: no cover - environment dependent
                pytest.skip(f"Chromium unavailable: {exc}")
            page = await browser.new_page(viewport={"width": 1280, "height": 900})
            if url:
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            elif html is not None:
                await page.set_content(html)
            return await scenario(page)
        finally:
            if browser is not None:
                await browser.close()
            await playwright.stop()

    return asyncio.run(runner())
