"""Real-DOM upload routing tests.

These tests use a local HTML fixture, not a real portal.  They verify that a
file is attached to the field the user asked for, that a mismatched upload is
refused instead of silently going to the first file input, and that the
scanner can verify ``hasFile`` afterwards.
"""

from __future__ import annotations

import asyncio

import pytest

from backend.core.dom_scanner import DOMScanner
from backend.core.orchestrator import FormPilotOrchestrator

HTML = """
<html><body><form>
  <label for="photo_file">Recent Passport Photograph</label>
  <input type="file" id="photo_file" name="photo_file" accept=".jpg,.jpeg">

  <label for="sig_file">Candidate Digital Signature</label>
  <input type="file" id="sig_file" name="sig_file" accept=".jpg,.jpeg">
</form></body></html>
"""


def _jpeg(path):
    from PIL import Image

    Image.new("RGB", (120, 160), (240, 240, 240)).save(path, "JPEG", quality=85)
    return path


def test_upload_targets_the_matching_field_and_verifies_has_file(tmp_path):
    async_api = pytest.importorskip("playwright.async_api")
    photo = _jpeg(tmp_path / "photo.jpg")
    signature = _jpeg(tmp_path / "signature.jpg")

    async def scenario():
        playwright = await async_api.async_playwright().start()
        browser = None
        try:
            try:
                browser = await playwright.chromium.launch(headless=True)
            except Exception as exc:  # pragma: no cover - environment dependent
                pytest.skip(f"Chromium unavailable: {exc}")
            page = await browser.new_page()
            await page.set_content(HTML)

            orchestrator = FormPilotOrchestrator()
            orchestrator.page = page

            photo_result = await orchestrator.attach_upload(str(photo), "photo_upload")
            assert photo_result["success"] is True
            assert await page.locator("#photo_file").evaluate("el => el.files.length") == 1
            assert await page.locator("#sig_file").evaluate("el => el.files.length") == 0

            signature_result = await orchestrator.attach_upload(
                str(signature), "signature_upload"
            )
            assert signature_result["success"] is True
            assert await page.locator("#sig_file").evaluate("el => el.files.length") == 1

            dom = await page.evaluate(DOMScanner.DETECTION_JS)
            files = {entry["id"]: entry for entry in dom["fileInputs"]}
            assert files["photo_file"]["hasFile"] is True
            assert files["sig_file"]["hasFile"] is True

            # An unknown key must not fall through to the first file input.
            mismatch = await orchestrator.attach_upload(str(photo), "unrelated_document")
            assert mismatch["success"] is False
            assert "more than one file field" in mismatch["message"].lower()
            assert await page.locator("#photo_file").evaluate("el => el.files.length") == 1
        finally:
            if browser is not None:
                await browser.close()
            await playwright.stop()

    asyncio.run(scenario())


def test_upload_with_a_single_file_field_uses_it(tmp_path):
    async_api = pytest.importorskip("playwright.async_api")
    photo = _jpeg(tmp_path / "photo.jpg")

    async def scenario():
        playwright = await async_api.async_playwright().start()
        browser = None
        try:
            try:
                browser = await playwright.chromium.launch(headless=True)
            except Exception as exc:  # pragma: no cover - environment dependent
                pytest.skip(f"Chromium unavailable: {exc}")
            page = await browser.new_page()
            await page.set_content(
                """
                <html><body><form>
                  <label for="document">Supporting document</label>
                  <input type="file" id="document" name="document">
                </form></body></html>
                """
            )
            orchestrator = FormPilotOrchestrator()
            orchestrator.page = page

            result = await orchestrator.attach_upload(str(photo), "supporting_document")
            assert result["success"] is True
            assert await page.locator("#document").evaluate("el => el.files.length") == 1
        finally:
            if browser is not None:
                await browser.close()
            await playwright.stop()

    asyncio.run(scenario())
