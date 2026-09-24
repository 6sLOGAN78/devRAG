# Docker Compose Configurations (`/docker`)

This directory contains the required configurations to spin up the local dependency infrastructure for **DevRAG**.

## `docker-compose-base.yml`
Provisions the stateful infrastructure components required for local development:
- **MySQL 8**: Primary relational database for tenants, users, and tasks.
- **Redis 7**: Caching and rate-limiting store.
- **MinIO**: S3-compatible object storage for uploaded user documents.
- **Infinity**: High-performance Hybrid Search vector database.

### Usage
```bash
docker compose -f docker/docker-compose-base.yml up -d
```
