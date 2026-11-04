#!/usr/bin/env bash
set -eu
echo "=== FASE 1 smoke: nginx-activepieces.conf ==="
if [ ! -f "nginx-activepieces.conf" ]; then
  echo "FAIL: nginx-activepieces.conf ontbreekt"
  exit 1
fi
# Test nginx syntax
docker run --rm -v "$(pwd)/nginx-activepieces.conf:/etc/nginx/conf.d/test.conf:ro" \
  nginx:alpine nginx -t -c /etc/nginx/nginx.conf 2>&1 | grep -q "syntax is ok"
echo "PASS: nginx configuratie syntax geldig"
