---
phase: 03
scope: backend
depth: standard
files_reviewed: 58
status: issues_found
critical: 0
warning: 9
info: 10
---

# Phase 3 backend code review

Reviewed 58 backend files (Python under `api/`, `common/`, `rag/`; `internal/common/logger.go`; the three scripts; routes, permissions, service-conf and compose files; `Dockerfile`; `pyproject.toml`). `CLAUDE.md` and everything under `web/` were skipped as instructed. No source file was modified.

Overall: the parts the focus list worried about most held up. Details I traced and found sound:
- Provider keys never reach a response, log, exception message or metric. The `repr`s hide them, `SecretStr` is used, `ModelException` is built from a parsed body, and validation errors do not echo input.
- AAD binding is consistent between `seal_key`, `open_key` and every call site.
- The SSRF guard covers decimal, hex, octal, short, IPv4-mapped, NAT64 and 6to4 spellings, and the chat, embedding and test paths all re-validate on each attempt.
- No client redirects are followed on any path.
- Authorization is consistent: scope is derived from the dataset or the principal, the permission subject is used and never the inherited role, and `me` datasets are hidden.
- The upload path checks the cap, count, magic bytes, size, byte-compare before blob reuse and storage cleanup on failure.
- Every ES read, update and delete is AND-ed with the `kb_id` filter.
- The rate limiter fails closed.

There are no Critical findings. The Warnings are availability and defence-in-depth gaps around provider calls, one residual key-fragment path, the Nginx catch-alls, key rotation, and log redaction.

Accepted limits (R-136 to R-153) were not re-reported. Where I think an acceptance is unsafe, the finding says so (BE-05).

## Warnings

### BE-01 (Warning) Provider calls have no total deadline, and a timed-out request still commits its save
**Files:** `rag/llm/chat_model.py:254-263`, `rag/llm/embedding_model.py:201-202`, `api/db/services/provider_service.py:199-277`, `api/utils/blocking.py:32-45`, `api/apps/restful_apis/provider_api.py:150-152`

**Scenario:**
- Every driver timeout is an httpx per-phase timeout (`timeout=seconds`). A tenant-chosen base URL that trickles one byte every few seconds never trips it.
- `Base.chat` and `Base.encode` have no `asyncio.wait_for` or overall wall-clock bound.
- `save_provider` runs on `PROVIDER_EXECUTOR`, which has 8 threads. The handler gives up after 50 s with 504 `provider_timeout`. The worker thread cannot be cancelled and keeps going.
- Two things follow.
  - A workspace admin who points a base URL at a slow-drip server can pin all 8 provider threads. The limiter allows 10 saves per 300 s per workspace, so this is easy. Every other tenant's provider save, add-model and key test then queues and times out. This is a cross-tenant availability problem.
  - When a slow-but-finishing provider makes the handler return 504, the abandoned worker later passes the tests and runs `save_instance`, which commits. The client sees a failure for a provider that is now saved, and the rate ticket is already spent.

**Fix:**
- Put a hard total deadline on each test call. For chat, wrap `loop.run(self.async_chat(...))` in `asyncio.wait_for(..., timeout=self.timeout)`. For embeddings, enforce a deadline across the batch loop, or use an `httpx.Timeout` plus a watchdog.
- Make the sum of the service deadlines (2 models x deadline) smaller than `PROVIDER_TIMEOUT_SECONDS`, and validate that when settings load (`key_test_timeout_seconds` is allowed up to 86400).
- Pass a cancellation flag into `save_provider` and check it just before `save_instance`, so a request the handler already abandoned does not write.

### BE-02 (Warning) Provider response bodies are read without a size cap
**Files:** `rag/llm/chat_model.py:258-263` (`_on_response` calls `await response.aread()` and slices to 64 KiB only afterwards), plus the OpenAI/Azure/Ollama embedding paths and the non-streaming chat path.

**Scenario:** An admin sets base URL `https://attacker.example`. On save (and on every later call) that server answers 400/500 with a multi-GB, or endless, body. `aread()` buffers all of it in the app process. The OpenAI SDK also reads error bodies fully, so removing the hook would not fix it. The dev container limit is 768 MB, so one authenticated admin can OOM the single `app` container that also hosts Nginx, the Go API and Python.

**Not verified:** I did not run a PoC.

