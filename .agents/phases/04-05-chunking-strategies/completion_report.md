## Implemented
- `deepdoc/chunker/__init__.py`
- `deepdoc/chunker/models.py`
- `deepdoc/chunker/base.py`
- `deepdoc/chunker/general.py`
- `deepdoc/chunker/qa.py`
- `deepdoc/chunker/manual.py`
- `tests/python/test_chunker.py`
- `test_complex_document.py`
- `.agents/contracts/deepdoc-chunking.md`

## Chunk Model
```python
class SourceRegion(BaseModel):
    page: int
    bbox: List[float] | None = None

class Chunk(BaseModel):
    id: str | None = None
    text: str
    chunk_index: int
    page_numbers: List[int]
    source_regions: List[SourceRegion]
    source_block_ids: List[str]
    content_type: str = "text" # "text", "table", "qa"
    metadata: dict[str, Any]
```

## Strategies
GeneralChunker: Dynamically merges TextBlocks inside a sequence up to `max_tokens`. Skips layouts strictly mapped as `header` or `footer` gracefully preventing pagination drift in retrieval semantics. Yields isolated Tables synchronously. Safely fragments oversized nodes along punctuation boundaries enforcing compliance reliably.
QAChunker: Aggregates logical `Q:` prefix variants grouping sequential `A:` blocks implicitly preventing retrieval disconnection. Re-injects preceding Question logic across massively chunked answer components safely bridging token limits.
ManualChunker: Processes granular boundaries dynamically injected from an external document UI context skipping automatic traversal logic unconditionally.

## Token Counting
Tokenizer/counting method: `tiktoken` (`cl100k_base` BPE encoder)
Default max tokens: `500` (configurable)
Minimum tokens: `0` (configurable)
Overlap: `0` (configurable)

## Table Handling
Normally bound tabular structures are fully rendered deterministically via markdown semantics natively outputting independent `content_type="table"` chunks cleanly. Large tables horizontally breaking standard maximum token limits safely partition along vertical row sequences reliably preserving initial table headers directly onto fragmented sub-blocks dynamically.

## Q&A Handling
Patterns recognized dynamically: `Q:`, `Question:`, `A:`, `Answer:`
Oversized Answer blocks gracefully truncate internally enforcing sequential splits mathematically whilst actively persisting the explicit Question text payload directly onto every emitted subset avoiding unindexed context collapse seamlessly.

## Metadata Verification
document_id: YES
page: YES
bbox/source regions: YES
content type: YES
source block IDs: YES

## Tests
Chunk model tests: 1
General chunker tests: 4
Q&A tests: 1
Manual chunker tests: 1
Table tests: 1 (handled in general tests)
Integration tests: 1
Total: 8
Passed: 8
Failed: 0

## Complex Document Verification
Fixture: `test_complex_document.py`
Pages: 2
Chunks generated: 3
Maximum chunk size: Compliant
Tables preserved: YES
Q&A preserved: YES
Multi-column ordering: Handled inherently via layout structures implicitly inherited from 04-03 reading orders.
Metadata preserved: YES
Result: SUCCESS

## Architecture Verification
04-01 contract preserved: YES
04-02 OCR reused: YES
04-03 layout reused: YES
04-04 table structure reused: YES
Phase 03 preserved: YES
Database unchanged: YES
API unchanged: YES
Embeddings deferred: YES
Vector DB deferred: YES

## Deviations
None.

## Next Phase
Next Subphase: 05-01 — Embedding Models & Vector Abstraction
