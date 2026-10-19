# Phase 5 discussion log

**Date:** 2026-10-19
**Mode:** default, answered as plain-text numbered choices
**Areas selected:** all four (1 2 3 4)

## 1. Rerank model source
| Question | Options | Chosen |
|---|---|---|
| Where the real reranker comes from | 1 local TEI CPU container; 2 Jina/Cohere key; 3 OpenRouter if it has rerank | **1 and 3**: TEI is built and guaranteed; an OpenRouter rerank driver is added too if research confirms one exists (D-01, D-02) |
| Rerank required or optional | 1 optional per assistant (docs); 2 always on | **1** (D-03) |
| CPU candidate cap (R-52) | 1 keep 1024 default, configurable cap, time and record; 2 cap low now | **1** (D-04) |

## 2. Answer model and cost
The user asked whether option 1 also goes through OpenRouter. Yes: every chat option is an OpenRouter model on the same key, and only the TEI reranker is local.

| Question | Options | Chosen |
|---|---|---|
| Answer model | 1 llama-3.1-8b via OpenRouter (switch if citations unreliable); 2 stronger OpenRouter model now; 3 user names it | **1** (D-05) |
| Real chat calls per gate run | 1 about 10–15; 2 about 30–50; 3 no hard cap | **1** (D-06) |
| Accuracy check | 1 planted facts, cite the right chunk, key words; 2 plus an LLM judge | **1** (D-07) |

## 3. Who creates assistants
The user answered "11 1 1", read as 1, 1, 1, 1 and confirmed in the reply.

| Question | Options | Chosen |
|---|---|---|
| Who can create | 1 any member; 2 owner/admin only | **1** (D-08) |
| Visibility | 1 private by default, shareable to team; 2 always workspace-wide | **1** (D-09) |
| Datasets a shared assistant may use | 1 shared → team datasets only, private → any the creator can open; 2 any the creator can open; 3 teammate must open all | **1** (D-10) |
| Sessions | 1 private per user; 2 shared on shared assistants | **1** (D-11) |

## 4. Chat page and citations
| Question | Options | Chosen |
|---|---|---|
| Assistant settings depth | 1 core settings, advanced later (Partial); 2 everything now | **1** (D-12) |
| Citation click | 1 side drawer with chunk and highlighted PDF region; 2 hover popover text only; 3 both | **1** (D-13) |
| Stop | 1 keep partial answer, marked stopped; 2 discard | **1** (D-14) |
| Empty response | 1 friendly default, editable, no model call; 2 model answers from own knowledge | **1** (D-15) |

## Carried forward, not asked
OpenRouter key (P3 D-01/D-25), `##N$$` (R-27), SSE framing per docs (R-26, research closes it), 404 cross-tenant (P3 D-20), Python owns routes, test discipline, fail-closed doc-store writes (P4 lesson). These are recorded as D-16..D-22.

## Claude's discretion
TEI image and model; default threshold, weight and top N from the docs; session naming and paging; how an unavailable bound dataset is reported.

## Deferred
Advanced assistant settings; citation hover; non-OpenRouter chat proof; Phase 4 open items (B-36, B-34, R-190).
