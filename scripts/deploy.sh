#!/bin/bash
# Production Deployment Script for SanskritiSetu
# Usage: ./scripts/deploy.sh [environment]
# Example: ./scripts/deploy.sh production

set -e  # Exit on error

ENVIRONMENT=${1:-production}
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  SanskritiSetu Deployment - $ENVIRONMENT${NC}"
echo -e "${GREEN}========================================${NC}"

# 1. Pre-flight checks
echo -e "\n${YELLOW}[1/7] Pre-flight checks...${NC}"

# Check Docker
if ! command -v docker &> /dev/null;
then
    echo -e "${RED}ERROR: Docker not installed${NC}"
    exit 1
fi

# Check Docker Compose
if ! command -v docker-compose &> /dev/null;
then
    echo -e "${RED}ERROR: Docker Compose not installed${NC}"
    exit 1
fi

# Check system resources
TOTAL_MEM=$(free -m | awk 'NR==2{print $2}')
if [ "$TOTAL_MEM" -lt 2048 ]; then
    echo -e "${RED}WARNING: Less than 2GB RAM available${NC}"
fi

echo -e "${GREEN}✓ Pre-flight checks passed${NC}"

# 2. Backup current state
echo -e "\n${YELLOW}[2/7] Creating backup...${NC}"
BACKUP_DIR="backups/deploy_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

# Backup database (only if container is running)
if docker ps | grep -q postgres;
then
    docker exec postgres pg_dump -U postgres sanskritisetu | gzip > "$BACKUP_DIR/database.sql.gz"
    echo -e "${GREEN}✓ Database backed up${NC}"
else
    echo -e "${YELLOW}⚠ Postgres container not running, skipping DB backup${NC}"
fi

# 3. Pull latest code
echo -e "\n${YELLOW}[3/7] Pulling latest code...${NC}"
git pull origin main
echo -e "${GREEN}✓ Code updated${NC}"

# 4. Build new images
echo -e "\n${YELLOW}[4/7] Building Docker images...${NC}"
docker-compose -f docker-compose.base.yml -f docker-compose.prod.yml build --no-cache
echo -e "${GREEN}✓ Images built${NC}"

# 5. Database migrations
echo -e "\n${YELLOW}[5/7] Running database migrations...${NC}"
# Run migrations in a temporary container to avoid starting the whole stack if migration fails
if ! docker-compose -f docker-compose.base.yml -f docker-compose.prod.yml run --rm web alembic upgrade head; then
    echo -e "${RED}ERROR: Database migration failed! Aborting deployment.${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Migrations complete${NC}"

# 6. Deploy new version
echo -e "\n${YELLOW}[6/7] Deploying new version...${NC}"
docker-compose -f docker-compose.base.yml -f docker-compose.prod.yml up -d
echo -e "${GREEN}✓ Services started${NC}"

# 7. Health checks
echo -e "\n${YELLOW}[7/7] Running health checks...${NC}"

# Wait for service to be ready
echo -n "Waiting for service to be ready"
MAX_RETRIES=30
HEALTHY=false

for i in $(seq 1 $MAX_RETRIES);
do
    if curl -s -f http://localhost:8000/health > /dev/null 2>&1;
    then
        echo ""
        echo -e "${GREEN}✓ Service is healthy${NC}"
        HEALTHY=true
        break
    fi
    echo -n "."
    sleep 2
done

if [ "$HEALTHY" = false ]; then
    echo ""
    echo -e "${RED}ERROR: Health check failed after 60 seconds${NC}"
    echo -e "${YELLOW}Rolling back...${NC}"

    # Rollback DB if backup exists
    if [ -f "$BACKUP_DIR/database.sql.gz" ]; then
        echo "Restoring database..."
        gunzip -c "$BACKUP_DIR/database.sql.gz" |
            docker exec -i postgres psql -U postgres sanskritisetu
    fi

    # Stop new containers
    docker-compose -f docker-compose.base.yml -f docker-compose.prod.yml down

    echo -e "${RED}Deployment failed and rolled back${NC}"
    exit 1
fi

# Test readiness (DB connection)
if curl -s -f http://localhost:8000/ready > /dev/null 2>&1;
then
    echo -e "${GREEN}✓ Service is ready (DB connected)${NC}"
else
    echo -e "${YELLOW}WARNING: Service health check passed but readiness failed (DB issue?)${NC}"
fi

# 8. Final summary
echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN}  Deployment Successful!${NC}"
echo -e "${GREEN}========================================${NC}"
echo -e "Environment: $ENVIRONMENT"
echo -e "Backup: $BACKUP_DIR"
echo -e "Health: http://localhost:8000/health"
echo -e "Grafana: http://localhost:3000"
echo -e "Prometheus: http://localhost:9090"
echo -e "\n${YELLOW}To rollback manually:${NC}"
echo -e "  gunzip -c $BACKUP_DIR/database.sql.gz | docker exec -i postgres psql -U postgres sanskritisetu"
echo -e "  docker-compose -f docker-compose.base.yml -f docker-compose.prod.yml down"
