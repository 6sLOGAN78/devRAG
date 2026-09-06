# DeepDoc Chunking Contract

## Pipeline
```text
DocumentStructure (04-01 Models + 04-02 OCR + 04-03 Layout + 04-04 Table)
       ↓
BaseChunker (General / QA / Manual)
       ↓
List[Chunk]
```

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
The `metadata` dynamically pulls fields from the root `DocumentStructure`, e.g., `document_id`.

## Chunker Interface
`BaseChunker` defines the generic interface containing `token_counter` configuration alongside `max_tokens`, `min_tokens`, and `overlap_tokens`.
```python
def chunk(self, document: DocumentStructure) -> List[Chunk]:
    ...
```

## Token Counting
Uses OpenAI's `tiktoken` string tokenizer implicitly bound to `cl100k_base` semantics. This avoids full LLM embeddings during the chunking phase, delivering fast and deterministic character counting.

## Strategies
- **GeneralChunker**: Sweeps the structured PageNodes top-to-bottom. Aggregates normal `TextBlock`s until the `max_token` constraint is triggered. Evaluates layout annotations gracefully omitting isolated `header` and `footer` blocks to prevent recurrent metadata pollution. Isolates `TableBlock` entities cleanly emitting them dynamically via markdown tabular serialization as standalone chunks. Sub-splits extremely large textual nodes safely via deterministic sentence boundaries (using Regex punctuation grouping).
- **QAChunker**: Explicitly buffers and binds Q&A semantics natively parsing standard prefix structures (`Q:`, `Question:`, `A:`, `Answer:`). Binds matched contextual questions deterministically alongside their sibling textual answers directly circumventing conventional `max_token` thresholds on answer fragmentation (it prepends the Question string natively back onto multi-chunk oversized Answer continuations).
- **ManualChunker**: Relinquishes heuristic boundary tracking passing full declarative chunk boundaries externally via an explicit `chunk_blocks()` list array function. Fallbacks into 1:1 Block to Chunk serialization against unmapped parameters.

## Metadata Tracking
Metadata natively projects multi-page provenance coordinates inside the unified `Chunk` instance preserving arrays of `page_numbers` alongside exact dimensional `source_regions` linking explicitly back to phase 04-02 coordinates mapping. This ensures granular origin referencing without iterative layout inference.

## Limitations
Vectors arrays and vector storage layers intentionally defer to 05-xx implementations.
