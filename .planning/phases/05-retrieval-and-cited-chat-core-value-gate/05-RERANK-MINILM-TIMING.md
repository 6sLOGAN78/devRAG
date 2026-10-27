# Phase 5 real CPU rerank timing (R-219)

Measured 2026-10-26T15:01:01.511194+00:00 through the production TEIRerank driver, batches of 32, five repetitions per row.
The input is repository documentation cut with count_tokens to the stated cl100k token lengths; TEI uses its own tokenizer and truncates at its model limit.

| Pairs | Chunk tokens | p50 seconds | p95 seconds | Pairs/second |
|---|---|---|---|---|
| 16 | 128 | 0.8863 | 1.2640 | 18.05 |
| 32 | 128 | 1.9898 | 2.4664 | 16.08 |
| 64 | 128 | 4.6921 | 5.4865 | 13.64 |
| 128 | 128 | 7.2436 | 8.0968 | 17.67 |
| 256 | 128 | 15.7105 | 16.5029 | 16.29 |
| 1024 | 128 | 62.4198 | 68.9301 | 16.41 |
| 16 | 512 | 4.0462 | 4.6264 | 3.95 |
| 32 | 512 | 11.3143 | 12.9303 | 2.83 |
| 64 | 512 | 18.9502 | 21.6911 | 3.38 |
| 128 | 512 | 19.3936 | 26.0081 | 6.60 |
| 256 | 512 | 38.3075 | 46.9396 | 6.68 |
| 1024 | 512 | 174.3547 | 218.9194 | 5.87 |

Chosen rerank cap at p95 <= 5 s for 512-token chunks: **16**.
Peak sampled container memory: **592.80 MiB** (docker stats working-set proxy for RSS, sampled throughout the run).
Memory limit with 25% headroom rounded up to 256 MiB: **768m**.
Restart-to-health with weights already cached: **4.569 seconds**.
Image uncompressed size: **937659489 bytes**.
Model volume: `devrag-stack_tei_data                                              1         3.446GB`.
Backend startup log: `2026-10-26T14:23:24.044543Z  INFO text_embeddings_backend: backends/src/lib.rs:751: Downloading 'onnx/model.onnx'`.
The retrieval pool remains top_k = 1024; only the cross-encoder window is capped.