**Fix:** Give the `httpx` clients a size-limiting transport. Wrap `httpx.AsyncHTTPTransport` and `HTTPTransport` and raise once a running byte counter passes a cap, for example 64 KiB for error responses and 8 MiB for success bodies. Pass it as `transport=` in `_Session` and `_http()`. In the hook, read with `aiter_bytes` and stop at `_BODY_LIMIT`.

### BE-03 (Warning) Echoed-key scrub runs after truncation, so a key prefix can survive
**Files:** `rag/llm/errors.py:49-52` (`safe_text` cuts to 200 characters), `api/db/services/provider_service.py:182-193` (`_scrub(exc.safe_message, key)`), `api/db/services/llm_service.py:108-110` and `:128-132`

**Scenario:**
- A provider (OpenAI-compatible gateways often do this) answers `{"error":{"message":"... Invalid key <KEY> ..."}}`.
- The key is not `sk-` shaped, for example a 32-hex Azure or compatible key. `redact_text` therefore cannot mask it, and only the exact-match `text.replace(key, "***")` protects it.
- `safe_text` has already cut the message to 200 characters. If the key straddles character 200, the exact key is no longer in the string and the prefix is returned in the 400 body.
- I reproduced it with a 32-character key placed at offset 190: the output ended `... key ab12cd34ab` after `_scrub`, which is 10 of the 32 characters.
- The response goes to whoever made the call. For a save without a new key, or any later `LLMBundle` error, that caller never typed the key. This breaks "nobody can read a key back".

**Fix:**
- Scrub before truncating. Give `ModelException` a `secrets` parameter (or a `scrub` callable). The order is then: remove control characters, replace each secret, `redact_text`, then cut to 200.
- Have `_failure` and `bundle_error` pass the key in at construction time and not afterwards.
- Also scrub the key's last 8 and first 8 characters when the key is at least 16 characters long, because providers print masked forms.

### BE-04 (Warning) Nginx catch-alls accept 1 GiB bodies and 3600 s timeouts before authentication
**Files:** `conf/routes.yaml:83-84`, `:55-66`; `scripts/gen_routes.py:23-24,66-68` (`PY_BODY_LIMIT = "1024m"`, python `streaming` defaults to true); generated `docker/nginx/ragflow.conf:85-104,141-152,222-233`; `api/apps/__init__.py:34`

**Scenario:**
- The comment in `gen_routes.py` says Python locations "keep the upload allowance ... until upload routes exist and narrow them". The upload route now exists with `101m`, and the Phase 3 families have `1m`.
- The catch-alls `/api/` and `/v1/`, plus `/api/v1/system/healthz` and `/api/v1/system/status` and their aliases, still have `client_max_body_size 1024m` and `proxy_read_timeout/send_timeout 3600s`.
- Nginx buffers the request body (`proxy_request_buffering` is not turned off) before Python's gate can answer 401. An unauthenticated client can therefore POST up to 1 GiB per connection to any unlisted `/api/...` or `/v1/...` path. This costs disk and bandwidth, and `client_body_timeout 30s` only bounds a stalled client.
- Quart's global `MAX_CONTENT_LENGTH` is also 1 GiB.
- The Phase 3 JSON families (`/api/v1/providers`, `/models`, `/datasets`) inherit the 3600 s timeouts, although none of them stream.

**Fix:**
- In `routes.yaml`, give the catch-alls and the two status/healthz rows `body_limit: 16k` (or `1m`) and `streaming: false`. Only the upload row keeps `101m` and `streaming: true`. Flip the python default of `streaming` to false, and require the future SSE routes to opt in.
- Set `app.config["MAX_CONTENT_LENGTH"]` to a few MiB. The upload handler already sets a per-request cap.
- Regenerate with `gen_routes.py`.

### BE-05 (Warning) Master-key rotation is advertised but cannot work (a decision I consider unsafe)
**Files:** `common/security/secretbox.py:16,102-113`, `common/settings.py:209-214`, `docker/.env.example` (`LLM_KEY_ID` comment), `api/db/services/tenant_llm_service.py:58-82`

