---
phase: 03-models-knowledge-bases-and-upload
plan: 22
subsystem: ui
tags: [models-page, default-models, defaults-card, live-journey, openrouter, read-only-member, i18n]

requires:
  - phase: 03-models-knowledge-bases-and-upload
    provides: "03-13 defaults API; 03-20 Models page and read hooks; 03-21 provider dialogs and mutations; 03-27 live provider tier (key loading, model variables, call budget); 03-03 live web tier (accounts, ingress)"
provides:
  - web/src/pages/user-setting/model/defaults-card.tsx (DefaultsCard: form for owner and admin, definition list for members)
  - web/src/services/model-service.ts saveDefaults, web/src/hooks/use-llm-request.ts useSaveDefaultsRequest
  - web/src/test/live/provider-key.ts (liveProviderKey, endsWithKeyTail, containsKeyFragment)
  - web/src/pages/user-setting/model/models.live.test.ts (live Models journey on the real stack with the real provider)
affects: [03-23 dataset gallery (uses the embedding default), Phase 3 verification]

tech-stack:
  added: []
  patterns:
    - "Defaults form is remounted (key = effective saved ids) whenever the saved values or the model list change, so dirty state never outlives the server state"
    - "The submit compares against a baseline ref, so a repeated click after a save sends nothing even before React re-renders"
    - "Live tests that type a secret turn off the testing-library DOM dump and assert about the secret only with booleans"

key-files:
  created:
    - web/src/pages/user-setting/model/defaults-card.tsx
    - web/src/pages/user-setting/model/defaults-card.test.tsx
    - web/src/pages/user-setting/model/models.live.test.ts
    - web/src/test/live/provider-key.ts
  modified:
    - web/src/services/model-service.ts
    - web/src/services/model-service.test.ts
    - web/src/hooks/use-llm-request.ts
    - web/src/pages/user-setting/model/index.tsx
    - web/src/pages/user-setting/model/models-page.test.tsx
    - web/src/locales/en.json
    - web/src/locales/zh.json

key-decisions:
  - "The initial value of each select is the saved default only while its model still exists in the workspace; nothing is preselected (D-18, T-03-22-02). Both selects are disabled with the matching helper when no model of that type exists."
  - "The defaults card owns its loading, failure and retry, independent of the providers card; a failure in one never hides the other (tested both ways)."
  - "Members' card calls only the defaults route (no model list) and shows composite ids in mono or 'Not set' in muted text; no select, no button."
  - "Inline error: the server sentence for a 400/404/409 (bounded to 300, text node); fixed copy 'The default models weren't saved. Try again.' for anything else."

patterns-established:
  - "Pattern: live browser tests read the provider key through provider-key.ts (env var, else git-ignored docker/.env) and never print it"

requirements-completed: [UI-37, TEN-12, TEN-13, LLM-28]

duration: ~1h30m
completed: 2026-10-09
---

# Phase 3 Plan 22: Default models card and live Models journey Summary

**The Models page is complete: owners and admins pick the default chat and embedding model explicitly (both stay on "Not set" until chosen), members read the same two values as plain text, and a live journey through the real SPA, ingress and OpenRouter proves set up, mask, persisted defaults, refusal of a bad key without losing the session, a valid key change, and the member's read-only view.**

## Accomplishments

- `saveDefaults(tenantId, changes)`: PATCH `/api/v1/models/default` with `tenant_id` and only the named fields (composite id, or `null` to clear); `useSaveDefaultsRequest` writes the answer into the defaults cache and refetches on settle.
- `DefaultsCard({ role })` mounted as the second card of the page: skeleton with an announced status, in-place `ErrorState` (noun "default models"), a `max-w-md` form (`defaults-form`, `default-chat`, `default-embedding`, `defaults-submit`) with `LlmSelect` grouped by provider and filtered by type, a single primary button that is `aria-disabled` until dirty and while saving, an inline `Alert` for refusals, the toast "Default models saved", and a `<dl>` for members.
- A saved default whose model is gone shows "Not set" and is not sent back; a repeated click sends one request.
- Copy: `models.defaults.*` (title, chat, embedding, embeddingHelp, noChat, noEmbedding, submit, saved, loading, failed) and `models.errorNoun.defaults` / `.settings`, en and zh with identical key sets.
- Live tier: `provider-key.ts` plus `models.live.test.ts` (4 tests, fresh owner and member accounts per run).

## Task Commits

| Task | Commit | Result |
|------|--------|--------|
| 1 Failing defaults-card and service tests, live suite, key loader | `d71eba7` | red run below |
| 2 Defaults mutation, hook, card, locale keys | `a255cf4` | defaults tests green |
| 3 Mount the card, update the page tests | `079060c` | full suite green |
| 3 (follow-up) live test closes the dialog with Escape | `6f87977` | live file green |

## Verification (real output)

Red run (before implementation), `npm run test -- --run src/pages/user-setting/model/defaults-card.test.tsx src/services/model-service.test.ts`: `Test Files  2 failed`, the card file failing on `Cannot find module './defaults-card'` (also `tsc`: TS2307) and the two new service tests on `TypeError: saveDefaults is not a function`.

Green runs:

