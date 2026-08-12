# Database Entities Reference

## Level 1: Conceptual Overview

This document catalogs all system entity domain models mapped across Python Peewee ORM classes and Go GORM data access objects.

---

## Level 2: Implementation Details

### Catalog of Entities

1. **`User`**: User profile, authentication credentials, status flags.
   - Python: [api/db/db_models.py](file:///home/logan78/Desktop/ragflow/api/db/db_models.py#L750)
2. **`Tenant`**: Multi-tenant workspace container, API keys, quota configs.
   - Python: [api/db/db_models.py](file:///home/logan78/Desktop/ragflow/api/db/db_models.py#L780)
3. **`Knowledgebase`**: Dataset container, default chunk parser, embedding model ID.
   - Python: [api/db/db_models.py](file:///home/logan78/Desktop/ragflow/api/db/db_models.py#L837) | Go: [internal/dao/kb.go](file:///home/logan78/Desktop/ragflow/internal/dao/kb.go#L30)
4. **`Document`**: Single file entry within dataset, token count, chunk count, progress status.
   - Python: [api/db/db_models.py](file:///home/logan78/Desktop/ragflow/api/db/db_models.py#L894) | Go: [internal/dao/document.go](file:///home/logan78/Desktop/ragflow/internal/dao/document.go#L30)
5. **`Task`**: Unit of background ingestion work (page range, parsing progress, status).
   - Python: [api/db/db_models.py](file:///home/logan78/Desktop/ragflow/api/db/db_models.py#L1002) | Go: [internal/dao/ingestion.go](file:///home/logan78/Desktop/ragflow/internal/dao/ingestion.go#L30)
6. **`File`**: File manager blob object, parent directory ID, content hash.
   - Python: [api/db/db_models.py](file:///home/logan78/Desktop/ragflow/api/db/db_models.py#L924) | Go: [internal/dao/file.go](file:///home/logan78/Desktop/ragflow/internal/dao/file.go#L30)
7. **`File2Document`**: Link entity mapping user files to dataset documents.
   - Python: [api/db/db_models.py](file:///home/logan78/Desktop/ragflow/api/db/db_models.py#L939) | Go: [internal/dao/file2document.go](file:///home/logan78/Desktop/ragflow/internal/dao/file2document.go#L30)
8. **`Dialog`**: Chat application configuration, prompt instructions, top_k, similarity thresholds.
   - Python: [api/db/db_models.py](file:///home/logan78/Desktop/ragflow/api/db/db_models.py#L1020) | Go: [internal/dao/chat.go](file:///home/logan78/Desktop/ragflow/internal/dao/chat.go#L30)
9. **`APIToken`**: Service token for external REST API authentication.
   - Python: [api/db/db_models.py](file:///home/logan78/Desktop/ragflow/api/db/db_models.py#L760) | Go: [internal/dao/api_token.go](file:///home/logan78/Desktop/ragflow/internal/dao/api_token.go#L25)
