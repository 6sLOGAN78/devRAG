# 02 - Production Infrastructure & Backing Services

## Objective
Create the local and production-grade Docker Compose architecture required to run RAGFlow's backing services (DB, Cache, Queue, Object Storage, Vector DB, and Ingress).

## Production Requirements
RAGFlow relies on a highly decoupled architecture. The backing services must be orchestrated using `docker-compose.yml` (and eventually Helm).

### Required Services & Ports
1. **Edge/Ingress (Nginx):**
   - Handles SSL termination and routes `/v1/` to Go (9384) and Python (9380).
   - Ports: 80, 443.
2. **Relational Database (MySQL 8.0+):**
   - Stores tenant, user, and document metadata.
   - Port: 3306.
3. **Cache & Session (Redis / Valkey 8):**
   - Stores JWT session states, rate limiting, and LLM cache.
   - Port: 6379.
4. **Message Queue (NATS JetStream):**
   - Extremely high-throughput queue for async parsing tasks (DeepDoc).
   - Port: 4222.
5. **Object Storage (MinIO / S3):**
   - Stores uploaded raw PDFs and parsed chunk JSONs.
   - Ports: 9000 (API), 9001 (Console).
6. **Vector Search Engine (Infinity or Elasticsearch):**
   - High-performance vector embeddings storage and hybrid search (BM25 + Vector).
   - Port: 23817 (Infinity) or 9200 (ES).

## Implementation Tasks
- [ ] Create `docker/docker-compose-base.yml` containing MySQL, Redis, NATS, MinIO, and Infinity.
- [ ] Write `docker/init.sql` to initialize the default MySQL database `rag_flow`.
- [ ] Configure Docker health checks for all services to ensure correct boot ordering.
- [ ] Create a local `.env` file to manage credentials securely without committing them.

## Deliverable
A `docker compose up -d` command that successfully spins up the entire backing infrastructure in a ready state.