**Scenario:**
- `secretbox` documents "seal uses the active kid; open_ uses the kid named in the envelope", and `.env.example` tells operators to change `LLM_KEY_ID` when rotating.
- `keyring_from_settings` returns a single-entry keyring `{llm.key_id: key}`, and there is no setting for retired keys.
- An operator who sets `LLM_KEY_ID=k2` with a new key makes every stored envelope `v1:k1:...` fail with `KeyError`. That surfaces as `key_unreadable` (503) for every model, and for every save that tests with the stored key.
- Recovery means every workspace admin re-entering every provider key.
- Changing only the key value and keeping `k1` fails the same way.
- Losing `LLM_KEY_ENCRYPTION_KEY` already means losing all keys, which the comment states. A routine rotation shouldn't have the same effect.

**Fix:**
- Add `llm.previous_keys`, a `kid:base64` list, for example `LLM_KEY_ENCRYPTION_KEY_PREVIOUS=k1:...`. `keyring_from_settings` returns the active key plus all previous ones.
- Add a one-shot `scripts/reseal_keys.py` that opens with the keyring and re-seals every `tenant_llm.api_key` with the active kid.
- Until then, remove the "change it when rotating" advice from `.env.example` so nobody follows it.

### BE-06 (Warning) Elasticsearch `query_string` is built from raw user text
**File:** `rag/utils/es_conn.py:119-126` (`_text_query`)

**Scenario:**
- `matching_text` goes unescaped into `query_string`. `lenient: True` only tolerates type mismatches. Syntax errors still raise `parse_exception` (HTTP 400), for example an unbalanced quote or parenthesis, a trailing `AND`/`OR`, or a trailing `:`.
- A user question such as `what is (revenue` becomes `BadRequestError`, which `_guard` turns into `DocStoreError("document store search failed")`, so the search fails for an ordinary question.
- `allow_leading_wildcard` defaults to true, and `*`, `?`, regex `/.../` and `~` fuzzy are live. A single member query like `*a*b*c*` is an expensive scan over a shared tenant index.
- The `kb_id` filter keeps results inside the dataset, so this is a robustness and DoS issue and not a leak.

**Not verified:** I did not run it against ES.

**Fix:**
- Use `simple_query_string` with `flags` limited to `AND|OR|PHRASE|PREFIX` (it never throws).
- Or keep `query_string` but add `"allow_leading_wildcard": False, "analyze_wildcard": False, "fuzzy_max_expansions": 10, "max_determinized_states": 1000`, and escape reserved characters (`+ - = && || > < ! ( ) { } [ ] ^ " ~ * ? : \ /`) in the adapter. Keep the query-builder's `^boost` syntax out of the escape.
- Put the choice in the port contract so Infinity behaves the same way.

### BE-07 (Warning) Async `LLMBundle` methods run blocking DNS and database work on the event loop
**Files:** `api/db/services/llm_service.py:213-219,248-262`, `rag/llm/chat_model.py:273-285` (`_check_target` -> `validate_base_url` -> `socket.getaddrinfo`), `api/db/services/tenant_llm_service.py:134-139`

**Scenario:** `async_chat` and `async_chat_streamly` are documented to "run on the caller's loop". Two blocking calls happen inside them.
- `_check_target` resolves the host synchronously on every attempt. `getaddrinfo` has no timeout (the `url_guard` docstring says callers must run it in a bounded executor).
- `_report_usage` calls `add_used_tokens`, a synchronous MySQL `UPDATE` with the pool's 30 s read/write timeouts.

A slow resolver or database stalls every request on the loop, including health probes. Phase 5 chat streaming will use exactly these paths.

**Fix:**
- In the async driver, run `self._check_target` through `await asyncio.to_thread(...)` or a named executor.
- In the async bundle methods, run `_report_usage` through `run_blocking(DB_EXECUTOR, ...)`.
- Add a unit test that fails when `socket.getaddrinfo` or `DB.execute_sql` is entered with a running loop.

### BE-08 (Warning) Python log redaction skips non-string `extra` values
**File:** `common/log_utils.py:121-130` (`redact_value`), `:133-141`

**Scenario:** `redact_value` handles `dict`, `list`, `tuple` and `str`; everything else is returned unchanged and `JsonFormatter` renders it with `json.dumps(default=str)` after redaction. I confirmed that `logger.info("x", extra={"err": ValueError("api_key=abc123def456")})` writes `"err": "api_key=abc123def456"`. Sets, bytes and arbitrary objects behave the same way. The Go twin handles `error`, `[]byte` and arbitrary values, so the two implementations disagree. No current caller passes such a value (all current `extra=` uses are strings and ints), so this is a trap for Phase 4 and later, such as `extra={"error": exc}`.

