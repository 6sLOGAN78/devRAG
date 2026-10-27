---
phase: 06-deep-parsing-and-chunking-breadth
plan: "05"
subsystem: document-assets
requirements-completed: []
---

# Plan 06-05: Open extracted images and office figures securely

PDF embedded images and detected vector figure/table crops, plus safe DOCX/PPTX image relationships, now reach typed bounded image descriptors. DeepDoc normalizes PNG/JPEG pixels into deterministic metadata-free PNG; API/worker remote paths do not decode images. Original byte/hash fixtures stay fixed. PDF rectangles retain canonical actual page geometry; Office images carry no fabricated page coordinates. Legacy unconfigured Office behavior still counts skipped images. No runtime acquisition or package/model change.

Planned DocumentAsset migration0004 was applied on actual MySQL and verified from an empty scratch database, including idempotent rerun;39 registered tables and generated Go entities/schema agree. Opaque IDs and unique tenant/document/kind/SHA ownership prevent global digest access. Current task and shared operation-log generation fence writes under the existing dataset mutation lock; bytes never enter embedding text, chunk DTOs or Elasticsearch. Only a current successfully published original document's assets are listed/downloaded after dataset visibility; authorization is rechecked after object I/O. Unknown/foreign/private/deleted/stale IDs refuse; token roles remain their actual credential subject.

Scoped duplicate images reuse one owned object/ID; identical images in another document keep separate ownership and storage keys. Successful reparse collects obsolete rows/objects, and shared file deletion covers document and dataset deletion. Lost/cancelled workers cannot publish after object writes; best-effort compensation preserves the original control signal. MinIO assertions verify actual object removal and cross-document preservation. Failed storage cleanup remains the existing best-effort logged-orphan limitation, with authorization already removed.

The authenticated PNG route uses no-store, nosniff, sandbox and exact length. Generated policy/OpenAPI/types and real route invokers/matrix/leak coverage are wired. The existing source drawer fetches header-authenticated blobs, renders captions as text, supports retry, and revokes URLs on source/workspace changes. Actual Chrome shows the readable original52/9100 Office figure next to the literal hostile-markup source passage. Assistant visual review is not user UAT approval.

Verification: full unit2421passed/8existing skips; frontend2143passed105files plus71focused; affected real service regressions121passed; fresh migration14passed; final rebuilt native03/04/05, PDF/Office Chrome and document-detail32passed; real new-route matrix5passed and response/log leak sweep6passed. Go internal and actual schema checks, build, CI7/7, security/async lint and unchanged exact admission pass. See06-05-VERIFICATION.json and complete06-05-FILES.txt inventory. No paid call, requirement checkbox or full-phase completion claim.

## Deviations and review

Supplemental shared glue includes the pure asset codec, byte normalizer/client, explicit PDF wire serialization, Office relationship reader, document-detail DTO, file/progress cleanup, generated schema/policy/TS outputs, fixture cleanup and real matrix snapshots. These changes are necessary to connect the declared parser/service/UI path; no unrelated feature is claimed. Original docs/06-CONTRACTS ownership and native boundaries are preserved. Inline review was used; no agents were authorized.

Retained intended REDs cover missing typed descriptors, Office transport, native normalize endpoint, ownership service, PDF asset response, region crop and frontend image journey. Rejected setup failures (wrong upload MIME, empty Bearer header, mistyped expected Office sentence) were corrected against unchanged frozen source bytes. A stale legacy detail assertion that treated supported page ranges as unknown was replaced by an actual unknown key plus a positive persisted-pages/layout check. Explicit38-table expectations were updated to the planned39th relation. No model/quality threshold or original fixture was tuned to pass.

Next06 reconstructs structured PDF tables through the pinned TSR model and this owned crop path. Phase5 UAT5/6 and Phase4 B36 remain separate and pending; the complete Phase6 gate is still pending.
