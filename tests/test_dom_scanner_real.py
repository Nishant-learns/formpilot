"""Real-DOM classification tests for security challenges.

Chromium is optional here.  The test skips only when the browser cannot be
launched, so it still catches selector/classification regressions on machines
where Playwright is available.
"""

from __future__ import annotations

import pytest

from backend.core.dom_scanner import DOMScanner


def _scan(html: str):
    sync_api = pytest.importorskip("playwright.sync_api")
    try:
        playwright = sync_api.sync_playwright().start()
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"Playwright driver unavailable: {exc}")

    browser = None
    try:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Exception as exc:  # pragma: no cover - environment dependent
            pytest.skip(f"Chromium unavailable: {exc}")
        page = browser.new_page(viewport={"width": 900, "height": 600})
        page.set_content(html)
        return page.evaluate(DOMScanner.DETECTION_JS)
    finally:
        if browser is not None:
            browser.close()
        playwright.stop()


def test_canvas_with_nearby_text_input_is_a_text_captcha():
    dom = _scan(
        """
        <html><body><form>
          <label for="cap">Enter the security code</label>
          <input id="cap" name="captcha_code">
          <canvas id="captchaCanvas" width="120" height="40"></canvas>
        </form></body></html>
        """
    )

    kinds = {(element["tagName"], element["kind"]) for element in dom["captchaElements"]}
    assert ("canvas", "text") in kinds
    assert any(element["kind"] == "text" for element in dom["captchaElements"])


def test_captcha_wrapper_is_not_mistaken_for_the_challenge():
    dom = _scan(
        """
        <html><body><form>
          <label>Visual security verification</label>
          <div class="captcha-box">
            <canvas id="captchaCanvas" width="180" height="50"></canvas>
            <input id="captchaInput" name="captchaInput">
          </div>
        </form></body></html>
        """
    )

    kinds = {element["kind"] for element in dom["captchaElements"]}
    assert "unknown" not in kinds
    assert "text" in kinds
    assert all(element["tagName"] != "div" for element in dom["captchaElements"])


def test_cloudflare_style_widget_is_interactive_not_text():
    dom = _scan(
        """
        <html><body>
          <div class="g-recaptcha" data-sitekey="demo" style="width:300px;height:80px"></div>
        </body></html>
        """
    )

    assert any(element["kind"] == "interactive" for element in dom["captchaElements"])


def test_slider_challenge_is_classified_for_human_instructions():
    dom = _scan(
        """
        <html><body>
          <div id="slider-captcha" style="width:300px;height:60px">Slide to verify</div>
        </body></html>
        """
    )

    kinds = {element["kind"] for element in dom["captchaElements"]}
    assert "slider" in kinds


def test_text_only_security_code_field_is_detected():
    dom = _scan(
        """
        <html><body><form>
          <label for="code">Enter the security code</label>
          <input id="code" name="captcha_code">
        </form></body></html>
        """
    )

    assert any(
        element["tagName"] == "input" and element["kind"] == "text"
        for element in dom["captchaElements"]
    )


def test_file_and_live_photo_signals_are_reported():
    dom = _scan(
        """
        <html><body><form>
          <label for="photo">Live photo</label>
          <input id="photo" name="photo" type="file" accept="image/*" capture="user">
          <label for="otp">Enter OTP</label>
          <input id="otp" name="otp_code">
        </form></body></html>
        """
    )

    assert dom["livePhotoRequired"] is True
    assert dom["fileInputs"][0]["capture"] == "user"
    assert dom["fileInputs"][0]["hasFile"] is False
    assert dom["otpInputs"][0]["id"] == "otp"
