"""Deterministic resolver tests: unique ids, ambiguity, coverage, drift."""

from __future__ import annotations

from backend.core.action_resolver import ActionResolver
from backend.core.blueprint import BlueprintElement, PageBlueprint
from backend.core.dom_scanner import DOMScanner

from tests.browser_helpers import run_with_page

FORM_HTML = """
<html><body>
  <nav>
    <a href="#" onclick="window.__clicked='login'; return false;">Login</a>
  </nav>
  <h4>Create Account &amp; Login</h4>
  <p>Register -> Login -> Apply</p>
  <form>
    <label for="uid">User ID</label>
    <input id="uid" name="userId" type="text">
    <label for="dob">Date of Birth</label>
    <input id="dob" name="dob" type="date">
    <label for="cat">Category</label>
    <select id="cat" name="category">
      <option value="">Choose</option>
      <option value="GEN">General</option>
      <option value="OBC">OBC-NCL</option>
    </select>
    <button id="save" onclick="window.__clicked='save'; return false;">Save &amp; Next</button>
  </form>
</body></html>
"""


def test_resolver_clicks_fills_and_selects_by_blueprint_id():
    async def scenario(page):
        await page.set_content(FORM_HTML)
        _dom, blueprint = await DOMScanner.scan(page)
        resolver = ActionResolver(page, blueprint)

        gateway = next(item for item in blueprint.gateways() if item.name == "Login")
        result = await resolver.click(gateway.id)
        assert result.ok, result.to_dict()
        assert result.method.endswith("blueprint_id")
        assert await page.evaluate("window.__clicked") == "login"

        user_id = next(
            item for item in blueprint.fields() if item.attributes.get("name") == "userId"
        )
        filled = await resolver.fill(user_id.id, "ABC-123")
        assert filled.ok, filled.to_dict()
        assert await page.locator("#uid").input_value() == "ABC-123"

        dob = next(item for item in blueprint.fields() if item.attributes.get("name") == "dob")
        date_filled = await resolver.fill(dob.id, "01/02/2000")
        assert date_filled.ok, date_filled.to_dict()
        assert await page.locator("#dob").input_value() == "2000-02-01"

        category = next(item for item in blueprint.fields() if item.tag == "select")
        selected = await resolver.select(category.id, "General")
        assert selected.ok, selected.to_dict()
        assert await page.locator("#cat").input_value() == "GEN"

    run_with_page(scenario)


def test_resolver_refuses_ambiguous_role_and_text_matches():
    async def scenario(page):
        await page.set_content(
            """
            <html><body>
              <button>Continue</button>
              <button>Continue</button>
            </body></html>
            """
        )
        element = BlueprintElement(
            id="manual-ambiguous",
            tag="button",
            role="button",
            name="Continue",
        )
        blueprint = PageBlueprint(
            scan_id="manual",
            url="about:blank",
            title="",
            elements=[element],
        )
        result = await ActionResolver(page, blueprint).click(element.id)
        assert result.ok is False
        assert result.error_code == "MULTIPLE_MATCHES"

    run_with_page(scenario)


def test_resolver_reports_a_covering_element_instead_of_force_clicking():
    async def scenario(page):
        await page.set_content(
            """
            <html><body>
              <div style="position:relative;height:120px">
                <button id="target"
                        style="position:absolute;left:20px;top:20px"
                        onclick="window.__clicked=true">Continue</button>
                <div id="overlay"
                     style="position:absolute;left:0;top:0;width:220px;height:110px;
                            background:rgba(0,0,0,0.05)"></div>
              </div>
            </body></html>
            """
        )
        _dom, blueprint = await DOMScanner.scan(page)
        target = next(
            item for item in blueprint.elements.values() if item.attributes.get("id") == "target"
        )
        result = await ActionResolver(page, blueprint).click(target.id)
        assert result.ok is False
        assert result.error_code == "COVERED"
        assert result.details["covered_by"]["id"] == "overlay"
        assert await page.evaluate("window.__clicked === true") is False

    run_with_page(scenario)


def test_resolver_falls_back_to_unique_css_when_the_scan_id_is_stale():
    async def scenario(page):
        await page.set_content(FORM_HTML)
        _dom, blueprint = await DOMScanner.scan(page)
        save = next(
            item for item in blueprint.elements.values() if item.attributes.get("id") == "save"
        )
        old_id = save.id
        await page.eval_on_selector("#save", "el => el.removeAttribute('data-fp-id')")
        result = await ActionResolver(page, blueprint).click(old_id)
        assert result.ok, result.to_dict()
        assert result.method == "playwright:css"
        assert await page.evaluate("window.__clicked") == "save"

    run_with_page(scenario)


def test_resolver_refuses_a_different_tag_after_drift():
    async def scenario(page):
        await page.set_content("<html><body><a id='target'>Go</a></body></html>")
        element = BlueprintElement(
            id="manual-drift",
            tag="button",
            role="button",
            name="Go",
            css="#target",
            css_unique=True,
        )
        blueprint = PageBlueprint(
            scan_id="manual",
            url="about:blank",
            title="",
            elements=[element],
        )
        result = await ActionResolver(page, blueprint).click(element.id)
        assert result.ok is False
        assert result.error_code == "DRIFT"
        assert result.drift is True

    run_with_page(scenario)


def test_resolver_treats_a_navigation_during_click_as_success():
    """A link can navigate before Playwright's click call returns.

    The click raises "execution context was destroyed", but the page really
    moved.  Reporting that as CLICK_FAILED sends the agent into fallback
    clicks on the new page and loses the navigation.
    """

    async def scenario(page):
        await page.set_content(
            """
            <html><body>
              <a id="go" href="#">Get Started</a>
            </body></html>
            """
        )
        _dom, blueprint = await DOMScanner.scan(page)
        target = next(
            item for item in blueprint.elements.values() if item.attributes.get("id") == "go"
        )
        resolver = ActionResolver(page, blueprint)

        class NavigatingLocator:
            async def click(self, timeout=0):
                await page.goto("data:text/html,<html><body>Signup</body></html>")
                raise RuntimeError("Execution context was destroyed")

        async def fake_resolve(element_id):
            return page.main_frame, NavigatingLocator(), target, "blueprint_id"

        async def noop(*args, **kwargs):
            return None

        async def true(*args, **kwargs):
            return True

        async def tag(*args, **kwargs):
            return target.tag

        resolver.resolve = fake_resolve
        resolver._scroll = noop
        resolver._tag = tag
        resolver._is_visible = true
        resolver._is_enabled = true
        resolver._hit_test = noop

        result = await resolver.click(target.id)

        assert result.ok, result.to_dict()
        assert "navigated" in result.method
        assert page.url.startswith("data:text/html")

    run_with_page(scenario)


def test_resolver_uploads_to_the_exact_file_input(tmp_path):
    upload = tmp_path / "document.txt"
    upload.write_text("demo", encoding="utf-8")

    async def scenario(page):
        await page.set_content(
            """
            <html><body><form>
              <label for="photo">Photograph</label>
              <input id="photo" name="photo" type="file">
              <label for="document">Supporting document</label>
              <input id="document" name="document" type="file">
            </form></body></html>
            """
        )
        _dom, blueprint = await DOMScanner.scan(page)
        document = next(
            item
            for item in blueprint.fields()
            if item.attributes.get("name") == "document"
        )
        result = await ActionResolver(page, blueprint).upload(document.id, str(upload))
        assert result.ok, result.to_dict()
        assert await page.locator("#document").evaluate("el => el.files.length") == 1
        assert await page.locator("#photo").evaluate("el => el.files.length") == 0

    run_with_page(scenario)
