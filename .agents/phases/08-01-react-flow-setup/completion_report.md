# Phase 08-01 React Flow Setup Completion Report

## A. Repository Findings
- Frontend framework: React 19 (via Vite)
- Router: React Router v7 (`react-router`)
- Styling system: Tailwind CSS v4 (`@tailwindcss/vite`)
- State management: Zustand (`zustand`)
- Existing layout: Desktop-oriented layout (`MainLayout` shell) with side navigation.
- Existing agent pages: Empty placeholder pointing to `/agents`.
- Testing framework: Vitest + React Testing Library (`@testing-library/react`)
- Package manager: npm (`package-lock.json`)

## B. React Flow Integration
- React Flow version: `@xyflow/react` v12 (installed natively into `package.json`).
- integration point: Sub-page `/agents/canvas` within `MainLayout` shell.
- provider usage: Wrapped `CanvasArea` and `NodePalette` with `ReactFlowProvider` inside `CanvasPage`.
- node state: Managed internally with `useNodesState`.
- edge state: Managed internally with `useEdgesState`.
- viewport handling: Full flexbox auto-height container (`flex-1 h-full w-full`) ensuring natural bounding boxes without exploding layout constraints. Built-in `fitView` applied.

## C. Files Changed
1. `web/package.json` / `package-lock.json`
   - Purpose: Added `@xyflow/react`.
2. `web/src/routes.tsx`
   - Purpose: Substituted the `Agents` stub route with a direct subroute `/agents/canvas` mounting the `CanvasPage`.
3. `web/src/layouts/main-layout.tsx`
   - Purpose: Updated the sidebar NavLink to point to `/agents/canvas`.
4. `web/src/pages/agents/canvas/index.tsx`
   - Purpose: Main container managing React Flow instance, dropping handles, and projecting coordinates `screenToFlowPosition`.
5. `web/src/pages/agents/canvas/palette.tsx`
   - Purpose: Renders draggable `NodeDefinition` elements pushing `type` via standard HTML5 DataTransfer `application/reactflow`.
6. `web/src/pages/agents/canvas/placeholder-nodes.tsx`
   - Purpose: Created basic renderers for LLM, Retrieval, Code, and Switch nodes with `source` and `target` Handles.
7. `web/src/pages/agents/canvas/types.ts`
   - Purpose: Basic strictly-typed TypeScript types (`NodeTypeType` and `NodeDefinition`).
8. `web/src/pages/agents/canvas/index.test.tsx` (Created)
   - Purpose: Verifies palette and layout component rendering. 

## D. Node Model
Each backend node logic abstraction (`llm`, `retrieval`, `code`, `switch`) corresponds directly to a `BaseNode` placeholder UI. The `placeholder-nodes.tsx` map links the node types dynamically inside React Flow. Standard graph `data` properties populate basic identifiers.

## E. Drag-and-Drop Flow
1. Palette `onDragStart` captures the structural ID mapping. 
2. `CanvasArea` listens via `onDrop`.
3. `event.dataTransfer.getData` pulls the type. 
4. Uses `@xyflow/react` hook `useReactFlow().screenToFlowPosition()` to cleanly map bounding offsets into the active viewport regardless of zoom.
5. Pushes `newNode` into `useNodesState` with a unique ID generator.

## F. Edge Flow
Using `onConnect`, connection requests map standard `source` handles to `target` handles via `@xyflow/react` `addEdge`. Handled deterministically into `useEdgesState`. 

## G. Phase 07 Compatibility
The frontend UI emits standard JSON mapping precisely:
- `nodes`: Contains structural `id`, `type`, `position`, `data`.
- `edges`: Maps `source` to `target` (and eventually, with custom edge rendering, we'll map `route`).
This guarantees simple mapping into Phase 07 `AgentGraph` JSON architectures. The logic executes fully independent of the backend; UI representation remains stateless relative to business logic.

## H. Tests
- automated tests: Fixed a missing Vitest import inside `use-knowledge-request.test.tsx`. Built `index.test.tsx` verifying canvas mounting and DOM inclusion. 
- typecheck: Resolved strict TS warnings ensuring cleanly validated types.
- lint: Run via oxlint, passes smoothly (disregarding `react(only-export-components)` fast-refresh warnings in `.tsx` data-structures).
- build: `tsc -b && vite build` succeeded efficiently.
- manual tests: Drag and drop correctly tracks pointer positions, instantiating new handles.
- browser verification: No console crashes or duplicated key hooks.

## I. Known Limitations
1. Custom configurations (e.g. LLM prompts, branch logic blocks) have not been implemented yet per instructions.
2. `SwitchNode` placeholders currently only emit a basic `target` and `source` handle, instead of separate conditional branching routes. 
3. Persistent workflows aren't mapped over REST; graph state is strictly local page-memory.
