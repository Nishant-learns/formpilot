"""Field commit verdicts: what the portal actually kept, and why it matters."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from backend.core.field_commit import (
    CommitStatus,
    EntryMatch,
    classify_commit,
    committed,
    compare_entry,
    kind_for,
    retryable,
)
from backend.core.orchestrator import FormPilotOrchestrator

from tests.browser_helpers import run_with_page


# ------------------------------------------------------------------ comparison


def test_exact_value_is_same_and_committed():
    verdict = classify_commit("Aman Kumar", "Aman Kumar", kind="text")

    assert verdict["status"] == CommitStatus.OK.value
    assert verdict["match"] == EntryMatch.SAME.value
    assert committed(verdict) is True


def test_case_and_whitespace_differences_are_the_same_value():
    assert compare_entry("Aman Kumar", "  AMAN   KUMAR ", "text") is EntryMatch.SAME


def test_a_reformatted_date_is_equivalent_not_a_failure():
    verdict = classify_commit("15/08/2003", "2003-08-15", kind="date")

    assert verdict["status"] == CommitStatus.OK.value
    assert verdict["match"] == EntryMatch.REFORMATTED.value


def test_a_different_date_is_a_failure():
    verdict = classify_commit("15/08/2003", "16/08/2003", kind="date")

    assert verdict["status"] == CommitStatus.DID_NOT_COMMIT.value
    assert verdict["match"] == EntryMatch.DIFFERENT.value


def test_a_country_code_prefix_is_a_reformat_not_a_different_number():
    assert compare_entry("9876543210", "+91 98765 43210", "digits") is EntryMatch.REFORMATTED


def test_a_truncated_number_is_not_held():
    verdict = classify_commit("9876543210", "98765", kind="digits")

    assert verdict["match"] == EntryMatch.NOT_HELD.value
    assert verdict["status"] == CommitStatus.DID_NOT_COMMIT.value


def test_an_empty_field_says_so_plainly():
    verdict = classify_commit("Nishant Kumar", "", kind="text")

    assert verdict["match"] == EntryMatch.NOT_HELD.value
    assert "empty" in verdict["reason"]


def test_a_truncated_name_is_not_held():
    assert compare_entry("Nishant Kumar", "Nish", "text") is EntryMatch.NOT_HELD


def test_a_password_is_compared_exactly():
    assert compare_entry("s3cret", "S3cret", "password") is EntryMatch.DIFFERENT
    assert compare_entry("s3cret", "s3cret", "password") is EntryMatch.SAME


def test_a_select_is_case_insensitive_but_not_fuzzy():
    assert compare_entry("Uttar Pradesh", "UTTAR PRADESH", "select") is EntryMatch.SAME
    assert compare_entry("Uttar Pradesh", "UP", "select") is EntryMatch.DIFFERENT


def test_an_unreadable_field_is_unverified_not_success():
    verdict = classify_commit("Nishant", "Nishant", readable=False)

    assert verdict["status"] == CommitStatus.UNVERIFIED.value
    assert committed(verdict) is False


def test_only_dropped_or_replaced_values_are_retryable():
    assert retryable({"match": EntryMatch.NOT_HELD.value}) is True
    assert retryable({"match": EntryMatch.DIFFERENT.value}) is True
    assert retryable({"match": EntryMatch.SAME.value}) is False
    assert retryable(None) is False


def test_kind_mapping_follows_the_field_not_the_label():
    assert kind_for({"type": "password"}) == "password"
    assert kind_for({"tagName": "select"}) == "select"
    assert kind_for({"type": "date"}) == "date"
    assert kind_for({"type": "tel"}) == "digits"
    assert kind_for({"type": "email"}) == "email"
    assert kind_for({"tagName": "textarea"}) == "multiline"
    assert kind_for({"type": "text"}) == "text"


# ------------------------------------------------------------------ orchestrator


class _FakeVault:
    def __init__(self, values=None):
        self.values = values or {}

    def find_field_value(self, key):
        return self.values.get(key)

    def get_formatted_dob(self, fmt):
        return self.values.get("dob")


def _orchestrator(page, values=None):
    orchestrator = FormPilotOrchestrator()
    orchestrator.page = page
    orchestrator.target_url = page.url
    orchestrator.is_running = True
    orchestrator.vault_mgr = SimpleNamespace(vault=_FakeVault(values))
    return orchestrator


def test_a_value_dropped_once_is_reentered_and_then_verified():
    async def scenario(page):
        await page.set_content(
            """
            <html><body>
              <label for="full_name">Full Name</label>
              <input id="full_name" name="full_name" type="text"
                     oninput="if (!window.__dropped) { window.__dropped = true;
                              const el = this; setTimeout(() => { el.value = ''; }, 20); }">
            </body></html>
            """
        )
        orchestrator = _orchestrator(page, {"full_name": "Nishant Kumar"})
        dom = await orchestrator._scan_dom()

        verified = await orchestrator._fill_form(dom)

        assert verified == 1
        assert orchestrator.fill_summary["status"] == "FILLED"
        assert orchestrator.fill_summary["retried"] == 1
        assert len(orchestrator.filled_audit) == 1
        assert await page.input_value("#full_name") == "Nishant Kumar"

    run_with_page(scenario)


def test_a_truncating_portal_is_reported_with_the_commit_verdict():
    async def scenario(page):
        await page.set_content(
            """
            <html><body>
              <label for="full_name">Full Name</label>
              <input id="full_name" name="full_name" type="text"
                     oninput="this.value = this.value.slice(0, 4)">
            </body></html>
            """
        )
        orchestrator = _orchestrator(page, {"full_name": "Nishant Kumar"})
        dom = await orchestrator._scan_dom()

        verified = await orchestrator._fill_form(dom)

        assert verified == 0
        failure = orchestrator.fill_failures[0]
        assert failure["status"] == "FAILED"
        assert failure["commit"]["match"] == "not_held"
        assert failure["retried"] is True
        assert "whole value" in failure["reason"]
        assert orchestrator.fill_summary["failed"] == 1

    run_with_page(scenario)


def test_a_reformatted_value_is_counted_as_verified_and_reported():
    async def scenario(page):
        await page.set_content(
            """
            <html><body>
              <label for="dob">Date of Birth</label>
              <input id="dob" name="dob" type="text"
                     oninput="const d = this.value.split('-');
                              if (d.length === 3) { this.value = d[2] + '/' + d[1] + '/' + d[0]; }">
            </body></html>
            """
        )
        orchestrator = _orchestrator(page, {"dob": "2003-08-15"})
        dom = await orchestrator._scan_dom()

        verified = await orchestrator._fill_form(dom)

        assert verified == 1
        assert orchestrator.fill_summary["status"] == "FILLED"
        assert orchestrator.fill_summary["reformatted"] == 1
        assert orchestrator.fill_summary["fields"][0]["commit"] == "reformatted"
        assert await page.input_value("#dob") == "15/08/2003"

    run_with_page(scenario)
