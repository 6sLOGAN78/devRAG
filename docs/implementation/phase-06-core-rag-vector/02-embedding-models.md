## Objective
Integrate LLM providers (via LiteLLM or direct SDKs) to convert text into dense vector embeddings.

## Why Now?
Text chunks must be converted to float arrays to be stored in the Vector DB.

## Dependencies
- 01-vector-db-adapters

## Implementation Tasks
- [ ] Integrate `litellm` library.
- [ ] Create `EmbeddingEngine` wrapper handling API keys, rate limits, and batching.
- [ ] Support models like `text-embedding-3-small`, or local HuggingFace embeddings.

## Components
- Embedding Engine

## Files
- `rag/nlp/embedding.py`

## Interfaces
- Outbound to OpenAI/Ollama APIs.

## Data Changes
N/A

## Data Flow
Text -> Embedding API -> Float[]

## Testing
- Unit test embedding generation with a mock API key.

## Deliverable
Text-to-vector capability.

## Definition of Done
- Engine can reliably return vectors for text inputs.

## Next Subphase
03-indexing-pipeline