#!/bin/bash
################################################################################
# Rollback Script for SanskritiSetu.org
# Version: 2.0
# Usage: ./scripts/deploy_rollback.sh [BACKUP_DIR]
#
# DESCRIPTION:
#   Rollback to a previous deployment state by restoring:
#   - Database from backup
#   - Docker containers from previous image
#   - Configuration files
#
# ARGUMENTS:
#   BACKUP_DIR    Optional. Path to backup directory.
#                 If not specified, uses the most recent backup.
#
# EXAMPLES:
#   ./scripts/deploy_rollback.sh
#   ./scripts/deploy_rollback.sh backups/deploy_20251128_143000
#
################################################################################

set -e  # Exit on error
set -o pipefail  # Catch errors in pipes

# ==================== CONFIGURATION ====================

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
COMPOSE_FILE="docker-compose.yml"
HEALTH_URL="http://localhost:8000/health"
MAX_HEALTH_RETRIES=30
HEALTH_RETRY_DELAY=2

# Logging
LOG_DIR="logs/rollbacks"
LOG_FILE="${LOG_DIR}/rollback_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "$LOG_DIR"

# ==================== UTILITY FUNCTIONS ====================

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
        SUCCESS)
            echo -e "${GREEN}[✓]${NC} $message" | tee -a "$LOG_FILE"
            ;;
        *)
            echo "$message" | tee -a "$LOG_FILE"
            ;;
    esac
}

error_exit() {
    log ERROR "$1"
    log ERROR "Rollback FAILED at $(date)"
    exit 1
}

