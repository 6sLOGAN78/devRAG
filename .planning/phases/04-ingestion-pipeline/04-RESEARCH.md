# Phase 4: Ingestion Pipeline - Research

**Researched:** 2026-10-10
**Domain:** Redis-Streams task executor, page-range task splitting, text-layer PDF and Office/HTML/TXT parsing, `naive` chunking, embedding, Elasticsearch bulk indexing, crash/cancel/retry semantics, chunk inspector UI
**Confidence:** MEDIUM-HIGH (queue, lock and PDF behaviour spiked on real Valkey 8.1.10 and pypdfium2 5.14.0; Elasticsearch behaviours of new fields and the cost figure are not spiked, see Assumptions)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Parsing starts only when someone presses Parse, for one document or for several selected documents. Nothing is parsed automatically after upload; documents wait at "Not started".
- **D-02:** In a dataset shared with the team, a document may be parsed, cancelled and re-parsed by its uploader, the dataset's creator, and the workspace owner and admins. Other members see status and progress but no parse controls. Same rule as removing documents in Phase 3 (Phase 3 D-09), and an API token is judged as its user, never elevated.
- **D-03:** Re-parsing rebuilds the document from the stored file and replaces all of its chunks, including chunks that were edited or added by hand. Hand-made changes do not survive a re-parse.
- **D-04:** Re-parsing a document that already has chunks always asks for confirmation. The dialog names the document, states its chunk count, says the chunks will be replaced, and states how many edited and hand-added chunks will be lost.
- **D-05:** A task is attempted 3 times in total (one try plus two automatic retries), then the document is marked failed. The cap is a configuration value. Failures that can never succeed (for example a PDF with no readable text, D-14) fail at once and are not retried.
- **D-06:** When a parse is cancelled or fails part-way, the chunks already indexed for that document are kept and remain searchable. They are not removed and the totals are not rolled back.
- **D-07:** A failed or cancelled document that still has chunks is shown as "Partly indexed" with its chunk count. (A document can therefore be in a failed or cancelled state and still contribute to search.)
- **D-08:** A failed document shows a Failed badge with a short plain reason, and a details panel with the step that failed and the progress log. Stack traces, provider keys and internal paths never reach the UI or an API response; they stay in server logs, under the Phase 3 redaction rules.
- **D-09:** A failed or cancelled document offers "Parse again". It starts at once without a confirmation, unless the document's remaining chunks include edited or hand-added ones; in that case the D-04 warning appears first. Parse again replaces the partial chunks (D-03).
- **D-10:** Editing a chunk's text, adding a chunk by hand, and switching a chunk or a whole document on or off for search are allowed to the same people as parsing (D-02). Other members can read the chunks in the inspector and see no edit controls.
- **D-11:** Editing or adding a chunk needs a new embedding. If the embedding call fails, the save is refused with the reason, and the previous text and vector stay in place. The index never holds text that does not match its vector, and there is no "pending" chunk state.
- **D-12:** A chunk that is switched off stays in the inspector list in its place, visibly dimmed with an "Off" badge, and can be switched back on. A filter shows all chunks, only those on, or only those off.
- **D-13:** Markdown, CSV and JSON files are parsed as plain text with the TXT parser. Images and every other uploaded type without a parser show "Parsing not available yet" with no Parse button, and the API refuses a parse request for them with a clear reason.
- **D-14:** For a PDF, pages with a text layer are parsed and pages without one are skipped and counted in the log. If no page has text, the document fails at once with "This PDF has no readable text; scanned documents are not supported yet" and is not retried (D-05).
- **D-15:** The chunking-method dialog lists all eight methods (General, Q&A, Paper, Book, Laws, Presentation, Table, Manual). The seven not built in this phase are shown as unavailable with "Available in a later release" and cannot be chosen. The API also refuses an unimplemented chunker explicitly; nothing falls back silently.
- **D-16:** Live test documents are tiny and purpose-built: one generated text-layer PDF of 13 or more pages with a few lines per page, and one small file per other format. Each gate run embeds roughly a few dozen chunks on the user's OpenRouter key. No large real-world document is added to the live tiers in this phase.
- **D-17:** One engine (Elasticsearch 8.11.3, one index per tenant, R-136), one embedding provider path proven live (OpenRouter with `baai/bge-m3`, 1024 dimensions), one chunker (`naive`), text-layer PDFs only. One `ParsedBlock` type and one `Chunk` type are defined before a second parser is written.
- **D-18:** Redis Streams on Valkey is the only queue (`te.{priority}.common`, consumer group, XACK); the queue sits behind an interface and NATS is not built. Python owns the worker, the task executor and every route in this phase; Go owns identity only.
- **D-19:** Route, permission and isolation rules from Phases 2 and 3 apply unchanged: one envelope `{code, message, data}` with machine reasons in `data.reason`; every route declared in `conf/routes.yaml`; default-deny gates; permission decisions through the generated permission table; another tenant's or an invisible resource is the one 404; a private (`me`) dataset is hidden from everyone but its creator; every new tenant-scoped route gets a cross-tenant matrix builder and a leak-sweep exerciser.
- **D-20:** Peewee owns the schema and Go only verifies. The `task` table already exists; a schema change needs a recorded decision and a migration, not an ad-hoc column.
- **D-21:** No new package, service or image without asking the user. Hand-written shadcn-style components; English and draft Chinese copy with identical key sets; document-related locale keys avoid the `documents.` prefix (R-151).
- **D-22:** Test discipline: test-first; live tiers against the real stack and the real provider with the key in the git-ignored `docker/.env`; no mocks of own services; no fixed sleeps; nothing weakened, skipped or marked flaky. Phase exit is `scripts/clean_room.sh --runs 3` on web port 8088 with at least 4096 MB of available RAM. The dev app container has a 768 MB limit.
- **D-23:** No secret in logs or responses: the existing redaction rules cover the worker's logs, task progress messages and error details as well.

### Claude's Discretion
- Chunk ID construction (R-11): settle the exact scheme within the documented `doc_id + "_" + order`; hand-added chunks need ids that cannot collide with parsed ones.
- The Redis lock design (R-12): owner token, compare-and-delete release, TTL renewal while a task runs.
- How live the progress display is (refresh interval or push), within `docs/02-frontend/` and the documented `update_progress` roll-up.
- How edited and hand-added chunks are recorded so D-04 and D-09 can count them.
- What document preview and thumbnails cover in this phase (DOC-20, DOC-21, UI-19).
- Worker settings: concurrency limiters, heartbeat timeout, batch sizes, executor memory limit and compose wiring.
- Layout of the parse controls, progress display, error details panel, chunk inspector and chunk editor (UI design contract).
- Which Phase 3 review findings in code this phase touches are fixed here (BE-09, BE-07, ...); record any that are taken on.

### Deferred Ideas (OUT OF SCOPE)
- Parse-on-upload as a per-dataset setting.
- OCR for scanned PDFs, layout analysis, table structure recognition, proper Markdown and table handling, and the other seven chunkers (Phase 6).
- A "pending" state for chunks whose embedding failed.
- A realistic 50-page live test document.
- Fixing the remaining Phase 3 code-review warnings this phase does not touch.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ING-01..03 | task rows, 12-page split, XADD on `te.{p}.common`, high priority drained first | Sections "Task splitting", "Queue and reclaim"; `XREADGROUP` over `[te.1.common, te.0.common]` in that order |
| ING-04..07 | consumer group, reclaim, lock, XACK | "Queue and reclaim", "R-12 lock" (spiked on Valkey 8.1.10) |
| ING-08..10 | progress, `update_progress` daemon, limiters, heartbeat | "Roll-up daemon", "Worker process" |
| ING-11..12 | failure record, retry_count, cancel | "Retry and failure classification", "Cancellation" |
| ING-13..16 | pipeline, thread offload, DB close before inference, standalone container | "Worker process", "Environment/compose" |
| PARSE-01..03 | router, PDF spans with char boxes, zoom-3 raster | "PDF extraction" (pypdfium2 only, spiked) |
| PARSE-09..13 | DOCX, XLSX, PPTX, HTML, TXT | "Office and text parsers", package table |
| CHUNK-01..02, 16..21 | factory, naive, chunk fields, preprocessing, list/create/edit/disable | "Chunker", "Tokenizer", "Chunk document", "Chunk editing" |
| IDX-01..03, 07, 14 | batches, truncation, L2, bulk upsert with deterministic id, delete cleanup | "Embedding in the worker", "R-11 chunk ids" |
| DOC-09..13, 20..23 | parse/cancel/re-parse, state, batch status, thumbnail, preview, task status, counters | "API surface", "Counters" |
| KB-14..16, 19 | ingestion summary, logs, embedding check, totals | "API surface", "Counters" |
| UI-13..17, 19 | chunk-method dialog, configurator, progress, inspector, editor, viewer | "Frontend" |
| DEPLOY-17 | standalone executor container | "Environment/compose" |
| TEST-11, E2E-05..06 | DB + pipeline tests, flows | "Validation Architecture" |
</phase_requirements>

## Summary

