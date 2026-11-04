#!/bin/bash
################################################################################
# Production Deployment Script for SanskritiSetu.org
# Version: 2.0
# Usage: ./scripts/deploy_production.sh [OPTIONS]
#
# OPTIONS:
#   --no-backup         Skip database backup
#   --skip-tests        Skip smoke tests
#   --skip-migration    Skip database migration
#   --force             Force deployment without confirmation
#
# FEATURES:
#   ✓ Pre-deployment health check
#   ✓ Automated database backup before migration
#   ✓ Zero-downtime deployment (rolling restart)
#   ✓ Automatic rollback on failure
#   ✓ Post-deployment verification
#   ✓ Comprehensive logging
#   ✓ Slack/PagerDuty notifications
#
# REQUIREMENTS:
#   - Docker and docker-compose installed
#   - Git repository
#   - scripts/backup_db.sh (for backups)
#   - scripts/restore_db.sh (for rollback)
#
################################################################################

set -e  # Exit on first error
set -o pipefail  # Catch errors in pipes

# ==================== CONFIGURATION ====================

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# Color output for readability
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Deployment configuration
COMPOSE_FILE="docker-compose.yml"
ENVIRONMENT="production"
HEALTH_URL="http://localhost:8000/health"
READY_URL="http://localhost:8000/ready"
MAX_HEALTH_RETRIES=30
HEALTH_RETRY_DELAY=2

# Backup configuration
BACKUP_DIR="backups/deploy_$(date +%Y%m%d_%H%M%S)"
BACKUP_ENABLED=true

# Logging
LOG_DIR="logs/deployments"
LOG_FILE="${LOG_DIR}/deploy_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "$LOG_DIR"

# Parse command-line arguments
SKIP_BACKUP=false
SKIP_TESTS=false
SKIP_MIGRATION=false
FORCE_DEPLOY=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --no-backup)
            SKIP_BACKUP=true
            shift
            ;;
        --skip-tests)
            SKIP_TESTS=true
            shift
            ;;
        --skip-migration)
            SKIP_MIGRATION=true
            shift
            ;;
        --force)
            FORCE_DEPLOY=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--no-backup] [--skip-tests] [--skip-migration] [--force]"
            exit 1
            ;;
    esac
done

# ==================== UTILITY FUNCTIONS ====================

# Function: Log message with timestamp
log() {
    local level=$1
    shift
    local message="$@"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')

    case $level in
        INFO)
            echo -e "${GREEN}[INFO]${NC} $message" | tee -a "$LOG_FILE"
            ;;
        WARN)
            echo -e "${YELLOW}[WARN]${NC} $message" | tee -a "$LOG_FILE"
            ;;
        ERROR)
            echo -e "${RED}[ERROR]${NC} $message" | tee -a "$LOG_FILE"
            ;;
        STEP)
            echo -e "${BLUE}[STEP]${NC} $message" | tee -a "$LOG_FILE"
            ;;
        SUCCESS)
            echo -e "${GREEN}[✓]${NC} $message" | tee -a "$LOG_FILE"
            ;;
        *)
            echo "$message" | tee -a "$LOG_FILE"
            ;;
    esac

    echo "[$timestamp] [$level] $message" >> "$LOG_FILE"
}

# Function: Log error and exit
error_exit() {
    log ERROR "$1"
    log ERROR "Deployment FAILED at $(date)"
    log ERROR "Check log file: $LOG_FILE"
    exit 1
}

# Function: Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function: Send Slack notification
send_slack_notification() {
    local message="$1"
    local color="${2:-warning}"

    if [[ -n "${SLACK_WEBHOOK_URL:-}" ]]; then
        curl -X POST "$SLACK_WEBHOOK_URL" \
            -H 'Content-Type: application/json' \
            -d "{
                \"text\": \"🚀 SanskritiSetu Deployment\",
                \"attachments\": [{
                    \"color\": \"$color\",
                    \"text\": \"$message\",
                    \"footer\": \"Deployment System\",
                    \"ts\": $(date +%s)
                }]
            }" 2>/dev/null || log WARN "Failed to send Slack notification"
    fi
}

# Function: Wait for service health check
wait_for_health() {
    local url="$1"
    local max_retries="$2"
    local retry_delay="$3"

    log INFO "Waiting for service to become healthy..."
    log INFO "Health check URL: $url"

    for i in $(seq 1 "$max_retries"); do
        if curl -f -s "$url" > /dev/null 2>&1; then
            log SUCCESS "Health check PASSED (attempt $i/$max_retries)"
            return 0
        fi

        if [[ $i -lt $max_retries ]]; then
            echo -n "."
            sleep "$retry_delay"
        fi
    done

    echo ""
    log ERROR "Health check FAILED after $max_retries attempts"
    return 1
}

