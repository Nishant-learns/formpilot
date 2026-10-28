"""A step is saved only when the page structure actually moves."""

from __future__ import annotations

from types import SimpleNamespace

from backend.core.orchestrator import FormPilotOrchestrator

from tests.browser_helpers import run_with_page


def _orchestrator(page):
    orchestrator = FormPilotOrchestrator()
    orchestrator.page = page
    orchestrator.target_url = page.url
    orchestrator.is_running = True
    orchestrator.state = "RUNNING"
    orchestrator.vault_mgr = SimpleNamespace(vault=SimpleNamespace())
    return orchestrator


def test_text_only_change_is_not_a_step_change():
    """A toastr validation message must not count as "Section 1 saved"."""

    async def scenario(page):
        await page.set_content(
            """
            <html><body>
              <div id="message"></div>
              <input id="mobile" name="mobile" type="text">
            </body></html>
            """
        )
        orchestrator = _orchestrator(page)
        before = await orchestrator._page_snapshot()

        await page.evaluate(
            "document.getElementById('message').textContent = 'Please enter Mobile OTP'"
        )
        changed = await orchestrator._wait_for_page_change(before, timeout_ms=700)

        assert changed is False

    run_with_page(scenario)


def test_structural_change_is_a_step_change():
    async def scenario(page):
        await page.set_content(
            """
            <html><body>
              <input id="mobile" name="mobile" type="text">
            </body></html>
            """
        )
        orchestrator = _orchestrator(page)
        before = await orchestrator._page_snapshot()

        await page.evaluate(
            "const input = document.createElement('input');"
            "input.name = 'otp'; document.body.appendChild(input);"
        )
        changed = await orchestrator._wait_for_page_change(before, timeout_ms=1500)

        assert changed is True

    run_with_page(scenario)


def test_a_hidden_form_becoming_visible_is_a_step_change():
    """Single-page portals swap views without changing the URL.

    The practice portal keeps its registration form in the DOM and reveals it
    from the gateway.  Counting hidden inputs made the two views look
    identical, so a real transition was reported as "nothing happened".
    """

    async def scenario(page):
        await page.set_content(
            """
            <html><body>
              <div id="gateway">
                <button type="button" onclick="openForm()">New Registration / OTR</button>
              </div>
              <form id="registration" style="display:none">
                <input id="mobile" name="mobile" type="text">
                <button type="submit">Save &amp; Next</button>
              </form>
              <script>
                function openForm() {
                  document.getElementById('gateway').style.display = 'none';
                  document.getElementById('registration').style.display = 'block';
                }
              </script>
            </body></html>
            """
        )
        orchestrator = _orchestrator(page)
        before = await orchestrator._page_snapshot()

        await page.click("text=New Registration / OTR")
        changed = await orchestrator._wait_for_page_change(before, timeout_ms=1500)

        assert changed is True

    run_with_page(scenario)


def test_a_full_form_with_an_otp_field_is_not_an_otp_page():
    """The practice portal keeps its phone OTP box inside section 1.

    An OTP input on a full form must not block "Save & Next"; only a
    dedicated verification page does.
    """

    async def scenario(page):
        await page.set_content(
            """
            <html><body>
              <form action="/signup">
                <label for="mobile">Mobile Number</label>
                <input id="mobile" name="mobile" type="text">
                <label for="mobileOtp">Enter OTP</label>
                <input id="mobileOtp" name="mobileOtp" type="text" maxlength="6">
                <button type="submit">Save &amp; Next</button>
              </form>
            </body></html>
            """
        )
        orchestrator = _orchestrator(page)
        dom = await orchestrator._scan_dom()

        assert orchestrator._is_otp_page(dom) is False

    run_with_page(scenario)


def test_advance_refuses_a_page_that_still_needs_an_otp():
    async def scenario(page):
        await page.set_content(
            """
            <html><body>
              <form action="/site/validateotp">
                <label>Verify Mobile OTP</label>
                <input name="SignupForm[mobile_otp][]" type="text" maxlength="1">
                <button type="submit" id="signup_submit">Create Account</button>
              </form>
            </body></html>
            """
        )
        orchestrator = _orchestrator(page)
        dom = await orchestrator._scan_dom()

        advanced = await orchestrator._advance(dom)

        assert advanced is False

    run_with_page(scenario)
