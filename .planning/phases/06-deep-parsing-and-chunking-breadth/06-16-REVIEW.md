# Plan06-16 inline review

Reviewed the actual changed native decoder/service, capability/default/credential glue, parser/chunker/index/search/API views, model/Picture compatibility and Audio/source UI against the frozen plan and current contracts. No sub-agent was used. Original fixture inputs and approved acquisition packet stay unchanged.

- Native boundary: exact local model/manifest verification before advertisement; CPU int8/2threads/1worker; no VAD/fetch; explicit byte/duration/sample/channel/result caps. One shared authenticated executor slot and timeout keep uncancellable native work bounded. Corruption/silence/oversize/options/language and malformed result contracts exercised.
- Model ownership: ASR bit4 preserves chat1/embed2/vision8/rerank16 and reservedtts32; same legacy/composite identities. Only current active tenant model/instance opens credentials. ASR permits only DeepDoc and exact operator service/model. Existing Tenant ASR default slots set/read/delete; sealed-key paths remain separate.
- Worker/source: named provider pool/limiter, cancellation before queued operation/after result; no host native imports. Original document identity and validated seconds reach index/chunkAPI/retrieval/source, with absent PDF geometry. Oversize segment/context refuses instead of truncating.
- UI/schema: real configured model and explicit language inputs, no automatic transcription when settings save. Default selector changes only ASR slot; no secrets/URLs in local provider form. Source and inspector render validated seconds/plain source text. EN/ZH, generated schema/types and Go/Python/UI availability checked.

Resolved finding: malformed native400 JSON list caused an AttributeError rather than a fixed unavailable refusal. The intended RED is retained inphase6-16-refusal-red.log; parser client now validates refusal shape. Focused19green and current rebuilt service/browser gates own regression evidence.

Observed model-quality exception: firstWAVbeam1 and MP3beam5 both recovered52/73 but emitted light house. Original live assertions failed. User explicitly accepted only lighthouse/light house spelling equivalence; transcript bytes remain unchanged. Both original failure logs, observations, derived accuracy metrics and approval are retained. Captured realWAV output is replayed through actual index and accepted outputs are evaluated offline; no fourth local ASR request is authorized. Tests reject wrong/swapped values. Originalbeam1 WAV also says calibration of set; currentbeam5 MP3 says calibration offset. No word-perfect/general accuracy claim.

Environmental failures: reboot-reset map limit and stopped services were restored after usercommand/verification. Later low disk caused MinIO write refusals; narrowly authorized cache cleanup reclaimed3.383GB with identical image inventory, and isolated upload passed after cleanup. Old unavailableAudio fixtures now use still-unbuiltResume, retaining exact refusal assertions. Final rebuilt services89 and Chromechoice1 passed beforeR247/summary.

No unresolved high-severity finding identified. Phase5 final human acceptance, Phase4B36, fullPhase6gate/UAT remain separately pending.
