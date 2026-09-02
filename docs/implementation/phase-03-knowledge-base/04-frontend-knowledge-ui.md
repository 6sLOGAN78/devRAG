## Objective
Build the Knowledge Base (Dataset) listing and Document upload UI.

## Why Now?
Completes the full-stack loop for Phase 03.

## Dependencies
- 03-frontend-auth-and-layout
- Dataset/Document APIs

## Implementation Tasks
- [ ] Build Dataset List view (`pages/datasets`).
- [ ] Build Create Dataset Modal.
- [ ] Build Dataset Detail view (Document List).
- [ ] Build File Upload Dialog component with drag-and-drop and progress bar.
- [ ] Integrate React Query / custom hooks for API calls.

## Components
- Dataset List
- Document Table
- File Upload Dialog

## Files
- `web/src/pages/datasets/index.tsx`
- `web/src/pages/datasets/detail.tsx`
- `web/src/components/file-upload-dialog/index.tsx`
- `web/src/hooks/use-knowledge-request.ts`

## Interfaces
- Consumes Dataset/Document REST APIs.

## Data Changes
N/A

## Data Flow
UI Drag&Drop -> Axios Multipart -> Backend

## Testing
- E2E testing (manual or Playwright): Create dataset, upload PDF, see it in list.

## Deliverable
Complete UI for Knowledge Base management.

## Definition of Done
- User can create datasets and upload files seamlessly from the browser.

## Next Subphase
Phase 04 - Deep Document Parsing