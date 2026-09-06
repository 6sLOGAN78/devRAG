# Phase 08-04 Persistent Agent Canvas & Graph API Synchronization

## A. Repository Findings
- Backend Architecture: The API endpoints for web-facing features are hosted in Go (`internal/handler`, `internal/service`, `internal/dao`). Python handles agent runtime/ML, but the orchestration DB writes for UI go through Go. 
- Handler Architecture: Handlers are defined in `internal/handler` and utilize `gin-gonic` for HTTP context manipulation, bound dynamically in `internal/router/router.go`.
- DB Schema: The schema uses Gorm. The table `agent_canvas` handles tenant-level isolation for saved graphs.
- Frontend State Architecture: Extensively leans on TanStack React Query (`use-agent-request.ts`) and React Flow native `useReactFlow()` getter states.
- API Client: React Query encapsulated `axios` client stored at `web/src/utils/authorization-util.ts`.
- Authentication: Handled gracefully via existing `middleware.Auth(cfg)` resolving `tenant_id` and `user_id`.

## B. API Contract
- `POST /api/v1/agent/canvas/save`:
  - Request: `{ id: string, graph: { nodes: CanvasNode[], edges: CanvasEdge[] } }`
  - Success Response: `{ data: { success: true } }`
  - Errors: 400 (Bad Request), 401 (Unauthorized), 500 (DB Failure).
- `GET /api/v1/agent/canvas/:id`:
  - Response: `{ data: { id: string, graph: { nodes: CanvasNode[], edges: CanvasEdge[] } } }`
  - Errors: 404 (Not Found if it doesn't exist), 401 (Unauthorized).

## C. Database Mapping
- `AgentCanvas` in `internal/dao/models.go` is mapped identically to `api/db/db_models.py`.
- Primary Columns: `id`, `tenant_id`, `name`, `description`, `graph_definition` (JSON Text), `version`, `created_by`.
- The `req.Graph` is serialized via `json.Marshal` on the Go backend and safely piped into `graph_definition`.

## D. Serialization
- React Flow Node ➔ Backend Node: The frontend hook slices `getNodes().map(...)` specifically returning `{id, type, position, data}` avoiding injecting transient UI properties like `selected` or `dragging`.
- React Flow Edge ➔ Backend Edge: Sliced exclusively into `{id, source, target, sourceHandle, targetHandle}`.
- Backend Node ➔ React Flow Node: Delivered purely through TanStack React Query and loaded dynamically into `setNodes` bounding coordinates and properties identically. 

## E. Graph Validation
- Frontend: `isValidConnection` strictly halts cyclical loops and self-target connections. Drag/Drop mechanics enforce schema structure dynamically.
- Shared/Backend: Handled gracefully matching exact Phase 07 expected outputs (arrays of Node/Edge logic).

## F. Persistence Flow
- Save: UI `HandleSave()` ➔ strips transient DOM/React state ➔ `useSaveCanvas` ➔ `POST /save` ➔ `handler.SaveCanvas` ➔ `service.SaveCanvas` ➔ `dao.SaveAgentCanvas` (Upsert/Version tick) ➔ HTTP 200.
- Load: `CanvasArea` mount ➔ `useGetCanvas("default-canvas")` ➔ `GET /:id` ➔ `dao.GetAgentCanvasByIDAndTenant` ➔ Unmarshal `GraphDefinition` ➔ Returns to React Query ➔ `useEffect` injects `setNodes` and sets baseline incremental `id` counters to prevent collision.

## G. Security
- Authentication: Requires explicit Bearer Tokens validated by `middleware.Auth`.
- Authorization & Isolation: Queries specifically chain `WHERE id = ? AND tenant_id = ?` halting IDOR.
- Input Validation: Binding via `c.ShouldBindJSON` protects against bad payloads.

## H. Testing
- Backend unit tests pass (`go test ./internal/...`). 
- Frontend tests pass (`vitest` validates `<CanvasPage />` mounting and rendering isolated).
- Typescript build strictly validates hooks and custom interfaces.
- Standard React cascading loop validations are clear.

## I. Known Limitations
- The canvas strictly edits a singular 'default-canvas' layout. Managing multiple workflow projects concurrently requires injecting Dynamic IDs through React Router (`/agents/canvas/:id`).

---

# Next-Phase Readiness — Phase 09-01
- Canvas ID: `'default-canvas'`.
- Canvas Ownership: Tied safely to `tenant_id`. 
- Canvas Execution Definition: Accessible purely via `agent_canvas` DB lookup pulling `graph_definition`.
- Version Tick: Automatically increments `.Version` by 1 recursively on every upsert.
- Next integration: The Agent Chat Session system (Phase 09-01) merely needs to read `graph_definition` from `agent_canvas` and execute it!

**PHASE 08-04 STATUS: COMPLETE**
**NEXT: PHASE 09-01 — CHAT SESSION MODELS**
