# Phase 05-03 Python Task Executor Final Implementation Report

## Architecture Discovered
- **API Framework**: Quart (running via Hypercorn).
- **Task architecture**: Go Syncer pulls `DocumentTask` and `POST`s to Python via `/api/v1/ml/parse_document`. Python uses `asyncio.create_task` + `loop.run_in_executor` for background worker threads to free the HTTP loop.
- **DeepDoc architecture**: Directly instantiates `TxtParser` / `MarkdownParser` and routes the parsed AST to `GeneralChunker`.
- **MinIO architecture**: MinIO Python SDK (`fget_object`) downloaded to a temporary file via `storage_service.py`.
- **DB architecture**: Peewee ORM with transactional insertions.
- **Redis architecture**: Introduced `RedisDistributedLock` mimicking `RAGFlow` to coordinate shared background thread operations.

## Actual Call Chain
`POST /api/v1/ml/parse_document` (`api/apps/ml.py`)
  -> `run_parsing_background` (asyncio task)
  -> `loop.run_in_executor(None, parsing_service.process_task)`
  -> `ParsingService.process_task` (`api/services/parsing_service.py`)
  -> `StorageService.download_file` (`api/services/storage_service.py`)
  -> `TxtParser.parse` (`deepdoc/parsers/txt_parser.py`)
  -> `GeneralChunker.chunk` (`deepdoc/chunker/general.py`)
  -> `DocumentChunk.insert_many()`
  -> `RedisDistributedLock("update_progress")` (progress update)
  -> `task.save()`

## Task Lifecycle
- **Initial**: `unstart`
- **Running**: Go daemon changes to `running` via `SKIP LOCKED` query.
- **Progress**: Updated to 100 on successful DB insertion via `RedisDistributedLock`.
- **Success**: Status changes to `success` post-insertion.
- **Failure**: Caught exceptions mark status `failed` and append `error_msg` safely via `_fail_task()` also under the progress lock.

## Redis Coordination
### `update_progress`
- Used inside `ParsingService._fail_task` and `process_task` final save blocks.
- Protects the progress update critical section from being overwritten incorrectly.
- Degraded mode fallback: If Redis is unavailable, it catches `TimeoutError` and falls back to transactional SQLite/MySQL saves so parsing is not completely halted, but logs the timeout.

### `clean_task_executor`
- Used in `api/services/executor_cleaner.py` (`clean_task_executor_loop`) running asynchronously inside the Quart event loop.
- Periodically (5 min) queries for `DocumentTask`s stuck in `running` for >30 minutes.
- Only the instance that acquires the `clean_task_executor` lock can execute the destructive cleanup, preventing duplicate cleanup races across multiple Quart workers.

## DeepDoc
- Reused `TxtParser`, `MarkdownParser`, and `GeneralChunker`.

## Storage
- `minio.Minio` client wrapping `fget_object`. Bucket name and object are parsed directly from the document's `minio_path`.

## Database
- Atomic `DocumentChunk.delete()` and batch `DocumentChunk.insert_many()` mapped against the task. Duplicate handling clears existing chunks safely before appending, providing strict idempotency.

## Files Changed
- `api/services/parsing_service.py` (added distributed lock)
- `common/redis_conn.py` (created RedisDistributedLock)
- `api/services/executor_cleaner.py` (created cleaner worker thread)
- `api/apps/__init__.py` (started cleaner worker on app start)
- `tests/unit/test_python_task_executor.py` (added mock for Redis lock)

## `.agents`
- Verified and read Phase 05 constraints as instructed.

## Tests
- **API/E2E Tests**: `test_python_task_executor.py` verified the immediate HTTP `200` return and exact successful asynchronous threading, DB chunk updates, and status toggles.
- **Redis Mocking**: Tested fallback handling by validating that the test suite does not hang when a live Redis server is unavailable.

## Known Limitations
- Progress updates are currently a binary 0 -> 100 because the current chunker implementations do not fire granular callbacks.

## Next Subphase
05-04-frontend-progress-ui
