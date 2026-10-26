"""Guards against accidental legacy branding, internal notes, or secrets.

The scan covers files that are served to users or published in the repository.
Test files are excluded because they contain negative assertions by design.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PUBLIC_PATHS = [
    ROOT / "backend",
    ROOT / "frontend" / "src",
    ROOT / "frontend" / "index.html",
    ROOT / "scripts",
    ROOT / "README.md",
    ROOT / ".env.example",
    ROOT / "run.sh",
    ROOT / "pytest.ini",
]

# Split the most sensitive legacy names so this guard does not republish them.
BANNED_TERMS = [
    "sar" + "kari",
    "cyber" + "bhaiya",
    "cyber" + "walebhaiya",
    "applyos",
    "bharatpilot",
    "stealth",
    "tetra",
    "gazette",
    "forensic",
    "quarantine",
    "hostile",
    "anti-bot",
    "residential proxy",
    "geofence",
    "captcha farming",
    "captcha bypass",
]

PUBLIC_SUFFIXES = {
    ".py",
    ".jsx",
    ".js",
    ".html",
    ".md",
    ".sh",
    ".ini",
    ".example",
    ".txt",
    ".json",
}


def _public_files():
    for path in PUBLIC_PATHS:
        if path.is_file():
            yield path
        elif path.is_dir():
            for child in path.rglob("*"):
                if child.is_file() and "__pycache__" not in child.parts:
                    yield child


def test_no_legacy_or_internal_language_in_public_files():
    violations = []
    for path in _public_files():
        if path.suffix.lower() not in PUBLIC_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
        for term in BANNED_TERMS:
            if term in text:
                violations.append(f"{path.relative_to(ROOT)}: {term}")
    assert not violations, "Legacy/internal language found:\n" + "\n".join(violations)


def test_demo_identity_uses_reserved_example_values():
    vault_source = (ROOT / "backend" / "core" / "vault.py").read_text(encoding="utf-8")

    assert "demo.candidate@example.com" in vault_source
    assert "Aman Kumar Sharma" in vault_source
    assert "123456789012" in vault_source


def test_no_api_keys_are_checked_in():
    pattern = re.compile(r"(?:sk-tinyfish-|tf_live_|tf_test_)[A-Za-z0-9_-]{12,}")
    violations = []
    for path in _public_files():
        if path.suffix.lower() not in PUBLIC_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if pattern.search(text):
            violations.append(str(path.relative_to(ROOT)))
    assert not violations, "Possible API key found in: " + ", ".join(violations)


def test_readme_documents_the_real_integration():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "FormPilot" in readme
    assert "https://api.search.tinyfish.ai" in readme
    assert "https://api.browser.tinyfish.ai" in readme
    assert "https://api.fetch.tinyfish.ai" in readme
    assert "pytest" in readme
    assert "not a government website" in readme
    assert ("Sar" "kari") not in readme
