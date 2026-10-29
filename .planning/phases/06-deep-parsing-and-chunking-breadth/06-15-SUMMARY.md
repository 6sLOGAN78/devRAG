---
phase: 06-deep-parsing-and-chunking-breadth
plan: "15"
subsystem: picture-vision
requirements-completed: []
---

# Plan06-15: Caption pictures with a configured vision model

Picture now normalizes PNG/JPEG in approved DeepDoc, then sends bounded PNG data bytes to the configured workspace vision model through the existing guarded transport and named provider executor. The fixed prompt treats image instructions as untrusted data; remote image URLs, empty/oversize captions and missing models refuse. Explicit OCR-only mode returns real native text/spans instead. Captions and chunks retain authenticated generation-owned original-image IDs; no PDF geometry is invented. Provider usage survives failures and captions use existing credential scrubbing; queued cancellation prevents provider calls.

OpenRouter and OpenAI-compatible providers support vision. Same-name chat+vision requests preserve one composite/structural identity, sealed key, usage and chat defaults with flags9. Duplicate identical pairs and incompatible metadata combinations refuse; inactive models/instances cannot offer models or open credentials. Vision defaults reuse existing Tenant columns. Existing add-model route, model/default selectors and saved Picture settings carry optional model/OCR controls, with English/Chinese labels. Generated OpenAPI/types and Go availability match; no new dependency, migration, model or paid request.

Verification: root2655passed/8existing skips; frontend2173passed109files; Go allpass. Native/parser/prior browser stack57passed, services85, authorization/OpenAPI/leaks186, model/provider routes20, key/provider71, active-model/credentials33. Latest rebuilt app/worker Chrome1passed, saved vision choice reopened, exact52/73 caption retrieved and owned640x480original loaded; screenshot inspected. Label review found two missing translations: actual RED then locale/default/add-model34passed, rebuild/health/browser repeated. Current CI7/security/generated/admission passed; exact log hashes/image IDs in06-15-VERIFICATION.json, actual files06-15-FILES.txt.

Review: inline self-review. RED exposed missing capability/picture, inactive model/instance access and literal credential reflection; fixes retain tenant ownership. Test-only provider uses deterministic multimodal responses; real paid caption belongs to30. Early browser POST405 and invalid probe PNG were fixture errors corrected before accepted evidence. Legacy unavailable-image fixture became an unknown suffix, keeping exact refusal assertions. UI test focus waits for the existing mount effect; unchanged paging timeout passed with bounded worker concurrency. Native dependencies stay isolated; exact12 runtime manifests and pinned stage digests reused. Approved unused/unshared immutable regular build-cache IDs reclaimed7.118GB with identical image inventory; no container/image/volume/network/project deletion.

R246 accepted automatically, not user-reviewed. Phase5 final human acceptance, Phase4B36 and fullPhase6gate/UAT remain pending. Continue16 Audio/ASR.
