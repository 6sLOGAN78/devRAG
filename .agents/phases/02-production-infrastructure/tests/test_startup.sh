#!/bin/bash
set -e
echo "Testing startup..."
docker compose -f docker/docker-compose-base.yml up -d
