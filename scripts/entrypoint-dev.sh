#!/bin/bash
# ============================================
# Development Backend Entrypoint
# Simplified: only runs migrations and starts server
# User seeding is handled by Alembic migration
# ============================================

set -e

echo "[START] SanskritiSetu Backend"

# Wait for PostgreSQL
echo "[WAIT] PostgreSQL..."
max_attempts=30
attempt=1

while [ $attempt -le $max_attempts ]; do
    if pg_isready -h postgres -U postgres -d sanskritisetu 2>/dev/null; then
        echo "[OK] PostgreSQL ready"
        break
    fi
    echo "  Attempt $attempt/$max_attempts"
    sleep 1
    attempt=$((attempt + 1))
done

if [ $attempt -gt $max_attempts ]; then
    echo "[ERROR] PostgreSQL timeout"
    exit 1
fi

# Wait for Redis
redis_wait=0
redis_max_wait=30
until redis-cli -h redis -p 6379 ping 2>/dev/null | grep -q PONG; do
    if [ $redis_wait -ge $redis_max_wait ]; then
        echo "[WARN] Redis not available after ${redis_max_wait}s, continuing anyway"
        break
    fi
    echo "  Redis wait $redis_wait/$redis_max_wait"
    sleep 1
    redis_wait=$((redis_wait + 1))
done
if [ $redis_wait -lt $redis_max_wait ]; then
    echo "[OK] Redis ready"
fi

# Run migrations (includes user seeding via Alembic)
echo "[MIGRATE] Running Alembic migrations..."
export RUN_MIGRATIONS=true
python -m alembic -c /app/src/alembic.ini upgrade head
echo "[OK] Migrations complete"

# Show config status
echo "[CONFIG] Status:"
[ -n "$JWT_SECRET_KEY" ] && echo "  JWT: configured" || echo "  JWT: missing"
[ -n "$DEEPSEEK_API_KEY" ] && echo "  DeepSeek: configured" || echo "  DeepSeek: not set"

# Start server
# Start server or run custom command
if [ "$#" -gt 0 ]; then
    exec "$@"
else
    echo "[START] FastAPI on http://0.0.0.0:8000"
    exec uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload --log-level info --lifespan on
fi