**Fix:** Add a final branch to `redact_value`: for any non-primitive (`not isinstance(value, (int, float, bool, type(None)))`), return `redact_text(str(value))`. Handle `bytes` and `BaseException` explicitly. Add a vector to the shared Python/Go/Nginx vector file.

### BE-09 (Warning) Dataset and document `parser_config` is size-checked only
**Files:** `api/db/services/knowledgebase_service.py:195-205`, `:466`, `api/db/services/document_service.py:106-122`, `api/apps/restful_apis/document_api.py:140-152`

**Scenario:**
- Any JSON object of 4096 characters or fewer is stored and merged over the defaults. The keys the Phase 4 chunker reads, `chunk_token_num`, `pages`, `delimiter`, `layout_recognize`, `auto_keywords`, `table_context_size` and `image_context_size`, have no type or range check. Examples: `{"chunk_token_num": -5}`, `{"pages": "x"}`, `{"delimiter": 7}`.
- The values are persisted and returned as-is, and a bad one is hit only when a worker parses a document. Failing at the API with 400 is the project's own rule ("input validation").
- A deeply nested object also reaches `json.dumps`, which raises `RecursionError` past roughly 1000 levels. It is not caught by `except (TypeError, ValueError)`, so that is a 500.

**Not verified:** The Phase 4 consumer does not exist yet.

**Fix:**
- Add a `ParserConfig` pydantic model (`extra="allow"` with typed known keys). For example, `chunk_token_num` is 1..8192, `pages` is a list of `[int, int]` pairs, `delimiter` is a string of at most 64 characters, `auto_keywords` is 0..32.
- Validate in `_validate` and `_parser_for`, and catch `RecursionError`.

## Info

### BE-10 (Info) `add_models` can attach a stale envelope after a concurrent key rotation
**File:** `api/db/services/tenant_model_service.py:316-330` against `:262-267`

`add_models` reads the stored envelope with a plain `SELECT` inside a REPEATABLE READ transaction and then inserts new `tenant_llm` rows with it. A concurrent `save_instance(replace_key=True)` can commit in between. That rotation updates only the rows listed in `own_names`, and the new rows are not among them. The new model keeps the old, possibly revoked, key and shows as configured until its first call fails. Both operations are admin-only and rate limited, so the window is narrow.

**Fix:** Read the envelope with `.for_update()` on the instance row (`TenantModelInstance`) in both `add_models` and `_write_save`, or take the same named lock (`kb-create`-style, per instance) around both.

### BE-11 (Info) Upload transactions are not retried on a deadlock and lock files in a different order than deletes
**Files:** `api/db/services/file_service.py:100-107` (`reuse_or_store` locks candidates in `create_time` order), `:134-139` (`release_files` locks by sorted id), `api/db/services/document_service.py:197-222`

R-143 documents the retry for deletes only. A multi-file upload that locks several candidate file rows in `create_time` order can deadlock against another multi-file upload in a different dataset (different named lock) or against a multi-document delete (sorted id). MySQL picks a victim and the upload surfaces as a 500 with a clean rollback. The SPA sends one file per request, so only API clients that batch hit it.

**Fix:** Order candidates by `File.id` before locking, and apply the same `DEADLOCK_ATTEMPTS` retry used in `_remove_rows` around the `_store` transaction (re-seeking the streams between attempts).

### BE-12 (Info) `create_dataset` releases its lock without guarding `LockError`
**File:** `api/db/services/knowledgebase_service.py:324-325`

`finally: lock.release()` raises `LockError` when `RELEASE_LOCK` does not return 1, for example after a dropped lock connection. That exception replaces the return value after the dataset row is committed, so the client gets a 500 for a dataset that now exists. `_named_lock` (same file, `:437-450`) and `upload_documents` already guard this.

**Fix:** Use `with _named_lock(create_lock_name(tenant_id), LOCK_TIMEOUT_SECONDS, "another dataset is being created, try again shortly"):` in `create_dataset`.

