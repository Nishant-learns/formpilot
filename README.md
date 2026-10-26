# FormPilot

**A guided application assistant for public recruitment and admission forms.**

FormPilot helps a candidate fill long official forms from one saved profile, review every section before continuing, and stop safely before payment or final submission. It is an independent project: it is **not** a government website and it never submits an application or makes a payment on the candidate's behalf.

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-teal.svg)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-19-cyan.svg)](https://react.dev)
[![Playwright](https://img.shields.io/badge/Playwright-1.45%2B-green.svg)](https://playwright.dev)
[![TinyFish](https://img.shields.io/badge/TinyFish-Search%20%C2%B7%20Fetch%20%C2%B7%20Cloud%20Browser-blue.svg)](https://tinyfish.ai)
[![License](https://img.shields.io/badge/License-MIT-amber.svg)](LICENSE)

---

## Why FormPilot

Public application forms are repetitive and unforgiving. A single mismatched name, an expired category certificate, or an incorrectly sized photograph can invalidate an application after hours of work.

FormPilot reduces that risk with a simple loop:

1. **Find the official portal.** A curated registry resolves common recruitment bodies; unknown requests can be checked with TinyFish Search. Non-government links are flagged before they are opened.
2. **Fill from a saved profile.** A single candidate profile supplies identity, contact, address, academic, and custom fields. Confirmation fields such as “Verify Name” and “Confirm Email” stay in sync.
3. **Review each section.** The run pauses after every section. The candidate sees a live screenshot and a field-level audit, then approves, corrects a detail, or stops.
4. **Stop before payment or submission.** FormPilot never clicks a payment or final-submit button. The final screen is a handover with the filled details and the official portal still open.

The included practice portal lets judges and new contributors try the complete flow safely, including CAPTCHA and OTP checkpoints, without touching a real government site.

---

## What is included

| Area | Capability |
|---|---|
| **Portal resolution** | Registry of official recruitment and admission portals, direct-URL domain checks, and optional live search through TinyFish |
| **Guided filling** | Semantic DOM scanner, dual confirmation fields, custom portal fields, missing-field prompts, error detection |
| **Human checkpoints** | Gateway choice, missing field, CAPTCHA, OTP, section approval, and a pre-payment / final-submission safety stop |
| **Candidate profile** | One reusable profile with nested academic records, custom fields, and masked sensitive values |
| **Document preparation** | Deterministic photo and signature compression to common portal ranges (20–50 KB / 350×350 px and 10–20 KB / 140×60 px) |
| **Assistant** | Candidate-facing chat for common questions, saved-detail corrections, status, pause/resume, and live web results |
| **Run journal** | Local JSONL events, run metadata, and the final audit for support and review |
| **Deployment controls** | Optional API token, protected uploads, redacted configuration, optional AES-256-GCM profile encryption |
| **Practice portal** | A clearly labelled demo site with new-registration and returning-candidate routes |

---

## Architecture

```mermaid
flowchart TD
    Candidate["Candidate cockpit<br/>(React + Vite)"] -->|REST + WebSocket| API["FastAPI server"]
    API --> Oracle["Portal resolver<br/>registry + domain checks + TinyFish Search"]
    Oracle --> Orchestrator["Run orchestrator"]
    Orchestrator --> Scanner["Semantic DOM scanner"]
    Scanner --> Registry["Field registry"]
    Registry --> Vault["Candidate profile<br/>local JSON or encrypted envelope"]
    Orchestrator -->|CDP when configured| Cloud["TinyFish cloud browser"]
    Orchestrator -->|always available| Local["Local Chromium"]
    Cloud --> Portal["Official application portal"]
    Local --> Portal
    Orchestrator --> Gates["Human checkpoints"]
    Gates --> Candidate
    Orchestrator --> Journal["Run journal<br/>events + audit"]
```

The orchestrator is portal-agnostic. A small adapter supplies hints for the practice portal (current step, payment screen, next button), while the DOM scanner and field registry handle ordinary HTML forms.

### Human checkpoints

FormPilot pauses at the following points:

- **Gateway choice** — new registration or returning candidate.
- **Missing field** — a detail is required but not saved; the candidate enters it once.
- **CAPTCHA** — the candidate solves the challenge; it is never sent to a third party.
- **OTP** — the candidate enters the code; it is not stored in the profile.
- **Section approval** — the candidate reviews the screenshot and audit before advancing.
- **Pre-payment safety stop** — FormPilot stops and hands control back. It does not click payment or final-submit buttons.

---

## TinyFish integration

FormPilot uses TinyFish as an optional web-data and browser layer. A key is **not** required for the local practice flow; without one, FormPilot uses the built-in registry and local Chromium and says so in the activity log.

| Purpose | Request |
|---|---|
| **Search** — find an official notification or portal | `GET https://api.search.tinyfish.ai?query=...&location=IN` |
| **Fetch** — read a page as clean content | `POST https://api.fetch.tinyfish.ai` with `{"urls": ["..."], "format": "markdown"}` |
| **Cloud browser** — obtain a CDP session | `POST https://api.browser.tinyfish.ai` with `{"url": "...", "proxy_config": {"country_code": "IN"}}` |
| **Session cleanup** | `DELETE https://api.browser.tinyfish.ai/{session_id}` |
| **Wallet** (read-only) | `GET https://agent.tinyfish.ai/v1/wallet` |

All requests send the key in the `X-API-Key` header. The key is read from `TINYFISH_API_KEY` or the in-app connection settings. It is never returned by the API: configuration responses show `***` and a boolean “configured” flag.

### Cloud browser or local browser?

- **Local mode** always uses Playwright's Chromium on the same machine. This is the default for the practice portal and for `127.0.0.1` / `localhost` targets.
- **Auto mode** uses the TinyFish cloud browser for public `https://` targets when a key is configured, otherwise it falls back to local Chromium.
- **Cloud mode** requests a TinyFish browser session for public targets. If the session cannot be created, the run continues locally and the activity log labels the fallback. The app never presents a local browser as a cloud session.

Cloud browser sessions are metered by TinyFish. Use them deliberately, and check the wallet endpoint in **Settings → TinyFish connection** before a long run.

---

## Quickstart

### Requirements

- Python 3.11 or newer
- Node.js 20 or newer
- A Chromium browser for Playwright

### Recommended setup

```bash
git clone https://github.com/Nishant-learns/formpilot.git
cd formpilot

./scripts/bootstrap.sh
```

The bootstrap script creates `.venv`, installs backend and frontend dependencies, downloads Chromium, copies `.env.example` to `.env` if needed, and builds the frontend.

Start the app:

```bash
./run.sh
```

Open **http://127.0.0.1:8000**. The practice portal is at **http://127.0.0.1:8000/gov-portal-demo**.

### Manual setup

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
python -m playwright install chromium

cp .env.example .env
# Optional: add TINYFISH_API_KEY to .env for live search and cloud browser sessions.

npm ci --prefix frontend
npm run build --prefix frontend
./run.sh
```

`run.sh` loads `.env` when present, prefers `.venv`, and binds to `127.0.0.1:8000` by default. Use `FORMPILOT_HOST` and `FORMPILOT_PORT` to change that.

---

## Practice demo

The practice portal is a **fictional demo**, not a government website. It uses dummy details only and never contacts a real portal.

| Item | Value |
|---|---|
| New registration | Open `/gov-portal-demo`, choose **New registration** |
| Returning candidate | Registration `FP-2026-881902`, password `Practice@123` |
| Demo CAPTCHA | `7X9KP` (registration form), `4X9K` (login) |
| Demo OTP | `492015` |
| Demo profile | `Aman Kumar Sharma` / `demo.candidate@example.com` |

The values are shown in the practice UI so the flow can be tested without external services. They are not real credentials.

Reset the local demo after experimenting:

```bash
python scripts/reset_demo.py
```

This restores the fictional profile, removes practice registrations, clears run journals, and deletes generated photo/signature files. It does not touch `.env` or source code.

### What the demo exercises

- Portal lookup and domain verification
- Gateway choice between new registration and login
- Field filling from the saved profile
- Missing-field and CAPTCHA checkpoints
- OTP relay through the configured ntfy topic (or the demo code)
- Section approval with a screenshot and audit
- Pre-payment handover with a field-by-field match count

The full flow can also be driven from a terminal after the server is running:

```bash
python scripts/e2e_demo.py                    # new registration
python scripts/e2e_demo.py --login            # returning candidate
python scripts/e2e_demo.py http://127.0.0.1:8000/gov-portal-demo
```

---

## Configuration

Copy `.env.example` to `.env` and adjust as needed. Important variables:

| Variable | Default | Purpose |
|---|---|---|
| `FORMPILOT_ENV` | `demo` | `demo` or `production` |
| `FORMPILOT_DEMO_MODE` | `true` in demo | Enables demo conveniences |
| `FORMPILOT_ENABLE_SIMULATOR` | `true` in demo | Serves the practice portal |
| `FORMPILOT_HOST` / `FORMPILOT_PORT` | `127.0.0.1` / `8000` | Bind address for `run.sh` |
| `TINYFISH_API_KEY` | empty | Enables live search, fetch, and cloud browser sessions |
| `TINYFISH_MODE` | `auto` | `auto`, `local`, or `cloud` |
| `TINYFISH_PROXY_COUNTRY` | `IN` | Two-letter region for cloud browser sessions |
| `TINYFISH_TIMEOUT_SECONDS` | `90` | Cloud browser session timeout |
| `FORMPILOT_AUTH_TOKEN` | empty | Require a shared token for API, WebSocket, and uploads |
| `FORMPILOT_VAULT_KEY` | empty | Base64 32-byte key for AES-256-GCM profile encryption |
| `FORMPILOT_MASK_PII` | `false` | Mask sensitive values in API responses |
| `FORMPILOT_NTFY_TOPIC` | `formpilot_demo_otp` | ntfy topic used by the OTP relay |
| `FORMPILOT_DEMO_OTP` | `492015` | Fallback code for the practice flow |

Generate a profile-encryption key:

```bash
python scripts/generate_vault_key.py
```

Changing or losing `FORMPILOT_VAULT_KEY` makes an encrypted profile unreadable. Back up the key separately from the profile file.

---

## API overview

The cockpit uses these endpoints; the full schema is available at **http://127.0.0.1:8000/docs**.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/health` | Health, demo status, TinyFish configuration status |
| `GET` | `/api/oracle/search?q=...&live=false` | Resolve a portal from the registry or a direct URL |
| `GET` | `/api/oracle/directory` | List the verified portal registry |
| `GET` / `POST` | `/api/vault` | Read or update the candidate profile |
| `POST` | `/api/vault/custom-field` | Add a portal-specific field |
| `POST` | `/api/vault/reset` | Restore the demo profile (demo mode only) |
| `POST` | `/api/biometrics/compress-photo` | Compress a photograph |
| `POST` | `/api/biometrics/compress-signature` | Compress a signature |
| `POST` | `/api/agent/start` | Start a guided run |
| `GET` | `/api/agent/state` | Current state and active checkpoint |
| `POST` | `/api/agent/user-response` | Answer an open checkpoint |
| `POST` | `/api/agent/stop` | Stop the run |
| `POST` | `/api/chat/message` | Ask FormPilot a question |
| `GET` | `/api/runs` | List local run journals |
| `WS` | `/ws/cockpit` | Live events, screenshots, and chat |

When `FORMPILOT_AUTH_TOKEN` is set, every `/api/*` route except health and the practice portal, plus `/uploads/*`, requires the token as `X-API-Token`, `Authorization: Bearer ...`, or the `token` query parameter for WebSocket connections.

---

## Testing

Install the development dependencies and run the backend suite:

```bash
pip install -r requirements-dev.txt
pytest
```

The default suite covers the field registry, profile persistence and encryption, portal resolution, TinyFish request handling, assistant behaviour, biometrics, API security, run journals, and the practice portal. The browser-based end-to-end test is opt-in:

```bash
# Start the app in one terminal
./run.sh

# In another terminal
FORMPILOT_E2E_URL=http://127.0.0.1:8000/gov-portal-demo pytest -m e2e
```

Run the quick API smoke test:

```bash
python scripts/smoke_test.py
```

Build the frontend:

```bash
npm ci --prefix frontend
npm run build --prefix frontend
```

CI runs the backend tests and the frontend production build on every push and pull request.

---

## Security and privacy

FormPilot is designed for local-first use with a clear demo/production boundary.

- **No secrets in the repository.** API keys are read from the environment or entered in the settings dialog. Configuration responses redact the key and never include a preview.
- **Runtime data is ignored.** The profile, engine configuration, practice registrations, run journals, uploads, and `.env` files are excluded from git. Only example files are tracked.
- **Sensitive values are masked.** API views can mask Aadhaar numbers, passwords, and phone numbers. The audit and support exports use the same masking rules.
- **The profile can be encrypted at rest.** Set `FORMPILOT_VAULT_KEY` to store an AES-256-GCM envelope instead of plaintext JSON.
- **Uploads are constrained.** Image type and size are validated, file names are checked, and `/uploads/*` is protected when authentication is enabled.
- **The API can be gated.** Set a long random `FORMPILOT_AUTH_TOKEN` before exposing the app beyond localhost.
- **The demo is fictional.** The default profile uses reserved example domains and clearly fictional identifiers. It is not a real candidate's data.
- **No payments and no automatic submission.** The run stops at the payment or final-submission screen. The candidate completes payment and final submission directly on the official portal.

For a shared deployment, also use HTTPS behind a reverse proxy, a private ntfy topic, a strong auth token, encrypted storage, and a production process manager. Disable the practice portal with `FORMPILOT_ENABLE_SIMULATOR=false` outside demos.

---

## Project structure

```text
formpilot/
├── backend/
│   ├── main.py                 # FastAPI app, auth, REST/WebSocket, static frontend
│   ├── core/
│   │   ├── orchestrator.py     # Guided run loop and human checkpoints
│   │   ├── dom_scanner.py      # Semantic field detection and safe DOM updates
│   │   ├── field_registry.py   # Canonical field keys and vault resolution
│   │   ├── vault.py            # Candidate profile and persistence
│   │   ├── vault_crypto.py     # Optional AES-256-GCM envelope
│   │   ├── oracle.py           # Portal registry and domain checks
│   │   ├── tinyfish_client.py  # Search, Fetch, Browser, and Wallet clients
│   │   ├── chat_assistant.py   # Candidate-facing assistant
│   │   ├── biometrics.py       # Photo and signature compression
│   │   ├── navigator.py        # Resilient navigation helpers
│   │   ├── portal_adapter.py   # Portal-specific step and button hints
│   │   ├── run_store.py        # Local event and audit journal
│   │   ├── otp_service.py      # OTP relay
│   │   └── settings.py         # Environment-backed configuration
│   └── simulator/portal.py     # Practice portal and demo endpoints
├── frontend/
│   ├── src/                    # React cockpit
│   └── dist/                   # Built assets served by FastAPI
├── data/                       # Runtime data (ignored; examples tracked)
├── scripts/                    # Bootstrap, reset, smoke test, E2E driver
├── tests/                      # Backend test suite
├── .env.example
├── requirements.txt
├── requirements-dev.txt
└── run.sh
```

---

## Limitations

- FormPilot depends on the structure of the page it is filling. A major portal redesign can require an update to the DOM classifier or a portal adapter.
- CAPTCHA and OTP steps always require the candidate. FormPilot does not solve them automatically.
- The portal registry is intentionally small and auditable. Unknown portals are verified from a direct URL or left unverified.
- TinyFish Search results are evidence, not confirmation. Always check the official notification and eligibility rules.
- Cloud browser sessions are metered and depend on TinyFish availability; local Chromium remains the fallback.
- The practice portal is for demonstration and testing only. It must not be presented as a real government service.

---

## Contributing

Issues and pull requests are welcome. Before opening a pull request:

```bash
pytest
npm run build --prefix frontend
```

Please keep test data fictional, never commit a real API key or candidate's personal data, and add a test for any change to the field registry, portal resolution, or checkpoint behaviour.

## License

MIT. See [LICENSE](LICENSE).
