#!/bin/bash
set -e
export PYTHONPATH=.
pytest tests/unit
echo "Python Quart tests passed!"
