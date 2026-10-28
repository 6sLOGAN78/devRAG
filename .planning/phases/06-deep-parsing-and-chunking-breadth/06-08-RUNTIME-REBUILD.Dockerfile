# syntax=docker/dockerfile:1
# One app image: SPA (built), Go API binary, Python API, Nginx, under tini (D-23, D-24, D-26).
# Python 3.13 deviates from docs/18-deployment/docker.md ("3.10 slim"), see D-16.

FROM node:22-alpine AS web-build
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM golang:1.25-alpine AS go-build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY cmd ./cmd
COPY internal ./internal
COPY conf/embed.go conf/schema.json ./conf/
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/ragflow_server ./cmd

# Reuse exact verified local runtime; pyproject/uv.lock hashes checked before build.
FROM devrag-app-runtime-p6-08:local AS runtime
WORKDIR /ragflow
COPY api ./api
COPY common ./common
COPY rag ./rag
COPY deepdoc ./deepdoc
COPY conf ./conf
COPY scripts/render_conf.py ./scripts/render_conf.py
COPY --from=go-build /out/ragflow_server /ragflow/bin/ragflow_server
COPY --from=web-build /web/dist /ragflow/web/dist
COPY docker/nginx/nginx.conf /etc/nginx/nginx.conf
COPY docker/nginx/proxy.conf /etc/nginx/proxy.conf
COPY docker/nginx/ragflow.conf /etc/nginx/conf.d/ragflow.conf
COPY docker/nginx/ragflow.https.conf /etc/nginx/ragflow.https.conf
COPY docker/entrypoint.sh docker/entrypoint_init.sh docker/healthcheck.sh docker/prepare_runtime.sh docker/entrypoint_task_executor.sh docker/healthcheck_task_executor.sh /ragflow/docker/
RUN chmod 0755 /ragflow/docker/*.sh /ragflow/bin/ragflow_server \
    && mkdir -p /ragflow/logs /ragflow/conf
EXPOSE 80 443
ENTRYPOINT ["tini", "--", "/ragflow/docker/entrypoint.sh"]
