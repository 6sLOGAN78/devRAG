## Objective
Initialize the root monorepo, define the workspace boundaries (web, cmd, internal, api, agent, deepdoc, common), and configure linting/formatting standards.

## Why Now?
Before writing any code, the physical structure of the dual-stack (Go/Python) and React frontend repository must be established so that CI/CD and developers share the same environment.

## Dependencies
None.

## Implementation Tasks
- [ ] Initialize Git repository.
- [ ] Create base directories: `web/`, `cmd/`, `internal/`, `api/`, `agent/`, `deepdoc/`, `common/`, `rag/`.
- [ ] Setup Node.js / React app in `web/` using Vite or Next.js.
- [ ] Initialize Go modules in root or `cmd/`/`internal/`.
- [ ] Initialize Python environment (requirements.txt / Poetry) in `api/`.
- [ ] Configure Prettier/ESLint for frontend.
- [ ] Configure `golangci-lint` for Go.
- [ ] Configure `ruff` / `black` / `mypy` for Python.

## Components
- Monorepo structural foundation.

## Files
- `package.json` (root/web)
- `go.mod`
- `pyproject.toml` or `requirements.txt`
- `.gitignore`
- `.editorconfig`

## Interfaces
N/A

## Data Changes
N/A

## Data Flow
N/A

## Testing
- Verify linting scripts run successfully on empty projects.

## Deliverable
A clean, standardized monorepo structure ready for code.

## Definition of Done
- All base directories created.
- Dependency managers (npm/yarn/pnpm, go mod, pip/poetry) initialized.
- Linter hooks configured.

## Next Subphase
02-infrastructure-services