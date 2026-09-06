# Go Entrypoints (`cmd/`)

Standard Go directory structure for application entrypoints.

## Structure
- `server/`: Contains `ragflow_server.go`, the primary Go API Gateway and syncer daemon. Run this to start the Go backend.
- `test_db/`: Utility script for testing database connectivity.
- `config_test/`: Utility for validating YAML configurations.
