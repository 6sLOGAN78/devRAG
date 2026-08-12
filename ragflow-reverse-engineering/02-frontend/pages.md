# Frontend Pages Catalog

## Level 1: Application Pages Hierarchy

This document lists every top-level page in the RAGFlow single-page application, mapping page paths to source code files in `web/src/pages/`.

---

## Level 2: Comprehensive Pages Catalog

### 1. Authentication Pages (`web/src/pages/login-next/`)
- **Login / Register Page** (`/login-next`): Renders email/password authentication forms, OAuth2 login options (GitHub, Google, OIDC), and registration workflows.
- Source: [`web/src/pages/login-next/index.tsx`](file:///home/logan78/Desktop/ragflow/web/src/pages/login-next)

### 2. Datasets & Knowledge Base Pages (`web/src/pages/datasets/` & `web/src/pages/dataset/`)
- **Datasets List Page** (`/datasets`): Renders dataset cards, creation modal, search filter bar, and pagination.
  - Source: [`web/src/pages/datasets/index.tsx`](file:///home/logan78/Desktop/ragflow/web/src/pages/datasets)
- **Dataset Detail & Document Management** (`/dataset/files`): Renders document table, parser selector, upload dialog, chunk status indicators, and document deletion controls.
  - Source: [`web/src/pages/dataset/index.tsx`](file:///home/logan78/Desktop/ragflow/web/src/pages/dataset)
- **Parsed Chunks Preview** (`/chunk`): Visualizes individual document chunks, chunk status, text representation, vector representations, and manual chunk edits.
  - Source: [`web/src/pages/chunk/index.tsx`](file:///home/logan78/Desktop/ragflow/web/src/pages/chunk)
- **Retrieval Testing Page** (`/retrieval`): Interactive test drawer to query the dataset, evaluate vector similarity scores, and inspect hit chunks.
  - Source: [`web/src/pages/dataset/testing/index.tsx`](file:///home/logan78/Desktop/ragflow/web/src/pages/dataset/testing)

### 3. Agent & Canvas Pages (`web/src/pages/agent/` & `web/src/pages/agents/`)
- **Agents Gallery Page** (`/agents`): List of existing user agents, template gallery, search filters, and creation buttons.
  - Source: [`web/src/pages/agents/index.tsx`](file:///home/logan78/Desktop/ragflow/web/src/pages/agents)
- **Agent Workflow Canvas Page** (`/agent`): Drag-and-drop workflow canvas built on `@xyflow/react`.
  - Source: [`web/src/pages/agent/canvas/index.tsx`](file:///home/logan78/Desktop/ragflow/web/src/pages/agent/canvas/index.tsx)
- **Agent Share Page** (`/agent/share`): Public standalone web widget page for executing shared agents.
  - Source: [`web/src/pages/agent/share/index.tsx`](file:///home/logan78/Desktop/ragflow/web/src/pages/agent/share)

### 4. Chat Playground Pages (`web/src/pages/next-chats/`)
- **Chat Playground** (`/chats` / `/chat`): Interactive multi-session chat workspace supporting SSE streaming responses, markdown formatting, citations preview, and system prompts.
  - Source: [`web/src/pages/next-chats/index.tsx`](file:///home/logan78/Desktop/ragflow/web/src/pages/next-chats)
- **Shared Chat Page** (`/chats/share`): Public shared chat page.
  - Source: [`web/src/pages/next-chats/share/index.tsx`](file:///home/logan78/Desktop/ragflow/web/src/pages/next-chats/share)

### 5. User Settings & Admin Pages (`web/src/pages/user-setting/` & `web/src/pages/admin/`)
- **User Profile & API Keys** (`/user-setting/profile`): Profile configuration, API key generation (`APIToken`), team member management, and LLM model provider key configuration.
  - Source: [`web/src/pages/user-setting/index.tsx`](file:///home/logan78/Desktop/ragflow/web/src/pages/user-setting)
- **Enterprise Admin Dashboard** (`/admin`): User role administration, system metrics monitoring, service health status.
  - Source: [`web/src/pages/admin/index.tsx`](file:///home/logan78/Desktop/ragflow/web/src/pages/admin)