- Targeted after Task 2: `src/locales src/pages/user-setting/model src/services src/components` -> `Test Files  16 passed (16)`, `Tests  295 passed (295)`.
- Full unit suite after Task 3: `cd web && npm run test -- --run` -> `Test Files  41 passed (41)`, `Tests  807 passed (807)`. `npm run typecheck` exit 0. `npm run build` exit 0 (`built in 11.29s`). `git diff --stat -- web/package.json web/package-lock.json`: empty.
- Stack rebuilt once with `PREFLIGHT_ALLOW_LOW_MAP_COUNT=1 PREFLIGHT_PORTS= make up` (exit 0, layers cached) and `scripts/wait_stack.sh`: `stack ready:` app, es01, minio, mysql, redis, mailpit healthy, init exited. Web on 8088.
- Live, `LIVE_BASE_URL=http://127.0.0.1:8088 npm run test:live -- src/pages/user-setting/model/models.live.test.ts`:
  - first run: `Tests  1 failed | 3 passed (4)`; the failure was my own query (two buttons named "Close" in the dialog), fixed by closing with Escape.
  - second run: `Test Files  1 passed (1)`, `Tests  4 passed (4)`, `Duration  8.88s`.
  - The captured output of both runs was scanned for the key and every 12-character window of it: not found.
- What the live file asserts (all passed): before setup both selects are disabled with their helpers; set up through the dialog; row shows "Configured"; mask ends in the key's last four characters and contains the bullet mask; both models listed, embedding with `1024 dimensions`; the key is not in the page HTML; selects start on "Not set" although models exist; after choosing and saving, a fresh render shows both selected and the "Default chat" / "Default embedding" badges, and `GET /api/v1/models/default` holds the same ids; a made-up key shows `provider-refusal` ("OpenRouter refused this configuration" plus the provider's reason) while the path is still `/user-setting/model`, the stored token is unchanged, no "Session expired" text and no toast exist, the dialog stays open, and after closing the row mask is unchanged; a valid key change (no model field shown) closes the dialog, toasts "OpenRouter updated", keeps both models and both defaults and the models API still lists both with the 1024 dimension; a member of the joined workspace sees `models-readonly-notice`, the configured provider with no mask and no address, the defaults as `dt`/`dd` text with the model names, no select and no button.

Live provider calls: each run made 3 saves (set up with 2 models = 2 real calls, bad key = 1 refused call, valid key change = 1 call): about 4 real provider calls per run, 8 over the two runs. Models: `meta-llama/llama-3.1-8b-instruct` and `baai/bge-m3` (1024). OpenRouter accepted the real key (no 401 or 402).

## Deviations from Plan

### Instructed by the orchestrator

**1. [Decision] Real OpenRouter key in the browser tier instead of the Node fake provider**
- **Plan said:** the browser tier uses a loopback Node fake provider (`fake-provider.ts`, `startFakeProvider`) and never the real key (T-03-22-04).
- **Instruction received:** run the live Models journey with real OpenRouter calls and the user's key from the git-ignored `docker/.env` (D-01, D-29), the bad-key case with a made-up key.
- **Done:** `fake-provider.ts` was not written. The key is loaded by `web/src/test/live/provider-key.ts`, typed into the dialog, and kept out of output: the testing-library DOM dump is replaced for this file (a controlled password input's value would be part of it), assertions about the key are booleans (`endsWithKeyTail`, `containsKeyFragment`), and the run output was scanned for the key (none).
- **Consequence:** the plan's step (2b) asserted that the fake recorded one new chat request carrying the new key's last four characters. With one real key that exact assertion is not possible (the "new" key is the same). The replacement checks the observable result: the dialog closes after a passing real test, the toast "OpenRouter updated" shows, the mask still ends with the key's tail, both models and both defaults remain, and the models API still lists both. That the other model is re-sealed with the new key is covered by the server tests of plans 03-10 and 03-12.
- **T-03-22-04 status:** not mitigated by design any more; the exposure is limited to the test process memory, the typed password field and the request to the app, with the leak checks above.

### Auto-fixed Issues

**2. [Rule 1 - Bug] Page tests made wrong by the new card**
- **Found during:** Task 3 (full unit run)
- **Issue:** the page test server did not serve `GET /api/v1/models`, the exact owner button list gained "Save defaults", `getByRole("status")` matched two skeletons, and the "defaults request fails" test expected no error state.
- **Fix:** the in-memory server now serves the model list; the button list ends with the unlabelled "Save defaults" button; the skeleton query is scoped to the providers skeleton; the defaults-failure test asserts the card's own error and a new test asserts the providers failure leaves the defaults card in place.
- **Commit:** `079060c`

**3. [Rule 1 - Bug] Own test mistakes**
- The first card test counted the membership request among model reads (fixed by filtering to `/api/v1/models`); the first live run's Close-button ambiguity (fixed with Escape, `6f87977`).

## Known Stubs

None.

## Threat Flags

None new. T-03-22-01: members get a `dl` and no control (tested; the server 403 is plan 03-13). T-03-22-02: initial values only from saved defaults that still exist (unit test with models present and nothing saved). T-03-22-03: the live bad-key case asserts path, token and the absence of any session text or toast. T-03-22-04: see deviation 1. T-03-22-05: no fake listener was started, so nothing listens on all interfaces.

## Notes for plan 03-23

- Dataset creation can read the embedding default through `useDefaultsRequest()` (query key `["ws", tenantId, "defaults"]`); an unset default is the empty string.
- Test ids on the Models page now include `defaults-card`, `defaults-form`, `default-chat`, `default-embedding`, `defaults-submit`, `defaults-skeleton`, `defaults-error`, `defaults-readonly`.
- Live tests that need the provider key use `liveProviderKey()`; every live provider save costs real calls, and the budget is 10 saves per 300 s per workspace.

## Self-Check: PASSED

- Files present: defaults-card.tsx, defaults-card.test.tsx, models.live.test.ts, provider-key.ts (checked with `ls`).
- Commits present in `git log`: d71eba7, a255cf4, 079060c, 6f87977.
