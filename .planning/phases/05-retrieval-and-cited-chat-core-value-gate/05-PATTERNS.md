# Phase 5: Retrieval and Cited Chat (Core Value Gate) - Pattern Map

**Mapped:** 2026-10-19
**Files analyzed:** 58 new or modified files (grouped rows count each file named)
**Analogs found:** 54 / 58 (4 partial or no analog, listed under "No Analog Found")

Sources read: `05-CONTEXT.md` (D-01..D-26), `05-RESEARCH.md`, `05-UI-SPEC.md`, `05-VALIDATION.md`, `CLAUDE.md`. Line numbers below are from the repo at this commit. Excerpts are short on purpose: open the cited range before copying.

## File Classification

### Backend: new files

| New file | Role | Data flow | Closest analog | Match |
|---|---|---|---|---|
| `rag/nlp/fusion.py` | utility (pure functions) | transform | `rag/svr/chunk_doc.py` (`l2_normalize`, 37-42) and `rag/nlp/token_count.py` | role-match |
| `rag/nlp/query.py` | utility (query builder) | transform | `api/db/services/chunk_service.py` `list_chunks` keyword path (190-195) | role-match |
| `rag/nlp/synonym.py` (+ `rag/res/synonym.json`) | utility (cached dictionary) | request-response | `common/ratelimit.py` (per-call Valkey client, fail mode) | partial |
| `rag/nlp/search.py` (Retriever) | service | request-response | `api/db/services/chunk_service.py` `list_chunks` + `rag/utils/es_conn.py` `search` | role-match |
| `rag/llm/rerank_model.py` | driver | request-response (batched HTTP) | `rag/llm/embedding_model.py` `Base` (153-260) + `chat_model.py` `_Session` (251-269) | exact (shape) |
| `rag/prompts/generator.py` | utility (prompt + context builder) | transform | `rag/llm/stream.py` (pure module, frozen dataclass) | partial |
| `rag/prompts/citations.py` | utility (marker post-processor) | transform | `rag/llm/stream.py` `StreamSanitizer` (49-82) | partial |
| `api/db/services/retrieval_service.py` | service | request-response | `api/db/services/chunk_service.py` (`authorize_read`, `_embed`, DocStoreError mapping) | exact |
| `api/db/services/dialog_service.py` | service | CRUD | `api/db/services/knowledgebase_service.py` | exact |
| `api/db/services/conversation_service.py` | service | CRUD + lock | `api/db/services/task_service.py` `_write_message` (200-206) + `rag/svr/task_lock.py` | role-match |
| `api/apps/restful_apis/retrieval_api.py` | route | request-response | `api/apps/restful_apis/chunk_api.py` `create_chunk` (143-159) | exact |
| `api/apps/restful_apis/chat_api.py` (assistants, sessions, feedback) | route | CRUD | `api/apps/restful_apis/dataset_api.py` | exact |
| completion route (in `chat_api.py` or a sibling `completion_api.py`) | route | streaming (SSE) | `api/apps/restful_apis/page_api.py` `content` + `_body` (81-135) | partial |
| `api/db/migrations/0003_chat_assistants.py` | migration | batch (DDL) | `api/db/migrations/0002_baseline_schema.py` + `runner.add_column_if_missing` (47-52) | exact |

### Backend: modified files

| File | Change | Closest analog (for the new code) |
|---|---|---|
| `api/db/models/chat.py` | `Dialog.created_by`, `Dialog.permission` | `Search.created_by` (chat.py:134); `Knowledgebase.permission` |
| `api/db/services/tenant_scope.py` | `assistant_visible`, `can_manage_assistant` | `dataset_visible` / `can_manage_dataset` (100-118) |
| `rag/utils/es_conn.py` | `must_not` inside `condition`, search path only | `_filter_clauses` (82-95) and `search` body build (347-368) |
| `rag/llm/__init__.py`, `api/db/services/tenant_model_service.py`, `llm_service.py`, `provider_service.py`, `model_defaults_service.py`, `api/apps/restful_apis/provider_api.py` | `TEI` provider row, `rerank` model type | Ollama row (`rag/llm/__init__.py:45`), `TYPE_BITS` (`tenant_model_service.py:34`) |
| `common/settings.py`, `conf/service_conf.yaml.template` | `ChatSettings` / `RetrievalSettings` | `IngestSettings` (201) + `_parse_ingest` (437) + template `ingest:` block (93-105) |
| `api/utils/reasons.py` | new machine reasons | existing constants (1-80) |
| `api/apps/__init__.py` | register blueprints | lines 50-68 |
| `conf/routes.yaml` (+ generated Nginx and Vite files) | endpoint rows, streaming family | rows 179-199, families 63-77 |
| `api/db/services/chunk_service.py` | move `_positions` / `_page_sizes` to a shared helper | its own 80-111 |

### Infrastructure and scripts

| File | Closest analog |
|---|---|
| `docker/docker-compose-base.yml` service `tei` | `es01` block (75-97) |
| `docker/docker-compose.dev.yml` `tei.mem_limit` | `es01` (3-9), `mailpit` (end of file) |
| `docker/.env.example`, `test/unit_test/test_env_catalog.py` | `ES_PORT`, `STACK_VERSION` entries (.env.example:13, 30) |
| `Makefile` (31, 37), `scripts/clean_room.sh` (56), `scripts/wait_stack.sh` | profile lists |

### Tests (Python)

| File | Tier | Closest analog |
|---|---|---|
| `test/unit_test/test_fusion_golden.py`, `test_rrf.py`, `test_sanitize_floats.py` | unit | `test/unit_test/test_tokenizer.py` |
| `test/unit_test/test_query_builder.py` | unit | `test/unit_test/test_tokenizer.py` |
| `test/unit_test/test_rerank_model.py` | unit (loopback fake) | `test/unit_test/test_llm_drivers.py` + `test/helpers/fake_provider.py` |
| `test/unit_test/test_prompt_context.py`, `test_citations.py` | unit | `test/unit_test/test_tokenizer.py` |
| `test/integration/test_retrieval_es.py` | integration (real ES) | `test/integration/test_doc_store_es.py` + `test/helpers/doc_store_contract.py` |
| `test/integration/test_rerank_tei.py` | integration (real TEI) | `test/integration/test_compose_infra.py` |
| `test/integration/test_dialog_service.py`, `test_conversation_service.py` | integration (real MySQL) | `test/integration/test_knowledgebase_service.py` |
| `test/testcases/test_chat_flow.py`, `test_retrieval_flow.py`, `test_chat_stream_nginx.py` | e2e | `test/testcases/test_chunk_flow.py`, `test_parse_flow.py` |
| `test/testcases/test_live_chat.py` | live_model | `test/testcases/test_live_ingestion.py` |
| `test/testcases/test_spa_chat_browser.py` | e2e + live, real Chrome | `test/testcases/test_spa_ingestion_browser.py` |
| `test/testcases/test_phase3_isolation.py`, `_matrix_fixtures.py`, `test_response_leaks.py` | e2e (extend) | their own chunk rows |
| `test/helpers/fake_provider.py` (gated chat stream, chat-request record) | helper | `_sse` (174-191), `delay_ms`, `release_slow` |
| `test/unit_test/test_phase5_records.py`, `test_phase5_traceability.py` | unit | `test_phase4_records.py`, `test_phase4_traceability.py` |

### Web (new unless noted)

| File | Role | Closest analog |
|---|---|---|
| `web/src/services/sse.ts` | service (fetch stream) | `services/http.ts` (auth attach, purge, `ApiError`); no stream analog |
| `web/src/services/chat-service.ts`, `retrieval-service.ts` | service (mappers) | `services/chunk-service.ts` |
| `web/src/hooks/use-chat-request.ts`, `use-retrieval-request.ts` | hook (TanStack) | `hooks/use-chunk-request.ts` |
| `web/src/hooks/use-assistant-permissions.ts` | hook | `hooks/use-dataset-permissions.ts` |
| `web/src/constants/app-paths.ts`, `api-paths.ts`, `routes.ts` (modify) | config | same files |
| `web/src/locales/areas/{en,zh}/{chat,assistant,retrieval,source}.json` | locale | `locales/areas/en/inspector.json` |
| `web/src/components/ui/range-field.tsx` | component | `components/ui/progress.tsx` (small native-element component) |
| `web/src/components/markdown-content/*` | component | no analog (needs approved packages) |
| `web/src/pages/chat/index.tsx`, rail, conversation, message-list, message-item, message-input, `errors.ts` | page | `pages/datasets/index.tsx`, `pages/chunk/index.tsx`, `pages/datasets/errors.ts` |
| `web/src/pages/chat/assistant-dialog/*` | dialog + form | `components/dataset-settings-dialog/*`, `components/create-dataset-dialog/*` |
| `web/src/pages/chat/source-drawer.tsx` | sheet | `components/ui/sheet.tsx` + `components/document-preview/page-preview.tsx` |
| `web/src/pages/dataset/testing/*` | page | `pages/chunk/index.tsx` (binding), `pages/dataset/dataset-workspace.tsx` |
| `web/src/pages/dataset/dataset-workspace.tsx` (modify) | page | `dataset-upload` button (193-195) |
| `web/src/test/server-areas/{chat,assistants,retrieval}.ts` | test server | `test/server-areas/chunks.ts` |
| `web/src/services/sse.test.ts`, `src/pages/chat/chat.live.test.ts`, source gate | tests | `chunk-inspector.test.tsx`, `inspector.live.test.ts`, `constants/phase4-source-gate.test.ts` |
| `web/src/components/llm-select`, `services/model-service.ts` (modify) | component | same files (`ModelType` at model-service.ts:52) |

