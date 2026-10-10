# Phase 4: Ingestion Pipeline - Context

**Gathered:** 2026-10-10
**Status:** Ready for planning

<domain>
## Phase Boundary

A user presses Parse on an uploaded document and a background worker turns it into searchable chunks: fetch the stored file, parse it, chunk it with the `naive` chunker, embed the chunks with the dataset's real embedding model, and bulk-index them into Elasticsearch, with live progress shown in the dataset page. The worker runs as its own container, survives crashes (reclaim), retries, and honours cancel. A chunk inspector shows chunks beside the original document, and lets permitted users edit a chunk, add one by hand, and switch chunks on or off.

In scope: the parse, cancel and re-parse API and UI; `task` rows with page-range splitting; the Redis Streams queue and consumer group; the task executor process and container; the `update_progress` roll-up; the file-type router; parsers for text-layer PDF, DOCX, XLSX, PPTX, HTML and TXT (with Markdown, CSV and JSON handled as plain text, D-13); the `naive` chunker; embedding and bulk indexing; chunk list, create, edit and enable/disable; document enable/disable; ingestion summary and logs; document preview and thumbnails; chunking-method dialog and parser configurator; removal of chunks when a document or dataset is deleted.

Not in scope: OCR, layout analysis, table structure recognition and the other seven chunkers (Phase 6); retrieval, rerank and chat (Phase 5); a second doc engine or embedding provider; NATS or the Go ingestor; knowledge-graph, RAPTOR and auto-keyword enrichment.
</domain>

<decisions>
## Implementation Decisions

Every decision in the four discussed sections was chosen by the user on 2026-10-10.

### Starting and re-parsing
- **D-01:** Parsing starts only when someone presses Parse, for one document or for several selected documents. Nothing is parsed automatically after upload; documents wait at "Not started".
- **D-02:** In a dataset shared with the team, a document may be parsed, cancelled and re-parsed by its uploader, the dataset's creator, and the workspace owner and admins. Other members see status and progress but no parse controls. This is the same rule as removing documents in Phase 3 (Phase 3 D-09), and an API token is judged as its user, never elevated.
- **D-03:** Re-parsing rebuilds the document from the stored file and replaces all of its chunks, including chunks that were edited or added by hand. Hand-made changes do not survive a re-parse.
- **D-04:** Re-parsing a document that already has chunks always asks for confirmation. The dialog names the document, states its chunk count, says the chunks will be replaced, and states how many edited and hand-added chunks will be lost.

### Failure, retry and cancel
- **D-05:** A task is attempted 3 times in total (one try plus two automatic retries), then the document is marked failed. The cap is a configuration value. Failures that can never succeed (for example a PDF with no readable text, D-14) fail at once and are not retried.
- **D-06:** When a parse is cancelled or fails part-way, the chunks already indexed for that document are kept and remain searchable. They are not removed and the totals are not rolled back.
- **D-07:** A failed or cancelled document that still has chunks is shown as "Partly indexed" with its chunk count, so nobody mistakes it for a complete document. (A document can therefore be in a failed or cancelled state and still contribute to search.)
- **D-08:** A failed document shows a Failed badge with a short plain reason (for example "This PDF has no readable text" or "The embedding provider timed out"), and a details panel with the step that failed and the progress log. Stack traces, provider keys and internal paths never reach the UI or an API response; they stay in server logs, under the Phase 3 redaction rules.
- **D-09:** A failed or cancelled document offers "Parse again". It starts at once without a confirmation, unless the document's remaining chunks include edited or hand-added ones; in that case the D-04 warning appears first. Parse again replaces the partial chunks (D-03).

### Chunk editing
- **D-10:** Editing a chunk's text, adding a chunk by hand, and switching a chunk or a whole document on or off for search are allowed to the same people as parsing (D-02): the uploader, the dataset's creator, and the workspace owner and admins. Other members can read the chunks in the inspector and see no edit controls.
- **D-11:** Editing or adding a chunk needs a new embedding. If the embedding call fails, the save is refused with the reason, and the previous text and vector stay in place. The index never holds text that does not match its vector, and there is no "pending" chunk state.
- **D-12:** A chunk that is switched off stays in the inspector list in its place, visibly dimmed with an "Off" badge, and can be switched back on. A filter shows all chunks, only those on, or only those off.

