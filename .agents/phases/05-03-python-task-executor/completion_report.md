## Architecture Discovered
- **API Framework**: Quart (async Python web framework) running via Hypercorn.
- **Task Execution**: Async processing to free up Quart's main event loop for accepting tasks.
- **Storage**: `Minio` client wrapping `fget_object`.
- **DeepDoc**: Used existing `TxtParser`, `MarkdownParser`, and `GeneralChunker`.
- **Database**: Peewee with models established in Phase 05-01.

## Actual Call Chain
`POST /api/v1/ml/parse_document` (api/apps/ml.py)
   → `run_parsing_background` (asyncio task in api/apps/ml.py)
   → `loop.run_in_executor` (threadpool execution)
   → `ParsingService.process_task` (api/services/parsing_service.py)
   → `StorageService.download_file` (api/services/storage_service.py)
   → `TxtParser.parse` (deepdoc/parsers/txt_parser.py)
   → `GeneralChunker.chunk` (deepdoc/chunker/general.py)
   → `DocumentChunk.insert_many` (batch peewee inserts)
   → `task.save()` (status success)

## API Contract
- **Endpoint**: `POST /api/v1/ml/parse_document`
- **Request**: `{"task_id": "...", "document_id": "..."}`
- **Response**: `200 OK` `{"status": "accepted", "task_id": "..."}`
- **Errors**: `400 Bad Request` if missing parameters.
- **Idempotency**: The implementation is idempotent; existing chunks for the same document are explicitly cleared (`DocumentChunk.delete()`) before persisting new chunks, meaning multiple parsing executions safely overwrite the output state rather than appending duplicates.

## Task Lifecycle
- **Execution state**: Validates if `status == 'running'`.
- **Success**: Status -> `success`, Progress -> `100`, Document Parse Status -> `success`.
- **Failure**: Caught exceptions invoke `_fail_task` mutating Status -> `failed` and writing an error message.

## Files Changed
- `api/apps/ml.py` (added route)
- `api/services/parsing_service.py` (created business logic)
- `api/services/storage_service.py` (created minio wrapper)
- `tests/unit/test_python_task_executor.py` (E2E integration test)

## Tests
`test_parse_document_api` successfully issues HTTP request, verifies immediate `accepted` status, executes background threaded execution (mocking minio download), invokes the real `TxtParser` and `GeneralChunker`, persists into a live SQLite temporary file, and accurately tracks output success states and final chunks length.

## Next Subphase
05-04 frontend progress UI

## Redis Distributed Lock
As required, `RedisDistributedLock` was implemented in `common/redis_conn.py` to synchronize distributed tasks (such as progress updates, GraphRAG indexing, and dataset modifications) across instances, ensuring concurrency correctness in Python workers outside of DB transactions.
