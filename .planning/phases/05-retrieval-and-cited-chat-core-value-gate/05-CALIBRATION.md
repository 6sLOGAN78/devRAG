# Phase 5 retrieval calibration (plan 05-06)

Measured once with the real `baai/bge-m3` embedding model (1024 dimensions) on the planted corpus: one TXT of six paragraphs and one
three-page PDF (`test/helpers/planted.py`), threshold 0 and rerank off, so every returned chunk is scored. Blended similarity is
`(1 - w) * term + w * vector` with w = 0.3. Question wording is not recorded, only a short label.

## Relevant questions (worded without the planted token)

| Label | Weight | Term | Vector | Blended | Fact chunk returned |
|---|---|---|---|---|---|
| coolant temperature of the reactor (TXT) | 0.3 | 0.1667 | 0.5669 | 0.2867 | yes |
| depth of the glacier ice (TXT) | 0.3 | 0.2857 | 0.5104 | 0.3531 | yes |
| weekend bakery sales (TXT) | 0.3 | 0.3333 | 0.5959 | 0.4121 | yes |
| height of the lighthouse (PDF) | 0.3 | 0.6667 | 0.5716 | 0.6381 | yes |
| quince harvest of the orchard (PDF) | 0.3 | 0.5000 | 0.5329 | 0.5099 | yes |

## Irrelevant questions

| Label | Weight | Term | Vector | Blended | Fact chunk returned |
|---|---|---|---|---|---|
| off-topic news question | 0.3 | 0.0000 | 0.3649 | 0.1095 | yes |
| nonsense token string | 0.3 | 0.0000 | 0.3637 | 0.1091 | yes |
| another domain (databases) | 0.3 | 0.0000 | 0.2609 | 0.0783 | yes |
| stopwords only | 0.3 | 0.0000 | 0.4069 | 0.1221 | yes |
| short generic greeting | 0.3 | 0.0000 | 0.3457 | 0.1037 | yes |

## Weight probes (two relevant questions at weight 0 = term only and 1 = vector only)

| Label | Weight | Term | Vector | Blended | Fact chunk returned |
|---|---|---|---|---|---|
| coolant temperature of the reactor (TXT) | 0.0 | 0.1667 | 0.5668 | 0.1667 | yes |
| coolant temperature of the reactor (TXT) | 1.0 | 0.1667 | 0.5668 | 0.5668 | yes |
| height of the lighthouse (PDF) | 0.0 | 0.6667 | 0.5716 | 0.6667 | yes |
| height of the lighthouse (PDF) | 1.0 | 0.6667 | 0.5716 | 0.5716 | yes |

## Supplementary: the wording of the planted-fact tests (rare token included)

| Label | Weight | Term | Vector | Blended | Fact chunk returned |
|---|---|---|---|---|---|
| planted-fact wording: Zorblax-4417 | 0.3 | 0.8333 | 0.7152 | 0.7979 | yes |
| planted-fact wording: Quenthar-9082 | 0.3 | 0.7143 | 0.6623 | 0.6987 | yes |
| planted-fact wording: Plimsby-3356 | 0.3 | 0.7500 | 0.7408 | 0.7472 | yes |
| planted-fact wording: Brantwell-6130 | 0.3 | 0.7500 | 0.6106 | 0.7082 | yes |
| planted-fact wording: Oskarine-8847 | 0.3 | 0.7143 | 0.5987 | 0.6796 | yes |

## Summary of the blended similarity

| Group | Min | Max | Mean |
|---|---|---|---|
| relevant | 0.2867 | 0.6381 | 0.4400 |
| irrelevant | 0.0783 | 0.1221 | 0.1045 |

## Rule

Current default T = 0.20, margin 0.05: keep the current threshold T when the highest irrelevant similarity is below T - 0.05 and the lowest relevant similarity is at or above T + 0.05; otherwise move it to the midpoint of those two values, rounded to the nearest 0.05 and clamped to [0.05, 0.6]; if the lowest relevant similarity is not above the highest irrelevant similarity the threshold cannot separate them and the outcome is blocked (the weights, the tokenizer or the embedding model are the problem).

## Outcome

**keep**, threshold 0.20

Query embeddings spent: 19 of 24 allowed (outside the live budget of D-06).

## Notes

- corpus: 7 chunks in 2 documents