### Files this phase cannot fully parse
- **D-13:** Markdown, CSV and JSON files are parsed as plain text with the TXT parser, so they become searchable in this phase. Images and every other uploaded type without a parser show "Parsing not available yet" with no Parse button, and the API refuses a parse request for them with a clear reason. Proper Markdown and table handling still arrives in Phase 6.
- **D-14:** For a PDF, pages with a text layer are parsed and pages without one are skipped and counted in the log (for example "12 of 40 pages had no readable text"). If no page has text, the document fails at once with "This PDF has no readable text; scanned documents are not supported yet" and is not retried (D-05).
- **D-15:** The chunking-method dialog lists all eight methods (General, Q&A, Paper, Book, Laws, Presentation, Table, Manual). The seven not built in this phase are shown as unavailable with "Available in a later release" and cannot be chosen. The API also refuses an unimplemented chunker explicitly; nothing falls back silently.
- **D-16:** Live test documents are tiny and purpose-built: one generated text-layer PDF of 13 or more pages with a few lines per page (enough to prove the page-range split at 12 pages), and one small file per other format. Each gate run embeds roughly a few dozen chunks on the user's OpenRouter key. No large real-world document is added to the live tiers in this phase.

### Carried from earlier phases (locked)
- **D-17:** One engine (Elasticsearch 8.11.3, one index per tenant, R-136), one embedding provider path proven live (OpenRouter with `baai/bge-m3`, 1024 dimensions), one chunker (`naive`), text-layer PDFs only. One `ParsedBlock` type and one `Chunk` type are defined before a second parser is written (roadmap scope note).
- **D-18:** Redis Streams on Valkey is the only queue (`te.{priority}.common`, consumer group, XACK); the queue sits behind an interface and NATS is not built (CLAUDE.md D2). Python owns the worker, the task executor and every route in this phase; Go owns identity only.
- **D-19:** Route, permission and isolation rules from Phases 2 and 3 apply unchanged: one envelope `{code, message, data}` with machine reasons in `data.reason`; every route declared in `conf/routes.yaml`; default-deny gates; permission decisions through the generated permission table; another tenant's or an invisible resource is the one 404; a private (`me`) dataset is hidden from everyone but its creator; every new tenant-scoped route gets a cross-tenant matrix builder and a leak-sweep exerciser.
- **D-20:** Peewee owns the schema and Go only verifies. The `task` table already exists; a schema change needs a recorded decision and a migration, not an ad-hoc column.
- **D-21:** No new package, service or image without asking the user. Hand-written shadcn-style components; English and draft Chinese copy with identical key sets; document-related locale keys avoid the `documents.` prefix (R-151).
- **D-22:** Test discipline: test-first; live tiers against the real stack and the real provider with the key in the git-ignored `docker/.env` (agents may read it, never print or write it); no mocks of own services; no fixed sleeps; nothing weakened, skipped or marked flaky. Phase exit is `scripts/clean_room.sh --runs 3` on web port 8088 with at least 4096 MB of available RAM. The dev app container has a 768 MB limit, which constrains what the worker container may load.
- **D-23:** No secret in logs or responses: the existing redaction rules cover the worker's logs, task progress messages and error details as well.

### Settled after research (2026-10-10)
D-24 to D-27 were chosen by the user in answer to the research open questions. D-28 to D-31 are the orchestrator's choices on the remaining open questions; the user has not reviewed them.
- **D-24:** Package approval (D-21) is given for seven Python packages: `pypdfium2`, `Pillow`, `python-docx`, `python-pptx`, `openpyxl`, `lxml` and `beautifulsoup4`, with the transitive packages they require. The plan verifies each package's licence and source before installing, pins exact versions and hash-locks them in `uv.lock`. No other new Python package, no new npm package and no new Docker image: `pdfplumber`, `chardet`, `readability-lxml`, `html-text`, `infinity-sdk`, `react-pdf-highlighter` and `pdfjs-dist` are not added in this phase.
- **D-25:** A damaged file that the parser cannot open (for example a truncated `.docx`) is retried up to the cap of D-05 and then fails with its reason. Only a PDF with no readable text fails at once without retries (D-14).
- **D-26:** The document switch and each chunk's own switch are separate. Switching a document off hides all its chunks from search; switching it back on restores exactly what was searchable before, so chunks someone switched off individually stay off. This is recorded per chunk in the index, not by a database change.
- **D-27:** CHUNK-17, PARSE-09 and PARSE-11 are delivered in part and recorded as partial, not complete. In this phase English and mixed text are handled fully, Chinese is tokenized by character and adjacent character pairs, and images embedded in DOCX and PPTX are skipped and counted in the log. Traditional-to-simplified conversion, a dictionary Chinese tokenizer and embedded-image handling move to Phase 6; the plan updates `REQUIREMENTS.md` and the Phase 6 roadmap entry to say so.
- **D-28:** Encoding detection for text files uses `charset-normalizer`, which is already locked, promoted to a direct dependency. The docs name `chardet` as an example; record the substitution in `.planning/DECISIONS.md`.
- **D-29:** The executor container starts with the 768 MB limit research proposed. The plan measures the worker's peak memory with the test documents and the stack's total against the gate's 4096 MB available-RAM check, and lowers the limit if the measurement allows.
- **D-30:** The worker-kill test uses a text file of about 40 chunks, which is within the "few dozen chunks per run" of D-16.
- **D-31:** Phase 3 review findings BE-06 (search text built from raw user input), BE-08 (log redaction of non-string fields), BE-09 (`parser_config` validation) and BE-13 (doc-store adapter gaps) are fixed in this phase, because this phase is the first to put real chunks behind that code. BE-07 (blocking work in the async `LLMBundle` methods) is not on the worker's path and waits for Phase 5.