wait_for_health() {
    local url="$1"
    local max_retries="$2"
    local retry_delay="$3"

    log INFO "Waiting for service to become healthy..."

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

# ==================== ROLLBACK PROCEDURE ====================

log INFO "========================================"
log INFO "SanskritiSetu Rollback Procedure"
log INFO "========================================"
log INFO "Timestamp: $(date)"
log INFO "User: $(whoami)"
log INFO "Host: $(hostname)"
log INFO "Log file: $LOG_FILE"
log INFO "========================================"

# STEP 1: Determine backup directory
BACKUP_DIR="${1:-}"

if [[ -z "$BACKUP_DIR" ]]; then
    # Find most recent deployment backup
    LATEST_BACKUP=$(ls -dt backups/deploy_* 2>/dev/null | head -1)

    if [[ -z "$LATEST_BACKUP" ]]; then
        # Try to find any recent postgres backup
        LATEST_DB_BACKUP=$(ls -t backups/postgres/*.sql.gz 2>/dev/null | head -1)

        if [[ -z "$LATEST_DB_BACKUP" ]]; then
            error_exit "No backup found for rollback. Please specify a backup directory."
        fi

        log WARN "No deployment backup found. Will restore from database backup only."
        DB_BACKUP_FILE="$LATEST_DB_BACKUP"
    else
        BACKUP_DIR="$LATEST_BACKUP"
        log INFO "Using most recent backup: $BACKUP_DIR"
    fi
else
    if [[ ! -d "$BACKUP_DIR" ]]; then
        error_exit "Backup directory not found: $BACKUP_DIR"
    fi
    log INFO "Using specified backup: $BACKUP_DIR"
fi

# STEP 2: Verify backup contents
log INFO "Verifying backup contents..."

if [[ -n "$BACKUP_DIR" ]]; then
    # Check for database backup
    if [[ -f "$BACKUP_DIR/database.sql.gz" ]]; then
        DB_BACKUP_FILE="$BACKUP_DIR/database.sql.gz"
        log SUCCESS "Database backup found: $DB_BACKUP_FILE"
    else
        log WARN "No database backup found in $BACKUP_DIR"
    fi

    # Check for compose file backup
    if [[ -f "$BACKUP_DIR/docker-compose.yml.backup" ]]; then
        COMPOSE_BACKUP="$BACKUP_DIR/docker-compose.yml.backup"
        log SUCCESS "Compose file backup found"
    else
        log WARN "No compose file backup found"
    fi

    # Check for environment file backup
    if [[ -f "$BACKUP_DIR/.env.backup" ]]; then
        ENV_BACKUP="$BACKUP_DIR/.env.backup"
        log SUCCESS "Environment file backup found"
    else
        log WARN "No environment file backup found"
    fi
fi

# STEP 3: Safety confirmation
log WARN "========================================"
log WARN "WARNING: This will rollback the system"
log WARN "========================================"
log WARN "This operation will:"
log WARN "  1. Stop all running containers"
log WARN "  2. Restore database from backup"
log WARN "  3. Restore configuration files"
log WARN "  4. Restart containers with previous version"
log WARN ""

if [[ -n "$DB_BACKUP_FILE" ]]; then
    log INFO "Database will be restored from: $DB_BACKUP_FILE"
    log INFO "Backup size: $(du -h "$DB_BACKUP_FILE" | cut -f1)"
fi

log WARN "========================================"

read -p "Are you sure you want to proceed? (yes/NO): " -r
echo

if [[ ! "$REPLY" =~ ^[Yy][Ee][Ss]$ ]]; then
    log INFO "Rollback cancelled by user"
    exit 0
fi

# STEP 4: Stop current containers
log INFO "[1/5] Stopping current containers..."

# Get list of currently running containers for logging
RUNNING_CONTAINERS=$(docker-compose ps --services --filter "status=running" 2>/dev/null || echo "none")
log INFO "Currently running: $(echo $RUNNING_CONTAINERS | tr '\n' ', ' | sed 's/,$//')"

if docker-compose down 2>&1 | tee -a "$LOG_FILE"; then
    log SUCCESS "Containers stopped"
else
    log WARN "Some containers may not have stopped cleanly"
fi

sleep 3

# STEP 5: Restore configuration files
log INFO "[2/5] Restoring configuration files..."

if [[ -n "${COMPOSE_BACKUP:-}" ]] && [[ -f "$COMPOSE_BACKUP" ]]; then
    cp "$COMPOSE_BACKUP" "$COMPOSE_FILE"
    log SUCCESS "Compose file restored"
else
    log WARN "No compose file to restore, using current version"
fi

if [[ -n "${ENV_BACKUP:-}" ]] && [[ -f "$ENV_BACKUP" ]]; then
    cp "$ENV_BACKUP" ".env"
    log SUCCESS "Environment file restored"
else
    log WARN "No environment file to restore, using current version"
fi

# STEP 6: Restore database
if [[ -n "${DB_BACKUP_FILE:-}" ]] && [[ -f "$DB_BACKUP_FILE" ]]; then
    log INFO "[3/5] Restoring database from backup..."

    # Start only PostgreSQL for database restore
    if docker-compose up -d postgres 2>&1 | tee -a "$LOG_FILE"; then
        log SUCCESS "PostgreSQL container started"

        # Wait for PostgreSQL to be ready
        log INFO "Waiting for PostgreSQL to be ready..."
        sleep 10

        # Use restore script if available
        if [[ -f "scripts/restore_db.sh" ]]; then
            log INFO "Using restore script..."
            # Geen `--bevestig` en geen "y" via stdin: restore_db.sh vraagt zelf, door een mens, om
            # de databasenaam en weigert zonder toetsenbord (meetlat eis 6, besluit 2026-10-14).
            # pipefail: een mislukt herstel telt anders als gelukt door de afloopstatus van tee.
            if (set -o pipefail; bash scripts/restore_db.sh "$DB_BACKUP_FILE" 2>&1 | tee -a "$LOG_FILE"); then
                log SUCCESS "Database restored successfully"
            else
                error_exit "Database NIET hersteld (restore_db.sh vraagt om een mens en weigert zonder toetsenbord); herstel met de hand: bash scripts/restore_db.sh $DB_BACKUP_FILE"
            fi
        else
            # Geen terugvalpad met `gunzip | psql`: dat overschrijft de database zonder voor-back-up
            # en zonder dat een mens de naam typt (meetlat eis 6).
            error_exit "scripts/restore_db.sh ontbreekt; database NIET hersteld"
        fi
    else
        error_exit "Failed to start PostgreSQL container"
    fi
else
    log WARN "[3/5] No database backup to restore, skipping"
fi

# STEP 7: Start all services
log INFO "[4/5] Starting all services..."

if docker-compose up -d 2>&1 | tee -a "$LOG_FILE"; then
    log SUCCESS "Services started"
else
    error_exit "Failed to start services"
fi

# Wait for services to initialize
sleep 10

# STEP 8: Health checks
log INFO "[5/5] Running health checks..."

if wait_for_health "$HEALTH_URL" "$MAX_HEALTH_RETRIES" "$HEALTH_RETRY_DELAY"; then
    log SUCCESS "Health check passed"
else
    log ERROR "Health check failed - manual intervention required"
    log ERROR "Check container logs with: docker-compose logs"
    exit 1
fi

# Verify critical services
log INFO "Verifying critical services..."

CRITICAL_SERVICES=("backend" "postgres" "redis" "web")
ALL_HEALTHY=true

for service in "${CRITICAL_SERVICES[@]}"; do
    if docker-compose ps | grep -q "$service.*Up"; then
        log SUCCESS "Service $service: RUNNING"
    else
        if docker-compose ps --services | grep -q "^${service}$"; then
            log WARN "Service $service: NOT RUNNING"
            ALL_HEALTHY=false
        fi
    fi
done

# Database connectivity test
if curl -f -s "http://localhost:8000/ready" > /dev/null 2>&1; then
    log SUCCESS "Database connectivity: OK"
else
    log WARN "Database connectivity: FAILED"
fi

# STEP 9: Generate rollback report
log INFO "Generating rollback report..."

REPORT_FILE="${LOG_DIR}/rollback_report_$(date +%Y%m%d_%H%M%S).txt"

cat > "$REPORT_FILE" << EOF
================================================================================
ROLLBACK REPORT - SanskritiSetu
================================================================================
Timestamp: $(date)
User: $(whoami)
Host: $(hostname)

Rollback Details:
  Backup Source: ${BACKUP_DIR:-${DB_BACKUP_FILE}}
  Database Restored: $([ -n "${DB_BACKUP_FILE:-}" ] && echo "Yes" || echo "No")
  Config Restored: $([ -n "${COMPOSE_BACKUP:-}" ] && echo "Yes" || echo "No")
  Status: $([ "$ALL_HEALTHY" = true ] && echo "SUCCESS" || echo "PARTIAL")

Services Status:
$(docker-compose ps 2>&1)

Health Checks:
  API Health: $(curl -s -o /dev/null -w "%{http_code}" "$HEALTH_URL" 2>/dev/null || echo "FAILED")
  Database: $(curl -s -o /dev/null -w "%{http_code}" "http://localhost:8000/ready" 2>/dev/null || echo "FAILED")

Timeline:
  1. Containers stopped: $(date -d '2 minutes ago' '+%Y-%m-%d %H:%M:%S' 2>/dev/null || date '+%Y-%m-%d %H:%M:%S')
  2. Database restored: $(date -d '1 minute ago' '+%Y-%m-%d %H:%M:%S' 2>/dev/null || date '+%Y-%m-%d %H:%M:%S')
  3. Services started: $(date '+%Y-%m-%d %H:%M:%S')

Next Steps:
  1. Monitor application logs: docker-compose logs -f
  2. Check Grafana dashboards: http://localhost:3000
  3. Verify user functionality
  4. Investigate root cause of deployment issue
  5. Create incident report

Log Files:
  - Rollback log: $LOG_FILE
  - This report: $REPORT_FILE

================================================================================
EOF

log SUCCESS "Rollback report saved: $REPORT_FILE"

# ==================== ROLLBACK SUMMARY ====================

log INFO "========================================"
log SUCCESS "✓ ROLLBACK COMPLETED"
log INFO "========================================"
log INFO "Backup source: ${BACKUP_DIR:-${DB_BACKUP_FILE}}"
log INFO "Report file: $REPORT_FILE"
log INFO "Log file: $LOG_FILE"
log INFO ""
log INFO "Service URLs:"
log INFO "  - Application: http://localhost:8000"
log INFO "  - Health check: $HEALTH_URL"
log INFO "  - Grafana: http://localhost:3000"
log INFO ""
log INFO "To check logs:"
log INFO "  docker-compose logs -f [service_name]"
log INFO "========================================"

exit 0
