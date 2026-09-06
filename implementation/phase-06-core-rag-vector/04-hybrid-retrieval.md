## Objective
Implement Hybrid Retrieval (combining Dense Vector Search and BM25 Full-Text Search).

## Why Now?
Dense search alone is insufficient for precise keyword matches.

## Dependencies
- 03-indexing-pipeline

## Implementation Tasks
- [ ] Implement query embedding.
- [ ] Execute Vector Similarity Search (KNN).
- [ ] Execute BM25 Full-Text Search (if using Elasticsearch).
- [ ] Merge results and apply Reciprocal Rank Fusion (RRF) or weighted sum scoring.

## Components
- Retrieval Service

## Files
- `rag/nlp/retrieval.py`

## Interfaces
N/A

## Data Changes
N/A

## Data Flow
Query -> Embed Query -> Search Vector DB -> Merge Results -> List[Chunks]

## Testing
- Integration test with specific queries testing both keyword and semantic matches.

## Deliverable
Hybrid search engine.

## Definition of Done
- `search(query)` returns the most relevant chunks combining both methodologies.

## Next Subphase
05-reranking-engine