The phase can be built without a schema change, without new services and with a short list of new Python packages. The existing `task`, `document` and `pipeline_operation_log` tables are enough: "Partly indexed" is derived (`run` in cancelled/failed and `chunk_num > 0`), the structured failure (step, code, plain reason) lives in the `pipeline_operation_log.dsl` JSON of the parse run, and every counter is set to the truth in the index rather than incremented, which makes crash, retry and reclaim exactly-once by construction. Two small additions outside the schema are recommended and need decision rows: a `stats` read method on the doc-store port (count and sum of a numeric field, needed for the counters) and four chunk fields (`order_int`, `task_id`, `origin_kwd`, `token_num_int`).

Chunk ids stay in the documented shape `doc_id + "_" + order`. The order is made deterministic and independent of other tasks by `order = from_page * 1000 + index_in_task`, so a retried or reclaimed task rewrites exactly the same ids, and any surplus from an earlier, different attempt is removed by a delete on `(doc_id, task_id)` before the task's first insert. Hand-added chunks use `doc_id + "_m_" + uuid4hex`, a different grammar, so they can never collide. "Parse again" deletes every chunk of the document first (D-03), then creates new task rows; D-06 holds because nothing deletes chunks on cancel or failure.

The lock (R-12) is `valkey.lock.Lock` (already in the pinned client, owner token, Lua compare-and-delete release, `reacquire`) renewed by a heartbeat thread; reclaim is `XAUTOCLAIM` by any live executor followed by a lock attempt, so a task still renewed by a live owner is never double-processed. All of this was spiked on `valkey/valkey:8` (server 8.1.10) with valkey-py 6.1.1.

**Primary recommendation:** Build the executor as one process per container with a unique consumer name, a lock-renewal-and-cancel-watch thread per running task, set-to-truth counters under a document row lock, `pypdfium2` (not pdfplumber) for the PDF, an in-repo stdlib tokenizer (not `infinity-sdk`), and server-rasterised page images with CSS-positioned boxes in the inspector (no `react-pdf-highlighter`, no new npm package).

## Project Constraints (from CLAUDE.md)

- `docs/` wins over `spec.md`, existing code, RAGFlow and judgment; any decision not in `docs/` is recorded (`.planning/DECISIONS.md`).
- No new service, database, queue, framework or abstraction layer without checking against `docs/`.
- No critical placeholders; every feature verified by realistic execution; backend production-grade: typed interfaces, config/env, validation, structured errors and logging, migrations, transactions, async processing, retries, timeouts, idempotency, health checks; no giant files.
- Tests: each phase ends with passing tests; Python stack pinned (Quart, Peewee, valkey, elasticsearch 8.x, litellm 1.103.2); FastAPI/SQLAlchemy/Celery/LangChain, PyMuPDF (AGPL) and `antd` are forbidden; use fetch + eventsource-parser for streaming (not needed here).
- `ruff` line-length 200; `asyncio_mode=auto`; pytest `-p no:anyio`.
- CLAUDE.md lists `react-pdf-highlighter`, `chardet`, `pdfplumber`, `readability-lxml`, `html-text`, `nltk`, `infinity-sdk` as ref-baseline candidates; this research recommends against several (see Package table). CLAUDE.md states they are "start here" baselines and D-21 requires approval for each anyway.
- All edits go through a GSD workflow (this research is part of `/gsd:plan-phase`).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Parse/cancel/re-parse request, task row creation, page counting | API (Python Quart) | DB, Valkey | Authorisation and the confirmation rule live with the route; tasks are created in one transaction then enqueued |
| Parsing, chunking, embedding, indexing | Task executor (Python, own container) | Storage, Doc store, LLM provider | Blocking CPU and network work stays off the API process (ING-14/16) |
| Progress roll-up, document state transitions | Task executor (lock-guarded daemon) | DB | ING-08: "lock-guarded `update_progress` daemon"; one writer cluster-wide |
| Chunk list/create/edit/enable | API | Doc store, LLM provider | Synchronous user actions; embedding failure must refuse the save (D-11) |
| Page image, thumbnail, raw preview | API (bounded executor) | Storage | On-demand render of one page; keeps worker free |
| Progress display, chunk inspector, dialogs | Browser (React SPA) | API | Polling via React Query; boxes positioned in CSS over the server image |
| Authorisation of every route | API gate + `tenant_scope` | — | Existing rules (D-19); worker trusts only MySQL, never message content |

## Standard Stack

### Core (already locked, reused)

| Library | Version (uv.lock) | Purpose | Note |
|---------|-------------------|---------|------|
| valkey (py) | 6.1.1 | Streams, `Lock` | `[VERIFIED: spike]` `xadd`, `xreadgroup`, `xautoclaim`, `xpending_range`, `Lock.reacquire` work on server 8.1.10 |
| elasticsearch | 8.19.3 | bulk, update_by_query | existing `ESConnection` |
| peewee / PyMySQL | 3.19 / 1.2.3 | tasks, documents | existing `DB`, `transaction()`, `DatabaseLock` |
| xxhash | 4.0.1 | task digest | already locked |
| tiktoken | 0.14.0 | chunk token counts, truncation | already locked; embedding driver already truncates at 8191 with vendored `cl100k_base` |
| openai / litellm | 2.54.0 / 1.103.2 | embedding via `LLMBundle` | existing |
| charset-normalizer | 3.5.2 (transitive via `requests`) | TXT encoding detection | recommended instead of `chardet`; needs to become a direct dependency (no new package) |

### New packages (single approval table, D-21)

Versions resolved by `uv pip install` into a throwaway venv on 2026-10-10. Licences and ages are from training knowledge `[ASSUMED]`; the planner should confirm them at the approval checkpoint. slopcheck was not run (not installed in this session); every name below comes from `CLAUDE.md` or the reference `pyproject.toml`, so none is a search-discovered name.

| Package | Resolved | Purpose in this phase | Installed size (measured) | Licence `[ASSUMED]` | In reference repo | Needed now? |
|---------|----------|-----------------------|---------------------------|---------------------|-------------------|-------------|
| `pypdfium2` | 5.14.0 | PDF page count, text with char boxes, raster at zoom 3, thumbnail | 0.2 MB + 7.7 MB `pypdfium2_raw` (bundled pdfium) | BSD-3 / Apache-2.0 (+pdfium BSD) | via `pdfplumber`; CLAUDE.md lists it | YES |
| `Pillow` | 12.3.0 | `bitmap.to_pil()`, PNG/JPEG encode, thumbnail | 5.5 MB + 14 MB bundled libs | HPND | yes (`pillow>=12.3.0`) | YES |
| `python-docx` | 1.2.0 | DOCX paragraphs, headings, tables | 1.8 MB | MIT | yes | YES |
| `python-pptx` | 1.0.2 | PPTX slides, shape tables, notes | 1.5 MB (+ `XlsxWriter` 3.2.9, 0.9 MB, hard dependency) | MIT | yes | YES |
| `openpyxl` | 3.1.5 | XLSX sheets (read-only mode) | 1.4 MB (+ `et-xmlfile` 2.0.0) | MIT | yes | YES |
| `lxml` | 6.1.3 | XML/HTML parser used by docx, pptx and bs4 | 12 MB | BSD-3 | yes (`lxml>=6.1.1`, CVE-2026-41066 floor) | YES |
| `beautifulsoup4` | 4.15.0 | HTML text extraction, script/style stripping | 0.4 MB (+ `soupsieve` 2.10) | MIT | yes | YES |

Total new on disk about 45 MB (measured 57 MB RSS after importing all of them). Not recommended now (each would also need approval): `pdfplumber` (+ `pdfminer.six`, `cryptography`; pypdfium2 alone returns spans and char boxes, see Code Examples), `chardet` (charset-normalizer is already locked), `readability-lxml`, `html-text` (BeautifulSoup+lxml covers PARSE-12; both are reference extras), `numpy` (vector math is 1024 floats, `math` is enough), `infinity-sdk` (see Tokenizer), `hanziconv` (traditional-to-simplified table, defer to Phase 6 with the Chinese tokenizer), `defusedxml` (see Security), `react-pdf-highlighter`, `pdfjs-dist`.

**Approval checkpoint wording for the planner:** one `checkpoint:human-verify` listing the seven rows above plus the transitive `XlsxWriter`, `et-xmlfile`, `soupsieve`, and the promotion of `charset-normalizer` to a direct dependency.

**Installation (after approval, by the executor, never by research):**
```bash
uv add pypdfium2 pillow python-docx python-pptx openpyxl lxml beautifulsoup4 charset-normalizer
```

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| pypdfium2 only | pdfplumber + pypdfium2 (CLAUDE.md D6) | pdfplumber gives word/line grouping and tables helpers, costs `pdfminer.six` and `cryptography`; Phase 6 needs it for the ported `pdf_parser`; reintroduce then |
| charset-normalizer | chardet 5.2 (docs say "chardet/utf-8") | docs name chardet as an example; a locked equivalent avoids a new package. Needs user's call (Open Question 2) |
| stdlib tokenizer | `infinity-sdk` 0.7.3 | wheel is 29 MB and drags pandas, pyarrow, polars, numpy<2, sqlglot, thrift, datrie, hanziconv, nltk (measured from PyPI metadata); far too large for a thin phase |
| server-rasterised pages | `react-pdf-highlighter` 6.1.0 + pdf.js | new npm packages, worker config, its own selection layer; useless for scans in Phase 6 |

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| pypdfium2 | PyPI | multi-year `[ASSUMED]` | high `[ASSUMED]` | github.com/pypdfium2-team/pypdfium2 `[ASSUMED]` | not run | Approved pending user checkpoint |
| Pillow, python-docx, python-pptx, openpyxl, lxml, beautifulsoup4 | PyPI | 10+ years `[ASSUMED]` | very high `[ASSUMED]` | well known `[ASSUMED]` | not run | Approved pending user checkpoint |

