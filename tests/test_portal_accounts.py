"""Portal account memory: per-portal facts, summaries and read-only inspection."""

from __future__ import annotations

import asyncio
import json

import pytest

from backend.core.perception import Perception, PerceivedAction, PerceivedField
from backend.core.portal_accounts import PortalAccountStore


def _store(tmp_path) -> PortalAccountStore:
    return PortalAccountStore(str(tmp_path / "portal_accounts.json"))


def test_an_account_fact_is_scoped_to_the_portal_and_identifier(tmp_path):
    store = _store(tmp_path)
    store.record(
        "regn.hpsc.gov.in",
        identifier_type="mobile",
        identifier_value="9876543210",
        account_exists="yes",
        login_method="mobile_otp",
        confirmed_by_human=True,
    )

    exact = store.get(
        "regn.hpsc.gov.in", identifier_type="mobile", identifier_value="9876543210"
    )
    other = store.get(
        "regn.hpsc.gov.in", identifier_type="email", identifier_value="other@example.com"
    )

    assert exact is not None
    assert exact.account_exists == "yes"
    assert exact.login_method == "mobile_otp"
    assert exact.confirmed_by_human_at
    assert other is None


def test_domain_summary_aggregates_identifiers_without_guessing(tmp_path):
    store = _store(tmp_path)
    store.record("regn.hpsc.gov.in", account_exists="yes", registration_status="in_progress")
    store.record(
        "regn.hpsc.gov.in",
        identifier_type="mobile",
        identifier_value="9876543210",
        last_known_step="section_2",
    )

    summary = store.domain_summary("regn.hpsc.gov.in")

    assert summary["accounts"] == 2
    assert summary["account_exists"] == "yes"
    assert summary["registration_status"] == "in_progress"
    assert summary["last_known_step"] == "section_2"
    assert summary["identifiers"][0]["type"] == "mobile"
    assert summary["identifiers"][0]["value"].endswith("3210")
    assert "987654" not in summary["identifiers"][0]["value"]


def test_unknown_stays_unknown_until_a_human_confirms(tmp_path):
    store = _store(tmp_path)
    store.record("regn.hpsc.gov.in", last_path_choice="login", confirmed_by_human=True)

    account = store.get("regn.hpsc.gov.in")

    assert account.account_exists == "unknown"
    assert account.last_path_choice == "login"
    assert account.confirmed_by_human_at


def test_invalid_account_values_are_refused(tmp_path):
    store = _store(tmp_path)

    with pytest.raises(ValueError):
        store.record("regn.hpsc.gov.in", account_exists="maybe")
    with pytest.raises(ValueError):
        store.record("regn.hpsc.gov.in", registration_status="done")
    with pytest.raises(ValueError):
        store.record("", account_exists="yes")


def test_accounts_persist_and_are_encrypted_when_a_key_is_present(tmp_path):
    import base64

    from backend.core.vault_crypto import VaultCipher

    cipher = VaultCipher(base64.b64encode(b"1" * 32).decode("ascii"))
    path = tmp_path / "portal_accounts.json"
    first = PortalAccountStore(str(path), cipher=cipher)
    first.record(
        "regn.hpsc.gov.in",
        identifier_type="mobile",
        identifier_value="9876543210",
        account_exists="yes",
    )

    raw = path.read_text(encoding="utf-8")
    assert "9876543210" not in raw
    assert json.loads(raw).get("encrypted") is True

    second = PortalAccountStore(str(path), cipher=cipher)
    account = second.get(
        "regn.hpsc.gov.in", identifier_type="mobile", identifier_value="9876543210"
    )
    assert account is not None
    assert account.account_exists == "yes"


def test_login_inspection_reads_methods_and_recovery_without_touching_the_page():
    perception = Perception(
        page_signature="sha256:login",
        url="https://regn.hpsc.gov.in/login",
        title="Sign in",
        visible_text="Sign in with mobile OTP or URN and password. Forgot password?",
        fields=[
            PerceivedField(handle="fp-1", label_text="Mobile number"),
            PerceivedField(handle="fp-2", label_text="Password", input_type="password"),
        ],
        actions=[
            PerceivedAction(handle="fp-3", text="Forgot password?", role="link"),
            PerceivedAction(handle="fp-4", text="Register", role="link"),
        ],
    )

    inspection = PortalAccountStore.inspect_login_ui(perception)

    assert inspection.read_only is True
    assert "mobile_otp" in inspection.login_methods
    assert "urn_password" in inspection.login_methods
    assert inspection.has_password is True
    assert inspection.recovery_paths == ["Forgot password?"]
    assert inspection.domain == "regn.hpsc.gov.in"


def test_api_lists_records_and_returns_masked_identifiers(client):
    put = client.put(
        "/api/portal-accounts/regn.hpsc.gov.in",
        json={
            "identifier_type": "mobile",
            "identifier_value": "9876543210",
            "account_exists": "yes",
            "registration_status": "in_progress",
        },
    )
    assert put.status_code == 200
    assert put.json()["account"]["identifier_value"].endswith("3210")

    listed = client.get("/api/portal-accounts", params={"domain": "regn.hpsc.gov.in"})
    payload = listed.json()

    assert listed.status_code == 200
    assert payload["summary"]["account_exists"] == "yes"
    assert payload["accounts"][0]["account_exists"] == "yes"
    assert "987654" not in json.dumps(payload)

    removed = client.delete(
        "/api/portal-accounts/regn.hpsc.gov.in",
        params={"identifier_type": "mobile", "identifier_value": "9876543210"},
    )
    assert removed.json()["success"] is True


def test_api_rejects_an_invalid_domain_and_account_value(client):
    bad_domain = client.put(
        "/api/portal-accounts/not a domain",
        json={"account_exists": "yes"},
    )
    bad_value = client.put(
        "/api/portal-accounts/regn.hpsc.gov.in",
        json={"account_exists": "maybe"},
    )

    assert bad_domain.status_code == 422
    assert bad_value.status_code == 422


def test_chat_reads_and_records_portal_account_memory(vault_manager):
    from backend.core.chat_assistant import FormPilotChatAssistant

    class Page:
        url = "https://regn.hpsc.gov.in/apply"

    class Orchestrator:
        page = Page()

        def get_state(self):
            return {
                "state": "RUNNING",
                "active_gate": {
                    "login_inspection": {
                        "login_methods": ["mobile_otp"],
                        "read_only": True,
                    }
                },
                "portal_account": {"account_exists": "unknown", "accounts": 0},
            }

    assistant = FormPilotChatAssistant(
        orchestrator=Orchestrator(),
        vault_mgr=vault_manager,
    )

    read = asyncio.run(assistant._execute_tool("get_portal_account", {}))
    written = asyncio.run(
        assistant._execute_tool("remember_portal_account", {"account_exists": "yes"})
    )

    assert read["ok"] is True
    assert read["account"]["account_exists"] == "unknown"
    assert written["ok"] is True
    assert written["account"]["account_exists"] == "yes"
    assert written["account"]["identifier_value"] == ""
