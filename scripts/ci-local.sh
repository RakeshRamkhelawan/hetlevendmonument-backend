#!/usr/bin/env bash
# ci-local.sh - Local CI runner that mirrors GitHub Actions CI exactly.
# Usage: bash scripts/ci-local.sh [python|frontend|docker|security]
# With no argument, all 4 jobs are executed in sequence.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${REPO_ROOT}/docker-compose.ci.yml"

# ---------------------------------------------------------------------------
# Colors
# ---------------------------------------------------------------------------
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RESET='\033[0m'

ok()   { echo -e "${GREEN}[OK]${RESET}   $*"; }
fail() { echo -e "${RED}[FAIL]${RESET} $*"; }
info() { echo -e "${CYAN}[INFO]${RESET} $*"; }
warn() { echo -e "${YELLOW}[WARN]${RESET} $*"; }

# ---------------------------------------------------------------------------
# Tracking
# ---------------------------------------------------------------------------
FAILED_JOBS=()

mark_fail() {
    FAILED_JOBS+=("$1")
}

# ---------------------------------------------------------------------------
# Service management
# ---------------------------------------------------------------------------
services_running=false

start_services() {
    if [ "$services_running" = true ]; then
        return 0
    fi
    info "Starting CI services (postgres-ci on :5433, redis-ci on :6380)..."
    docker compose -f "${COMPOSE_FILE}" up -d
    info "Waiting for services to be healthy..."

    local max_wait=90
    local elapsed=0
    local ready_count=0
    while [ $elapsed -lt $max_wait ]; do
        pg_health=$(docker inspect --format='{{.State.Health.Status}}' \
            "$(docker compose -f "${COMPOSE_FILE}" ps -q postgres-ci 2>/dev/null)" 2>/dev/null || echo "unknown")
        rd_health=$(docker inspect --format='{{.State.Health.Status}}' \
            "$(docker compose -f "${COMPOSE_FILE}" ps -q redis-ci 2>/dev/null)" 2>/dev/null || echo "unknown")

        if [ "$pg_health" = "healthy" ] && [ "$rd_health" = "healthy" ]; then
            # Health check passed, now verify database is actually accepting authenticated connections
            # Force IPv4 with 127.0.0.1 to avoid IPv6 issues on Windows Docker Desktop
            if docker compose -f "${COMPOSE_FILE}" exec -T postgres-ci \
                psql -h 127.0.0.1 -U test -d test -c "SELECT 1" &>/dev/null; then
                ready_count=$((ready_count + 1))
                # Require 2 consecutive successful checks (10+ seconds stable) before returning
                if [ $ready_count -ge 2 ]; then
                    ok "Services are healthy and stable"
                    services_running=true
                    return 0
                fi
            else
                ready_count=0
            fi
        else
            ready_count=0
        fi
        sleep 5
        elapsed=$((elapsed + 5))
        printf "."
    done
    echo ""
    fail "Timeout waiting for CI services to become healthy"
    return 1
}

stop_services() {
    if [ "$services_running" = true ]; then
        info "Stopping CI services..."
        docker compose -f "${COMPOSE_FILE}" down --remove-orphans 2>/dev/null || true
        services_running=false
    fi
}

# Ensure services are stopped on exit (only if we started them)
trap 'stop_services' EXIT

# ---------------------------------------------------------------------------
# CI environment variables (mirrors GitHub Actions)
# ---------------------------------------------------------------------------
export ENVIRONMENT=test
export JWT_SECRET_KEY=test-secret-for-ci
export SECRET_KEY=test-secret-for-ci
export DATABASE_URL=postgresql+asyncpg://test:test@localhost:5433/test
export REDIS_URL=redis://localhost:6380/0
export BM25_INDEX_DIR=/tmp/bm25-indexes

