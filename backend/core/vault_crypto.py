"""Optional AES-256-GCM encryption for the Candidate One-Vault.

This is deliberately opt-in: a hackathon demo should still run with a plain
JSON file.  When `FORMPILOT_VAULT_KEY` is set the vault is encrypted at rest
with a 32-byte base64 key.  Key management remains the operator's job; do not
hard-code a key in the repository.
"""

from __future__ import annotations

import base64
import json
import os
from typing import Any, Optional

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except Exception:  # pragma: no cover - cryptography is an optional dependency
    AESGCM = None  # type: ignore[assignment]


class VaultCryptoError(RuntimeError):
    pass


class VaultCipher:
    VERSION = 1

    def __init__(self, key_b64: str):
        if AESGCM is None:
            raise VaultCryptoError(
                "FORMPILOT_VAULT_KEY is set but the 'cryptography' package is not installed."
            )
        try:
            key = base64.b64decode(key_b64, validate=True)
        except Exception as exc:
            raise VaultCryptoError("FORMPILOT_VAULT_KEY must be valid base64.") from exc
        if len(key) != 32:
            raise VaultCryptoError("FORMPILOT_VAULT_KEY must decode to exactly 32 bytes for AES-256.")
        self._aes = AESGCM(key)

    def encrypt_bytes(self, plaintext: bytes) -> dict[str, Any]:
        nonce = os.urandom(12)
        ciphertext = self._aes.encrypt(nonce, plaintext, b"formpilot-vault-v1")
        return {
            "version": self.VERSION,
            "encrypted": True,
            "algorithm": "AES-256-GCM",
            "nonce": base64.b64encode(nonce).decode("ascii"),
            "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
        }

    def decrypt_bytes(self, envelope: dict[str, Any]) -> bytes:
        try:
            nonce = base64.b64decode(envelope["nonce"])
            ciphertext = base64.b64decode(envelope["ciphertext"])
        except Exception as exc:
            raise VaultCryptoError("Encrypted vault envelope is malformed.") from exc
        try:
            return self._aes.decrypt(nonce, ciphertext, b"formpilot-vault-v1")
        except Exception as exc:
            raise VaultCryptoError(
                "Could not decrypt the vault. Check FORMPILOT_VAULT_KEY."
            ) from exc


def cipher_from_env() -> Optional[VaultCipher]:
    key = os.getenv("FORMPILOT_VAULT_KEY", "").strip()
    return VaultCipher(key) if key else None


def generate_key_b64() -> str:
    return base64.b64encode(os.urandom(32)).decode("ascii")


def decode_envelope(raw: str) -> tuple[bool, dict[str, Any] | bytes]:
    """Return (is_encrypted, payload)."""
    data = json.loads(raw)
    if isinstance(data, dict) and data.get("encrypted") is True:
        return True, data
    return False, raw.encode("utf-8")
