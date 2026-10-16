#!/usr/bin/env bash
# Executor health: the alive file must be younger than WORKER_HEARTBEAT_TIMEOUT (the app image has no valkey-cli).
set -uo pipefail

cd /ragflow
exec python -m rag.svr.healthcheck
