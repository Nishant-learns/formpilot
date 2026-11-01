"""Comprehensive unit tests for enterprise hardening components:
1. SSRFGuard: Multi-layer IP/DNS blocking and cloud metadata defense.
2. AuditHashChain: Cryptographic Merkle hash-chaining and tamper verification.
3. PIISanitizer: Recursive PII scrubbing for Aadhaar, PAN, phone, email, and credentials.
4. CircuitBreaker: Three-state resilience and fail-fast threshold mechanics.
5. IdempotencyEngine: Exactly-once execution and concurrent replay caching.
"""

from __future__ import annotations

import asyncio
import time
import pytest

from backend.core.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    CircuitState,
)
from backend.core.idempotency import (
    IdempotencyConflictError,
    IdempotencyEngine,
    IdempotencyStatus,
)
from backend.core.security_hardening import (
    GENESIS_HASH,
    AuditHashChain,
    PIISanitizer,
    SSRFGuard,
)


# ---------------------------------------------------------------------------
# SSRFGuard Tests
# ---------------------------------------------------------------------------

def test_ssrf_blocks_cloud_metadata():
    safe, msg = SSRFGuard.is_safe_url("http://169.254.169.254/latest/meta-data/")
    assert safe is False
    assert "metadata" in msg.lower() or "blocked" in msg.lower()


def test_ssrf_blocks_private_subnets():
    # RFC 1918 10.0.0.0/8
    safe, _ = SSRFGuard.is_safe_url("http://10.0.0.1/admin")
    assert safe is False

    # RFC 1918 192.168.0.0/16
    safe, _ = SSRFGuard.is_safe_url("http://192.168.1.100:8080/metrics")
    assert safe is False

    # RFC 1918 172.16.0.0/12
    safe, _ = SSRFGuard.is_safe_url("https://172.20.1.5/")
    assert safe is False


def test_ssrf_blocks_loopback_unless_explicitly_permitted():
    # Strict mode (production default): loopback blocked
    safe, _ = SSRFGuard.is_safe_url("http://127.0.0.1:8000/api")
    assert safe is False

    safe, _ = SSRFGuard.is_safe_url("http://localhost:8000/api")
    assert safe is False

    # Local simulator mode: loopback permitted
    safe, _ = SSRFGuard.is_safe_url("http://127.0.0.1:8000/gov-portal-demo", allow_local_simulator=True)
    assert safe is True

    # Cloud metadata is NEVER permitted even with allow_local_simulator=True
    safe, _ = SSRFGuard.is_safe_url("http://169.254.169.254/meta-data", allow_local_simulator=True)
    assert safe is False


def test_ssrf_blocks_dangerous_schemes():
    safe, msg = SSRFGuard.is_safe_url("file:///etc/passwd")
    assert safe is False
    assert "scheme" in msg.lower()

    safe, msg = SSRFGuard.is_safe_url("ftp://internal.server/data")
    assert safe is False
    assert "scheme" in msg.lower()

    safe, msg = SSRFGuard.is_safe_url("gopher://127.0.0.1:70")
    assert safe is False


def test_ssrf_permits_legitimate_public_urls(monkeypatch):
    # Verify public domain validation with deterministic resolved IP
    monkeypatch.setattr(
        SSRFGuard,
        "resolve_dns_and_check",
        lambda hostname: (True, ["93.184.216.34"], ""),
    )
    safe, _ = SSRFGuard.is_safe_url("https://gov-portal-simulator.vercel.app")
    assert safe is True

    safe, _ = SSRFGuard.is_safe_url("https://example.com/admit-card")
    assert safe is True


# ---------------------------------------------------------------------------
# AuditHashChain Tests
# ---------------------------------------------------------------------------

def test_audit_hash_chain_creation_and_genesis():
    chain = AuditHashChain()
    assert len(chain.entries) == 0

    entry1 = chain.append("AGENT_START", {"query": "upsc", "mode": "fill"})
    assert entry1["index"] == 0
    assert entry1["prev_hash"] == GENESIS_HASH
    assert entry1["entry_hash"] is not None

    entry2 = chain.append("FIELD_MATCH", {"field": "aadhaar", "matched": True})
    assert entry2["index"] == 1
    assert entry2["prev_hash"] == entry1["entry_hash"]

    valid, err = chain.verify()
    assert valid is True
    assert err is None


def test_audit_hash_chain_detects_payload_tampering():
    chain = AuditHashChain()
    chain.append("CHECKPOINT", {"field": "name", "val": "Aman"})
    chain.append("CHECKPOINT", {"field": "dob", "val": "2000-01-01"})

    # Tamper with first entry payload
    chain.entries[0]["data"]["val"] = "Forged Name"

    valid, err = chain.verify()
    assert valid is False
    assert "Tampered payload" in err


