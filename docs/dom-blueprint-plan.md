# FormPilot DOM Blueprint Plan

Status: implementation reference
Last updated: 2026-10-28 (section 16 added; earlier sections kept as history)

This file is the source of truth for the DOM-blueprint work. If an implementation
decision conflicts with this file, stop and reconcile it here first.

## 0. Implementation status (2026-10-27)

Implemented and tested:

- `backend/core/blueprint.py`: typed `BlueprintElement` / `PageBlueprint`,
  indexes, prompt tree, debug JSON, summary and legacy enrichment.
- `backend/core/dom_scanner.py`: `STRUCTURE_JS` plus `DOMScanner.scan(page)`.
  It stamps per-scan `data-fp-id` values, builds a nested tree, records
  role/name, CSS/XPath, visibility, interactability, hit-test coverage,
  options, frames and open shadow roots, then enriches the legacy lists.
- `backend/core/action_resolver.py`: blueprint-id resolution, unique-match
  validation, tag-drift check, visibility/enabled/editable checks, coverage
  check, click/fill/select/check/upload/press with structured error codes.
- `backend/core/orchestrator.py`: `_scan_dom()` now returns the legacy DOM and
  stores `self.blueprint`; `_safe_click()` resolves blueprint ids first and
  re-identifies stale controls after one re-scan; `_fill_form()` uses the
  resolver for text/select fields and keeps the injector as fallback;
  `_advance()` takes a fresh scan before clicking.
- `backend/core/form_model.py`: fields and gateways keep `element_id`, frame,
  role, CSS, XPath, element hash, visibility and coverage. Blueprint ids are
  runtime-only and are stripped from recipes.
- `backend/core/recipe.py`: gateway/next-action recipes keep durable locators
  but never per-scan ids or hit-test geometry.
- `backend/core/decision_policy.py`: deterministic entry-path, login-method and
  account-identifier decisions. A single explicit option may be followed; two
  or more options always open a human gate. There is no `options[0]` fallback.
  See `docs/decision-policy.md`.
- `backend/core/orchestrator.py` (decision + verification layer): explicit
  `GATEWAY_DECISION`, `LOGIN_METHOD`, `ACCOUNT_IDENTIFIER` and
  `FILL_INCOMPLETE` gates; real page-change verification after entry clicks and
  section advance; `fill_summary` / `fill_failures` built from a fresh scan so
  a form is never reported as filled unless the portal kept the values.
- `backend/core/chat_assistant.py`: entry/login/identifier intents and
  fill-recheck actions run before the generic workflow and report the real
  orchestrator result.
- Frontend: `SessionStrip` only marks details done for `FILLED`/`NO_FIELDS`;
  `HumanCheckpointModal` renders the new gates; `LiveChat` exposes entry/login
  quick actions and badges; `App.jsx` shows an incomplete-fill warning banner.
- Tests: `test_dom_scanner.py`, `test_action_resolver.py`,
  `test_hpsc_gateway.py`, `test_decision_policy.py`,
  `test_fill_verification.py`, plus form-model, chat and recipe coverage.

Verified live on 2026-10-27: the HPSC entry page's `Login` anchor resolves as
`a[href="/frontend/site/login"]`, role `link`, unique CSS, and clicking it
navigates to `https://regn.hpsc.gov.in/frontend/site/login`.

Not implemented yet (later phases in this document):

- AI planner/repairer and the declarative plan validator.
- Deterministic recipe replay that executes saved steps without the generic
  loop, plus element-hash drift repair.
- A custom-dropdown driver that opens the widget, re-scans and clicks a
  `role=option`.
- Full migration of CAPTCHA/OTP locators to blueprint ids. These remain
  human-only and keep their existing selectors.

## 1. Problem

The current agent scans the page into flat lists (`inputs`, `gateways`,
`nextButtons`) and clicks by visible text. That fails when:

- the control is an `<a>` rather than a `<button>` (HPSC Login),
- several nodes share the same text (`Login` appears in a link, a heading and a
  paragraph),
- the first text match is hidden, covered, or not actionable,
- the page re-renders and IDs/positions change,
- the form is inside an iframe or an open shadow root,
- a custom dropdown or a validation error changes the page.

HPSC evidence:

```html
<a href="/frontend/site/login" class="btn btn-main"> Login </a>
```

- `get_by_role("button", name="Login")` returns 0.
- `get_by_role("link", name="Login")` returns 1.
- `locator("text=Login")` returns 3 nodes.
- `_safe_click` falls back to `.first`, which is order-dependent.
- `FormModel._gateways()` drops `tagName`, `className`, `href`, `rect` and never
  carries an element ID, so the click layer receives only
  `{type, text, id: null, name: null}`.

The fix is not another text heuristic. The fix is a complete, structured DOM
blueprint and an action resolver that references unique element IDs.

## 2. Non-negotiable decisions

1. Playwright is the execution engine. Selenium is not used.
2. The DOM blueprint is the source of truth for perception.
3. Actions reference blueprint element IDs, never visible text as the first
   choice.
4. The resolver must validate exactly one match before acting. No `.first`.
5. AI is a planner/repairer, not the browser driver.
6. AI outputs declarative JSON actions, never generated code.
7. AI never sees or fills PII; the vault supplies values.
8. CAPTCHA, OTP, live photo, payment and final submission remain human-only.
9. Every successful AI plan is compiled into a deterministic recipe.
10. TinyFish (or any external agent) is an optional provider behind an
    interface, not the foundation.
11. One executor owns the live browser. External agents get a snapshot or a
    separate session and return a plan/recipe.
12. Stale recipes never override the live DOM.

## 3. Target architecture

```
page.frames + open shadow roots
        |
        v
DOM Scanner v2
  - stable per-scan IDs
  - flat index + nested tree
  - CSS / XPath / role / accessible name
  - visibility, enabled, editable, interactable
  - hit test / covered_by
  - options, frames, shadow hosts, element hash
        |
        v
PageBlueprint
  - full internal blueprint
  - compact prompt/debug view
        |
        v
ActionResolver
  - element_id -> frame -> unique locator
  - validate identity -> actionability -> act -> verify
  - stale/missing -> re-scan -> locator ladder
        |
        v
Orchestrator
  - gateway, fill, advance, human gates
        |
        v
RecipeStore v2
  - durable locators + element hashes
  - deterministic replay + drift repair
```

### Fast paths

Known portal:

```
Scan -> Blueprint -> Recipe match -> Resolver -> Verify -> Done
AI calls: 0
```

Unknown portal:

```
Scan -> Blueprint -> AI Planner -> Plan -> Validator -> Resolver
     -> Verify -> Recipe Compiler -> Done
AI calls: 1-2
```

Failure/drift:

```
Resolver diagnostics -> AI Repairer -> New Plan -> Validator
     -> Resolver -> Verify -> Recipe Update -> Done
AI calls: 1-2
```

Sensitive/ambiguous:

```
Human gate
```

## 4. Scanner v2

The scanner runs in every Playwright frame, including same-origin iframes.
It also descends into open shadow roots.

Each meaningful element gets:

- `id`: per-scan stable ID, stored in `data-fp-id` (for example
  `fp-a1b2c3-42`).
- `frame`, `frame_index`, `parent_id`, `depth`
- `tag`, `role`, accessible `name`, own `text`
- `attributes` (stable attributes only; no values/tokens)
- `css`, `css_unique`, `xpath`
- `rect`, `visible`, `in_viewport`, `enabled`, `editable`, `interactable`,
  `hover_only`
- `covered_by` from `document.elementFromPoint(center)`
- `options` for selects/listboxes
- `element_hash` (tag + role + name + stable attrs + text + options)
- `children`
- `shadow_host` when inside an open shadow root

Page-level metadata:

- URL, title, ready state, viewport, scroll position
- frames and frame URLs
- forms, dialogs, alerts
- CAPTCHA / OTP / payment signals
- mutation counter, scan ID, captured-at timestamp
- truncation flag and omitted-node count

Meaningful-node filter:

- Always include interactive elements, form controls, labels, headings,
  landmarks, tables, dialogs, alerts, iframes.
- Include `div`/`span` only when they carry text, a role, a click handler,
  `tabindex`, or are a control wrapper.
- Keep structural ancestors so the tree remains navigable.
- Cap at 6,000 meaningful nodes; mark `truncated` rather than silently dropping.

Element IDs are per scan. They are not durable across visits. Recipes store
durable locators (CSS/XPath/role/name/hash), not scan IDs.

## 5. Blueprint model

`backend/core/blueprint.py`:

- `BlueprintElement` dataclass with the fields above.
- `PageBlueprint`:
  - `get(id)`
  - `find(role=..., name=..., tag=..., text=..., visible=...)`
  - `interactables()`, `fields()`, `gateways()`, `next_candidates()`
  - `by_role_name`, `by_tag`, `by_frame` indexes
  - `to_prompt_tree()`: compact tree with IDs for the AI planner
  - `to_debug_json()`: full tree for diagnostics
  - `summary()`: counts, frames, scan ID, truncation

Prompt tree example:

```html
<a id="fp-42" role="link" name="Login" href="/frontend/site/login" visible="true" />
<input id="fp-51" type="text" name="userId" label="User ID" required="true" />
```

## 6. Action resolver

`backend/core/action_resolver.py`.

Actions: `Click`, `Fill`, `Select`, `Check`, `Upload`, `PressKey`, `Scroll`,
`Wait`, `Navigate`.

Resolution ladder:

