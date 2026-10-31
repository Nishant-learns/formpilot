"""Blueprint scanner tests against real Chromium DOMs."""

from __future__ import annotations

from backend.core.dom_scanner import DOMScanner

from tests.browser_helpers import run_with_page

PORTAL_HTML = """
<html><body>
  <nav>
    <a href="/frontend/site/login" class="btn btn-main"> Login </a>
  </nav>
  <h4>Create Account &amp; Login</h4>
  <p>Register -> Login -> Apply</p>
  <form>
    <label for="uid">User ID</label>
    <input id="uid" name="userId" type="text" required>
    <label for="pwd">Password</label>
    <input id="pwd" name="password" type="password">
    <label for="cat">Category</label>
    <select id="cat" name="category">
      <option value="">Choose</option>
      <option value="GEN">General</option>
      <option value="OBC">OBC-NCL</option>
    </select>
    <button id="go" type="submit">Log In</button>
    <button id="hidden" style="display:none">Continue</button>
  </form>
</body></html>
"""


def test_scanner_builds_a_tree_with_unique_ids_and_durable_locators():
    async def scenario(page):
        await page.set_content(PORTAL_HTML)
        dom, blueprint = await DOMScanner.scan(page)

        assert blueprint.scan_id
        ids = [element.id for element in blueprint.elements.values()]
        assert len(ids) == len(set(ids))
        assert len(ids) == len(blueprint.elements)

        gateway = next(item for item in blueprint.gateways() if item.name == "Login")
        assert gateway.tag == "a"
        assert gateway.role == "link"
        assert gateway.css == 'a[href="/frontend/site/login"]'
        assert gateway.css_unique is True
        assert gateway.xpath
        assert gateway.visible is True
        assert gateway.interactable is True
        assert gateway.parent_id
        assert gateway.id in blueprint.get(gateway.parent_id).children

        user_id = next(
            item
            for item in blueprint.fields()
            if item.attributes.get("name") == "userId"
        )
        assert user_id.role == "textbox"
        assert user_id.name == "User ID"
        assert user_id.attributes.get("required") is True
        assert user_id.editable is True

        category = next(item for item in blueprint.fields() if item.tag == "select")
        assert category.role == "combobox"
        assert {option["text"] for option in category.options} >= {
            "General",
            "OBC-NCL",
        }

        hidden = next(
            item
            for item in blueprint.elements.values()
            if item.attributes.get("id") == "hidden"
        )
        assert hidden.visible is False
        assert hidden.interactable is False
        assert hidden.id not in {item.id for item in blueprint.next_candidates()}

        prompt = blueprint.to_prompt_tree()
        assert gateway.id in prompt
        assert 'role="link"' in prompt

        legacy_gateway = next(item for item in dom["gateways"] if item["text"] == "Login")
        assert legacy_gateway["element_id"] == gateway.id
        assert legacy_gateway["role"] == "link"
        assert legacy_gateway["css"] == gateway.css
        assert legacy_gateway["visible"] is True

    run_with_page(scenario)


def test_scanner_descends_into_iframes_and_open_shadow_roots():
    html = """
    <html><body>
      <iframe srcdoc="<html><body><button id='inner'>Continue</button></body></html>"></iframe>
      <div id="host"></div>
      <script>
        const host = document.getElementById('host');
        const root = host.attachShadow({mode: 'open'});
        root.innerHTML = '<button id="shadow-btn">Shadow Next</button>';
      </script>
    </body></html>
    """

    async def scenario(page):
        await page.set_content(html)
        await page.wait_for_timeout(250)
        _dom, blueprint = await DOMScanner.scan(page)

        inner = next(
            item
            for item in blueprint.elements.values()
            if item.name == "Continue" and item.tag == "button"
        )
        assert inner.frame != "main"
        assert inner.frame_index > 0
        assert inner.visible is True

        shadow = next(
            item for item in blueprint.elements.values() if item.name == "Shadow Next"
        )
        assert shadow.shadow_host
        host = blueprint.get(shadow.shadow_host)
        assert host is not None
        assert host.tag == "div"

        # The resolver can address both controls by their per-scan ids.
        assert inner.id.startswith("fp-")
        assert shadow.id.startswith("fp-")

    run_with_page(scenario)


def test_scanner_records_the_element_covering_a_button():
    html = """
    <html><body>
      <div style="position:relative;height:120px">
        <button id="target" style="position:absolute;left:20px;top:20px">Continue</button>
        <div id="overlay"
             style="position:absolute;left:0;top:0;width:220px;height:110px;
                    background:rgba(0,0,0,0.05)"></div>
      </div>
    </body></html>
    """

    async def scenario(page):
        await page.set_content(html)
        _dom, blueprint = await DOMScanner.scan(page)

        target = next(
            item for item in blueprint.elements.values() if item.attributes.get("id") == "target"
        )
        assert target.interactable is True
        assert target.covered_by is not None
        assert target.covered_by.get("id") == "overlay"

    run_with_page(scenario)


DATE_FORM_HTML = """
<html><body><form>
  <div class="row">
    <div class="col">
      <label class="form-label">Date of Birth</label>
      <div class="input-group"><input type="text" placeholder="DD-MM-YYYY"></div>
    </div>
    <div class="col">
      <label class="form-label">Confirm Date of Birth</label>
      <div class="input-group"><input type="text" placeholder="DD-MM-YYYY"></div>
    </div>
  </div>
</form></body></html>
"""


def test_a_date_placeholder_is_a_format_hint_not_the_field_label():
    """The live HPSC form labels its date boxes only by a sibling <label>."""

    async def scenario(page):
        await page.set_content(DATE_FORM_HTML)
        dom, _ = await DOMScanner.scan(page)

        labels = [str(item.get("label") or "") for item in dom.get("inputs") or []]
        assert "Date of Birth" in labels
        assert "Confirm Date of Birth" in labels
        assert "DD-MM-YYYY" not in labels

    run_with_page(scenario)
