---
phase: 04-ingestion-pipeline
verified: 2026-10-19
status: human_needed
score: 5/5 success criteria verified; 60/60 requirement IDs claimed by a plan (56 satisfied, 4 partial by design under D-27); 0 gaps
overrides_applied: 0
gaps: []
deferred:
  - item: "Three consecutive clean-room runs (scripts/clean_room.sh --runs 3), plan 04-35 task 3, B-36"
    decided_by: "user, 2026-10-19 ('stop that check, make a doc so we can check later, and finish phase 4')"
    record: "04-DEFERRED-CLEAN-ROOM.md, 04-35-GATE-LOG.md, .planning/BLOCKERS.md B-36"
    effect: "Final proof for TEST-11, E2E-05, E2E-06. Not passed even once end to end. 04-VALIDATION.md stays status: draft, nyquist_compliant: false."
  - item: "CHUNK-17, PARSE-09, PARSE-11, UI-14 remainder (traditional-to-simplified Chinese, dictionary tokenizer, embedded images in DOCX and PPTX, layout toggle, auto-keyword count)"
    addressed_in: "Phase 6"
    evidence: "ROADMAP.md Phase 6 'Moved from Phase 4 (D-27)' note; REQUIREMENTS.md rows marked Partial"
human_verification:
  - test: "Box alignment on the chunk inspector page image (UI-16, B-35)"
    expected: "On page 1 and page 13 of the 13-page PDF the highlighted rectangle sits on the text of the selected chunk. Neighbouring chunks cut from one text block may show the same rectangle (R-190)."
    why_human: "Real Chrome tests only prove the box is inside the image and the page is right; whether it covers the right text needs an eye on devrag-inspector-box-page1.png and devrag-inspector-box-page13.png"
  - test: "Chinese draft copy review (B-18, B-35)"
    expected: "Every Phase 4 file under web/src/locales/areas/zh/ (chunking, details, editor, failures, inspector, parsing, viewer) reads correctly to a Chinese reader"
    why_human: "Key parity with English is tested; the text itself was written by an agent and never reviewed"
  - test: "Confirm the PDF page cap of 20,000 (B-34, R-189)"
    expected: "User confirms 20,000 pages or names another number; it is the single value ParseLimits.max_pages"
    why_human: "No document under docs/ gives a figure; an agent chose it in plan 04-08"
  - test: "Decide whether finer PDF chunk boxes are wanted (R-190, B-35)"
    expected: "Accept that chunks cut from one PDF text block share the block's rectangle, or ask for line-level boxes"
    why_human: "Product decision about a known limitation, not a defect against any stated criterion"
  - test: "Run the deferred clean-room gate (B-36)"
    expected: "scripts/clean_room.sh --runs 3 ends with 'clean-room: 3 run(s) passed'; then approve 04-VALIDATION.md and close B-36"
    why_human: "User deferred it; it stops and rebuilds the stack, costs real OpenRouter calls, and I was told not to run it"
---

# Phase 4: Ingestion Pipeline Verification Report

**Phase goal:** A user can start parsing an uploaded document and watch it become searchable chunks, produced by a background worker that survives crashes, retries and cancellation.
**Verified:** 2026-10-19
**Status:** human_needed. Every success criterion and every requirement holds against the running stack and the code. Nothing is a gap. Status is not `passed` because the user deferred the three-run clean-room exit gate and four human checks are open.
**Re-verification:** No, initial verification.

Evidence types used below: **RUN** = I ran it in this session; **GATE** = taken from the committed gate records (`04-35-GATE-LOG.md`, `04-DEFERRED-CLEAN-ROOM.md`, plan summaries); **CODE** = read in the source; **NOT** = not verified.

## Test runs in this session (stack healthy, web on 8088)

