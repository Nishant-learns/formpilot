"""Vault persistence, formatting, masking, and optional encryption."""

from __future__ import annotations

import json

from backend.core.vault import CandidateVault, VaultManager
from backend.core.vault_crypto import generate_key_b64


def test_demo_defaults_are_fictional_and_internally_consistent(vault_manager):
    vault = vault_manager.vault

    assert vault.full_name == "Aman Kumar Sharma"
    assert vault.email == "demo.candidate@example.com"
    assert vault.aadhaar_number == "123456789012"
    assert vault.registration_id == "FP-2026-881902"
    assert vault.account_password == "Practice@123"
    assert vault.get_formatted_dob("DD/MM/YYYY") == "15/08/2003"
    assert vault.find_field_value("matric_roll_number") == vault.matric.roll_number


def test_updates_persist_and_alias_keys_resolve(vault_manager, tmp_path):
    vault_manager.set_semantic_field("matric_roll_number", "99887766")
    vault_manager.add_custom_field("APAAR ID", "9999-8888-7777")

    reloaded = VaultManager(str(tmp_path / "candidate_vault.json"))

    assert reloaded.vault.matric.roll_number == "99887766"
    assert reloaded.vault.custom_fields["apaar_id"] == "9999-8888-7777"
    assert reloaded.vault.find_field_value("10th_roll") == "99887766"


def test_generic_update_merges_custom_fields(vault_manager):
    vault_manager.update({"father_name": "Rajesh Kumar Sharma"})
    vault_manager.update({"custom_fields": {"height_cm": "175"}})
    vault_manager.update({"new_portal_code": "ABC-123"})

    assert vault_manager.vault.father_name == "Rajesh Kumar Sharma"
    assert vault_manager.vault.custom_fields["height_cm"] == "175"
    assert vault_manager.vault.custom_fields["new_portal_code"] == "ABC-123"


def test_public_view_masks_sensitive_values(vault_manager):
    public = vault_manager.vault.public_dict(mask_sensitive=True)

    assert public["full_name"] == "Aman Kumar Sharma"
    assert public["aadhaar_number"].endswith("9012")
    assert set(public["aadhaar_number"][:-4]) == {"*"}
    assert public["account_password"].endswith("@123")
    assert public["mobile"].endswith("3210")


def test_plaintext_vault_is_readable_json(vault_manager, tmp_path):
    raw = (tmp_path / "candidate_vault.json").read_text(encoding="utf-8")
    data = json.loads(raw)
    assert data["full_name"] == "Aman Kumar Sharma"
    assert "encrypted" not in data


def test_encrypted_vault_round_trip(monkeypatch, tmp_path):
    monkeypatch.setenv("FORMPILOT_VAULT_KEY", generate_key_b64())
    path = tmp_path / "encrypted_vault.json"

    manager = VaultManager(str(path))
    manager.set_semantic_field("mobile", "9000000001")

    raw = path.read_text(encoding="utf-8")
    assert json.loads(raw)["encrypted"] is True
    assert "Aman Kumar Sharma" not in raw
    assert "9000000001" not in raw

    reloaded = VaultManager(str(path))
    assert reloaded.vault.full_name == "Aman Kumar Sharma"
    assert reloaded.vault.mobile == "9000000001"
    assert isinstance(reloaded.vault, CandidateVault)


def test_missing_vault_creates_defaults(tmp_path):
    path = tmp_path / "does-not-exist.json"
    manager = VaultManager(str(path))

    assert path.exists()
    assert manager.vault.full_name == "Aman Kumar Sharma"