### BE-13 (Info) Elasticsearch adapter gaps against its documented rules
**File:** `rag/utils/es_conn.py`
- `:279-280`: `order_by` field names are not regex-checked, although R-145 says sort fields are. Only select, highlight and aggregation names are. It is a dict key, so there is no structural injection, but it is inconsistent with the documented rule.
- `:277-278`: `highlight` has no `"encoder": "html"`. Uploaded `.html` files become chunk text, and `_highlight` returns that markup unescaped around `<em>`. Any UI that renders highlights as HTML (rehype-raw) receives attacker-controlled markup.
- `:215-224`: `insert` forces `kb_id` and refuses a missing index, but does not check that a `q_{dim}_vec` field in the row is mapped. With the fixed-dimension dynamic templates removed, a vector for a dimension that `create_idx` never provisioned gets dynamically mapped as plain `float`, which silently loses HNSW. This is the same failure R-145 gives for the missing-index case.
- `:210-232`: documents are indexed with `_id = row["id"]` in a per-tenant shared index, so a caller-supplied id that collides with a chunk of another dataset in the same workspace overwrites it. `get` and `search` are safe because they filter by `kb_id`. The rule that ids are unique per workspace (for example derived from `doc_id`) is unwritten.
- `api/db/services/knowledgebase_service.py:276-279`: `DimensionConflict` is a `DocStoreError`, so it is reported as 503 `index_unavailable` ("try again shortly"), but a retry cannot succeed.

**Fix:** validate `order_by` with `FIELD_RE`; add the html encoder; in `insert`, check `get_field_mapping` for each vector field present (cache per index); prefix `_id` with the dataset id or reject ids that already exist under another `kb_id`; map `DimensionConflict` to a 409.

### BE-14 (Info) Redaction residuals beyond the accepted R-148 / T-03-02-02 limits
**Files:** `common/log_utils.py:44,78-95,67-69`, `internal/common/logger.go:34`
- Values longer than 4096 characters are only masked for their first 4096 (`_BARE`, `_QUOTED` are capped; the possessive quoted match fails and the bare fallback masks 4096). I confirmed `password=` + 5000 characters leaves 904 characters of the tail in the output. Accepted limits mention the 512-character key-shape cap only.
- A URL `https://ghp_token@host/` is kept as is: `_redact_userinfo` redacts only a password after a colon.
- The `ragflow-` API-token shape is masked by Nginx only; the Python and Go redactors do not mask it in free text.
- A double-encoded JSON fragment (`\"api_key\": \"...\"`) is not matched by `KEYSEP` in Python or by the Go pattern.

**Fix:** when a run hits the cap, mask to the end of the line or next separator; mask userinfo with no colon as well; add a `ragflow-[A-Za-z0-9_-]{20,}` shape to both redactors and the vector file.

### BE-15 (Info) Ollama chat leaks the eagerly created litellm HTTP client
**File:** `rag/llm/chat_model.py:292-295`

`AsyncHTTPHandler(timeout=...)` builds its own `httpx.AsyncClient` in `__init__` (checked in the installed litellm). The next line assigns `handler.client = session.http`, which replaces `_client` without closing the first client. One unclosed client (and its transport) is created per Ollama chat attempt.

**Fix:** `await handler._client.aclose()` before the assignment, or subclass and override `create_client`. I could not verify whether litellm's `ollama_chat` also reads `OLLAMA_API_KEY` from the environment for the request header (the embedding driver guards that case; the chat path does not).

### BE-16 (Info) File names may contain bidirectional and other format characters
**File:** `api/db/services/upload_rules.py:99-100`

Only category `Cc` is rejected. `invoice\u202Egnp.pdf` is accepted and shown reversed (`invoicefdp.png`) in the document table.

**Fix:** also reject categories `Cf`, `Zl`, `Zp` (and `Cs`).

### BE-17 (Info) Deleting a provider leaves datasets pointing at removed embedding models
**File:** `api/db/services/tenant_model_service.py:459-483`

`delete_provider` clears the workspace defaults but ignores `knowledgebase.embd_id` and `tenant_embd_id`. After the delete, every dataset using that provider's embedding model has a dangling reference. The vectors in the shared index have no model that can re-embed queries. Phase 4 and 5 will fail with `model_unavailable` and no earlier warning.