def test_audit_hash_chain_detects_hash_tampering():
    chain = AuditHashChain()
    chain.append("STEP_1", {"status": "ok"})
    chain.append("STEP_2", {"status": "ok"})

    # Tamper with block entry_hash
    chain.entries[0]["entry_hash"] = "f" * 64

    valid, err = chain.verify()
    assert valid is False
    assert "Tampered chain link" in err or "Forged entry hash" in err


# ---------------------------------------------------------------------------
# PIISanitizer Tests
# ---------------------------------------------------------------------------

def test_pii_sanitizer_masks_identifiers():
    raw_text = "Candidate Aman, Aadhaar: 1234 5678 9012, PAN: ABCDE1234F, Mobile: 9876543210"
    sanitized = PIISanitizer.mask_text(raw_text)

    assert "1234 5678 9012" not in sanitized
    assert "**** **** 9012" in sanitized
    assert "ABCDE1234F" not in sanitized
    assert "*****1234*" in sanitized
    assert "9876543210" not in sanitized
    assert "******3210" in sanitized


def test_pii_sanitizer_masks_nested_structures():
    nested_data = {
        "candidate": {
            "name": "Aman Sharma",
            "password": "superSecretPassword123",
            "secret_token": "token-xyz-12345",
            "contacts": [
                {"email": "aman.sharma@example.com", "phone": "9876543210"}
            ],
        }
    }
    sanitized = PIISanitizer.mask_structure(nested_data)

    assert sanitized["candidate"]["name"] == "Aman Sharma"
    assert sanitized["candidate"]["password"] == "[REDACTED]"
    assert sanitized["candidate"]["secret_token"] == "[REDACTED]"
    assert sanitized["candidate"]["contacts"][0]["phone"] == "******3210"
    assert sanitized["candidate"]["contacts"][0]["email"] == "a***@example.com"


# ---------------------------------------------------------------------------
# CircuitBreaker Tests
# ---------------------------------------------------------------------------

def test_circuit_breaker_transitions_to_open_on_threshold():
    async def _test():
        cb = CircuitBreaker("gov-portal", failure_threshold=3, recovery_timeout=0.2)
        assert cb.state == CircuitState.CLOSED

        async def fail_call():
            raise ConnectionResetError("502 Bad Gateway")

        # Record 3 failures
        for _ in range(3):
            with pytest.raises(ConnectionResetError):
                await cb.execute(fail_call)

        # Circuit should now be OPEN
        assert cb.state == CircuitState.OPEN

        # Subsequent execution must fail-fast without invoking target
        target_executed = False

        async def probe_call():
            nonlocal target_executed
            target_executed = True
            return "ok"

        with pytest.raises(CircuitBreakerOpenError) as exc_info:
            await cb.execute(probe_call)

        assert target_executed is False
        assert exc_info.value.retry_after > 0

    asyncio.run(_test())


def test_circuit_breaker_recovers_via_half_open():
    async def _test():
        cb = CircuitBreaker("gov-portal-recovery", failure_threshold=2, recovery_timeout=0.1, half_open_success_threshold=2)

        async def fail_call():
            raise TimeoutError("504 Gateway Timeout")

        for _ in range(2):
            with pytest.raises(TimeoutError):
                await cb.execute(fail_call)

        assert cb.state == CircuitState.OPEN

        # Wait for recovery timeout to elapse
        await asyncio.sleep(0.15)
        assert cb.state == CircuitState.HALF_OPEN

        async def success_call():
            return "200 OK"

        # Canary execution 1
        res1 = await cb.execute(success_call)
        assert res1 == "200 OK"
        assert cb.state == CircuitState.HALF_OPEN

        # Canary execution 2
        res2 = await cb.execute(success_call)
        assert res2 == "200 OK"
        # Should be restored to CLOSED
        assert cb.state == CircuitState.CLOSED

    asyncio.run(_test())


# ---------------------------------------------------------------------------
# IdempotencyEngine Tests
# ---------------------------------------------------------------------------

def test_idempotency_lifecycle():
    async def _test():
        engine = IdempotencyEngine()
        test_key = "submit-form-txn-12345"

        # 1. First acquisition: should succeed
        acquired, cached = await engine.acquire(test_key)
        assert acquired is True
        assert cached is None

        # 2. Concurrent duplicate request while IN_PROGRESS: should raise conflict
        with pytest.raises(IdempotencyConflictError):
            await engine.acquire(test_key)

        # 3. Complete execution
        payload = {"status": "SUCCESS", "registration_id": "UPSC-2026-9999"}
        await engine.complete(test_key, status_code=200, response_body=payload)

        # 4. Subsequent acquisition with identical key: returns cached response
        acquired, cached = await engine.acquire(test_key)
        assert acquired is False
        assert cached is not None
        assert cached.status == IdempotencyStatus.COMPLETED
        assert cached.status_code == 200
        assert cached.response_body == payload

    asyncio.run(_test())


def test_idempotency_rejects_invalid_keys():
    engine = IdempotencyEngine()
    assert engine.is_valid_key("a") is False
    assert engine.is_valid_key("valid-key-123") is True
    assert engine.is_valid_key("bad key with spaces") is False
