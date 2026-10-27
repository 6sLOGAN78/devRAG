# Phase 5 live citation adherence (plan 05-13)

Five planted-fact questions were asked three times per model through the real completion route with temperature 0.
A result cites the planted chunk when a valid final marker points to its reference chunk and the answer contains the numeric fact.
A fallback-inserted marker counts as a raw no-marker answer for the switch rule.

Rule: keep the 8B model only with at least 14 of 15 planted citations and at most 2 raw no-marker answers; otherwise test `openai/gpt-4o-mini` once.

## meta-llama/llama-3.1-8b-instruct

| Fact label | Run | Valid indices | Cites planted | Raw no marker | Fallback repaired |
|---|---:|---|---|---|---|
| Zorblax-4417 | 1 | 0 | yes | no | no |
| Zorblax-4417 | 2 | 0 | yes | no | no |
| Zorblax-4417 | 3 | 0 | yes | no | no |
| Quenthar-9082 | 1 | 0 | yes | no | no |
| Quenthar-9082 | 2 | 0 | yes | no | no |
| Quenthar-9082 | 3 | 0 | yes | no | no |
| Plimsby-3356 | 1 | 0 | yes | no | no |
| Plimsby-3356 | 2 | 0 | yes | no | no |
| Plimsby-3356 | 3 | 0 | yes | no | no |
| Brantwell-6130 | 1 | 0 | yes | no | no |
| Brantwell-6130 | 2 | 0 | yes | no | no |
| Brantwell-6130 | 3 | 0 | yes | no | no |
| Oskarine-8847 | 1 | 0 | yes | no | no |
| Oskarine-8847 | 2 | 0 | yes | no | no |
| Oskarine-8847 | 3 | 0 | yes | no | no |

Planted citations: 15/15; raw no-marker: 0/15; fallback repaired: 0/15; chat requests: 15/20 maximum.

## Outcome

**keep**: meta-llama/llama-3.1-8b-instruct

Pinned `CITATION_RULES` SHA-256: `de84e758fc405a78d1b83c00dfa5f85dfa27d651c2c206c8c04ce2b5ffb714b6`.

Standing gate signal for plan 05-25: at least 6 of 7 planted-fact turns cite the planted chunk.


Live attempt 1 (2026-10-27): stopped after 2 passed / 1 failed in 30.15 s. Both hard streamed TXT/PDF source checks passed. The rerank-off Quenthar-9082 turn answered that it could not find the answer and cited index 0 (wrong fact), failing the unchanged numeric-answer assertion. App usage logs independently count 3 chat turns, 6 query embeddings (including citation fallback), and 4 local TEI requests; provider save adds one chat connection test. Seven chunks were ingested. No OpenRouter rerank call or browser live turn ran. The account was cleaned by the fixture. Six deterministic real-stack regressions confirm all planted TXT facts reach generation without rerank. Under D-05 the live model is switched to openai/gpt-4o-mini for attempt 2; no prompt or citation assertion is weakened. A fixture teardown will print non-secret budget counts even if the next attempt fails. The retry is a separate measured attempt and its spend must not be hidden.
