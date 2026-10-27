# Phase 5 real CPU rerank timing (R-219)

Measured 2026-10-26T14:24:24.595948+00:00 through the production TEIRerank driver, batches of 32, five repetitions per row.
The input is repository documentation cut with count_tokens to the stated cl100k token lengths; TEI uses its own tokenizer and truncates at its model limit.

| Pairs | Chunk tokens | p50 seconds | p95 seconds | Pairs/second |
|---|---|---|---|---|
| 16 | 512 | 1.5617 | 1.9085 | 10.25 |

Chosen rerank cap at p95 <= 5 s for 512-token chunks: **16**.
Peak sampled container memory: **638.60 MiB** (docker stats working-set proxy for RSS, sampled throughout the run).
Memory limit with 25% headroom rounded up to 256 MiB: **1024m**.
Restart-to-health with weights already cached: **5.036 seconds**.
Image uncompressed size: **937659489 bytes**.
Model volume: `devrag-stack_tei_data                                              1         3.446GB`.
Backend startup log: `2026-10-26T14:23:24.044543Z  INFO text_embeddings_backend: backends/src/lib.rs:751: Downloading 'onnx/model.onnx'`.
The retrieval pool remains top_k = 1024; only the cross-encoder window is capped.
