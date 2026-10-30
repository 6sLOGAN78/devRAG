---
phase: 06-deep-parsing-and-chunking-breadth
plan: "19"
subsystem: tag-ranking
requirements-completed: []
---

# Plan 06-19: Manage tags and produce retrieval rank features

The Tag method now partitions original text while preserving source text and geometry, derives bounded normalized tag weights, and writes labels plus object-valued `tag_feas` to the existing Elasticsearch mapping. The source fixture fixes lighthouse/calibration at 4/5 and retains 52 metres and 73 units. Its existing `*_feas` map is compatible with weighted objects; generic `tag_fea` would match a scalar template, so no mapping migration was needed. Tag cosine uses full vector norms, and `10 * tag_score + pagerank` contributes before and after reranking without changing old unfeatured fusion scores.

Authorized Knowledgebase PageRank is saved at 0–100 and propagated through task, row, manual/edit, and retrieval paths; zero omits the positive-only feature. Dataset tag list, selected delete, and explicit selected-dataset aggregation authorize every dataset before index access, use only current SQL documents, impose document/chunk/label/time bounds, and check exact writes under the existing named upload lock. The UI exposes Tag selection, normalized weights, PageRank, explicit deletion confirmation, and scoped aggregation; late workspace responses are fenced. All 14 chunk methods now agree across Python, Go, frontend catalog and save/reopen.

Initial behavioral RED3 and subsequent index, API, PageRank and UI RED are retained. Final marked unit 2588 passed/8 existing skipped; full web 2183/111 files; affected real services 193; rebuilt-image browser plus dataset 51; tenant matrix17; leak6; Go and CI7/7 passed. Original source and two actual Chrome screenshots were inspected. Current app/worker/native containers are healthy and match recorded built images. See `06-19-VERIFICATION.json` for fixture, log, image, source and screenshot hashes.

Inline review documented the tag mapping choice, current-document and ownership fences, and checked partial-delete reporting. No new package/model, paid external call, or local ASR replay. R250 accepted automatically, not user-reviewed. REQUIREMENTS checkboxes remain untouched. Phase5 human acceptance, Phase4 B36, and the final Phase6 gate/UAT remain pending. Continue Plan20 bounded document metadata.
