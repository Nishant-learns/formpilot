"""Typed post-conditions: a dispatched action is not a committed action."""

from __future__ import annotations

from types import SimpleNamespace

from backend.core.action_resolver import ActionResolver, Postcondition
from backend.core.dom_scanner import DOMScanner
from backend.core.orchestrator import FormPilotOrchestrator

from tests.browser_helpers import run_with_page

CLICK_HTML = """
<html><body>
  <p id="message">Nothing yet</p>
  <button type="button" id="save"
          onclick="document.getElementById('message').textContent='Saved';">
    Save
  </button>
  <button type="button" id="idle">Idle</button>
</body></html>
"""

SELECT_HTML = """
<html><body>
  <form>
    <label for="cat">Category</label>
    <select id="cat" name="category">
      <option value="">Choose</option>
      <option value="GEN">General</option>
    </select>
  </form>
</body></html>
"""

SELECT_REVERTS_HTML = """
<html><body>
  <form>
    <label for="cat">Category</label>
    <select id="cat" name="category" onchange="this.value='';">
      <option value="">Choose</option>
      <option value="GEN">General</option>
    </select>
  </form>
</body></html>
"""

CHECK_REVERTS_HTML = """
<html><body>
  <label for="agree">I agree</label>
  <input type="checkbox" id="agree" name="agree" onchange="this.checked = false;">
</body></html>
"""


async def _blueprint(page, html: str):
    await page.set_content(html)
    _dom, blueprint = await DOMScanner.scan(page)
    return blueprint


def test_a_click_that_changes_the_page_is_changed():
    async def scenario(page):
        blueprint = await _blueprint(page, CLICK_HTML)
        save = next(item for item in blueprint.elements.values() if item.name == "Save")

        result = await ActionResolver(page, blueprint).click(save.id)

        assert result.ok, result.to_dict()
        assert result.postcondition == Postcondition.CHANGED.value
        assert result.details["postcondition"] == "changed"

    run_with_page(scenario)


def test_a_click_that_changes_nothing_is_not_a_failure_but_is_reported():
    async def scenario(page):
        blueprint = await _blueprint(page, CLICK_HTML)
        idle = next(item for item in blueprint.elements.values() if item.name == "Idle")

        result = await ActionResolver(page, blueprint).click(idle.id)

        # The click was dispatched, so it is not an error ...
        assert result.ok is True
        # ... but the page did not react, and the caller is told.
        assert result.postcondition == Postcondition.NO_CHANGE.value

    run_with_page(scenario)


def test_a_select_that_keeps_the_value_is_held():
    async def scenario(page):
        blueprint = await _blueprint(page, SELECT_HTML)
        category = next(item for item in blueprint.fields() if item.tag == "select")

        result = await ActionResolver(page, blueprint).select(category.id, "General")

        assert result.ok, result.to_dict()
        assert result.postcondition == Postcondition.HELD.value
        assert await page.locator("#cat").input_value() == "GEN"

    run_with_page(scenario)


def test_a_select_that_reverts_is_not_held():
    async def scenario(page):
        blueprint = await _blueprint(page, SELECT_REVERTS_HTML)
        category = next(item for item in blueprint.fields() if item.tag == "select")

        result = await ActionResolver(page, blueprint, timeout_ms=1000).select(
            category.id, "General"
        )

        assert result.ok is False
        assert result.error_code == "SELECT_NOT_HELD"
        assert result.postcondition == Postcondition.NOT_HELD.value
        assert await page.locator("#cat").input_value() == ""

    run_with_page(scenario)


def test_a_checkbox_that_reverts_is_not_held():
    async def scenario(page):
        blueprint = await _blueprint(page, CHECK_REVERTS_HTML)
        agree = next(item for item in blueprint.fields() if item.tag == "input")

        result = await ActionResolver(page, blueprint, timeout_ms=1000).check(agree.id)

        assert result.ok is False
        assert result.error_code == "CHECK_NOT_HELD"
        assert result.postcondition == Postcondition.NOT_HELD.value
        assert await page.locator("#agree").is_checked() is False

    run_with_page(scenario)


def test_an_upload_that_keeps_the_file_is_held(tmp_path):
    async def scenario(page):
        blueprint = await _blueprint(
            page,
            '<html><body><input type="file" id="doc" name="doc"></body></html>',
        )
        doc = next(item for item in blueprint.fields() if item.tag == "input")
        path = tmp_path / "photo.jpg"
        path.write_bytes(b"not really a jpeg")

        result = await ActionResolver(page, blueprint).upload(doc.id, str(path))

        assert result.ok, result.to_dict()
        assert result.postcondition == Postcondition.HELD.value
        assert "photo.jpg" in result.message

    run_with_page(scenario)


