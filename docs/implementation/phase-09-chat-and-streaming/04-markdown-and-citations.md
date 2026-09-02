## Objective
Enhance the Chat UI with Markdown rendering, Syntax Highlighting, KaTeX, and clickable Citation pills.

## Why Now?
RAG responses require precise formatting and verifiable source links to prevent hallucination concerns.

## Dependencies
- 03-frontend-chat-ui

## Implementation Tasks
- [ ] Integrate `react-markdown`, `remark-gfm`, `rehype-katex`.
- [ ] Create `markdown-content` component.
- [ ] Parse special citation tags from the backend (e.g., `[1]`, `[2]`).
- [ ] Implement a Drawer/Popover that opens when a citation is clicked, showing the original Document chunk and highlighting the bounding box on the PDF preview.

## Components
- Markdown Renderer
- Citation Drawer

## Files
- `web/src/components/markdown-content/index.tsx`
- `web/src/components/message-item/index.tsx`
- `web/src/components/document-preview/index.tsx`

## Interfaces
N/A

## Data Changes
N/A

## Data Flow
N/A

## Testing
- Provide a markdown string with tables, math, and code. Verify rendering.
- Verify clicking citation `[1]` fetches and displays the correct PDF page.

## Deliverable
Enterprise-grade chat rendering.

## Definition of Done
- **MVP IS NOW COMPLETE**. The system functions from end-to-end: Upload -> Parse -> Graph -> Chat with Citations.

## Next Subphase
Phase 10 - 01-integration-testing