# Phase 4: Ingestion Pipeline - Pattern Map

**Mapped:** 2026-10-10
**Files analyzed:** about 135 new or modified files (Python production 37, ops and config 14, Python tests 30, frontend 40, generated 6, docs records 8)
**Analogs found:** about 120 with a codebase analog / about 135 total. The 15 without a close one are listed under "No Analog Found".

Scope notes for the planner:
- Every path is relative to `/home/logan78/desktop x/devRag_@` (the path contains a space and `@`; always quote it).
- Phase 3 built most of what Phase 4 copies: `document_api.py`, `dataset_api.py`, `document_service.py`, `knowledgebase_service.py`, `tenant_scope.py`, `handler_support.py`, `service_errors.py`, `blocking.py`, `common/ratelimit.py`, the doc-store port and ES adapter, the storage drivers, `LLMBundle`, the matrix and leak-sweep fixtures, and the dataset page. `rag/svr/`, `rag/parsers/`, `rag/chunking/`, `rag/nlp/`, `rag/queue/` do not exist yet.
- Reference repo `/home/logan78/desktop x/ragflow` is evidence only. `docs/` and the code here win. `04-UI-SPEC.md` names win over `04-RESEARCH.md` for frontend files and folders.

---

## Gotchas (existing tests and gates this phase will trip or must extend)

All verified by reading the code at the lines given, except items marked "unverified".

### Architecture and layering

1. **`rag/` may not import `api.db`, `api.apps` or `quart` (`test/unit_test/test_layering.py:55-57`, `_violations("rag", ("api.apps", "api.db", "quart", ...))`, recursive over `rag/**`).** The task executor (`rag/svr/task_executor.py`, the path `docs/` prescribes) needs Peewee models, `LLMBundle` (`api/db/services/llm_service.py`) and the services. Pick one and record it in `.planning/DECISIONS.md` in the same task that creates `rag/svr/`: (a) keep `rag/parsers`, `rag/chunking`, `rag/nlp`, `rag/queue` pure and carve out only `rag/svr` for `api.db` in the test (keep `api.apps` and `quart` forbidden for it), or (b) put DB-touching orchestration in `api/db/services/*` and give `rag/svr` only Protocols. Recommendation: (a), smallest change, matches the docs path. `common/doc_store` and `common/net` stay forbidden from importing `api`, `rag`, `quart` (`test_layering.py:60-63`), so `StatsResult` lives in `doc_store_base.py`.
2. **Adding `stats` as an abstract method breaks `test/unit_test/test_doc_store_port.py:123-155`.** The `Minimal` subclass implements exactly ten methods and the assertion `names <= DocStoreConnection.__abstractmethods__` lists those ten. Add `stats` to both in the same task. `ESConnection` is the only production subclass. Also add the new cases to `test/helpers/doc_store_contract.py` (class `DocStoreContract`, run by `test/integration/test_doc_store_es.py::TestEsDocStore`).
3. **`scripts/ci/check_placeholders.py` bans, in `api common rag deepdoc agent cmd internal web/src`:** classes named `Fake*`/`Mock*`/`Stub*`, functions `fake_*`/`stub_*`/`mock_*`, `raise NotImplementedError`, `import mock`, and `TODO/FIXME/XXX` comments (`check_placeholders.py:20-23,36-60`). Queue interfaces use `abc.ABC` + `@abstractmethod` (as `rag/utils/storage_base.py` does). Test doubles live under `test/` only. Note `test/helpers/doc_store_contract.py` raises `NotImplementedError` in fixtures; that is allowed only because `test/` is not a production tree.
4. **`scripts/ci/check_secrets.py` (non-test files only):** a quoted literal of any length assigned to an identifier containing `secret|password|passwd|api_key` is a finding (the earlier `SECRET_BULLETS` case), and a quoted literal of 16+ characters with no space assigned to an identifier containing `token` is a finding (`check_secrets.py:33-37`, `TOKEN_MIN_LEN = 16`). Phase 4 risks: a TS map such as `{ tokenTotal: "datasets.ingestion.count.tokenTotal" }`, a Python constant such as `TOKEN_FIELD = "token_num_int_total"`, or a status map keyed `...token...`. Name such constants without `token`, or build the string from parts. Tests (`test/`, `*.test.ts[x]`) are exempt from the generic heuristic; `web/src/locales/` is exempt from it too but still scanned for the default-secret literals.
5. **`scripts/ci/check_decisions.py`:** every `.planning/DECISIONS.md` row has exactly 5 cells and a status of `user-confirmed`, `accepted (auto, not user-reviewed)` or `open`; the word `proposed` anywhere in a row fails (`check_decisions.py:63-66`); `user-confirmed` is legal only for the R-ids hard-coded in `CONFIRMED` (line 21), so new Phase 4 rows are `accepted (auto, not user-reviewed)` even when the user chose them (Phase 3 did the same, `test_phase3_records.py` `STATUS`). R-11 and R-12 are currently `open`; resolving them keeps a legal status. Add a `test/unit_test/test_phase4_records.py` modelled on `test_phase3_records.py` (FIRST_ROW/LAST_ROW, `REQUIRED_TITLES`, one title per row).
6. **`filterwarnings = ["error", ...]` (`pyproject.toml:50-56`) turns every warning into a failure,** including `ResourceWarning`/unraisable exceptions and unhandled thread exceptions (heartbeat thread). Unverified but likely with the new packages: BeautifulSoup `GuessedAtParserWarning` (always pass `"lxml"` or `"html.parser"` explicitly) and `XMLParsedAsHTMLWarning`; `zipfile` `UserWarning: Duplicate name` on crafted archives; unclosed pdfium pages/bitmaps; openpyxl workbooks left open (close read-only workbooks). Close everything in `finally`.
7. **`check_no_sleep.py` scans every test file** (`test/**`, `*.test.ts[x]`, `internal/testutil`) for `sleep(`, `Sleep(` and `setTimeout(` except `test/helpers/wait.py`, `internal/testutil/wait.go`, `web/src/test/wait-until.ts` (`check_no_sleep.py:14-15`). The kill, cancel and poll tests use `wait_until` (`test/helpers/wait.py:9-30`). Production TS (`dataset-files.tsx:96` uses `window.setTimeout`) is not scanned.

### Routes, permissions, isolation

8. **Permission table size is pinned at 12** (`test/unit_test/test_permissions_table.py:85`, plus the oracle `test/fixtures/permission_cases.json` shared with `internal/common/permissions_test.go`). Parse, cancel, chunk writes and switches need no new row: they use `datasets.manage_document` (`conf/permissions.yaml:17`, allows owner, admin, normal, api_token) plus the object rule `tenant_scope.can_remove_document` (D-02, D-10). Do not add a row unless the oracle, the `12` and the Go test change together.
9. **Every new route needs a `conf/routes.yaml` endpoint row and a Nginx-compatible family.** `/api/v1/datasets/` is already a Python prefix with `body_limit: 1m` (`routes.yaml:80`), so all `/api/v1/datasets/{id}/documents/...` routes and `/api/v1/datasets/{id}/ingestions...`, `.../embedding/check` need no family. `/v1/task/status/{task_id}` falls under the `/v1/` catch-all (`routes.yaml:84`, 1024m, `auth: api`). If a new family is added, `test_nginx_limits.py:62-75` (`test_python_owned_locations_have_an_explicit_per_path_body_limit`) fails: it allows only the upload path at 101m, `JSON_FAMILIES` at 1m and everything else at 1024m. Also `test_nginx_limits.py:85-93` requires `proxy_read_timeout >= 3600` on every Python location. Regenerate with `uv run python scripts/gen_routes.py`; drift gate `scripts/ci/check_generated.py`. Add cases to `test/fixtures/route_policy_cases.json`.
10. **Matrix coverage guard fails in both directions** (`test/testcases/_matrix_fixtures.py:817-831`, `coverage_problems`): an `implemented: true` scope-tenant row without a `BUILDERS` entry (path parameters) or `NO_ID_CHECKS` entry fails, and a fixture key matching no implemented row fails. So land rows as `implemented: false`, and flip them in the same plan that adds the handler, the builder and the sweep exerciser. `World.snapshot()` (`_matrix_fixtures.py:190-205`) must also read chunk state (counts and `available`) or the "unchanged after a refused call" check is vacuous for chunk writes. Go twin (`internal/e2e/matrix_fixtures_test.go:88`) reads only `owner: go` rows (R-153): no Go change.
11. **Leak sweep requires a 2xx and a 4xx response for every implemented row** (`test_response_leaks.py:619-634`) and `len(responses) >= 2 * len(rows)`; each exerciser is a `sweep_*_rows(s, w)` function wired into the `sweep` fixture (`test_response_leaks.py:587-615`). Banned response keys: exact `status` and `source` outside system rows, any key matching `password|passwd|pbkdf2|access_token|secret|salt|ticket|otp|...|delete_time`, exact `token`/`beta` outside token rows (`_leak_sweep.py:20-26`). **UI-SPEC planner note 14 names a log-entry field `status`: rename it** (for example `result`). The `document.status` column (search switch) must surface as `enabled`. Key shapes `sk-...` and `v1:<kid>:<b64>` envelopes are banned in any body (`_leak_sweep.py:30-31`), so progress-log lines and chunk text in tests must not contain them. Image and `/content` routes are scanned through `resp.text`.
12. **Document DTO keys are pinned in four places** and `thumbnail` is in `BANNED`: `test/testcases/test_upload_flow.py:30-31,105`, `test/testcases/test_document_flow.py:24-25,76`, `test/integration/test_document_service.py` (`DTO_KEYS`), and the web in-memory server `web/src/test/dataset-server.ts` (`DocumentRow`). `document_dto` (`document_service.py:159-176`) is shared by the upload response and the list, and `list_documents` deliberately selects columns without `thumbnail` and `progress_msg` (`document_service.py:315-318`). UI-SPEC planner note 1 adds `thumbnail`, `chunk_count`, `parseable`, `enabled`, `last_log_id`, `pages_total`, `pages_without_text`, `error`, progress message to list rows: update all four pins and the `BANNED` set in one task, and decide whether the upload response keeps the narrow key set (recommended: a separate `document_row_dto` for the list).
13. **Reason strings are spelled only in `api/utils/reasons.py`** (docstring line 3). Existing relevant: `PARSER_INVALID = "parser_invalid"`, `MODEL_UNAVAILABLE`, `INDEX_UNAVAILABLE`, `DIMENSION_MISMATCH`, `PROVIDER_*`, `STORAGE_UNAVAILABLE`, `BUSY`, `IDS_INVALID`. UI-SPEC uses `parser_config_invalid` and `chunker_unavailable`, `parse_unavailable`, `already_running`, `queue_unavailable`, `parse_running`, `chunk_too_long`, `confirm_required`: add them there and settle `parser_invalid` versus `parser_config_invalid` once. Today `_parser_for` (`document_service.py:117-132`) accepts any of the 14 `PARSER_IDS` (`knowledgebase_service.py:60`), so a dataset can already hold `qa`; D-15 refuses it at parse time and at settings write.
14. **Handlers never import models or peewee** (`test_layering.py:36-38`); services never import `quart`. Read `g.principal` and settings on the loop before `run_blocking` (`document_api.py:231,246`, comment on line 231). A fifth executor (a `PDF_EXECUTOR`) is allowed: `test_handler_support.py:test_four_named_bounded_executors_exist` checks only the four it names, but rename its test to say so.

