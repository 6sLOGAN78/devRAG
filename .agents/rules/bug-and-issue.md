---
description: Post-implementation bug and issue scanning procedure
trigger: model_decision
---
# Post-Implementation Bug & Issue Scan

Whenever you finish implementing a new feature in this repository, you MUST follow this prompt to scan the codebase and verify your work:

1. **Self-Review Checklist:**
   - Did I handle all error cases gracefully (no unhandled panics or exceptions)?
   - Does the code conform to the Handler -> Service -> DAO layered architecture?
   - Are `tenant_id` filters correctly applied to all database and vector store queries?
   - Do my changes in the Go backend accidentally break expectations in the Python API (or vice versa)?

2. **Action:**
   - Actively search the codebase to verify the new feature integrates correctly.
   - If any bugs, logical gaps, or missing tests are found during this self-scan, **fix them immediately**.
   - If there are architectural issues or limitations that cannot be fixed immediately, document them in `.agents/issues.md`.