1. `[data-fp-id="fp-42"]` in the correct frame. Require exactly one match.
2. Blueprint CSS. Require exactly one match.
3. Blueprint XPath. Require exactly one match.
4. Role + accessible name. Require exactly one visible interactable.
5. Label/name/placeholder + tag. Require exactly one.
6. Text + tag + structural neighborhood. Require exactly one.
7. Otherwise fail with `NOT_FOUND` or `AMBIGUOUS`; re-scan once; if still
   ambiguous, ask the human. Never pick `.first`.

Before acting:

- validate tag, role/name and element hash (or stable attributes),
- check visible, enabled, editable where required,
- hit-test the target; if another element covers it, record `covered_by` and
  either dismiss a known overlay or hand off.

Action fallbacks:

- Click: actionability trial -> normal click -> scroll + coordinate click at the
  hit-tested point -> JS `element.click()` only when the hit target is the
  element or its descendant. Never force-click a hidden element.
- Fill: `locator.fill()` -> `press_sequentially` -> JS native setter with
  `input`/`change`/`blur`.
- Select: native `select_option` -> open custom dropdown, re-scan, click the
  exact `role=option`.
- Check: `check()` / `uncheck()` -> JS fallback.
- Upload: `set_input_files`.

After every action: verify value/URL/section/dialog/error. If no effect,
re-scan and retry once, then return a precise error code:

`NOT_FOUND`, `MULTIPLE_MATCHES`, `NOT_VISIBLE`, `DISABLED`, `COVERED`,
`NO_EFFECT`, `FRAME_NOT_ACCESSIBLE`, `STALE_SNAPSHOT`.

## 7. Orchestrator integration

- `_scan_dom()`: returns the compatibility DOM and stores the typed
  `PageBlueprint` in `self.blueprint`. (The earlier draft called this
  `_capture_page()`; the shipped name is `_scan_dom()`.)
- `_observe_page()`: attaches the blueprint summary (`scan_id`, element/frame
  counts, truncation) to the form map.
- `FormModel.build_field()`: adds `element_id`, `frame`, `role`, `css`,
  `xpath`, `element_hash`, `css_unique`.
- `FormModel.locators()`: priority order is
  `blueprint_id -> css -> xpath -> role/name -> label -> name -> index`.
- `FormModel._gateways()` and `_next_actions()`: preserve element ID, tag, role,
  name, href, CSS, XPath, frame, visibility and coverage.
- `_click_gateway()`: `resolver.click(gateway["element_id"])`.
- `_safe_click()`: thin resolver wrapper; legacy fallback only when no blueprint
  element ID exists.
- `_fill_form()`: `resolver.fill()` / `resolver.select()` for fields with a
  blueprint id; the existing JS injection remains the fallback for radio
  groups, checkboxes, date formatting and unusual widgets. A field scanned as
  disabled or hidden is not bypassed by the injector.
- `_advance()`: takes a fresh scan, resolves the next button by its current
  blueprint id, clicks it, and verifies the step changed.
- `_handle_captcha()` / `_handle_otp()`: still human-only and still use their
  existing selectors. Migrating their locators to blueprint ids is a later
  hardening task, not an automation path.
- Emit action diagnostics through `self._last_action_result`: scan ID, element
  ID, method, error code, drift and details.

For HPSC, `_click_gateway` must resolve
`a.btn.btn-main[href="/frontend/site/login"]` in the main frame, validate it is
the only match, verify the hit target, click it, and wait for
`/frontend/site/login`.

## 8. Recipes and drift

Current status: recipes still use the version-1 file schema, but gateway and
next-action entries are now sanitized to durable locators (no `element_id`,
no `covered_by`). Full recipe-v2 replay and hash-based drift repair are not
implemented yet.

Recipe v2 stores durable structure, not scan IDs:

```json
{
  "version": 2,
  "recipe_id": "...",
  "portal": "regn.hpsc.gov.in",
  "page_type": "login",
  "page_key": "...",
  "blueprint_fingerprint": "...",
  "steps": [
    {
      "step_key": "...",
      "elements": [
        {
          "role": "link",
          "name": "Login",
          "tag": "a",
          "css": "a.btn.btn-main[href=\"/frontend/site/login\"]",
          "xpath": "...",
          "frame": "main",
          "element_hash": "...",
          "attrs": {"href": "/frontend/site/login"}
        }
      ],
      "fields": []
    }
  ]
}
```

Replay:

1. Scan the live page.
2. Match by portal + page key + fingerprint + field keys.
3. Resolve saved locators in order; each must be unique.
4. If all resolve: deterministic replay, no AI.
5. If some fail: mark drift, repair from live role/name/hash/neighbors, update
   the recipe, continue.
6. If the page changed too much: ignore the recipe and use the generic/agent
   path.

Never store values, tokens, OTPs, CAPTCHA answers or passwords in a recipe.

## 9. AI layer

Interfaces:

```python
class Planner(Protocol):
    async def plan(self, goal, blueprint, history) -> Plan: ...

class Repairer(Protocol):
    async def repair(self, goal, blueprint, failure, history) -> Plan: ...
```

Plan format:

```json
{
  "goal": "log in to the portal",
  "actions": [
    {
      "type": "click",
      "element_id": "fp-42",
      "confidence": 0.98,
      "reason": "Login link in the top navigation"
    },
    {
      "type": "fill",
      "element_id": "fp-51",
      "value_ref": "vault.user_id",
      "confidence": 0.95
    }
  ]
}
```

Validator:

1. Schema valid.
2. Every `element_id` exists in the current blueprint.
3. The element resolves to exactly one match.
4. The action type is allowed for that element.
5. Sensitive elements are blocked.
6. Navigation targets are in the blueprint or an allowlist.
7. Confidence is above the auto-execute threshold.

Confidence policy:

- high: execute automatically,
- medium: dry-run and show the plan for review,
- low or ambiguous: ask the human.

AI is used for:

- first visit to an unknown page (plan),
- ambiguous field/label mapping,
- failure/drift repair.

AI is not used for:

- clicking known elements,
- filling values,
- CAPTCHA/OTP/payment/final submission,
- generating code,
- arbitrary navigation.

## 10. Cost model

The dominant cost is context size x calls x retries.

- Raw HTML/DOM can be 100k+ tokens.
- Compact blueprint is typically a few thousand tokens.
- Known recipe: 0 AI calls.
- New page: 1-2 calls.
- Repair: 1-2 calls.

Track `ai_calls`, `tokens_in`, `tokens_out`, `estimated_cost`, `repair_count`
in run metadata. Without measurement, cost optimization is guesswork.

## 11. Safety and privacy

- Redact password, OTP, CAPTCHA, payment and identity values before any AI call.
- Send only the relevant subtree, not the whole DOM.
- Treat page text as untrusted (prompt injection).
- Constrain AI output to the action schema and existing element IDs.
- No arbitrary code, no arbitrary URLs, no direct browser control from AI.
- Human gates remain human.
- Prefer no-training/zero-retention providers; offer a local-model option.

## 12. Tests

- `test_dom_scanner.py`: tree shape, unique IDs, CSS/XPath uniqueness,
  roles/names, visibility, options, iframes, open shadow roots.
- `test_action_resolver.py`: unique resolution, ambiguity rejection, stale ID
  re-scan, covered element, click/fill/select/check/upload, verification.
- `test_hpsc_gateway.py`: HPSC-like fixture; role `link`, unique CSS, click
  navigates to `/frontend/site/login`.
- `test_recipe_v2.py`: save/load, deterministic replay, drift repair, redaction.
- `test_orchestrator_blueprint.py`: gateway -> login -> fill; stop race; CAPTCHA
  gate; no blind click.
- Regression: duplicate labels, hidden first match, overlay-covered button, SPA
  re-render, custom dropdown, iframe form, shadow DOM button.
- Performance: 5k-node page scan under ~1s; prompt tree within token cap.
- Full suite remains green.

## 13. Phases

| Phase | Work | Outcome | Status |
|---|---|---|---|
| 0 | Instrument click failure, save HPSC fixture | Know why the cloud click failed | Done |
| 1 | Scanner v2 + PageBlueprint + compatibility layer | Full DOM blueprint | Done |
| 2 | ActionResolver + gateway migration | HPSC Login works via element ID | Done |
| 3 | Fill/select/upload/advance migration | No blind field/button actions | Partial: fill/select/advance use resolver; upload and security fields still use legacy paths |
| 4 | Recipe v2 + drift repair + deterministic replay | Faster repeat runs | Partial: durable locators stored, scan ids stripped; replay/drift repair pending |
| 5 | Compact prompt tree + AI planner + validator | Agent plans from IDs | Pending: prompt tree exists, planner/validator not built |
| 6 | Hardening, performance, docs, full suite | Stable release | In progress |

Phase 0-2 is the critical slice and is complete. Phase 3-6 build on it.

## 14. Files

New:

- `backend/core/blueprint.py`
- `backend/core/action_resolver.py`
- `backend/core/decision_policy.py`
- `tests/browser_helpers.py`
- `tests/test_dom_scanner.py`
- `tests/test_action_resolver.py`
- `tests/test_hpsc_gateway.py`
- `tests/test_decision_policy.py`
- `tests/test_fill_verification.py`
- `docs/decision-policy.md`

Modified:

- `backend/core/dom_scanner.py`
- `backend/core/form_model.py`
- `backend/core/portal_adapter.py`
- `backend/core/orchestrator.py`
- `backend/core/chat_assistant.py`
- `backend/core/recipe.py`
- `backend/main.py`
- `frontend/src/App.jsx`
- `frontend/src/components/SessionStrip.jsx`
- `frontend/src/components/HumanCheckpointModal.jsx`
- `frontend/src/components/LiveChat.jsx`
- `scripts/e2e_demo.py`
- `tests/test_form_model.py`
- `tests/test_chat_assistant.py`
- `tests/test_recipe.py`