def test_an_upload_that_is_cleared_is_not_held(tmp_path):
    async def scenario(page):
        blueprint = await _blueprint(
            page,
            '<html><body>'
            '<input type="file" id="doc" name="doc" onchange="this.value=\'\';">'
            "</body></html>",
        )
        doc = next(item for item in blueprint.fields() if item.tag == "input")
        path = tmp_path / "photo.jpg"
        path.write_bytes(b"not really a jpeg")

        result = await ActionResolver(page, blueprint).upload(doc.id, str(path))

        assert result.ok is False
        assert result.error_code == "UPLOAD_NOT_HELD"
        assert result.postcondition == Postcondition.NOT_HELD.value

    run_with_page(scenario)


def test_the_verdict_is_in_the_serialised_result():
    from backend.core.action_resolver import ActionResult

    payload = ActionResult(ok=True, action="click", postcondition="no_change").to_dict()

    assert payload["postcondition"] == "no_change"


# ------------------------------------------------------- the advance guard


def _orchestrator(page):
    orchestrator = FormPilotOrchestrator()
    orchestrator.page = page
    orchestrator.target_url = page.url
    orchestrator.is_running = True
    orchestrator.state = "RUNNING"
    orchestrator.vault_mgr = SimpleNamespace(vault=SimpleNamespace())
    return orchestrator


STUCK_FORM_HTML = """
<html><body>
  <form>
    <label for="name">Name</label>
    <input id="name" name="name" type="text">
    <button type="button" id="save"
            onclick="window.__clicks = (window.__clicks || 0) + 1; return false;">
      Save &amp; Next
    </button>
  </form>
</body></html>
"""


def test_a_save_click_that_changes_nothing_is_not_repeated():
    async def scenario(page):
        await page.set_content(STUCK_FORM_HTML)
        orchestrator = _orchestrator(page)

        async def no_change(before, timeout_ms=9000):
            return False

        orchestrator._wait_for_page_change = no_change
        dom = await orchestrator._scan_dom()

        first = await orchestrator._advance(dom)
        assert first is False
        assert await page.evaluate("window.__clicks") == 1
        assert orchestrator._blocked_advance

        # The same stuck page must not be clicked again.
        second = await orchestrator._advance(dom)
        assert second is None
        assert await page.evaluate("window.__clicks") == 1

        # A human answer lifts the block; the click is allowed once more.
        orchestrator._blocked_advance = ""
        third = await orchestrator._advance(dom)
        assert third is False
        assert await page.evaluate("window.__clicks") == 2

    run_with_page(scenario)


def test_a_real_advance_lifts_the_block():
    async def scenario(page):
        await page.set_content(
            """
            <html><body>
              <form>
                <label for="name">Name</label>
                <input id="name" name="name" type="text">
                <button type="button" id="save"
                        onclick="document.body.innerHTML = '<h2>Step 2</h2>';">
                  Save &amp; Next
                </button>
              </form>
            </body></html>
            """
        )
        orchestrator = _orchestrator(page)
        orchestrator._blocked_advance = "some-old-signature"
        dom = await orchestrator._scan_dom()

        advanced = await orchestrator._advance(dom)

        assert advanced is True
        assert orchestrator._blocked_advance == ""

    run_with_page(scenario)


def test_the_report_explains_a_click_that_did_nothing(tmp_path):
    from backend.core.run_report import build_run_report
    from backend.core.run_store import RunStore

    store = RunStore(tmp_path / "runs")
    run_id = "run-no-change"
    store.start(run_id, {"query": "hpsc", "run_mode": "fill"})
    store.record_step(
        run_id,
        "advance",
        status="failed",
        error_code="navigation_failure",
        output={"url": "https://portal.example/form", "postcondition": "no_change"},
    )
    store.finish(run_id, "WAITING_FOR_USER")

    report = build_run_report(store.run_detail(run_id))

    advance = next(item for item in report["timeline"] if item["kind"] == "advance")
    assert advance["detail"] == "The button was clicked but the page did not react."


def test_a_toast_only_change_does_not_count_as_a_save():
    """The page changed text but not structure: do not save or click twice."""

    async def scenario(page):
        await page.set_content(
            """
            <html><body>
              <div id="toast"></div>
              <form>
                <label for="name">Name</label>
                <input id="name" name="name" type="text">
                <button type="button" id="save"
                        onclick="document.getElementById('toast').textContent='Saving...';">
                  Save &amp; Next
                </button>
              </form>
            </body></html>
            """
        )
        orchestrator = _orchestrator(page)

        async def changed(before, timeout_ms=9000):
            return True

        orchestrator._wait_for_page_change = changed
        dom = await orchestrator._scan_dom()

        first = await orchestrator._advance(dom)
        assert first is False
        assert orchestrator._blocked_advance

        second = await orchestrator._advance(dom)
        assert second is None

    run_with_page(scenario)
