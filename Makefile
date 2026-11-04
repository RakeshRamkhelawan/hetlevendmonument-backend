.PHONY: help up down logs test build clean ci ci-python ci-frontend ci-docker ci-security

help:
	@echo "SanskritiSetu v3.0 - Unified Maintenance Hub"
	@echo ""
	@echo "Infrastructure Commands:"
	@echo "  make up              - Start all services (detached)"
	@echo "  make down            - Stop all services"
	@echo "  make build           - Build/Rebuild all images"
	@echo "  make ps              - Show service status"
	@echo "  make clean           - Full reset (removes volumes)"
	@echo ""
	@echo "Database & Migrations:"
	@echo "  make migrate-gen MSG='msg' - Generate a new Alembic revision"
	@echo "  make migrate-up      - Apply all pending migrations"
	@echo "  make migrate-down    - Rollback last migration"
	@echo "  make db-shell        - Open PostgreSQL shell inside container"
	@echo ""
	@echo "Quality & Testing:"
	@echo "  make test            - Run unit tests in container"
	@echo "  make test-int        - Run integration tests (critical batch, ~2-3 min)
  @echo "  make test-int-p1     - Run P1 integration tests (~15-20 min)"
  @echo "  make test-int-p2     - Run P2 integration tests (~30-45 min)"
  @echo "  make test-int-all    - Run ALL integration tests (~60-90 min)"
  @echo "  make test-int-quick  - Run quick smoke tests (~30 sec)""
	@echo "  make test-db-up      - Start PostgreSQL test database (port 5455)"
	@echo "  make test-db-down    - Stop PostgreSQL test database"
	@echo "  make test-db-status  - Check test database status"
	@echo "  make lint            - Run linter (ruff) in container"
	@echo "  make format          - Auto-format all Python files (black + isort)"
	@echo "  make format-check    - Check formatting without modifying files"
	@echo ""
	@echo "Observability:"
	@echo "  make logs            - Follow all logs"
	@echo "  make health          - Check health of all endpoints"
	@echo "  make dashboard       - Show URLs for all dashboards"

up:
	docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d

up-obs:
	docker-compose up -d
	docker-compose -f docker-compose.observability.yml up -d

down:
	docker-compose down
	docker-compose -f docker-compose.observability.yml down 2>/dev/null || true

logs:
	docker-compose logs -f

logs-backend:
	docker-compose logs -f backend

logs-workflow:
	docker-compose logs -f workflow-engine

logs-ai:
	docker-compose logs -f ai-service

test:
	docker-compose exec backend pytest tests/unit --cov=src -v

test-int:
	@echo "Running integration tests (critical batch, ~2-3 min)..."
	@powershell -ExecutionPolicy Bypass -File scripts/run_integration_tests.ps1 -Batch critical

test-int-p1:
	@echo "Running P1 integration tests (~15-20 min)..."
	@powershell -ExecutionPolicy Bypass -File scripts/run_integration_tests.ps1 -Batch p1

test-int-p2:
	@echo "Running P2 integration tests (~30-45 min)..."
	@powershell -ExecutionPolicy Bypass -File scripts/run_integration_tests.ps1 -Batch p2

test-int-all:
	@echo "Running ALL integration tests (~60-90 min)..."
	@powershell -ExecutionPolicy Bypass -File scripts/run_integration_tests.ps1 -Batch all

test-int-quick:
	@echo "Running quick smoke tests (~30 sec)..."
	@powershell -ExecutionPolicy Bypass -File scripts/run_integration_tests.ps1 -Batch quick

test-db-up:
	@echo "Starting PostgreSQL test database on port 5455..."
	@docker-compose -f docker-compose.integration-test.yml up -d postgres-integration redis-integration
	@echo "Waiting for PostgreSQL to be healthy..."
	@powershell -Command "$$max=30; $$i=0; while ($$i -lt $$max) { $$i++; Start-Sleep -Seconds 2; $$health=docker inspect --format='{{.State.Health.Status}}' sanskritisetu_postgres_integration 2>$$null; if ($$health -eq 'healthy') { Write-Host '✅ Test database ready!'; exit 0 } Write-Host -NoNewline '.' }; Write-Host '`n❌ Timeout waiting for database'"
	@echo "Connection: postgresql+asyncpg://postgres:postgres@localhost:5455/sanskritisetu_test"

