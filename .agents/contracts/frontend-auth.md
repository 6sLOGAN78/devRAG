# Frontend Authentication Contract

## Overview
The frontend strictly relies on the backend for security context and authentication validation. The frontend maintains UI state to coordinate application views, not to enforce security bounds.

## Token Management
- **Location**: `localStorage` (Key: `devrag_auth_token`).
- **Axios Interceptor**: Globally intercepts and injects `Authorization: Bearer <token>` into `apiClient`.
- **Expiration Strategy**: When a `401 Unauthorized` occurs, the interceptor aggressively strips the token, clears Zustand, and redirects to `/login`.

## Route Architecture
```text
React Router 7
├── Public Routes (Unauthenticated entry)
│   ├── /login
│   └── /register
└── Protected Routes (Requires valid Zustand auth state)
    └── MainLayout
        ├── /dashboard
        └── /... (future pages)
```

## Hydration
On application startup (`App.tsx` mount), the Zustand `auth-store` attempts hydration:
1. Validates local token existence.
2. Invokes `/api/v1/user/info` to fetch canonical user state natively.
3. Removes token and sets `isHydrating = false` if 401 returns.
4. Triggers protected-route gates accordingly.

## 401 Handling
To avoid redirection loops:
- `401` errors occurring strictly on `/user/login` or `/user/register` bypass global logout logic (the API response is fed to the component for UI messaging).
- `401` errors on any other endpoint trigger a hard cleanup sequence resulting in forced redirection to `/login`.

