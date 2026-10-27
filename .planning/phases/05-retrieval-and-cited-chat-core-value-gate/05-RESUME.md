# Phase 5 recovery procedure — archived after completion 2026-10-27

**Current status:** Plans 05-15 and 05-28 are complete. All 28 summaries exist and all automated gate tiers pass; see `05-GATE-LOG.md` and `05-VERIFICATION.md`. Timing is complete (12 rows / 60 samples), cap 16 / dev 3 GiB. B-37/B-39/B-40 are resolved. The outstanding Phase 3/4 live checks passed 17/17 once; the earlier successful Phase 5 API/browser 14-check result was preserved without repeat. No automated suite or timing recovery below remains pending.

**Next work:** human UAT and final validation approval in `05-HUMAN-UAT.md` / `05-VALIDATION.md`. B-36 Phase 4 clean-room verification stays deferred. No commits, requirement changes or Phase 6 advancement are authorized by this handoff. Do not rerun paid calls from this archived procedure as a default resume action.

The remaining text is the historical recovery procedure, retained for provenance; its pending/blocker statements are superseded by the final evidence.

## Environment required

Use a session with permission to access Docker, the local stack and Python asyncio self-pipe sockets. Current-session blockers B-39 and B-40 describe the failures. Do not change auth deadlines or tests to accommodate this restriction. Run from the quoted project path:

```sh
cd '/home/logan78/desktop x/devRAG'
docker ps --format '{{.Names}}\t{{.Status}}'
curl -fsS http://127.0.0.1:6381/health
```

The existing virtualenv activation script points to the old checkout. Use `uv run python` from this directory. In a restricted cache environment, `UV_CACHE_DIR=/tmp/devrag-uv-cache uv run --no-sync python` uses the existing environment without syncing or changing dependencies.

Inspect the active TEI image, command and model revision before measuring; use the approved BGE revision `2cfc18c9415c912f9d8155881c133215df768a70`, four physical performance cores 0,2,4,6 on this host, AVX2 and 1024 batch tokens. Do not print the full container environment. Avoid other test workloads during the missing long-input row.

## Recover only the missing timing row

The eleven-row JSON is the recovered BGE run. MiniLM results have their own explicit filenames. The following one-off command uses the production driver, persists each of five repetitions atomically, and retains the original eleven-row source before merging. It has been syntax-checked; it could not be executed against TEI in the restricted session.

```sh
uv run python - <<'PY'
import asyncio
import hashlib
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path

from common.settings import LlmSettings
from rag.llm import resolve_provider
from rag.llm.rerank_model import TEIRerank
from scripts.probe import time_rerank as probe

phase = Path('.planning/phases/05-retrieval-and-cited-chat-core-value-gate')
source = phase / '05-RERANK-TIMING.samples.json'
original = json.loads(source.read_text())
if any(row['n'] == 1024 and str(row['length']) == '512' for row in original['rows']):
    raise SystemExit('Final row already present; inspect saved evidence before making more calls.')
assert len(original['rows']) == 11
assert all(len(row['seconds']) == 5 for row in original['rows'])
fingerprint = hashlib.sha256(source.read_bytes()).hexdigest()
partial = phase / '05-RERANK-BGE-RECOVERY.samples.json'
progress = json.loads(partial.read_text()) if partial.exists() else {
    'source_sha256': fingerprint, 'n': 1024, 'length': '512',
    'seconds': [], 'peak_mib': 0.0,
}
assert progress['source_sha256'] == fingerprint
assert progress['n'] == 1024 and progress['length'] == '512'
assert 0 <= len(progress['seconds']) <= 5
assert all(math.isfinite(value) and value > 0 for value in progress['seconds'])
container = 'devrag-stack-tei-1'
base = 'http://127.0.0.1:6381'

def save(path, data):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(data, indent=2) + '\n')
    temporary.replace(path)

async def recover():
    driver = TEIRerank(resolve_provider('TEI'), 'BAAI/bge-reranker-base', None, base,
                       llm_settings=LlmSettings(max_retries=0), allow_private=True, timeout=120)
    text = probe.docs_text(512)
    sampler = probe.MemorySampler(container)
    sampler.thread.start()
    try:
        while len(progress['seconds']) < 5:
            start = time.monotonic()
            result = await driver.similarity('How are documents processed and reranked?', [text] * 1024)
            assert len(result.scores) == 1024
            progress['seconds'].append(time.monotonic() - start)
            progress['peak_mib'] = max(progress['peak_mib'], sampler.peak)
            progress['last_updated'] = datetime.now(timezone.utc).isoformat()
            save(partial, progress)
            print(f"Saved repetition {len(progress['seconds'])}/5", flush=True)
        if sampler.error or progress['peak_mib'] <= 0:
            raise RuntimeError(sampler.error or 'No memory samples recorded')
    finally:
        sampler.stop.set()
        await asyncio.to_thread(sampler.thread.join, 125)

asyncio.run(recover())
row = {'n': 1024, 'length': '512', 'tokens': 512, 'seconds': progress['seconds']}
row['p50'] = probe.percentile(row['seconds'], .5)
row['p95'] = probe.percentile(row['seconds'], .95)
row['pairs_per_second'] = 1024 / row['p50']
guard = json.loads((phase / '05-RERANK-BGE-APPROVED-GUARD.samples.json').read_text())
peak = max(original['peak_mib'], progress['peak_mib'], guard['peak_mib'])
cold = probe.cold_start(container, base)
image_id = probe.docker('inspect', '--format', '{{.Image}}', container)
image_bytes = int(probe.docker('image', 'inspect', '--format', '{{.Size}}', image_id))
volume = next(line for line in probe.docker('system', 'df', '-v').splitlines() if 'devrag-stack_tei_data' in line)
backend = 'ONNX; retain and verify the active backend startup line separately'
rows = [*original['rows'], row]
backup = phase / '05-RERANK-BGE-RECOVERED-11.samples.json'
if not backup.exists():
    backup.write_bytes(source.read_bytes())
save(source, {'rows': rows, 'peak_mib': peak, 'provenance': {
    'original_11_rows': backup.name, 'source_sha256': fingerprint,
    'final_row': partial.name, 'cached_restart_seconds': cold,
    'image_bytes': image_bytes, 'volume': volume,
}})
print(probe.render(rows, peak, cold, image_bytes, volume, backend))
print('The report above is measured output. Update the evidence and R-219 after verifying provenance and backend logs.')
PY
```

