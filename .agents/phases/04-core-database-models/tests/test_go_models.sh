#!/bin/bash
set -e
go run cmd/test_db.go
echo "Go tests passed"
