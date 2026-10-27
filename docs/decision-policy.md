# FormPilot Decision Policy

Status: implementation reference
Last updated: 2026-10-27

This document is the source of truth for no-guess decisions: how the agent
chooses an entry path, a login method, an account identifier, and when it may
call a form "filled". If the implementation conflicts with this file, reconcile
this file first.

## 1. Why this exists

A portal can offer several valid ways to enter: create a new account, sign in
to an existing account, resume a saved application, or continue on the page
that is already open. The agent cannot know which one belongs to the candidate
from the URL, browser history, a saved recipe, or the presence of a login form.

The same applies inside a login form: a selector may offer mobile OTP, URN and
password, or email and password. Picking the first option can lock the wrong
account or send an OTP to the wrong identifier.

FormPilot therefore separates **evidence** from **choice**:

- Evidence is what the live page shows.
- Choice belongs to the candidate.
- The agent may follow a single explicit path, but it must ask when the page
  offers two or more paths.
- The UI may only claim a form is filled when a fresh scan confirms every value
  it recorded.

## 2. Entry-path rules

Implemented in `backend/core/decision_policy.py`.

### 2.1 Detection

A clickable is an entry path when its label or `href` says so:

- register: `New Registration`, `Account Creation`, `Create Account`,
  `Create your account`, `Register`, `Sign up`, `Get Started`, `New User`,
  `First time`, `OTR`, `Apply Online`, and the Hindi equivalents.
- login: `Login`, `Log in`, `Sign in`, `Candidate Login`, `Already registered`,
  `Returning candidate`, `Existing account`.
- resume: `Resume application`, `Continue application`, `Already started`,
  `Saved application`, `Track application`, `Application status`.

Auth URLs are treated as evidence too: `/signup`, `/register`,
`/create-account`, `/login`, `/signin`, `/resume`, `/track`, and similar paths.
A form submit button is an action, not an entry path, unless its `href`
explicitly points at an auth route.

Ambiguous labels are rejected. For example, `Create Account & Login` without a
disambiguating `href` does not become either option.

### 2.2 Canonical options

Multiple links that mean the same thing are collapsed into one option per entry
type. The canonical control is chosen by a deterministic score:

1. the page that is already open wins for its own entry type,
2. href matches the expected auth path,
3. has a blueprint element id,
4. is outside a form,
5. is a button/input rather than a generic node,
6. shorter label.

This is not a guess about the candidate's intent: the candidate still chooses
register versus login versus resume. Preferring the open page also means that
choosing "login" on a login page does not re-click a navigation link that may
not change the page.

A page that is itself a login or registration form contributes a synthetic
`current_page` option. For example, a login page with a "Create Account" link
produces two options: register (the link) and login (the current page). The
agent asks instead of auto-clicking the registration link.

### 2.3 Gate behavior

- Zero options: if the page has unclassifiable entry links, open a
  `LIVE_HANDOFF` gate and ask the candidate to choose in the live browser.
- One option: follow it. A single explicit path is not a guess.
- Two or more options: open `GATEWAY_DECISION`. The gate lists the options,
  marks `requires_explicit_choice` and `no_default`, and never selects
  `options[0]`.
- A response is accepted only when it matches exactly one option by
  `element_id`, `id`, `mode`/`type`, exact text, or exact href.
- `DISMISS` is not a choice. The gate stays open.
- An unmatched response keeps the gate open with an explanation.
- A click on an entry path is verified by a real page change (URL, title,
  section, heading, input count, button count or text digest). A click that
  changes nothing is an error, not a silent success.

The chat assistant and the checkpoint panel both call the same public methods:
`choose_entry_mode`, `choose_login_method`, and `choose_account_identifier`.

## 3. Login method and identifier

### 3.1 Login method

`login_method_options` finds a visible `<select>` whose label/name/id mentions
login/method/type and whose options classify as at least two different methods.
Supported method classes:

- `mobile_otp`
- `aadhaar_otp`
- `urn_password`
- `email_password`
- `password`
- `digilocker`

If the selector has one option, the agent may select it. If it has two or more,
the agent opens a `LOGIN_METHOD` gate. The select is applied only after the
choice, and the result is verified.

### 3.2 Account identifier

`identifier_options` finds visible text/email/tel/number inputs that classify as
different identifiers: `aadhaar_number`, `registration_id`, `mobile`, `email`,
`username`. If two or more are visible on a login page, the agent opens an
`ACCOUNT_IDENTIFIER` gate.