**Packages removed due to slopcheck [SLOP]:** none (slopcheck unavailable). **Flagged [SUS]:** none known. Because slopcheck did not run, all rows above are `[ASSUMED]` for legitimacy and the planner must keep the `checkpoint:human-verify` gate. Registry check performed: all seven resolve on PyPI at the versions shown (`uv pip install`, 2026-10-10). Postinstall-script check does not apply (Python wheels).

## Architecture Patterns

### System Architecture Diagram

```
Browser (React Query, poll 2 s while any row is running)
   | POST /datasets/{id}/documents/parse {doc_ids, run:"1"|"2"}
   v
API (Quart) --authorise (can_manage rule, D-02)--> MySQL: one transaction
   |   - doc.run=1, progress=0; delete old task rows; INSERT task rows (from_page,to_page,digest)
   |   - INSERT pipeline_operation_log (status running)
   |   (re-parse: first DocStore.delete({"doc_id":[...]}) then reset counters)
   +--XADD {"message": {"task_id","digest"}} --> Valkey stream te.{0|1}.common
                                                      |
                     XREADGROUP (consumer = host-pid-rand), XAUTOCLAIM every 15 s
                                                      v
Task executor container(s) (N, no config) -----------------------------------------
  collect -> lock:task_{id} (valkey Lock, token, TTL 60 s) -> attempt++ (MySQL, atomic)
     |            \__ heartbeat thread: reacquire lock, poll cancel, zadd heartbeat
     v
  load task+doc+kb from MySQL (message is never trusted) -> Storage.iter_chunks -> parse
     -> naive chunk -> [per 64] truncate, embed (LLMBundle, 16 per provider call), L2 -> DocStore.insert
     -> task done in one UPDATE (progress=1, chunk_ids)  -> XACK
     \__ failure: classify -> terminal (progress=-1, ack) | retry (XADD new msg, XACK old)
  update_progress daemon (Valkey lock "update_progress"): task rows -> document.run/progress/msg,
     settle_totals(doc) = DocStore.stats -> document + knowledgebase counters (row lock, set-to-truth)
```

### Recommended Project Structure
```
rag/svr/                 task_executor.py (entry), executor_loop.py, task_lock.py, progress.py, cancel.py
rag/queue/               queue_base.py (interface), valkey_streams.py   # D-18: behind an interface
rag/parsers/             types.py (ParsedBlock), router.py, pdf.py, docx.py, xlsx.py, pptx.py, html.py, txt.py
rag/chunking/            types.py (Chunk), naive.py, factory.py         # FACTORY[parser_id]
rag/nlp/                 tokenizer.py (stdlib), normalize.py
api/db/services/         task_service.py, ingestion_service.py, chunk_service.py, totals_service.py
api/apps/restful_apis/   parse_api.py, chunk_api.py, ingestion_api.py, page_api.py
docker/                  entrypoint_task_executor.sh
```

### Pattern 1: R-11 chunk id and idempotent task rewrite
**What:** `id = f"{doc_id}_{order}"`, `order = task.from_page * 1000 + i` (i = chunk index within the task, `0 <= i < 1000 * (to_page - from_page)`, hard error beyond). For single-task documents `from_page = 0`, so `order = i`. Chunk stores `order_int = order`, `task_id`, `page_num_int`, `origin_kwd = "parsed"`.
**Why it satisfies the obligations:**
- (a) A reclaimed or retried task recomputes the same ids from the same file and config; `insert` is an upsert by `_id`. Before the first insert of an attempt the worker runs `DocStore.delete({"doc_id": [doc], "task_id": [task]})`, which removes any surplus from an earlier attempt whose chunk count differed.
- (b) Parse again: API calls `DocStore.delete({"doc_id": [doc]})` first (removes parsed, edited and manual chunks, D-03), then new task rows are created; each new task writes the same ids as before for an unchanged file and config, so the count is identical.
- (c) Manual chunk id is `f"{doc_id}_m_{uuid4().hex}"`. Parsed ids match `^[0-9a-f]{32}_[0-9]+$`, manual ids `^[0-9a-f]{32}_m_[0-9a-f]{32}$`; the grammars are disjoint. Manual chunks get `order_int = 2_000_000_000` (int32 ceiling is 2147483647, parsed orders stay below 1.0e9 because pages are capped at 1,000,000) and sort by `create_timestamp_flt` as the tie-break.
- (d) D-06: nothing deletes chunks on cancel or failure. A retry/reclaim replaces only that task's chunks (delete by `task_id`), a "Parse again" replaces all.
**Stale worker guard (reference pattern, `insert_chunks` in `rag/svr/task_executor.py`):** after each bulk insert re-read the task row; if it is gone (re-parse or document delete happened meanwhile) delete `{"task_id": [task]}` and stop. This closes the race where a slow old worker writes after the re-parse's delete.
**`task.digest`:** `xxh64(doc_id, from_page, to_page, content_hash, parser_id, chunk_token_num, delimiter, overlap, PIPELINE_VERSION)`; the same value is placed in the queue message. The worker drops (ack) any message whose digest differs from the row's: stale messages from before a re-parse, and message tampering. It is **not** used to reuse previous chunks (the reference reuses finished tasks' chunks on re-parse via `reuse_prev_task_chunks`; that would keep hand edits and contradict D-03, so do not port it).
**`task.chunk_ids`:** space-separated ids, written once, in the same UPDATE that sets `progress = 1` (not cumulatively per batch as the reference does, which is O(n^2) writes). It is the manifest used by tests (index contains exactly these ids) and by the stale-worker guard; correctness never depends on it, because cleanup is by `(doc_id, task_id)`.
**Reference evidence:** the reference uses `xxh64(content + doc_id)` ids (content hash, not order) and `digest` for reuse; the docs scheme (`doc_id + "_" + order`) wins (authority order).

### Pattern 2: R-12 lock plus reclaim without double processing
- Lock: `valkey.lock.Lock(client, f"lock:task_{task_id}", timeout=TASK_LOCK_TTL, thread_local=False)`; `acquire(blocking=False)`. `[VERIFIED: spike]` acquire, `owned()`, `extend`, `reacquire`, token mismatch returns 0 on extend and release.
- Heartbeat thread (one per running task, period = TTL/3): `lock.reacquire()` (resets TTL; raises `LockNotOwnedError` if the token changed, which sets the `lost` event and cancels the task), writes `ZADD <consumer> <now>` heartbeat and `SADD TASKEXE` (ING-10), and polls MySQL `document.run` / task existence once per `CANCEL_POLL_SECONDS` (1 s).
- Defaults (configuration): `TASK_LOCK_TTL_SECONDS=60` (dev compose 15), `WORKER_HEARTBEAT_TIMEOUT=120` (docs value), `RECLAIM_IDLE_MS = 2 x TTL`, `INGEST_MAX_ATTEMPTS=3`.
- Collect order: (1) own pending (`XREADGROUP ... 0`) is not needed because consumer names are unique per process; (2) `XAUTOCLAIM(queue, group, me, min_idle_time=RECLAIM_IDLE_MS, start_id="0-0", count=10)` every 15 s on both queues, high priority first; (3) `XREADGROUP ... ">"` on `te.1.common` then `te.0.common` (ING-03). Every message obtained, claimed or new, goes through the same gate: try the task lock; if held by a live owner, leave the message pending and move on (never ack it).
- `[VERIFIED: spike]` `XAUTOCLAIM` moves ownership, resets idle time and increments `times_delivered`; `XACK` is by id and works from any consumer, so the original owner finishing late still clears the entry. In valkey-py 6.1.1 `xautoclaim(..., justid=True)` returns only the id list (the next-start cursor is dropped); call it without `justid`, which returns `(next_id, messages, deleted_ids)`.
- Dead consumers: after claiming, `XGROUP DELCONSUMER` for consumers whose heartbeat expired and whose pending count is zero (housekeeping, optional).
- Consumer name: `f"te_{hostname}_{pid}_{uuid4().hex[:6]}"`, unique per process, so adding an executor needs no configuration (success criterion 5). This deviates from the docs/reference `task_executor_{TYPE}_{IDX}`, which needs a per-instance index; record it.

