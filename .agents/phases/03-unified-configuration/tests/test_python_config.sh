#!/bin/bash
set -e
python3 common/settings.py conf/service_conf.yaml > /dev/null
echo "Python config test passed."
