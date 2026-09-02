# Phase 02: Gateway & Authentication

## Phase Objective
Build the dual-stack API servers (Go Gin & Python Quart) and implement the authentication and session management layer (JWT, Login/Register).

## Why This Phase Comes Here
All APIs require authentication and a web server to receive requests. The dual-stack router is the entry point for the frontend.

## Dependencies
Depends on:
- Phase 01

Required by:
- Phase 03, Phase 04

## Phase Architecture
Go Gin acts as the high-concurrency API server (and reverse proxy logic), while Python Quart runs as the ASGI server for ML tasks. Auth logic utilizes JWTs stored in Redis.

## Subphase Order
01-go-gin-gateway -> 02-python-quart-service -> 03-authentication-flow -> 04-tenant-middleware

## Phase Deliverable
Working API servers that can register users, issue JWT tokens, and protect authenticated routes.

## Phase Definition of Done
- Go server runs on port 9380.
- Python server runs on a separate port or handled via Go reverse proxy.
- User login returns valid JWT token.

## What NOT To Build Yet
Knowledge base APIs, File uploads.

## Next Phase
Phase 03: Knowledge Base & Document Management
