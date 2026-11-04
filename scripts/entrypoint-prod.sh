#!/bin/bash
# ============================================
# Production Backend Entrypoint
# Runs migrations and starts FastAPI
# ============================================

set -e

echo "[START] SanskritiSetu Backend"

# ============================================
# 0. Pre-flight: required env vars
# ============================================
for var in DATABASE_URL SECRET_KEY JWT_SECRET_KEY; do
    if [ -z "${!var:-}" ]; then
        echo "[ERROR] Required environment variable $var is not set"
        exit 1
    fi
done

# Graceful shutdown: forward SIGTERM to uvicorn so in-flight requests finish
# Azure Container Apps sends SIGTERM before SIGKILL (30s window)
# Guard with -n check: APP_PID is set only after uvicorn starts; || true
# prevents the trap itself from failing if kill/wait returns non-zero.
trap 'echo "[STOP] SIGTERM received — shutting down gracefully"; if [ -n "${APP_PID:-}" ]; then kill -TERM "$APP_PID" 2>/dev/null || true; wait "$APP_PID" || true; fi' TERM INT

# ============================================
# 1. Wait for PostgreSQL
# ============================================
echo "[WAIT] PostgreSQL..."
python3 << 'PYEOF'
import time, sys, os
from sqlalchemy import create_engine

max_attempts = 30
db_url = os.getenv('DATABASE_URL', 'postgresql+asyncpg://postgres:postgres@postgres:5432/sanskritisetu')
db_url_sync = db_url.replace('asyncpg', 'psycopg2')

for attempt in range(1, max_attempts + 1):
    try:
        engine = create_engine(db_url_sync)
        conn = engine.connect()
        conn.close()
        print('postgres:5432 - accepting connections')
        sys.exit(0)
    except Exception as e:
        if attempt == max_attempts:
            print(f'[ERROR] PostgreSQL did not become ready in time')
            sys.exit(1)
        time.sleep(2)
PYEOF

echo "[OK] PostgreSQL ready"

# ============================================
# 2. Run Alembic Migrations (optional)
# ============================================
# Migrations are normally run by the migration-job Container App Job BEFORE this
# app starts. Set RUN_MIGRATIONS=true only for local dev or one-off deployments.
if [ "${RUN_MIGRATIONS:-false}" = "true" ]; then
    echo "[MIGRATE] Running Alembic migrations..."
    if python3 -m alembic -c /app/src/alembic.ini upgrade head; then
        echo "[OK] Migrations completed successfully"
    else
        echo "[ERROR] Alembic migration failed."
        exit 1
    fi
else
    echo "[MIGRATE] Skipping migrations (RUN_MIGRATIONS not set — migration-job handles this)"
fi

# ============================================
# 3. Start Gunicorn + UvicornWorker (ADR-010 + ADR-011)
# ============================================
echo "[START] Gunicorn+UvicornWorker on 0.0.0.0:8000"
gunicorn src.main:app \
    -c gunicorn_config.py &
APP_PID=$!
wait $APP_PID
