## Objective
Create a unified Vector Database adapter interface in Python to abstract specific implementations (e.g., Elasticsearch, Infinity).

## Why Now?
RAG requires scalable semantic search.

## Dependencies
- Vector DB running in docker (Phase 01)

## Implementation Tasks
- [ ] Define `BaseVectorStore` abstract class (insert, delete, search, create_index).
- [ ] Implement `ElasticsearchAdapter` or `InfinityAdapter`.
- [ ] Write schema initialization logic to create Vector Indices when a Dataset is created.

## Components
- Vector DB Adapter

## Files
- `rag/utils/vector_store.py`
- `rag/utils/es_adapter.py`

## Interfaces
N/A

## Data Changes
Creates indices in Vector DB.

## Data Flow
Python App -> Vector Store API

## Testing
- Unit test inserting and retrieving a mock vector.

## Deliverable
Vector DB abstraction layer.

## Definition of Done
- Application can communicate with Vector DB regardless of underlying technology.

## Next Subphase
02-embedding-models