### Settings, compose and scripts

15. **New `Settings` sections need defaults** (`common/settings.py:227-233` uses `field(default_factory=...)`; `test/helpers/app.py::memory_settings` builds `Settings` with only eight sections). Add an `ingest` section the same way, parse it in `parse_settings` (`settings.py:397-444`), render it in `conf/service_conf.yaml.template`, and extend `test_settings.py` and `test_render_conf.py`. Also add the variables to `docker/.env.example`, to `x-app-env` in `docker/docker-compose.yml` (`test_env_catalog.py:121-141` pattern: every catalogued variable must appear as `  NAME:` in the compose text) and add a `PHASE4_VARIABLES` test.
16. **`Dockerfile:49` copies scripts by name:** `COPY docker/entrypoint.sh docker/entrypoint_init.sh docker/healthcheck.sh docker/prepare_runtime.sh /ragflow/docker/`. A new `docker/entrypoint_task_executor.sh` (and any executor healthcheck script) must be added to that line or it is absent in the image. `COPY rag ./rag` already covers new `rag/*` packages (`test_container_scripts.py:264` pins that line).
17. **New compose service rules:** profile `cpu` (the gate runs `--profile cpu --profile elasticsearch --profile mail` with both files, pinned by `test_clean_room_guard.py:225-230`); `image: ${RAGFLOW_IMAGE:-devrag-app:local}` with `pull_policy: never` and no `build:` (only `init` builds, `docker-compose.yml:72-79`); `restart: unless-stopped`; `environment: *app-env`; no ports; no `container_name` (so `--scale` works). The entrypoint must render the config (`python scripts/render_conf.py --out "$SERVICE_CONF"`, as `entrypoint.sh:12` and `entrypoint_init.sh:8` do) because each container has its own filesystem.
18. **Dev override must give the executor what `app` gets** (`docker/docker-compose.dev.yml:32-43`): `mem_limit` (768m for `app`; D-29 starts the executor at 768m and measures), `extra_hosts: ["host.docker.internal:host-gateway"]` and `LLM_ALLOW_PRIVATE_BASE_URLS: ${DEV_LLM_ALLOW_PRIVATE_BASE_URLS:-true}`. Without them the stack-mode fake provider (`test/helpers/fake_provider.py`, `STACK_HOST = "host.docker.internal"`, line 40) that the non-live parse e2e tests and the web live suite use is unreachable or refused by `common/net/url_guard.py` from the worker. Never copy dev values into `docker-compose.yml`.
19. **Executor log file clash:** `init_root_logger(SERVICE_NAME, log_dir)` writes `<LOG_DIR>/ragflow_server.log` through a `RotatingFileHandler` (`common/log_utils.py:171-180`), and the compose bind `../ragflow-logs:/ragflow/logs` is shared. Give the executor its own logger name (and the consumer id for scaled copies) or log to stdout only.
20. **`scripts/wait_stack.sh:68-84` waits for every non-`init` service** of the project: it must be `healthy`, or have no healthcheck and be `running`. A new executor is therefore waited for automatically; give it a healthcheck (heartbeat key age) so a crash loop is caught, and add a `test_container_scripts.py` case for the evaluate function with the new service row. With `--scale task-executor=2` the snapshot has two rows with one service name (`wait_stack.sh:52-64`).
21. **Gate step order is pinned:** `test_clean_room_guard.py:255-259` requires `live-model` immediately after `e2e-serial` and immediately before `go-race`; `:262-264` pins the exact `live-model` command. Kill, cancel and poison tests ride on the existing `e2e and serial` step; the live ingestion test on `live_model`. Do not insert a new step between those two. The gate script must never name `OPENROUTER` (`:267-270`).
22. **Memory:** `docker-compose.dev.yml` limits sum to about 4.6 GB with an executor at 768m; `scripts/preflight.sh:21` `MIN_RAM_MB=4096`; `scripts/record_memory.py:18` `BUDGET_MIB = 3891` compares measured use; `--record` rewrites the "Dev memory budget (measured)" section of `DECISIONS.md`. D-29: measure with the 13-page PDF and the 40-chunk text file and lower the limit if the measurement allows. The embedding path imports `openai` lazily (`rag/llm/embedding_model.py:264`) and `litellm` only inside the chat driver (`rag/llm/chat_model.py:59`), so the worker does not pay the roughly 200 MB `litellm` import.
23. **Valkey is configured as a cache, not a queue:** `docker/docker-compose-base.yml:39` runs `valkey-server --maxmemory 128mb --maxmemory-policy allkeys-lru` (dev limit 160m, `docker-compose.dev.yml:19-20`), with no AOF. Under `allkeys-lru` the `te.*` streams, `lock:task_*` keys and heartbeat keys are evictable, and a Valkey restart (`test/testcases/test_dependency_outage.py:57-71` stops `redis`) drops pending entries. Decide and record one of: change the policy to `noeviction`/`volatile-lru` for this deployment, and/or add a reconciliation (a document at `run = '1'` with no live task message is re-enqueued or failed `worker_lost`). The executor must survive the outage: reconnect, recreate the group on `NOGROUP`, never exit.

### Tests and fixtures that need extending

24. **`test/helpers/accounts.py::delete_accounts`** (`accounts.py:108-145`) deletes `file2document`, `document`, `file`, `knowledgebase` for a tenant but **not `task` rows or `pipeline_operation_log` rows**. Extend `_delete_dataset_rows` by recorded tenant only: `DELETE FROM task WHERE doc_id IN (SELECT id FROM document WHERE kb_id IN (SELECT id FROM knowledgebase WHERE tenant_id = %s))` before the document delete, and `DELETE FROM pipeline_operation_log WHERE tenant_id = %s`. `delete_tenant_artifacts` already drops the ES index and MinIO prefix, so chunks and blobs are cleaned. `test/unit_test/test_account_helpers.py` does not pin the statement list (checked).
25. **Production delete paths leave log rows behind:** `file_service.release_files` deletes `Task` rows (`file_service.py:166`) but nothing deletes `PipelineOperationLog` rows per document; only the dataset delete does, by `kb_id` (`knowledgebase_service.py:629`). Add the per-document delete inside `release_files` or `_remove_rows` (same transaction) and test it.
26. **`document_service.delete_documents` prunes the index first, then rows** (`document_service.py:372-377` then `:379-392`). A worker inserting between those steps leaves orphan chunks. The stale-worker guard (re-read the task row after each insert, delete by `task_id` if gone) is mandatory, and the delete route needs a test with a running task.
27. **`BaseModel.save()` stamps `update_time`; `Model.update(...).execute()` does not** (`api/db/models/base.py:60-70`). Existing services stamp by hand (`document_service.py:277-278`). Task and document updates from the worker should stamp or deliberately not.
28. **`test/testcases/conftest.py:17-32`:** `compose()` always uses `-f docker-compose.yml -f docker-compose.dev.yml --profile cpu` and takes `extra_files`. The kill-test override (small `INGEST_BATCH_SIZE`, short lock and reclaim times) is a third compose file applied by the test itself (`compose("up", "-d", "--no-deps", "task-executor", extra_files=(...))`), then restored. `clean_room.sh:56` does not include it.
29. **`test_live_models.py:1-17,85-98` rules for the live tier:** key read only through `stack_env()`, fixed failure message when absent (no skip), nothing printed, budgets counted. `test_clean_room_guard.py:279-291` also checks the live file for the fixed message and no skip, and that the tier fails without the key; a new `test_live_ingestion.py` should copy the header and the `live_env` fixture.
30. **Redaction affects user-facing progress text.** Progress messages and log lines are passed through `redact_text` before they are stored (UI-SPEC note 16, D-23). The key/value scan masks the value after any word containing `token`, `key`, `secret`, `password`, `cookie`, `otp`, `ticket`, `beta` followed by `:` or `=` (`log_utils.py:13-14,20-22`, `_is_sensitive`). A line such as `token_num: 480` becomes `token_num: ***`. Write progress lines without those words before a colon or equals sign. In `extra=` dicts any key containing `token` is masked (R-149; use `usage_total`). BE-08 (`log_utils.py:121-130`): `redact_value` skips non-string values, so pass `type(exc).__name__` strings, not exception objects, until the one-branch fix lands (D-31).