---

## Pattern Assignments: Backend

### `api/db/migrations/0003_chat_assistants.py` (migration, DDL)

**Analog:** `api/db/migrations/0002_baseline_schema.py` and the helper in `api/db/migrations/runner.py`.

File contract (0002:1-13): module exposes `VERSION` equal to the numeric prefix and `upgrade(db)`. The runner wraps each migration plus the version write in one `db.atomic()` (runner.py:126), but MySQL commits DDL implicitly, so every alter must be idempotent:

```python
# runner.py:47-52
def add_column_if_missing(db: Any, table: str, column: str, field: peewee.Field) -> bool:
    if column in {c.name for c in db.get_columns(table)}:
        return False
    migrate(MySQLMigrator(db).add_column(table, column, field))
    return True
```

Usage (test_migration_runner.py:160): `add_column_if_missing(DB, "scratch", "note", peewee.CharField(max_length=20, default=""))`. Add `created_by` (`CharField(max_length=32, null=False, default="")`) and `permission` (`CharField(max_length=16, null=False, default="me")`), then `add_index_if_missing(db, "dialog", ("created_by",))` and `("permission",)` (runner.py:55-67).

**Gotcha:** 0002 builds missing tables from the *current* `ALL_MODELS`, so a fresh database already has the new columns once `chat.py` is edited; 0003 is then a no-op and an old database gets them from 0003. Both paths must pass `test_migration_runner.py`. After the model edit run `scripts/export_schema.py` and `scripts/gen_go_entities.py` (`conf/schema.json`, `internal/entity/dialog.go`); `test/unit_test/test_schema_export.py` and `test_gen_go_entities.py` are the drift gates.

### `api/db/services/tenant_scope.py` (modify: `assistant_visible`, `can_manage_assistant`)

**Analog:** same file, lines 100-118. Copy the logic, give new names (research Pattern 5: never reuse the dataset names at call sites).

```python
# tenant_scope.py:100-118
def dataset_visible(creator_id, permission, caller_id, caller_in_tenant) -> bool:
    if not caller_in_tenant or not caller_id: return False
    if creator_id == caller_id: return True
    return permission == PERMISSION_TEAM

def can_manage_dataset(creator_id, caller_id, role) -> bool:
    if not caller_id: return False
    return creator_id == caller_id or is_elevated(role)
```

D-24 differs from datasets in one place: an owner or admin manages only a `team` assistant, never a `me` one. `can_manage_assistant(creator_id, permission, caller_id, role)` therefore is `creator_id == caller_id or (permission == PERMISSION_TEAM and is_elevated(role))`. `assistant_visible` is identical to `dataset_visible` (a `me` assistant is invisible to owner and admin). Unit-test beside `test/unit_test/test_tenant_scope.py`.

### `api/db/services/dialog_service.py` (service, CRUD)

**Analog:** `api/db/services/knowledgebase_service.py`. Take these pieces in order.

**Module header and imports** (knowledgebase_service.py:28-57): `from __future__ import annotations`, a docstring that lists decision ids, `ServiceError`/`Kind`, `reasons`, `DB`, `transaction`, `DatabaseLock`, no web framework import.

**Frozen records instead of ORM rows** (232-252): `_record(row) -> DatasetRecord` and `VisibleDataset(dataset, scope)` (130-132). Mirror as `AssistantRecord` / `VisibleAssistant`.

**Visibility load, one 404 for every miss** (341-352):

```python
def load_visible_dataset(principal, dataset_id) -> VisibleDataset:
    if not isinstance(dataset_id, str) or _ID.fullmatch(dataset_id) is None:
        raise _not_found()
    with DB.connection_context():
        row = Knowledgebase.get_or_none((Knowledgebase.id == dataset_id) & (Knowledgebase.status == _VALID))
    if row is None: raise _not_found()
    scope = scope_for_tenant(principal, row.tenant_id)
    if scope is None or not dataset_visible(row.created_by, row.permission, principal.user_id, True):
        raise _not_found()
    return VisibleDataset(_record(row), scope)
```

**List by visibility** (327-338): `visible = (tenant_id == scope.tenant_id) & (status == "1") & ((created_by == user_id) | (permission == PERMISSION_TEAM))`, `.paginate(page, page_size)`, and the escaped `LIKE` keyword filter at 331-334. Reuse `_escape_like`. The list view must omit `icon` (UI-SPEC choice 31).

**Name uniqueness under a named lock** (255-261, 278-320): `_name_taken` compares case-insensitively; create takes `DatabaseLock(f"kb-create:{tenant}", 10)` and raises `Kind.CONFLICT, reasons.DUPLICATE_NAME`. Use a distinct lock name (`dialog-create:{tenant_id}`, within the 64-character limit).

**DTO as an explicit key list** (360-380): "Keys are listed here, so a column added to the table never reaches a client unreviewed." The assistant view must say `chat_id` where an id key is needed, never `dialog_id`, and use `permission`, never `status` or `source` (leak sweep; `_leak_sweep.py:21-24`).

**Update with `changes` dict and `model_fields_set`** (473-524, route side dataset_api.py:226-240): an absent key is not a change. D-25 (keep hidden bound ids) is the new logic: compute `kept = [id for id in row.kb_ids if id not in visible_to_saver]`, apply the saver's list only to the visible ids, write `kept + chosen`.

**Delete** (544-579): authorise everything first, then change. D-26 deletes every member's `Conversation` rows for the assistant in the same transaction (`with DB.connection_context(), transaction():`, task_service.py:200-206 style).

**Error mapping:** `ServiceError(Kind.CONFLICT, "assistant_dataset_not_shared", msg, data={"dataset_ids": [...]})` and `ServiceError(Kind.CONFLICT, "assistant_has_member_chats", msg, data={"count": n})`. `service_error_response` already merges `exc.data` into `data` (api/apps/service_errors.py:50-53). Add both names to `api/utils/reasons.py`.

### `api/db/services/conversation_service.py` (service, CRUD + turn lock)

**Analog 1 (row-locked read-modify-write of one JSON/text column):** `api/db/services/task_service.py:200-206`:

```python
def _write_message(task_id, line, values):
    with DB.connection_context(), transaction():
        row = Task.select(Task.progress_msg).where(Task.id == task_id).for_update().first()
        if row is None: return
        Task.update(progress_msg=_append_message(row.progress_msg, line), **values, **_stamp()).where(Task.id == task_id).execute()
```

Copy the shape for appending the user message and the assistant message to `Conversation.message` (a `JSONField`). Every session query filters `dialog_id` **and** `user_id` (D-11); any miss is the one `NOT_FOUND` (`knowledgebase_service._not_found`, 153-154).

**Analog 2 (Valkey lock with TTL, owner-checked release):** `rag/svr/task_lock.py:19-66`. `open_client(settings)` (line 19-22) gives a short-timeout client; `TaskLock.named(client, prefix, name, ttl_seconds)` builds `{prefix}.lock.{name}`; `acquire()` is non-blocking and returns bool; `release()` is compare-and-delete; Valkey errors become `QueueUnavailable`. Use it (or the same `valkey.lock.Lock` underneath) for `chat_turn:{session_id}` with TTL equal to the stream deadline; map a failed acquire to `Kind.CONFLICT, "turn_in_progress"` and an unreachable store to `Kind.UNAVAILABLE` (fail closed, same rule as `common/ratelimit.py:5-8`).

**Analog 3 (per-workspace per-user rate limit, 429 + Retry-After):** `api/db/services/ingestion_service.py:101-110` `write_rate_guard`:

```python
window = limiter or FixedWindowLimiter(settings.redis)
try:
    window.hit(f"chunk:{tenant_id}", settings.ingest.parse_rate_max, settings.ingest.parse_rate_window_seconds)
except RateLimited as limited:
    raise ServiceError(Kind.RATE_LIMITED, "rate_limited", "...", retry_after=limited.retry_after) from None
except RateLimitUnavailable:
    raise ServiceError(Kind.UNAVAILABLE, reasons.BUSY, "...") from None
```

Add `chat_rate_guard(settings, tenant_id, user_id)` with key `chat:{tenant}:{user}` and numbers from the new settings section.

**Read-time redaction:** no analog exists; see "No Analog Found".

### `api/db/services/retrieval_service.py` (service, request-response)

**Analog:** `api/db/services/chunk_service.py`. The same four steps: authorise, embed with the dataset's model, call the DocStore under `DocStoreError` mapping, shape the result.

**Imports to copy** (chunk_service.py:17-41): `LLMBundle`, `embedding_dimensions`, `load_visible_dataset`, `VisibleDataset`, `DocStoreConnection, DocStoreError, MatchTextExpr, index_name, vector_field`, `get_doc_store`, `reasons`, `Kind, ServiceError`.

