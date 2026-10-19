# 04-35 gate log

Append-only record. No secrets, only PASS/FAIL lines and figures.

- Pre-gate checks, all PASS: `scripts/ci/run_all.py` 7 of 7; `run_tests.py -m unit` 2055 passed, 4 skipped in 61 s; web unit project 82 files, 1703 tests in 45 s; `PHASE4_GATE=1` traceability 6 passed.
- Executor memory (R-188): peak 127 MiB sampled and 193 MiB cgroup high-water mark at 768m; after the limit change to 384m, 161 MiB sampled and 201 MiB cgroup mark; OOMKilled false; stack total measured 2078 MiB of the 3891 MiB budget; host available RAM 7743 MiB, free disk 17 GB, `vm.max_map_count` 65530.
- GATE ATTEMPT 1 (`PREFLIGHT_ALLOW_LOW_MAP_COUNT=1 LIVE_BASE_URL=http://127.0.0.1:8088 scripts/clean_room.sh --runs 3`) REFUSED at step `project-guard` before anything was stopped or removed:
  `FAIL project name collision: 8 container(s) of project 'devrag-stack' belong to another checkout: /home/logan78/desktop x/devRag_@/docker`.
  Cause: the `mailpit` container carries the compose working-dir label `/home/logan78/desktop x/devRag_@/docker` (seven other containers carry `/home/logan78/desktop x/devRAG/docker`). The guard is working as designed (B-05) and was not bypassed; no container or volume was touched by hand.
- Required from the user: remove the stray container yourself, then restart the gate from run 1:
  `docker rm -f devrag-stack-mailpit-1` (it holds no volume), then
  `PREFLIGHT_ALLOW_LOW_MAP_COUNT=1 LIVE_BASE_URL=http://127.0.0.1:8088 scripts/clean_room.sh --runs 3`.
  Alternatively recreate it from this checkout with
  `docker compose -p devrag-stack --env-file docker/.env -f docker/docker-compose.yml -f docker/docker-compose.dev.yml --profile cpu --profile elasticsearch --profile mail up -d --force-recreate --no-deps mailpit`.
- The three clean-room runs have NOT been done. `clean-room: 3 run(s) passed` does not appear in this log.
- Stack after the refusal: all services healthy (nothing was stopped).
