## Objective
Build the chat interface: Sidebar for sessions, input area, and message bubbles.

## Why Now?
Frontend implementation of the Chat APIs.

## Dependencies
- 02-sse-streaming-api

## Implementation Tasks
- [ ] Build `pages/next-chats/index.tsx`.
- [ ] Implement SSE client using `@microsoft/fetch-event-source` or native `EventSource` in `hooks/use-send-message.ts`.
- [ ] Manage local React state for the actively streaming message bubble.
- [ ] Implement `message-input` component (textarea auto-grow, enter to send).

## Components
- Chat Layout
- SSE Hook

## Files
- `web/src/pages/next-chats/index.tsx`
- `web/src/hooks/use-send-message.ts`
- `web/src/components/message-input/index.tsx`

## Interfaces
N/A

## Data Changes
N/A

## Data Flow
User Types -> Hook -> SSE Request -> State Update -> Re-render bubble

## Testing
- E2E test chatting with the bot and verifying streaming updates.

## Deliverable
Working Chat UI.

## Definition of Done
- UI streams text smoothly without stuttering or dropping connections.

## Next Subphase
04-markdown-and-citations