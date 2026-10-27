# Phase 5 real CPU rerank timing (R-219)

Measured 2026-10-26T09:26:06.174728+00:00 through the production TEIRerank driver, batches of 32, five repetitions per row.
The input is repository documentation cut with count_tokens to the stated cl100k token lengths; TEI uses its own tokenizer and truncates at its model limit.

| Pairs | Chunk tokens | p50 seconds | p95 seconds | Pairs/second |
|---|---|---|---|---|
| 16 | 512 | 12.0788 | 13.1678 | 1.32 |

Chosen rerank cap at p95 <= 5 s for 512-token chunks: **None**.
Peak sampled container memory: **5448.70 MiB** (docker stats working-set proxy for RSS, sampled throughout the run).
Memory limit with 25% headroom rounded up to 256 MiB: **6912m**.
Restart-to-health with weights already cached: **10.198 seconds**.
Image uncompressed size: **937659489 bytes**.
Model volume: `devrag-stack_tei_data                                              1         3.354GB`.
Backend startup log: `2026-10-26T09:24:02.821512Z  INFO text_embeddings_backend: backends/src/lib.rs:751: Downloading 'onnx/model.onnx'`.
The retrieval pool remains top_k = 1024; only the cross-encoder window is capped.

## Outcome and measurement scope

**B-37: the approved BGE model misses the required latency floor.** Five 16-pair runs at 512 tokens took 13.0750, 12.0788, 12.0446, 11.9489 and 13.1910 seconds, with p95 13.1678 seconds against the 5-second budget. The server used ONNX, AVX2, a provisional 6 GiB memory cap and 4096 internal batch tokens. No production rerank cap or final memory limit is selected from this failed guard.

The initial 512-internal-token configuration was also measured: N=16 at 128 tokens p50 7.338 s / p95 8.214 s; N=32 at 128 tokens p50 13.774 s / p95 15.464 s. That full run was interrupted to test the more efficient 4096-token batch configuration first. The remaining 6-size by 2-length matrix is not run: the smallest long-chunk window already fails, and plan 05-15 requires a smaller model or user decision at that point. This is incomplete benchmark coverage, not a passing full timing gate.

The initial ONNX downloader left an incomplete blob. A direct download of the identical approved revision passed the published SHA-256 before provisioning. Startup exceeded the initial 3 and 4 GiB limits (Docker OOM events with exit 137). The temporary 6 GiB limit is sufficient for the tested 4096-token configuration. The memory recommendation above is informational until the model decision; it has not been applied.
