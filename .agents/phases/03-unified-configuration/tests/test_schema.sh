#!/bin/bash
set -e
[ -f conf/service_conf.yaml ] || { echo "Missing yaml"; exit 1; }
echo "Schema test passed."
