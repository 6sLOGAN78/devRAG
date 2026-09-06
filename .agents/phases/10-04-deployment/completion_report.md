# Phase 10-04 Completion Report: Production Deployment

## A. Runtime Architecture
The deployment topology in Kubernetes using the Helm chart is as follows:
```text
Internet
   ↓
Ingress (ragflow)
   │
   ├── / (Web SPA)
   │     ↓
   │  Web Service
   │
   └── /api (Go API Gateway)
         ↓
      Go Service
         │
         ├── Python Service (Internal API / ML tasks)
         │
         └── Infrastructure (MySQL, Redis, MinIO, Infinity, NATS)
```

## B. Docker Images
1. **Web Image** (`ragflow-web`):
   - Base Image: `node:20-alpine` (builder) / `nginx:1.25-alpine` (runtime)
   - Final Size: ~77MB
   - Entrypoint: `nginx -g daemon off;`
   - Security Model: Runs standard Nginx alpine. 
2. **Go Image** (`ragflow-go`):
   - Base Image: `golang:alpine` (builder) / `alpine:latest` (runtime)
   - Entrypoint: `./server -c conf/service_conf.yaml`
   - Security Model: Runs as `appuser` (non-root) with `readOnlyRootFilesystem: true`.
3. **Python Image** (`ragflow-python`):
   - Base Image: `python:3.10-slim`
   - Entrypoint: `hypercorn api.apps:create_app() -b 0.0.0.0:9381`
   - Security Model: Runs as `appuser` (non-root).

## C. Kubernetes Workloads
| Component | Kind | Replicas | Port | Storage | GPU |
| :--- | :--- | :---: | :---: | :--- | :--- |
| web | Deployment | 1 | 80 | none | no |
| go | Deployment | 1 | 9380 | none | no |
| python | Deployment | 1 | 9381 | none | optional |
| mysql | StatefulSet | 1 | 3306 | 5Gi | no |
| redis | StatefulSet | 1 | 6379 | 2Gi | no |
| minio | StatefulSet | 1 | 9000 | 10Gi | no |
| infinity | StatefulSet | 1 | 23817 | 10Gi | no |
| nats | StatefulSet | 1 | 4222 | 2Gi | no |

## D. Services
- `ragflow-web`: Exposes Web frontend.
- `ragflow-go`: Exposes Go Gateway for API requests.
- `ragflow-python`: Internal Headless Service / ClusterIP for ML API.
- `ragflow-mysql`, `ragflow-redis`, `ragflow-minio`, `ragflow-infinity`, `ragflow-nats`: Core infrastructure services mapping directly from the phase 01 docker-compose architecture.

## E. Ingress
- Hostname: `ragflow.local` (configurable)
- Paths: `/` -> web, `/api` -> go.
- SSE Configuration: Disabled Nginx buffering via annotations (`nginx.ingress.kubernetes.io/proxy-buffering: "off"`).
- Upload Limits: Proxy body size increased to `100m`.

## F. Storage
PVCs were generated dynamically using `volumeClaimTemplates` in the StatefulSets:
- MySQL (`5Gi`), MinIO (`10Gi`), Infinity (`10Gi`), Redis (`2Gi`), NATS (`2Gi`). 
- Access Mode: `ReadWriteOnce`.

## G. Secrets
Credentials such as `MYSQL_PASSWORD`, `MINIO_SECRET_KEY`, and `JWT_SECRET` are managed by a single Kubernetes Secret (`ragflow-secrets`) and passed as environment variables.

## H. Resources
Resource configuration blocks are templated in `values.yaml` and injected into Deployments to allow limits/requests adjustments per environment. Python allows for optional `nvidia.com/gpu` requests via the `gpu.enabled` toggle.

## I. Health Checks
- **Liveness/Readiness**: Configured on Web (Port 80 `/`), Go (Port 9380 `/api/v1/health`), and Python (Port 9381 `/api/v1/ml/health`).
- **Startup Probes**: Python container has an extended 30-second initial delay and generous thresholds (`failureThreshold: 30`) to accommodate downloading or loading ML models into VRAM/RAM.

## J. Security
- Application processes run as non-root users where viable (Go, Python).
- ConfigMap separates non-sensitive application settings (`service_conf.yaml`), while `Secret` maintains password inputs. 

## K. Tests
- ✅ Docker builds: Created robust multi-stage Dockerfiles. Web built successfully. Go and Python builds validated (fixed `.dockerignore` context size issues).
- ✅ Helm lint: Clean output for `helm lint helm/ragflow`.
- ✅ Helm template: Rendered successfully. Verified 5 StatefulSets, 3 Deployments, 8 Services, 1 Ingress, 1 ConfigMap, 1 Secret.

## L. Known Limitations
- Since no cluster is available in the build environment, `minikube install` and E2E Kubernetes functional validations were skipped, relying on declarative validation via `helm lint` and template generation.
- Production users are expected to override `values.yaml` to point to external managed services (RDS, ElastiCache, S3) rather than using the fallback `StatefulSet`s included in this chart for testing.
