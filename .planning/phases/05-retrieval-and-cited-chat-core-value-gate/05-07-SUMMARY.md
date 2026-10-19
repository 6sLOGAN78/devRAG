---
phase: 05-retrieval-and-cited-chat-core-value-gate
plan: 07
subsystem: chat-assistants
tags: [assistants, dialog, sharing, dataset-binding, migration, authorisation]
requires:
  - phase: 05-01
    provides: "decision rows and Phase 5 record tests"
  - phase: 05-05
    provides: "rerank model type used to validate rerank_id"
provides:
  - "Migration 0003: dialog.created_by and dialog.permission with indexes (idempotent, no-op on a fresh database)"
  - "tenant_scope.assistant_visible and can_manage_assistant"
  - "dialog_service: create_assistant, list_assistants, get_assistant, update_assistant, delete_assistant, load_visible_assistant, resolve_for_chat, sanitize_llm_setting"
  - "Rows R-209 (rules as built) and R-210 (view keys)"
affects: [05-08, 05-09, 05-11, 05-19, 05-27]
tech-stack:
  added: []
  patterns:
    - "Service answers dict views with an explicit key list; records are frozen dataclasses"
    - "Model services run before the caller opens a connection scope; a nested scope would close it"
    - "Per-reader dataset set computed by one batch query (live_datasets) and a pure openable() rule"
key-files:
  created:
    - api/db/migrations/0003_chat_assistants.py
    - api/db/services/dialog_service.py
    - api/db/services/dialog_rules.py
    - api/db/services/dialog_records.py
    - api/db/services/dialog_datasets.py
    - test/integration/test_dialog_service.py
    - test/unit_test/test_dialog_rules.py
  modified:
    - api/db/models/chat.py
    - api/db/services/tenant_scope.py
    - api/utils/reasons.py
    - conf/schema.json
    - internal/entity/dialog.go
    - test/unit_test/test_tenant_scope.py
    - test/unit_test/test_phase5_records.py
    - test/integration/test_migration_runner.py
    - test/integration/test_schema.py
    - test/helpers/accounts.py
    - .planning/DECISIONS.md
key-decisions:
  - "R-209: binding, per-reader chat-time set, keep-hidden save, narrowing count, manage matrix and delete cascade as built; a deleted dataset id is dropped by the next save that sends kb_ids"
  - "R-210: explicit view keys; PNG or JPEG data-URL icon up to 400,000 characters, detail only; hand-off to 05-08 about the 404 reason"
patterns-established:
  - "can_manage_assistant(creator, permission, caller, subject): creator, or owner/admin for team only, decided by the permission subject"
requirements-completed: []
duration: ~1h45m
completed: 2026-10-20
---

# Phase 5 Plan 07: Assistant Model and Service Layer Summary

Chat assistants now exist as a service layer with every ownership, sharing and dataset-binding rule (D-08..D-11, D-23..D-26) proven against real MySQL: private by default, shareable with the team, per-reader dataset sets at chat time, and a cascade delete of every member's sessions.

## Tasks

| Task | Commit | Result |
|------|--------|--------|
| 1. Columns, migration 0003, schema and Go entity, visibility helpers | b113e4c | `Dialog.created_by` and `Dialog.permission` (indexed), migration `0003_chat_assistants.py`, `conf/schema.json` and `internal/entity/dialog.go` regenerated, `assistant_visible` and `can_manage_assistant`, schema and migration tests moved to version 0003 |
| 2. Create, list, read and delete | 9f5e57b | `create_assistant`, `list_assistants`, `get_assistant`, `delete_assistant`, `load_visible_assistant`; validation module, view module, dataset-facts module; 75 integration tests (parametrized) plus 29 unit tests of the rules |
| 3. Update rules and the chat-time dataset set | e7d89a9 | `update_assistant` (D-23, D-24, D-25, widen check), `resolve_for_chat` and `ChatBinding`; 27 more integration tests; rows R-209 and R-210 |

## What was built

- **Visibility and management.** `assistant_visible` has the dataset truth table (a `me` assistant is invisible to owner and admin). `can_manage_assistant` is the creator, or owner/admin for `team` only; the service passes `scope.subject`, so an API token is never elevated (tested).
- **Binding (D-10).** Team assistants bind team datasets only; widening checks every live bound dataset, hidden ones included, and names only offenders the caller can open; staying `team` checks only ids added by the save.
- **Per reader at chat time (D-25).** `resolve_for_chat` returns the bound ids that exist in the workspace and that the asker can open, with `unavailable_count` for the rest, no error when none are usable. The view's `kb_ids` and `unavailable_datasets` use the same rule, which a test asserts.
- **Keep-hidden save (D-25).** Stored ids the saver cannot open are kept; the requested ids follow.
- **Narrowing (D-23).** 409 `assistant_has_member_chats` with `data.count` of distinct users other than the creator; checked under the row lock; nothing deleted.
- **Delete (D-26).** One transaction deletes every `Conversation` of the assistant and the assistant, with a rollback test.
- **Locks.** Create and rename take `dialog-create:{tenant_id}`; update and delete take the dialog row `FOR UPDATE`. A test holds the row lock the way plan 05-09 will and shows a narrowing waits, then sees the session that committed first.

## Verification

