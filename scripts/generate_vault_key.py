"""Print a random 32-byte base64 key for FORMPILOT_VAULT_KEY."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.core.vault_crypto import generate_key_b64


if __name__ == "__main__":
    print(generate_key_b64())