Not created: `backend/core/actions.py` was merged into `action_resolver.py`.
The HPSC fixture lives inline in `tests/test_hpsc_gateway.py` rather than in a
separate HTML file.

## 15. Acceptance criteria

- HPSC Login gateway resolves and clicks the exact anchor on 10/10 runs.
  Status: verified once against the live portal and pinned by regression tests.
  A 10-run live soak has not been run.
- No action is executed by `.first` text matching. Status: the gateway,
  advance and fill paths no longer use `.first`; human-only OTP/CAPTCHA/upload
  helpers still contain legacy `.first` selectors.
- Known recipe runs with 0 AI calls. Status: there is no AI call in the
  runtime today, so this holds trivially; deterministic recipe replay itself
  is not implemented yet.
- New page plan uses at most 2 AI calls. Status: not implemented.
- Drift repair uses at most 2 AI calls, or hands off to a human. Status: not
  implemented.
- No AI action without a valid blueprint element ID. Status: no AI actions
  exist yet.
- CAPTCHA/OTP/payment/final submission never auto-executed. Status: holds.
- Full test suite green. Status: 165 passed, 2 skipped on 2026-10-27.
  Both opt-in practice-portal flows also passed: new registration stopped at
  `AWAITING_PAYMENT`; returning-candidate login finished at `DONE`.

---

## 16. Semantic understanding layer and the two identities (2026-10-28)

Status: **design direction agreed in discussion; not implemented.**
This section does not replace sections 3, 9 or 13. It adds the missing layer
above the DOM blueprint and records why it is needed. Older text is kept
deliberately so the reasoning trail is visible.

### 16.1 How we got here

The DOM blueprint work made the operator reliable at the mechanics: stable
element ids, resolver checks, real page-change verification, human gates for
entry and OTP. That is necessary but not sufficient. A live HPSC run on
2026-10-28 exposed the gap between **executing** a form and **understanding**
it.

Observed failures from that run (`data/runs/run-20261028-153849-133aef`):

- Two date fields were announced as `DD-MM-YYYY`. The scanner used the
  placeholder as the label, so the fields were treated as unknown, not as
  date of birth or date of passing.
- `name_as_matric` was announced as `No IdentityModel[name_as_matric]` and
  saved as an unrelated custom field.
- The photo ID upload reported success, then failed verification on every
  recheck and was uploaded again. The portal likely clears the file input
  after its async upload and keeps a preview instead.
- The review gate repeated `Recheck → 15 of 18 verified → 5 need attention`
  because `FILL_INCOMPLETE` only offered Recheck and Continue. There was no
  "fix this field" path, so the same failures repeated.
- `15 of 18` and `5 need attention` used different accounting: the denominator
  counted attempted fields, while the failure list also included skipped
  fields.
- The chat said it could not fill DOB. It had saved `dob`, but the open page
  had no field classified as `dob`, so the chat's page update found nothing.
  The popup and the chat were writing to different keys.
- "first name Nishant, no middle name, last name Kumar" became a single
  `full_name = Nishant Kumar`. The vault had no first/middle/last parts, so
  the chat could not fill a three-box name section correctly.
- Section save was attempted while blocking fields remained; the portal did
  not move, and the run retried instead of explaining which fields blocked it.

Root cause: meaning is still inferred from labels, placeholders and registry
keys in several places, and the chat and the operator each have their own path
to the vault. The system needs one shared understanding of the page.

### 16.2 The two identities

The product has two working identities, plus the human.

**Operator (hands).** Reads the DOM, accessibility tree, screenshot, network
and errors. Knows how to click, type, select, upload, wait, retry and recover.
Owns technical failures. Never decides what a field *means*.

**Interpreter (mind).** Sees the page as a person does: headings, questions,
groups, hints, required markers, document requests. Knows what the vault
contains. Decides what the page is asking for, which saved fact answers it,
when to ask, and how to explain the result. Never clicks blindly or invents a
value.

**Human (judgment).** Resolves ambiguity, confirms identity details, solves
CAPTCHA/OTP/live photo, handles payment and final submission, and can take
control of the browser at any time.

The chat must speak as the interpreter. The orchestrator must act as the
operator. Both must read the same page understanding. This is the sync that is
missing today.

### 16.3 Page lifecycle

Every navigation runs the same loop:

1. **Load.** Playwright opens the URL or follows a link.
2. **Perceive.** Capture the DOM blueprint, accessibility tree, visible text,
   headings, groups, labels, helper text, placeholders, input types, options,
   required state, stable element handles and a screenshot.
3. **Classify.** Decide what kind of page this is: application form, section
   form, signed-in dashboard, public landing page, listing/results page,
   login/register page, OTP page, CAPTCHA page, payment page, error page.
4. **Understand.** Build a human-readable page model.
   - For a form: a **Form Understanding** with sections, questions, concepts,
     expected formats, constraints, documents and confidence.
   - For a dashboard/landing: a **Page Understanding** with the page purpose,
     the information shown, the distinct paths available, and which paths are
     application actions versus informational links.
5. **Decide.** Match questions to vault facts. If the page offers more than one
   path, ask the human. If a fact is missing or ambiguous, ask one plain
   question. Never guess register/login/resume or a login method.
6. **Act.** The operator fills, clicks, uploads, waits and verifies. Human-only
   steps stop for the human.
7. **Verify.** Re-perceive the page and compare meaning, not strings: dates in
   any format, name order, case, punctuation, select text versus value, upload
   preview versus file input.
8. **Explain and learn.** Tell the human what was understood, what was filled,
   what the page now shows, and what is still needed. Store confirmed mappings
   as aliases for next time.
9. **Repeat.** On navigation, start again from perception. Never reuse a stale
   form map.

### 16.4 Form Understanding document

The interpreter's output is a structured, human-readable document. It is built
before the first fill and cached by page signature.

```text
page: HPSC Universal Registration — Personal Details
url, title, page_signature, page_type=FORM
sections:
  - Personal Details
      question: What is your first name?        concept=first_name   required
      question: What is your middle name?       concept=middle_name  optional
      question: What is your last name?         concept=last_name    required
      question: When were you born?             concept=dob          required
                expected_format=DD-MM-YYYY
      question: Attach a photo ID proof         concept=photo_id     required, file
  - Education
      question: Name as printed on matric certificate
                concept=name_as_matric       required
human_only: [captcha, otp, live_photo, payment, final_submit]
ambiguities:
  - two date fields share the placeholder DD-MM-YYYY; resolved by group heading
```

Each field carries evidence (label, helper text, placeholder, group heading,
screenshot region), a confidence score, an expected answer type/format, and a
stable element handle for the operator. Low confidence is never auto-filled.

### 16.5 Semantic profile (vault)

The vault becomes a semantic profile, not only a flat key-value store:

- facts: `full_name`, `first_name`, `middle_name`, `last_name`, `dob`,
  `name_as_matric`, contact, address, academic, documents
- aliases and multilingual synonyms for each concept ("date of birth", "DOB",
  "birthday", "when were you born", "जन्म तिथि")
- provenance: explicit from the candidate, derived from another fact, or
  confirmed from a portal
- verification status: unverified, confirmed by the candidate, verified on a
  page
- unknown facts are explicit (`middle_name = null`), not silently invented

Derived values are allowed only when they are unambiguous. `Nishant Kumar` can
derive first `Nishant` and last `Kumar`; it cannot derive a middle name.

### 16.6 Name example

The form asks for First Name, Middle Name, Last Name.

- Vault: `full_name = Nishant Kumar`; candidate explicitly said first
  `Nishant`, last `Kumar`, no middle name.
- Plan: fill first and last. Middle is optional, so leave it blank.
- If middle is required, ask once: leave blank, enter `-`, or provide a middle
  name. Never invent one.
- If the form asks for a single Full Name instead, compose `Nishant Kumar`.
- Verify by reading the page back and show:
  `First: Nishant · Middle: — · Last: Kumar`.

### 16.7 DOB example

The page says "When were you born?" with placeholder `DD-MM-YYYY`.

- Concept: `dob`, matched by meaning, not by label equality.
- Canonical vault value: `2005-08-03`.
- Render `03-08-2005` for this field. For `type=date`, render `2005-08-03`.
- Verify by parsing both values as dates, not by comparing strings.
- If the portal rejects the value, the operator tries the alternate format once,
  then the interpreter explains the rejection and asks.

The placeholder is a format hint, never the field's identity.

### 16.8 Dashboard and landing pages

A dashboard is not a form. It is a page with a purpose, information and paths.

Example, HPSC signed-in dashboard:

```text
page_type=DASHBOARD
purpose: candidate is signed in; registration ID shown
information: registration ID, application status
paths:
  - Preview Universal Registration        informational/preview
  - Proceed for Universal Registration    application action
```

The interpreter opens a next-step gate with the distinct paths and asks which
one the candidate wants. It does not assume "Proceed" or "Preview".

Example, public landing page:

```text
page_type=LANDING
purpose: exam information and entry paths
paths:
  - New Registration / OTR   first-time candidate
  - Candidate Login          returning candidate
```

The interpreter asks whether the candidate is already registered or applying
for the first time. It never guesses. If the page has a single clear path, it
may follow it and say so.

After the human chooses, the operator navigates, the page is perceived again,
and the loop repeats. A dashboard with no actionable paths ends as `DONE`; a
dashboard with links never ends prematurely.

