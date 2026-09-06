---
description: Rules for Python API and ML backend development
trigger:
  paths: ["api/**/*.py"]
---
# Python Backend Rules

When working on the Python backend for devRAG, adhere to the following standards:

1. **Web Framework:**
   - The project uses Quart/Flask. Respect async boundaries where applicable.
2. **ORM Usage:**
   - Use `peewee` for Python-based database interactions. Models live in `api/db/db_models.py`.
3. **Multi-Tenancy Checks:**
   - Endpoints must verify permissions using the `UserTenant` mapping.
   - Utilize `@login_required` decorators for protected API routes.
4. **Code Quality:**
   - Maintain PEP-8 compliance.
   - Type hint function arguments and return types where possible to make intent clear.