test-db-down:
	@echo "Stopping PostgreSQL test database..."
	@docker-compose -f docker-compose.integration-test.yml down
	@echo "✅ Test database stopped"

test-db-status:
	@docker-compose -f docker-compose.integration-test.yml ps

test-db-logs:
	@docker-compose -f docker-compose.integration-test.yml logs -f postgres-integration
migrate-gen:
	docker-compose exec backend alembic revision --autogenerate -m "$(MSG)"

migrate-up:
	docker-compose exec backend alembic upgrade head

migrate-down:
	docker-compose exec backend alembic downgrade -1

check-migrations:  ## Controleer ORM drift (vereist DATABASE_URL env var)
	alembic -c src/alembic.ini check
	@echo "Alembic drift: none"

db-shell:
	docker-compose exec postgres psql -U postgres -d sanskritisetu

lint:
	docker-compose exec backend ruff check .

format:
	@echo "🔧 Formatting Python files..."
	@docker-compose exec backend black src/ tests/ scripts/ --line-length=100
	@docker-compose exec backend isort src/ tests/ scripts/ --profile=black --line-length=100
	@echo "✅ Formatting complete"

format-check:
	@echo "🔍 Checking formatting..."
	@docker-compose exec backend black src/ tests/ scripts/ --line-length=100 --check
	@docker-compose exec backend isort src/ tests/ scripts/ --profile=black --line-length=100 --check
	@docker-compose exec backend ruff check src/ tests/ scripts/
	@echo "✅ All formatting checks passed"

build:
	docker-compose build

rebuild:
	docker-compose build --no-cache

clean:
	docker-compose down -v
	docker system prune -f

ps:
	docker-compose ps

health:
	@echo "Checking service health..."
	@curl -s http://localhost/api/health || echo "Backend: DOWN"
	@curl -s http://localhost:3000/health || echo "Workflow: DOWN"
	@curl -s http://localhost:8001/health || echo "AI Service: DOWN"
	@curl -s http://localhost:8002/health || echo "Notifications: DOWN"

dashboard:
	@echo "Service Dashboards:"
	@echo "  Traefik:    http://localhost:8080"
	@echo "  RabbitMQ:   http://localhost:15672 (admin/admin)"
	@echo "  Prometheus: http://localhost:9091"  # Port 9091 avoids conflict with agentic_trader on 9090
	@echo "  Grafana:    http://localhost:3000 (admin/admin)"
	@echo "  Jaeger:     http://localhost:16686"

# ============================================================================
# PRODUCTION DEPLOYMENT TARGETS
# ============================================================================

.PHONY: prod-validate prod-migrate prod-deploy prod-health prod-backup prod-logs

# 1. Validation
prod-validate:
	@echo "🔍 Validating production configuration..."
	@python scripts/validate_production_secrets.py
	@docker-compose -f docker-compose.base.yml -f docker-compose.prod.yml config > /dev/null
	@echo "✅ Validation OK"

# 2. Backup
prod-backup:
	@echo "💾 Creating Pre-Deployment Backup..."
	@bash scripts/backup_db.sh

# 3. Migration
prod-migrate:
	@echo "🗄️  Applying Database Migrations..."
	@docker-compose -f docker-compose.base.yml -f docker-compose.prod.yml run --rm backend alembic -c src/alembic.ini upgrade head
	@echo "✅ Migrations Applied"

# 4. Deployment Check
prod-health:
	@echo "🏥 Checking Health..."
	@curl -s -f http://localhost:8100/health > /dev/null && echo "✅ Backend UP" || echo "❌ Backend DOWN"  # Port 8100 avoids conflict with agentic_trader on 8000
	@curl -s -f http://localhost:3000 > /dev/null && echo "✅ Frontend UP" || echo "❌ Frontend DOWN"