### Frontend

31. **Route list and nav are pinned:** `web/src/layouts/layouts.test.tsx:248-249` lists the exact 12 route paths (add `/dataset/logs`, `/chunk`, `/document` there), `layouts.test.tsx:106` and `components/shell-i18n.test.tsx:55-56` pin 7 nav entries (no nav entry is added in Phase 4), `NESTED_PREFIXES` in `components/app-sidebar.tsx:15` is `{ "/datasets": ["/dataset/"] }` matched by `startsWith`, so `/dataset/logs` is already covered but `/chunk` and `/document` need entries matched as exact or followed by `/` (UI-SPEC "Routes").
32. **`ui/sheet.tsx` is the left navigation drawer** (`fixed inset-y-0 left-0 ... border-r ... slide-in-from-left`, close label `nav.closeMenu`, lines 30-52). The right-hand details sheet needs a `side` variant or a className override that keeps the default for the nav tests.
33. **`ui/choice-group.tsx` has only a group-level `disabled`** (lines 11-19) and no per-option disabled or badge; extend with defaults that keep current behaviour (Create dataset uses it). `ui/switch.tsx`, `ui/checkbox.tsx`, `ui/segmented-control.tsx` do not exist. `ui/alert.tsx` already has `variant="info"` (`role="status"`), `ui/progress.tsx`, `ui/pagination.tsx`, `ui/search-input.tsx`, `ui/textarea.tsx` exist.
34. **`useDocumentsRequest` has no `placeholderData: keepPreviousData` and no `refetchInterval`** (`hooks/use-document-request.ts:43-52`) (FE-01). Keep the key shapes: `documentsQueryKey` is asserted in `hooks/use-document-request.test.tsx:60-62` and invalidation relies on `documentsKeyRoot` prefix.
35. **`dataset-files.tsx:20` `COLUMNS` drives header text through `datasets.files.col.${column}`** and `document-row.tsx:25-27` `percentOf` rounds (`Math.round`); FE-18 requires floor and a 99 cap while `run === "1"`. Phase 3 tests that assert "0%" and "Not started" must keep passing.
36. **`DatasetDetailView` has no `parserConfig`** (`services/dataset-service.ts:36-47`) although the API already returns `parser_config` (`knowledgebase_service.py:379`). The default chunking dialog needs it; extend the mapper and `services/mappers.test.ts`.
37. **`services/http.ts` for blob routes:** default timeout 10 s (`TIMEOUT_MS`, line 29), per-request `timeout` is honoured. With `responseType: "blob"` an error body arrives as a `Blob`, so the failure interceptor's `isEnvelope` check fails and the `ApiError` has `code -1` and no `data.reason` (`http.ts:216-232`): image, content and download errors are classified by status only. `safeMessage` caps toast text at 160 characters (`MAX_MESSAGE_LENGTH`, line 30); UI-SPEC allows 300 for inline server text, which the page's own `errors.ts` must bound.
38. **No-hardcoded-copy scan** (`web/src/constants/no-hardcoded-copy.test.ts:44-67`): over `pages/`, `components/`, `layouts/` it flags JSX text with a letter, text-bearing attributes (`title|description|aria-label|placeholder|alt|label|heading|body|actionLabel`) set to a literal, and any English locale value of 5+ characters (largest piece after removing `{{x}}`) that appears as a string literal, case-sensitive and followed by a non-word character. New values that collide with ordinary words: `Table`, `Paper`, `Manual`, `General`, `Parse`, `Parsing`, `Details`, `Finished`, `Failed`, `Chunk ...`. Keep method ids (`"naive"`, `"paper"`, lowercase) and status codes in `hooks/`, `services/`, `constants/`, which the scan does not read. Locale keys must not start with `documents.` or `document.` (R-151), and no key is both a string and a parent. `locales/locales.test.ts` enforces identical key sets in `en.json` and `zh.json`, no empty values, same placeholders.
39. **`git diff --stat -- web/package.json web/package-lock.json` must stay empty** (D-21, D-24; UI-SPEC Test Hooks). No `react-pdf-highlighter`, `pdfjs-dist`, `@tanstack/react-table`, Radix switch/checkbox/tabs.
40. **FE-02: workspace binding.** The inspector, viewer and log pages must not send workspace-scoped requests until the store is initialised and bound to the dataset's workspace. `pages/dataset/index.tsx:48-78` holds the working pattern (`boundTenantRef`, `initialised`, `bindActive`); extract and reuse it rather than writing a second variant.

---

## File Classification

### Python: queue, executor, parsers, chunkers (new)

| New/Modified File | Role | Data Flow | Closest Analog | Match |
|---|---|---|---|---|
| `rag/queue/queue_base.py` | interface | pub-sub | `rag/utils/storage_base.py` (ABC, typed errors) | role-match |
| `rag/queue/valkey_streams.py` | service | pub-sub | `common/ratelimit.py` (Valkey client, fail-closed errors) | partial |
| `rag/svr/task_executor.py` | entry process | event-driven | `api/ragflow_server.py` | role-match |
| `rag/svr/executor_loop.py` | service | event-driven, batch | none; ordering from `document_service.py` delete flow | partial |
| `rag/svr/task_lock.py` | utility | request-response | `api/db/database.py::DatabaseLock` | role-match |
| `rag/svr/progress.py` (roll-up daemon) | service | batch | `document_service.py::_remove_rows` (transaction, deadlock retry) | partial |
| `rag/svr/cancel.py`, heartbeat thread | utility | event-driven | none | none |
| `rag/parsers/types.py` (`ParsedBlock`) | model | transform | `api/db/services/upload_rules.py::ValidatedFile` | partial |
| `rag/parsers/router.py` | utility | transform | `rag/llm/__init__.py` registry + `upload_rules.file_type_for` | role-match |
| `rag/parsers/limits.py` (`check_ooxml_limits`) | utility | transform | `api/db/services/upload_rules.py` | role-match |
| `rag/parsers/pdf.py` | service | file-I/O, transform | none (RESEARCH spiked pypdfium2) | none |
| `rag/parsers/{docx,xlsx,pptx,html,txt}.py` | service | file-I/O, transform | none | none |
| `rag/chunking/types.py` (`Chunk`) | model | transform | `rag/parsers/types.py` (same pattern) | partial |
| `rag/chunking/naive.py` | service | transform | none | none |
| `rag/chunking/factory.py` | utility | transform | `rag/llm/__init__.py::resolve_provider` | role-match |
| `rag/nlp/tokenizer.py`, `normalize.py` | utility | transform | `rag/llm/embedding_model.py` (tiktoken use) | partial |
| `api/db/services/task_service.py` | service | CRUD | `api/db/services/document_service.py` | role-match |
| `api/db/services/ingestion_service.py` | service | CRUD | `document_service.py` + `knowledgebase_service.py` | role-match |
| `api/db/services/chunk_service.py` | service | CRUD, request-response | `document_service.py` + `rag/utils/es_conn.py` | role-match |
| `api/db/services/totals_service.py` | service | CRUD | `document_service.py::_remove_rows` | role-match |
| `api/apps/restful_apis/parse_api.py` | controller | request-response | `document_api.py` (delete handler) | exact |
| `api/apps/restful_apis/chunk_api.py` | controller | CRUD | `document_api.py`, `dataset_api.py` | exact |
| `api/apps/restful_apis/ingestion_api.py` | controller | request-response | `document_api.py::list_documents` | exact |
| `api/apps/restful_apis/page_api.py` (image, content, thumbnail) | controller | file-I/O | `document_api.py::upload_documents` (non-JSON) | partial |

### Python: modified

| File | Change | Analog | Match |
|---|---|---|---|
| `common/doc_store/doc_store_base.py` | `stats` method, `StatsResult` | same file | exact |
| `rag/utils/es_conn.py` | `stats`, BE-06 query escaping, BE-13 vector-mapping check, html highlight encoder | same file | exact |
| `common/log_utils.py` | BE-08 non-string values | same file | exact |
| `api/db/services/document_service.py` | list/detail DTO, ParserConfig (BE-09), delete log rows | same file | exact |
| `api/db/services/knowledgebase_service.py` | ParserConfig validation, summary counts | same file | exact |
| `api/db/services/file_service.py` | delete `pipeline_operation_log` rows per document | same file | exact |
| `api/utils/reasons.py`, `api/utils/blocking.py` | new reasons, `PDF_EXECUTOR` | same files | exact |
| `api/apps/__init__.py` | register four blueprints | same file lines 50-62 | exact |
| `common/settings.py`, `conf/service_conf.yaml.template` | `IngestSettings` | `UploadSettings` / `upload:` block | exact |
| `conf/routes.yaml` | endpoint rows | same file lines 138-172 | exact |
| `pyproject.toml`, `uv.lock` | seven approved packages + `charset-normalizer` direct | same file | exact |

### Ops and records

