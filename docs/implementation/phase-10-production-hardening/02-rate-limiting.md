## Objective
Implement Redis-based rate limiting and robust error handling in the API Gateways.

## Why Now?
Production systems must protect LLM API budgets and infrastructure from abuse.

## Dependencies
- Phase 02 (Gateway)

## Implementation Tasks
- [ ] Go: Add Redis rate limiter middleware to Gin (Token Bucket algorithm).
- [ ] Apply stricter limits on `/chat/completions` and `/document/upload`.
- [ ] Standardize JSON error responses across Go and Python.
- [ ] Implement central structured logging (Uber Zap / Python logging).

## Components
- Rate Limiter Middleware
- Logging System

## Files
- `internal/middleware/ratelimit.go`
- `api/utils/logger.py`

## Interfaces
- HTTP 429 Too Many Requests

## Data Changes
N/A

## Data Flow
Client -> Rate Limiter -> Handler

## Testing
- Hammer the API with requests and verify HTTP 429 responses.

## Deliverable
Secure and resilient API.

## Definition of Done
- Abuse is prevented via automatic rate limiting.

## Next Subphase
03-admin-dashboard