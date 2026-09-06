## Objective
Build the React frontend foundation: Routing, Axios interceptors, Login page, and Main Application Layout.

## Why Now?
Backend APIs are ready; we need the UI to consume them.

## Dependencies
- React workspace initialized (Phase 01)
- Auth APIs (Phase 02)

## Implementation Tasks
- [ ] Setup React Router 7.
- [ ] Create Axios instance with Auth Token interceptor (`utils/authorization-util.ts`).
- [ ] Build Login/Register UI (`pages/login-next`).
- [ ] Create Zustand store for User/Auth state.
- [ ] Build Main Layout with Sidebar (Navigation).

## Components
- Router
- Axios Interceptor
- Login Page
- Main Layout

## Files
- `web/src/routes.tsx`
- `web/src/utils/authorization-util.ts`
- `web/src/pages/login-next/index.tsx`
- `web/src/layouts/main-layout.tsx`

## Interfaces
- Consumes Auth REST API.

## Data Changes
N/A

## Data Flow
UI Form -> Axios -> Backend -> Token in LocalStorage -> Zustand State -> Redirect to Dashboard

## Testing
- Run UI, login, verify token is saved and layout renders.

## Deliverable
Authenticated frontend shell.

## Definition of Done
- User can log in via UI and see the main application shell.
- 401 errors trigger logout.

## Next Subphase
04-frontend-knowledge-ui