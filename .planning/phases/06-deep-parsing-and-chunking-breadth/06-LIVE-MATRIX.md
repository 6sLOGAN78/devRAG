# Phase 6 proposed live-test inventory

Approval pending; all calls below are made only by the explicitly selected Phase6 live suite, with one module-scoped ledger incremented before requests. Deterministic fixtures never make cloud calls. Native quality/performance probes run separately under bounded CPU/time limits, are unbilled local validations and are logged separately from the selected-live local-ASR cap.

| Class | Planned request inventory | Proposed cap |
|---|---|---:|
| Chat-class |1 provider save,2 source-supported answer turns,2 keyword batches,2 question batches,2 tag batches,2 metadata batches,1 résumé extraction,3 RAPTOR summaries:15 planned,5 headroom |20|
| Vision |1 save probe,1 PDF figure (repeats dedup),1 DOCX figure,1 PPTX figure,1 standalone image,1 figure-backend caption |6|
| Hosted OCR / document inference |Mistral save+parse2, Paddle job1, Tencent job1,SoMark job1:5 planned,1 headroom |6|
| External parser submits |Docling1,MinerU1,Paddle1,Mistral1,Tencent1,SoMark1,OpenDataLoader1,Figure1 |8|
| Local ASR in this selected live suite |1 save probe,1 WAV,1 MP3 |3|
| Query embeddings |Bounded source/summary retrieval/answer checks, including declared fallback |12|
| Embedded source/summary chunks |Planted corpus plus real enrichment/summary outputs |200|

OCR/vision operations that are also counted as parser submits are cross-classified, not added twice to a claimed invoice total. HTTP status polling of a single submitted job is bounded by a deadline/attempt cap and is logged separately; a resubmit consumes another slot. All provider probes, cancellations and retries count before submission. No hidden repair loop, no suite-wide paid replay. Real actual usage/token counters and fixture/model/endpoint IDs are recorded after each attempt, including failure/teardown.

Cloud provider credentials and compatible service URLs are prerequisite checks; existing OpenRouter access cannot pretend to be Tencent/Mistral/SoMark/Paddle access. Absent required real evidence blocks that part of the final gate. Do not fabricate screenshots, native measurements or real-service passes from test transport fixtures. The final Phase6 gate preserves earlier Phase5 paid evidence and records its disjoint historical failed-attempt spend.
