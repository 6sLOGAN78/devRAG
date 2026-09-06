#!/bin/bash
set -e
cat << 'BAD' > invalid_conf.yaml
mysql:
  host: mysql
  port: -1
  user: u
  password: p
  db: d
BAD
if go run cmd/config_main.go invalid_conf.yaml > /dev/null 2>&1; then echo "Go should have failed on invalid port"; exit 1; fi
if python3 common/settings.py invalid_conf.yaml > /dev/null 2>&1; then echo "Py should have failed on invalid port"; exit 1; fi
rm invalid_conf.yaml
echo "Invalid config test passed."