Preserve the mixed-run provenance and raw recovery repetitions in the final report. Confirm the active ONNX backend from startup logs without copying request contents. Apply `choose_cap(rows)` and `choose_mem_limit(peak)` to the settings/template/example and dev-only memory limit, with matching regressions. The current defaults are 16 and 3 GiB; no final value may be inferred for the missing row. Update R-52/R-219 and B-37 only after completion. Create 05-15-SUMMARY.md when all three plan tasks have evidence.

## Complete the gate in order

1. Rebuild the current tree with `docker compose -p devrag-stack --env-file docker/.env -f docker/docker-compose.yml -f docker/docker-compose.dev.yml --profile cpu --profile elasticsearch --profile mail --profile tei-cpu up -d --build`, then `WAIT_STACK_TIMEOUT=900 scripts/wait_stack.sh`. Retain existing volumes.
2. Rerun the unchanged full Python unit tier after fixing the environment's self-pipe restriction. The restricted-session full run did not complete. The focused offline check passed 172 tests; that does not replace the full tier.
3. Recheck real BGE integration and the retrieval API after applying the final measured limits. The earlier full integration suite (890 plus eight real-TEI cases), Go race/integration-E2E, frontend ingress (61), and deterministic browser results are recorded in 05-GATE-LOG.md. Rerun an affected tier when runtime settings or code changes justify it.
4. Run ordinary E2E with `uv run python run_tests.py -m 'e2e and not serial and not live_model'`. After it exits, run serial E2E with `uv run python run_tests.py -m 'e2e and serial and not live_model'`. Record commands, counts and durations. The paid `live_model` browser case is excluded from these invocations because its successful result is already retained. The serial tier restarts shared dependencies and must run alone.
5. Audit the remaining live-model inventory. The saved 14-check result covers Phase 5 API/browser tests; this log does not contain a completed Phase 3 `test_live_models.py` tier result for this gate. Recover evidence first. If missing, the plan-authorized outstanding file must be run separately and its four chat-class calls and embedding calls recorded. Do not invoke the entire `live_model` tier and repeat Phase 5 calls. R-227/R-228 already account for the failed first attempt and successful retry separately.
6. Finish R-231 and pin LAST_ROW=231 / its required title only after all results are known. Run CI, security/async lint and `PHASE5_GATE=1 uv run python -m pytest test/unit_test/test_phase5_traceability.py test/unit_test/test_phase5_records.py -q`. Keep the missing-summary assertion unchanged.
7. Finish the review/validation sign-off and 05-28-SUMMARY.md from actual results. Keep manual checks pending for the user and preserve B-36. Do not tick requirements or advance to Phase 6 while this gate is incomplete.

## Current results and budget

The successful Phase 5 run spent nine answer turns plus two connection tests (11 chat-class calls), 13 query embeddings, two API-corpus ingestion embedding calls and two external rerank requests including the provider-save test. The browser adds its own ingestion, whose call count is not separately retained in this gate log. The earlier failed attempt spent three answer turns plus one save test (four chat-class calls) and six query embeddings. D-06's 15-turn ceiling applies per Phase 5 attempt, not to cumulative retries or Phase 3's separate four chat-class calls. The refined query-embedding ceiling is 17 (R-227). Current-session paid spend is zero.