### Pattern 3: Attempts, retry and failure classification
- Attempt counter is `task.retry_count`, incremented under the lock by `UPDATE task SET retry_count = retry_count + 1 WHERE id = :id AND progress >= 0 AND progress < 1 AND retry_count < :cap`; rowcount 0 plus `retry_count >= cap` means the task is already exhausted: mark `progress = -1` with message "gave up after 3 attempts", write the log row, XACK. A crash-killed attempt therefore consumes an attempt, which is what bounds a file that kills the process.
- Terminal at once (typed `TerminalTaskError`, no retry): `no_readable_text`, `unsupported_type`, `chunker_unavailable`, `file_too_large`, `archive_limits_exceeded` (bomb guard), `provider_refused`, `dimension_mismatch`, `model_unavailable`, `document_deleted`.
- Retryable by default: provider timeout/rate limit/unreachable, doc store or storage unavailable, any other exception (including a damaged file raising out of the parser).
- Retry mechanics: on a retryable failure, `XADD` a fresh message `{task_id, digest}` then `XACK` the old one (duplicates are harmless: lock plus attempt guard plus `progress` check; loss is impossible). Optional backoff: do not requeue instantly; use `delay = min(2**attempt * 2, 30)` as a `not_before` field the collector respects.
- Poison file recommendation: a `.docx` whose bytes start with the zip signature but are truncated/garbage fails in `python-docx` on every attempt, before any embedding call (zero provider cost). Treat parser exceptions on such files as retryable, which makes success criterion 4 provable in the real stack; document this as a decision (alternative: classify damaged files terminal and use a deterministic fault such as an unreachable doc store for the retry-cap proof, which is harder to arrange without mocks).
- Graceful shutdown (SIGTERM): stop taking messages, finish the current batch, release the lock, refund the attempt (`retry_count - 1`), leave the message pending for immediate `XAUTOCLAIM` (min-idle 0 for messages whose owner heartbeat is gone).
- Document-level D-14: a task whose pages carry no text emits zero chunks and succeeds with a log line "N of M pages in this range had no readable text". The roll-up marks the document failed `no_readable_text` (terminal, no retry) when every task is done and total chunks are zero. This is within seconds because no embedding call is made.