### 16.9 Human in the loop

- Before filling a section: show a short "here is what I understood" summary;
  let the human correct a concept before any value is typed.
- On ambiguity: one plain question, with options when the page offers them.
- On human-only steps: CAPTCHA, OTP, live photo, payment and final submission
  remain human-only; the gate stays open until the page actually changes.
- After filling: show "here is what the page now shows" and let the human
  confirm. No claim of success without verification.
- On repeated failure: stop after two identical cycles and explain the specific
  blocker; never loop.
- Takeover: the human can take browser control at any time; the operator
  finishes its atomic action, pauses, grants exclusive control, and on return
  re-perceives the page before resuming.

### 16.10 Trust rules

1. Meaning before mechanics: understand the page before acting on it.
2. Evidence for every interpretation; no evidence, no auto-fill.
3. Confidence thresholds: high fills, medium asks, low never fills.
4. No invented values: answers come from the vault or the human in this run.
5. Verify after acting; the interpreter may not claim success on the
   operator's behalf.
6. The human confirms identity details and resolves ambiguity.
7. Human-only gates are absolute.
8. Learn from confirmed mappings; the registry is a fast path, not the brain.
9. Technical failures are the operator's job; they are never an excuse to
   guess a field's meaning.
10. Sensitive data goes only where the configured model endpoint allows; the
    settings dialog states this.

### 16.11 Relationship to the existing implementation

- `blueprint.py` / `dom_scanner.py`: the eyes and stable handles. Keep.
- `action_resolver.py`: the hands. Keep.
- `form_model.py` / `field_registry.py`: fast-path dictionary and safety
  guard. Keep, but stop treating it as the only source of meaning.
- `orchestrator.py`: the operator loop. It should consume a Form Understanding
  instead of inferring meaning from labels alone.
- `chat_assistant.py`: the interpreter's voice. It should read and write the
  same understanding and the same outstanding-field state as the operator.
- New work will likely need a page-understanding module, a semantic-profile
  module, a shared outstanding-field record, and a confirmation UI. Names are
  intentionally not fixed yet.

### 16.12 What this changes in behaviour

- Date fields are identified by meaning and format, not by `DD-MM-YYYY`.
- `name_as_matric` is a real concept, not framework junk.
- Name parts are handled explicitly; no invented middle name.
- Photo upload is verified by portal evidence, not only `files.length`.
- Counts and "needs attention" come from one source.
- `FILL_INCOMPLETE` offers per-field fixes, not only Recheck/Continue.
- The chat can fill the exact open field and reports verified/saved/failed
  honestly.
- Save is blocked while required fields are unresolved; validation messages
  are attributed to fields.
- Dashboards and landing pages are understood as pages with paths, not forms.
- Takeover is always available, exclusive and resumable.

### 16.13 Open decisions (discuss before coding)

1. **Understanding cadence:** run the full understanding pass on every page, or
   only on first visit and when the page signature changes? Recommended:
   first visit plus change detection, with a manual "re-read page" action.
2. **Confirmation:** always show the "here is what I understood" summary before
   filling, or only when confidence is below a threshold? Recommended: always
   for the first section of a new portal, then only on low confidence.
3. **Vision:** use screenshots on every page, or only when the accessibility
   tree is ambiguous or the layout is unusual? Recommended: on ambiguous
   pages and for document/upload sections.
4. **Name storage:** store first/middle/last separately, with `full_name`
   composed? Recommended: yes, and keep explicit parts authoritative.
5. **Takeover resume:** after the human returns control, wait for Continue or
   auto-resume? Recommended: re-perceive, then wait for Continue.
6. **Model budget:** how many model calls per page are acceptable? Recommended:
   one understanding call per page signature, plus one clarification call only
   when needed.

### 16.14 Implementation slices (after the discussion above)

- **Slice A — perception and understanding, read-only.** Build the Form
  Understanding for one HPSC fixture and show it in the UI/API without filling
  anything.
- **Slice B — semantic profile and matching.** Add name parts, aliases,
  provenance and confidence; match concepts to facts; ask on ambiguity.
- **Slice C — operator uses the understanding.** Fill and verify against
  concepts; one outstanding-field record; per-field gate actions; upload
  evidence; save guard and stall detection.
- **Slice D — chat bound to the same state.** Fill the open field, verify,
  report honestly, bind answers to the open gate, handle name parts.
- **Slice E — takeover.** Always-available pause, exclusive control lease,
  return-and-rescan.
- **Slice F — evaluation.** HPSC fixtures, date/name/upload regressions,
  dashboard/landing paths, false-claim checks, full suite and practice e2e.

### 16.15 Acceptance criteria for this layer

- On the HPSC personal-details page, the two date fields are understood as
  date concepts with the correct format; neither is announced as
  `DD-MM-YYYY`.
- `name_as_matric` is understood as a name concept and mapped to a confirmed
  candidate fact.
- A photo upload that the portal keeps as a preview is verified once and is
  not re-uploaded on recheck.
- The review gate reports one consistent count and offers a fix for each
  outstanding field.
- Chat "fill dob 03/08/2005" fills and verifies the actual field, or explains
  the exact blocker; it never says "no open field" while the field is visible.
- "first name Nishant, last name Kumar, no middle name" fills a three-part
  name section correctly, leaving middle blank when allowed and asking when
  required.
- A dashboard with two application links asks which one; a landing page with
  login/register asks whether the candidate is new or returning.
- No field is reported filled unless a fresh page read confirms it.
- The human can take control at any time, and returning control triggers a
  fresh read before the operator continues.

### 16.16 Decisions from the 2026-10-28 review

These resolve the open questions in 16.13 for the build/test phase. The
original questions are kept above as history.

1. **Page brief visibility: always during build and testing.**
   The brief is shown before filling and the human confirms it. This is a
   testing aid, not the permanent product burden. In production the brief
   becomes a compact, non-blocking banner: the agent continues on high
   confidence and pauses only for ambiguity, missing facts, or human-only
   steps. The human can always open the full brief or ask the chat what the
   page wants.

2. **Explicit profile storage: yes.**
   The vault stores facts explicitly, with labels, types, parts, aliases,
   provenance, verification status and portal scope. Explicit values always
   win over derived values. The agent must not infer a middle name, a login
   method, or an account status from a guess.

3. **Takeover resume: wait for Continue.**
   After the human returns control, the operator re-perceives the page and
   waits for the human to press Continue. Auto-resume can be added later if
   testing shows it is safe.

4. **Model budget: one understanding call per page signature, plus one
   clarification call only when needed.**
   The page signature covers URL, DOM structure, visible text and field
   inventory. A matching signature reuses the cached brief. A changed
   signature, a navigation, or a human takeover triggers a fresh read.

### 16.17 Ask only what only the human knows

The goal is to remove burden, not to move it. The agent owns page questions.
The human owns identity and account questions.

**The agent must answer these itself, without asking:**

- What kind of page is this?
- What does this field mean?
- Which saved fact answers this question?
- What format does this field expect?
- Is this a dashboard, a form, a landing page or an error?
- Which links are informational and which are application paths?
- Did the page keep the value?
- What is the next technical step?

**Only the human can answer these:**

- Have you registered on this portal before, or is this your first time?
- Which account/path do you want when more than one is genuinely valid?
- Which login method do you want when the portal offers several?
- What is a personal fact that is missing from the vault?
- Do you have a middle name, or should it be left blank?
- Which document variant do you want to upload?
- Do you approve this payment or final submission?
- Do you want to take control of the browser?

If the agent must ask about the page, it asks as a **confirmation with a
proposed answer**, not as homework:

- Good: “I think this is your date of birth. Is that right?”
- Bad: “What does this field mean?”
- Good: “This looks like your HPSC dashboard. I see two application links.
  Which one?”
- Bad: “Is this a dashboard?”

### 16.18 Portal account memory

“Have you registered before?” is a per-portal fact, not a global profile fact.
Store it explicitly:

```text
portal: regn.hpsc.gov.in
account_exists: yes | no | unknown
identifiers_seen: [mobile, email, URN]
login_method: mobile_otp | urn_password | unknown
registration_status: not_started | in_progress | submitted
last_known_step: ...
confirmed_by_human_at: ...
```

Rules:

- Ask once at entry when the answer is unknown.
- If the human says “first time” but the portal reports the mobile is already
  registered, do not fail silently. Surface the conflict and offer login or
  account recovery, then store the corrected fact.
- Never submit an OTP or reset a password to discover account existence.
- Keep the fact scoped to the portal domain and the identifier used.

### 16.19 What “always show the brief” means in practice

- **Build/test:** full brief, explicit confirmation before the first fill of a
  section.
- **Production:** compact banner (“I understood this page as …”), auto-continue
  on high confidence, pause on ambiguity or human-only decisions.
- **On demand:** the chat can always explain the page, the next action, and
  what is still missing.
- **Never:** ask the human to classify the page, name a field, or translate a
  label. That is the agent’s job.

### 16.20 Remaining questions for the next review

1. When the human is “not sure” whether they registered, should the agent
   inspect the portal’s login/recovery UI (read-only) or simply ask them to
   try a login path? Recommended: read-only inspection of the visible login
   options, then ask; never submit credentials or OTP to probe.
2. Should portal account memory be keyed by domain, or by domain plus
   identifier? Recommended: domain plus the identifier actually used, with a
   domain-level summary.
3. Should the page brief live in a dedicated panel, the chat, or both?
   Recommended: dedicated panel with a one-line chat summary, so the chat
   stays conversational.

