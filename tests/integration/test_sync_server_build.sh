#!/usr/bin/env bash
set -euo pipefail

echo "=== Fase 4.1: sync-server Dockerfile check ==="

# Check package-lock.json bestaat
if [ ! -f "services/sync-server/package-lock.json" ]; then
  echo "FAIL: services/sync-server/package-lock.json ontbreekt"
  exit 1
fi

# Check Dockerfile gebruikt npm ci
if ! grep -q "npm ci" services/sync-server/Dockerfile; then
  echo "FAIL: Dockerfile gebruikt geen 'npm ci'"
  exit 1
fi

# Check BuildKit cache mount
if ! grep -q "mount=type=cache" services/sync-server/Dockerfile; then
  echo "FAIL: Dockerfile heeft geen BuildKit cache mount"
  exit 1
fi

# Bouw de image
DOCKER_BUILDKIT=1 docker build services/sync-server/ -t sync-server-test:ci
echo "PASS: sync-server Docker build geslaagd"

docker rmi sync-server-test:ci
echo "PASS: Alle checks geslaagd"