| File | Role | Closest Analog | Match |
|---|---|---|---|
| `docker/docker-compose.yml` (`task-executor` service) | config | `init`/`app` services lines 72-119 | exact |
| `docker/docker-compose.dev.yml` | config | `app` block lines 32-43 | exact |
| `docker/docker-compose.test.yml` (kill-test override, name is the planner's) | config | dev file | role-match |
| `docker/entrypoint_task_executor.sh` | config | `docker/entrypoint.sh`, `entrypoint_init.sh` | exact |
| `docker/healthcheck_task_executor.sh` | config | `docker/healthcheck.sh` | role-match |
| `Dockerfile` (COPY line 49) | config | same file | exact |
| `docker/.env.example` | config | same file | exact |
| `scripts/wait_stack.sh`, `scripts/record_memory.py`, `scripts/preflight.sh` | config | same files | exact |
| `.planning/DECISIONS.md`, `REQUIREMENTS.md`, `ROADMAP.md` | records | `test_phase3_records.py` contract | role-match |
| generated: `api/apps/route_policy_gen.py`, `internal/common/route_policy_gen.go`, `docker/nginx/ragflow*.conf`, `web/src/constants/api-routes.generated.json`, `web/openapi/openapi.json`, `web/src/interfaces/openapi.d.ts` | generated | `uv run python scripts/gen_routes.py`, `scripts/export_openapi.py`, `npm run gen:api`; never hand-edit | n/a |

### Python tests (new unless marked "extend")

| File | Tier | Closest Analog | Match |
|---|---|---|---|
| `test/unit_test/test_task_split.py`, `test_pdf_parser.py`, `test_parsers.py`, `test_naive_chunker.py`, `test_queue_message.py` | unit | `test/unit_test/test_upload_rules.py` | role-match |
| `test/integration/test_queue.py`, `test_task_lock_reclaim.py` | integration (real Valkey) | `test/integration/test_ratelimit.py` | exact |
| `test/integration/test_rollup.py`, `test_chunk_service.py`, `test_indexing.py` | integration (real MySQL, ES) | `test/integration/test_document_service.py`, `test_doc_store_es.py` | exact |
| `test/testcases/test_parse_flow.py`, `test_ingestion_api.py` | e2e | `test/testcases/test_document_flow.py` | exact |
| `test/testcases/test_ingestion_failure.py` | e2e serial | `test/testcases/test_dependency_outage.py` | role-match |
| `test/testcases/test_live_ingestion.py` | live_model | `test/testcases/test_live_models.py` | exact |
| `test/helpers/ingest.py` | helper | `test/helpers/uploads.py` (PDF generator has no analog) | partial |
| `test/unit_test/test_phase4_records.py`, `test_phase4_traceability.py` | unit | `test_phase3_records.py`, `test_phase3_traceability.py` | exact |
| extend: `_matrix_fixtures.py`, `test_cross_tenant_matrix.py`, `_leak_sweep.py`, `test_response_leaks.py`, `test_doc_store_port.py`, `doc_store_contract.py`, `test_layering.py`, `test_env_catalog.py`, `test_settings.py`, `test_render_conf.py`, `test_container_scripts.py`, `test_route_policy.py` fixtures, `test_upload_flow.py`, `test_document_flow.py`, `test_document_service.py`, `accounts.py`, `test_spa_browser.py` | mixed | same files | exact |

### Frontend (`web/src`)

| File | Role | Closest Analog | Match |
|---|---|---|---|
| `services/document-service.ts` (extend), `services/chunk-service.ts`, `services/ingestion-service.ts` | service | `services/document-service.ts`, `dataset-service.ts` | exact |
| `constants/api-paths.ts` (extend) | config | same file `datasetDocumentsPath` | exact |
| `hooks/use-document-request.ts` (extend), `hooks/use-chunk-request.ts` | hook | `hooks/use-document-request.ts` | exact |
| `hooks/use-dataset-permissions.ts` (`canChangeDocument`) | hook | same file | exact |
| `pages/dataset/document-row.tsx`, `document-status-badge.tsx`, `dataset-files.tsx`, `errors.ts` (extend) | component | same files | exact |
| `pages/dataset/{document-row-actions,selection-bar,ingestion-summary,reparse-dialog,parsing-details-sheet}.tsx` | component | `components/delete-document-dialog.tsx`, `dataset-actions-menu.tsx` | role-match |
| `pages/dataset/logs/index.tsx` | page | `pages/dataset/index.tsx` + `dataset-files.tsx` | role-match |
| `pages/chunk/{index,chunk-card,chunk-editor,chunk-list,discard-dialog}.tsx` | page, component | `pages/dataset/index.tsx`, `components/dataset-settings-dialog/settings-form.tsx` | role-match |
| `pages/document-viewer/index.tsx` | page | `pages/dataset/index.tsx` | role-match |
| `components/chunk-method-dialog/*`, `components/parse-configuration/*` | component | `components/dataset-settings-dialog/*` | role-match |
| `components/document-preview/{page-preview,text-preview}.tsx` | component | none | none |
| `components/ui/{switch,checkbox,segmented-control}.tsx` | component | `ui/native-select.tsx`, `ui/choice-group.tsx` | role-match |
| `components/ui/{choice-group,sheet}.tsx` (extend) | component | same files | exact |
| `constants/routes.ts`, `components/app-sidebar.tsx` (extend) | config | same files | exact |
| `locales/en.json`, `locales/zh.json` | config | same files | exact |
| `test/dataset-server.ts` (extend), `*.test.tsx`, `*.live.test.ts` | test | `dataset-files.test.tsx`, `dataset.live.test.ts`, `use-document-request.test.tsx` | exact |

---

## Pattern Assignments

### `api/apps/restful_apis/parse_api.py`, `chunk_api.py`, `ingestion_api.py` (controller, request-response)

**Analog:** `api/apps/restful_apis/document_api.py` (list and delete handlers) and `dataset_api.py` (update handler).

**Imports and blueprint** (`document_api.py:29-50`):
```python
from __future__ import annotations
from pydantic import BaseModel, ConfigDict
from quart import Blueprint, Response, current_app, g, request
from quart_schema import document_response, validate_request
from api.apps.service_errors import service_error_response
from api.db.services import document_service
from api.db.services.service_errors import Kind, ServiceError
from api.utils import reasons
from api.utils.api_utils import json_result
from api.utils.blocking import DB_EXECUTOR, STORAGE_EXECUTOR, run_blocking
document_bp = Blueprint("document", __name__)
DOCUMENTS = "/api/v1/datasets/<dataset_id>/documents"   # Quart spells <name>, the registry {name}
```

**Mutating handler shape** (`document_api.py:242-257`): request model with `extra="forbid"`, authorise first, then the blocking call on a bounded executor with an explicit timeout, then map `ServiceError`:
```python
@validate_request(DeleteDocumentsBody)
@document_response(DeletedEnvelope, 200)
async def delete_documents(dataset_id: str, data: DeleteDocumentsBody) -> Response:
    try:
        settings = _settings()  # read here, on the loop
        principal = g.principal
        visible = await run_blocking(DB_EXECUTOR, document_service.authorize_removal, principal, dataset_id, timeout=AUTHORIZE_TIMEOUT_SECONDS)
        ids = list(data.ids)
        deleted = await run_blocking(STORAGE_EXECUTOR, lambda: document_service.delete_documents(settings, visible, principal.user_id, ids), timeout=DELETE_TIMEOUT_SECONDS)
        return json_result({"deleted": deleted})
    except ServiceError as exc:
        return service_error_response(exc)
```
Registration (`document_api.py:260-262`): `bp.add_url_rule(PATH, endpoint=..., view_func=..., methods=[...])`; constants identical to the registry rows.

**Per-route notes**
- Parse/cancel (`POST .../documents/parse`, body `{doc_ids, run, confirm_replace?}`): `doc_ids` 1..100 validated by the service like `_clean_ids` (`document_service.py:335-345`, `IDS_INVALID`). Use `DOCSTORE_EXECUTOR` (as `create_dataset`, `dataset_api.py:188`) because a re-parse prunes the index before creating tasks (D-03). All-or-nothing: run every permission, visibility, parseability and chunker check for every id before any state change (UI-SPEC note 3).
- 409 `confirm_required` carries counts through `ServiceError(Kind.CONFLICT, reasons.CONFIRM_REQUIRED, "...", data={"documents": [...]})`; `service_error_response` merges `data` after `reason` (`service_errors.py:47-48`).
- Query parsing helper `_whole(name, default, low, high)` (`document_api.py:214-220`) for `page`/`size`; keywords capped at `MAX_KEYWORDS = 128` (`:64`). Chunk `keywords` must survive `what is (revenue` (BE-06).
- Chunk write routes refuse with 409 `parse_running` while `document.run == '1'`; edit/add embed first through `LLMBundle.encode` in `PROVIDER_EXECUTOR` (45 s handler timeout, the driver's own limit is 30 s) and write only on success (D-11).
- Permission: `allowed(visible.scope.subject, "datasets", "manage_document")` then `can_remove_document(doc.created_by, dataset.created_by, user_id, scope.subject)` exactly as `document_service.delete_documents` does (`document_service.py:362-371`). The subject, never the role, so an API token is not elevated.

**Dataset default chunking write:** `dataset_api.update_dataset` (`:226-240`) already takes `parser_id`/`parser_config`; use `forbid_unless(visible.scope, AREA, MANAGE)` and `knowledgebase_service._require_manage` (`knowledgebase_service.py:430-434`). The per-document settings write has no route in `docs/` or RESEARCH: choose one (for example `PATCH /api/v1/datasets/{dataset_id}/documents/{doc_id}`) and record it (UI-SPEC checker flag 13).

---

### `api/db/services/{task,ingestion,chunk,totals}_service.py` (service, CRUD)

**Analog:** `api/db/services/document_service.py` and `knowledgebase_service.py`.

**Authorisation and visibility** (`document_service.py:94-110`, `knowledgebase_service.py:348-359`, `tenant_scope.py:114-125`):
```python
def authorize_upload(principal: Principal, dataset_id: str) -> VisibleDataset:
    visible = load_visible_dataset(principal, dataset_id)      # the one NOT_FOUND
    if not allowed(visible.scope.subject, AREA, MANAGE_DOCUMENT):
        raise ServiceError(Kind.FORBIDDEN, reasons.FORBIDDEN, "forbidden")
    return visible

def can_remove_document(document_creator_id, dataset_creator_id, caller_id, role) -> bool:
    if not caller_id: return False
    return document_creator_id == caller_id or can_manage_dataset(dataset_creator_id, caller_id, role)
```
Add `authorize_parse`/`authorize_chunk_write` that call these (one rule, two names, as the frontend does with `canChangeDocument`).

**Named lock, transaction, deadlock retry** (`knowledgebase_service.py:437-450`, `document_service.py:398-424`):
```python
@contextmanager
def _named_lock(name: str, timeout: int, busy_message: str) -> Iterator[None]:
    lock = DatabaseLock(name, timeout)
    try: lock.acquire()
    except (LockTimeoutError, LockError):
        raise ServiceError(Kind.UNAVAILABLE, reasons.BUSY, busy_message) from None
    try: yield
    finally:
        try: lock.release()
        except LockError: logger.warning("lock was not held at release name=%s", name)
```
```python
for attempt in range(1, DEADLOCK_ATTEMPTS + 1):
    try:
        with transaction():
            locked = list(Document.select(...).where(Document.id.in_(wanted)).order_by(Document.id).for_update())
            ...
        return freed
    except peewee.OperationalError as exc:
        if exc.args and exc.args[0] == _MYSQL_DEADLOCK and attempt < DEADLOCK_ATTEMPTS:
            continue
        raise
```
Use for: creating task rows + `pipeline_operation_log` row + `document.run='1'` in one transaction, then `XADD` after commit (a failed enqueue is 503 `queue_unavailable` and must leave nothing running: roll the state back or enqueue inside a compensating block). Lock name `kb-upload:{dataset_id}` (`upload_lock_name`, 42 characters) serialises with uploads and deletes; names are capped at 64 (`database.py:35,185-187`).

**Counters set to truth** (RESEARCH Pattern 5) copy the guarded update from `_remove_rows` (`document_service.py:411-417`): `peewee.fn.GREATEST(Knowledgebase.chunk_num + delta, 0)` with `update_time=now, update_date=timestamp_to_date(now)` stamped by hand (Gotcha 27), after `SELECT ... FOR UPDATE` on the document row.

**Typed errors, no secrets in messages** (`service_errors.py:15-40`): `ServiceError(kind, reason, message, retry_after=None, data=None)`; `__str__` returns only the reason. Failure objects stored for the UI (`{step, code, message}`) are built from typed codes, never from `str(exc)`.

**DTO whitelisting** (`document_service.py:159-176`): list keys explicitly so a new column never reaches a client unreviewed. `thumbnail` is an exposed key only in the list DTO and only as a `data:image/...;base64,` value of about 16 KB at most.

**Provider failures** reuse `LLMBundle` (`llm_service.py:102-112`, `bundle_error`): refusal is `Kind.INVALID`/`provider_refused` (400, never 401), timeout `Kind.TIMEOUT` (504), unreachable `Kind.BAD_GATEWAY` (502), rate limit `Kind.UNAVAILABLE` (503).

---

### `rag/svr/task_executor.py` (entry process, event-driven)

**Analog:** `api/ragflow_server.py` (boot order, signal handling, exit codes).

**Boot and verification** (`ragflow_server.py:58-71,93-107`): `init_database(settings.mysql)`, `SELECT 1`, require `current_version() >= 1`, wrap failures in a `BootError` carrying only `type(exc).__name__` (driver messages can hold host details). The executor does no DDL and does not seed.
```python
def verify_database(settings: Settings) -> None:
    hint = "run `python -m api.db.init_db` first"
    try:
        init_database(settings.mysql)
        with DB.connection_context():
            DB.execute_sql("SELECT 1")
            version = current_version()
    except (peewee.PeeweeException, pymysql.MySQLError) as exc:
        raise BootError(f"database is not ready ({type(exc).__name__}); {hint}") from exc
```

**Signals and exit** (`ragflow_server.py:110-139`): `loop.add_signal_handler(sig, stop.set)` for SIGINT/SIGTERM inside `contextlib.suppress(NotImplementedError)`; `main()` returns 1 on `BootError`/`ConfigError`, closes `DB` in `finally`. The executor is synchronous: use `signal.signal` plus a `threading.Event` set by the handler (stop taking messages, finish the batch, release the lock, refund the attempt per RESEARCH Pattern 3). Entry command `python -m rag.svr.task_executor`.

**Logging:** `init_root_logger(<own name>, settings.logging.dir or None, settings.logging.level)` (Gotcha 19).

**Connections:** open `DB.connection_context()` per short operation and never hold one across the embedding call (ING-15; `DB` is a pooled `RetryingPooledMySQLDatabase`, `database.py:74-83`; writes are never retried by the pool, R-83, so progress writes tolerate failure).

---

### `rag/svr/task_lock.py` (utility)

**Analog:** `api/db/database.py::DatabaseLock` (lines 182-243) for the acquire/holds/release/context-manager shape, but the backing store is Valkey (`valkey.lock.Lock`, owner token, compare-and-delete release, `reacquire`, spiked in RESEARCH).
```python
class DatabaseLock:
    def __init__(self, lock_name: str, timeout: int = 10) -> None: ...
    def acquire(self) -> None: ...        # raises LockTimeoutError / LockError
    def holds_lock(self) -> bool: ...
    def release(self) -> None: ...        # raises LockError when not held
    def __enter__(self) -> DatabaseLock: ...
    def __exit__(self, *exc_info: object) -> None: ...
```
Mirror those names and the two typed errors so callers read alike; a lost lock sets an event that cancels the task.

---

### `rag/queue/queue_base.py`, `rag/queue/valkey_streams.py` (interface and implementation)

**Interface analog:** `rag/utils/storage_base.py:22-31,59-72`: an `abc.ABC` with `@abstractmethod`s, plus typed errors whose messages never hold keys.
```python
class StorageError(Exception):
    """A storage operation failed or was refused. The message never contains a key, path or credential."""
class Storage(ABC):
    @abstractmethod
    def put(self, bucket: str, key: str, data: bytes | BinaryIO, length: int | None = None) -> None: ...
```
**Factory analog:** `rag/utils/storage_factory.py:19-43` (cached per connection tuple under a lock, driver imported lazily, `reset_*_cache()` for tests).

**Valkey client analog:** `common/ratelimit.py:35-58`:
```python
def _client(self) -> valkey.Valkey:
    rd = self._redis
    return valkey.Valkey(host=rd.host, port=rd.port, password=rd.password or None, db=rd.db,
                         socket_timeout=SOCKET_TIMEOUT_SECONDS, socket_connect_timeout=SOCKET_TIMEOUT_SECONDS)
...
except (ValkeyError, OSError):
    raise RateLimitUnavailable("rate limit store unavailable") from None
finally:
    client.close()
```
Copy: settings-driven construction (`settings.redis`), explicit timeouts, translate `ValkeyError`/`OSError` into a typed `QueueUnavailable` without the host. Differences: a blocking `XREADGROUP block=` needs `socket_timeout` larger than the block time; the executor keeps one long-lived client, the API enqueue path may use a per-call client like the limiter. In valkey-py 6.1.1 call `xautoclaim` without `justid` (RESEARCH Pitfall 2). Queue names `te.{priority}.common`, group name per `docs/10-cache-and-queues/queues.md`; message body only `{task_id, digest}`.

---

### `api/db/services/chunk_service.py`, `rag/svr/executor_loop.py` indexing step (doc store use)

**Analog:** `rag/utils/es_conn.py` and `common/doc_store/doc_store_base.py`.

**Calls and scoping** (`es_conn.py:213-235,252-275`): `insert(rows, index_name(tenant_id), dataset_id)` forces `kb_id`, refuses a missing index and a zero or wrong-length vector (`check_row_vectors`, `doc_store_base.py:144-149`), bulk-indexes with `_id = row["id"]` and refreshes once per call; `update(condition, new_value, ...)` is an `update_by_query` with a painless loop over `new_value` and refuses `id`/`kb_id`; `delete(condition, ...)` returns the deleted count; empty conditions are refused (`require_condition`, `doc_store_base.py:111-115`); condition keys match `[A-Za-z0-9_]{1,64}`.
```python
def _filter_clauses(condition, dataset_ids):
    validate_condition_keys(condition)
    clauses = [{"terms": {"kb_id": list(dataset_ids)}}]
    for key, value in condition.items():
        if isinstance(value, (list, tuple, set)): clauses.append({"terms": {key: list(value)}})
        elif isinstance(value, (str, int, float, bool)): clauses.append({"term": {key: value}})
        else: raise InvalidFilter("invalid condition value")
    return clauses
```
**New `stats` (port + adapter):** add to `DocStoreConnection` next to `delete` (`doc_store_base.py:259-261`) and a frozen `StatsResult(count, total)` beside `SearchResult` (`:206-212`). In the adapter reuse `_guard("stats")` (`es_conn.py:62-71`), `_filter_clauses`, `validate_single_index`, `require_dataset_id`; body `size=0`, `track_total_hits=True`, a `sum` aggregation on a validated field name (`FIELD_RE`).

**Dynamic templates already map the new fields** (`rag/utils/es_mapping.py:30-59`): `*_int` integer (`order_int`, `token_num_int`, `available_int`, `position_int`), `*_id` keyword via the `kwd` regex (`task_id`), `*_kwd` keyword (`origin_kwd`, `docnm_kwd`), `*_ltks` whitespace text, `*_with_weight` stored text not indexed (`content_with_weight`). No mapping change; verify with a Wave 0 test that `position_int` as nested arrays round-trips in `_source` (RESEARCH A1, unverified).

**Chunk ids:** parsed `doc_id_{from_page*1000+i}` (grammar `^[0-9a-f]{32}_[0-9]+$`), manual `doc_id_m_{uuid4hex}`. Ids are unique per workspace index, so a chunk id from another dataset cannot collide (BE-13 note about `_id` overwrite); validate chunk ids in paths against these two grammars before any lookup and always pass the dataset id.

**BE-06 (take it in this phase, D-31):** `_text_query` (`es_conn.py:112-121`) sends `matching_text` raw into `query_string`. Escape reserved characters in the adapter, set `allow_leading_wildcard: False`, `analyze_wildcard: False`, and tokenise the keyword with the same tokenizer as `content_ltks`. Add contract cases for `what is (revenue` and `*a*b*`.

**BE-13 (take it, D-31):** `insert` must check that a `q_{dim}_vec` field present in a row is mapped (`get_field_mapping`, cache per index) or an unmapped vector is silently dynamic-mapped as float; add `"encoder": "html"` to highlight; validate `order_by` field names with `FIELD_RE`; map `DimensionConflict` to 409 not 503.

**D-26 document switch vs chunk switch:** `update` rewrites listed fields on every matching row. Keep `available_int` as the chunk's own switch and add a separate per-chunk field for the document-level flag (for example `doc_enabled_int`), updated by `{"doc_id": [d]}`; the retrieval filter ANDs both. RESEARCH Pattern 6 (turn every chunk on at re-enable) is overruled by D-26 and UI-SPEC checker flags.

---

### `rag/svr/executor_loop.py` embedding step

**Analog:** `api/db/services/llm_service.py` and `rag/llm/embedding_model.py`.

**Build once, call from a worker thread** (`llm_service.py:130-159,279-288`):
```python
bundle = LLMBundle(tenant_id, dataset.embd_id, "embedding", settings=settings, expected_dimension=dimension)
vectors, _tokens = bundle.encode(texts)      # raises ServiceError(provider_*, model_unavailable, dimension_mismatch)
```
- Construction reads one credential row: build it from the same worker thread, outside a `DB.connection_context()` you hold open across the call.
- The driver already splits into provider calls of `BATCH_SIZE = 16`, cuts input at `TOKEN_CEILING = 8191` and replaces empty text (`embedding_model.py:47-48`); the pipeline batch of 64 is the worker's own (RESEARCH Pattern 7). Drop empty chunks before embedding; fail terminal on a zero vector.
- Usage is recorded by the bundle (`tenant_llm.used_tokens`) and logged with `usage_log_fields` (no field name contains `token`).
- Map `ServiceError.reason` to the retry classification: `model_unavailable`, `dimension_mismatch`, `provider_refused` are terminal; `provider_timeout`, `provider_rate_limited`, `provider_unreachable` retry.
- **Cancel-aware wait for a blocking call:** submit the batch to a dedicated embed `ThreadPoolExecutor` and poll `concurrent.futures.wait([future], timeout=0.5)`; same bounded-pool idea as `api/utils/blocking.py:24-27`. `rag.llm.sync_loop.PrivateLoop` (`sync_loop.py:40-63`) is needed only if async driver methods are used from the thread; the sync `encode` does not need it. Never `asyncio.run` around a driver stream.
- BE-07 (`async_*` blocking the loop) is not on this path and waits for Phase 5 (D-31).

---

### `rag/parsers/router.py`, `rag/chunking/factory.py` (registry utilities)

**Analog:** `rag/llm/__init__.py:36-65` and `api/db/services/upload_rules.py:50-82,121`.
```python
PROVIDER_SPECS: tuple[ProviderSpec, ...] = (ProviderSpec(...), ...)
_INDEX: dict[str, ProviderSpec] = {}
for _spec in PROVIDER_SPECS:
    _INDEX[_spec.name.lower()] = _spec
    _INDEX[_spec.slug] = _spec
def resolve_provider(value: str) -> ProviderSpec:
    found = _INDEX.get(value.strip().lower()) if isinstance(value, str) else None
    if found is None:
        raise UnknownProvider("unknown provider")
    return found
```
Router: one table suffix to parser (`pdf`, `docx`, `xlsx`, `pptx`, `html`/`htm`, and `txt`/`md`/`markdown`/`csv`/`json` all to the TXT parser, D-13), a typed `UnsupportedType`, and a `parseable(suffix) -> bool` the DTO uses. The suffix list must stay a subset of `DEFAULT_UPLOAD_EXTENSIONS` (`settings.py:154`); `epub`, images and audio are uploadable but not parseable. Factory: `FACTORY = {"naive": naive.chunk}`; `get_chunker("qa")` raises a typed `ChunkerUnavailable` (never falls back, D-15); both `PARSER_IDS` (`knowledgebase_service.py:60`) and the dialog's eight methods derive from one list.

**Archive limits** (`rag/parsers/limits.py`): follow `upload_rules.py` style (pure functions raising typed errors with fixed messages that echo nothing). The guard body is in RESEARCH "Zip-bomb guard (measured)"; apply it before any Office parser opens the zip. `charset_normalizer` for text (D-28), BeautifulSoup always with an explicit parser (Gotcha 6).

---

### `rag/parsers/*.py`, `rag/chunking/naive.py`, `rag/nlp/*` (no close analog)

Use RESEARCH "Code Examples" (spiked pypdfium2 recipe, naive chunker contract, `ParsedBlock`/`Chunk` types) and the Phase 3 conventions: dataclasses with `frozen=True` (`upload_rules.py:41-47`), streams read through `Storage.iter_chunks` and closed in `finally` (a MinIO stream pins a pooled connection until closed: `minio_conn.py:108-123`; the reader helper `file_service.IterReader` at `file_service.py:54-103` shows seek(0)-by-reopen). For the tokenizer, tiktoken `cl100k_base` is already loaded from litellm's vendored file without a download (`embedding_model.py` `_point_tiktoken_at_vendored_ranks`, lines 56+); reuse that function instead of writing a second loader. pdfium calls go behind one process-wide lock (RESEARCH Pitfall 8) and every page, textpage and bitmap is closed.

---

### `api/apps/restful_apis/page_api.py` (image, content, thumbnail; file-I/O)

**Analog (partial):** the upload handler in `document_api.py:185-207` for non-JSON IO discipline: authorise before touching bytes, run blocking storage work in `STORAGE_EXECUTOR` with a deadline, close streams in `finally` (`close_upload_streams`, `:163-167`). Responses are raw `quart.Response(bytes, mimetype=...)` instead of `json_result`; errors still go through `service_error_response`. Add `PDF_EXECUTOR` (2 threads) in `api/utils/blocking.py` beside the four existing pools (`blocking.py:24-27`) and use `run_blocking(PDF_EXECUTOR, ..., timeout=...)`. Headers: `Cache-Control: private`, `X-Content-Type-Options: nosniff`, `Content-Disposition: attachment` except PDF inline for `/content`, `Content-Security-Policy: sandbox`; HTML is never served as `text/html`. Page number is 1-based in the path, task ranges are 0-based (`from_page` inclusive, `to_page` exclusive; `MAXIMUM_TASK_PAGE_NUMBER = 1_000_000` is a sentinel, not a page size: add `TASK_PAGE_SIZE = 12` configurable).

---

### `common/settings.py`, `conf/service_conf.yaml.template`, `docker/.env.example`, `docker-compose.yml` (config)

**Analog:** the `UploadSettings` chain.

`settings.py:191-198`:
```python
@dataclass(frozen=True)
class UploadSettings:
    max_file_bytes: int = MAX_UPLOAD_FILE_BYTES
    max_files_per_request: int = 20
    ...
```
`settings.py:385-394` (`_parse_upload`): `defaults = UploadSettings()` then `_bounded(sec, "upload", "name", defaults.name, hi)` per field; `ConfigError("invalid value for config key: <section>.<key>")` on a bad value. `parse_settings` passes `upload=_parse_upload(data)` (`:443`) and `Settings` declares `upload: UploadSettings = field(default_factory=UploadSettings)` (`:233`).

Template block (`service_conf.yaml.template:85-90`): `max_file_bytes: ${UPLOAD_MAX_FILE_BYTES:-104857600}`: bare ints, single-quoted strings. New `ingest:` keys (names are the planner's; the env names in RESEARCH are `INGEST_BATCH_SIZE`, `INGEST_MAX_ATTEMPTS`, `TASK_LOCK_TTL_SECONDS`, `RECLAIM_IDLE_MS`, `WORKER_HEARTBEAT_TIMEOUT`, `PROGRESS_INTERVAL_SECONDS`, `CANCEL_POLL_SECONDS`, `TASK_PAGE_SIZE`, `XLSX_MAX_CELLS`). No secrets, so no `# secret` marker in `.env.example`. Compose passes each in `x-app-env` (`docker-compose.yml:60-67` pattern `NAME: ${NAME:-default}`).

---

### `docker/docker-compose.yml` `task-executor` service, `entrypoint_task_executor.sh`, healthcheck

**Analog:** `docker-compose.yml:72-119` (`init`, `app`), `docker/entrypoint.sh`, `docker/entrypoint_init.sh`, `docker/healthcheck.sh`.

`docker/entrypoint.sh:6-16,31-37` supplies the idioms: `cd /ragflow`, `python scripts/render_conf.py --out "$SERVICE_CONF"`, `chown`, `drop() { setpriv --reuid="$APP_UID" --regid="$APP_GID" --clear-groups "$@"; }`, a trap that kills children on TERM/INT, `wait -n` and a non-zero exit when the child ends. A single-process executor can `exec` the dropped command under tini (`entrypoint: ["tini","--","/ragflow/docker/entrypoint_task_executor.sh"]`) so SIGTERM reaches Python.

`docker/healthcheck.sh:9-20` shows the `expect NAME URL CODE` style and exit-1-with-message convention; the executor check reads the Valkey heartbeat key age against `WORKER_HEARTBEAT_TIMEOUT` (use `python -c` with the project's settings, or `valkey-cli` is not in the app image: verify before relying on it).

Compose skeleton to copy (`docker-compose.yml:94-101`): `profiles: [cpu]`, `image: ${RAGFLOW_IMAGE:-devrag-app:local}`, `pull_policy: never`, `restart: unless-stopped`, `environment: <<: *app-env`, `depends_on: init: condition: service_completed_successfully`, `networks: [ragflow]`, `healthcheck:` block (interval 10s, timeout 5s, retries 3, start_period 30s). Dev file: add a `task-executor:` block with `mem_limit`, `extra_hosts` and `LLM_ALLOW_PRIVATE_BASE_URLS` as in `docker-compose.dev.yml:32-43`.

---

### `api/apps/__init__.py`, `conf/routes.yaml`, `api/utils/reasons.py`

**Registration** (`api/apps/__init__.py:50-62`): add four local imports next to the existing five and `app.register_blueprint(...)` calls before the `extra_blueprints` loop.

**Endpoint row** (`conf/routes.yaml:169-172`):
```yaml
- {method: DELETE, path: "/api/v1/datasets/{dataset_id}/documents", owner: python, auth: api, roles: [owner, admin, normal], scope: tenant, implemented: true,
   note: "plan 03-17 removes documents; the document creator, owner or admin (D-09)"}
```
New rows use `{doc_id}`, `{chunk_id}`, `{log_id}`, `{task_id}` placeholders, `owner: python`, `scope: tenant`, `implemented: false` until the handler plan flips it (Gotcha 10). Chunk, parse and settings writes keep `auth: api` (an API token is judged as its user, D-02); there is no reason to tighten to `jwt`.

---

### Tests: integration and e2e (real stack)

**Service-level integration:** `test/integration/test_document_service.py` is the template. Key reusable helpers (lines 53-90): `put_chunks(cfg, owner, dataset, doc_id, count)` inserts real chunks with an 8-dim vector into the real index, `chunk_ids(...)` reads them back through `search(get_doc_store(cfg), index_name(tenant), [dataset.id], condition={"doc_id": [doc_id]}, limit=100)`, `team_dataset_of(...)` makes a team dataset whose creator is not the workspace owner (needed for D-02 "uploader / creator / owner and admin / other member"), `race_together(calls)` uses a `threading.Barrier`. Import fixtures by name from the base module (`_bound_database`, `settings`, `llm`, `registry`, `storage`, `space`, lines 41-47).

**Engine contract:** new `stats` cases belong in `test/helpers/doc_store_contract.py::DocStoreContract` (rows built by `row(chunk_id, doc_id, text, axis, position)`, helper `search(...)`), automatically run by `TestEsDocStore` (`test_doc_store_es.py:~48`). No fixed waits: writes refresh before returning.

**Valkey integration** (`test_queue.py`, `test_task_lock_reclaim.py`): follow `test/integration/test_ratelimit.py`: real Valkey from `load_settings()`, unique key prefix per test, cleanup by exact key, no mock.

**E2E:** `test/testcases/test_document_flow.py` header pattern (lines 1-60): `pytestmark = pytest.mark.e2e`, `registry` fixture from `test_provider_flow`, `fake_provider_stack` for the embedding provider, helpers `api(...)`, `ok(...)`, `put(...)`, `documents_path(...)`, `assert_no_storage_detail(...)`. For parse flows add `wait_until(lambda: doc_run(...) == "3", timeout=..., describe=...)`.

**Serial failure tests** (`test_ingestion_failure.py`): copy the `stopped(service, ...)` context manager from `test_dependency_outage.py:50-71` (always restart in `finally`, wait for health with `wait_until`, `service_health(...)` from `test/testcases/conftest.py:73-83`, `compose(...)` helper). Kill the executor container through `docker kill` found by compose label, as `container_id` does in `test_compose_infra.py:23-26`.

**Cross-tenant matrix builder** (`_matrix_fixtures.py:416-422,425-446`):
```python
def _list_documents(w: World) -> Target:
    return Target({"dataset_id": str(w.a_team_dataset["id"])}, _sender("GET", DATASETS + "/{dataset_id}/documents", extra_fields=set()), w.snapshot_documents)
```
Add one builder per new path-parameter row (`.../documents/parse`, `.../chunks`, `.../chunks/{chunk_id}`, `.../ingestions`, `.../ingestions/{log_id}`, `.../ingestions/summary`, `.../embedding/check`, `.../pages/{n}/image`, `.../content`, `.../thumbnail`, `/v1/task/status/{task_id}`), pointing at `w.a_team_documents[0]` (the World already has two team documents and one private document, `:155-157`), with `extra_fields=set()` for request models that forbid extra fields. Extend `World` with a parsed document (parse it once through the real route using the fake provider) and make `snapshot_documents()` include chunk counts.

**Leak-sweep exerciser** (`test_response_leaks.py:440-486`): per row, label each call (`s.req(row, "success as owner", "GET", path, a.token)`): success as owner, as team member, with an API token, a private dataset as a member, absent id, malformed id, outsider, plus `s.errors(row, "GET", path, "PATCH")` for no credential, made-up bearer, wrong method. New function `sweep_ingestion_rows(s, w)` registered in `sweep()` after `sweep_dataset_write_rows` (`:608-609`).

**Live tier:** header and fixtures from `test_live_models.py:1-17,85-98`. Keep the budget counter idea (D-16: a few dozen chunks per run) and print only counts.

---

### Frontend: services, hooks, permissions

**Service analog:** `web/src/services/document-service.ts`:
```ts
function toDocument(raw: unknown): DocumentView {
  const dto = asRecord(raw);
  return { id: text(dto.id), name: text(dto.name), ..., chunkNum: count(dto.chunk_num) };
}
export async function listDocuments(input: ListDocumentsInput): Promise<DocumentPage> {
  const params: Record<string, string | number> = { page: clampWhole(input.page, 1, Number.MAX_SAFE_INTEGER), page_size: clampWhole(input.pageSize, 1, MAX_DOCUMENT_PAGE_SIZE) };
  ...
  const data = asRecord(await request<unknown>({ url: datasetDocumentsPath(input.datasetId), method: "GET", params }, { silent: true }));
  return { items: Array.isArray(data.items) ? data.items.map(toDocument) : [], total: count(data.total) };
}
```
Rules to keep: snake_case DTO read through `asRecord/text/count`, explicit field list, every call `{ silent: true }`, `expectRecord(value, what, ["id"])` for creation answers. Per-request timeouts from UI-SPEC (`timeout: 30_000` parse, `45_000` chunk save, `timeout: 0` plus `AbortController` for downloads). Thumbnail accepted only when it starts with `data:image/jpeg;base64,` or `data:image/png;base64,`. Blob routes: `responseType: "blob"`, create an object URL only for `image/jpeg` or `image/png`, revoke on change.

**Paths** (`constants/api-paths.ts`, `datasetDocumentsPath`): `resolveUnder("python", "/api/v1/datasets/", \`${encodeURIComponent(id)}/documents\`)`; add siblings for `parse`, `{doc}`, `{doc}/chunks`, `{doc}/chunks/{chunk}`, `{doc}/pages/{n}/image`, `{doc}/content`, `ingestions`, `ingestions/summary`, `ingestions/{log}`, and `taskStatusPath` via `resolveUnder("python", "/v1/", ...)`. A miss is a build-time throw, so regenerate `api-routes.generated.json` first.

**Hook analog:** `hooks/use-document-request.ts:13-34,43-52,59-69`. Query keys start `["ws", tenantId, ...]`; `retry: false`; mutations `gcTime: 0`; `invalidateDocumentData` refreshes the documents root plus both dataset keys. Phase 4 changes: `placeholderData: keepPreviousData`, `refetchInterval: (query) => query.state.data?.items.some((r) => r.run === "1") ? 2000 : false`, `refetchIntervalInBackground: false`, mutations invalidate in `onSettled` (FE-03), not `onSuccess`. New `hooks/use-chunk-request.ts` follows the same key shape (`["ws", tenantId, "chunks", datasetId, docId, page, keywords, show]`).

**Permissions analog:** `hooks/use-dataset-permissions.ts:21-23,43-47`:
```ts
export function canRemoveDocument(datasetCreatedBy, documentCreatedBy, userId, role): boolean {
  return canManageDataset(datasetCreatedBy, userId, role) || (userId !== null && userId !== "" && documentCreatedBy !== "" && documentCreatedBy === userId);
}
export function useCanRemoveDocument(dataset, document): boolean { ... }
```
Add `canChangeDocument`/`useCanChangeDocument` returning exactly the same value; the dataset default uses `useCanManageDataset`.

---

### Frontend: dataset page extensions

**Analogs:** `pages/dataset/document-row.tsx` (row structure, uploaded date, `percentOf`, `data-testid` convention), `document-status-badge.tsx` (badge with icon + text, "Unknown status" fallback), `dataset-files.tsx` (table, toolbar, skeleton, empty/error ladder, focus restore after delete).

Status badge today (`document-status-badge.tsx:11-26`): `Badge variant="default"` + `Circle` icon for `run === "0"`, outline "Unknown status" otherwise. Extend to the UI-SPEC state map (`Loader2` static under reduced motion, `CircleCheck`, `CircleAlert`, `CircleSlash`, `CircleDashed` with the existing `degraded` variant) driven by `(run, chunkCount, parseable)`; keep the fallback branch.

Row actions: the trigger and non-modal menu pattern is `components/dataset-actions-menu.tsx:22-73` (`<DropdownMenu modal={false}>`, `chosen` ref so the menu does not steal focus back when it opens a dialog, `onCloseAutoFocus`). Controls the caller may not use are absent, not disabled.

Confirmation dialogs: standalone `AlertDialog`, "Keep ..." as the cancel with default focus, `event.preventDefault()` on the action then an async `confirm()`, in-flight ref guard, `onEscapeKeyDown` blocked while in flight, error `Alert` inside, `onCloseAutoFocus` supplied by the owner: copy `components/delete-document-dialog.tsx:42-126` for `ReparseDialog` and `DiscardChangesDialog`. Keep error and counts in a body mounted only while open (FE-04). Never stack an `AlertDialog` over a `Dialog` or the sheet (R-152): the sheet's "Parse again" closes the sheet, waits for unmount, then opens the dialog.

Form dialogs: `components/dataset-settings-dialog/index.tsx:67-85` (a `Dialog` whose body is mounted only while open, `pendingRef` blocking Esc and outside click while a save runs, skeleton and `ErrorState` ladder) and `settings-form.tsx:66-130` (`useForm` + `zodResolver`, `mode: "onSubmit"`, `reValidateMode: "onChange"`, `inFlight` ref + `busy` state, `changesOf(...)` sending only changed fields, server errors placed by a function in `errors.ts`, `notifySuccess(t(...))`). `ParseConfiguration` fields: chunk size 1..8192, delimiters 1..64 with `\n`/`\t` escape round trip, overlap 0..50; ranges mirror the server `ParserConfig` (BE-09).

Server error placement: `pages/datasets/errors.ts:36-75` (`reasonOf(error)` reads `ApiError.data.reason`; a function maps `(status, reason)` to `{target, key}`; only an alert may carry bounded server text). Write `pages/dataset/errors.ts` additions (`parseFailureOf`, `chunkFailureOf`) as pure functions with a table test, classifying a timeout by status or kind, never by a translated string (FE-06). A provider refusal is never a session event: no 401.

Polling notice: three failed polls in a row show the info `Alert` (`datasets.files.pollPaused`); the same treatment applies to the inspector, the log page and the open sheet (checker flag 6).

Workspace binding for the new pages: `pages/dataset/index.tsx:26-103` (id regex `^[0-9a-f]{32}$` before any request, `boundTenantRef`, `initialised`, `bindActive`, `DatasetNotFound` for a 404, `ErrorState` otherwise, `ready={!initialised || activeTenantId === shown.tenantId}`). The `/chunk` and `/document` pages validate both ids (`id`, `doc`) the same way.

Routes: `constants/routes.ts:79-85` entry shape for `/dataset/files` (no `nav`, lazy `import()`); add `/dataset/logs`, `/chunk`, `/document` the same way. `build` runs `web/scripts/check-chunks.mjs`, so keep each page a lazy chunk.

New `ui/` components follow `ui/progress.tsx` and `ui/choice-group.tsx` (props interface, `cn`, native element carrying the keyboard behaviour, visible text beside colour). `switch` is `<input type="checkbox" role="switch">` with a visible "On"/"Off".

Tests: `pages/dataset/dataset-files.test.tsx:1-60` (Harness component around the real hooks and services, in-memory server from `web/src/test/dataset-server.ts`, `http.defaults.adapter` swapped and restored, `registerQueryClient`, `useUserStore`/`useWorkspaceStore` reset), `hooks/use-document-request.test.tsx:1-60` (adapter keyed by `"METHOD url"`, `renderHook`), and the live pattern `pages/dataset/dataset.live.test.ts` with `web/src/test/wait-until.ts`. Use fake timers for the `refetchInterval` assertions. The live provider key never enters the browser tier; the SPA live suite uses `web/src/test/live/fake-provider.ts` and the real worker.

---

## Shared Patterns

### Envelope, reasons and status mapping
**Source:** `api/utils/api_utils.py:11-42`, `api/apps/service_errors.py:21-51`, `api/db/services/service_errors.py`, `api/utils/reasons.py`.
**Apply to:** every new handler and service. `Kind.NOT_FOUND` and `Kind.FORBIDDEN` have fixed bodies; other kinds produce `{code, message, data: {reason, ...exc.data}}` with status from `_TABLE` (`INVALID` 400, `CONFLICT` 409, `PAYLOAD_TOO_LARGE` 413, `RATE_LIMITED` 429, `UNAVAILABLE` 503, `TIMEOUT` 504, `BAD_GATEWAY` 502). `service_error_response` returns `Retry-After` when `retry_after` is set.

### One 404 for anything not visible
**Source:** `knowledgebase_service.load_visible_dataset` (`:348-359`) and `document_service.delete_documents` (`:365-367`, `len(found) != len(wanted)` is `_not_found()`).
**Apply to:** dataset, document, chunk, log, task and page-image routes. Visibility first, then permission (403), then the object lookup scoped to the dataset; an id of another dataset or tenant is the same 404.

### Bounded blocking calls
**Source:** `api/utils/blocking.py:22-45`.
**Apply to:** all handler-side work. `DB_EXECUTOR` 16, `PROVIDER_EXECUTOR` 8, `DOCSTORE_EXECUTOR` 8, `STORAGE_EXECUTOR` 8; each call has an explicit `timeout`; the service-level deadline sits below the handler's.

### Structured logging without secrets
**Source:** `common/log_utils.py`, `rag/llm/errors.py::safe_text`, `llm_service.py:89-99`.
**Apply to:** the executor and all new services. Log ids and counts; never `str(exc)` of a provider, storage or parser exception (use `type(exc).__name__`); never a path, key or request body. Stack traces stay in server logs; the UI and API carry only `{step, code, message}` from typed codes (D-08, D-23). See Gotcha 30 for the redaction side effect on progress text.

### Settings access
**Source:** `current_app.extensions["ragflow_settings"]` in handlers (`document_api.py:125-126`), `get_settings()` in processes. No `os.environ` reads in feature code.

### Test discipline
**Source:** `test/helpers/wait.py`, `test_live_models.py`, `test/helpers/fake_provider.py`.
**Apply to:** all tests. `pytestmark = pytest.mark.<tier>`, no `sleep(`, no mocks of own services (the fake provider stands in for a third party), cleanup by recorded ids only, obviously fake secrets built from parts so `check_secrets.py` stays quiet.

---

## No Analog Found

Planner should use RESEARCH.md patterns (and the read-only reference where noted):

| File | Role | Data Flow | Reason / pattern source |
|---|---|---|---|
| `rag/parsers/pdf.py` | service | file-I/O | No PDF code exists. RESEARCH "PDF text with character boxes, page count, raster at zoom 3 (spiked)" |
| `rag/parsers/{docx,xlsx,pptx,html,txt}.py` | service | file-I/O | No Office or HTML code exists. RESEARCH "Office and text parsers"; ref `deepdoc/parser/` |
| `rag/chunking/naive.py` | service | transform | RESEARCH "Naive chunker contract"; ref `rag/app/naive.py` |
| `rag/nlp/tokenizer.py`, `normalize.py` | utility | transform | RESEARCH "Tokenizer and CHUNK-17"; ref `rag/nlp/` (stdlib rewrite, no `infinity-sdk`) |
| `rag/svr/executor_loop.py` collect/claim loop | service | event-driven | RESEARCH Patterns 2-4; ref `rag/svr/task_executor.py`, `rag/utils/redis_conn.py` |
| `rag/svr/cancel.py` heartbeat and cancel-watch thread | utility | event-driven | RESEARCH Pattern 4 |
| `rag/svr/progress.py` roll-up daemon | service | batch | RESEARCH "Roll-up daemon"; `docs/10-cache-and-queues/scheduling.md` |
| `rag/queue/valkey_streams.py` stream commands | service | pub-sub | Only the client construction exists (`common/ratelimit.py`). RESEARCH "Valkey streams, claim and lock (spiked)" |
| `components/document-preview/page-preview.tsx` (image + percent-positioned boxes) | component | request-response | UI-SPEC "Preview pane"; geometry in RESEARCH "Frontend" |
| `components/document-preview/text-preview.tsx` | component | request-response | UI-SPEC "Document viewer" |
| `pages/chunk/chunk-editor.tsx` unsaved-changes guard (`useBlocker`, `beforeunload`) | component | event-driven | UI-SPEC "Unsaved changes"; React Router `useBlocker` |
| `test/helpers/ingest.py` 13-page text PDF generator | test helper | transform | `uploads.pdf_bytes` makes a magic-bytes stub only; write a minimal valid PDF by hand (no `fpdf2`, D-24) |
| DOCX/XLSX/PPTX/HTML test file builders | test helper | transform | Generate with the newly approved libraries; poison file = zip signature + garbage |
| Compose kill-test override file | config | batch | Dev override pattern only (`docker-compose.dev.yml`); keys per RESEARCH "Crash, reclaim, poison and cancel strategy" |
| Page-image coordinate conversion (pdfium bottom-left to top-left points) | utility | transform | RESEARCH Pattern 6 and spike notes |

## Metadata

**Analog search scope:** `api/` (apps, db/services, utils), `common/` (doc_store, ratelimit, settings, log_utils, health, constants), `rag/` (llm, utils), `conf/`, `docker/`, `scripts/` (ci, wait_stack, clean_room, preflight, record_memory), `test/` (unit_test, integration, testcases, helpers), `web/src` (pages/dataset, pages/datasets, components, hooks, services, constants, locales, test), `.planning/` phase 3 and 4 records.
**Files scanned:** about 150; about 70 read in full or in the relevant ranges.
**Not read in full (planner to confirm when touching):** `scripts/gen_routes.py` internals, `run_tests.py`, `api/apps/middleware.py`, `rag/llm/chat_model.py`, `web/src/locales/*.json` beyond the namespace list, `internal/**` (no Go change expected: Phase 4 has no schema change and the Go matrix covers `owner: go` rows only).
**Not verified:** Elasticsearch behaviour of nested `position_int` and of `stats`; the warnings the new packages raise under `filterwarnings = error`; whether `valkey-cli` exists in the app image (for the executor healthcheck).
**Pattern extraction date:** 2026-10-10
