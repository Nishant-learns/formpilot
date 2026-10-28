"""Shared test setup.

Environment variables are set before any backend module is imported so the
application uses a disposable data directory instead of the developer's real
vault, uploads, or run journals.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

_TEST_ROOT = Path(tempfile.mkdtemp(prefix="formpilot-tests-"))
os.environ["FORMPILOT_ENV"] = "demo"
os.environ["FORMPILOT_DEMO_MODE"] = "true"
os.environ["FORMPILOT_ENABLE_SIMULATOR"] = "true"
os.environ["FORMPILOT_DATA_DIR"] = str(_TEST_ROOT / "data")
os.environ["FORMPILOT_UPLOADS_DIR"] = str(_TEST_ROOT / "uploads")
os.environ["FORMPILOT_RUNS_DIR"] = str(_TEST_ROOT / "runs")
os.environ["FORMPILOT_AUTH_TOKEN"] = ""
os.environ["FORMPILOT_VAULT_KEY"] = ""
os.environ["FORMPILOT_NTFY_TOPIC"] = "formpilot_test_otp"
os.environ["FORMPILOT_DEMO_OTP"] = "492015"
os.environ["TINYFISH_API_KEY"] = ""
os.environ["TINYFISH_MODE"] = "local"
# Tests exercise the deterministic fallback unless they inject a fake model.
os.environ["FORMPILOT_LLM_API_KEY"] = ""
os.environ["OPENAI_API_KEY"] = ""
os.environ["FORMPILOT_LLM_BASE_URL"] = "https://api.openai.com/v1"
os.environ["FORMPILOT_LLM_MODEL"] = "gpt-4o-mini"

for _directory in (
    _TEST_ROOT / "data",
    _TEST_ROOT / "uploads",
    _TEST_ROOT / "runs",
):
    _directory.mkdir(parents=True, exist_ok=True)


def pytest_sessionfinish(session, exitstatus):  # pragma: no cover - cleanup hook
    shutil.rmtree(_TEST_ROOT, ignore_errors=True)


import pytest  # noqa: E402  (import after environment setup)


@pytest.fixture(autouse=True)
def clean_facts_store():
    """Give every test an empty semantic fact store."""
    from backend.core import settings
    from backend.core.facts import FactBook

    FactBook.reset_instance()
    (settings.DATA_DIR / "facts.json").unlink(missing_ok=True)
    yield
    FactBook.reset_instance()
    (settings.DATA_DIR / "facts.json").unlink(missing_ok=True)


@pytest.fixture()
def vault_manager(tmp_path):
    """An isolated vault backed by a temporary file."""
    from backend.core.vault import VaultManager

    manager = VaultManager(str(tmp_path / "candidate_vault.json"))
    manager.reset_defaults()
    return manager


@pytest.fixture()
def client():
    """FastAPI test client with a fresh demo profile for each test."""
    from fastapi.testclient import TestClient

    from backend.main import app, chat_assistant, vault_mgr

    vault_mgr.reset_defaults()
    chat_assistant.chat_history.clear()
    with TestClient(app) as test_client:
        yield test_client