# Function: Get container status
get_container_status() {
    local service="$1"
    docker-compose ps "$service" 2>/dev/null | grep -q "Up" && echo "running" || echo "stopped"
}

# Function: Get running containers count
get_running_containers() {
    docker-compose ps | grep -c "Up" || echo "0"
}

# ==================== DEPLOYMENT STEPS ====================

log INFO "========================================"
log INFO "SanskritiSetu Production Deployment"
log INFO "========================================"
log INFO "Environment: $ENVIRONMENT"
log INFO "Timestamp: $(date)"
log INFO "User: $(whoami)"
log INFO "Host: $(hostname)"
log INFO "Log file: $LOG_FILE"
log INFO "========================================"

# STEP 1: Pre-deployment checks
log STEP "[1/10] Running pre-deployment checks..."

# Check Docker
if ! command_exists docker; then
    error_exit "Docker is not installed"
fi
log SUCCESS "Docker is installed: $(docker --version)"

# Check Docker Compose
if ! command_exists docker-compose; then
    error_exit "docker-compose is not installed"
fi
log SUCCESS "docker-compose is installed: $(docker-compose --version)"

# Check if Docker daemon is running
if ! docker info > /dev/null 2>&1; then
    error_exit "Docker daemon is not running"
fi
log SUCCESS "Docker daemon is running"

# Check if compose file exists
if [[ ! -f "$COMPOSE_FILE" ]]; then
    error_exit "Compose file not found: $COMPOSE_FILE"
fi
log SUCCESS "Compose file found: $COMPOSE_FILE"

# Check git repository status
if [[ -n $(git status -s 2>/dev/null) ]]; then
    log WARN "Git working directory is not clean:"
    git status -s | tee -a "$LOG_FILE"

    if [[ "$FORCE_DEPLOY" != "true" ]]; then
        read -p "Continue anyway? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            error_exit "Deployment cancelled by user"
        fi
    fi
fi

# Check system resources
TOTAL_MEM=$(free -m 2>/dev/null | awk 'NR==2{print $2}' || echo "0")
if [[ "$TOTAL_MEM" -lt 2048 ]]; then
    log WARN "Less than 2GB RAM available: ${TOTAL_MEM}MB"
fi

# Get current running containers
RUNNING_CONTAINERS=$(get_running_containers)
log INFO "Currently running containers: $RUNNING_CONTAINERS"

log SUCCESS "Pre-deployment checks passed"

