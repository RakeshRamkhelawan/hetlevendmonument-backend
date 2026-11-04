#!/bin/bash
#
# Developer Setup Script - Generates local development secrets
# Run this script once after cloning the repository
# Creates .env.local with unique secrets for local development
#
# Usage: ./scripts/setup-dev-secrets.sh
# Or:    bash scripts/setup-dev-secrets.sh (Windows PowerShell)
#

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Ensure script runs from project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   Sanskriti Setu - Developer Secrets Setup                 ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"

# Check if .env.local already exists
if [ -f ".env.local" ]; then
    echo -e "${YELLOW}ℹ️  .env.local already exists${NC}"
    read -p "Do you want to regenerate secrets? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${GREEN}✓ Using existing .env.local${NC}"
        exit 0
    fi
    echo -e "${YELLOW}⚠️  Backing up existing .env.local to .env.local.backup${NC}"
    mv ".env.local" ".env.local.backup"
fi

# Function to generate random secret
generate_secret() {
    local length=${1:-32}
    if command -v openssl &> /dev/null; then
        openssl rand -base64 "$length" | tr -d '\n'
    else
        # Fallback for Windows/systems without openssl
        head -c "$length" /dev/urandom | base64 | tr -d '\n'
    fi
}

echo -e "${BLUE}Generating secure secrets...${NC}"

# Generate secrets
JWT_SECRET=$(generate_secret 32)
if [ -z "$JWT_SECRET" ]; then
    echo -e "${RED}✗ Failed to generate JWT secret${NC}"
    exit 1
fi

POSTGRES_PASSWORD=$(generate_secret 24)
REDIS_PASSWORD=$(generate_secret 24)

echo -e "${GREEN}✓ Secrets generated${NC}"

# Get hostname for database
if [ "$OSTYPE" = "msys" ] || [ "$OSTYPE" = "win32" ]; then
    DB_HOST="postgres"
else
    DB_HOST="localhost"
fi

# Create .env.local
cat > ".env.local" << EOF
# ============================================
# Development Secrets - GENERATED
# Generated: $(date)
# DO NOT COMMIT THIS FILE
# ============================================

# Environment
ENVIRONMENT=development
DEBUG=true
LOG_LEVEL=DEBUG

# Authentication & Security
JWT_SECRET_KEY=$JWT_SECRET
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=30

# Database
DATABASE_URL=postgresql+asyncpg://postgres:${POSTGRES_PASSWORD}@${DB_HOST}:5432/sanskriti_setu
POSTGRES_PASSWORD=$POSTGRES_PASSWORD

# Redis Cache
REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/0
REDIS_PASSWORD=$REDIS_PASSWORD

# Dramatiq Message Broker (ADR-006: Dramatiq + Redis)
DRAMATIQ_BROKER_URL=redis://:${REDIS_PASSWORD}@redis:6379/1

# API & Ports
API_HOST=0.0.0.0
API_PORT=8000
CORS_ORIGINS=http://localhost:5173,http://localhost:3003,http://localhost:3000

# Optional: LLM Providers
# GOOGLE_API_KEY=your-key-here
# OPENAI_API_KEY=your-key-here
# ANTHROPIC_API_KEY=your-key-here

# Optional: Stripe (if using payments)
# STRIPE_API_KEY=your-key-here
# STRIPE_PUBLISHABLE_KEY=your-key-here

# Development
TEST_DATABASE_URL=sqlite:///./test.db
TESTING=0

EOF

# Set restrictive permissions
chmod 600 ".env.local"

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}✓ Setup Complete!${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"

echo
echo -e "${BLUE}Created ${YELLOW}.env.local${BLUE} with the following secrets:${NC}"
echo "  • JWT_SECRET_KEY: $(echo $JWT_SECRET | head -c 16)..."
echo "  • POSTGRES_PASSWORD: $(echo $POSTGRES_PASSWORD | head -c 16)..."
echo "  • REDIS_PASSWORD: $(echo $REDIS_PASSWORD | head -c 16)..."

echo
echo -e "${YELLOW}Next steps:${NC}"
echo "  1. Start services: ${BLUE}docker-compose -f docker-compose.dev.yml up${NC}"
echo "  2. Run migrations: ${BLUE}alembic -c src/alembic.ini upgrade head${NC}"
echo "  3. Start backend:  ${BLUE}uvicorn src.main:app --reload${NC}"
echo "  4. Start frontend: ${BLUE}cd frontend && npm run dev${NC}"

echo
echo -e "${YELLOW}Security Reminders:${NC}"
echo "  • ${RED}NEVER${NC} commit .env.local to git"
echo "  • ${RED}NEVER${NC} share .env.local files with team members"
echo "  • Each developer generates their own secrets"
echo "  • For staging/production, use GitHub Actions secrets"

echo
echo -e "${GREEN}✓ Happy coding! 🚀${NC}"
