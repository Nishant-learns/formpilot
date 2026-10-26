"""Quick local smoke test. Run after starting the server:

    python scripts/smoke_test.py

The script uses the FastAPI test client, so it does not need a running
network port, but it does execute the app's startup/shutdown lifecycle.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from backend.main import app


def main() -> None:
    with TestClient(app) as client:
        health = client.get("/api/health")
        health.raise_for_status()
        payload = health.json()
        assert payload["status"] == "ok"
        assert payload["app"] == "FormPilot"

        oracle = client.get("/api/oracle/search", params={"q": "railway", "live": "false"})
        oracle.raise_for_status()
        portal = oracle.json()
        assert "rrbapply.gov.in" in portal["target_url"]

        config = client.get("/api/engine/config").json()
        assert config["tinyfish_api_key"] in {"", "***"}
        assert "browser_profile" not in config
        assert "proxy_type" not in config

        page = client.get("/gov-portal-demo")
        page.raise_for_status()
        assert "not a government website" in page.text

    print("Smoke test passed: health, oracle, config redaction, practice portal.")


if __name__ == "__main__":
    main()