### 16.21 Locked decisions (final for this slice)

These close the three questions in 16.20.

1. **Unknown account status: read-only inspection, then ask.**
   When the candidate says "not sure" whether they registered, the operator
   inspects the visible login/recovery UI only: which login methods exist
   (mobile OTP, URN + password, email), whether a "forgot password" or
   "recover account" path is present, and any visible hints. It then asks the
   human to choose login or register. It never submits credentials, never
   requests an OTP, and never resets anything to probe for existence.

2. **Portal account memory is keyed by domain plus identifier, with a
   domain-level summary.**
   The detailed record is `(domain, identifier_type, identifier_value)`, for
   example `(regn.hpsc.gov.in, mobile, 98xxxxxx21)`. A domain-level summary
   aggregates what is known about the portal across identifiers, so the agent
   can say "you have an in-progress application here" without guessing which
   identifier it belongs to.

3. **The brief lives in a dedicated panel, with a one-line chat summary.**
   The panel is the source of truth and can be opened at any time. The chat
   stays conversational: it states the page in one line and expands on
   request. Both read the same `PageBrief` object; neither keeps a private
   copy.

### 16.22 Draft contracts (review before coding)

Status: **proposal only.** No code should be written against these until they
are reviewed. Field names are chosen to be readable in logs and JSON; they can
change now, not after implementation.

The contracts are the boundary between the operator and the interpreter. The
operator produces `Perception`; the interpreter produces `PageBrief`; the
planner produces `FieldMapping`; the gate consumes `OutstandingField`; the
vault owns `Fact` and `PortalAccount`.

#### 16.22.1 Perception (operator -> interpreter)

What the operator captures on every load or meaningful change. It is evidence,
not meaning.

```json
{
  "perception_id": "per-...",
  "captured_at": "2026-10-28T15:38:49Z",
  "url": "https://regn.hpsc.gov.in/...",
  "final_url": "https://regn.hpsc.gov.in/...",
  "title": "HPSC — Universal Registration",
  "page_signature": "sha256:...",
  "visible_text": "Personal Details ... Date of Birth ...",
  "headings": [{"level": 2, "text": "Personal Details"}],
  "a11y_tree": "<serialized accessibility tree>",
  "screenshot_ref": "runs/<run>/shot-001.png",
  "frames": [{"url": "...", "depth": 1}],
  "fields": [
    {
      "handle": "fp-17",
      "tag": "input",
      "type": "text",
      "accessible_name": "Date of Birth",
      "label_text": "Date of Birth",
      "placeholder": "DD-MM-YYYY",
      "helper_text": "Enter as printed on matric certificate",
      "required": true,
      "disabled": false,
      "readonly": false,
      "options": [],
      "group_heading": "Personal Details",
      "value": "",
      "rect": {"x": 410, "y": 260, "w": 300, "h": 38}
    }
  ],
  "actions": [
    {"handle": "fp-31", "role": "button", "name": "Save & Next", "enabled": true}
  ],
  "errors_visible": [],
  "captcha_present": false,
  "otp_present": false
}
```

Rules:

- `handle` is the operator's stable id for this perception only. It is never
  used as meaning.
- `page_signature` is derived from URL path, visible text, field inventory
  (tag/type/name/placeholder) and headings. It intentionally ignores volatile
  values, timestamps and session tokens.
- The screenshot is a reference, not a payload. The interpreter receives the
  image only when the text tree is ambiguous or the page is visual.

#### 16.22.2 PageBrief (interpreter -> everyone)

One document per page signature. It is what the panel shows, what the chat
summarises, and what the planner reads.

```json
{
  "brief_id": "brief-...",
  "page_signature": "sha256:...",
  "url": "https://regn.hpsc.gov.in/...",
  "page_type": "FORM",
  "title": "Personal Details",
  "purpose": "Collect the candidate's identity details for universal registration.",
  "confidence": 0.93,
  "sections": [
    {
      "section_id": "sec-personal",
      "heading": "Personal Details",
      "confidence": 0.95,
      "questions": [
        {
          "question_id": "q-1",
          "asked": "What is your first name?",
          "concept": "first_name",
          "concept_confidence": 0.97,
          "answer_type": "text",
          "expected_format": null,
          "required": true,
          "handle": "fp-12",
          "evidence": ["label: First Name", "group: Personal Details"],
          "constraints": {"max_length": 50}
        },
        {
          "question_id": "q-2",
          "asked": "When were you born?",
          "concept": "date_of_birth",
          "concept_confidence": 0.94,
          "answer_type": "date",
          "expected_format": "DD-MM-YYYY",
          "required": true,
          "handle": "fp-17",
          "evidence": ["label: Date of Birth", "placeholder: DD-MM-YYYY"],
          "constraints": {"min_age_years": 15}
        }
      ]
    }
  ],
  "information": [
    {"label": "Registration ID", "value": "HPSC-2026-...", "kind": "identifier"}
  ],
  "paths": [
    {
      "path_id": "p-1",
      "label": "Proceed for Universal Registration",
      "handle": "fp-41",
      "kind": "application_action",
      "needs_human_choice": true
    }
  ],
  "human_only": ["captcha", "otp", "live_photo", "payment", "final_submit"],
  "ambiguities": [
    {
      "ambiguity_id": "amb-1",
      "description": "Two date fields share the placeholder DD-MM-YYYY.",
      "question_ids": ["q-2", "q-9"],
      "resolution": "resolved_by_group_heading",
      "confidence": 0.82
    }
  ],
  "cache": {"created_at": "...", "invalidated_by": null}
}
```

`page_type` is one of: `FORM`, `SECTION_FORM`, `DASHBOARD`, `LANDING`,
`LISTING`, `LOGIN`, `REGISTER`, `OTP`, `CAPTCHA`, `PAYMENT`, `ERROR`,
`UNKNOWN`.

`paths[].kind` is one of: `application_action`, `informational`,
`navigation`, `account_action`, `unknown`. Only `application_action` and
`account_action` may need a human choice.

#### 16.22.3 Fact (vault)

A labeled, typed, sourced value. This replaces the flat key-value profile.

```json
{
  "fact_id": "fact-...",
  "concept": "first_name",
  "label": "First name",
  "value": "Nishant",
  "value_type": "text",
  "parts": null,
  "aliases": ["given name", "first name", "पहला नाम"],
  "provenance": "explicit_user",
  "verification": "confirmed_by_human",
  "verified_at": "2026-10-28T10:12:00Z",
  "scope": {"kind": "global"},
  "constraints": {"max_length": 50},
  "notes": null
}
```

A composite fact uses `parts`:

```json
{
  "concept": "full_name",
  "label": "Full name",
  "value": "Nishant Kumar",
  "value_type": "text",
  "parts": {
    "first": "Nishant",
    "middle": null,
    "middle_known_absent": true,
    "last": "Kumar"
  },
  "provenance": "explicit_user",
  "verification": "confirmed_by_human"
}
```

Rules:

- `provenance` is one of `explicit_user`, `derived`, `portal_confirmed`,
  `imported`.
- `verification` is one of `unverified`, `confirmed_by_human`,
  `verified_on_page`.
- Explicit facts always win over derived ones. A derived fact is stored with
  `provenance: derived` and is replaced, not merged, when an explicit value
  arrives.
- `middle_known_absent: true` is a fact. It means "the user says there is no
  middle name", and is different from `middle: null` with
  `middle_known_absent: false` ("not known yet").
- `scope` is either `{"kind": "global"}` or
  `{"kind": "portal", "domain": "...", "identifier_type": "...",
  "identifier_value": "..."}`.
- A concept is a stable snake_case name. New concepts require a human-confirmed
  mapping; a temporary question is never persisted as a permanent concept.

#### 16.22.4 PortalAccount

What the candidate has done on a specific portal. Separate from the global
profile.

```json
{
  "account_id": "acct-...",
  "domain": "regn.hpsc.gov.in",
  "identifier_type": "mobile",
  "identifier_value": "98xxxxxx21",
  "account_exists": "yes",
  "login_method": "mobile_otp",
  "registration_status": "in_progress",
  "last_known_step": "personal_details",
  "last_seen_url": "https://regn.hpsc.gov.in/...",
  "confirmed_by_human_at": "2026-10-28T15:00:00Z",
  "evidence": ["human: I have an account", "page: login form offers mobile OTP"]
}
```

`account_exists` is `yes | no | unknown`. `login_method` is `mobile_otp |
urn_password | email_password | unknown`. `registration_status` is
`not_started | in_progress | submitted | unknown`.

Domain summary, derived, not stored twice:

```json
{
  "domain": "regn.hpsc.gov.in",
  "known_identifiers": ["mobile:98xxxxxx21"],
  "any_in_progress": true,
  "last_interaction_at": "2026-10-28T15:38:49Z"
}
```

#### 16.22.5 FieldMapping (learned fast path)

The memory that makes the registry learn. One record per confirmed
question-to-concept mapping, scoped to a portal.

```json
{
  "mapping_id": "map-...",
  "domain": "regn.hpsc.gov.in",
  "question_signature": "sha256:...",
  "asked_text": "When were you born?",
  "concept": "date_of_birth",
  "source": "human_confirmed",
  "confidence": 1.0,
  "created_at": "...",
  "last_used_at": "..."
}
```

`question_signature` hashes the normalised label, helper text, group heading
and input type. Placeholders are included only when no label exists, and are
never the sole identity. `source` is `seed_registry`, `human_confirmed` or
`model_inferred`. Only `seed_registry` and `human_confirmed` may auto-fill
without asking; `model_inferred` may propose, never act silently.