| Command | Result |
|---|---|
| `uv run python run_tests.py -m unit` | 2055 passed, 4 skipped, 0 failed (RUN) |
| `uv run python scripts/ci/run_all.py` | 7/7 gates passed (RUN) |
| `PHASE4_GATE=1 uv run python -m pytest test/unit_test/test_phase4_traceability.py -q` | 6 passed (RUN) |
| `cd web && npx vitest run --project unit` | 82 files, 1703 tests passed (RUN) |
| e2e: `test_parse_flow`, `test_parse_formats`, `test_parse_pdf`, `test_chunk_flow`, `test_delete_chunks_flow` | 54 passed (RUN) |
| e2e: `test_ingestion_api`, `test_document_switch_flow`, `test_document_detail_flow`, `test_ingestion_failure` (serial: kill, poison, cancel, re-parse on the real executor container) | 38 passed (RUN) |
| e2e: `test_ingestion_scaling` (two executors, graceful stop), `test_spa_ingestion_browser` (real headless Chrome) | 8 passed (RUN) |
| integration: `test_executor_loop`, `test_task_lock_reclaim`, `test_queue`, `test_rollup`, `test_pipeline_failures`, `test_indexing`, `test_totals_service`, `test_task_service`, `test_ingestion_service`, `test_executor_recovery` | 96 passed (RUN) |
| `live_model` tier (real OpenRouter, `baai/bge-m3`) | 17 passed, not re-run by me, cost (GATE: 04-33 summary, `04-DEFERRED-CLEAN-ROOM.md`) |
| Go race, Go integration+e2e, Go manual and cgo, vitest live (57), Python integration (643), e2e (662), e2e-serial (13) | passed once each against the stack, outside the clean room (GATE: `04-DEFERRED-CLEAN-ROOM.md`; not re-run by me) |
| `scripts/clean_room.sh --runs 3` | NOT run, deferred by the user (see "Deferred items") |

The serial failure and scaling tests recreate only the `task-executor` service and restore the single default executor in teardown. After them one executor was running and healthy (`docker ps`, RUN); the app, MySQL, MinIO, Elasticsearch and Valkey containers were not touched.

## Success criteria

| # | Criterion | Verdict | Evidence |
|---|---|---|---|
| 1 | Parse a text-layer PDF longer than 12 pages; status moves not-started to running with live progress to finished; split into page-range tasks; chunks embedded with the dataset's real embedding model and present in Elasticsearch; dataset chunk and token totals updated | VERIFIED | RUN: `test_parse_pdf` (13-page PDF: two task rows `(0,12)` and `(12,13)`, chunks on all 13 pages, ids, counts equal the index, totals set to truth) and `test_parse_flow` pass. CODE: `task_service.split_pages` cuts by `ingest.task_page_size` = 12 (`common/settings.py`, `service_conf.yaml.template`); `rag/svr/pipeline.py` fetches, parses, chunks, embeds in batches of 64 (provider calls of 16, R-165), L2-normalises (`chunk_doc.l2_normalize`) and bulk inserts; progress is written per batch (`set_progress`) and rolled up by the daemon (`progress.py`). GATE: `test_live_ingestion` (04-33, 11 tests, real OpenRouter) shows 1024-number unit-length vectors, nearest-chunk placement of a page-7 sentence, `used_tokens` recorded, dataset `chunk_num` equal to the per-document sum, 0 key leaks. Real Chrome `test_spa_ingestion_browser` drives the Parse click through to Finished (RUN). |
| 2 | Chunk inspector shows chunks beside the original document with bounding box on the correct page; edit text, add a manual chunk, disable a chunk, each reflected in the index | VERIFIED, box accuracy needs an eye | RUN: `test_chunk_flow` (list with positions, add, edit, switch, embed-before-write refusal, re-parse keeps counts), `test_document_switch_flow`, `test_document_detail_flow` pass; real Chrome inspector journeys pass, with the box asserted inside the page image and the page correct on pages 1 and 13. CODE: `web/src/pages/chunk/` (inspector, editor, list, edit guard), `page_service.ZOOM = 3.0` page images, `build_row` stores `position_int` and `page_dims_flt`, hand-added ids `{doc_id}_m_{uuid}` (R-155). GATE: live edit changes the vector (cosine < 0.999999) and an added chunk is found by dense search. The coarse-box limit R-190 and the by-eye alignment check are human items 1 and 4. |
| 3 | DOCX, XLSX, PPTX, HTML, TXT parse to chunks with `naive` using the dataset's token size and delimiter; an unimplemented chunker is rejected explicitly, never a silent fallback | VERIFIED | RUN: `test_parse_formats` passes (all five formats plus Markdown, CSV, JSON as text, D-13). CODE: `rag/parsers/router.py` maps the suffixes; `pipeline._naive_config` reads `chunk_token_num`, `delimiter`, `overlapped_percent` from `parser_config`; `rag/chunking/factory.get_chunker` raises `ChunkerUnavailable` for every method but `naive` (reason `chunker_unavailable`, terminal, listed in `common/ingest_codes.py`); the dialog lists all eight methods with seven disabled (`web/src/components/chunk-method-dialog/`, vitest). GATE: live run parsed all six file kinds with the real model. |
| 4 | Killing the worker mid-task: reclaimed and completed with no duplicate chunks; poison file fails terminally after the retry cap with its error visible in the UI; re-parse leaves an identical chunk count; cancelling stops the worker and marks the document cancelled | VERIFIED | RUN, on the real executor container: `test_kill_mid_task_is_reclaimed_and_completes_with_exact_chunks` (40-chunk file, D-30), `test_poison_a_truncated_docx_fails_after_three_attempts_with_a_plain_reason`, `test_cancel_keeps_the_indexed_chunks_stops_within_five_seconds_and_parse_again_finishes`, `test_reparse_leaves_the_same_count_and_ids_also_after_a_cancel_and_after_a_failed_run` all pass; `test_parse_flow` and `test_parse_pdf` repeat re-parse with same count and same ids; Chrome `test_cancelling_a_running_parse_...` passes. RUN integration: `test_task_lock_reclaim` (expired owner reclaimed, completed once), `test_queue` (reclaim then late ack), `test_executor_loop` (cancel stops the task within 3 s), `test_pipeline_failures` (cancel inside an embedding call noticed within 1.5 s). CODE: parsed ids are deterministic `{doc_id}_{from_page*1000+i}` so a reclaimed task rewrites the same ids and the pipeline deletes the task's earlier rows first (`pipeline.run_pipeline`); `claim_attempt` caps attempts at `ingest.max_attempts` = 3 and a crashed task that used every attempt fails `worker_lost` (`executor_loop._locked`); owner-token lock with compare-and-delete release (`task_lock.py`). Failure text shown is a fixed plain message from `PLAIN_MESSAGES`; the failure test asserts no traceback, path, host or key shape in any response or progress line. |
| 5 | Executor runs as its own container, a second executor needs no configuration, and deleting a document or dataset removes its chunks | VERIFIED | RUN: `test_ingestion_scaling` (second executor from `--scale task-executor=2` with no other setting; graceful stop) and `test_delete_chunks_flow` (document and dataset delete remove chunks from the index) pass. CODE: `docker/docker-compose.yml` `task-executor` service has its own entrypoint (`entrypoint_task_executor.sh`), healthcheck, no port and no container name, so replicas register unique consumers (`consumer_name()`: `te_<host>_<pid>_<rand>`) in one group. Limit 384m measured in plan 04-35 (R-188, GATE: 201 MiB peak). Integration `test_executor_container` and `test_executor_memory` are in the gate record, not re-run by me. |

