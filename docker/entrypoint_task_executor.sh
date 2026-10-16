#!/usr/bin/env bash
# Task executor entrypoint: render config, drop to the host UID/GID, exec the executor.
# exec keeps Python as the process tini signals, so SIGTERM reaches it for a graceful stop (ING-16).
# The executor logs to stdout only, so no log directory is prepared.
set -euo pipefail

cd /ragflow
APP_UID="${APP_UID:-1000}"
APP_GID="${APP_GID:-1000}"
export APP_UID APP_GID SERVICE_CONF="${SERVICE_CONF:-/ragflow/conf/service_conf.yaml}"

python scripts/render_conf.py --out "$SERVICE_CONF"
chown "$APP_UID:$APP_GID" "$SERVICE_CONF"

exec setpriv --reuid="$APP_UID" --regid="$APP_GID" --clear-groups python -m rag.svr.task_executor
