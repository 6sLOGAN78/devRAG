#!/bin/bash
set -e
go run cmd/config_main.go conf/service_conf.yaml > /dev/null
echo "Go config test passed."
