---
phase: 06-deep-parsing-and-chunking-breadth
plan: "17"
subsystem: email-mime
requirements-completed: []
---

# Plan06-17: Read email envelopes and message bodies

A member can upload .eml, save Email and retrieve decoded From/To/Subject/Date, message ID, selected body and ignored attachment provenance. Plain alternatives win deterministically; HTML-only messages use the existing inert extractor. Attachments, inline images and nested forwarded-message payloads are never executed, fetched or claimed parsed. MIME source8MiB, selected decoded body1MiB, parts128, depth16 and header/recipient/filename caps bound processing. Invalid declarations, charset/transfer errors, unreadable bodies and insufficient envelope budgets refuse with fixed typed errors. Unknown/absent dates are retained without invented values. Related start and mixed body ordering are tested.

Email has a distinct config/chunker, repeating the actual envelope/MIME labels on bounded body chunks without fabricated geometry. Optional typed EmailEnvelope preserves existing ParsedBlock constructors; ordinary chunk text carries provenance through existing authenticated index/retrieval/source views, so no new route/DTO/schema is needed. Upload defaults, MIME/environment catalog, Python/Go/frontend method availability and EN/ZH helper copy agree; explicit operator allowlists remain effective. Existing form disables only ignored delimiter/overlap controls and preserves effective chunk size. Actual app/worker code hashes match the workspace.

Original6069-byte EML and annotation were frozen before product code; core and supplemental malformed-MIME RED evidence retained. Final focused12pass; sharedglue307; markedunit2564/8existing skips plus reviewed127 (all12 Email cases and CI tooling) and legacyunmarked51. Frontend2179/110files, Go, rebuilt services85, actual Chrome save/parse/retrieve/source1, CI7/security/OpenAPI/admission pass. Screenshot visually inspected; multilingual subject/addresses and ignored attachment labels visible, numeric52/73 and excluded traps asserted in real worker/index/browser. Detailed command log hashes and images in06-17-VERIFICATION.json.

Review fixed stale test expectations exposed by broader checks: old helper text omitted EML, old parser-config checks still called QA/Paper unbuilt, and source-view checks still called PNG unsupported after Picture implementation. Refusal/ownership assertions remain intact; failure logs retained. Reboot interrupted initial build/reset hostmap; observed262144 and all services healthy before current live checks. Exact96 unused/unshared immutable regular build cache records reclaimed987.7MB under existing authorization, image inventory identical. No images/volumes/containers/networks/project files deleted. No new package/model, paid call or localASR submission. All3 prior ASR calls remain exhausted and spelling acceptance remains narrow.

Inline review only; R248 accepted automatically, not user-reviewed. No REQUIREMENTS checkbox changes. Phase5 final human acceptance,Phase4B36/fullPhase6gate/UAT remain pending. Continue18 Resume.
