#!/bin/bash
set -e
python3 -m api.db.test_db
echo "Python tests passed"