### Pattern 4: Cancellation
- Source of truth is MySQL: `document.run = '2'` (cancel). API cancel is one transaction: set `run='2'`, leave `progress` as is, keep chunks, `UPDATE pipeline_operation_log` to cancelled, then settle totals. No Redis cancel key is required (the reference's `{task_id}-cancel` key is an optimisation, and Valkey may be flushed). A task is "cancelled" when its row is missing, its document is missing, or `document.run != '1'`.
- Notice latency: the heartbeat thread polls every `CANCEL_POLL_SECONDS` (default 1 s) and sets a `threading.Event`. Checkpoints in the pipeline check the event between pages, between 64-chunk batches and before every insert. For a blocking embedding call use a cancel-aware wait: submit the batch to the embed executor, then `concurrent.futures.wait([future], timeout=0.5)` in a loop checking the event; on cancel abandon the future (its thread ends at the driver's own 30 s timeout, result discarded, no insert) and raise `TaskCancelled`. Result: cancel is observed within about 1.5 s even mid-call.
- Representation (no schema change): cancelled = `document.run = '2'`; failed = `run = '4'` and `progress = -1`; "Partly indexed" is computed in the DTO as `run in ('2','4') and chunk_num > 0`; chunks and totals stay (D-06). `Parse again` from `2`/`4` creates new tasks and sets `run = '1'`.
- Race: Parse again right after Cancel while the old worker is still inside an embedding call. Old task rows are deleted by the re-parse; the old worker's post-insert row re-check fails and it deletes `{"task_id": old}`; the stale-worker guard is therefore mandatory, not optional.

### Pattern 5: Counters are set to the truth
`settle_totals(doc_id)`: in one transaction `SELECT chunk_num, token_num FROM document WHERE id=? FOR UPDATE`; call `DocStore.stats({"doc_id": [doc]}, index, kb_id, sum_field="token_num_int")` -> `(count, sum)`; `UPDATE document SET chunk_num, token_num`; `UPDATE knowledgebase SET chunk_num = GREATEST(chunk_num + (new_c - old_c), 0), token_num = ...`. Idempotent, safe to repeat, repairs drift. Called by: the roll-up daemon each cycle for running documents and at every terminal transition, cancel, manual chunk create, chunk delete, document re-parse reset (sets 0 after the index delete). The existing delete path already subtracts `document.chunk_num` / `token_num`, which stays consistent. Why not increments: the reference's `increment_chunk_num` double counts when a worker dies after incrementing and before XACK, and cannot represent D-06 partial totals.
**`token_num` meaning (decision):** sum of `token_num_int` of the document's chunks, where `token_num_int` is the tiktoken `cl100k_base` count of the chunk text at index time (deterministic; independent of provider usage, which `LLMBundle` already records in `tenant_llm.used_tokens`). The reference counts embedding tokens; docs only name the column.
**Port addition:** `DocStoreConnection.stats(condition, index_name, dataset_id, sum_field=None) -> StatsResult(count, total)`; ES adapter: `_search` with `size=0`, `track_total_hits=true`, `sum` aggregation, same `kb_id` filter and key validation. One abstract method, contract test added to `test/helpers/doc_store_contract.py`.

### Pattern 6: Chunk document written to the index
Fields, keeping the docs table (`indexing.md`) and reference names; new fields marked NEW (each matches an existing dynamic template, so no mapping change):

| Field | Type via template | Value |
|-------|-------------------|-------|
| `id` (`_id`), `doc_id`, `kb_id` | keyword | `doc_id_order`; ids |
| `docnm_kwd` | keyword | file name |
| `content_with_weight` | stored text, not indexed (`_with_weight`) | raw chunk text |
| `content_ltks`, `content_sm_ltks` | whitespace text | tokenised / fine-grained tokenised |
| `title_tks`, `title_sm_tks` | whitespace text | tokenised file name |
| `position_int` | integer array | `[[page, x0, top, x1, bottom], ...]` pixel-free PDF points x 1 (see below) |
| `page_num_int`, `top_int` | integer | first box |
| `available_int` | integer | 1 on, 0 off |
| `q_1024_vec` | dense_vector | L2-normalised |
| `create_time`, `create_timestamp_flt` | date / float | index time |
| `order_int` NEW | integer | R-11 order (sort key) |
| `task_id` NEW | keyword (`*_id`) | producing task |
| `origin_kwd` NEW | keyword | `parsed` / `edited` / `manual` |
| `token_num_int` NEW | integer | tiktoken count |

`position_int` order is `[page, x0, top, x1, bottom]` per CHUNK-16 and `indexing.md`; the reference stores `[page, x0, x1, top, bottom]`; the docs win. Coordinates: PDF points, origin top-left (convert pdfium's bottom-left `y`), rounded to int, **page numbers 1-based**. Nested arrays in an integer field are accepted by Elasticsearch and kept in `_source` `[ASSUMED: ES behaviour not spiked; verify in Wave 0]`. D-04 count: `search(condition={"doc_id": d, "origin_kwd": ["edited","manual"]}, limit=0).total`. D-12 filter: `condition["available_int"] = 0|1`. An edit sets `origin_kwd = "edited"` unless it is already `manual`.
Document-level switch (DOC-13): `document.status` '1'/'0' plus a bulk `available_int` update on all its chunks (reference behaviour); re-enabling turns every chunk on, overriding individual switches (Open Question 4).

### Pattern 7: Embedding in the worker (IDX-01..03, reconciliation)
- Worker unit is a batch of `INGEST_BATCH_SIZE = 64` chunks (IDX-01, IDX-07, progress, cancel check, insert); `LLMBundle.encode` is called with those 64 texts and the existing driver splits them into provider calls of 16 (`rag/llm/embedding_model.py: BATCH_SIZE = 16`). Both numbers hold: 64 is the pipeline batch, 16 the provider request size; record as a decision. Do not raise the driver's 16 (provider limits unknown).
- Truncation (IDX-02): the driver already cuts input to 8191 tokens (`TOKEN_CEILING`, spec says 8192; keep the driver value, it is the safe bound) and replaces empty text with a space. Empty chunks must still be kept out of `insert` (zero vector refusal, R-145): drop chunks whose stripped text is empty before embedding.
- Order: the driver returns vectors in input order; the worker asserts `len(vectors) == len(batch)`.
- L2 (IDX-03): worker normalises with `math.sqrt(sum(v*v))` (no numpy); a vector whose norm is 0 or non-finite fails the chunk batch as `provider_refused`-class terminal (the doc store would refuse it anyway).
- Dimension: `LLMBundle(..., expected_dimension=dataset dimension)` raises `dimension_mismatch` (terminal).
- Usage: recorded by `LLMBundle` per call (`tenant_llm.used_tokens`); the worker logs `usage_total` per task (no field name containing "token", R-149).
- Timeouts and the retry cap: one provider call times out at 30 s (`LLM_EMBEDDING_TIMEOUT_SECONDS`) after the driver's own retries (`LLM_MAX_RETRIES`). A timeout is retryable at task level, so the worst case per task is 3 attempts x (driver retries x 30 s). Cancel is not blocked by it (Pattern 4). A single 30 s OpenRouter timeout seen in the Phase 3 gate recovers through the driver retry or the first task retry.
- Blocking: `LLMBundle` is synchronous and its construction reads one credential row; build and call it from the embed executor thread. BE-07 (async methods block the loop) is not exercised by the worker's sync path; fixing it is needed only when Phase 5 uses `async_*`; leave to Phase 5 and record that Phase 4 did not take it on (Open Question 6).
- Cost estimate for one gate run `[ASSUMED]`: PDF 13 pages x 6 short paragraphs is roughly 40 to 80 chunks of 100 to 200 tokens, plus five small files of about 5 chunks each, so under 20,000 embedding tokens including retried batches; at an assumed price in the order of US$0.01 per million tokens for `baai/bge-m3` the cost is a fraction of a cent. Three clean-room runs plus the kill-test (INGEST_BATCH_SIZE=2) stay below US$0.01. The provider price was not looked up.

### Anti-Patterns to Avoid
- Incrementing `chunk_num`/`token_num` on task completion (double counts on crash).
- Reusing previous chunks on re-parse (keeps edited chunks, violates D-03).
- Trusting queue message content for tenant, document, page range or parser (load from MySQL by `task_id`).
- Holding a DB connection across the embedding call (ING-15): open `DB.connection_context()` per short operation.
- A worker that edits `document` rows directly outside the roll-up (multiple writers); only the daemon and the API write document state.
- Docs/reference queue name drift: the reference flow doc mentions `ragflow_TASK_EXE_QUEUE` and `RPUSH`; `docs/10-cache-and-queues/queues.md` and `ingestion-pipeline.md` (streams `te.{p}.common`) win, and `document-processing.md` contradicts them; record in DECISIONS.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Distributed lock | `SET NX` + manual Lua | `valkey.lock.Lock` (`acquire`, `reacquire`, `owned`) | Owner token and compare-and-delete already implemented and spiked |
| Queue reclaim | Own pending scanner | `XAUTOCLAIM` | Server-side idle filter; no `XPENDING`+`XCLAIM` race |
| Retry of provider calls | New loop | existing `rag.llm.retry.run_with_retries` inside the driver | Already bounded and tested |
| Encoding detection | Heuristic sniffing | `charset_normalizer.from_bytes` | Already in the image |
| Bulk indexing | Per-document `index` calls | `ESConnection.insert` (bulk, refresh, vector checks) | Existing hardened adapter |
| PDF text boxes | Parsing PDF streams | `pypdfium2` textpage `get_charbox` / `get_rect` | Spiked: exact boxes |
| Archive bomb protection | Ad hoc size checks inside parsers | one `check_ooxml_limits(zipfile)` before any Office parser | Single reviewed choke point |
| Token counting | `len(text.split())` | tiktoken `cl100k_base` (already used by the embedder) | Same unit as truncation |

**Key insight:** every hard part of this phase (exactly-once effects across crashes) disappears when effects are idempotent by construction: deterministic ids, delete-by-task before write, and set-to-truth counters.

## Runtime State Inventory

Not a rename/refactor phase; omitted. One related note: the first run of this phase puts the first rows into `ragflow_{tenant}` indices and the first entries into the `te.*` streams, so there is no pre-existing runtime state to migrate. `Task` rows are deleted by Phase 3 document delete (`release_files`), consistent with the new flow.

## Common Pitfalls

### Pitfall 1: `XAUTOCLAIM` steals a live task
**What goes wrong:** pending entries age while a long task runs; another worker claims and runs it concurrently.
**Avoid:** every claimed or fresh message must pass the task lock gate; the owner renews the lock; `RECLAIM_IDLE_MS` is at least 2 x lock TTL. **Warning sign:** two consumers logging the same `task_id`.

### Pitfall 2: valkey-py `justid` drops the cursor
`xautoclaim(..., justid=True)` returned only `[ids]` in 6.1.1 `[VERIFIED: spike]`. Do not use it and do not unpack three values from it.

### Pitfall 3: Deleted document, running worker
`document_service.delete_documents` prunes the index first, then deletes rows. A worker inserting between those steps leaves orphan chunks. The worker re-checks the task row after each insert and deletes by `task_id` if gone; delete must also set `run` to cancelled... simplest: delete first cancels (rows gone) and the guard cleans up. Add a test.

### Pitfall 4: Chunks beyond the shrink
A retry producing fewer chunks leaves old high-order ids. Fixed by delete-by-`(doc_id, task_id)` before the first insert of each attempt.

### Pitfall 5: Zero vectors and empty chunks
`insert` refuses the whole batch on one zero vector (R-145). Filter empty chunks before embedding; fail terminal if the vector is zero.

### Pitfall 6: Vector field not mapped
BE-13: an unmapped `q_{dim}_vec` is silently dynamic-mapped as float. Take BE-13's `insert` mapping check into this phase (first writer of vectors), or at least call `create_idx` at task start (idempotent, `DimensionConflict` is terminal).

### Pitfall 7: Chunk keyword filter
BE-06: `query_string` on raw user text throws on `what is (revenue` and allows leading wildcards. The chunk list keyword filter is the first user-text consumer. Take BE-06's fix: escape reserved characters and set `allow_leading_wildcard: false`, `analyze_wildcard: false` in the adapter. Also pass the keyword through the same tokenizer as `content_ltks`.

### Pitfall 8: Pdfium is not thread safe
Use one process-wide lock around every pdfium call (`pypdfium2` documents that PDFium is not thread safe `[ASSUMED]`) and close pages, textpages and bitmaps. One zoom-3 A4 bitmap is about 13.5 MB (`[VERIFIED: spike]`: 1786x2526 RGB), render 0.05 s. Never hold more than one rendered page.

### Pitfall 9: Page counting semantics
`MAXIMUM_TASK_PAGE_NUMBER` in `api/db/models/knowledge.py` is 1,000,000 (the "to the end" sentinel), not 12. Add `TASK_PAGE_SIZE = 12` (configurable, `parser_config.task_page_size`) and keep `from_page` 0-based, `to_page` exclusive.

### Pitfall 10: Peewee pool and long inference
Connections returned to the pool before the embedding call; the heartbeat thread opens its own short `connection_context()` each poll. A MySQL write is never retried by the pool (R-83), so progress writes must tolerate failure (log and continue; the next write wins).

### Pitfall 11: Unique Valkey consumer names and cleanup
Unique names accumulate in `XINFO CONSUMERS`; delete empty dead ones (heartbeat expired) during housekeeping.

### Pitfall 12: Test hooks in production code
CI forbids `sleep(` text in tests and `NotImplementedError` placeholders. Do not add a "hold here" hook to production code to make kill tests deterministic; use the configuration knob `INGEST_BATCH_SIZE` (see Validation).

## Code Examples

### Valkey streams, claim and lock (spiked)
```python
# Source: spike on valkey/valkey:8 (8.1.10) with valkey-py 6.1.1, 2026-10-10
r.xgroup_create("te.0.common", "ragflow_consumer_group", id="0", mkstream=True)   # BUSYGROUP is ignored
r.xadd("te.0.common", {"message": json.dumps({"task_id": tid, "digest": dg})})
got = r.xreadgroup(GROUP, consumer, {"te.1.common": ">", "te.0.common": ">"}, count=1, block=1000)
next_id, claimed, _deleted = r.xautoclaim(Q, GROUP, consumer, min_idle_time=reclaim_ms, start_id="0-0", count=10)
lock = Lock(r, f"lock:task_{tid}", timeout=60, thread_local=False)
if lock.acquire(blocking=False):
    ...             # heartbeat thread: lock.reacquire() every 20 s
    lock.release()  # compare-and-delete
r.xack(Q, GROUP, msg_id)
```

### PDF text with character boxes, page count, raster at zoom 3 (spiked)
```python
# Source: spike with pypdfium2 5.14.0 on a generated 13-page PDF
import pypdfium2 as pdfium
pdf = pdfium.PdfDocument(path_or_bytes)          # corrupt input: PdfiumError("Failed to load document")
n_pages = len(pdf)
page = pdf[i]; tp = page.get_textpage()
text = tp.get_text_range()                       # '' on a page without a text layer -> D-14
lines = [tp.get_rect(k) for k in range(tp.count_rects())]   # (l, b, r, t), PDF points, origin bottom-left
chars = [tp.get_charbox(j) for j in range(tp.count_chars())]
img = page.render(scale=3).to_pil()              # PARSE-03; 1786x2526 RGB, 0.05 s, PNG 436 KB for a text page
page.close(); pdf.close()
```
Spiked results: text page 1614 chars, mixed PDF per-page counts `17, 0, 19` (blank image page yields 0), garbage bytes raise `PdfiumError`. Max RSS after importing all candidate parsers: 57 MB; one render run: 69 MB.

### Zip-bomb guard (measured)
A DOCX with one 200 MB member of zeros compresses to 199 KB; `ZipInfo.file_size` shows 200 MB before any extraction, so the guard is a pre-check on declared sizes.
```python
def check_ooxml_limits(zf: zipfile.ZipFile, *, max_members=2000, max_total=200 * 2**20, max_member=100 * 2**20, max_ratio=200):
    infos = zf.infolist()
    if len(infos) > max_members or sum(i.file_size for i in infos) > max_total: raise ArchiveLimitsExceeded
    for i in infos:
        if i.file_size > max_member or (i.compress_size and i.file_size / i.compress_size > max_ratio): raise ArchiveLimitsExceeded
```

### Naive chunker contract
```python
# rag/chunking/naive.py
def chunk(blocks: Iterator[ParsedBlock], cfg: NaiveConfig) -> Iterator[Chunk]:
    # greedy merge of blocks until chunk_token_num (tiktoken), split at delimiter characters first,
    # overlap from cfg.overlapped_percent; each Chunk keeps the merged blocks' page/box list.
```
`ParsedBlock(text, page, boxes[(page,x0,top,x1,bottom)], kind)` and `Chunk(text, positions, token_num, order)` are the only two types; every parser yields `ParsedBlock`.

## Specific Findings by Obligation

### PDF extraction (obligation 5)
- pypdfium2 alone provides what PARSE-02/03 need; pdfplumber is not needed in Phase 4. Per page: text, line rects, char boxes; boxes converted to top-left origin.
- Phase 4 needs no raster during ingestion (no OCR, no layout). `rasterize_page(pdf, i, zoom=3)` is implemented (PARSE-03) and used by: the thumbnail (page 0 downscaled to about 160 px JPEG, stored base64 in `document.thumbnail` by the worker on its first task; DOC-20) and the on-demand page image route.
- Page image route (new, decision): `GET /api/v1/datasets/{id}/documents/{doc_id}/pages/{n}/image` renders one page (zoom 3, JPEG q80, `ETag = content_hash:n:zoom`, `Cache-Control: private`) in a bounded `PDF_EXECUTOR` (2 threads), fetching the blob to a temp file via `iter_chunks` (closed in `finally`). Peak API memory for one request is about 14 MB bitmap + encode buffers; the 768 MB app container is not at risk. No page cache in MinIO this phase (avoids cleanup on delete and dedupe).
- Document preview (DOC-21, UI-19): `GET .../documents/{doc_id}/content` streams the original (`Content-Disposition: attachment` for everything except PDF inline; `X-Content-Type-Options: nosniff`; HTML is never served inline).
- D-14: a task counts pages with empty `get_text_range().strip()`.
- Memory: a 100 MB PDF read from a temp file by pdfium (not into Python memory); worker peak estimated 250 to 400 MB `[ASSUMED, measure with scripts/record_memory.py]`. **Proposed executor limit: `mem_limit: 768m`** in `docker-compose.dev.yml` (same as app), `restart: unless-stopped`, one executor by default. Stack limits then sum to about 4.6 GB, so the gate's 4096 MB available-RAM check is the planner's attention item (Open Question 5).

### Office and text parsers (obligation 6)
- None of the parsing libraries is in `uv.lock` today (checked): all seven are new (table above). `charset-normalizer` is present as a transitive dependency.
- DOCX: `python-docx` paragraphs in order, heading style to a `kind="heading"` block, tables to HTML strings (`<table>`), embedded images ignored (stored images are Phase 6; PARSE-09 mentions them, flag in Open Questions). XLSX: `openpyxl.load_workbook(read_only=True, data_only=True)`, one block per row group with header-row context, capped at configurable `XLSX_MAX_CELLS`. PPTX: one block per slide (title, text frames, table cells, notes). HTML: `BeautifulSoup(markup, "lxml")`, drop `script`, `style`, `noscript`, `template`, comments; text only (never reproduce markup). TXT/MD/CSV/JSON (D-13): decode via charset-normalizer with UTF-8 first, paragraph split on blank lines.
- Router: `rag/parsers/router.py` maps suffix to parser; unmapped types return `unsupported_type` at the API (`parse_unavailable` reason, 400) and the dataset DTO exposes `parseable: bool` so the UI hides the button.

### Tokenizer and CHUNK-17 (obligation 6)
- The reference tokenizer delegates to `infinity.rag_tokenizer`; `infinity-sdk` 0.7.3 is a 29 MB wheel with 22 declared dependencies including pandas, pyarrow, polars-lts-cpu, numpy<2, sqlglot, thrift, datrie, hanziconv and nltk (PyPI metadata, checked). An install attempt into a scratch venv had not finished downloading when abandoned; I did not measure installed size.
- Smallest correct option: `rag/nlp/tokenizer.py` in the repo, stdlib only: NFKC (covers `strQ2B` full-to-half width), lower-case, URL/email stripping regex, Latin tokens by `\w+`, CJK as unigrams plus bigrams, `fine_grained_tokenize` splits camel/underscore and digit boundaries, token positions kept for highlighting. `content_ltks` is the space-joined coarse tokens, `content_sm_ltks` the fine-grained ones. The ES templates (`*_ltks` whitespace analyzer) already fit. The same function must tokenise queries in Phase 5 (shared module).
- Gap to flag: traditional-to-simplified Chinese (CHUNK-17) needs a mapping table (`hanziconv`, tiny, is what the reference uses); it is deferred to Phase 6 with a dictionary tokenizer, and recorded as a partial coverage of CHUNK-17 in Phase 4 (Open Question 3). English and mixed text are fully covered.

### API surface (additions to `conf/routes.yaml`; Nginx already routes `/api/v1/datasets/` and `/v1/` to Python)
| Method | Path | Notes |
|--------|------|-------|
| POST | `/api/v1/datasets/{dataset_id}/documents/parse` | body `{doc_ids, run:"1"|"2", confirm_replace?}`; `run=2` cancels (DOC-10); refuses `confirm_replace=false` with 409 `confirm_required` carrying chunk/edited counts (D-04/D-09) |
| POST | `/api/v1/datasets/{dataset_id}/documents/batch-update-status` | DOC-13 |
| GET | `.../documents/{doc_id}/chunks` | page, size, keyword, `available` filter (0/1/all) |
| POST | `.../documents/{doc_id}/chunks` | manual chunk (CHUNK-19) |
| PATCH | `.../documents/{doc_id}/chunks/{chunk_id}` | text edit and/or `available` (CHUNK-20/21); edit embeds first (D-11) |
| GET | `.../documents/{doc_id}` | detail incl. failure object and `edited_chunk_count` |
| GET | `.../documents/{doc_id}/pages/{n}/image`, `/content`, `/thumbnail` | DOC-20/21 |
| GET | `/api/v1/datasets/{dataset_id}/ingestions/summary`, `/ingestions`, `/ingestions/{log_id}` | KB-14/15 from `document` counts and `pipeline_operation_log` |
| POST | `/api/v1/datasets/{dataset_id}/embedding/check` | KB-16: embed one fixed probe string, compare dimension to the recorded one |
| GET | `/v1/task/status/{task_id}` | DOC-22, tenant resolved through task -> document -> dataset |
Task and chunk ids in paths are validated as `[0-9a-f]{32}` or the chunk grammar; unknown, foreign and invisible are the one 404. Parse/cancel/edit use `can_remove_document`-style rule (`created_by`, dataset creator, elevated, never for tokens elevated). Each new tenant-scoped route needs a matrix builder and leak-sweep exerciser (D-19).

### Roll-up daemon
Runs inside each executor; every `PROGRESS_INTERVAL_SECONDS` (2) it takes the Valkey lock `update_progress` (non-blocking, TTL 10 s) and, for documents with `run = '1'`: progress = mean of task progress (failed tasks count as 0 for the mean), merges task `progress_msg` (cap 3000 lines, redacted), writes `document.progress/progress_msg/process_duration`; when all tasks are 1 -> `run='3'`, `progress=1`; when any task is -1 and none is in flight -> `run='4'`, `progress=-1`; always calls `settle_totals`. It also closes the `pipeline_operation_log` row with `operation_status` and `dsl = {"error": {"step","code","message"}, "tasks": n, "attempts": max}`. It never touches a document with `run = '2'`.
D-08 storage: the plain reason and step live in the log row's `dsl.error`; the document list/detail join the latest log row for documents in states 2/4 in one batched query. Server logs keep the stack (redacted, BE-08: pass strings, not exception objects, in `extra=`; take BE-08's one-branch fix because the worker is the first heavy user).

### Schema position (obligation 3)
**No schema change is needed.** Reused: `document.run/progress/progress_msg/chunk_num/token_num/process_begin_at/process_duration/thumbnail`, `task.*`, `pipeline_operation_log.*`. If the planner prefers the failure reason as a first-class column, the single candidate is `document.error_code VARCHAR(64) NULL` plus migration `0003`, regenerated Go entities (`scripts/gen_go_entities.py`) and the schema export; this research does not recommend it. Non-schema additions needing decision rows: port method `stats`, chunk fields (`order_int`, `task_id`, `origin_kwd`, `token_num_int`), `TASK_PAGE_SIZE`, the page-image route, the consumer-name rule.

### Frontend (obligation 7)
- No new npm package. Chunk inspector: left panel shows the server page image of the chunk's first position page, `position: relative` container with `<img>`; each box is an absolutely positioned `div` using percentages `x0/pageW`, `top/pageH` (page size in points returned by the chunks endpoint as `page_size[page]`), so zoom changes never misalign. Multiple pages: page selector. Right panel: chunk list, filter All/On/Off (D-12), editor, add-chunk, on/off switch.
- Live progress: React Query `refetchInterval: (query) => rows.some(r => r.run === "1") ? 2000 : false` on the documents list, plus invalidation after Parse/Cancel; stop when no row runs. Docs say "background polling" (`state-management.md`) and give no SSE route for ingestion; SSE is not used.
- Components (hand-written, D-21): chunking-method dialog (eight methods, seven disabled with copy), parser configurator (`chunk_token_num` 1..8192, `delimiter`, `overlapped_percent`), status badge states (Not started, Running with bar, Finished, Cancelled, Failed, Partly indexed), details panel, re-parse confirm dialog. Avoid stacking `AlertDialog` over `Dialog` (R-152).
- BE-09: add the `ParserConfig` pydantic validation (known keys typed and ranged, `RecursionError` caught) because this phase is the first consumer of those keys; reject at the API.

### Environment and compose (DEPLOY-17)
- Same image `devrag-app:local`, new service `task-executor` in `docker/docker-compose.yml` (profile `cpu`), `entrypoint: ["tini","--","/ragflow/docker/entrypoint_task_executor.sh"]`, `restart: unless-stopped`, same `x-app-env`, no ports, healthcheck = Valkey heartbeat key age < `WORKER_HEARTBEAT_TIMEOUT` (script reads the zset). Scale with `docker compose up --scale task-executor=2` (no container_name, no fixed consumer name). Dockerfile already copies `rag/`; add `COPY` of any new top-level package (`rag/` covers all proposed modules). Dev override adds `mem_limit: 768m`.
- `docker/entrypoint_task_executor.sh` must wait for MySQL schema (init service already `depends_on`).

## State of the Art

| Old approach | Current approach | Impact |
|--------------|------------------|--------|
| Reference: content-hash chunk ids, reuse of previous task chunks | Docs: `doc_id_order`, delete-and-rewrite | Deterministic, honours D-03 |
| Reference: increment counters at task end | Set-to-truth under row lock | Crash-safe |
| Reference: fixed consumer `task_executor_{type}_{idx}` | Unique per process + `XAUTOCLAIM` | Scale without config |
| PyMuPDF (docs wording) | pypdfium2 | AGPL avoided (D6) |

**Deprecated/outdated:** `valkey-py` `xautoclaim(justid=True)` loses the cursor (client behaviour in 6.1.1); the docs' queue name `ragflow_TASK_EXE_QUEUE` in `document-processing.md`.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Elasticsearch stores nested arrays `[[p,x0,t,x1,b],...]` in an `integer` field and returns them unchanged in `_source` | Pattern 6 | Inspector boxes break; fall back to a flat array with 5-int stride or `*_nst` nested |
| A2 | pdfium is not thread safe (process-wide lock needed) | Pitfall 8 | Lock unnecessary (harmless) or crashes if wrong the other way |
| A3 | Licences and download counts of the seven new packages | Package table | User approval based on wrong licence data |
| A4 | Embedding cost per gate run is under US$0.01 | Pattern 7 | Larger bill; price not looked up |
| A5 | Worker peak memory 250 to 400 MB; 768m limit suffices | Obligation 5 | OOM kill on larger files; measure with `record_memory.py` |
| A6 | `python-docx`/`python-pptx` (lxml) do not resolve external entities by default | Security | XXE exposure; add a unit test with an entity payload and add `defusedxml` if it fails |
| A7 | A truncated-zip `.docx` raises inside python-docx every time (poison file) | Pattern 3 | Test arrangement changes |
| A8 | Re-enabling a document should turn all its chunks on | Pattern 6 | Individual switches lost silently |
| A9 | `token_num` as tiktoken chunk-text tokens is acceptable (vs embedding usage) | Pattern 5 | Different totals than reference users expect |
| A10 | Pass a 12-page task budget of up to 1000 chunks per page is never exceeded | Pattern 1 | Order overflow; worker raises a terminal error |

## Open Questions

1. **Poison-file classification.** Recommended: damaged Office/PDF files are retryable (3 attempts) so criterion 4 is provable with a zero-cost file. Alternative: terminal "file is damaged" and prove the cap with a different deterministic fault. Needs the planner's/user's call.
2. **chardet vs charset-normalizer.** Docs/CLAUDE.md name chardet; charset-normalizer avoids a new package. Which does the user want at the approval checkpoint?
3. **CHUNK-17 coverage in Phase 4.** English and mixed text are covered; traditional-to-simplified conversion and a dictionary Chinese tokenizer are deferred to Phase 6 (character n-grams for CJK now). Confirm that partial coverage is acceptable.
4. **Document on/off versus per-chunk switches.** Reference behaviour overrides individual switches on re-enable. Alternative: a second field. Decide before the UI copy is fixed.
5. **Memory budget.** Adding a 768m executor lifts the sum of container limits to about 4.6 GB while the gate requires 4096 MB available RAM; confirm or lower the limit after measuring.
6. **BE-07** (async `LLMBundle` blocks the loop) is not hit by the sync worker path; recommended to defer to Phase 5. **BE-06, BE-08, BE-09, BE-13 (insert mapping check)** are recommended to be taken on in Phase 4 (listed with their trigger above).
7. **PARSE-09/PARSE-11 "embedded images":** images are not stored or captioned until Phase 6; only text is extracted now. Confirm the requirement is satisfied by listing them as skipped in the log.
8. **Crash-test determinism:** the plan assumes the config knob `INGEST_BATCH_SIZE=2` in a test compose override and a TXT file of about 40 chunks; confirm that about 40 chunks per kill test is within D-16's "few dozen".
9. **D-14 wording:** the "N of M pages had no readable text" figure is per task range; the roll-up can sum them for the document-level log line.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker / compose | executor container, kill tests | yes | stack up, 6 containers healthy | — |
| Valkey (stack) | queue, lock | yes | valkey/valkey:8 (spike: 8.1.10) | — |
| Elasticsearch 8.11.3 | index | yes | healthy, 594 MiB used | — |
| MySQL, MinIO | state, blobs | yes | healthy | — |
| uv + Python 3.13 | spikes, install | yes | uv 0.9.18, cpython 3.13.11 | — |
| OpenRouter key | live tier | present in git-ignored `docker/.env` (not read) | — | none: live tier fails by design |
| slopcheck | package audit | no | — | all packages `[ASSUMED]`, human checkpoint |
| Host free RAM | gate | 6.3 GB available at research time | — | gate needs >= 4096 MB |
| Throwaway containers | spikes | `p4spike-valkey` created and removed | — | — |

**Missing with no fallback:** none. **Host notes:** `vm.max_map_count` resets after reboot (B-02/B-33); gate needs `PREFLIGHT_ALLOW_LOW_MAP_COUNT=1` and `LIVE_BASE_URL=http://127.0.0.1:8088`.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.1.1, pytest-asyncio 1.4.0 (`asyncio_mode=auto`, `-p no:anyio`), pytest-timeout 2.4.0; vitest for web |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]`; markers `unit`, `integration`, `e2e`, `serial`, `live_model` |
| Quick run command | `uv run pytest test/unit_test -q -x` |
| Full suite command | `uv run python run_tests.py` then `scripts/clean_room.sh --runs 3` (phase gate) |
| Helpers | `test/helpers/wait.py::wait_until` (use instead of sleeps), `test/helpers/uploads.py::pdf_bytes/text_bytes`, `test/helpers/doc_store_contract.py` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ING-01 | 13-page PDF -> 2 tasks (0..12, 12..13), 0-based, exclusive | unit + integration | `pytest test/unit_test/test_task_split.py -q` | Wave 0 |
| ING-02/03 | XADD names; priority 1 drained first | integration (real Valkey) | `pytest -m integration test/integration/test_queue.py -q` | Wave 0 |
| ING-04..07 | two consumers, no double delivery; XAUTOCLAIM; lock owner token; ack | integration | `pytest -m integration test/integration/test_task_lock_reclaim.py -q` | Wave 0 |
| ING-08/10 | roll-up progress, heartbeat | integration | `pytest -m integration test/integration/test_rollup.py -q` | Wave 0 |
| ING-11/12 | retry cap 3, terminal failure, cancel latency under 5 s | e2e serial | `pytest -m "e2e and serial" test/testcases/test_ingestion_failure.py -q` | Wave 0 |
| ING-13..16 | pipeline end to end; separate container | e2e + live_model | `pytest -m live_model test/testcases/test_live_ingestion.py -q` | Wave 0 |
| PARSE-02/03 | text, boxes, zoom-3 size 1786x2526 for A4 | unit | `pytest test/unit_test/test_pdf_parser.py -q` | Wave 0 |
| PARSE-09..13 | each format yields expected text | unit (generated files) | `pytest test/unit_test/test_parsers.py -q` | Wave 0 |
| CHUNK-01/02 | factory refuses unimplemented chunkers explicitly; naive size/delimiter | unit | `pytest test/unit_test/test_naive_chunker.py -q` | Wave 0 |
| CHUNK-16..21 | chunk fields, list/create/edit/disable reflected in index | integration (real ES) | `pytest -m integration test/integration/test_chunk_service.py -q` | Wave 0 |
| IDX-01..03,07 | batches of 64, L2 norm = 1.0 within 1e-6, deterministic ids, re-parse same count | integration | `pytest -m integration test/integration/test_indexing.py -q` | Wave 0 |
| IDX-14, DOC-09..13 | delete removes chunks; parse/cancel/re-parse; status batch | e2e | `pytest -m e2e test/testcases/test_parse_flow.py -q` | Wave 0 |
| DOC-20..23, KB-14..16,19 | thumbnail, preview, task status, summary, logs, check, totals | e2e | `pytest -m e2e test/testcases/test_ingestion_api.py -q` | Wave 0 |
| UI-13..17,19 | dialogs, progress poll, inspector boxes, editor | vitest + real Chrome tier | `cd web && npx vitest run src/pages/dataset src/pages/chunk` | Wave 0 |
| DEPLOY-17 | executor service up, scales to 2 | compose smoke | `scripts/wait_stack.sh` extended | Wave 0 |
| E2E-05/06, TEST-11 | document-processing and indexing flows, no mocks | e2e + live_model | as above | Wave 0 |

### Crash, reclaim, poison and cancel strategy (obligation 9)
- **Kill mid-task, deterministic, no sleeps:** compose override for the test tier sets `INGEST_BATCH_SIZE=2` and `TASK_LOCK_TTL_SECONDS=8`, `RECLAIM_IDLE_MS=16000`. Test uploads a TXT of about 40 chunks, posts Parse, then `wait_until(lambda: index_count(doc) >= 2 and task.progress < 1, timeout=60)`; this is a real observable (first batch is in Elasticsearch, task not finished). Then `docker kill <executor>` via the Docker CLI from the host-side test (the clean-room script runs on the host). A second executor (started beforehand by `--scale task-executor=2`, or the killed one restarted by compose) reclaims once the lock TTL lapses; test `wait_until(doc.run == "3", timeout=120)` and asserts `count(doc_id) == expected`, `task.retry_count == 2`, and the id set equals the manifest.
- **Poison:** truncated `.docx` (zip magic + garbage); assert `retry_count == 3`, `run == "4"`, `progress == -1`, UI/API failure object has `step` and plain `message`, no path or traceback substring; assert zero provider calls (usage counter unchanged).
- **Cancel:** with `INGEST_BATCH_SIZE=2` same observable, then POST `run=2`; `wait_until(run == "2")`; assert chunks kept, `chunk_num` equals index count, and no new chunks appear after a settle check (`wait_until` on a stable count using an Event-based poll).
- **Re-parse identical count:** parse, record count, parse again, compare; also after a cancel and a failed run.
- **Lock unit tests** run against real Valkey (project rule: no mocks of own services); the Valkey and ES used are the stack's.
- CI rules: no `sleep(` text, no `NotImplementedError`; use `wait_until` and `threading.Event().wait(...)` only inside helpers.

### Sampling Rate
- **Per task commit:** `uv run pytest test/unit_test -q -x` (and the one integration file touched).
- **Per wave merge:** `uv run pytest -m "integration" -q` plus `uv run python scripts/ci/run_all.py`.
- **Phase gate:** `scripts/clean_room.sh --runs 3` with `PREFLIGHT_ALLOW_LOW_MAP_COUNT=1 LIVE_BASE_URL=http://127.0.0.1:8088`.

### Wave 0 Gaps
- [ ] All test files listed above (none exist)
- [ ] `test/helpers/ingest.py`: generated 13-page PDF (spiked recipe with `fpdf2` is NOT allowed as a project dependency; write a minimal PDF by hand or use the existing `uploads.pdf_bytes` helper extended), small DOCX/XLSX/PPTX/HTML generated with the new libraries, poison files
- [ ] Doc-store contract cases for `stats`
- [ ] Compose test override for the executor (`INGEST_BATCH_SIZE`, TTLs)
- [ ] Web test fixtures for the chunk inspector

## Security Domain

### Applicable ASVS Categories (L1)
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | inherited | existing gate; worker has no user-facing auth |
| V3 Session Management | inherited | none new |
| V4 Access Control | yes | `tenant_scope` + generated permission table; parse/edit rule = `can_remove_document`; one 404; worker loads tenant from MySQL |
| V5 Input Validation | yes | pydantic request models `extra="forbid"`; `ParserConfig` ranges (BE-09); id grammars |
| V6 Cryptography | no new | message integrity by digest check only, not a secret |
| V7/V8 Errors, data protection | yes | plain reasons only; redaction (D-23) |
| V12 Files | yes | archive limits, no path from file names, safe preview headers |

### Known Threat Patterns
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Zip/DOCX/XLSX/PPTX bomb | DoS | `check_ooxml_limits` before parsing (members, total, per member, ratio); openpyxl read-only with cell cap; pdfium page cap 1,000,000 and file cap 100 MB; per-task timeout (`@timeout` equivalent via future wait) |
| XXE / entity expansion in OOXML and XLSX | Info disclosure | lxml defaults in python-docx/pptx/openpyxl (`resolve_entities` false assumed, A6); unit test with an external-entity payload; add `defusedxml` only if the test fails |
| HTML script/markup in chunks | XSS | BeautifulSoup text only; chunk text stored as text and rendered as a text node; ES highlight encoder `html` (BE-13) if highlights are ever shown |
| Extracted image paths / stored object keys | Tampering | none written this phase; server-generated keys only (R-144); no filename in any key |
| Cross-tenant chunk/task access | Info disclosure | every route resolves dataset visibility first; every ES call AND-ed with `kb_id` and tenant index; chunk ids validated against grammar and `doc_id` ownership |
| Queue message tampering | Tampering/EoP | message holds only `task_id` + `digest`; worker loads everything from MySQL and drops digest mismatches; Valkey is password protected, internal network |
| Error detail leakage | Info disclosure | failure object built from typed codes; free text from exceptions never stored; logs redacted; progress_msg lines pass through `redact_text` |
| Stale/zombie worker writes | Tampering | task-row re-check after insert, delete by `task_id` |
| Resource exhaustion by a huge parse request | DoS | `doc_ids` max 100 (as delete), per-tenant rate limit via `FixedWindowLimiter` on parse |
| Preview of active content | XSS | `/content` sets `Content-Disposition: attachment` except PDF, `nosniff`, `Content-Security-Policy: sandbox` |

## Sources

### Primary (HIGH confidence)
- Spike on `valkey/valkey:8` (server 8.1.10) with valkey-py 6.1.1: XADD/XREADGROUP/XAUTOCLAIM/XPENDING/XACK, Lock, Lua scripts (2026-10-10)
- Spike with pypdfium2 5.14.0: page count, text, char boxes, rects, zoom-3 render, blank page, corrupt file (2026-10-10)
- `uv pip install` resolution of the seven packages into a scratch venv (versions and sizes)
- PyPI JSON metadata for `infinity-sdk` 0.7.3 (size, 22 requirements)
- Project files: `docs/05-rag-pipeline/*`, `docs/06-document-processing/*`, `docs/10-cache-and-queues/*`, `docs/21-end-to-end-flows/*`, `docs/02-frontend/*`, `docs/04-api/*`, `docs/apis.md`; `api/db/models/knowledge.py`, `api/db/services/{document_service,llm_service,knowledgebase_service,tenant_scope,file_service}.py`, `common/doc_store/doc_store_base.py`, `rag/utils/{es_conn,es_mapping,storage_base}.py`, `rag/llm/embedding_model.py`, `docker/docker-compose*.yml`, `Dockerfile`, `conf/routes.yaml`, `conf/permissions.yaml`, `uv.lock`, `pyproject.toml`, `web/package.json`
- Reference (read-only): `rag/svr/task_executor.py`, `api/db/services/task_service.py`, `api/db/services/document_service.py`, `rag/utils/redis_conn.py`

### Secondary (MEDIUM confidence)
- Phase 3 summaries 03-07, 03-08, 03-11, 03-16, 03-17 and `03-REVIEW-backend.md` (BE-06..BE-13, BE-17)

### Tertiary (LOW confidence)
- Licences, popularity, price of `baai/bge-m3`, pdfium thread-safety statement, lxml XXE defaults (training knowledge only)

## Metadata

**Confidence breakdown:**
- Standard stack: MEDIUM (versions resolved today; legitimacy audit not run)
- Architecture (queue, lock, ids, counters): HIGH for Valkey/PDF behaviour, MEDIUM for Elasticsearch new-field behaviour (not spiked)
- Pitfalls: MEDIUM-HIGH

**Not verified (stated plainly):** Elasticsearch nested `position_int`, `update`/`delete` by `task_id` and the new `stats` aggregation against the real index; OpenRouter price; worker memory under a 100 MB file; XXE behaviour of the Office libraries; `infinity-sdk` installed size (install abandoned); behaviour of a truncated DOCX in python-docx; react-pdf-highlighter size (not needed); any live provider call (none made).

**Research date:** 2026-10-10
**Valid until:** 2026-11-09 (package versions move; re-resolve at install)