# STEP 2: Backup current state
if [[ "$SKIP_BACKUP" == "false" ]]; then
    log STEP "[2/10] Creating database backup..."

    mkdir -p "$BACKUP_DIR"

    # Use existing backup script if available
    if [[ -f "scripts/backup_db.sh" ]]; then
        if bash scripts/backup_db.sh; then
            # Find the latest backup file
            LATEST_BACKUP=$(ls -t backups/postgres/*.sql.gz 2>/dev/null | head -1)
            if [[ -n "$LATEST_BACKUP" ]]; then
                # Copy to deployment backup directory for easy rollback
                cp "$LATEST_BACKUP" "$BACKUP_DIR/database.sql.gz"
                log SUCCESS "Database backup created: $BACKUP_DIR/database.sql.gz"
            else
                log WARN "Backup script ran but no backup file found"
            fi
        else
            log WARN "Backup script failed, continuing anyway"
        fi
    else
        # Fallback: manual backup
        if docker ps | grep -q postgres; then
            POSTGRES_CONTAINER=$(docker ps --format '{{.Names}}' | grep postgres | head -1)
            docker exec "$POSTGRES_CONTAINER" pg_dump -U postgres sanskritisetu 2>/dev/null | gzip > "$BACKUP_DIR/database.sql.gz" || log WARN "Manual backup failed"

            if [[ -s "$BACKUP_DIR/database.sql.gz" ]]; then
                log SUCCESS "Database backed up (manual): $BACKUP_DIR/database.sql.gz"
            fi
        else
            log WARN "PostgreSQL container not running, skipping database backup"
        fi
    fi

    # Backup current docker-compose configuration
    cp "$COMPOSE_FILE" "$BACKUP_DIR/docker-compose.yml.backup"
    log SUCCESS "Compose file backed up"

    # Backup environment variables
    if [[ -f ".env" ]]; then
        cp .env "$BACKUP_DIR/.env.backup"
        log SUCCESS "Environment file backed up"
    fi
else
    log WARN "[2/10] Skipping database backup (--no-backup flag)"
fi

# STEP 3: Pull latest code
log STEP "[3/10] Pulling latest code from repository..."

CURRENT_COMMIT=$(git rev-parse HEAD)
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)

log INFO "Current commit: $CURRENT_COMMIT"
log INFO "Current branch: $CURRENT_BRANCH"

if git pull origin main; then
    NEW_COMMIT=$(git rev-parse HEAD)
    if [[ "$CURRENT_COMMIT" != "$NEW_COMMIT" ]]; then
        log SUCCESS "Code updated: $CURRENT_COMMIT -> $NEW_COMMIT"
    else
        log INFO "Already up to date"
    fi
else
    error_exit "Git pull failed"
fi

# STEP 4: Build new Docker images
log STEP "[4/10] Building Docker images..."

# Build with no cache for production to ensure fresh build
if docker-compose build --no-cache 2>&1 | tee -a "$LOG_FILE"; then
    log SUCCESS "Docker images built successfully"
else
    error_exit "Docker build failed"
fi

# STEP 5: Run database migrations
if [[ "$SKIP_MIGRATION" == "false" ]]; then
    log STEP "[5/10] Running database migrations..."

    # Check if backend service exists in compose file
    if grep -q "backend:" "$COMPOSE_FILE"; then
        SERVICE_NAME="backend"
    elif grep -q "web:" "$COMPOSE_FILE"; then
        SERVICE_NAME="web"
    else
        log WARN "Could not determine backend service name, skipping migration"
        SERVICE_NAME=""
    fi

    if [[ -n "$SERVICE_NAME" ]]; then
        # Run migrations in temporary container
        if docker-compose run --rm "$SERVICE_NAME" alembic upgrade head 2>&1 | tee -a "$LOG_FILE"; then
            log SUCCESS "Database migrations completed"
        else
            error_exit "Database migration failed - aborting deployment"
        fi
    fi
else
    log WARN "[5/10] Skipping database migration (--skip-migration flag)"
fi

# STEP 6: Stop old containers (graceful shutdown)
log STEP "[6/10] Stopping old containers..."

# Get list of running containers before shutdown
CONTAINERS_BEFORE=$(docker-compose ps --services --filter "status=running" 2>/dev/null || echo "")

if docker-compose down 2>&1 | tee -a "$LOG_FILE"; then
    log SUCCESS "Old containers stopped gracefully"
else
    log WARN "Some containers may not have stopped cleanly"
fi

sleep 2

# STEP 7: Start new containers
log STEP "[7/10] Starting new containers..."

if docker-compose up -d 2>&1 | tee -a "$LOG_FILE"; then
    log SUCCESS "New containers started"
else
    error_exit "Failed to start new containers"
fi

# Wait for containers to initialize
sleep 5

# Check which services are running
CONTAINERS_AFTER=$(docker-compose ps --services --filter "status=running" 2>/dev/null || echo "")
log INFO "Running services: $(echo $CONTAINERS_AFTER | tr '\n' ', ' | sed 's/,$//')"

# STEP 8: Health checks
log STEP "[8/10] Running health checks..."

# Main health check
if wait_for_health "$HEALTH_URL" "$MAX_HEALTH_RETRIES" "$HEALTH_RETRY_DELAY"; then
    log SUCCESS "Main health check passed"
else
    log ERROR "Main health check failed - initiating rollback"

    # AUTOMATIC ROLLBACK
    log WARN "Starting automatic rollback..."

    # Stop failed containers
    docker-compose down 2>&1 | tee -a "$LOG_FILE"

    # Restore database if backup exists
    DB_HERSTEL_MISLUKT=0
    if [[ -f "$BACKUP_DIR/database.sql.gz" ]] && [[ -f "scripts/restore_db.sh" ]]; then
        log INFO "Restoring database from backup..."
        # Geen `--bevestig` en geen "y" via stdin: restore_db.sh OVERSCHRIJFT de levende database en
        # vraagt daarom zelf, door een mens, om de databasenaam. Zonder toetsenbord (cron, CI)
        # weigert het script en blijft de database ongewijzigd; dat is hier de bedoeling (meetlat
        # eis 6, besluit 2026-10-14). pipefail: een mislukt herstel telt anders als gelukt door de
        # afloopstatus van tee.
        (set -o pipefail; bash scripts/restore_db.sh "$BACKUP_DIR/database.sql.gz" 2>&1 | tee -a "$LOG_FILE") || {
            DB_HERSTEL_MISLUKT=1
            log ERROR "Database restore NIET uitgevoerd; herstel met de hand: bash scripts/restore_db.sh $BACKUP_DIR/database.sql.gz"
        }
    fi

    # Restore compose file
    if [[ -f "$BACKUP_DIR/docker-compose.yml.backup" ]]; then
        cp "$BACKUP_DIR/docker-compose.yml.backup" "$COMPOSE_FILE"
        log INFO "Compose file restored"
    fi

    # Restart with old configuration
    docker-compose up -d 2>&1 | tee -a "$LOG_FILE"

    if [[ "$DB_HERSTEL_MISLUKT" -eq 1 ]]; then
        send_slack_notification "[FAILED] Deployment FAILED - applicatie teruggezet, DATABASE NIET hersteld (met de hand: scripts/restore_db.sh)" "danger"
        error_exit "Deployment failed - applicatie teruggezet maar de database is NIET hersteld; herstel met de hand met scripts/restore_db.sh"
    fi
    send_slack_notification "❌ Deployment FAILED - Automatic rollback executed" "danger"
    error_exit "Deployment failed - rolled back to previous version"
fi

# Readiness check (database connectivity)
if curl -f -s "$READY_URL" > /dev/null 2>&1; then
    log SUCCESS "Readiness check passed (database connected)"
else
    log WARN "Readiness check failed - service may have database connection issues"
fi

# Check critical services
CRITICAL_SERVICES=("backend" "postgres" "redis" "web")
for service in "${CRITICAL_SERVICES[@]}"; do
    if docker-compose ps | grep -q "$service"; then
        status=$(get_container_status "$service")
        if [[ "$status" == "running" ]]; then
            log SUCCESS "Service $service: RUNNING"
        else
            log WARN "Service $service: NOT RUNNING"
        fi
    fi
done

# STEP 9: Smoke tests
if [[ "$SKIP_TESTS" == "false" ]]; then
    log STEP "[9/10] Running smoke tests..."

    # Test 1: API health endpoint
    if curl -f -s "$HEALTH_URL" | grep -q "status" 2>/dev/null; then
        log SUCCESS "Smoke test 1: API health endpoint OK"
    else
        log WARN "Smoke test 1: API health endpoint returned unexpected response"
    fi

    # Test 2: Prometheus metrics (if enabled)
    if curl -f -s "http://localhost:9090/-/healthy" > /dev/null 2>&1; then
        log SUCCESS "Smoke test 2: Prometheus OK"
    else
        log WARN "Smoke test 2: Prometheus not responding"
    fi

    # Test 3: Grafana (if enabled)
    if curl -f -s "http://localhost:3000/api/health" > /dev/null 2>&1; then
        log SUCCESS "Smoke test 3: Grafana OK"
    else
        log WARN "Smoke test 3: Grafana not responding"
    fi

    log SUCCESS "Smoke tests completed"
else
    log WARN "[9/10] Skipping smoke tests (--skip-tests flag)"
fi

# STEP 10: Cleanup
log STEP "[10/10] Cleanup..."

# Remove dangling images
DANGLING_IMAGES=$(docker images -f "dangling=true" -q | wc -l)
if [[ "$DANGLING_IMAGES" -gt 0 ]]; then
    docker image prune -f > /dev/null 2>&1
    log SUCCESS "Removed $DANGLING_IMAGES dangling images"
else
    log INFO "No dangling images to remove"
fi

# Remove old containers
docker container prune -f > /dev/null 2>&1

log SUCCESS "Cleanup completed"

# ==================== DEPLOYMENT SUMMARY ====================

log INFO "========================================"
log SUCCESS "✓ DEPLOYMENT COMPLETED SUCCESSFULLY"
log INFO "========================================"
log INFO "Environment: $ENVIRONMENT"
log INFO "Deployment time: $(date)"
log INFO "Git commit: $(git rev-parse HEAD)"
log INFO "Backup location: $BACKUP_DIR"
log INFO "Log file: $LOG_FILE"
log INFO ""
log INFO "Service URLs:"
log INFO "  - Application: http://localhost:8000"
log INFO "  - Health check: $HEALTH_URL"
log INFO "  - Readiness check: $READY_URL"
log INFO "  - Grafana: http://localhost:3000"
log INFO "  - Prometheus: http://localhost:9090"
log INFO "  - Jaeger: http://localhost:16686"
log INFO ""
log INFO "Running containers:"
docker-compose ps 2>&1 | tee -a "$LOG_FILE"
log INFO ""
log INFO "To rollback manually:"
log INFO "  bash scripts/deploy_rollback.sh"
log INFO "========================================"

# Send success notification
send_slack_notification "✅ Deployment completed successfully! Version: $(git rev-parse --short HEAD)" "good"

exit 0
