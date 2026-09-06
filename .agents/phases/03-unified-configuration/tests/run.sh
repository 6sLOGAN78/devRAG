#!/bin/bash
set -e
echo "Running configuration tests..."
bash .agents/phases/03-unified-configuration/tests/test_schema.sh
bash .agents/phases/03-unified-configuration/tests/test_go_config.sh
bash .agents/phases/03-unified-configuration/tests/test_python_config.sh
bash .agents/phases/03-unified-configuration/tests/test_cross_language.sh
bash .agents/phases/03-unified-configuration/tests/test_missing_config.sh
bash .agents/phases/03-unified-configuration/tests/test_invalid_config.sh
bash .agents/phases/03-unified-configuration/tests/test_environment_overrides.sh
echo "All config tests passed!"
