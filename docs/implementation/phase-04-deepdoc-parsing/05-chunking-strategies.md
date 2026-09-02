## Objective
Implement specific chunking strategies (General, Q&A, Manual) using the structured output from layout and OCR.

## Why Now?
DeepDoc outputs structured pages, but Vector DBs need semantically sized chunks (e.g., 500 tokens).

## Dependencies
- 04-table-structure

## Implementation Tasks
- [ ] Implement `GeneralChunker`: merges paragraphs until max token size, keeping table markdown intact.
- [ ] Implement `Q&AChunker`: specifically looks for Question/Answer patterns.
- [ ] Ensure chunks retain metadata (page number, bounding box coords for citation highlighting).

## Components
- Chunker Engine

## Files
- `deepdoc/chunker/general.py`
- `deepdoc/chunker/qa.py`

## Interfaces
N/A

## Data Changes
N/A

## Data Flow
DocumentStructure -> Chunker -> List[ChunkDict]

## Testing
- Verify chunks adhere to token limits and don't split mid-sentence.

## Deliverable
Final chunking output ready for vectorization.

## Definition of Done
- System reliably converts complex PDFs into an array of clean text chunks with metadata.

## Next Subphase
Phase 05 - 01-task-queue-models