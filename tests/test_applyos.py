import asyncio
import os
import json
import pytest
from backend.core.vault import VaultManager, CandidateVault
from backend.core.oracle import SarkariOracle
from backend.core.biometrics import BiometricCompressor
from backend.core.tinyfish_client import TinyFishClient, EngineConfig
from backend.core.dom_scanner import DOMScanner
from backend.core.navigator import ResilientNavigator
from backend.core.orchestrator import CyberWaleBhaiyaOrchestrator

def test_candidate_vault_invariants():
    """Verify Candidate One-Vault loading, formatting, and extensible custom fields."""
    mgr = VaultManager.get_instance()
    vault = mgr.vault
    
    assert vault.full_name in ("Aman Kumar Sharma", "Nishant Kumar")
    assert vault.category in ("OBC-NCL", "General", "UR")
    assert vault.domicile_state in ("Bihar", "Delhi", "UP")
    assert vault.find_field_value("candidate_name") in ("Aman Kumar Sharma", "Nishant Kumar")
    assert vault.find_field_value("10th_roll") == "24108842"

    # Test custom dynamic field addition (e.g. APAAR ID)
    mgr.add_custom_field("apaar_id", "9988-7766-5544")
    assert mgr.vault.find_field_value("apaar_id") == "9988-7766-5544"
    print("✓ Candidate One-Vault invariants verified.")

def test_sarkari_oracle_consensus():
    """Verify Multi-Source Consensus Oracle and Authoritative Gov Domain Lock."""
    # Query 1: Railway
    rrb = SarkariOracle.resolve_target("apply for railway ntpc")
    assert rrb.is_gov_domain is True
    assert "rrbapply.gov.in" in rrb.target_url
    assert rrb.domain_trust_score >= 95
    assert rrb.gazette_verified is True

    # Query 2: SSC
    ssc = SarkariOracle.resolve_target("ssc cgl 2026")
    assert ssc.is_gov_domain is True
    assert "ssc.gov.in" in ssc.target_url

    # Query 3: BPSC
    bpsc = SarkariOracle.resolve_target("bpsc bihar")
    assert bpsc.is_gov_domain is True
    assert "onlinebpsc.bihar.gov.in" in bpsc.target_url

    # Query 4: Third-party aggregator interception
    agg = SarkariOracle.resolve_target("https://www.sarkariresult.com/railway/rrb-ntpc/")
    assert agg.is_gov_domain is True
    assert "rrbapply.gov.in" in agg.target_url  # Redirected away from ad-heavy aggregator to official deep link!
    
    print("✓ Sarkari Result Oracle consensus and domain locks verified.")

def test_deterministic_biometrics():
    """Verify strict Pillow binary search compression for signatures and photographs."""
    BiometricCompressor.generate_sample_assets()
    
    # Read generated assets
    uploads_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
    photo_p = os.path.join(uploads_dir, "candidate_photo.jpg")
    sig_p = os.path.join(uploads_dir, "candidate_signature.jpg")
    
    with open(photo_p, "rb") as f:
        photo_bytes = f.read()
    with open(sig_p, "rb") as f:
        sig_bytes = f.read()

    # Photograph: must be 20KB - 50KB JPEG, 350x350
    photo_res = BiometricCompressor.compress_photograph(photo_bytes)
    assert photo_res["success"] is True
    assert 20.0 <= photo_res["compressed_size_kb"] <= 50.0
    assert photo_res["dimensions"] == "350x350 px"
    assert photo_res["in_spec"] is True

    # Signature: must be 10KB - 20KB JPEG, 140x60
    sig_res = BiometricCompressor.compress_signature(sig_bytes)
    assert sig_res["success"] is True
    assert 10.0 <= sig_res["compressed_size_kb"] <= 20.0
    assert sig_res["dimensions"] == "140x60 px"
    assert sig_res["in_spec"] is True

    print("✓ Deterministic biometric compression pipeline verified within strict portal limits.")

def test_tinyfish_configuration():
    """Verify TinyFish Cloud Browser config and connection diagnostics."""
    client = TinyFishClient()
    cfg = client.config
    assert cfg.mode in ("local", "tinyfish")
    assert cfg.proxy_region in ("in", "us", "auto")
    
    # Test connection without API key should cleanly activate TinyFish managed proxy profile
    res = asyncio.run(client.test_connection(api_key=""))
    assert res["success"] is True
    assert "TinyFish Architecture Active" in res["message"]
    print("✓ TinyFish Cloud Browser adapter & config verified.")

def test_dom_scanner_classification():
    """Verify semantic classification of dual confirmation pairs and dynamic fields."""
    # Test Full Name primary and verify
    assert DOMScanner.classify_field({"id": "candidateName", "name": "candidateName", "label": "Full Name"}) == ("full_name", False)
    assert DOMScanner.classify_field({"id": "verifyCandidateName", "name": "verifyCandidateName", "label": "Verify Name"}) == ("verify_full_name", True)

    # Test Father Name primary and verify
    assert DOMScanner.classify_field({"id": "txtFather", "label": "Father's Name"}) == ("father_name", False)
    assert DOMScanner.classify_field({"id": "confirmFatherName", "label": "Re-enter Father's Name"}) == ("verify_father_name", True)

    # Test Mobile and Email
    assert DOMScanner.classify_field({"name": "mobile", "label": "Mobile 10 digits"}) == ("mobile", False)
    assert DOMScanner.classify_field({"name": "confirmEmail", "label": "Confirm Email ID"}) == ("confirm_email", True)

    # Test Custom APAAR ID
    assert DOMScanner.classify_field({"id": "apaar_id", "label": "APAAR ID"}) == ("apaar_id", False)
    print("✓ Semantic classification & dual confirmation pairs verified.")

if __name__ == "__main__":
    print("\n=======================================================")
    print("RUNNING COMPLETE APPLYOS (BHARATPILOT) INVARIANT AUDIT")
    print("=======================================================\n")
    test_candidate_vault_invariants()
    test_sarkari_oracle_consensus()
    test_deterministic_biometrics()
    test_tinyfish_configuration()
    test_dom_scanner_classification()
    print("\n>>> ALL ARCHITECTURAL INVARIANTS PASSED AUDIT WITH 100% SUCCESS <<<")
