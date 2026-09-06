# Phase 06-02 Embedding Models Implementation Report

## Architecture Discovered
- **Existing ML abstractions**: None present in the initial sweep.
- **Provider Infrastructure**: The RAG flow previously lacked direct connections to embedding providers.
- **Local Inference Architecture**: Was absent, allowing the introduction of `sentence-transformers` for CPU/GPU agnostic local vector generation.
- **Rate-limit/Retry**: The repository did not have a shared retry decorator. `tenacity` was introduced to wrap external provider limits resiliently.

## Embedding Contract
- **Input**: `texts: List[str]`
- **Output**: `List[List[float]]` (Strict corresponding float vectors).
- **Ordering**: The engine splits text arrays into exact batches, iterates through the provider, reassembles them, and sorts based on provider indices (where provided) to absolutely guarantee that `texts[N]` maps to `vectors[N]`.
- **Dimension Validation**: Dimension is verified post-response against the configured `EmbeddingConfig.dimension`. Non-matching inputs raise `EmbeddingDimensionError`.
- **Batch Semantics**: A configurable `batch_size` iterates over inputs, preventing large payload failures and guaranteeing order preservation.
- **Errors**: Abstracted using `EmbeddingError` and `EmbeddingDimensionError` instead of raw provider exceptions.

## Providers
### LiteLLMProvider
- **Provider Name**: `litellm`
- **Client**: Uses `litellm.embedding` bridging remote APIs.
- **Batching**: Sends explicit batch sizes defined by configuration. Uses the `'index'` key of the provider response to enforce safe reordering.
- **Retry behavior**: Traps `RateLimitError`, `APIConnectionError`, `APIError`, and `Timeout`. Bounded retry configured via Tenacity (max 5 attempts, exponential backoff from 2s to 10s).
- **Limitations**: Dependent on specific versions of `litellm` (pinned to 1.30.0 for Python 3.10 `NotRequired` type compatibility).

### LocalHFProvider
- **Provider Name**: `huggingface`
- **Client**: `sentence-transformers`
- **Configuration**: Loads the configured model synchronously at class initialization.
- **Batching**: Delegates native batching and ordering to `model.encode`.
- **Retry behavior**: Not applicable for local deterministic CPU/GPU loads.
- **Limitations**: Incurs large memory footprints if multiple distinct models are loaded per process.

## Model / Dimension Compatibility
- Models and expected dimensions are securely bridged using `EmbeddingConfig(provider, model, dimension)`.
- If a vector store expects a `1536`-dimensional index for a `dataset_id`, the next pipeline phase (03-indexing-pipeline) will load the `EmbeddingConfig` for that dataset to safely match dimensions before calling `BaseVectorStore.insert`.

## Local vs Remote
Both architectures implement the `BaseEmbeddingProvider` interface. The `EmbeddingEngine` delegates dynamically at runtime based on `config.provider`. This enables the core ingestion pipelines to swap between an API-based OpenAI model and a local HuggingFace inference node without changing a single line of ingestion logic.

## Files Changed
- `requirements.txt` (Added `litellm`, `tenacity`, `sentence-transformers`)
- `rag/nlp/embedding.py` (Created Engine, Providers, and Config)
- `tests/unit/test_embedding.py` (Created comprehensive test suite)
- `.agents/phases/06-02-embedding-models/completion_report.md` (Created)

## Tests
- **Unit Tests**: Executed `tests/unit/test_embedding.py`. All 6 passed.
- **Batch tests**: Confirmed splitting 3 documents with a `batch_size=2` correctly queries providers twice and maintains a flat 3-element response list.
- **Retry / Rate-Limit tests**: Confirmed that when `litellm` throws a `RateLimitError`, Tenacity traps it and successfully retries.
- **Dimension tests**: Verified that a mismatch between configured `dimension=3` and response `dimension=2` triggers `EmbeddingDimensionError`.
- **Local-model tests**: Validated `sentence-transformers` instantiation and native batch encoding.
- **Lint/type checks**: Tests pass without any logic or import errors.

## Known Limitations
- The current local HF provider does not expose a global model registry mechanism. This means multiple `EmbeddingEngine` initializations for the same local model will load duplicate models into RAM. Future iterations (when multi-model caching becomes critical) will need a Singleton model registry.
- Pricing and token usage reporting are not yet extracted from LiteLLM responses, as the accounting layer has not yet been specified.

## Next Subphase
03-indexing-pipeline