#### 16.22.6 OutstandingField (gate)

One record per unresolved question. This is what the review gate and the chat
both read, so their counts can never diverge.

```json
{
  "outstanding_id": "out-...",
  "question_id": "q-2",
  "handle": "fp-17",
  "asked": "When were you born?",
  "concept": "date_of_birth",
  "state": "mismatch",
  "blocking": true,
  "reason": "Page shows 2005-08-03 but expects DD-MM-YYYY.",
  "evidence": ["page value: 2005-08-03", "placeholder: DD-MM-YYYY"],
  "fix_actions": ["retry_with_format", "ask_human", "take_control"],
  "attempts": 1,
  "last_attempt_at": "..."
}
```

`state` is one of `missing_fact`, `ambiguous`, `unfilled`, `mismatch`,
`upload_unverified`, `validation_error`, `human_only`, `skipped_optional`.

Rules:

- The gate count is `len([o for o in outstanding if o.blocking])`.
- The same list is shown in the panel, the chat and the review gate.
- Every blocking item must offer at least one fix action; `recheck` alone is
  not a fix.
- Two identical failed attempts on the same `outstanding_id` stop the loop and
  hand over with the specific reason.

#### 16.22.7 Cache and invalidation

- Key: `page_signature`.
- Store: `PageBrief` plus the confirmed `FieldMapping` records it produced.
- Invalidate on: navigation to a different URL path, a change in the field
  inventory, a human takeover, or an explicit "re-read page".
- Do not invalidate on: typing into a field, validation messages that do not
  change structure, or clock/time changes.
- Cost target: one interpreter call per signature, one clarification call only
  when an ambiguity cannot be resolved from evidence.

#### 16.22.8 API surface (sketch)

- `GET /api/page/brief` — current `PageBrief` plus outstanding fields.
- `POST /api/page/brief/confirm` — human confirms or corrects a concept.
- `GET /api/page/brief/stream` — optional; pushes a new brief on change.
- `GET /api/facts`, `PUT /api/facts/{concept}` — explicit facts and parts.
- `GET /api/portals/{domain}` — portal account memory and summary.

#### 16.22.9 Invariants

1. The operator never decides meaning; the interpreter never clicks.
2. Every `PageBrief` question has at least one piece of evidence and a handle.
3. No value is filled from a `Fact` with `verification: unverified` unless the
   human confirms it in the current run, except facts the user entered
   explicitly in this run.
4. A placeholder is a format hint, never an identity.
5. Explicit facts beat derived facts; absence of a middle name is a fact.
6. One outstanding-field list, one count, everywhere.
7. Human-only gates are absolute and cannot be satisfied by confidence.
8. Confirmed mappings are learned; inferred mappings only propose.
9. No claim of success without a fresh read of the page.
10. Two identical failures stop the loop.

### 16.23 Contract review closed (2026-10-28)

The four questions from 16.22 were reviewed and accepted:

1. `SECTION_FORM` stays as a distinct page type. Section forms have their own
   Save & Next, partial validation and per-section gates, so collapsing them
   into `FORM` would lose behaviour the operator needs.
2. Aliases live in one global concept dictionary, with optional per-fact
   extras. "DOB / birthday / when were you born" is defined once, not copied
   into every fact.
3. Evidence text is stored inline on the question; screenshot references are
   stored as references. The brief must be readable and auditable without
   joining back to `Perception`.
4. `information` and `paths` are optional on every brief. A form may surface a
   registration ID; a dashboard must surface paths.

Slice A is therefore: **perception and a read-only page brief, with no
filling.** The first implementation deliberately does not send a screenshot to
the model. Text, accessibility data and stable handles are enough to prove the
pipeline; vision is added when the text tree is ambiguous, as decided in
16.16.

Acceptance for Slice A:

- A live page can be perceived without filling anything.
- The brief names the page type and, for forms, every question it can see.
- Date fields are identified by their label and format, never announced as
  `DD-MM-YYYY`.
- Name parts and "name as per matric certificate" are distinct concepts.
- Landing and dashboard pages list their paths and ask which one when the
  choice belongs to the human.
- The same page signature reuses the cached brief; a changed page does not.
- If the model is unavailable, a deterministic brief is still produced and is
  labelled as such.

### 16.24 Slice B: semantic facts (2026-10-28)

Slice B adds the fact layer behind the vault. The vault still stores the
candidate's profile; `backend/core/facts.py` gives every value a concept, a
label, a provenance, a verification state and a scope.

Decisions taken while implementing:

1. **The saved profile is an explicit human statement.** A value read from the
   vault is reported as `provenance: explicit_user` and
   `verification: confirmed_by_human`. The candidate entered and saved it in
   their own profile, so it does not need to be re-confirmed on every run.
   A fact the chat learns later is stored the same way, with
   `source: explicit`.
2. **Derived facts are labelled.** Name parts split from a full name are
   `provenance: derived`. They never overwrite an explicit part. The split is
   mechanical, so the parts are usable; a derived value that requires judgment
   is not.
3. **`name_as_matric` requires one confirmation.** The certificate may print
   the name differently from the current profile. When only a full name is
   known, the brief marks `name_as_matric` as `needs_confirmation` instead of
   silently filling it.
4. **Absence is stored.** `middle_known_absent: true` makes `middle_name`
   resolve to `known_absent` with no value. It is not a missing fact, so the
   gate must not ask for it again.
5. **Confirmation fields are aliases of their parent.** `verify_full_name`,
   `verify_father_name` and `verify_mother_name` resolve to the parent fact and
   are never stored twice. `confirm_email` is copied mechanically from `email`.
6. **Scope is explicit.** A fact is either global or portal-scoped by domain.
   A portal fact wins on its own domain and nowhere else.
7. **Sensitive values stay masked in views.** `GET /api/facts` and
   `GET /api/facts/resolve` mask Aadhaar, mobile and password values the same
   way the vault view does. The operator reads the raw value internally.
8. **Facts are encrypted with the vault key.** `data/facts.json` uses the same
   AES-256-GCM envelope and atomic write as `candidate_vault.json`.
9. **Unknown concepts are refused.** A concept must exist in the dictionary
   before it can be stored. A new question becomes a concept only after a human
   confirms the mapping; it is never persisted from a model guess.

The page brief now carries `fact_status`, `fact_provenance` and
`fact_verification` per question, plus a `fact_summary` on the brief payload.
The brief still never contains the value itself: it says whether a fact exists,
where it came from and whether a human confirmed it.

API added in this slice:

- `GET /api/facts?domain=` — every known fact, masked, with a summary.
- `GET /api/facts/resolve?concept=&domain=` — one resolution, including why it
  is missing.
- `PUT /api/facts/{concept}` — store an explicit fact, optional parts, aliases,
  verification and portal scope.
- `DELETE /api/facts/{concept}?domain=` — remove an explicit fact so the
  derived or profile value applies again.

Acceptance for Slice B:

- An explicit first name beats a name derived from the full name.
- "No middle name" is `known_absent`, not `missing`.
- A portal-scoped value wins only on that domain.
- Facts survive a reload and are encrypted when a vault key is set.
- Every field-registry key maps to a concept.
- The brief tells the human which questions already have a fact.

### 16.25 Slice C: filling from concepts (2026-10-28)

`backend/core/fill_plan.py` turns one perception plus the fact book into one
instruction per field. The operator still does the typing and the fresh-scan
verification; the plan only decides *whether* and *what* may be typed.

Instruction states:

- `fill` — a fact exists and is safe to type.
- `leave_blank` — the human said the value does not exist (for example, no
  middle name). The field is skipped and is not treated as missing.
- `confirm` — only a derived value exists (currently `name_as_matric`). The
  operator asks the human to confirm it instead of typing it silently.
- `ask_human` — no fact, or a select has no matching option.
- `human_only` — OTP, CAPTCHA, live photo, payment.
- `upload` — a document upload handled by the upload pipeline.
- `fallback` — the question is not in the concept dictionary; the existing
  registry fast path decides.

Decisions:

1. **The plan is built from the same scan as the fill.** Handles are per-scan,
   so building the plan from a cached brief would be unsafe. The brief handles
   are never reused across scans.
2. **The plan uses the deterministic interpreter.** No model call is made
   during filling. A model read is for the human-facing brief; the fast path
   must stay fast and offline-safe.
3. **Dates are formatted from the page's own format.** `DD/MM/YYYY` in the
   label or placeholder is honoured; a value is never reformatted from a guess.
4. **Selects are checked against the page's options.** If the page does not
   offer the fact's value, the field becomes `ask_human` instead of a failed
   type.
5. **Answers become explicit facts.** When the human supplies a value for a
   known concept during a run, it is stored with
   `provenance: explicit_user` and `verification: confirmed_by_human`, so it
   beats derived values on the next run. Unknown questions keep the existing
   custom-field path until a human confirms a concept.
6. **Verification is unchanged.** Every filled value is still checked against
   a fresh scan; a value the portal drops is a failure, not a success.

Acceptance for Slice C:

- First, middle and last names fill from the full name without asking.
- A known-absent middle name stays empty and is reported as skipped, not
  missing.
- `name_as_matric` asks once instead of being typed from a derived value.
- A date is typed in the page's format.
- A select without a matching option asks instead of failing.
- Existing registry-based fills and read-only-field handling still pass.

### 16.26 Chat binding to the shared brief (2026-10-28)

The chat assistant now reads the same page brief the cockpit shows. There is
one understanding of the page, not a separate chat-only guess.

Decisions:

