## Objective
Implement User Registration, Login, and JWT generation in the Go gateway, storing session state in Redis.

## Why Now?
Users must authenticate before accessing the system.

## Dependencies
- 01-go-gin-gateway
- 04-database-models (Phase 01)

## Implementation Tasks
- [ ] Create `POST /api/v1/user/register` handler (hash password, save to DB).
- [ ] Create `POST /api/v1/user/login` handler (verify hash, generate JWT).
- [ ] Implement JWT generation utility.
- [ ] Store active session token/metadata in Redis with TTL.
- [ ] Create Auth Middleware for Gin to validate JWT on protected routes.

## Components
- Auth Handler
- Auth Middleware
- Password Hasher
- JWT Signer

## Files
- `internal/handler/auth.go`
- `internal/middleware/auth.go`
- `internal/service/user.go`

## Interfaces
- `POST /api/v1/user/register`
- `POST /api/v1/user/login`

## Data Changes
Modifies `user` table. Reads/Writes Redis keys (`session:{user_id}`).

## Data Flow
Client -> Auth Handler -> DB (verify) -> Redis (store session) -> JWT Response

## Testing
- Unit test password hashing.
- Integration test for login flow and protected route access.

## Deliverable
Working authentication system.

## Definition of Done
- User can register.
- User can login and receive JWT.
- Invalid tokens are rejected by middleware.

## Next Subphase
04-tenant-middleware