## Locked decisions D-01 to D-31

Honored, checked against code, route table and the tests I ran. Selected evidence:

- **D-01, D-02, D-10** parse only on click; permitted users are the uploader, dataset creator, owner and admins (`conf/routes.yaml` note on `documents/parse`; `test_phase3_isolation` guard tests and matrix builders for the Phase 4 rows were extended, `deferred-items.md` RESOLVED).
- **D-03, D-04, D-09** re-parse replaces all chunks and asks for confirmation when chunks exist (`test_chunk_flow::...ask_before_replacing`, `test_ingestion_service::test_failed_or_cancelled_needs_confirmation_only_for_edited_or_manual_chunks`, `reparse-dialog.test.tsx`).
- **D-05, D-25** three attempts, terminal failures not retried (`failure.py`, poison test).
- **D-06, D-07** a cancelled or failed document keeps its chunks, shown as "Partly indexed" (`_current_switch` raises `TaskCancelled` and keeps chunks; `test_ingestion_read`, `test_document_view`).
- **D-08, D-23** plain reasons, no trace, path or key (failure e2e leak assertions, live key sweep).
- **D-11** edit or add embeds before writing, refused on failure (`test_chunk_flow`).
- **D-12, D-26** chunk and document switches are separate (`doc_enabled_int` plus `available_int`, R-163; `test_document_switch_flow`).
- **D-13, D-14, D-15** images and untyped files get no Parse button and a refused parse; pages without a text layer are counted, a PDF with none fails at once (`no_readable_text`); the eight-method dialog (parse flow, formats and PDF e2e, vitest).
- **D-18, D-20** Valkey Streams only behind a `TaskQueue` interface; no new Peewee column was added without a record (R-155..R-159).
- **D-21, D-24** only the seven approved Python packages; the source gate `phase4-source-gate.test.ts` and the pin tests pass.
- **D-27** partials delivered in part and handed to Phase 6 (see below).
- **D-28** `charset-normalizer` direct dependency (R-161). **D-29** limit 384m from a measurement (R-188). **D-30** 40-chunk kill test. **D-31** BE-06, BE-08, BE-09, BE-13 taken on (R-166), BE-07 left for Phase 5.