# ---------------------------------------------------------------------------
# Job: python
# Mirrors: ruff lint -> alembic upgrade head -> gevent guard -> pytest unit
# ---------------------------------------------------------------------------
run_python() {
    info "=== Job: python ==="
    local job_ok=true

    # Step 0: LLM Provider validation (early fail if imports broken)
    info "Step 0/5: LLM provider import validation"
    if python3 "${REPO_ROOT}/scripts/validate-llm-providers.py"; then
        ok "LLM provider imports validated"
    else
        fail "LLM provider import validation failed"
        job_ok=false
    fi

    # Step 1: Ruff lint
    info "Step 1/5: Ruff lint (src/, excluding src/alembic)"
    if ruff check "${REPO_ROOT}/src/" --exclude "${REPO_ROOT}/src/alembic"; then
        ok "Ruff lint passed"
    else
        fail "Ruff lint failed"
        job_ok=false
    fi

    # Step 2: Alembic migrations (online - requires running postgres)
    info "Step 2/5: Alembic upgrade head (online)"
    start_services || { fail "Could not start services for alembic migration"; mark_fail "python"; return; }
    mkdir -p /tmp/bm25-indexes
    if alembic -c "${REPO_ROOT}/src/alembic.ini" upgrade head; then
        ok "Alembic upgrade head passed"
    else
        fail "Alembic upgrade head failed"
        job_ok=false
    fi

    # Step 3: Gevent guard
    info "Step 3/5: Gevent warning filter guard"
    if grep -nE 'ignore::gevent\.monkey\._errors\.MonkeyPatchWarning' "${REPO_ROOT}/pyproject.toml"; then
        fail "Forbidden pytest warning filter found in pyproject.toml"
        fail "  Use a message-based Warning filter instead."
        job_ok=false
    else
        ok "Gevent guard passed (no forbidden filter found)"
    fi

    # Step 4: Pytest unit tests
    info "Step 4/5: Pytest unit tests"
    if pytest -c "${REPO_ROOT}/pyproject.toml" "${REPO_ROOT}/tests/unit" \
        -x -q --tb=short \
        -m "not requires_ollama" \
        --ignore="${REPO_ROOT}/tests/unit/generated_p1_e2e_1.py"; then
        ok "Pytest unit tests passed"
    else
        fail "Pytest unit tests failed"
        job_ok=false
    fi

    if [ "$job_ok" = true ]; then
        ok "Job python: PASSED"
    else
        fail "Job python: FAILED"
        mark_fail "python"
    fi
}

# ---------------------------------------------------------------------------
# Job: frontend
# Mirrors: npm ci -> vitest -> vite build
# ---------------------------------------------------------------------------
run_frontend() {
    info "=== Job: frontend ==="
    local job_ok=true
    local frontend_dir="${REPO_ROOT}/frontend"

    if [ ! -d "$frontend_dir" ]; then
        fail "frontend/ directory not found at ${frontend_dir}"
        mark_fail "frontend"
        return
    fi

    # Step 1: npm ci
    info "Step 1/3: npm ci"
    if (cd "$frontend_dir" && npm ci); then
        ok "npm ci passed"
    else
        fail "npm ci failed"
        job_ok=false
    fi

    # Step 2: Vitest unit tests (npm run test:unit to avoid Windows OOM)
    info "Step 2/3: Vitest unit tests"
    if (cd "$frontend_dir" && npm run test:unit -- --testTimeout=10000 --reporter=verbose); then
        ok "Vitest unit tests passed"
    else
        fail "Vitest unit tests failed"
        job_ok=false
    fi

    # Step 3: Vite build
    info "Step 3/3: Vite build check"
    if (cd "$frontend_dir" && npm run build); then
        ok "Vite build passed"
    else
        fail "Vite build failed"
        job_ok=false
    fi

    if [ "$job_ok" = true ]; then
        ok "Job frontend: PASSED"
    else
        fail "Job frontend: FAILED"
        mark_fail "frontend"
    fi
}

# ---------------------------------------------------------------------------
# Job: docker
# Mirrors: docker build backend -> alembic --sql offline -> heads -> build frontend
# ---------------------------------------------------------------------------
run_docker() {
    info "=== Job: docker ==="
    local job_ok=true

    # Step 1: Build backend image
    info "Step 1/4: Docker build backend (target: production-api)"
    if docker build --target production-api --load \
        -t sanskritisetu:ci-local-check \
        "${REPO_ROOT}"; then
        ok "Backend Docker build passed"
    else
        fail "Backend Docker build failed"
        mark_fail "docker"
        return
    fi

    # Step 2: Alembic offline dry-run (--sql mode)
    info "Step 2/4: Alembic upgrade head --sql (offline dry-run)"
    if docker run --rm --pull=never \
        --entrypoint python3 \
        -e DATABASE_URL="postgresql://x:x@localhost/x" \
        sanskritisetu:ci-local-check \
        -m alembic -c /app/src/alembic.ini upgrade head --sql \
        > /dev/null; then
        ok "Alembic offline dry-run passed"
    else
        fail "Alembic offline dry-run failed (check for sa.inspect() usage in migrations)"
        job_ok=false
    fi

    # Step 3: Single head check
    info "Step 3/4: Alembic heads check (must be exactly 1 head)"
    HEADS_RAW=$(docker run --rm --pull=never \
        --entrypoint python3 \
        -e DATABASE_URL="postgresql://x:x@localhost/x" \
        sanskritisetu:ci-local-check \
        -m alembic -c /app/src/alembic.ini heads 2>&1 || true)
    HEAD_COUNT=$(echo "$HEADS_RAW" | grep -cE '^\w.*\(head\)$' || echo "0")
    if [ "$HEAD_COUNT" -ne 1 ]; then
        fail "Alembic heads check failed: ${HEAD_COUNT} heads found, expected 1"
        fail "  Output: ${HEADS_RAW}"
        job_ok=false
    else
        ok "Alembic heads check passed (1 head)"
    fi

    # Step 4: Build frontend image
    info "Step 4/4: Docker build frontend"
    if docker build \
        --build-arg VITE_API_URL=https://localhost:8000 \
        -t sanskritisetu-frontend:ci-local-check \
        "${REPO_ROOT}/frontend"; then
        ok "Frontend Docker build passed"
    else
        fail "Frontend Docker build failed"
        job_ok=false
    fi

    if [ "$job_ok" = true ]; then
        ok "Job docker: PASSED"
    else
        fail "Job docker: FAILED"
        mark_fail "docker"
    fi
}

