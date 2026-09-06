# Authentication Contract

## Overview
The Go Gin gateway is the primary owner of authentication for devRAG. It provides registration, login, JWT issuance, and Redis-backed session validation.

## Registration
**POST** `/api/v1/user/register`
- **Request Schema:** `{"email": "...", "password": "...", "nickname": "..."}`
- **Validation:** email required, password >= 8 chars.
- **Success:** `201 Created`
- **Conflict:** `409 Conflict` (if email already registered)

## Login
**POST** `/api/v1/user/login`
- **Request Schema:** `{"email": "...", "password": "..."}`
- **Success:** `200 OK` with `{"token": "JWT", "user_id": "...", "email": "...", "nickname": "..."}`
- **Failure:** `401 Unauthorized` (Invalid credentials)
- **Side effects:** Creates an active session in Redis.

## JWT Claims
- `user_id`: The ID of the authenticated user.
- `session_id`: Unique identifier tying this token to a specific Redis session.
- `exp`: Expiration timestamp.
- `iat`: Issued at timestamp.

## Redis Session Contract
- **Key Format:** `session:{user_id}`
- **Value Format:** JSON object containing `{"session_id": "..."}`
- **TTL:** Defines the lifetime of the session, matching the JWT or configured via `SESSION_TTL_MINUTES`.
- **Invalidation:** Sessions are invalidated by deleting the key. Only the active `session_id` stored is valid.

## Protected Routes
- **Header:** `Authorization: Bearer <JWT>`
- **Behavior:** The `Auth` middleware extracts the JWT, verifies its signature, asserts it is not expired, then asserts the `session_id` inside the JWT precisely matches the active `session_id` inside Redis at `session:{user_id}`.
- **Context Injection:** On success, `user_id` is propagated to downstream handlers via the Gin context `c.Set("user_id", ...)`.

## Go/Python Boundary
Authentication is **owned exclusively by the Go Gateway**.
Future Python endpoints that require authentication must rely on this established contract (e.g., verifying the JWT and Redis session) or communicate with the Go gateway. Python will not manage standalone authentication logic unless explicitly requested in a future phase.
