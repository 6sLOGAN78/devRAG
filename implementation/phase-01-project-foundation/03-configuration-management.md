# 03 - Unified Configuration Management

## Objective
Implement a shared configuration schema (`conf/service_conf.yaml`) that provides identical truth to both the Go backend and Python backend.

## Production Requirements
In a dual-stack system, having two different config files is a recipe for production disaster. Both Go and Python MUST parse the exact same YAML file to retrieve database URIs, API keys, and internal ports.

### Config Schema (`service_conf.yaml`)
Must include sections for:
- `mysql`: host, port, user, password, db.
- `redis`: host, port, db.
- `minio`: endpoint, access_key, secret_key.
- `infinity`: host, port.
- `nats`: endpoints.
- `ragflow`: HTTP ports for Go (9384) and Python (9380).

## Implementation Tasks
- [ ] Create `conf/service_conf.yaml` schema with sensible local defaults.
- [ ] **Go implementation:** Write `internal/config/config.go` using Viper or koanf to unmarshal the YAML into a Go struct.
- [ ] **Python implementation:** Write `common/settings.py` using Pydantic Settings or PyYAML to parse the YAML into Python classes.
- [ ] Write startup assertions in both languages to panic/exit if the config file is unreadable or missing required keys.

## Deliverable
A single `service_conf.yaml` file that successfully boots both backend engines.
