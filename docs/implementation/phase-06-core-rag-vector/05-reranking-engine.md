## Objective
Integrate a Cross-Encoder model (e.g., BGE-Reranker or Cohere Rerank) to rescore top-K results.

## Why Now?
Reranking dramatically improves final RAG context accuracy.

## Dependencies
- 04-hybrid-retrieval

## Implementation Tasks
- [ ] Integrate reranking API or local HuggingFace cross-encoder.
- [ ] Wrap the `search` pipeline: fetch Top-50 -> Rerank -> Return Top-K.

## Components
- Reranker

## Files
- `rag/nlp/rerank.py`
- `rag/nlp/retrieval.py` (update)

## Interfaces
- Outbound to Rerank API (if using external).

## Data Changes
N/A

## Data Flow
Top-N Chunks + Query -> Cross-Encoder -> Sorted Top-K Chunks

## Testing
- Compare search accuracy with and without reranker on a test dataset.

## Deliverable
High-precision retrieval engine.

## Definition of Done
- Reranking successfully sorts the most relevant chunks to the top based on cross-attention.

## Next Subphase
Phase 07 - 01-graph-execution-model