- `uv run python -m pytest -m integration test/integration/test_dialog_service.py test/integration/test_migration_runner.py -q`: 115 passed. `test_schema.py` live checks pass with version 0003.
- `uv run python -m pytest test/unit_test/test_tenant_scope.py test/unit_test/test_schema_export.py test/unit_test/test_gen_go_entities.py test/unit_test/test_phase5_records.py test/unit_test/test_dialog_rules.py -q`: 92 passed.
- `uv run python scripts/export_schema.py --check` exit 0; `uv run python scripts/ci/run_all.py`: 7/7 gates (decisions 210 rows); `go build ./internal/... ./cmd/...` clean.
- `grep -c 'd23\|d24\|d25\|d26'` in the integration file: 13; `grep -c '^| R-209 \|^| R-210 '`: 2.
- The live `rag_flow` database was brought to version 0003 with the migration runner so the integration tests see the columns.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `sanitize_llm_setting` did not exist**
- **Found during:** Task 2
- **Issue:** The plan says `llm_setting` goes "through `sanitize_llm_setting`" and plan 05-11 imports it from `dialog_service`, but no such function existed (only the driver-side `sanitize_gen_conf`).
- **Fix:** Added `sanitize_llm_setting` in `dialog_rules.py`, re-exported from `dialog_service`. It refuses an out-of-range or unknown key with `fields_invalid` instead of clamping, so a stored value is always safe for the driver; the turn service can call it again on stored values.
- **Files modified:** `api/db/services/dialog_rules.py`, `api/db/services/dialog_service.py`
- **Commit:** 9f5e57b

**2. [Rule 3 - Blocking] Test cleanup left assistants and sessions behind**
- **Found during:** Task 2
- **Issue:** `AccountRegistry.cleanup` removed datasets but not `dialog` or `conversation` rows of a tenant.
- **Fix:** `_delete_chat_rows` in `test/helpers/accounts.py`, parameterised by the recorded tenant id.
- **Commit:** 9f5e57b

**3. [Rule 1 - Defensive validation] Icon charset gate**
- The plan gates the icon by prefix and length. The remainder must also be base64 characters only, so an icon cannot carry markup into an image source. Tested with a `<script>` suffix.

### Choices the plan left open

- **Module split.** The plan allowed a second file past about 350 lines. The service is split into `dialog_service.py` (operations, 380 lines), `dialog_rules.py` (pure validation, 206), `dialog_records.py` (frozen records and the view) and `dialog_datasets.py` (batch dataset facts and binding checks), not only `dialog_rules.py`.
- **Return shapes.** `create_assistant`, `get_assistant` and `update_assistant` return the detail view dict for the caller; `list_assistants` returns `(items, total)`; `resolve_for_chat` returns the frozen `ChatBinding`. Plan 05-08 can map these straight to envelopes.
- **Deleted datasets.** A bound id whose dataset was deleted is dropped by the next save that sends `kb_ids`; hidden (existing but unopenable) ids are always kept. Otherwise the unavailable notice could never clear. Recorded in R-209.
- **Embedding check scope.** On update the one-embedding-model check covers the requested ids only, so a hidden dataset can neither block a save nor be revealed by it. Chat time re-checks per reader.
- **Missing `llm_id`.** A create without a chat model, or with a null one, is `model_unavailable`; the model is never chosen for the caller (D-18 spirit).
- **Unchanged models are not re-validated.** A save that does not change `llm_id` or `rerank_id` skips the model lookup, so an assistant whose model was later removed can still be edited (tested).
- **TDD ordering.** Tests were written before the code for each task. For Task 2 the first full run was green on the first execution because the implementation was written in the same pass as the tests; the update and chat-time code was held back from the Task 2 commit so each commit contains only code its tests cover.

## Hand-offs

- **Plan 05-08 (routes).** `api/apps/service_errors.py` maps every `NOT_FOUND` to a bare 404 body, so a `dataset_not_found` service error loses its reason. The contract (R-210, UI-SPEC) wants `data.reason == "dataset_not_found"` for the SPA's Datasets field while an assistant miss stays bare. The route layer must special-case that reason (or the mapper must); the service sets the reason distinctly (`dataset_not_found` against internal `assistant_not_found`).
- **Plan 05-09.** Take `Dialog ... .for_update()` inside `with DB.connection_context(), transaction():` when creating a session; do not call `scope_for_tenant` inside that scope (it opens its own and would close yours). `load_visible_assistant` resolves the scope before any scope of the caller is open.
- **Plan 05-11.** `resolve_for_chat(principal, chat_id)` plus `sanitize_llm_setting` are importable from `api.db.services.dialog_service`.

## Known Stubs

None.

## Deferred Issues

Pre-existing lint findings outside this plan: `E501` in `test/helpers/ingest.py:402` and import-order or f-string findings in five `test/unit_test` files (`test_container_scripts.py`, `test_llm_registry.py`, `test_local_storage.py`, `test_model_ref.py`, `test_storage_factory.py`). Not touched.

## Threat Flags

None beyond the plan's register. T-05-07-01: `assistant_visible` has no override, `can_manage_assistant` elevates for `team` only, both roles tested. T-05-07-02: `resolve_for_chat` re-checks openability per reader. T-05-07-03: keep-hidden algorithm tested. T-05-07-04: row lock held-lock test. T-05-07-05: one NOT_FOUND body, offender ids limited to datasets the caller can open (a hidden offender yields an empty list). T-05-07-06: icon, prompt, dataset-count and stored-id caps tested at their boundaries.

## Next Phase Readiness

Plan 05-08 can build the five assistant routes on these functions; plan 05-09 can add sessions on the same row lock; plan 05-11 can call `resolve_for_chat`. Requirements CHAT-01..07 are not ticked (the orchestrator does that at verification).

## Self-Check: PASSED

Files verified present: `api/db/migrations/0003_chat_assistants.py`, `api/db/services/dialog_service.py`, `dialog_rules.py`, `dialog_records.py`, `dialog_datasets.py`, `test/integration/test_dialog_service.py`, `test/unit_test/test_dialog_rules.py`. Commits b113e4c, 9f5e57b and e7d89a9 verified in git log.