## Partial requirements and the Phase 6 hand-off (D-27)

| ID | Delivered in Phase 4 (CODE) | Handed to Phase 6 | Hand-off recorded |
|---|---|---|---|
| CHUNK-17 | `rag/nlp/tokenizer.py`: NFKC (full-to-half-width), lower case, URL and email stripping, Latin by word, CJK as unigrams and bigrams, token positions; `build_row` stores `content_ltks` and `content_sm_ltks` | traditional-to-simplified conversion, dictionary fine-grained tokenizer | `REQUIREMENTS.md` row `[ ]` with "partly delivered" text and traceability `Partial`; `ROADMAP.md` Phase 6 note; R-160 |
| PARSE-09 | `rag/parsers/docx.py`: body in order, headings marked, tables as escaped HTML; embedded images skipped and counted in `report.images_skipped`, logged as `[skipped] images=N` | embedded image handling | same three places |
| PARSE-11 | `rag/parsers/pptx.py`: slide titles, text frames, shape tables, speaker notes; images skipped and counted | image handling | same three places |
| UI-14 | `ChunkMethodDialog` parser configurator: chunk token size and delimiter (and overlap); the form says layout and keywords are never part of the request | layout-model toggle, auto-keyword count | same three places |

The remainders sit in Phase 6 scope (the note names the four IDs) but are not yet in its **Requirements** line (`PARSE-04..08, PARSE-14..26, CHUNK-03..15, ...`), which lists none of CHUNK-17, PARSE-09, PARSE-11, UI-14. Phase 6 planning must add them or they will fall between phases (WARNING, not a Phase 4 gap).

## Requirement coverage

All 60 requirement IDs of the roadmap line appear in the frontmatter of at least one of the 35 plans (computed by script: 0 missing, 0 extra; the traceability gate test also passes). `REQUIREMENTS.md` marks 56 `[x]` / `Complete` and 4 `[ ]` / `Partial` (CHUNK-17, PARSE-09, PARSE-11, UI-14). Orphaned requirements: none (ING-17..21 are mapped to later phases).