The chosen identifier is the only identifier field FormPilot fills on that
login form. Other identifier fields are reported as skipped, not filled.

## 4. Verified fill

The UI and backend share one source of truth: `fill_summary` and
`fill_failures`.

`_fill_form()` no longer records a field when the action merely returned
success. It:

1. collects every target and the value it intends to use,
2. applies the value through the action resolver or the JS injector,
3. takes a fresh DOM scan,
4. compares the portal's actual value (and selected text for selects) with the
   expected value,
5. records only verified fields in `filled_audit`,
6. removes stale audit records for any field that failed,
7. builds `fill_summary`.

`fill_summary.status` is one of:

| Status | Meaning |
|---|---|
| `FILLED` | Every attempted field was verified and nothing was skipped. |
| `PARTIAL` | Some fields verified, but some failed or were skipped. |
| `FAILED` | No attempted field could be verified. |
| `NO_FIELDS` | The page had no fillable fields. |

When the status is `PARTIAL` or `FAILED`:

- a `FILL_INCOMPLETE` gate opens before section review,
- the gate shows verified/failed/skipped counts and per-field reasons,
- the candidate can choose `FILL_RECHECK` or `CONTINUE`,
- continuing records the section as incomplete; it is never reported as
  `FILLED`,
- the cockpit shows a warning banner,
- the pre-payment safety lock becomes `NEEDS_REVIEW`,
- the status report in chat states the real verified/failed/skipped counts.

Uploads are verified too: a file is recorded only when the fresh scan shows the
file attached to the target input.

## 5. Chat contract

Chat actions go through orchestrator public methods and report the real result:

| Message | Action |
|---|---|
| "I need to register first" while an entry gate is open | `ENTRY_MODE_SELECTED` |
| Same message before the entry page appears | `ENTRY_MODE_REQUESTED` (applied only when an explicit option appears) |
| "use mobile OTP" while a login-method gate is open | `LOGIN_METHOD_SELECTED` |
| "use my email address" while an identifier gate is open | `ACCOUNT_IDENTIFIER_SELECTED` |
| "recheck the fields" while a fill gate is open | `FILL_RECHECK` |
| "continue after reviewing" while a fill gate is open | `FILL_CONTINUE` |
| "what is my status?" | `STATUS_REPORT` with verified/failed/skipped truth |

The chat runs entry/login intents before the generic workflow, so an actionable
sentence cannot fall through to the greeting.

## 6. API and UI

- `GET /api/agent/state` exposes `entry_mode`, `entry_options`, `login_method`,
  `login_identifier`, `fill_summary`, and `fill_failures`.
- `POST /api/agent/entry-mode` accepts `register`, `login`, or `resume` and
  returns success only when the page offers that path.
- WebSocket events and chat replies carry the same fields.
- `SessionStrip` marks the details step as done only for `FILLED` or
  `NO_FIELDS`, not merely because the agent is waiting for a human.
- `HumanCheckpointModal` renders `GATEWAY_DECISION`, `LOGIN_METHOD`,
  `ACCOUNT_IDENTIFIER`, and `FILL_INCOMPLETE` explicitly.
- `LiveChat` shows entry/login badges and offers quick actions for open gates.
- Dismissing a gate is never treated as a choice.

## 7. Safety invariants

- CAPTCHA, OTP, live photo, payment, and final submission remain human-only.
- FormPilot never pays or submits an application.
- FormPilot never sees or fills PII through an AI plan; the vault supplies
  values locally.
- A response that does not match exactly one option is rejected.
- No `unique[0]`, `.first`, or `options[0]` fallback exists in the decision path.

## 8. Tests

- `tests/test_decision_policy.py`: text/href classification, dedupe, synthetic
  current-page option, exact response matching, hidden/covered rejection,
  login-method and identifier gates.
- `tests/test_chat_assistant.py`: chat entry selection, remembered entry
  requests, login-method/identifier selection, fill recheck, honest status.
- `tests/test_fill_verification.py`: verified fill, portal-cleared value fails,
  `FILL_INCOMPLETE` recheck, dismissal is not a choice.

## 9. Files

- `backend/core/decision_policy.py`
- `backend/core/orchestrator.py`
- `backend/core/chat_assistant.py`
- `backend/core/dom_scanner.py`
- `backend/core/form_model.py`
- `backend/main.py`
- `frontend/src/App.jsx`
- `frontend/src/components/SessionStrip.jsx`
- `frontend/src/components/HumanCheckpointModal.jsx`
- `frontend/src/components/LiveChat.jsx`
- `scripts/e2e_demo.py`