### Claude's Discretion
- Chunk ID construction (R-11): research settles the exact scheme within the documented `doc_id + "_" + order`, such that re-parse and task reclaim produce no duplicate chunks. Hand-added chunks need ids that cannot collide with parsed ones.
- The Redis lock design (R-12): owner token, compare-and-delete release, TTL renewal while a task runs.
- How live the progress display is (refresh interval or push), within `docs/02-frontend/` and the documented `update_progress` roll-up.
- How edited and hand-added chunks are recorded so D-04 and D-09 can count them.
- What document preview and thumbnails cover in this phase, within the docs (DOC-20, DOC-21, UI-19).
- Worker settings: concurrency limiters, heartbeat timeout, batch sizes, executor memory limit and compose wiring, within `docs/10-cache-and-queues/` and `docs/18-deployment/`.
- Layout of the parse controls, progress display, error details panel, chunk inspector and chunk editor, to be fixed in the UI design contract (`/gsd-ui-phase 4`).
- Which Phase 3 review findings that sit in code this phase touches are fixed here (for example BE-09, validation of `parser_config` keys the chunker reads, and BE-07, blocking work on the event loop in `LLMBundle`); record any that are taken on.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.** `docs/` is authoritative over everything else.

### Pipeline, parsing and chunking
- `docs/05-rag-pipeline/ingestion-pipeline.md`, `parsing.md`, `preprocessing.md`, `chunking.md`, `embedding.md`, `indexing.md` — the pipeline stages, chunk fields and index schema
- `docs/06-document-processing/document-lifecycle.md` — document `run` states, progress and transitions
- `docs/06-document-processing/document-processing-workers.md` — the task executor
- `docs/06-document-processing/parsers.md`, `pdf-processing.md`, `office-documents.md`, `chunking-strategies.md`, `images.md`, `file-storage.md` — per-format parsers and the chunker contract
- `docs/21-end-to-end-flows/document-processing.md`, `docs/21-end-to-end-flows/indexing.md` — the flows E2E-05 and E2E-06 prove

### Queue, workers and locks
- `docs/10-cache-and-queues/queues.md`, `redis.md`, `workers.md`, `async-processing.md`, `background-jobs.md`, `scheduling.md` — stream names, consumer group, reclaim, heartbeat, lock, `update_progress`
- `docs/18-deployment/` (services, docker-compose, environment variables) — the standalone task-executor container (DEPLOY-17)

### API and frontend
- `docs/04-api/document-api.md`, `docs/04-api/dataset-api.md`, `docs/04-api/endpoint-catalog.md` — parse, cancel, chunk, ingestion-summary and task-status routes
- `docs/02-frontend/knowledge-base-ui.md`, `components.md`, `pages.md`, `routing.md`, `frontend-data-flow.md`, `document-upload-ui.md` — dataset page, chunk inspector, document viewer, chunking-method dialog

### Security and permissions
- `docs/16-auth/permissions.md`, `docs/16-auth/multi-tenancy.md`, `docs/20-security/file-security.md`

### Project records
- `.planning/ROADMAP.md` (Phase 4 goal, five success criteria, scope notes), `.planning/REQUIREMENTS.md` (ING-01..16, PARSE-01..03, PARSE-09..13, CHUNK-01..02, CHUNK-16..21, IDX-01..03, IDX-07, IDX-14, DOC-09..13, DOC-20..23, KB-14..16, KB-19, UI-13..17, UI-19, DEPLOY-17, TEST-11, E2E-05..06)
- `.planning/DECISIONS.md` (R-11 chunk id scheme, open; R-12 Redis lock; R-136 to R-153 from Phase 3), `.planning/BLOCKERS.md` (B-02, B-31, B-32, B-33 and other open rows)
- `.planning/phases/03-models-knowledge-bases-and-upload/03-CONTEXT.md`, `03-UI-SPEC.md`, `03-VERIFICATION.md`, `03-REVIEW.md` (with `03-REVIEW-backend.md` and `03-REVIEW-web.md`: open warnings in code this phase builds on)

