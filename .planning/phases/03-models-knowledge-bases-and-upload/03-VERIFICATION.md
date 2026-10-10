---
phase: 03-models-knowledge-bases-and-upload
verified: 2026-10-10
status: human_needed
score: 5/5 success criteria verified; 65/65 requirement IDs claimed by a plan and satisfied; 0 gaps
overrides_applied: 0
gaps: []
human_verification:
  - test: "Window drop guard in a headed browser (B-31)"
    expected: "Dropping a file on the page header (outside the dataset drop area) does not make the browser navigate to or open the file; a dropped folder is ignored"
    why_human: "Headless Chrome driven through Input.dispatchDragEvent does not navigate an unguarded page, so no automated assertion can fail; only jsdom covers the guard"
  - test: "Keyboard focus return after the upload, dataset settings and delete dialogs (B-31)"
    expected: "Closing each dialog with Escape or its button returns focus to the control that opened it"
    why_human: "Covered by jsdom onCloseAutoFocus tests only, never in a real browser"
  - test: "Visual and accessibility pass of the model settings page, datasets gallery, dataset page and upload dialog in light and dark theme (UI-10, UI-11, UI-12, UI-37, 03-UI-SPEC.md)"
    expected: "Layout, contrast, focus ring, empty states and the workspace selector match 03-UI-SPEC.md"
    why_human: "The models settings page is exercised by jsdom plus live API-client tests, not rendered by a real Chrome. Only the datasets and dataset pages run in real Chrome, and only as functional journeys"
  - test: "Read the Phase 3 Chinese strings in web/src/locales/zh.json"
    expected: "Provider, dataset, document and upload text reads correctly; corrections go into zh.json"
    why_human: "Strings are draft Chinese written by the agent (D-21); key parity is checked by tests but no Chinese reader has reviewed the text"
---

# Phase 3: Models, Knowledge Bases and Upload Verification Report

**Phase goal:** A tenant can connect a real model provider, create a knowledge base whose index is provisioned with the right vector dimension, and upload documents into it.
**Verified:** 2026-10-10
**Status:** human_needed. All five success criteria hold against the running stack. The four open items need a person; none is a gap.
**Re-verification:** No, initial verification.

Evidence types used below: **RUN** = I ran it in this session; **GATE** = taken from the committed gate record (`03-29-GATE-LOG.md`, `03-VALIDATION.md`); **CODE** = read in the source; **NOT** = not verified.

## Test runs in this session (stack healthy on web port 8088)

| Command | Result |
|---|---|
| `uv run python run_tests.py -m unit` | 1816 passed, 2 skipped, 0 failed (RUN) |
| `uv run python scripts/ci/run_all.py` | 7/7 gates passed, decisions 153 rows (RUN) |
| `test_provider_flow`, `test_models_flow`, `test_dataset_flow`, `test_dataset_lifecycle_flow`, `test_create_kb_e2e` | 67 passed (RUN) |
| `test_upload_flow`, `test_document_flow`, `test_phase3_isolation`, `test_response_leaks` | 132 passed (RUN) |
| `test/integration/` storage, ES doc store, document and upload services, key at rest, KB service, dataset lifecycle, LLM bundle | 254 passed (RUN) |
| `test_spa_browser.py` (real headless Chrome) | 11 passed (RUN) |
| `run_tests.py -m live_model` (one run, real OpenRouter, ~6 calls) | 6 passed (RUN) |
| `cd web && npm run test -- --run --maxWorkers=4` | 56 files, 1135 tests passed (RUN) |
| `cd web && npm run test:live` against the stack | 11 files, 46 tests passed (RUN) |
| Clean-room gate, 3 consecutive runs (746/782/762 s, live-model PASS x3) | passed (GATE; not re-run, as instructed) |

Read-only inspection after the runs: `tenant_llm` has 3 rows, all `v1:` envelopes, 0 non-`v1:` non-empty values, 0 `sk-` prefixed values, lengths 77 to 141 (RUN). The tests remove the datasets, documents and tenants they create, so no leftover index or blob was left to list; the per-dataset index and blob assertions come from the tests themselves.

## Success criteria