1. **The brief is part of the chat state.** `_state_context` carries the brief
   summary, page type, purpose, confidence, questions, paths, human-only steps,
   ambiguities and fact summary. The model explains the page from that brief
   instead of re-deriving it from raw fields.
2. **The page tool returns the brief.** `explain_current_page` includes the
   brief, so a question about the page and a question about a field resolve
   against the same object.
3. **The prompt forbids asking the human to do the interpreter's job.** Rules
   9-11 tell the model never to ask the candidate to classify the page, name a
   field or explain a label; `needs_confirmation` is presented as a derived
   value awaiting confirmation; `known_absent` is already answered and is not
   asked again.
4. **Saved details resolve semantically.** `get_saved_detail` asks the fact
   book first, so a derived name part (`first_name`, `middle_name`,
   `last_name`) and a confirmation field can be read even though the vault has
   no flat column for them. Values stay masked for sensitive concepts.
5. **Editing a name part stores an explicit fact.** A concept with no vault
   column is saved through the fact book with `provenance: explicit_user` and
   `verification: confirmed_by_human`; the vault profile is not rewritten.
6. **The open form is updated through the brief when the registry cannot map
   the field.** The classifier's semantic key is tried first; if it cannot see
   a concept such as `first_name`, the field is found by its brief handle and
   updated in place. A successful page edit is reported, a failed one is
   reported as "edit it directly", never as saved.

Acceptance for this slice:

- The chat state and the page tool both expose the brief.
- The system prompt carries the brief/fact-status rules.
- `get_saved_detail` returns a derived name part with its provenance.
- Editing `first_name` stores an explicit fact and leaves the vault untouched.
- Existing chat behaviour and the full suite still pass.

### 16.27 Always-available browser takeover (2026-10-28)

Takeover is now a first-class, always-available action, not only a side effect
of a checkpoint.

Flow:

1. `POST /api/agent/takeover` gives the human exclusive control. If the loop
   was driving, it pauses first; if a checkpoint is already waiting, the
   checkpoint keeps the human in control and no extra pause is added.
2. While the human drives, the operator does not scan, click or type. The live
   page is theirs.
3. `POST /api/agent/takeover/return` takes the page back, disables human input
   during a fresh scan, and rebuilds the operator blueprint and the shared page
   brief (`adopt_blueprint=True`). The run stays paused.
4. The human reviews the fresh brief and presses Continue. Resuming is always
   explicit; nothing auto-resumes after a takeover.
5. At a checkpoint the human still has an open question, so control is handed
   back to them after the rescan; the checkpoint itself is unchanged.

Decisions:

- **One owner at a time.** Human control and operator actions never overlap.
  `_release_live_control` refuses to take control back while a takeover is
  active, so a gate closing cannot silently steal the page.
- **Return means re-perceive.** The page may have navigated while the human was
  driving, so the operator adopts a new blueprint and a new brief. Cached
  handles from before the takeover are never reused.
- **Paused is the default after return.** A driving run stays paused until the
  human presses Continue. The takeover is over, but the run is not resumed
  automatically.
- **The state is visible.** `GET /api/agent/state` now carries
  `takeover: {available, active, paused_run, started_at, control_enabled}`.
- **The cockpit makes it obvious.** The live view shows "Take over" whenever a
  live page exists, "Return & rescan" while the human owns it, and a
  "You have the browser · FormPilot paused" badge over the page.

Acceptance for this slice:

- Takeover pauses a driving run and enables live control.
- Takeover is refused without a live browser.
- Returning control rescans, adopts the new page, and leaves the run paused.
- A gate closing while the human owns the page does not take control back.
- At a checkpoint, control returns to the human after the rescan.
- Stop/reset clear the takeover state.

### 16.28 Slice F: semantic-layer evaluation (2026-10-28)

`backend/core/evaluation.py` is an offline evaluation harness. It runs a small
set of page fixtures through perception -> deterministic brief -> fact
annotation -> fill plan and reports every check.

Fixtures:

- **HPSC personal details** - first/middle/last name, date of birth with a
  `DD-MM-YYYY` placeholder, name as per matric certificate, father's name,
  email + confirmation, mobile, photograph upload, and a Save & Next path.
- **HPSC OTP** - one human-only question and an OTP signal.
- **Candidate dashboard** - an application preview, a proceed action and a
  logout, plus a registration ID in the visible text.
- **HPSC landing** - register and login as two account paths.
- **Expired session** - an error page with no fields.

Checks per case:

- page type,
- concept for every field,
- fill-plan state for every field,
- planned value and date format,
- number of paths that need a human choice,
- human-only detection and page information,
- false-claim checks: a `fill` instruction must carry a value, and a
  `human_only` instruction must not.

Reporting:

- `run_evaluation()` returns `passed`, `metrics`, `failures` and per-case
  checks.
- `format_report()` renders a short human summary.
- `scripts/evaluate_semantic_layer.py` runs it offline and exits non-zero on a
  failure; `--json` prints the full report.
- `tests/test_evaluation.py` keeps the fixtures green and asserts the HPSC
  date, name-part, OTP and dashboard/landing regressions.

Finding from the first run: a dashboard `next` action was classified as
navigation, so "Proceed for Universal Registration" did not ask the human to
choose. `_path_kind` now treats `next` as an application action on a dashboard
as well as on a form. The fixture caught a real classification gap.

Deliberately not run in this slice: the live practice-portal end-to-end flow.
The user cannot supply OTP/human steps right now, so portal verification is
deferred until they are available. The automated suite and the evaluation
harness cover the semantic layer offline.

### 16.29 Portal account memory (2026-10-28)

`backend/core/portal_accounts.py` stores what is known about a candidate's
account on one portal. It is deliberately separate from the vault: "I have an
account on regn.hpsc.gov.in" is not a global profile fact.

Records:

- keyed by `(domain, identifier_type, identifier_value)`,
- `account_exists`: `yes | no | unknown`,
- `identifiers_seen`, `login_method`, `registration_status`,
  `last_known_step`, `last_path_choice`,
- `confirmed_by_human_at` and `updated_at`.

A domain-level summary aggregates accounts so FormPilot can say "you have an
in-progress application here" without guessing which identifier it belongs to.
Identifier values are masked in every public view.

Read-only inspection:

- `PortalAccountStore.inspect_login_ui` reads the visible page or DOM and
  reports the login methods, recovery links and hints.
- It never submits a credential, requests an OTP or resets a password.
- `GET /api/page/login-options` exposes the inspection for the current page.

Integration:

- The entry/next-step gate now carries `account_memory` and
  `login_inspection`. The cockpit shows what is remembered and the visible
  sign-in options, labelled as a read-only check.
- When the account status is unknown, the gate asks once: "Have you registered
  on this portal before?" The answer is stored with
  `confirmed_by_human_at`. "Not sure" is stored as unknown and is not asked
  again in the same gate.
- Choosing an entry path, a login method, an account identifier or approving a
  section records the corresponding memory. Path choice is not turned into an
  `account_exists` guess; only an explicit answer does that.
- The chat has `get_portal_account` and `remember_portal_account` tools and a
  prompt rule that forbids probing the portal to discover an account.
- API: `GET /api/portal-accounts`, `PUT/DELETE
  /api/portal-accounts/{domain}`.

Decisions:

- **Domain plus identifier, with a domain summary.** This matches the locked
  decision in 16.21.
- **Explicit answers only.** A path choice is recorded as a choice, not as
  proof that an account exists.
- **The store is encrypted at rest** with the same envelope as the vault and
  facts when `FORMPILOT_VAULT_KEY` is set.

Acceptance for this slice:

- A portal fact is scoped to its domain and identifier.
- A domain summary aggregates identifiers without revealing them.
- Unknown stays unknown until a human confirms it.
- Inspection reports methods and recovery paths without touching the page.
- The gate and chat can read and record the memory.
- Invalid values and domains are refused.

### 16.30 Portal account conflicts (2026-10-28)

Rule 16.18 says: if the human says "first time" but the portal reports the
identifier as already registered, do not fail silently. This slice implements
that rule.

Detection (`PortalAccountStore.detect_registration_conflict`):

- reads only text the page already shows (Perception or legacy DOM),
- matches explicit phrases: "already registered", "already exists", "already
  in use", "already linked", "duplicate registration", and the mobile/email
  variants,
- returns the matched phrase plus the sentence around it as evidence,
- never submits the identifier, requests an OTP or resets anything.

Correction (`PortalAccountStore.mark_conflict`):

- the earlier "no" answer is contradicted by the page, so the fact drops back
  to `account_exists: unknown` and `confirmed_by_human_at` is cleared,
- `last_known_step` becomes `registration_conflict` and the page sentence is
  kept in `conflict_evidence`,
- the identifier itself is not erased: the record still belongs to the same
  mobile/email.

Gate (`build_conflict_gate`, `gate_type: ACCOUNT_CONFLICT`):

- quotes the portal's sentence, states what the human said earlier, and lists
  the visible sign-in options as a read-only check,
- four explicit choices, no default: sign in, recover the account, register
  with a different identifier, stop,
- sign-in records `account_exists: yes` with the visible login method and
  applies the login entry path when the page offers one; otherwise the human
  finishes the step in the live browser,
- recover hands the browser over with the visible recovery links and never
  resets anything,
- register-with-another-identifier records `needs_other_identifier` and asks
  the human to enter a different number in the browser,
- stop ends the run and leaves the browser where it is.

Integration:

- `_account_conflict_checkpoint` runs in the drive loop after every scan, and
  only when memory says `account_exists: no`. Each detected conflict is
  handled once per run (signature includes domain, phrase and evidence).
