#!/bin/bash
set -e
export MYSQL_HOST="test_env_host"
go_out=$(MYSQL_HOST="test_env_host" go run cmd/config_test/config_main.go conf/service_conf.yaml)
if ! echo "$go_out" | grep -q '"host": "test_env_host"'; then echo "Go missed override"; exit 1; fi
py_out=$(MYSQL_HOST="test_env_host" python3 common/settings.py conf/service_conf.yaml)
if ! echo "$py_out" | grep -q '"host": "test_env_host"'; then echo "Py missed override"; exit 1; fi
echo "Environment override test passed."
