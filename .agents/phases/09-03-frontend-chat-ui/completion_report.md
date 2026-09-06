# Phase 09-03 Frontend Chat UI - Completion Report

## A. Summary
Implemented the first complete frontend chat experience built on top of Phase 09-01 (Chat History) and Phase 09-02 (SSE API). The UI features a left-side session selection sidebar, robust history reloading via `@tanstack/react-query`, an auto-growing input textarea component with keyboard controls, and an isolated React hook for chunked SSE parsing via `@microsoft/fetch-event-source`. All components fit directly into the existing styling paradigm (Tailwind and Lucide icons).

## B. Actual Files Changed
- `web/package.json` (Installed `@microsoft/fetch-event-source`)
- `web/src/routes.tsx` (Added the `/chat` route mapped to `<ChatPage />`)
- `web/src/pages/chat/index.tsx` (Main layout integrating sessions, history, and message inputs)
- `web/src/pages/chat/chat.test.tsx` (Integration E2E-style simulation ensuring SSE incrementally streams chunks over to the bubbles)
- `web/src/components/message-input/index.tsx` (Extracted textarea with auto-resizing, sending disabled guards, and styling)
- `web/src/components/message-input/message-input.test.tsx` (Component behavior test suite)
- `web/src/hooks/use-chat.ts` (API wrapper hooks for sessions and history)
- `web/src/hooks/use-send-message.ts` (Main SSE consumption hook parsing stream completion)
- `web/src/hooks/use-send-message.test.tsx` (Unit test verifying chunk concatenation behavior inside the hook state)

## C. Frontend Architecture
```text
ChatPage (pages/chat/index.tsx)
 ├── Session Sidebar (Rendered inline with React Query caching useChatSessions)
 ├── Message List (Renders both history messages + a mock bubble for the currently streaming message)
 └── Message Input (Controlled container triggering onSend -> useSendMessage hook)
```
The application state mostly lives in React Query (`useChatSessions`, `useChatHistory`). The temporary active text iteration resides solely in `useSendMessage`, which prevents the global app from re-rendering unnecessarilly when 300+ text chunks stream in. 

## D. SSE Integration
- **Endpoint**: `POST /api/v1/chat/completions`
- **Authentication**: `fetchEventSource` uses the exact bearer token extracted securely from `getToken()` which mirrors Axios.
- **Parsing**: `[DONE]` event concludes the loop and triggers a query invalidation on the history, retrieving the finalized canonical message (and citations). Text is parsed out of the `{"text":"..."}` chunk dynamically.
- **Cancellation**: Exposes an `AbortController.abort()` callback wired visually to the `Square` cancel button inside the text input area.

## E. State Model
- **`sessions`**: List loaded natively from API and bound to React-Query context cache.
- **`activeSessionId`**: React `useState` controlling which history object to load and append strings against.
- **`history`**: Persistent user/assistant bubbles queried securely by session ID via React Query.
- **`streamingMessage`**: React `useState` isolated in the messaging hook updated rapidly on every SSE chunk to prevent layout thrash.

## F. Session/History Integration
Selecting a session from the sidebar sets `activeSessionId`. This inherently triggers `useChatHistory(activeSessionId)` to perform an Axios fetch (`/api/v1/chat/message/:id`). React Query caches this result and provides automatic deduplication.
When `handleNewChat` is fired, a new session is pushed via `POST` bound to `default-canvas`. The resulting newly-saved `id` automatically becomes the `activeSessionId`.

## G. Testing
- Component testing verifying text area auto-growth bounds and keyboard shortcuts.
- Hooks tested specifically ensuring `fetchEventSource` streams append rather than overwrite partial phrases, closing elegantly upon receiving `[DONE]`.
- Integration "E2E-style" tested end-to-end via `chat.test.tsx` which mocks the axios client adapter and asserts exactly what text is seen within the Document DOM asynchronously, simulating delays dynamically.
- Full type verification tested using Vite build.

## H. Performance
Only the streaming string inside the `useSendMessage` hook updates every tick. To avoid stuttering or dropping connections, the component avoids mapping any intensive logic out of the SSE callback block. Once the full string is done, it calls one single `queryClient.invalidateQueries` which silently aligns the screen accurately.
An `autoScroll` boolean threshold prevents the UI from hijacking the scrollbar if the user manually scrubs back up the history to read past queries during a long stream.

## I. Accessibility
- All standard `aria-label` tags included on message input inputs/senders.
- Proper color contrasts maintained across Tailwind configurations.
- Form disables the send button cleanly and supports explicit keyboard control (`Enter` without `Shift`) natively.

## J. `.agents`
- Explored `web/src/pages/agents/canvas/index.tsx` to align exactly on the `CANVAS_ID` hardcode schema mapping strategy from Phase 08.
- Analyzed `authorization-util.ts` to deduce how custom token fetching works when mapping the SSE HTTP boundary since we couldn't rely strictly on Axios interceptors for native Fetch streams.
