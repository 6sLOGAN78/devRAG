---
phase: 03
depth: standard
files_reviewed: 122
status: issues_found
critical: 0
warning: 13
info: 24
reviewed: 2026-10-10
parts:
  - 03-REVIEW-backend.md
  - 03-REVIEW-web.md
---

# Phase 3 Code Review

The review covered the 124 source files Phase 3 changed (about 15,300 lines), excluding tests, generated files and locale files. It was split into two parts because one reviewer could not read that much properly. Full findings, with file and line, scenario and fix for each, are in the two part files.

| Part | File | Files | Critical | Warning | Info |
|---|---|---|---|---|---|
| Backend | `03-REVIEW-backend.md` | 58 | 0 | 9 | 10 |
| Frontend | `03-REVIEW-web.md` | 64 | 0 | 4 | 14 |

Neither reviewer ran the test suite, Docker, a browser or a live provider. Findings are from reading code paths; the backend reviewer reproduced BE-03, BE-08 and BE-14 with small pure-function runs, and says BE-06 and BE-13 rest on Elasticsearch documentation rather than a run.

## Warnings

### Backend

| Id | Finding |
|---|---|
| BE-01 | Provider test calls have no total deadline: a slow-drip base URL can pin all 8 provider threads for every tenant, and a request the handler timed out still commits its save |
| BE-02 | Provider response bodies are read with no size cap, so an admin-chosen base URL returning a huge error body can exhaust memory |
| BE-03 | The echoed-key scrub runs after the 200-character cut, so a key that is not `sk-` shaped and straddles the cut leaves a prefix in the 400 body |
| BE-04 | The Nginx catch-alls and the status and healthz locations accept 1 GiB bodies with 3600 s timeouts before authentication; the Phase 3 JSON routes inherit the 3600 s timeouts |
| BE-05 | Master-key rotation is advertised in `.env.example` but unsupported: the keyring holds only the active key, so changing `LLM_KEY_ID` makes every stored provider key unreadable |
| BE-06 | The Elasticsearch `query_string` is built from raw user text: unbalanced quotes or parentheses fail the search, and leading wildcards are expensive |
| BE-07 | The async `LLMBundle` methods do blocking DNS and a synchronous MySQL write on the event loop |
| BE-08 | The Python log redactor skips non-string `extra` values such as exceptions, so `extra={"err": ValueError("api_key=...")}` is logged unmasked |
| BE-09 | Dataset and document `parser_config` is checked only for size, with no type or range check on the keys the Phase 4 chunker will read |

### Frontend

| Id | Finding |
|---|---|
| FE-01 | Pagination and the gallery search box unmount on every page or search change, so keyboard focus is lost |
| FE-02 | The active workspace is resolved in two steps, so a reload fires queries for the wrong workspace and wipes `page` and `keywords` |
| FE-03 | Dataset create, update and delete refresh the cache only on success, so a timeout that actually succeeded leaves the gallery stale and a retry gets `duplicate_name` |
| FE-04 | `DeleteDocumentDialog` carries an old error into the next opening |

## Reading these against the phase

- BE-06 concerns the search path, which Phase 5 owns; the port signature is defined here but no route calls it yet.
- BE-09 has no consumer until Phase 4.
- BE-01, BE-02, BE-03, BE-05 and BE-08 are in code this phase ships and users can reach.
- BE-04 predates this phase for the catch-all locations; the new JSON routes inherited the long timeouts.

## Next step

`/gsd-code-review 3 --fix` applies fixes for the Critical and Warning findings.
