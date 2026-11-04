# PowerShell script voor E2E testing met lokale backend/frontend
# Vereisten: Docker Desktop moet draaien

param(
    [switch]$SkipMigrations,
    [switch]$Stop
)

$ErrorActionPreference = "Stop"

# Kleuren voor output
$Green = "`e[32m"
$Yellow = "`e[33m"
$Red = "`e[31m"
$Reset = "`e[0m"

function Write-Status($message) {
    Write-Host "$Green[STATUS]$Reset $message"
}

function Write-Warning($message) {
    Write-Host "$Yellow[WARNING]$Reset $message"
}

function Write-Error($message) {
    Write-Host "$Red[ERROR]$Reset $message"
}

if ($Stop) {
    Write-Status "Stopping E2E environment..."
    docker-compose -f docker-compose.e2e.fixed.yml down -v
    Get-Process -Name python -ErrorAction SilentlyContinue | Stop-Process -Force
    Get-Process -Name node -ErrorAction SilentlyContinue | Stop-Process -Force
    Write-Status "Environment stopped"
    exit 0
}

Write-Status "Starting SanskritiSetu E2E Environment..."
Write-Host ""

# Check of Docker draait
try {
    $dockerInfo = docker info 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Docker is not running. Please start Docker Desktop first."
        exit 1
    }
} catch {
    Write-Error "Docker is not running. Please start Docker Desktop first."
    exit 1
}

Write-Status "Docker is running"

# Start PostgreSQL, Redis, Mailhog
Write-Status "Starting Docker services (PostgreSQL, Redis, Mailhog)..."
docker-compose -f docker-compose.e2e.fixed.yml up -d
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to start Docker services"
    exit 1
}

# Wacht tot PostgreSQL ready is
Write-Status "Waiting for PostgreSQL..."
$maxRetries = 30
$retry = 0
while ($retry -lt $maxRetries) {
    $result = docker exec sanskritisetu-e2e-postgres pg_isready -U postgres 2>&1
    if ($result -match "accepting connections") {
        Write-Status "PostgreSQL is ready"
        break
    }
    Start-Sleep -Seconds 1
    $retry++
}

if ($retry -eq $maxRetries) {
    Write-Error "PostgreSQL did not become ready in time"
    exit 1
}

# Environment variables
$env:DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5434/sanskritisetu_e2e"
$env:REDIS_URL = "redis://localhost:6381/0"
$env:SECRET_KEY = "e2e-test-secret-key-do-not-use-in-production-32chars-long"
$env:JWT_SECRET_KEY = "e2e-test-jwt-secret-key-do-not-use-in-production-32chars"
$env:ENVIRONMENT = "test"
$env:TESTING = "1"
$env:LOG_LEVEL = "INFO"
$env:GOOGLE_API_KEY = "test-api-key-for-e2e-only"
$env:SMTP_HOST = "localhost"
$env:SMTP_PORT = "1026"
$env:SMTP_USER = ""
$env:SMTP_PASSWORD = ""

Write-Host ""
Write-Status "Configuration:"
Write-Host "  Database: $env:DATABASE_URL"
Write-Host "  Redis: $env:REDIS_URL"
Write-Host "  SMTP: $env:SMTP_HOST:$env:SMTP_PORT"
Write-Host ""

# Run migrations
if (-not $SkipMigrations) {
    Write-Status "Running database migrations..."
    python -m alembic -c src/alembic.ini upgrade head
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Migrations completed with warnings"
    } else {
        Write-Status "Migrations complete"
    }
}

Write-Host ""
Write-Status "E2E Environment is ready!"
Write-Host ""
Write-Host "Services:"
Write-Host "  PostgreSQL: localhost:5434"
Write-Host "  Redis: localhost:6381"
Write-Host "  Mailhog UI: http://localhost:8026"
Write-Host ""
Write-Host "To start the backend:"
Write-Host "  uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload"
Write-Host ""
Write-Host "To start the frontend:"
Write-Host "  cd frontend"
Write-Host "  `"`$env:VITE_API_URL=`"http://localhost:8001`"`"; npm run dev -- --port 5174"
Write-Host ""
Write-Host "To run E2E tests:"
Write-Host "  cd frontend"
Write-Host "  npx playwright test tests/e2e/company/ --project=chromium"
Write-Host ""
Write-Status "Press Ctrl+C to stop this script (services will keep running)"
Write-Status "Run with -Stop flag to stop all services"

# Keep script running
while ($true) {
    Start-Sleep -Seconds 1
}
