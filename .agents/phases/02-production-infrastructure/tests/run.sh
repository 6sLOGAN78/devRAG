#!/bin/bash
set -e
echo "Running all infrastructure tests..."
bash .agents/phases/02-production-infrastructure/tests/test_startup.sh
bash .agents/phases/02-production-infrastructure/tests/test_health.sh
echo "All tests passed!"
