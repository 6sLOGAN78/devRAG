#!/bin/bash
set -e
if go run cmd/config_test/config_main.go does_not_exist.yaml > /dev/null 2>&1; then echo "Go should have failed"; exit 1; fi
if python3 common/settings.py does_not_exist.yaml > /dev/null 2>&1; then echo "Py should have failed"; exit 1; fi
echo "Missing config test passed."
