## Objective
Implement a shared configuration mechanism (e.g., YAML + Env vars) that both the Go backend and Python backend can read to connect to infrastructure.

## Why Now?
Hardcoded credentials lead to security risks and deployment issues. Both stacks need a unified truth for database URIs, API keys, and internal ports.

## Dependencies
- 02-infrastructure-services

## Implementation Tasks
- [ ] Define `conf/service_conf.yaml` schema.
- [ ] Implement Go config loader (using Viper or koanf) in `internal/config/`.
- [ ] Implement Python config loader (using Pydantic Settings or PyYAML) in `common/settings.py`.
- [ ] Expose DB, Redis, MinIO, and VectorDB connection strings to both languages.

## Components
- Config Loader (Go)
- Settings Module (Python)

## Files
- `conf/service_conf.yaml`
- `internal/config/config.go`
- `common/settings.py`

## Interfaces
N/A

## Data Changes
N/A

## Data Flow
File System -> Config Loader -> Application Memory

## Testing
- Write Go unit test to parse `service_conf.yaml`.
- Write Python unit test to parse `service_conf.yaml`.

## Deliverable
A unified configuration file readable by both backend services.

## Definition of Done
- Configuration file format is agreed upon.
- Both Go and Python can parse it and instantiate connection structs/classes.

## Next Subphase
04-database-models