# 5. Master Deployment Command
prod-deploy: prod-validate prod-backup
	@echo "🚀 Starting Production Deployment..."
	@echo "[1/4] Building Images..."
	@docker-compose -f docker-compose.base.yml -f docker-compose.prod.yml build --no-cache
	@echo "[2/4] Running Migrations..."
	@$(MAKE) prod-migrate
	@echo "[3/4] Restarting Services..."
	@docker-compose -f docker-compose.base.yml -f docker-compose.prod.yml up -d
	@echo "[4/4] Verifying Deployment..."
	@timeout /t 15 > nul
	@$(MAKE) prod-health
	@echo "✅ Deployment Complete"

# Support
prod-logs:
	@docker-compose -f docker-compose.base.yml -f docker-compose.prod.yml logs -f --tail=100

prod-logs-backend:
	@docker-compose -f docker-compose.base.yml -f docker-compose.prod.yml logs -f --tail=100 backend

prod-stop:
	@docker-compose -f docker-compose.base.yml -f docker-compose.prod.yml down

prod-help:
	@echo "Production Deployment Commands:"
	@echo "  make prod-validate  - Validate configuration"
	@echo "  make prod-deploy    - Full deployment with backup"
	@echo "  make prod-health    - Check service health"
	@echo "  make prod-logs      - View logs"


# =============================================================================
# NEW: Optimized Test Commands (Batch Runner)
# =============================================================================

test-fast:
	@echo "Running fast unit tests (parallel, -n 8)..."
	@python -m pytest tests/unit -n 8 --timeout=60 -q --tb=short
	# NOTE: -n 8 is bewust gekozen (niet -n auto). Op Windows met 20 cores crashen
	# 20 parallelle workers de pipe met OSError EINVAL op ~83%. -n 8 = stabiel,
	# ~15-20 min voor 12.938 tests. MagicMock-fix zit in tests/conftest.py _custom_save.

test-security:
	@echo "Running security tests..."
	@python -m pytest tests/security -v --tb=short --timeout=120

test-batch:
	@if [ -z "$(N)" ]; then \
		echo "Usage: make test-batch N=1"; \
		echo "Available batches: 1-20"; \
		exit 1; \
	fi
	@echo "Running batch $(N)..."
	@python scripts/run_test_batches.py $(N)

test-all:
	@echo "Running all test batches..."
	@python scripts/run_test_batches.py --all

test-parallel:
	@echo "Running tests with parallel optimization..."
	@python scripts/run_tests_parallel.py --fast

test-ci:
	@echo "Running CI test suite..."
	@python scripts/run_tests_parallel.py --ci

test-coverage:
	@echo "Running tests with coverage..."
	@python -m pytest tests/unit tests/integration -m "not slow" \
		--cov=src --cov-report=xml --cov-report=html \
		--cov-fail-under=95 --timeout=120

# Test batch shortcuts
test-batches-1-5: test-batch-1 test-batch-2 test-batch-3 test-batch-4 test-batch-5
test-batches-6-10: test-batch-6 test-batch-7 test-batch-8 test-batch-9 test-batch-10
test-batches-11-15: test-batch-11 test-batch-12 test-batch-13 test-batch-14 test-batch-15
test-batches-16-20: test-batch-16 test-batch-17 test-batch-18 test-batch-19 test-batch-20

test-batch-%:
	@python scripts/run_test_batches.py $*

.PHONY: test-fast test-security test-batch test-all test-parallel test-ci test-coverage

# =============================================================================
# Local CI runner (mirrors GitHub Actions CI exactly)
# =============================================================================

ci:
	bash scripts/ci-local.sh

ci-python:
	bash scripts/ci-local.sh python

ci-frontend:
	bash scripts/ci-local.sh frontend

ci-docker:
	bash scripts/ci-local.sh docker

ci-security:
	bash scripts/ci-local.sh security
