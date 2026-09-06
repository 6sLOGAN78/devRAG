#!/bin/bash
set -e
go run cmd/config_main.go conf/service_conf.yaml > go_out.json
python3 common/settings.py conf/service_conf.yaml > py_out.json
diff -i -w go_out.json py_out.json
echo "Cross-language test passed."
