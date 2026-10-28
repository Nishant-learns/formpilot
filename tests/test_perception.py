"""Perception tests: the page as a human sees it, not as the DOM names it."""

from __future__ import annotations

from backend.core.perception import Perception

from tests.browser_helpers import run_with_page


PERSONAL_DETAILS = """
<html><head><title>Universal Registration — Personal Details</title></head><body>
  <h1>Personal Details</h1>
  <form>
    <fieldset>
      <legend>Name</legend>
      <label for="first">First Name <span>*</span></label>
      <input id="first" name="firstName" required>
      <label for="middle">Middle Name</label>
      <input id="middle" name="middleName">
      <label for="last">Last Name <span>*</span></label>
      <input id="last" name="lastName" required>
    </fieldset>
    <fieldset>
      <legend>Matriculation</legend>
      <label for="dob">Date of Birth</label>
      <input id="dob" name="identityModel.dob" placeholder="DD-MM-YYYY" required>
      <label for="dop">Date of Passing</label>
      <input id="dop" name="identityModel.dop" placeholder="DD-MM-YYYY" required>
    </fieldset>
    <label for="matricName">Name as printed on matric certificate</label>
    <input id="matricName" name="identityModel.name_as_matric" required>
    <label for="photo">Passport Photograph</label>
    <input id="photo" name="photo" type="file" required>
    <button type="button">Save &amp; Next</button>
  </form>
</body></html>
"""


def test_perception_keeps_label_placeholder_and_group_separate():
    async def scenario(page):
        await page.set_content(PERSONAL_DETAILS)
        perception = await Perception.capture(page)
        dob = next(field for field in perception.fields if field.label_text == "Date of Birth")
        assert dob.placeholder == "DD-MM-YYYY"
        assert dob.label_text == "Date of Birth"
        assert dob.group_heading == "Matriculation"
        assert dob.required is True
        assert dob.handle.startswith("fp-")

    run_with_page(scenario)


def test_perception_never_uses_the_placeholder_as_the_label():
    async def scenario(page):
        await page.set_content(
            """
            <html><body><form>
              <input id="only" name="identityModel.dob" placeholder="DD-MM-YYYY">
            </form></body></html>
            """
        )
        perception = await Perception.capture(page)
        field = perception.fields[0]
        assert field.label_text == ""
        assert field.placeholder == "DD-MM-YYYY"

    run_with_page(scenario)


def test_page_signature_ignores_typed_values_but_tracks_structure():
    async def scenario(page):
        await page.set_content(PERSONAL_DETAILS)
        first = await Perception.capture(page)
        await page.fill("#first", "Nishant")
        await page.fill("#dob", "03-08-2005")
        second = await Perception.capture(page)
        assert first.page_signature == second.page_signature

        await page.evaluate(
            "() => { const input = document.createElement('input');"
            "input.id = 'newField'; input.name = 'newField';"
            "document.querySelector('form').appendChild(input); }"
        )
        third = await Perception.capture(page)
        assert third.page_signature != first.page_signature

    run_with_page(scenario)


def test_perception_reports_human_only_signals():
    async def scenario(page):
        await page.set_content(
            """
            <html><body><form>
              <label for="otp">Enter OTP</label>
              <input id="otp" name="otp" placeholder="6-digit code">
              <label for="photo">Live photo</label>
              <input id="photo" name="photo" type="file" accept="image/*" capture="user">
            </form></body></html>
            """
        )
        perception = await Perception.capture(page)
        assert perception.signals["otp"] is True
        assert perception.signals["live_photo"] is True

    run_with_page(scenario)


def test_perception_keeps_actions_with_stable_handles():
    async def scenario(page):
        await page.set_content(
            """
            <html><body>
              <h1>Candidate Entry</h1>
              <a href="/register">New Registration</a>
              <a href="/login">Candidate Login</a>
            </body></html>
            """
        )
        perception = await Perception.capture(page)
        labels = {action.text: action for action in perception.actions}
        assert labels["New Registration"].kind_hint == "register"
        assert labels["Candidate Login"].kind_hint == "login"
        assert labels["Candidate Login"].handle.startswith("fp-")

    run_with_page(scenario)