| Group | IDs | Status | Main evidence |
|---|---|---|---|
| Task rows, queue, locks | ING-01..07 | SATISFIED | `task_service.py`, `rag/queue/valkey_streams.py` (`te.{priority}.common`, high stream read first, consumer group, `XAUTOCLAIM`, `XACK`+`XDEL`), `task_lock.py`; `test_queue`, `test_task_lock_reclaim`, kill e2e |
| Progress, limiters, heartbeat | ING-08..10 | SATISFIED | `progress.py` lock-guarded roll-up (`test_rollup`), `limiters.py` five named limiters, `heartbeat.py`. `kg_limiter` is built and tested but no stage takes it, as no knowledge-graph stage exists yet (stated in the module); the requirement text names the limiter, not a consumer |
| Failure, cancel, pipeline | ING-11..16 | SATISFIED | `failure.py`, `executor_loop.py`, `pipeline.py`, `embedding.py` (thread pool plus connection release before inference), executor container and healthcheck; failure, cancel, scaling e2e |
| Parsers | PARSE-01..03, 10, 12, 13 | SATISFIED | `router.py`, `pdf.py` (pypdfium2, boxes, zoom-3 raster via `page_service`, thumbnail), `xlsx.py`, `html.py`, `txt.py`; `test_parse_formats`, `test_parse_pdf` |
| Parsers, partial | PARSE-09, 11 | PARTIAL by D-27 | table above |
| Chunking | CHUNK-01, 02, 16, 18..21 | SATISFIED | `factory.py`, `naive.py` (512 default, delimiters, overlap), `chunk_doc.py`, `chunk_service`; `test_chunk_flow` |
| Chunking, partial | CHUNK-17 | PARTIAL by D-27 | table above |
| Index | IDX-01..03, 07, 14 | SATISFIED | batch 64, truncation at the driver, L2 norm, deterministic ids, delete removes chunks; `test_indexing`, `test_delete_chunks_flow`, live vector-norm test |
| Documents | DOC-09..13, 20..23 | SATISFIED | parse, cancel, re-parse, state and progress, document switch, thumbnails, content and text preview, task status route `GET /v1/task/status/{task_id}`, counters; `test_parse_flow`, `test_document_detail_flow`, `test_ingestion_api` |
| Knowledge base | KB-14..16, 19 | SATISFIED | ingestion summary, logs, log detail, embedding check routes (`conf/routes.yaml`, `implemented: true`); `test_ingestion_api`; totals set to truth by `settle_totals` (`test_totals_service`) |
| UI | UI-13, 15..17, 19 | SATISFIED, box accuracy and Chinese copy open | vitest 1703 passed; real Chrome journeys; human items 1 and 2 |
| UI, partial | UI-14 | PARTIAL by D-27 | table above |
| Deploy, tests | DEPLOY-17, TEST-11, E2E-05, E2E-06 | SATISFIED in their own tiers; final repeat deferred | executor service in compose; DB and pipeline tests; E2E tests above pass without mocking own services (the loopback provider is the third party's end of the embedding wire; the real provider is used in `live_model`). The three-run clean-room repeat stays open (B-36) |

## Anti-patterns

No `TBD`, `FIXME` or `XXX` in `api`, `rag`, `common`, `web/src`, `internal`, `cmd`, `conf`, `docker`, `scripts` or `test` other than the CI scanner's own pattern and its tests. The placeholder and no-sleep gates pass. No `NotImplementedError` placeholder in `rag` or `api` (two uses are exception handlers for the standard library). No skipped or xfailed Phase 4 test in `test/testcases` or `test/integration`.

## Findings against the record (WARNING, none breaks a criterion)

| Item | Detail |
|---|---|
| ROADMAP marks the gate plan done | `.planning/ROADMAP.md` (uncommitted change in the working tree) ticks `[x] 04-35-PLAN.md ... (clean_room x3)` and "Phase 4 ... (completed 2026-10-19)" although the three runs were deferred. The honest record is in `04-DEFERRED-CLEAN-ROOM.md` and B-36; the roadmap tick should be read with them. |
| `04-VALIDATION.md` not approved | `status: draft`, `nyquist_compliant: false`, `wave_0_complete: false` with the "NOT approved" note, which is accurate and must flip only after the gate passes. |
| Phase 6 requirement line | See the hand-off section. |
| Research assumption A2 | pdfium thread safety is unverified; a process-wide `PDFIUM_LOCK` is applied regardless. A4 (embedding cost per gate run) was never priced. |

## Deferred items (user decision, not a hidden pass)

1. **Three clean-room runs (B-36).** Deferred by the user on 2026-10-19. Six attempts so far: refusal by a stray container (resolved with the user's approval), three attempts that found two out-of-date tests and one real bug (roll-up finished a document and closed its log row in two commits, fixed in `2925739` with a regression test), one out-of-date e2e, and one run that passed unit (2055), integration (643), e2e (662) and e2e-serial (13) and failed only at live-model because OpenRouter was unreachable (live tier passed 17/17 minutes later); the last was stopped at the user's request. `clean-room: 3 run(s) passed` does not appear in the log. The `memory` step of the gate (`scripts/record_memory.py --record`) has not run either. I did not run `clean_room.sh`.
2. **Phase 6 remainders of CHUNK-17, PARSE-09, PARSE-11, UI-14** as listed above.

## Open items not verified

- **NOT:** the clean-room gate, its `memory` step, and repeatability of the live tier (OpenRouter reachability).
- **NOT:** the `live_model` tier, Go tiers and vitest live tier were not re-run by me; they rest on the gate record and the 04-33 summary.
- **NOT:** by-eye alignment of boxes, Chinese copy, visual and accessibility quality of the new pages in light and dark theme.
- Host overrides still needed on this machine: `PREFLIGHT_ALLOW_LOW_MAP_COUNT=1` (`vm.max_map_count` 65530) and `LIVE_BASE_URL=http://127.0.0.1:8088`.
- Known flaky item to watch in the gate: `models.live.test.ts` once failed right after heavy provider use and passed alone and on rerun.

## Gaps summary

No gaps. All five success criteria were exercised by tests I ran against the live stack, including the crash, poison, cancel, re-parse and scaling journeys on the real executor container, and the code paths behind them were read. Status is `human_needed` because the user deferred the three-run exit gate and four items need a person (box alignment, Chinese copy, the PDF page cap, the coarse-box decision).

---

_Verified: 2026-10-19_
_Verifier: Claude (gsd-verifier)_