**Authorise (visibility only)** (117-119): `authorize_read(principal, dataset_id) -> load_visible_dataset(...)`. For several datasets (assistant), call it per id or reuse a batch variant, and keep "foreign id = the one 404 for the whole request" (TEN-03). Permission area: `forbid_unless(scope, "datasets", "retrieval_test")`; the row already exists in `conf/permissions.yaml` (`enforced_in: phase-5`).

**Query embedding** (224-237), adapted:

```python
dimension = embedding_dimensions(visible.scope.tenant_id).get(dataset.embd_id)
if dimension is None:
    raise ServiceError(Kind.NOT_FOUND, reasons.MODEL_UNAVAILABLE, "that model is not available in this workspace")
bundle = LLMBundle(visible.scope.tenant_id, dataset.embd_id, "embedding", settings=settings, expected_dimension=dimension)
vector, _ = bundle.encode_queries(question)   # llm_service.py:295-297
```

`LLMBundle` reads a credential row in `__init__` and the sync methods block: run the whole service function in `PROVIDER_EXECUTOR` (chunk_api.py:152-156) or `DOCSTORE_EXECUTOR`; the embedder seam for the golden integration test is a parameter, as `doc_store` is (`doc_store: DocStoreConnection | None = None`, chunk_service.py:177).

**DocStore call and failure mapping** (198-209):

```python
engine = doc_store if doc_store is not None else get_doc_store(settings)
try:
    found = engine.search(select_fields, [], condition, match, order, offset, size, index_name(tenant_id), [dataset_id])
except DocStoreError as exc:
    logger.warning("chunk list could not read the index dataset=%s error=%s", visible.dataset.id, type(exc).__name__)
    raise _index_unavailable() from None
```

Log the dataset id and the exception class only, never the question or chunk text (research V7). `_index_unavailable` is `ServiceError(Kind.UNAVAILABLE, reasons.INDEX_UNAVAILABLE, ...)` (65-66).

**Positions and page sizes:** import the shared helper moved out of `chunk_service.py:80-111` (`_positions` handles nested and flat `position_int`; `_page_sizes` builds `{"<page>": [w, h]}` from `page_dims_flt`).

**Select fields to request:** the index row keys written by `rag/svr/chunk_doc.py:70-90`: `content_with_weight`, `content_ltks`, `title_tks`, `docnm_kwd`, `doc_id`, `position_int`, `page_num_int`, `page_dims_flt`, `available_int`, `doc_enabled_int`. Select names must match `FIELD_RE` (`[A-Za-z0-9_]{1,64}`, no dots).

**D-22 rule (from Phase 4):** any `engine.update(...)` result must be checked (`if not done: raise _index_unavailable()`, chunk_service.py:354-355). Retrieval itself writes nothing, but the CHAT-19 fallback and any future stats write must follow it.

### `rag/utils/es_conn.py` (modify: `must_not` in the search path only)

**Analog:** the file itself. Two facts constrain the change.

1. The port forbids new parameters: `doc_store_base.py:3-4` says "later phases add behaviour behind these methods, never parameters". So `must_not` travels inside `condition` under a reserved key and is popped in `search()` before `_filter_clauses` (which today raises `InvalidFilter("invalid condition value")` for a dict, es_conn.py:93-94).
2. The same filter list feeds both the `bool.filter` and the `knn.filter` (347, 142). A `must_not` must be applied to both, or kNN hits will come back that the text side excluded.

Current shape to extend (es_conn.py:325-349, 133-149):

```python
filters = _filter_clauses(condition or {}, scope)           # kb_id terms first, then one clause per key
...
knns.append(_knn(expr, dense_boost, filters))               # knn "filter": {"bool": {"filter": filters}}
bool_query: dict[str, Any] = {"filter": filters}
```

Add `must_not = _must_not_clauses(condition.pop("must_not", {}))` (validate keys with `CONDITION_KEY_RE`, scalar or list values, same type check as lines 87-94), pass `{"bool": {"filter": filters, "must_not": must_not}}` to `_knn`, and set `bool_query["must_not"]`. Add the case to the contract class in `test/helpers/doc_store_contract.py` (pattern at 245-251, `test_condition_filters_the_search`), not only to the Phase 5 integration test, so every future adapter gets it.

### `rag/nlp/query.py` (utility, transform)

**Analog:** `chunk_service.list_chunks` (190-195) already does the documented tokenise-then-match step:

```python
tokens = tokenize(keywords)                       # rag/nlp/tokenizer.py:15-23, the same function used for content_ltks
if not tokens:
    return {...empty...}                          # punctuation only: nothing can match, and nothing is an error
match.append(MatchTextExpr(["content_ltks"], " ".join(tokens), size, {"minimum_should_match": "100%"}))
```

Query builder differences: field list with boosts `title_tks^10 ... content_sm_ltks` (the adapter accepts `^n` on a field only, `MATCH_FIELD_RE` es_conn.py:57), `minimum_should_match` `30%` with one retry at `10%`, stopword drop, synonym tokens appended. `MatchTextExpr` is in `common/doc_store/doc_store_base.py:152-157`. The adapter already limits query flags to `AND|OR|PHRASE|PREFIX` and sets `lenient: true` (es_conn.py:59, 119-126), so user text never reaches Elasticsearch syntax; do not emit operators.

### `rag/nlp/search.py` (Retriever, request-response)

**Analog:** `chunk_service.list_chunks` for the DocStore call, `es_conn.search` for the expression set. Stage 1 expressions use the port value objects (doc_store_base.py:152-185):

```python
MatchTextExpr(fields, " ".join(tokens), top_k, {"minimum_should_match": "30%"})
MatchDenseExpr(vector_field(dim), query_vec, "float", "cosine", top_k, {"similarity": 0.0})
FusionExpr("weighted_sum", top_k, {"weights": "0.001,1"})
```

`_weights` (es_conn.py:98-111) only accepts `weighted_sum` and two non-negative numbers; `_knn` clamps `k` to `MAX_RESULT_WINDOW` (10000) and sets `num_candidates = 2k` (133-149). Hits are `_source` dicts plus `id` and `_score` (es_conn.py:382-387), `SearchResult(total, hits, aggregations)`.

Stage 2 (clean cosine) is a kNN-only call with `condition={"id": candidate_ids}`; the `id` key goes through the normal `terms` clause. Convert with `vsim = clamp(2*score - 1, 0, 1)` (research Pattern 2 step 5). Keep arithmetic in `rag/nlp/fusion.py`, not in this file.

### `rag/nlp/fusion.py` (pure utility)

**Analog:** `rag/svr/chunk_doc.py:37-42` for the style of a small guarded numeric helper that refuses non-finite input, and `rag/nlp/token_count.py` for a dependency-light module. No numpy is installed; keep pure Python. Research "Code Examples" gives `fuse`, `cosine_from_es_score`, `rrf`, `sanitize_floats`. `sanitize_floats` is applied at the serialisation edge only: `api/utils/api_utils.py` builds the body with `json.dumps(..., default=str)` (line 33), which would emit `NaN` for a bare float, so sanitise in the route's view builder before `json_result`.

Golden tests (`test_fusion_golden.py`): the numbers in research Pattern 2 (A=(1.0, 0.2), B=(0.2, 1.0); at w=0.3 A=0.76, B=0.44). Write the test first (D-21).

### `rag/llm/rerank_model.py` (driver, batched HTTP)

**Analog:** `rag/llm/embedding_model.py` `Base` for the structure and `rag/llm/chat_model.py` `_Session` for the HTTP client.

**Constructor and options** (embedding_model.py:156-180): `provider_spec, model_name, api_key, api_base, api_version, *, llm_settings, allow_private, deny_hosts, sleep, timeout`; `self.api_base = (api_base or provider_spec.default_base_url or "").strip().rstrip("/") or None`.

**SSRF check with default-host skip** (embedding_model.py:189-204; same rule in chat_model.py:273-285):

```python
if self.api_base == self.spec.default_base_url:
    return None  # the documented public host
...
validate_base_url(self.api_base, allow_private=self.allow_private, deny_hosts=self.deny_hosts)
```

This is why the `TEI` spec's `default_base_url = "http://tei:80"` works under `allow_private_base_urls=false` (research Pitfall 7). The skip is an exact string match only.

**One attempt, error classification** (embedding_model.py:217-230): `_attempt` re-validates the target, calls `_embed`, converts any exception through `classify_embedding_error`, never keeps the exception text; failure is logged as provider, model and code only. Rerank uses the async form: `arun_with_retries(lambda: ..., max_retries=self.llm_settings.max_retries, sleep=self._sleep)` (`rag/llm/retry.py:61-78`) with an `httpx.AsyncClient(follow_redirects=False, timeout=..., event_hooks={"response": [...]})`.

**HTTP client** (chat_model.py:251-269): `_Session` owns `_Capture` (status, body, retry-after of a failed response) and closes in `__aexit__`. It is module-private. Either import it with a short `# noqa: PLC2701` comment or promote it to a public name; do not copy 20 lines. Failure text reaches clients only via `ModelException(code, retryable=..., provider_status=..., body=...)` (`rag/llm/errors.py:56-72`, parsed, redacted, cut to 200 characters). Map 429 to `retryable=True`, 413/422/424 to `ERROR_INVALID_REQUEST`.