**Fix:** refuse with 409 `provider_in_use` (listing the dataset count) when any live dataset in the workspace references one of the provider's models, or state in the confirmation UI that datasets must be re-created.

### BE-18 (Info) Duplication, inconsistent constants, file size
- Provider failure mapping is duplicated: `provider_service._failure` (`:186-196`) and `llm_service.bundle_error` (`:99-117`), including the repeated `_REFUSAL_CODES`, `_RATE_LIMIT_STATUSES`, `_SCRUBBED` and `_FALLBACK_REFUSAL`. Use `bundle_error` with a scrubber in both places (this also gives BE-03 one place to fix).
- `MAX_DIMENSION` is 65536 in `tenant_model_service.py:37` but 4096 in `provider_service.py:43` and `MAX_VECTOR_SIZE`; the 65536 check is dead behind the 4096 one.
- `_escape_like` is copied in `knowledgebase_service.py:330` and `document_service.py:291`. `_whole` and the page/size constants are copied in `dataset_api.py` and `document_api.py`. `_guard`, `_TENANT_ID_PATTERN` and `LOOKUP_TIMEOUT_SECONDS` are copied in `provider_api.py` and `models_api.py`. These belong in `handler_support`.
- `knowledgebase_service.py` is 638 lines and mixes create, list, update, delete and DTOs. Split `dataset_delete.py` and the DTO helpers out. `gen_routes.py` is 558 lines with Go and Python templates inline.
- `ESConnection.__init__` passes `es.hosts` as one string while `internal_hosts` splits it on commas; a comma list would break the client.

### BE-19 (Info) Script and compose hygiene
- `docker/docker-compose.dev.yml:41`: `LLM_ALLOW_PRIVATE_BASE_URLS` defaults to **true** for anyone who layers the dev file, which turns off the private-range and loopback protection (container IPs, `127.0.0.1:9380`). Make the default false and have `clean_room.sh` set `DEV_LLM_ALLOW_PRIVATE_BASE_URLS=true` explicitly.
- `scripts/clean_room.sh:51-55`: `MYSQL_ROOT_PASSWORD` is exported to every step (`npm`, `uv`, `go test`) and not only to the Go scratch-database tests that need it. Export it just for those steps.
- `scripts/init_env.sh:20-24`: `--force` regenerates `LLM_KEY_ENCRYPTION_KEY` and the database passwords without saying that existing volumes and sealed provider keys become unreadable. Refuse `--force` when volumes of the project exist, or print that warning.
- `Dockerfile`: base images use mutable tags (`python:3.13-slim`, `golang:1.25-alpine`, `node:22-alpine`); pin digests for reproducible gates. `docker-compose.yml` has no `security_opt: [no-new-privileges:true]` or `cap_drop: [ALL]` for `app`.
- `rag/utils/minio_conn.py:60`: `secure=False` is hardcoded. The credential is never sent in clear (SigV4), but the object bytes are. Make it a setting for deployments where MinIO is not on the private compose network.
- `pyproject.toml`: `ruff` is unpinned in the dev group. Several pins differ from the `CLAUDE.md` table (`quart==0.23.1`, `quart-schema==0.25.0`, `PyMySQL==1.2.3`, `valkey==6.1.1`, `minio==7.2.20`). Check that the later versions are recorded as decisions in `.planning/DECISIONS.md`; I did not find rows for them in R-136 to R-153.

## Files not reviewed fully, or points I could not verify

- `api/apps/auth.py` (the gate), `api/apps/middleware.py`, `api/db/database.py`, `api/db/models/*`, `scripts/lib/compose_project.sh`, `docker/entrypoint*.sh` and the `.github` workflows are outside the file list. I read only the parts needed to confirm behaviour (`DatabaseLock`, `transaction`, `make_resolver`, the error handlers, `ragflow.conf`, `nginx.conf`).
- Not executed: Elasticsearch (BE-06, BE-13), MinIO, MySQL lock and deadlock behaviour (BE-10, BE-11), litellm's internal handling of the injected client for each provider route, and any live provider.
- The redaction behaviours in BE-03, BE-08 and BE-14 were reproduced with small pure-function runs against the real modules.
- The Go logger (`internal/common/logger.go`) was read in full; I found no linear-time or bypass problem beyond the shared residuals in BE-14.
- `web/` is covered by another review.
