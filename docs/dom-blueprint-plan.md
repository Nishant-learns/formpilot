# FormPilot DOM Blueprint Plan

Status: implementation reference
Last updated: 2026-10-27

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
