"""OTP relay behaviour for single-input and split-box verification pages."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from backend.core.orchestrator import FormPilotOrchestrator

from tests.browser_helpers import run_with_page


def _orchestrator(page):
    orchestrator = FormPilotOrchestrator()
    orchestrator.page = page
    orchestrator.target_url = page.url
    orchestrator.is_running = True
    orchestrator.state = "RUNNING"
    orchestrator.vault_mgr = SimpleNamespace(
        vault=SimpleNamespace(mobile="7654557189")
    )
    return orchestrator


def _split_otp_html(action="/site/validateotp", *, reject_first=False):
    boxes = "\n".join(
        '<input class="otp-box" name="SignupForm[mobile_otp][]" type="text" maxlength="1">'
        for _ in range(6)
    )
    reject = ""
    if reject_first:
        reject = """
          if (values.join('') !== '123456') {
            window.__attempts = (window.__attempts || 0) + 1;
            document.getElementById('err').textContent = 'Invalid OTP';
            document.querySelectorAll('.otp-box').forEach((el) => { el.value = ''; });
            return;
          }
        """
    return f"""
      <html><body>
        <form id="f" action="{action}"
              onsubmit="event.preventDefault();
                const values = Array.from(document.querySelectorAll('.otp-box')).map((el) => el.value);
                {reject}
                window.__otpValues = values;
                document.getElementById('result').textContent = 'Account created';
                document.getElementById('f').remove();">
          <label>Verify Mobile OTP</label>
          {boxes}
          <div id="err"></div>
          <div id="result"></div>
          <button type="submit" id="signup_submit">Create Account</button>
        </form>
      </body></html>
    """


def test_split_otp_boxes_receive_one_digit_each_and_submit():
    async def scenario(page):
        await page.set_content(_split_otp_html())
        orchestrator = _orchestrator(page)

        async def answer():
            return {"otp": "123456"}

        orchestrator._wait_for_user_response = answer
        dom = await orchestrator._scan_dom()

        handled = await orchestrator._handle_otp(dom)

        assert handled is True
        assert await page.evaluate("window.__otpValues") == list("123456")
        assert await page.evaluate("() => !document.getElementById('f')") is True
        assert orchestrator._otp_cleared is True
        assert orchestrator.active_gate is None

    run_with_page(scenario)


def test_single_otp_input_receives_the_whole_code():
    async def scenario(page):
        await page.set_content(
            """
            <html><body>
              <form id="f" action="/site/validateotp"
                    onsubmit="event.preventDefault();
                      window.__otpValue = document.getElementById('otp').value;
                      document.getElementById('result').textContent = 'Account created';
                      document.getElementById('f').remove();">
                <label for="otp">Enter OTP</label>
                <input id="otp" name="otp_code" type="text" maxlength="6">
                <div id="result"></div>
                <button type="submit" id="signup_submit">Verify OTP</button>
              </form>
            </body></html>
            """
        )
        orchestrator = _orchestrator(page)

        async def answer():
            return {"otp": "123456"}

        orchestrator._wait_for_user_response = answer
        dom = await orchestrator._scan_dom()

        handled = await orchestrator._handle_otp(dom)

        assert handled is True
        assert await page.evaluate("window.__otpValue") == "123456"
        assert orchestrator._otp_cleared is True

    run_with_page(scenario)


def test_rejected_otp_reopens_the_gate_and_a_retry_succeeds():
    async def scenario(page):
        await page.set_content(_split_otp_html(reject_first=True))
        orchestrator = _orchestrator(page)

        async def fast_change(before, *, timeout_ms=9000):
            await asyncio.sleep(0.05)
            return bool(await page.evaluate("() => !document.getElementById('f')"))

        orchestrator._wait_for_page_change = fast_change
        answers = iter([{"otp": "111111"}, {"otp": "123456"}])
        calls = {"count": 0}

        async def answer():
            calls["count"] += 1
            return next(answers)

        orchestrator._wait_for_user_response = answer
        dom = await orchestrator._scan_dom()

        handled = await orchestrator._handle_otp(dom)

        assert handled is True
        assert calls["count"] == 2
        assert await page.evaluate("window.__attempts") == 1
        assert await page.evaluate("window.__otpValues") == list("123456")
        assert orchestrator._otp_cleared is True

    run_with_page(scenario)


def test_dismissing_the_otp_gate_keeps_it_open():
    async def scenario(page):
        await page.set_content(_split_otp_html())
        orchestrator = _orchestrator(page)
        answers = iter([{"action": "DISMISS"}, {"otp": "123456"}])
        calls = {"count": 0}

        async def answer():
            calls["count"] += 1
            return next(answers)

        orchestrator._wait_for_user_response = answer
        dom = await orchestrator._scan_dom()

        handled = await orchestrator._handle_otp(dom)

        assert handled is True
        assert calls["count"] == 2
        assert await page.evaluate("window.__otpValues") == list("123456")

    run_with_page(scenario)


def test_send_otp_with_an_unsolved_captcha_does_not_open_an_otp_gate():
    """A login page can show a captcha and a Send OTP button together.

    Clicking Send OTP before the captcha is solved only produces a toastr and
    leaves the OTP boxes hidden.  The agent must not open a gate for a code it
    cannot enter anywhere.
    """

    async def scenario(page):
        await page.set_content(
            """
            <html><body>
              <form action="/site/login">
                <label for="mobile">Mobile Number</label>
                <input id="mobile" name="LoginForm[mobile_number]" type="text">
                <label for="captcha">Enter Captcha</label>
                <input id="captcha" name="LoginForm[captcha]" type="text">
                <div id="otp-section" style="display:none">
                  <label for="otp">Enter OTP</label>
                  <input id="otp" name="LoginForm[otp]" type="text">
                </div>
                <button type="button" id="send_otp_btn"
                  onclick="document.getElementById('err').textContent = 'Invalid captcha'">
                  Send OTP
                </button>
                <div id="err"></div>
              </form>
            </body></html>
            """
        )
        orchestrator = _orchestrator(page)
        dom = await orchestrator._scan_dom()

        handled = await orchestrator._handle_otp(dom)

        assert handled is False
        assert orchestrator.active_gate is None
        assert await page.input_value("#otp") == ""
        assert await page.inner_text("#err") == "Invalid captcha"

    run_with_page(scenario)


def test_dismissing_the_captcha_gate_keeps_it_pending():
    async def scenario(page):
        await page.set_content(
            """
            <html><body>
              <label for="captcha">Enter Captcha</label>
              <input id="captcha" name="LoginForm[captcha]" type="text">
            </body></html>
            """
        )
        orchestrator = _orchestrator(page)

        async def answer():
            return {"action": "DISMISS"}

        orchestrator._wait_for_user_response = answer
        dom = await orchestrator._scan_dom()

        pending = await orchestrator._handle_captcha(dom)

        assert pending is True
        assert orchestrator._captcha_signature == ""

    run_with_page(scenario)


def test_ajax_otp_success_without_a_page_change_is_accepted():
    """Some portals verify over AJAX and only reveal a success state.

    The practice portal keeps the same form and OTP input, then shows a
    persistent "verification complete" message.  Requiring a structural
    change would report a valid code as rejected.
    """

    async def scenario(page):
        await page.set_content(
            """
            <html><body>
              <form action="">
                <label for="otp">Enter OTP</label>
                <input id="otp" name="otp_code" type="text" maxlength="6">
                <button type="button" id="btn-verify-otp"
                  onclick="document.getElementById('status').style.display = 'block'">
                  Verify OTP
                </button>
                <div id="status" style="display:none">Demo verification complete.</div>
              </form>
            </body></html>
            """
        )
        orchestrator = _orchestrator(page)
        dom = await orchestrator._scan_dom()

        entered = await orchestrator._enter_otp_code(dom, "492015")
        assert entered["success"] is True
        result = await orchestrator._submit_otp_form(dom)

        assert result["success"] is True, result

    run_with_page(scenario)


def test_a_live_portal_otp_gate_never_advertises_the_demo_code():
    """The demo code belongs to the practice portal, not a real portal."""

    async def scenario(page):
        await page.set_content(_split_otp_html())
        orchestrator = _orchestrator(page)
        captured = {}

        async def answer():
            captured["gate"] = dict(orchestrator.active_gate or {})
            orchestrator.is_running = False
            return {"action": "STOPPED"}

        orchestrator._wait_for_user_response = answer
        dom = await orchestrator._scan_dom()

        await orchestrator._handle_otp(dom)

        gate = captured["gate"]
        assert gate.get("gate_type") == "OTP_RELAY"
        assert "demo_otp" not in gate
        assert "Demo mode code" not in str(gate.get("description") or "")

    run_with_page(scenario)


def test_the_simulator_otp_gate_shows_the_demo_code():
    async def scenario(page):
        await page.set_content(_split_otp_html())
        orchestrator = _orchestrator(page)
        orchestrator._adapter = SimpleNamespace(name="simulator")
        captured = {}

        async def answer():
            captured["gate"] = dict(orchestrator.active_gate or {})
            orchestrator.is_running = False
            return {"action": "STOPPED"}

        orchestrator._wait_for_user_response = answer
        dom = await orchestrator._scan_dom()

        await orchestrator._handle_otp(dom)

        gate = captured["gate"]
        assert gate.get("demo_otp")
        assert "Demo mode code" in str(gate.get("description") or "")

    run_with_page(scenario)


def test_a_generic_create_account_button_is_not_used_as_an_otp_submit():
    async def scenario(page):
        await page.set_content(
            """
            <html><body>
              <form id="f" action="/site/signup"
                    onsubmit="event.preventDefault(); window.__submitted = true;">
                <label for="otp">Enter OTP</label>
                <input id="otp" name="otp_code" type="text">
                <button type="submit" id="signup_submit">Create Account</button>
              </form>
            </body></html>
            """
        )
        orchestrator = _orchestrator(page)
        dom = await orchestrator._scan_dom()

        result = await orchestrator._submit_otp_form(dom)

        assert result["success"] is False
        assert "verification" in result["reason"].lower()
        assert await page.evaluate("window.__submitted || false") is False

    run_with_page(scenario)