- The cockpit renders the conflict block with the evidence, the read-only
  sign-in options and the four buttons.
- Chat prompt rule 13 tells the assistant to surface the conflict and never
  fill the registration form over it.
- `domain_summary` exposes `conflict_evidence` so the chat and cockpit can
  explain what happened later.

Deliberately not run in this slice: the live practice-portal conflict flow.
The user cannot supply OTP/human steps right now. The automated tests cover
detection, correction, gate shape and both orchestrator outcomes (stop, and
switch to login) offline.

## 17. Engineering lessons from Skyvern (2026-10-29)

We studied Skyvern at `/tmp/BharatCode/skyvern` (commit `b04c3f7`) in six
parallel deep reads: agent loop, perception/actions, workflow engine,
human-in-the-loop/security, infra/testing, and product/UX. The full CTO
write-up, with file-level evidence, lives in `docs/skyvern-learnings.md`.
This section records the decisions that affect the product plan.

### 17.1 The separations worth copying

Skyvern's value is not "an LLM that clicks"; it is five separations:

1. **Perception vs action** — reads are explicit tools, so the model cannot
   act on a page it has not just read.
2. **Action vs commit** — a value is filled only when a fresh read shows the
   portal kept it, classified as `same`, `reformatted`, `not_held` or
   `different`.
3. **Completion vs claim** — finishing is a gated verdict, not a sentence the
   agent writes about itself.
4. **Agent vs judge** — the verifier sees page evidence and tool results, not
   the agent's reasoning.
5. **Policy vs effect** — one human approval authorises exactly one effect,
   bound to a snapshot of the page.

FormPilot already has the right product shape (human-gated, explainable, no
guessing). These separations are the engineering discipline around it.

### 17.2 Slice G — field commit verdicts (done)

- `backend/core/field_commit.py` classifies what the portal kept:
  `same / reformatted / not_held / different`, mapped to
  `ok / did_not_commit / unverified`.
- Comparison is kind-aware: text, password, email, digits (country code is a
  reformat; truncation is not), date (ISO vs DD/MM/YYYY is a reformat;
  a different day is not), select, multiline. A plain text box labelled
  "Date of Birth" or "Mobile Number" gets the right rules.
- `_verify_fill_targets` now does one bounded retry for values the portal
  dropped or replaced, then reads back again. Selects, checkboxes and
  uploads are never retried.
- `fill_summary` gains `reformatted` and `retried`; each field result carries
  its commit verdict; failures carry the verdict and whether they were
  retried.
- `_values_match` delegates to the same rules, so "already filled" and
  "verified after fill" can never disagree.
- Tests: `tests/test_field_commit.py` (unit matrix + three real-DOM cases:
  dropped-once, truncating, reformatting).

### 17.3 Roadmap after Slice G

- **H. Run ledger** — steps, attempts, outputs, error codes, token/cost
  columns; structured events; run history API.
- **I. Security boundaries** — page text labelled untrusted; fill plans carry
  fact keys rather than raw values; final-submit approval frozen to a
  snapshot and re-verified before the click.
- **J. Gate quality** — closed reason enums, a recommended option, and
  attended-time budgeting.
- **K. Legibility** — summary strip, failure line, timeline linked to the
  brief, screenshot and fill plan for each step.
- **L. Scale-out** — SDK/CLI, cost metering, keyset pagination. Only after the
  local product is reliable.

### 17.4 Rejected on purpose

CAPTCHA solving, credential pools, policy that does not block, "take control"
that does not pause the agent, a 33-block workflow DSL, 100k-token prompts,
marathon turn budgets, email approvals, and fail-open completion. Reasons are
in `docs/skyvern-learnings.md` §3.

### 17.5 Metrics

Commit accuracy and false-success rate, reformat rate, retry rate, gate dwell
time, fields per minute, LLM calls per section, run completion and
abandonment point. The offline evaluation harness remains the merge gate and
will assert these as the ledger lands.

### 17.6 Slice H — run ledger and structured events (done)

A log says what was said; a ledger says what was attempted, against which
page, with what result, and how long it took. `run_store.py` now writes
`steps.json` beside `meta.json`, `events.jsonl` and `audit.json`.

Step rows:

- `step_id`, `seq`, `kind`, `status`, `page_signature`, `input_digest`,
  `attempt`, `started_at`, `finished_at`, `duration_ms`, `output`,
  `error_code`, `retryable`.

Recorded phases: `run`, `perceive`, `fill`, `advance`, `error`, `gate`,
`takeover`, `submit`. A gate is one row from `waiting` to `resolved` (or
`dismissed`/`stopped`/`timed_out`); a retry is a new row with
`attempt > 1`, never an overwrite. The pre-payment/final-submit lock records a
`submit` row with the audit hash and `final_action`.

Failure taxonomy (`failures.py`): `navigation_failure`, `auth_failure`,
`anti_bot`, `element_not_found`, `field_not_held`, `wrong_page`, `timeout`,
`budget_exceeded`, `portal_error`, `internal_error`. Only navigation, element
loss, timeout and portal errors are retryable; auth, anti-bot, wrong page and
a value the portal did not keep are not.

Redaction is enforced at the storage boundary: secret-looking keys become
`***`, text is capped, and a gate stores only the action name, never the
answer itself. A test
asserts an OTP never reaches `steps.json`.

API: `GET /api/runs` (limit/offset, now includes duration, error code, step
count), `GET /api/runs/{run_id}` (meta + steps + summary + events + audit),
`GET /api/runs/{run_id}/steps`.

Acceptance: a run can be reconstructed from disk after a restart; a retry is
its own row; no secret is stored. `tests/test_run_store.py` covers the ledger,
redaction, persistence, failure codes and the API.

Next: Slice I (security boundaries), then J (gate quality and attended time),
K (legibility) and L (scale-out).

### 17.7 Slice I — security boundaries (done)

Three boundaries now sit between the portal and the model.

**Page text is untrusted.** The page-brief prompt opens with a boundary
paragraph and rule 9, and the chat prompt has rule 14: labels, notices, error
messages and attributes are data to read and quote, never instructions. Text
that says "ignore previous instructions" cannot change the plan or the rules.

**Identifiers do not reach the model.** `_state_context` masks a real login
identifier: a phone number keeps its last four characters, an e-mail keeps one
local character and its domain. Field keys such as `mobile`, `email` or
`aadhaar` are not identifiers and pass through unchanged.

**The persisted audit is masked.** `_persisted_audit` copies the pre-payment
records with `vault_value` and `form_value` reduced to a last-four mask. The
gate's `audit_diff` keeps the display copy the human reviews. The payload
records `values_masked: true`, the display `audit_hash`, and a separate
`persisted_records_hash`.

**The review is frozen to a snapshot.** At the pre-payment/final-submit lock
FormPilot stores `run_id`, URL, audit hash, a digest of visible field values
and a timestamp. On `return_human_control` it re-reads the page. If the URL or
the value digest changed, it sets `approval_valid = false` and
`snapshot_changed = true` on the gate, emits a warning, and records a `submit`
step with status `invalidated` (`wrong_page` or `field_not_held`). A second
return with no further change reports `already_invalidated` without a
duplicate row.

Acceptance: `tests/test_security_boundaries.py` covers the prompt boundary,
identifier masking, audit masking, an unchanged snapshot, a changed field and
a changed URL. Full suite: 335 passed, 2 skipped.

Next: Slice J (typed gate reasons, recommended option, attended-time
budgeting), then K (legibility) and L (scale-out).

### 17.8 Slice J — typed gates and attended time (done)

A gate is now a typed stop, not a free-text interruption.

`backend/core/gates.py` owns a closed `GateReason` enum and maps every
`gate_type` to one reason: entry path, next step, account conflict, login
method, account identifier, missing fact, unknown field, incomplete fill,
section review, CAPTCHA, OTP, live photo, file upload, human handoff,
pre-payment review, error diagnosis, and `unknown` as the explicit fallback.

`apply_gate_metadata` stamps each gate with `reason`, `gate_opened_at`,
`gate_timeout_seconds` and `gate_deadline_at`. The ledger's `gate` row carries
the reason, and the chat state context exposes it with the optional
`recommended` entry.

**Recommendations are conservative.** A gate that exists because the human
must choose never carries a recommendation: entry path, login method, account
identifier, account conflict, section review, pre-payment review and every
human-only gate. Only two gates recommend a safer first move:
`FILL_INCOMPLETE` recommends `FILL_RECHECK`, and `ERROR_DIAGNOSIS` recommends
reading the portal message before retrying.

**Attended time.** The run clock separates active work from attended gate
time. `RUN_CEILING_SECONDS` (30 min) budgets active work and pauses while a
gate is open; `RUN_WALL_CEILING_SECONDS` (2 h) is the absolute ceiling that
still applies to a paused run. The gate timeout default moved from 5 to 30
minutes so a real ten-minute human pause cannot expire the gate. The clock is
exposed in `get_state` and every event as `run_clock`:
`wall_seconds`, `attended_seconds`, `active_seconds`, `ceiling_seconds`,
`wall_ceiling_seconds`, `gate_open`.

The cockpit modal renders the reason label and the suggested first step from
the enum, with a generic fallback for an unknown code.

Acceptance: `tests/test_gates.py` covers every gate type, the
no-recommendation rule, the two safe recommendations, gate dwell in the
ledger, the paused run clock and the absolute wall ceiling. Full suite:
362 passed, 2 skipped.

Next: Slice K (legibility), then L (scale-out).
