#!/bin/bash
set -e
echo "Testing health..."
echo "Waiting for services to be healthy..."
sleep 15
for service in mysql redis minio nats infinity nginx; do
  STATUS=$(docker inspect --format='{{json .State.Health.Status}}' $service)
  if [ "$STATUS" != '"healthy"' ]; then
    echo "$service is not healthy ($STATUS)"
    exit 1
  fi
  echo "$service is healthy"
done
