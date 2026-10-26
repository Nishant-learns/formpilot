"""Reset the local demo to a clean, fictional candidate profile.

This removes only runtime state: the saved profile, practice-portal
registrations, generated run journals, and prepared photo/signature files.
It never touches the source code or your `.env`.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.core import settings
from backend.core.vault import VaultManager


def main() -> None:
    settings.ensure_directories()

    manager = VaultManager.get_instance()
    manager.reset_defaults()

    for name in ("portal_registrations.json",):
        path = settings.DATA_DIR / name
        if path.exists():
            path.unlink()

    if settings.RUNS_DIR.exists():
        shutil.rmtree(settings.RUNS_DIR, ignore_errors=True)
    settings.RUNS_DIR.mkdir(parents=True, exist_ok=True)

    for name in (
        "candidate_photo.jpg",
        "candidate_signature.jpg",
        "compressed_photo.jpg",
        "compressed_signature.jpg",
    ):
        path = settings.UPLOADS_DIR / name
        if path.exists():
            path.unlink()

    print("Demo reset.")
    print(f"  Profile: {settings.VAULT_FILE}")
    print(f"  Practice login: {manager.vault.registration_id} / {manager.vault.account_password}")
    print("  Practice CAPTCHA: 7X9KP (form), 4X9K (login)")
    print(f"  Demo OTP: {settings.DEMO_OTP}")


if __name__ == "__main__":
    main()
