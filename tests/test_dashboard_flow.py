"""A signed-in dashboard is a hub, not the end of the run.

HPSC lands on ``/frontend/user/dashboard`` after login.  The page has no form
fields but links to the real registration.  The agent used to emit DONE there;
these tests pin the next-step checkpoint instead.
"""

from __future__ import annotations

import asyncio

from backend.core import decision_policy
from backend.core.form_model import FormModel
from backend.core.orchestrator import FormPilotOrchestrator

DASHBOARD_GATEWAYS = [
    {
        "text": "Preview Universal Registration",
        "href": "/frontend/user/dashboard/previewuniversal",
        "type": "NEW_REGISTRATION",
        "visible": True,
        "interactable": True,
        "insideForm": False,
        "element_id": "fp-preview",
        "tagName": "a",
        "role": "link",
    },
    {
        "text": "Proceed for Universal Registration",
        "href": "/frontend/user/dashboard/identity",
        "type": "NEW_REGISTRATION",
        "visible": True,
        "interactable": True,
        "insideForm": False,
        "element_id": "fp-proceed",
        "tagName": "a",
        "role": "link",
    },
]


def _dashboard_dom():
    return {
        "url": "https://regn.hpsc.gov.in/frontend/user/dashboard",
        "title": "Dashboard",
        "visibleText": (
            "Dashboard Registration ID 12345 Sign out "
            "Preview Universal Registration Proceed for Universal Registration"
        ),
        "inputs": [],
        "gateways": [dict(gateway) for gateway in DASHBOARD_GATEWAYS],
    }


def _dashboard_options():
    dom = _dashboard_dom()
    form_map = FormModel.build_form_map(dom, dom["url"])
    return dom, form_map, decision_policy.entry_options(dom, form_map)


def test_signed_in_dashboard_is_not_classified_as_a_registration_form():
    _dom, form_map, _options = _dashboard_options()

    assert form_map["page_type"] == "dashboard"


def test_dashboard_keeps_both_distinct_registration_links():
    _dom, _form_map, options = _dashboard_options()

    assert [option["text"] for option in options] == [
        "Preview Universal Registration",
        "Proceed for Universal Registration",
    ]
    assert {option["mode"] for option in options} == {"register"}
    assert {option["element_id"] for option in options} == {"fp-preview", "fp-proceed"}


def test_dashboard_never_adds_the_page_itself_as_an_entry_option():
    _dom, _form_map, options = _dashboard_options()

    assert all(option["source"] == "portal" for option in options)


def test_dashboard_opens_a_next_step_checkpoint_instead_of_done():
    class RecordingOrchestrator(FormPilotOrchestrator):
        def __init__(self):
            super().__init__()
            self.kinds = []

        async def _gateway_checkpoint(self, dom, gateways, *, kind="entry"):
            self.kinds.append(kind)

    dom = _dashboard_dom()
    orchestrator = RecordingOrchestrator()
    orchestrator.form_map = {"page_type": "dashboard"}

    handled = asyncio.run(orchestrator._dashboard_next_step(dom, dom["gateways"]))

    assert handled is True
    assert orchestrator.kinds == ["next_step"]


def test_dashboard_without_application_links_is_not_handled():
    orchestrator = FormPilotOrchestrator()
    orchestrator.form_map = {"page_type": "dashboard"}

    handled = asyncio.run(
        orchestrator._dashboard_next_step(
            {"url": "https://example.gov.in/dashboard", "inputs": [], "gateways": []},
            [],
        )
    )

    assert handled is False


def test_next_step_gate_lists_the_real_links():
    _dom, _form_map, options = _dashboard_options()

    gate = decision_policy.build_next_step_gate(options)

    assert gate["title"] == "What would you like to do next?"
    assert gate["no_default"] is True
    assert [option["text"] for option in gate["options"]] == [
        "Preview Universal Registration",
        "Proceed for Universal Registration",
    ]
    assert all(
        option["description"].startswith("Open:")
        for option in gate["options"]
    )


def test_same_target_registration_links_still_collapse():
    dom = {
        "url": "https://example.gov.in/",
        "visibleText": "",
        "inputs": [],
        "gateways": [
            {
                "text": "Register",
                "href": "/signup",
                "type": "NEW_REGISTRATION",
                "visible": True,
                "interactable": True,
                "insideForm": False,
            },
            {
                "text": "Create Account",
                "href": "https://example.gov.in/signup",
                "type": "NEW_REGISTRATION",
                "visible": True,
                "interactable": True,
                "insideForm": False,
            },
        ],
    }

    options = decision_policy.entry_options(dom)

    assert len(options) == 1
    assert options[0]["alternate_count"] == 1


def test_next_step_gate_opens_the_chosen_application_link():
    from tests.browser_helpers import run_with_page

    dashboard = """
    <html><body>
      <h1>Dashboard</h1>
      <p>Registration ID 12345 · Sign out</p>
      <a href="/previewuniversal">Preview Universal Registration</a>
      <a href="/identity" class="btn btn-main">Proceed for Universal Registration</a>
    </body></html>
    """
    identity = "<html><body><h1>Universal Registration</h1><p>Identity step</p></body></html>"

    async def scenario(page):
        async def dashboard_route(route):
            await route.fulfill(status=200, content_type="text/html", body=dashboard)

        async def identity_route(route):
            await route.fulfill(status=200, content_type="text/html", body=identity)

        await page.route("https://example.gov.in/dashboard", dashboard_route)
        await page.route("https://example.gov.in/identity", identity_route)
        await page.route("https://example.gov.in/previewuniversal", dashboard_route)
        await page.goto("https://example.gov.in/dashboard")

        orchestrator = FormPilotOrchestrator()
        orchestrator.page = page
        orchestrator.is_running = True
        orchestrator.state = "RUNNING"
        dom = await orchestrator._scan_dom()
        orchestrator.form_map = FormModel.build_form_map(dom, page.url)
        orchestrator._entry_options = decision_policy.entry_options(dom, orchestrator.form_map)

        async def answer():
            gate = orchestrator.active_gate or {}
            option = next(
                item
                for item in gate.get("options") or []
                if item.get("text") == "Proceed for Universal Registration"
            )
            return {"action": "GATEWAY_CHOICE", **option}

        orchestrator._wait_for_user_response = answer

        handled = await orchestrator._dashboard_next_step(dom, dom["gateways"])

        assert handled is True
        await page.wait_for_url("https://example.gov.in/identity", timeout=5000)
        assert "Universal Registration" in await page.inner_text("body")

    run_with_page(scenario)
