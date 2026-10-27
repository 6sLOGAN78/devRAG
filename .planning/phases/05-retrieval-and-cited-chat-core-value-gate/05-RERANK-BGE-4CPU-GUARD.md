# Phase 5 real CPU rerank timing (R-219)

Measured 2026-10-26T15:18:55.083497+00:00 through the production TEIRerank driver, batches of 32, five repetitions per row.
The input is repository documentation cut with count_tokens to the stated cl100k token lengths; TEI uses its own tokenizer and truncates at its model limit.

| Pairs | Chunk tokens | p50 seconds | p95 seconds | Pairs/second |
|---|---|---|---|---|
| 16 | 512 | 14.0435 | 14.9626 | 1.14 |

Chosen rerank cap at p95 <= 5 s for 512-token chunks: **None**.
Peak sampled container memory: **2234.37 MiB** (docker stats working-set proxy for RSS, sampled throughout the run).
Memory limit with 25% headroom rounded up to 256 MiB: **2816m**.
Restart-to-health with weights already cached: **8.173 seconds**.
Image uncompressed size: **937659489 bytes**.
Model volume: `devrag-stack_tei_data                                              2         3.446GB`.
Backend startup log: `2026-10-26T15:16:49.250698Z  INFO text_embeddings_backend: backends/src/lib.rs:751: Downloading 'onnx/model.onnx'`.
The retrieval pool remains top_k = 1024; only the cross-encoder window is capped.
