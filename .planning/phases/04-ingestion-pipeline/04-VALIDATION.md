---
phase: 4
slug: ingestion-pipeline
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-10-10
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: `04-RESEARCH.md`, section "Validation Architecture".

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio (`asyncio_mode=auto`, `-p no:anyio`, `filterwarnings=error`), pytest-timeout; vitest for web; real-Chrome tier for browser journeys |
| **Config file** | `pyproject.toml` (markers `unit`, `integration`, `e2e`, `serial`, `live_model`), `run_tests.py`, the `web/` vitest config, `scripts/clean_room.sh` (gate) |
| **Quick run command** | `uv run python run_tests.py -m unit` |
| **Full suite command** | `scripts/clean_room.sh --runs 3` (phase exit) |
| **Helpers** | `test/helpers/wait.py::wait_until` (instead of sleeps), `test/helpers/uploads.py`, `test/helpers/doc_store_contract.py` |
| **Estimated runtime** | Unit tier about 40 s and one gate run about 760 s at the end of Phase 3. Phase 4 figures are recorded by the planner once Wave 0 lands. |

---

## Sampling Rate

- **After every task commit:** Run `uv run python run_tests.py -m unit` plus the one integration file touched
- **After every plan wave:** Run `uv run python run_tests.py -m integration` and `uv run python scripts/ci/run_all.py`; `cd web && npm run test -- --run` when web files changed
- **Before `/gsd:verify-work`:** `scripts/clean_room.sh --runs 3` green with the provider key present, on web port 8088 with at least 4096 MB of available RAM
- **Max feedback latency:** 120 seconds for the unit tier and 60 seconds per task-level command (the Phase 3 limits), unless the planner measures otherwise

---

## Per-Task Verification Map

Task IDs, plans, waves and threat references are assigned by the planner. Rows are keyed by requirement until then.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | TBD | TBD | ING-01 | — | A 13-page PDF becomes 2 page-range tasks (0..12, 12..13) | unit + integration | `pytest test/unit_test/test_task_split.py -q` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | ING-02, ING-03 | TBD | XADD on `te.{priority}.common`; priority 1 drained first; message integrity checked | integration (real Valkey) | `pytest -m integration test/integration/test_queue.py -q` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | ING-04..07 | TBD | Two consumers, no double delivery; reclaim of un-acked messages; lock with owner token and compare-and-delete release; ack on completion | integration | `pytest -m integration test/integration/test_task_lock_reclaim.py -q` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | ING-08, ING-10 | — | Task progress rolled up to the document; worker heartbeat | integration | `pytest -m integration test/integration/test_rollup.py -q` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | ING-11, ING-12 | TBD | Retry cap 3, terminal failure with a plain reason and no internals; cancel noticed promptly; partial chunks kept (D-06) | e2e serial | `pytest -m "e2e and serial" test/testcases/test_ingestion_failure.py -q` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | ING-13..16, DEPLOY-17 | TBD | Pipeline end to end in a separate executor container; a second executor needs no configuration | e2e + live_model + compose | `pytest -m live_model test/testcases/test_live_ingestion.py -q` ; `scripts/wait_stack.sh` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | PARSE-01..03 | TBD | Router by file type; PDF text with character boxes; zoom-3 raster; pages without text skipped and counted (D-14) | unit | `pytest test/unit_test/test_pdf_parser.py -q` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | PARSE-09..13 | TBD | DOCX, XLSX, PPTX, HTML, TXT (and Markdown, CSV, JSON as text, D-13) yield expected text; archive bombs and XXE refused | unit (generated files) | `pytest test/unit_test/test_parsers.py -q` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | CHUNK-01, CHUNK-02 | — | Factory refuses unimplemented chunkers explicitly (D-15); `naive` honours token size and delimiter | unit | `pytest test/unit_test/test_naive_chunker.py -q` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | CHUNK-16..21 | TBD | Chunk fields; list, create, edit, switch on/off reflected in the index; an edit whose embedding fails is refused (D-11); permissions per D-10 | integration (real ES) | `pytest -m integration test/integration/test_chunk_service.py -q` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | IDX-01..03, IDX-07 | — | Batching, L2 norm 1.0 within 1e-6, deterministic ids, identical count on re-parse | integration | `pytest -m integration test/integration/test_indexing.py -q` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | IDX-14, DOC-09..13 | TBD | Parse, cancel, re-parse with confirmation data; document on/off; delete removes chunks; permissions per D-02 | e2e | `pytest -m e2e test/testcases/test_parse_flow.py -q` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | DOC-20..23, KB-14..16, KB-19 | TBD | Thumbnail, preview, task status, ingestion summary and logs, embedding check, totals equal to the index | e2e | `pytest -m e2e test/testcases/test_ingestion_api.py -q` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | D-19 (isolation) | TBD | Cross-tenant matrix builders and leak-sweep exercisers for every new tenant-scoped route; private datasets hidden; API tokens not elevated | e2e | `pytest -m e2e test/testcases/test_cross_tenant_matrix.py test/testcases/test_response_leaks.py -q` | extend existing | ⬜ pending |
| TBD | TBD | TBD | UI-13..17, UI-19 | — | Chunking-method dialog (seven unavailable), configurator, live progress, error details, inspector boxes, chunk editor, document viewer; en/zh key parity | vitest + real Chrome | `cd web && npm run test -- --run` ; `pytest -m e2e test/testcases/test_spa_browser.py -q` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | E2E-05, E2E-06, TEST-11 | — | Document-processing and indexing flows against the real stack and provider, no mocks | e2e + live_model | as above | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Crash, Reclaim, Poison and Cancel

No fixed sleeps and no mocks of own services; `wait_until` on real observables.

- **Kill mid-task:** a test-tier compose override sets a small ingest batch size and short lock and reclaim times. The test uploads a text file of about 40 chunks, starts a parse, waits until the first batch is in Elasticsearch and the task is unfinished, then kills the executor container. Another executor reclaims the task. The test asserts the document finishes, the chunk count equals the expected count, and the id set equals the task manifest.
- **Poison file:** a truncated `.docx`. The test asserts the retry count reaches the cap, the document is failed with a plain reason and no path or traceback text, and no provider call was made.
- **Cancel:** same observable, then cancel. The test asserts the document becomes cancelled, the chunks already indexed are kept (D-06), the totals equal the index count, and no new chunks appear.
- **Re-parse:** parse, record the count, parse again and compare; also after a cancel and after a failed run.

---

## Wave 0 Requirements

- [ ] Every test file listed above (none exists yet)
- [ ] `test/helpers/ingest.py` — generated 13-page text PDF, small DOCX, XLSX, PPTX and HTML files, and poison files, built without adding a test-only package
- [ ] Doc-store contract cases for the new count-and-sum method
- [ ] Compose test override for the executor (batch size, lock and reclaim times)
- [ ] Web test fixtures for the chunk inspector
- [ ] Package approval (D-21) recorded before any `uv add`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Bounding boxes sit on the right text in the chunk inspector | UI-16 | Visual alignment of a highlight over a rendered page is judged by eye; automated tests assert coordinates, not appearance | Parse the 13-page test PDF, open the inspector, select chunks on the first and last pages, confirm each highlight covers its text |

All other phase behaviors have automated verification.

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency recorded and within the limit
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
