#!/bin/bash
set -e
echo "Running Database Tests..."
docker compose -f docker/docker-compose-base.yml exec -T mysql mysql -u root -proot -e "DROP DATABASE IF EXISTS rag_flow; CREATE DATABASE rag_flow CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

export MYSQL_HOST=127.0.0.1
export MYSQL_PORT=13306

bash .agents/phases/04-core-database-models/tests/test_go_models.sh
bash .agents/phases/04-core-database-models/tests/test_python_models.sh

echo "All DB tests passed!"