| # | Criterion | Verdict | Evidence |
|---|---|---|---|
| 1 | Owner adds provider credentials and sets default chat and embedding models; key masked in every response and encrypted in MySQL; real chat and real embedding succeed with usage recorded | VERIFIED | RUN: `live_model` tier passed against OpenRouter: save tests the key with a real call, PATCH `/models/default` sets both defaults, a real chat and a real stream raise `used_tokens` and match `last_usage`, a real embedding batch matches the recorded dimension, a bad key is refused without ending the session, and no response or log contains the key. RUN: `test_response_leaks` and `test_provider_flow` pass. RUN: DB holds only sealed `v1:` envelopes. CODE: `common/security/secretbox.py` is AES-256-GCM with tenant, provider and instance bound as AAD. The settings page itself is covered by jsdom plus live API-client tests, not a real browser (human item 3). |
| 2 | Create dataset from the gallery; duplicate name and unavailable embedding model rejected; real ES index with `q_{dim}_vec` matching the model dimension and HNSW/cosine; list, view, update, delete; a second member sees it | VERIFIED | RUN: `test_live_models` asserts the field is `dense_vector` with the live model's dimension, `cosine`, `hnsw` m=16 ef_construction=200. RUN: `test_create_kb_e2e` (E2E-03) checks the same on `q_1024_vec` and that no other dimension is mapped. RUN: `test_dataset_flow` covers duplicate name (including two concurrent creates giving one dataset and one conflict), a foreign embedding model, and distinguishable reasons. RUN: `test_dataset_lifecycle` covers update to a new dimension, refused changes provisioning nothing, and delete removing the index data. RUN: team-permission visibility tested. Note: the default permission is `me` (D-08, D-27), so a second member sees a dataset only once it is shared with `team`. This follows the locked decisions. |
| 3 | Drag and drop one or more files; blob in MinIO under a generated key; document listed as not started at 0 progress; same content twice reuses the blob | VERIFIED | RUN: `test_upload_flow` checks generated keys `{tenant_id}/{uuid hex}`, the MinIO listing, `run=0` and `progress=0`, and identical content sharing one blob; parallel uploads of one name give `x.pdf` and `x(1).pdf` (D-14). RUN: real Chrome `test_dropping_a_file_on_the_dataset_page...` and the real file input journey pass (E2E-04). CODE: xxh64 plus size is a hint only, then a byte-for-byte compare (`file_service.py`, R-143). |
| 4 | Upload rejects a disallowed extension (400), an oversized file, a traversal filename, and an inaccessible dataset; nothing stored | VERIFIED | RUN: `BAD_UPLOADS` cases (exe, gif per D-28, double extension, wrong magic, NUL in text, `../` and `..\` traversal, empty file) each give 400 with a reason and an unchanged MinIO listing and row count. RUN: one byte over 100 MiB gives 413 `file_too_large`, exactly 100 MiB is accepted, a 102 MiB body is refused by Nginx before Python. RUN: a foreign, private or unknown dataset gives the one 404 and stores nothing. The criterion names no status for oversized; 413 is the correct code. |
| 5 | Deleting a document removes its rows; blob is collected only when no other document references it | VERIFIED | RUN: `test_a_delete_answers_the_count_and_a_shared_blob_is_removed_only_with_its_last_document` and `test_a_blob_shared_across_two_datasets_survives_the_first_delete` pass. RUN: integration `test_document_service` and the real-Chrome delete test (blob and index data gone) pass. |

## Locked decisions D-01 to D-29

Honored, checked against the code and tests I ran: OpenRouter on one key (D-01, D-25), live tier fails rather than skips without a key (D-04, guard test in the gate log), save tests the key first (D-16), keys never readable back (D-17), owner/admin only provider routes (D-07), default permission `me` and strict privacy with no admin override (D-08, D-27), 100 MiB limit enforced at Nginx and server (D-11), rename on duplicate name (D-14), images limited to jpg, jpeg, png (D-28), explicit default models (D-18), Python owns the routes (D-19), cross-tenant 404 (D-20), `litellm==1.103.2` (D-24, R-138), debt-marker scan clean. The Ollama driver exists and is contract-tested only, as D-03 allows (`embedding_model.OllamaEmbed`, no live Ollama proof).

## Requirement coverage

All 65 requirement IDs in the phase scope appear in the frontmatter of at least one of the 31 plans (computed by script: 0 missing, 0 extra). `REQUIREMENTS.md` marks all 65 `[x]` and `Complete` in the traceability table. Orphaned requirements: none.

| Group | IDs | Status | Main evidence |
|---|---|---|---|
| LLM drivers | LLM-01..05 | SATISFIED | `rag/llm/chat_model.py` (LiteLLM base), `embedding_model.py` (OpenAI, Azure, Ollama); unit and integration tests; live OpenRouter |
| LLM runtime | LLM-14..22 | SATISFIED | `llm_service.py` bundle, `retry.py`, `stream.py`, `model_meta.py`, `ALLOWED_GEN_CONF_KEYS`; `test_llm_bundle_flow`; live usage assertions |
| LLM routes and entities | LLM-23..29 | SATISFIED | `provider_api.py`, `models_api.py`, five tenant model entities in `api/db/models/llm.py`; provider and models flow tests |
| Knowledge base | KB-01..09 | SATISFIED | `dataset_api.py`, `knowledgebase_service.py`; dataset flow, lifecycle and E2E-03 |
| Tenancy | TEN-12, 13, 16 | SATISFIED | defaults, shared datasets, `permission` on create; isolation and matrix tests |
| Storage | STOR-01, 02, 06, 08, 10, 11 | SATISFIED | `storage_factory.py`, `minio_conn.py` (bucket on first write, presign), `local_conn.py` traversal guard; `test_storage.py` |
| Documents | DOC-01..08, 14..16 | SATISFIED | `document_api.py`, `document_service.py`, `file_service.py`, `upload_rules.py`; upload and document flow tests |
| Index | IDX-04..06, 08, 09 | SATISFIED | `es_mapping.py`, `es_conn.py`, `doc_store_base.py`; `test_doc_store_es.py` against real ES |
| UI | UI-10..12, 37 | SATISFIED, with limits | web unit (1135) and live (46) tests; real Chrome for the datasets and upload journeys. Settings page is not in real Chrome (human item 3) |
| Security | SEC-02, 03, 06 | SATISFIED | leak sweep, sealed envelopes, upload rules; see the BE-03 follow-up below |
| Tests | TEST-08, E2E-03, E2E-04 | SATISFIED | ES contract suite, `test_create_kb_e2e`, `test_upload_flow`, no mocks of own services (a fake provider is used in the non-live tiers and the real provider in `live_model`) |

LLM-15 and STOR-01 carry "Python implementation in v1; Go mirror deferred to v2" in `REQUIREMENTS.md`; that is the stated scope, not a gap.

## Anti-patterns

No `TBD`, `FIXME` or `XXX` in `api`, `rag`, `common`, `web/src`, `internal` or `cmd`. The CI placeholder gate passes. `git status` is clean.

## Code-review warnings (13): none breaks a criterion

None is a gap. They are follow-ups for a hardening plan or `/gsd-code-review 3 --fix`.

| Id | Weighed against the phase | Disposition |
|---|---|---|
| BE-03 | A provider that echoes a non-`sk-` shaped key can leave a key prefix in a 400 body when the key straddles character 200 (reproduced by the reviewer, not by me). OpenRouter keys are `sk-` shaped and masked, and the live leak test passes, so SEC-02 and criterion 1 hold for the proven provider. It is a real residual edge for other providers. | Follow-up, fix first |
| BE-01, BE-02 | Provider test deadline and response size cap; availability and memory hardening | Follow-up |
| BE-04 | Nginx catch-all 1 GiB body and 3600 s timeouts before auth; the upload route itself is limited to 101m | Follow-up |
| BE-05 | Master-key rotation unsupported although `.env.example` implies it; not a Phase 3 requirement | Follow-up, fix the docs or add the keyring |
| BE-06, BE-09 | Search query escaping and parser_config range checks; no consumer until Phases 4 and 5 | Deferred to Phases 4 and 5 |
| BE-07, BE-08 | Blocking calls on the event loop; log redactor skips non-string extras | Follow-up |
| FE-01..04 | Focus loss on pagination, workspace resolution flicker, stale cache after a timed-out success, stale dialog error | Follow-up |

## Open items not verified

- **NOT:** headed-browser behaviour (B-31) and visual or accessibility review: see the human items.
- **NOT:** a live proof for Azure, Ollama and the generic OpenAI-compatible entry. D-15 and D-03 allow contract tests only; only OpenRouter was run live.
- **NOT:** the Go tiers (`go vet`, Go tests) and `scripts/clean_room.sh` were not re-run by me; they rest on the gate record (3 clean runs, attempt 4, after three recorded restarts caused by a Go matrix scope fix, a transient provider timeout, and a test defect fixed in the test).
- Host overrides from B-33 (`vm.max_map_count`, `PREFLIGHT_PORTS=`, `LIVE_BASE_URL`) are still needed on this machine; B-32 (forgot-password test timing under load) is a Phase 2 test and I used `--maxWorkers=4`.

## Gaps summary

No gaps. Every success criterion was exercised by tests I ran against the live stack, including one real OpenRouter run. Status is `human_needed` only because four items (B-31 browser behaviour, visual pass, Chinese text) cannot be checked by a tool.

---

_Verified: 2026-10-10_
_Verifier: Claude (gsd-verifier)_