### Reference implementation (read-only, lower priority than docs)
- `/home/logan78/desktop x/ragflow` — `rag/svr/task_executor.py`, `rag/app/naive.py`, `rag/nlp/`, `deepdoc/parser/`, `api/db/services/task_service.py`, `api/db/services/document_service.py`, `rag/utils/redis_conn.py`
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `api/db/models/knowledge.py`: the `Task` model already has `doc_id`, `from_page`, `to_page`, `priority`, `progress`, `progress_msg`, `retry_count`, `digest`, `chunk_ids`, and `MAXIMUM_TASK_PAGE_NUMBER`.
- `api/db/services/llm_service.py` (`LLMBundle`): resolves the dataset's embedding model, checks the expected dimension and records usage; embedders are synchronous and batch at most 16 inputs per provider call.
- `common/doc_store/` and `rag/utils/es_conn.py`: `insert` (refuses a missing index and all-zero vectors), `update`, `delete` by condition, `delete_idx` for one dataset's rows; `index_name(tenant_id)`.
- `rag/utils/storage_factory.py`: `get_storage(settings)`; MinIO `iter_chunks` must be closed.
- `api/db/services/document_service.py`, `knowledgebase_service.py`, `tenant_scope.py`: `load_visible_dataset`, `can_remove_document`, `can_manage_dataset`, the `kb-upload:{dataset_id}` lock, server-owned `doc_num`, `chunk_num`, `token_num` counters.
- `common/ratelimit.py` and the Valkey settings; `common/security/` and `common/log_utils.py` redaction.
- SPA: dataset page and document table with status badge and progress cell, `FileUploadDialog`, confirm dialogs, `use-dataset-permissions` helpers, workspace-keyed query hooks, `Pagination`, `SearchInput`, `ChoiceGroup`.

### Established Patterns
- Handler → service layering with `acting_scope` (404), `forbid_unless` (403), `run_blocking` on bounded executors, `service_error_response`; request models with `extra="forbid"`.
- Routes and permissions are generated from `conf/routes.yaml` and `conf/permissions.yaml` by `scripts/gen_routes.py`; OpenAPI export and TS types are regenerated when routes flip to implemented.
- Sync driver code from a worker thread uses `rag.llm.sync_loop.PrivateLoop`; never bare `asyncio.run` around a driver stream.
- CI gates in `scripts/ci/run_all.py`: no `sleep(` text in tests, no `NotImplementedError` placeholders (use `abc`), secrets scan, decisions check.

### Integration Points
- A new `rag/svr/` task executor process and a compose service for it (the `Dockerfile` already copies `rag/`).
- New Python blueprints for parse, cancel, chunks, ingestion summary and task status under `api/apps/restful_apis`.
- Dataset and document delete (Phase 3) already call the doc store; this phase is the first to put chunks there, so IDX-14 is proven with real chunks.
- The dataset page's document rows gain parse controls, live progress and the error details panel; the chunk inspector and document viewer are new pages.
</code_context>

<specifics>
## Specific Ideas

- The user chose to keep partial chunks searchable after a failure or cancel (D-06), against the recommended "remove them". The "Partly indexed" label (D-07) exists so that choice does not mislead anyone.
- Success criterion 4 in the roadmap says "re-parsing a document leaves an identical chunk count" and "no duplicate chunks" after a worker is killed. With D-06, a retried or reclaimed task and a later re-parse must replace that task's earlier chunks, not add to them.
- Cost matters: parsing is never automatic (D-01), the retry cap is low (D-05), and live test documents are tiny (D-16).
- Safe defaults were preferred throughout, as in Phase 3: confirm before replacing chunks, warn before losing hand edits, refuse an edit that cannot be embedded.
</specifics>

<deferred>
## Deferred Ideas

- Parse-on-upload as a per-dataset setting — considered and not chosen; possible later.
- OCR for scanned PDFs, layout analysis, table structure recognition, proper Markdown and table handling, and the other seven chunkers — Phase 6.
- A "pending" state for chunks whose embedding failed — not chosen (D-11).
- A realistic 50-page live test document — not chosen for this phase (D-16).
- Fixing the remaining Phase 3 code-review warnings that this phase does not touch — `/gsd-code-review 3 --fix`.
</deferred>

---

*Phase: 04-ingestion-pipeline*
*Context gathered: 2026-10-10*
