# RAGFlow Multi-Tenant & RBAC Architecture

This document explains the organization, tenancy, and Role-Based Access Control (RBAC) implementation in RAGFlow. It covers how Workspaces (Tenants) work, the difference between user roles, and how data is isolated at the API and database levels.

## 1. Core Concepts: Users, Tenants, and Workspaces

RAGFlow is designed natively as a **multi-tenant** application. A "Tenant" in RAGFlow represents a Workspace, an Organization, or a Team. 

When a user registers for the first time, RAGFlow automatically provisions a default `Tenant` for them. The user becomes the `owner` of this tenant. Later, the user can invite other people to join their Tenant, effectively creating a team workspace.

### Core Database Models (`api/db/db_models.py`)

1. **`User` Table:** 
   Stores global user authentication and preferences.
   * `id`: Unique user identifier.
   * `email`, `password`, `nickname`, `language`, `color_schema`.
   * This is completely independent of the workspace data.

2. **`Tenant` Table:**
   Represents a team workspace or organization.
   * `id`: Unique tenant identifier.
   * `name`: Workspace name.
   * Stores global workspace configurations such as default LLM models (`llm_id`, `embd_id`), ensuring all users in the tenant fall back to the organization's API keys if not overridden.

3. **`UserTenant` Table (The RBAC Bridge):**
   This mapping table connects a `User` to a `Tenant` and assigns them a `role`.
   * `user_id` -> Foreign Key to `User.id`
   * `tenant_id` -> Foreign Key to `Tenant.id`
   * `role`: Determines permissions (e.g., `owner`, `admin`, `normal`, `invite`).
   * `status`: Validates if the mapping is active.

## 2. Roles & Permissions (`UserTenantRole`)

RAGFlow defines roles in `api/db/__init__.py` under the `UserTenantRole` enum:

* **`owner`:** The creator of the Workspace. They have complete control over the `Tenant`. They can invite members, delete members, configure the organization's LLM API keys (`TenantModel`), and have full visibility of all knowledge bases and agents in the workspace.
* **`admin`:** A privileged user to assist the owner. In the data layer, they have elevated rights similar to the owner (managing resources and users) but cannot delete the workspace itself or revoke the owner.
* **`normal`:** A standard team member. They can create their own resources (knowledge bases, documents, and agents) within the workspace. They can interact with resources shared with the `team`, but cannot invite new users or alter tenant-level billing/API keys.
* **`invite`:** A pending state. When an owner invites an email, a `UserTenant` row is created with this role. Once the user accepts, it switches to `normal`.

## 3. Data Isolation and Storage (Database Layer)

RAGFlow strictly isolates data at the `tenant_id` level.

### Relational Database (MySQL / PostgreSQL / OceanBase)
Almost every business resource table in RAGFlow contains a `tenant_id` column:
* `Knowledgebase`
* `Document`
* `Dialog` (Agents)
* `Canvas` (Workflows)
* `TenantModel` (LLM API configurations)

**Permission Scoping (`permission` and `created_by`):**
Some tables (like `Knowledgebase`) include `permission` and `created_by` fields. 
* If `permission == "me"`, only the user matching `created_by` (and the `owner`) can view/edit it.
* If `permission == "team"`, any user whose `UserTenant.tenant_id` matches the resource's `tenant_id` can access it.

### Document & Vector Storage (Elasticsearch / Infinity)
When text chunks and vector embeddings are stored in Elasticsearch or Infinity, the `tenant_id` is explicitly indexed alongside the chunk data. 

Whenever a vector search (RAG retrieval) is executed, the backend **always** injects a hard filter for `tenant_id == current_user.tenant_id`. This prevents cross-tenant data leakage at the vector-search level.

## 4. API Layer and Enforcement (`tenant_api.py`)

Access control is enforced via decorators and explicit checks in the Quart API controllers.

1. **Authentication Middleware (`@login_required`):** 
   Validates the JWT session and attaches a `current_user` object to the request context.

2. **Tenant Verification (`api/apps/restful_apis/tenant_api.py`):**
   Before executing an action on a tenant (e.g., fetching the user list or inviting someone), the API checks if the requester has the authority:
   ```python
   # Example from user_list endpoint
   if current_user.id != tenant_id:
       return get_json_result(data=False, message="no authorization", ...)
   ```

3. **Query Filtering (`api/db/services/`):**
   Service layers (like `DocumentService` or `KnowledgebaseService`) automatically apply `owner_filter` logic. They query the `UserTenant` table to verify the user's role. If the role is `normal`, the SQL query is appended with `WHERE created_by = user_id OR permission = 'team'`. If the role is `owner`, they bypass the `created_by` filter and can see all resources under the `tenant_id`.

## Summary Workflow

1. **Alice** signs up. RAGFlow creates `User (Alice)` and `Tenant (Alice Workspace)`. `UserTenant` links them with role `owner`.
2. **Alice** adds OpenAI API keys. Saved in `TenantModel` linked to `tenant_id`.
3. **Alice** invites **Bob** via email. A `UserTenant` row is created with role `invite` for Bob.
4. **Bob** logs in and accepts. His `UserTenant` role changes to `normal`.
5. **Bob** creates a Knowledgebase (KB) set to `team`. The KB is saved with Alice's `tenant_id`, `created_by = Bob`, and `permission = team`.
6. When **Bob** chats with an Agent using this KB, the system retrieves embeddings using the OpenAI keys from Alice's `TenantModel` and searches Infinity filtering strictly by Alice's `tenant_id`.
