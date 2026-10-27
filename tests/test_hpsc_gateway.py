"""Regression fixture for the HPSC Login gateway.

The portal renders Login as an anchor, while the old click path searched for a
button named "Login" and then fell back to ``text=Login``, which matched the
anchor, a heading and a paragraph.  These tests pin the exact structure and the
blueprint-id click path.
"""

from __future__ import annotations

from backend.core.dom_scanner import DOMScanner
from backend.core.form_model import FormModel
from backend.core.orchestrator import FormPilotOrchestrator

from tests.browser_helpers import run_with_page

HPSC_HOME = """
<html><head><base href="https://regn.hpsc.gov.in/"></head><body>
  <nav>
    <a href="/frontend/site/login" class="btn btn-main"> Login </a>
  </nav>
  <h4>Create Account &amp; Login</h4>
  <p>Register -> Login -> Apply</p>
</body></html>
"""

LOGIN_PAGE = "<html><body><h1>Candidate Login</h1></body></html>"


def _route_login(page):
    async def handler(route):
        await route.fulfill(
            status=200,
            content_type="text/html",
            body=LOGIN_PAGE,
        )

    return page.route("https://regn.hpsc.gov.in/frontend/site/login", handler)


def test_hpsc_login_is_a_link_and_the_text_query_is_ambiguous():
    async def scenario(page):
        await _route_login(page)
        await page.set_content(HPSC_HOME)

        assert await page.get_by_role("button", name="Login", exact=True).count() == 0
        assert await page.get_by_role("link", name="Login", exact=True).count() == 1
        assert await page.locator("text=Login").count() == 3

        _dom, blueprint = await DOMScanner.scan(page)
        gateway = next(item for item in blueprint.gateways() if item.name == "Login")
        assert gateway.tag == "a"
        assert gateway.role == "link"
        assert gateway.css == 'a[href="/frontend/site/login"]'
        assert gateway.css_unique is True
        assert gateway.covered_by is None

    run_with_page(scenario)


def test_hpsc_gateway_clicks_the_exact_anchor_and_navigates():
    async def scenario(page):
        await _route_login(page)
        await page.set_content(HPSC_HOME)

        orchestrator = FormPilotOrchestrator()
        orchestrator.page = page
        dom = await orchestrator._scan_dom()

        gateway = dom["gateways"][0]
        assert gateway["tagName"] == "a"
        assert gateway["role"] == "link"
        assert gateway["element_id"]
        assert gateway["css_unique"] is True

        clicked = await orchestrator._safe_click(gateway)
        assert clicked is True
        assert orchestrator._last_action_result is not None
        assert orchestrator._last_action_result.ok is True
        assert orchestrator._last_action_result.method == "playwright:blueprint_id"

        await page.wait_for_url(
            "https://regn.hpsc.gov.in/frontend/site/login",
            timeout=5000,
        )
        assert "Candidate Login" in await page.inner_text("body")

    run_with_page(scenario)


def test_form_model_preserves_the_gateway_blueprint_identity():
    async def scenario(page):
        await page.set_content(HPSC_HOME)
        dom, _blueprint = await DOMScanner.scan(page)
        form_map = FormModel.build_form_map(dom, page.url)
        gateway = form_map["gateways"][0]

        assert gateway["tag"] == "a"
        assert gateway["role"] == "link"
        assert gateway["href"] == "/frontend/site/login"
        assert gateway["element_id"]
        assert gateway["css"] == 'a[href="/frontend/site/login"]'
        assert gateway["css_unique"] is True
        assert gateway["xpath"]
        assert gateway["frame"] == "main"
        assert gateway["visible"] is True
        assert gateway["interactable"] is True

    run_with_page(scenario)


def test_legacy_click_refuses_two_links_with_the_same_text():
    async def scenario(page):
        await page.set_content(
            """
            <html><body>
              <a href="#one">Login</a>
              <a href="#two">Login</a>
            </body></html>
            """
        )
        orchestrator = FormPilotOrchestrator()
        orchestrator.page = page
        clicked = await orchestrator._legacy_click({"text": "Login", "tagName": "a"})
        assert clicked is False

    run_with_page(scenario)