**Token usage:** TEI sends none; estimate with `rag/nlp/token_count.count_tokens` and flag `estimated=True`, the same convention as `Usage` (`rag/llm/stream.py:15-20`).

**Registry:** `build_rerank(spec, ...)` mirrors `build_embedder` (embedding_model.py:343-367): pick a class by `spec.name`, construct with no I/O, validate on first call.

### `rag/llm/__init__.py` and the model-type surfaces (modify: `TEI` provider, `rerank` type)

**Analog:** the keyless Ollama row (`rag/llm/__init__.py:45`):

```python
ProviderSpec(Provider.OLLAMA, "ollama", "ollama_chat/", None, "none", "required", False, True)
```

`ProviderSpec` is a frozen dataclass of eight positional fields (29-38); add `model_types` with a default (`("chat", "embedding")`) so the five existing rows and `test/unit_test/test_llm_registry.py` `EXPECTED` (positional tuples) keep working, then add `Provider.TEI = "TEI"` and `ProviderSpec(Provider.TEI, "tei", "", "http://tei:80", "none", "default", False, False, ("rerank",))`. Update `test_five_providers_in_settings_page_order` to six.

Surfaces that hard-code the two types and must learn `rerank` (all found by grep):

| Place | Line |
|---|---|
| `api/db/services/tenant_model_service.py` `TYPE_BITS` and `_DEFAULT_FIELDS` | 34, 45 (bit 16 is reserved per the column comment; `_DEFAULT_FIELDS["rerank"] = ("rerank_id", "tenant_rerank_id")`) |
| `api/db/services/llm_service.py` `MODEL_TYPES`, bundle `_build` | 50, 161-170 |
| `api/db/services/provider_service.py` `MODEL_TYPES`, `_test_model` (needs a rerank branch: query plus two short documents) | 41, 199-221 |
| `api/db/services/model_defaults_service.py` `MODEL_TYPES` and its error text | 19, 39 |
| `api/apps/restful_apis/provider_api.py` `type: Literal["chat", "embedding"]` | 58 |
| web `services/model-service.ts` `ModelType`, `components/llm-select` | model-service.ts:52 |

`GET /api/v1/models?type=rerank` must work (models_api.py:90 passes the query value through `list_model_dtos`). The set-defaults slots stay `chat` and `embedding` (models_api.py:34).

### `rag/prompts/generator.py` and `rag/prompts/citations.py` (pure utilities)

**Analog (partial):** `rag/llm/stream.py`. Same shape: a frozen dataclass for results (`Usage`, 15-20), small total functions that never raise on odd input (`usage_from`, 35-41; `strip_control`, 44-46), no SDK imports. Token budgeting uses `rag/nlp/token_count.count_tokens` (token_count.py:14-15). Dedupe uses `xxhash` (already a dependency). The shared marker regex is `##(\d+)\$\$` (research Pattern 4); keep ONE compiled pattern in `citations.py` and import it in the generator so the prompt and the post-processor cannot drift.

Unit tests are pure (no fixtures): `test_prompt_context.py` (dedupe, trimming, numbering after trimming), `test_citations.py` (normalise `## N $$`, `[ID:N]`, `[N]` only when `N < len(chunks)`, drop out-of-range, fallback only when no valid marker remains).

### `api/apps/restful_apis/retrieval_api.py` (route, request-response)

**Analog:** `api/apps/restful_apis/chunk_api.py` `create_chunk` (143-159) for a POST that embeds, and `parse_api.py` for the lean module layout.

**Module layout to copy** (parse_api.py:13-36, 38-66): docstring listing requirements and decisions, route constant "identical to the endpoint row in conf/routes.yaml", executor timeout constants, `BaseModel` with `ConfigDict(extra="forbid")`, an envelope model for `document_response`, `_settings()` helper.

```python
# chunk_api.py:143-159 (shape)
@validate_request(CreateChunkBody)
@document_response(ChunkEnvelope, 200)
async def create_chunk(dataset_id, doc_id, data):
    try:
        settings = _settings()
        principal = g.principal            # read on the loop
        visible = await run_blocking(DB_EXECUTOR, chunk_service.authorize_write, principal, dataset_id, timeout=AUTHORIZE_TIMEOUT_SECONDS)
        await run_blocking(DB_EXECUTOR, ingestion_service.write_rate_guard, settings, visible.scope.tenant_id, timeout=AUTHORIZE_TIMEOUT_SECONDS)
        made = await run_blocking(PROVIDER_EXECUTOR, lambda: chunk_service.create_chunk(...), timeout=WRITE_TIMEOUT_SECONDS)
        return json_result(made)
    except ServiceError as exc:
        return service_error_response(exc)
```

Registration is the last line of the module: `bp.add_url_rule(PATH, endpoint=..., view_func=..., methods=["POST"])` (parse_api.py:95), and the blueprint is added in `api/apps/__init__.py` next to line 68.

Route specifics: `POST /api/v1/datasets/search` (a static path; the dynamic dataset routes accept GET/PUT only, dataset_api.py:266-267, so there is no conflict). Body: `dataset_ids` (list, one in the UI), `question`, `similarity_threshold`, `vector_similarity_weight`, `top_k`, `rerank_id?`, `page`, `size`, `tenant_id?` (the `Field(default=None, pattern=_TENANT_ID_PATTERN)` form, dataset_api.py:68). Handler order: `acting_scope(data.tenant_id)` -> `not_found_response()` if None -> `forbid_unless(scope, "datasets", "retrieval_test")` (dataset_api.py:171-176) -> rate guard -> service in `PROVIDER_EXECUTOR`. Total deadline: embed (30 s driver) + search + rerank; pick a handler timeout above the service's, like `WRITE_TIMEOUT_SECONDS = 45.0` over the driver's 30 s (chunk_api.py:38). The UI client uses 45 s (UI-SPEC "HTTP client rules").

### `api/apps/restful_apis/chat_api.py` (route, CRUD)

**Analog:** `api/apps/restful_apis/dataset_api.py`. Copy its five-handler layout almost mechanically:

- Bodies with `extra="forbid"` and `model_fields_set` for updates (dataset_api.py:71-83, 232).
- `_whole(name, default, low, high)` for page/size query parameters (158-164).
- List handler reads `g.principal.user_id` on the loop "the request context does not follow the call into the worker thread" (205).
- 404-for-everything via `not_found_response()`; 403 only through `forbid_unless` or a service `Kind.FORBIDDEN`.
- `View` and `Envelope` pydantic models for OpenAPI (105-147).

Routes per research Pattern 6: `GET|POST /api/v1/chats`, `GET|PUT|DELETE /api/v1/chats/<chat_id>`, `GET|POST /api/v1/chats/<chat_id>/sessions`, `GET|DELETE .../sessions/<session_id>`, feedback `POST`. Chat rows carry **no** new permission-matrix area (research Pattern 6): authorise in the service with `assistant_visible` / `can_manage_assistant`. Split the file if it passes about 300 lines (CLAUDE.md "no giant files"; `dataset_api.py` is 268 lines, `document_api.py` 423 is the upper bound already in the repo).

### Completion route (SSE) in `chat_api.py` or `completion_api.py`

**Analog (partial):** `api/apps/restful_apis/page_api.py` is the only streaming handler.

```python
# page_api.py:97-105  async generator whose finally runs when the client leaves
async def _body(pump) -> AsyncIterator[bytes]:
    try:
        while True:
            chunk = await run_blocking(STORAGE_EXECUTOR, pump.next_chunk, timeout=CHUNK_TIMEOUT_SECONDS)
            if chunk is None: break
            yield chunk
    finally:  # also when the client leaves: cancellation cannot interrupt a submit
        STORAGE_EXECUTOR.submit(pump.close)

# page_api.py:133  return Response(_body(...), mimetype=..., headers=headers)
```

Four rules to carry over from that file:

1. **Read request-scoped values before the `Response` exists** (page_api.py:64-65, 120): `settings = _settings()`, `principal = g.principal`. The generator runs after the handler returns, outside the request context.
2. **Cleanup that must survive cancellation goes through `EXECUTOR.submit(...)`**, never `await` (line 105). For the partial-answer write use `DB_EXECUTOR.submit(turn.persist_partial, text)`.
3. **All pre-stream failures are normal envelopes** returned from the `try / except ServiceError` before the `Response` is built (page_api.py:134-135), so 404/403/409/429 keep real statuses.
4. Add `resp.timeout = settings.chat.stream_deadline_seconds` (Quart's 60 s `RESPONSE_TIMEOUT` otherwise truncates the body silently; research Pitfall 1) and the headers `Cache-Control: no-cache`, `X-Accel-Buffering: no`. The response middleware (`api/apps/middleware.py:55-62`) only adds `X-API-Source` and logs; it does not read the body, so streaming is safe.

**Blocking calls inside the async generator (BE-07):** `LLMBundle.async_chat_streamly` (llm_service.py:271-280) and `async_chat` call `self._report_usage` (222-232), which executes a synchronous MySQL `UPDATE` on the loop, and `LLMBundle.__init__` reads a credential row (153). Build the bundle with `run_blocking(DB_EXECUTOR, lambda: LLMBundle(...))` and make `_report_usage` run via `run_blocking(DB_EXECUTOR, ...)`; the new unit test fails if `DB.execute_sql` is entered with a running loop.

**Frame writer:** copy `json_result`'s serialisation (`api/utils/api_utils.py:31-34`, `ensure_ascii=False`, key order `code, message, data`) but emit `b"data: " + payload + b"\n\n"`. Response keys use `finish`, `chat_id`, `permission` (not `status`, `source`, `dialog_id`).

### `common/settings.py` + `conf/service_conf.yaml.template` (modify)

**Analog:** `IngestSettings` (settings.py:201-226), `_parse_ingest` (437-470) and the template block (93-105). Add frozen dataclasses with defaults, parse through `_bounded(sec, "chat", "stream_deadline_seconds", default, hi, lo=...)` (303), register in `Settings` next to `ingest` (263) and in `parse_settings` (517). Template line shape: `key: ${ENV_NAME:-default}`. Cover with `test/unit_test/test_settings.py` and `test_env_catalog.py`. Candidates: `stream_deadline_seconds`, `max_question_chars`, `max_session_messages`, `rate_max`, `rate_window_seconds`, `retrieval.rerank_max_candidates`, `retrieval.top_k`, TEI base URL.

### `conf/routes.yaml` (modify) and generated files

**Analog:** the Phase 4 rows (routes.yaml:179-199) and the Python families (63-77).

```yaml
- {method: POST, path: "/api/v1/datasets/{dataset_id}/documents/parse", owner: python, auth: api, roles: [owner, admin, normal], scope: tenant, implemented: true,
   note: "plan 04-14 ..."}
```

New rows: `POST /api/v1/datasets/search` (covered by the existing `^~ /api/v1/datasets/` prefix family, body_limit 1m, no new family), `GET|POST /api/v1/chats`, `GET|PUT|DELETE /api/v1/chats/{chat_id}`, session rows, `POST /api/v1/chat/completions`, feedback. New families needed because `/api/` otherwise falls to the 1024m catch-all: `{owner: python, match: exact, path: /api/v1/chats, auth: api, body_limit: 1m}`, `{... match: prefix, path: /api/v1/chats/ ...}`, `{... match: exact, path: /api/v1/chat/completions ...}`. Python families default to `streaming: true` (3600 s upstream timeouts; gen_routes.py:84), so no extra flag is needed for SSE. Run `uv run python scripts/gen_routes.py` then `--check` (CI drift gate `scripts/ci/check_generated.py`). The row `scope: tenant` makes the cross-tenant matrix and the isolation table pick the row up automatically (see Shared Patterns).

### Infrastructure: `tei` service

**Analog:** `es01` in `docker/docker-compose-base.yml:75-97` (profile-gated infra service with a healthcheck and a network alias):

```yaml
  es01:
    profiles: [elasticsearch]
    image: docker.elastic.co/elasticsearch/elasticsearch:${STACK_VERSION:-8.11.3}
    ports:
      - ${BIND_HOST:-127.0.0.1}:${ES_PORT:-9200}:9200
    volumes:
      - esdata01:/usr/share/elasticsearch/data
    networks:
      ragflow:
        aliases: [es01]
    healthcheck:
      test: ["CMD-SHELL", "curl -fsS -u elastic:$$ELASTIC_PASSWORD '...'"]
      interval: 15s
      timeout: 10s
      retries: 40
      start_period: 30s
```

Use the compose block from research Pattern 3 verbatim (profile `tei-cpu`, `TEI_IMAGE` pinned `cpu-1.9.4`, volume `tei_data`, long `start_period`). Also add `tei_data:` under `volumes:` (112-117). Dev memory cap goes in `docker/docker-compose.dev.yml` beside `es01.mem_limit: 2g` (line 4), and the value is a measured number (plan task, not a guess; see R-188 precedent in dev compose line 40-41). Add `--profile tei-cpu` to the three profile lists: `Makefile:31` and `:37`, `scripts/clean_room.sh:56`. `scripts/wait_stack.sh` already treats any service with a healthcheck as required (`evaluate`, 66-82); the TEI first start downloads the model, so pass a larger `--timeout`/`WAIT_STACK_TIMEOUT` (default 300, line 11) from the callers rather than editing the loop. Pin tests: copy the style of `test/unit_test/test_compose_files.py:29-45` (service shape, dev-only keys absent from the production file).

### Python tests: extending the isolation harness (D-19)

See "Shared Patterns, Cross-tenant isolation" below; it applies to every new route and is the part Phase 4 forgot.

---

## Pattern Assignments: Tests

### `test/integration/test_retrieval_es.py` (integration, real ES, planted vectors)

**Analog:** `test/helpers/doc_store_contract.py` helpers and the existing hybrid test (220-232).

```python
# doc_store_contract.py:33-48
def unit_vector(axis, dim=DIM): vec = [0.0]*dim; vec[axis] = 1.0; return vec
def row(chunk_id, doc_id, text, axis, position=0) -> dict:
    return {"id": chunk_id, "doc_id": doc_id, "content_ltks": text, "title_tks": "title",
            "position_int": position, "available_int": 1, f"q_{DIM}_vec": unit_vector(axis)}
```

For the golden fusion integration test the retrieval service takes the embedder as a seam, so the query vector equals chunk S's vector and chunk K carries the rare keyword on an orthogonal axis. For rows that look like real parsed chunks (so `doc_enabled_int`, `docnm_kwd`, `page_dims_flt` exist), build them with `rag.svr.chunk_doc.build_row` the way `seed_chunks` does (`_matrix_fixtures.py:388-420`: `create_idx`, `Chunk(text, (), {}, count_tokens(text), i)`, `build_row`, `get_doc_store(load_settings())`). Random tenant ids and teardown by recorded index name: `test_doc_store_es.py:1-4`.

### `test/unit_test/test_rerank_model.py` (unit, loopback fake)

**Analog:** `test/unit_test/test_llm_drivers.py:1-60`. Same helpers: a `Sleeps` recorder injected as `sleep` so no test waits, a `make(...)` factory building the driver with `LlmSettings(max_retries=...)`, `allow_private=True`, `deny_hosts=()`, and the `fake_provider` fixture. Extend `test/helpers/fake_provider.py` with `POST /rerank` (TEI shape `[{"index", "score"}]` sorted by score; OpenRouter shape `results[{index, relevance_score}]`) next to `embeddings` (271-288); assertions on batch size 32 and `texts` length come from `fake.requests` (recorded bodies, `Recorded.body`, line 44-51).

### `test/helpers/fake_provider.py` (extend: gated chat stream, chat-request record)

**Analog:** the same file.

```python
# fake_provider.py:174-191  _sse(model, wants_usage): yields frames immediately
async def generate():
    yield frame({... "delta": {"role": "assistant"} ...})
    for piece in CHAT_PIECES: yield frame({... "delta": {"content": piece} ...})
    ...
    yield b"data: [DONE]\n\n"
```

The stream today emits at once. Add a gate modelled on the existing `/slow` endpoints (254-260: `await state._release.wait()`; control via `release_slow()` 117-119 and `delay_ms` 49): after the first content piece `await` a per-stream event so "first frame before last through Nginx" and "stop mid-stream" are deterministic. "No model call on empty" is asserted from `fake.hits("/v1/chat/completions") == []` (114-115). Keep `CHAT_PIECES` text free of `##N$$` unless the test wants a marker; add a variant that streams a marker split across two pieces (`"##"`, `"1$$"`) for the hold-back test.

### `test/testcases/test_chat_flow.py`, `test_retrieval_flow.py`, `test_chat_stream_nginx.py` (e2e)

**Analog:** `test/testcases/test_chunk_flow.py` / `test_parse_flow.py` for the registry-driven e2e shape, `test/helpers/ingest.py` for the world (`upload_text` 250-264, `start_parse` 267-273, `wait_run` 303-312, `paragraphs` 66-68), `test/helpers/fake_provider.py` `fake_provider_stack` fixture, and `test/helpers/wait.py::wait_until(predicate, timeout=, interval=, describe=)` for any waiting (`no_sleep` gate). For SSE use an `httpx` streaming request against the ingress; parse lines in the test itself, no sleeps.

### `test/testcases/test_live_chat.py` (live_model)

**Analog:** `test/testcases/test_live_ingestion.py`. Copy: module docstring naming requirements and decisions (1-14), `pytestmark = pytest.mark.live_model` (66), `MISSING_KEY_MESSAGE` and the hard fail without a key (68), a numeric cap constant asserted from counts (`CHUNK_CAP = 72`, 70; here `CHAT_TURN_CAP = 15` and the embed cap), `STATE` / `EVIDENCE` module dicts (82-83), fixtures re-exported from `test_live_models` (`live_env`, `bound_database`, `recorder`, `leaks`, ...; 41-65), key travels only in the provider PUT body and assertions reduce to booleans or counts. Planted-fact assertion (D-07): citation index resolves to the planted chunk id, and the answer text contains the fact's key words; no LLM judge.

### `test/testcases/test_spa_chat_browser.py` (real Chrome)

**Analog:** `test/testcases/test_spa_ingestion_browser.py`. Reuse verbatim: the `browser` fixture (40-47: `chrome_path()` assertion, `ChromeSession`, `_set_viewport`), `_press_expr` / `_press` (50-64: waits for finite animations then dispatches real mouse events), `_by_id`, `_wait_testid`, `_store_token`, `_set_viewport` imported from `test_spa_browser` (36), `Scene` class pattern (98+: `open(browser, path, ready_test_id)`), `ORIGIN` (`HTTP_PORT`, 33), `SCREENSHOT_DIR`. All waiting is `browser.wait_for(js_expr, description, timeout=...)`. Assert streaming by sampling the answer length at two distinct values before the done state, then click a pill and assert the drawer; reload and assert the same turn.

### `test/unit_test/test_phase5_records.py` and `_traceability.py`

**Analog:** `test/unit_test/test_phase4_records.py:1-50`: `FIRST_ROW`/`LAST_ROW` bounds, `STATUS` string, `ROW = re.compile(r"^\| R-(\d+) \|")`, `REQUIRED_TITLES` list where each substring must appear in exactly one row title. Next free ids: R-192, B-37 (`.planning/DECISIONS.md` ends at R-191).

---

## Pattern Assignments: Web

### `web/src/services/chat-service.ts`, `retrieval-service.ts`

**Analog:** `web/src/services/chunk-service.ts`. Pattern: explicit view interfaces, mappers that read every field through `text`/`count`/`asRecord`/`clampWhole` (`services/mapping.ts:6-30`), `request<unknown>(config, { silent: true })` (the page renders its own error), per-call timeout constant (`CHUNK_WRITE_TIMEOUT_MS = 45000`), arrays filtered through a mapper that returns `null` for an unusable item (`toPosition`, chunk-service.ts:46-52).

```ts
// chunk-service.ts:46-52 (shape to copy for scores and positions)
function toPosition(raw: unknown): ChunkPosition | null {
  const dto = asRecord(raw);
  const values = [dto.page, dto.x0, dto.x1, dto.top, dto.bottom];
  if (!values.every((value) => typeof value === "number" && Number.isFinite(value))) return null;
  return { page: dto.page as number, ... };
}
```

The SPA "never trusts a score or position it cannot parse and omits it" (UI-SPEC notes 3): map a non-finite score to `null`. Reuse `ChunkPosition` from chunk-service for the reference positions. Retrieval test timeout constant 45000, chat CRUD uses the default 10 s.

### `web/src/services/sse.ts`

**Analog (partial):** `web/src/services/http.ts`. The stream bypasses axios, so reuse its pieces, do not re-implement them: `getAuthorization()` (imported at line 14), `isSameOrigin(url, baseURL)` (exported, 88-95), `purgeSession` / `shouldPurge` semantics (a 401 on a request that carried the still-current token ends the session; 120-150), and `ApiError` (35-60, with `kind?: "timeout" | "network"` for FE-06). Build the error from the JSON envelope (`isEnvelope`, 62-69). `eventsource-parser` is behind a blocking human checkpoint (D-21); if declined, a ~40-line hand parser with the same unit tests (UI-SPEC Registry Safety). Never native `EventSource` and no token in a URL.

### `web/src/hooks/use-chat-request.ts`, `use-retrieval-request.ts`

**Analog:** `web/src/hooks/use-chunk-request.ts`.

```ts
// use-chunk-request.ts:13-16, 27-40  key shape + keepPreviousData + enabled gate (FE-01, FE-02)
export const chunksKeyRoot = (tenantId: string | null, datasetId: string, docId: string) => ["ws", tenantId, "chunks", datasetId, docId] as const;
return useQuery({ queryKey: chunksKey(...), queryFn: () => listChunks({...}), retry: false,
  placeholderData: keepPreviousData, enabled: enabled && tenantId !== null && dataset !== "" && doc !== "" });

// 83-95  mutation: not retried, gcTime 0, refresh in onSettled (FE-03)
useMutation({ mutationFn: ..., retry: false, gcTime: 0, onSettled: (...) => refreshAfterChunkWrite(...) })
```

`tenantId` comes from `useActiveWorkspace()?.tenantId ?? null` (`hooks/use-workspaces.ts:30-34`); every key starts with `["ws", tenantId, ...]`. The completion hook is not a query: hold the `AbortController` in a ref, invalidate the session detail and the chat list in `onSettled`/`finally` for complete, stopped, failed and aborted turns (UI-SPEC FE-03 test: "aborts a turn and asserts the session was refetched"). Model-list hook: `useModelsRequest("rerank")` after `ModelType` gains `rerank` (use-llm-request.ts:41-49).

### `web/src/hooks/use-assistant-permissions.ts`

**Analog:** `web/src/hooks/use-dataset-permissions.ts:11-45`. Same structure: a `MANAGER_ROLES` set, a pure `canManageAssistant(createdBy, userId, role, permission)` (creator always; owner or admin only when `permission === "team"`), `useRoleIn(tenantId)` and a `use...` wrapper reading `useUserStore((s) => s.user?.id ?? null)`. Pure function first so it is unit-testable without React (`use-dataset-permissions.test.ts` is the test analog).

### `web/src/constants/*` (modify)

- `app-paths.ts`: add `CHATS_ROUTE = "/chats"`, `DATASET_TESTING_ROUTE = "/dataset/testing"`, `retrievalTestPath(datasetId)` and `chatPath(chatId, sessionId?)` in the style of lines 16-33 (route constant + builder with `encodeURIComponent`, one definition shared by the link and the registered route). Extend `documentViewerPath(datasetId, docId, page?)` (line 31-33); the viewer already reads a `page` search parameter (`pages/document-viewer/index.tsx:43`). Update `constants/app-paths.test.ts:5-11` style test.
- `api-paths.ts`: every API path is resolved from `api-routes.generated.json` and a missing registry entry throws at build time (lines 1-26). Add `chatsPath` (`resolve("python", "/api/v1/chats")`), `chatPath(id)` (`resolveUnder("python", "/api/v1/chats/", ...)`), `chatCompletionsPath`, `datasetSearchPath`; regenerate the JSON with `scripts/gen_routes.py` after the registry rows land.
- `routes.ts`: add `/chats` (nav `MessagesSquare`, group `platform`, order 3), move `/system-status` to order 4 (currently 3, routes.ts "nav: { labelKey: "nav.systemStatus", ... order: 3"), add a `/chat` redirect entry in the style of `/` (redirect function, routes.ts:56-60) and `/dataset/testing` as a nav-less nested entry like `DATASET_LOGS_ROUTE` (routes.ts:88-95). `routes.test.tsx` and `app-sidebar` tests cover order.

### `web/src/locales/areas/{en,zh}/{chat,assistant,retrieval,source}.json`

**Analog:** `web/src/locales/areas/en/inspector.json` (nested object rooted at the area name, `_one`/`_other` plural keys, `{{interpolation}}`). `locales/index.ts:21-34` deep-merges area files and throws on a duplicate leaf; `areas.test.ts` enforces en/zh file-name parity, key parity and "never redefines a base key". Cross-cutting keys that live outside the area name (`nav.chat`, `errors.assistant.*`, `errors.retrieval.*`) are allowed as long as no base file defines them: put them in `chat.json` / `retrieval.json` under a root `"nav"` / `"errors"` object, never in `en.json`. `no-hardcoded-copy.test.ts` forbids any string literal in a page or component that starts with a locale value (UI-SPEC "Locale key rules"); if a collision appears, reword the locale value, never the gate.

### `web/src/components/ui/range-field.tsx`

**Analog:** `web/src/components/ui/progress.tsx` (a small native-element component with a typed props interface, `data-testid` prop, `cn()` classes, a doc comment naming the requirement). Native `<input type="range">`, label above, readout right, `aria-valuetext` = readout. No Radix slider (`@radix-ui/react-slider` is on the forbidden list of the source gate).

### `web/src/pages/chat/*` (page, rail, conversation)

**Analog 1 (list + search + pagination + states + FE-01):** `web/src/pages/datasets/index.tsx:1-60`. Imports to copy: `EmptyState`, `ErrorState`, `PageHeader`, `Pagination`, `SearchInput`, `Skeleton`, `useActiveWorkspace`, `parsePage`-style clamping of URL parameters (`MAX_PAGE`, regex `^\d{1,9}$`, lines 21-31). The rail's search is debounced into the list query only (UI-SPEC), not the URL.

**Analog 2 (page with URL ids, binding, split panes, preview):** `web/src/pages/chunk/index.tsx`: `useSearchParams`, `HEX_ID = /^[0-9a-f]{32}$/` (37) to validate `chat` and `session` before any request, `useDatasetBinding` for the "no workspace-scoped request before the store is bound" rule (FE-02; hooks/use-dataset-binding.ts:41-95 states the contract: `bound` must be true before sending). The chat page has no dataset binding, so gate queries on `tenantId !== null` and the workspace store being initialised (`useWorkspaceStore((s) => s.initialisedFor !== null)`, binding hook lines 56-57).

**Analog 3 (error mapping by status + `data.reason`):** `web/src/pages/datasets/errors.ts:44-70`:

```ts
export function datasetErrorTarget(error: unknown, action = "create"): DatasetFailure {
  if (!(error instanceof ApiError)) return { target: "alert", key: fallback };
  const reason = reasonOf(error);
  if (reason === "duplicate_name") return { target: "name", key: "datasets.error.duplicate" };
  ...
  if (error.status === 403) return { target: "alert", key: "workspace.forbidden" };
```

`pages/chat/errors.ts` (completion refusals table) and `pages/dataset/testing/errors.ts` follow it: classify by status plus `reasonOf(error)`; a timeout or abort is recognised by `error.kind` (FE-06), never by message text; server sentences are never shown (only fixed keys).

### `web/src/pages/chat/assistant-dialog/*` (dialog + form)

**Analog:** `web/src/components/dataset-settings-dialog/index.tsx` + `settings-form.tsx`, with `create-dataset-dialog/{schemas.ts,server-field-error.tsx,blocked-form.tsx}`.

Container (dataset-settings-dialog/index.tsx:53-76): body mounted only while open (FE-04), `pendingRef` blocks Esc and outside click during a save, `onCloseAutoFocus` supplied by the owner because there is no trigger:

```tsx
<Dialog open={open} onOpenChange={onOpenChange}>
  <DialogContent data-testid="..." onCloseAutoFocus={onCloseAutoFocus}
    onEscapeKeyDown={(event) => { if (pendingRef.current) event.preventDefault(); }}
    onInteractOutside={(event) => { if (pendingRef.current) event.preventDefault(); }}>
    <Body ... pendingRef={pendingRef} />
```

Form (settings-form.tsx:62-130): `useForm` with `zodResolver(schema)`, `mode: "onSubmit"`, `reValidateMode: "onChange"`; `changesOf(entity, values)` builds a PUT body with only changed fields (49-59); `inFlight` ref guards a double submit; `fail(error)` maps `datasetErrorTarget` to `form.setError` plus `ServerFieldError` or an `Alert`, and refreshes stale caches on 403/gone; success path `notifySuccess(...)` then `onClose()`; Name focused on mount (`useEffect` -> `nameInput.current?.focus()`).

Schema (create-dataset-dialog/schemas.ts:15-22): zod messages are locale keys (`"errors.dataset.nameRequired"`), `trim().min(1).max(NAME_MAX)`. `errors.assistant.*` follow.

Visibility radios: `components/ui/choice-group.tsx` already supports per-option `disabled` and a trailing `badge` with `aria-describedby` (5-17, 56-67), which is exactly the "Whole team" + "Needs shared datasets" case. Model selects: `LlmSelect` (`components/llm-select/index.tsx`) with `type="chat"` and `type="rerank"` and `notSetLabel`. Blocked form for no chat model: `create-dataset-dialog/blocked-form.tsx`. Dataset checklist: native `checkbox` rows (`components/ui/checkbox.tsx`).

D-23 refusal (409 `assistant_has_member_chats`, `data.count`) is an inline `Alert`, never an `AlertDialog` over the dialog (R-152). `ApiError.data` carries `{reason, count}` because `service_error_response` merges `exc.data` (service_errors.py:50-53).

### `web/src/pages/chat/source-drawer.tsx` (sheet)

**Analog:** `components/ui/sheet.tsx` (`side="right"`, `closeLabel` prop; right sheet is `w-full max-w-xl`, lines 28-31) plus `components/document-preview/page-preview.tsx`.

```tsx
// page-preview.tsx:33-51  props to satisfy
<PagePreview datasetId docId name pages={pagesTotal} page={page} onPageChange selection={{ chunkId, number, positions }} pageSizes={{ "1": [w, h] }} enabled />
```

`PreviewSelection` is `{ chunkId, number, positions: ChunkPosition[] }` (page-preview.tsx:23-28). `pages` and the `preview === "pages"` flag come from the Phase 4 document detail hook (`useDocumentDetailRequest`, hooks/use-document-request.ts); a 404 there means "text only". The passage box can reuse `components/document-preview/text-preview.tsx`. Page images are fetched with the Authorization header through `use-blob-url.ts` / `fetchPageImage` (services/page-service.ts:34-49); never put a token in a URL. Focus: `onOpenAutoFocus` to the passage box, `onCloseAutoFocus` to the opener.

### `web/src/pages/dataset/testing/*` and the dataset header button

**Analog:** `pages/chunk/index.tsx` (loads a dataset by `?id=` through `useDatasetBinding`, back link `datasetFilesPath`, `ErrorState`, `InspectorNotFound`) and `pages/dataset/dataset-workspace.tsx:193-195` for the header button (`<Button type="button" data-testid="dataset-upload" ...>` stays the only primary; add an `outline` "Test retrieval" `Link` before it). Hits render with `Progress` (`components/ui/progress.tsx:18`) for the overall bar and `Pagination` for result pages with its own accessible name (FE-07).

### `web/src/test/server-areas/{chat,assistants,retrieval,source}.ts`

**Analog:** `web/src/test/server-areas/chunks.ts`. A file in that directory is auto-registered: `dataset-server.ts:141` does `import.meta.glob("./server-areas/*.ts", { eager: true })` and installs each module's `handle` export. Shape (chunks.ts:65-100):

```ts
export const handle: AreaHandler = ({ server, config, method, url, params, ok, failure }) => {
  const matched = ROUTE.exec(url);
  if (!matched) return undefined;                       // not mine: fall through
  const state = chunkStateOf(server);                   // server.areaState("chunks", () => ({...})) cleared on reset
  if (method === "GET" ...) return ok({ items, total, page_sizes });
  ... return failure({ status: 404, message: "not found", reason: "not_found" });
```

Export fixture builders (`chunkRow`, `setChunks`) for the tests. The SSE endpoint is not an axios call, so its test double is a `fetch` stub in the test, not a server area.

### Web tests

- Component tests: `pages/chunk/chunk-inspector.test.tsx:1-60` (`useFilesServer()` from `test/files-harness.tsx:86-104`, `createMemoryRouter` + `QueryClientProvider` + `registerQueryClient`, `actAs(user, role)` at 72-80, `server.callsTo("GET", url)`, `waitUntil` from `@/test/wait-until`).
- `waitUntil` (`test/wait-until.ts`): `waitUntil(predicate, { timeout = 15_000, interval = 100, describe })`; the only permitted polling site, no fixed sleeps.
- Live: `pages/chunk/inspector.live.test.ts:1-60` (`createWorld`, `destroyWorld`, `openApp`, `installObjectUrls`, 300 s `beforeAll`), keep it free of OpenRouter calls except one gated test inside the budget.
- Source gate: copy `constants/phase4-source-gate.test.ts` to `phase5-source-gate.test.ts`: `import.meta.glob("/src/**/*.{ts,tsx}", { query: "?raw", ... })`, strip comments with `code()`, forbid `dangerouslySetInnerHTML`, `iframe`, `rehype-raw`, `EventSource`, `react-pdf-highlighter`, `pdfjs-dist`, `@tanstack/react-table`, `@radix-ui/react-slider`, and assert `package.json` declares only the three approved new packages after the checkpoint. Note the Phase 4 gate already forbids `iframe` and `dangerouslySetInnerHTML`; the new file only adds names.

---

## Shared Patterns

### Request handling and error envelope
**Source:** `api/apps/restful_apis/dataset_api.py:167-191`, `api/apps/service_errors.py:28-53`, `api/utils/api_utils.py:31-39`
**Apply to:** every new route (retrieval, chats, sessions, completions, feedback).

```python
try:
    scope = await acting_scope(data.tenant_id)            # handler_support.py:26-30
    if scope is None: return not_found_response()
    denied = forbid_unless(scope, AREA, ACTION)           # handler_support.py:33-35
    if denied is not None: return denied
    view = await run_blocking(EXECUTOR, fn, *args, timeout=...)   # blocking.py:36-52
    return json_result(view)
except ServiceError as exc:
    return service_error_response(exc)
```

`NOT_FOUND` is always the same body (service_errors.py:34-35), so an absent id, another workspace's id and a teammate's private assistant or session cannot be told apart (D-19). Provider failures map to 4xx/5xx but never to an authentication failure (service_errors.py module note). Executors: `DB_EXECUTOR` (MySQL), `PROVIDER_EXECUTOR` (embedding, rerank, chat setup), `DOCSTORE_EXECUTOR` (Elasticsearch). A missed deadline becomes `provider_timeout` for the provider pool and `operation_timeout` for the others.

### Request validation
**Source:** `dataset_api.py:55-69`, `parse_api.py:38-45`
**Apply to:** all request bodies. `model_config = ConfigDict(extra="forbid")`; ids and tenants with `Field(default=None, pattern=r"^[0-9a-f]{32}$")`; numeric bounds are a service check that raises a typed `ServiceError(Kind.INVALID, reason, msg)` (dataset_api.py `_whole` 158-164), not a raw pydantic 400, so the reason string reaches the SPA.

### Service error helpers
**Source:** `chunk_service.py:61-70`, `knowledgebase_service.py:145-154`
**Apply to:** every new service module. Private one-line factories `_not_found()`, `_index_unavailable()`, `_invalid(msg, reason)` returning `ServiceError`; messages never hold a host, key, SQL or the caller's input (service_errors.py module note).

### Logging
**Source:** `chunk_service.py:206`, `llm_service.py:231-232`
**Apply to:** retrieval, chat, rerank. Log ids and exception class names only: `logger.warning("... dataset=%s error=%s", dataset_id, type(exc).__name__)`. Never the question, chunk text, prompt, key or provider body. Structured usage fields must not contain the substring `token` (`usage_log_fields`, llm_service.py:89-99: the redactor masks any such field).

### Cross-tenant isolation (D-19; the Phase 4 miss)
**Source:** `test/testcases/test_phase3_isolation.py`, `_matrix_fixtures.py`, `test_response_leaks.py`, `_leak_sweep.py`
**Apply to:** every new implemented registry row, in the same plan that lands the route (research risk R7).

1. `phase3_rows()` (isolation.py:57-64) collects every implemented row whose path starts with `PHASE3_PREFIXES` (line 52). `POST /api/v1/datasets/search` is therefore picked up at once and fails `test_every_phase3_row_has_an_invoker` until an invoker exists. Extend the tuple with `"/api/v1/chats"` and `"/api/v1/chat/"` for the new families.
2. Add an invoker per row to `INVOKERS` (232-262); signature `(w: World, who, token, as_tenant) -> httpx.Response`, built with `call(w.client, METHOD, PATH, token, {}, body=_body(as_tenant, ...))`. Rows that delete or change data get a `PREPARE` entry (347-351) creating a disposable assistant or session. Add the key to `ID_ROWS` (283-308) when it is addressed by an id, to `NORMAL_IS_REFUSED_ON_A_RESOURCE` (268-281) when a member is refused by an object rule (update/delete of someone else's assistant), and to `PROVIDER_CALLING_ROWS` (308) for completion and search (a refused call must not reach the fake provider).
3. Matrix: `resource_of(row)` (_matrix_fixtures.py:302-322) maps a row to a `World.snapshot()` section; add branches for `/api/v1/chats...` and `/api/v1/datasets/search` and a `snapshot_chats()` beside `snapshot_chunks` (219-227). Rows with path params need a `BUILDERS` entry returning `Target(ids, _sender(METHOD, TEMPLATE, body, extra_fields=set()), w.snapshot_x)` (e.g. 560-563); rows without (`/api/v1/chats`, `/api/v1/datasets/search`, `/api/v1/chat/completions`) need a `NO_ID_CHECKS` entry (988-1000). `coverage_problems` (1003-1020) fails the suite on a gap or a stale key.
4. Leak sweep: add `sweep_chat_rows(s, w)` modelled on `sweep_chunk_rows` (test_response_leaks.py:680-745; `s.req(row, label, method, path, token, body)` for success, bad body, absent id, malformed id, private-as-member, outsider; `s.errors(row, method, path, "PUT")` for no credential, bogus bearer, wrong method) and call it where line 917-919 calls the others. `test_every_implemented_row_is_exercised_on_a_success_and_an_error_path` (931) requires one 2xx and one 4xx per row. A completion call in the sweep uses `client.request` and reads the whole stream, which is fine.
5. Banned response keys (`_leak_sweep.py:21-24`): `password`, `secret`, `salt`, `ticket`, `otp`, `access_token`, `dialog_id`, `delete_time`, and `status` / `source` outside the system rows. Use `finish`, `chat_id`, `permission`, `origin`. The key `token` exactly is a "credential key"; `usage.total_tokens` and `input_tokens` are fine.
6. New assertions specific to Phase 5, in the same file style as `test_a_private_dataset_is_the_one_404_on_every_dataset_and_document_route_for_everyone_but_its_creator` (579): a private assistant is the one 404 for owner and admin, a teammate's session id is the one 404, a stored reference is redacted after the dataset flips to `me`.

### Authorisation helpers (object-level rules)
**Source:** `api/db/services/tenant_scope.py:100-125`; `api/apps/permissions_gen.allowed`
**Apply to:** dialog_service, conversation_service, retrieval_service. The coarse matrix cannot express "own" (tenant_scope.py:12-14); the object rule lives in the service, the route only does `acting_scope` and `forbid_unless` for the one matrix row (`datasets.retrieval_test`). Judge on the permission **subject**, not the role, so an API token is never elevated (`ActingScope.subject`, tenant_scope.py:35-41; chunk_service.py:143 does the same).

### Executors and deadlines
**Source:** `api/utils/blocking.py:27-52`, `chunk_api.py:36-39`
Handler timeouts sit above service timeouts so the typed error wins (comment at chunk_api.py:38). Never use the loop's default executor.

### Valkey usage (turn lock, synonym cache, rate guard)
**Source:** `common/ratelimit.py:35-60` (client per call, `socket_timeout=2`, closed in `finally`, fail closed with a typed `...Unavailable`), `rag/svr/task_lock.py:19-66`. Every key sets a TTL (`volatile-lru` policy, research Pitfall 13); the synonym cache tolerates eviction.

### Frontend: workspace-scoped queries and cache refresh
**Source:** `hooks/use-chunk-request.ts:13-16, 27-40, 83-95`; `hooks/use-workspaces.ts:30-34`
Keys start `["ws", tenantId, ...]`; queries `retry: false`, `placeholderData: keepPreviousData` on paged/filtered lists, `enabled` false until the workspace is known (FE-01, FE-02); mutations `retry: false`, `gcTime: 0`, invalidate in `onSettled` (FE-03).

### Frontend: text-node rendering of server text
**Source:** `services/chunk-service.ts:3-5` ("Chunk text is user and document text: it is bounded and rendered as a text node only"), `phase4-source-gate.test.ts`. Applies to assistant names, document names, passages, greetings and answers. Answers pass through the one safe markdown component; nothing else renders markup.

---

## No Analog Found

| File or behaviour | Role | Data flow | Reason | Use instead |
|---|---|---|---|---|
| SSE parsing and the `fetch` stream in `web/src/services/sse.ts` | service | streaming | The SPA has no streaming client; all calls are axios | Research Pattern 7 and UI-SPEC "HTTP client rules"; reuse `http.ts` auth/purge/`ApiError` pieces |
| Server-side SSE generation (frame writer, stop persistence) | route | streaming (text/event-stream) | Only a binary byte stream exists (`page_api._body`); no event stream, no cancellation-persist code | Research "SSE frame writer and cancellation-safe persistence"; copy `_body`'s `finally` + `EXECUTOR.submit` rule |
| Read-time reference redaction (`{index, unavailable: true}`) | service | transform | No stored object carries chunk text with a later permission flip | Research Pattern 5; reuse `dataset_visible` per distinct `dataset_id` |
| `web/src/components/markdown-content/*` | component | transform | No markdown renderer exists and the packages (`react-markdown`, `remark-gfm`) are not installed | UI-SPEC "Answer rendering" table; packages behind the D-21 checkpoint, plain-text fallback otherwise |
| Citation marker hold-back and `##N$$` -> pill pre-processing | utility | transform | New to this phase | UI-SPEC "Marker hold-back (R-27)"; shared regex `/##(\d+)\$\$/g` |
| Avatar picker (file input + canvas resize to a data URL) | component | file-I/O | No picker exists (`AvatarInitials` only displays) | UI-SPEC field table "Picture"; `avatarDataUrl` in `components/avatar-initials.tsx:7` is the prefix gate to reuse |
| `rag/nlp/synonym.py` Valkey-cached dictionary | utility | request-response | Valkey is used for queues, locks and counters, not as a read-through cache | `common/ratelimit.py` client handling; research RETR-04 |

## Metadata

**Analog search scope:** `api/apps`, `api/db` (models, services, migrations), `rag/llm`, `rag/nlp`, `rag/svr`, `rag/utils`, `common`, `conf`, `docker`, `scripts`, `Makefile`, `test/helpers`, `test/unit_test`, `test/integration`, `test/testcases`, `web/src` (services, hooks, components, pages, constants, locales, test, test/server-areas).
**Files scanned:** about 95 (read in full or by range); grep over `api`, `rag`, `common`, `web/src` for type and constant sites.
**Facts that change the plan and are easy to miss:**
- The ES port forbids new parameters, so `must_not` rides in `condition` (es_conn.py + doc_store_base.py:3-4); it must apply to the kNN filter too.
- `phase3_rows()` auto-requires an isolation invoker for `POST /api/v1/datasets/search` the moment the row is flagged implemented.
- Migration 0002 builds tables from the current models, so 0003 must be a safe no-op on a fresh database.
- The rerank type must be added in six places (tenant_model_service, llm_service, provider_service, model_defaults_service, provider_api, web `ModelType`), not one.
- `LLMBundle._report_usage` is a blocking MySQL write inside an async method (BE-07); the streaming turn is its first real caller.
- Python route families default to `streaming: true` (3600 s) in `scripts/gen_routes.py:84`, so no streaming flag is needed for the completion row; only the `body_limit` families are new.
**Pattern extraction date:** 2026-10-19