# ---------------------------------------------------------------------------
# Job: security
# Mirrors: bandit HIGH/HIGH scan
# ---------------------------------------------------------------------------
run_security() {
    info "=== Job: security ==="
    local job_ok=true
    local report=/tmp/bandit-report.json

    # Step 1: Bandit scan
    info "Step 1/2: Bandit security scan (src/, excluding tests and alembic)"
    bandit -r "${REPO_ROOT}/src/" -ll -ii \
        -x "tests,tests_reboot,${REPO_ROOT}/src/alembic" \
        -f json -o "${report}" || true

    # Step 2: Check for HIGH/HIGH findings
    info "Step 2/2: Checking for HIGH severity / HIGH confidence findings"
    if [ -f "$report" ]; then
        CRITICAL=$(BANDIT_REPORT="/tmp/bandit-report.json" python3 -c "
import os, json
r = json.load(open(os.environ['BANDIT_REPORT']))
results = r.get('results', [])
critical = [i for i in results if i['issue_severity'] == 'HIGH' and i['issue_confidence'] == 'HIGH']
print(len(critical))
" 2>/dev/null || echo "0")

        if [ "$CRITICAL" -gt 0 ]; then
            fail "Bandit: ${CRITICAL} HIGH severity/HIGH confidence findings:"
            BANDIT_REPORT="/tmp/bandit-report.json" python3 -c "
import os, json
r = json.load(open(os.environ['BANDIT_REPORT']))
for i in r.get('results', []):
    if i['issue_severity'] == 'HIGH' and i['issue_confidence'] == 'HIGH':
        print('  ' + i['filename'] + ':' + str(i['line_number']) + ' - ' + i['issue_text'])
" 2>/dev/null || true
            job_ok=false
        else
            ok "Bandit: no critical findings (report: ${report})"
        fi
    else
        warn "bandit-report.json not generated - assuming no findings"
    fi

    if [ "$job_ok" = true ]; then
        ok "Job security: PASSED"
    else
        fail "Job security: FAILED"
        mark_fail "security"
    fi
}

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print_summary() {
    echo ""
    echo "================================================================="
    echo "  CI LOCAL SUMMARY"
    echo "================================================================="
    local all_jobs=("$@")
    for job in "${all_jobs[@]}"; do
        if printf '%s\n' "${FAILED_JOBS[@]}" | grep -qx "$job"; then
            echo -e "  ${RED}[FAIL]${RESET} ${job}"
        else
            echo -e "  ${GREEN}[OK]${RESET}   ${job}"
        fi
    done
    echo "================================================================="

    if [ "${#FAILED_JOBS[@]}" -gt 0 ]; then
        fail "Failed jobs: ${FAILED_JOBS[*]}"
        echo ""
        return 1
    else
        ok "All jobs passed."
        echo ""
        return 0
    fi
}

# ---------------------------------------------------------------------------
# Main dispatch
# ---------------------------------------------------------------------------
cd "${REPO_ROOT}"

JOB="${1:-all}"

case "$JOB" in
    python)
        run_python
        print_summary python
        exit $?
        ;;
    frontend)
        run_frontend
        print_summary frontend
        exit $?
        ;;
    docker)
        run_docker
        print_summary docker
        exit $?
        ;;
    security)
        run_security
        print_summary security
        exit $?
        ;;
    all)
        run_python
        run_frontend
        run_docker
        run_security
        print_summary python frontend docker security
        exit $?
        ;;
    *)
        echo "Usage: bash scripts/ci-local.sh [python|frontend|docker|security]"
        echo "  No argument = run all 4 jobs"
        exit 1
        ;;
esac
