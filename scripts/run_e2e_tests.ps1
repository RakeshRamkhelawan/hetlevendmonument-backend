# PowerShell script om E2E tests te draaien
# Vereisten: E2E environment moet draaien (zie run_e2e_local.ps1)

param(
    [string]$TestPath = "tests/e2e/company/",
    [string]$Project = "chromium",
    [switch]$UI
)

$ErrorActionPreference = "Stop"

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

# Check of services draaien
Write-Status "Checking services..."

$postgres = docker ps --format "{{.Names}}" | Select-String "sanskritisetu-e2e-postgres"
if (-not $postgres) {
    Write-Error "PostgreSQL container is not running. Run './scripts/run_e2e_local.ps1' first."
    exit 1
}

# Check backend
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8001/health" -Method GET -TimeoutSec 5 -ErrorAction Stop
    Write-Status "Backend is running on http://localhost:8001"
} catch {
    Write-Error "Backend is not responding on http://localhost:8001"
    Write-Host "Start the backend with:"
    Write-Host "  uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload"
    exit 1
}

# Check frontend
try {
    $response = Invoke-WebRequest -Uri "http://localhost:5174" -Method GET -TimeoutSec 5 -ErrorAction Stop
    Write-Status "Frontend is running on http://localhost:5174"
} catch {
    Write-Error "Frontend is not responding on http://localhost:5174"
    Write-Host "Start the frontend with:"
    Write-Host "  cd frontend"
    Write-Host "  '`$env:VITE_API_URL=""http://localhost:8001""'; npm run dev -- --port 5174"
    exit 1
}

Write-Host ""
Write-Status "Running E2E tests..."
Write-Host "  Test path: $TestPath"
Write-Host "  Browser: $Project"
Write-Host ""

Set-Location frontend

if ($UI) {
    npx playwright test $TestPath --project=$Project --ui
} else {
    npx playwright test $TestPath --project=$Project --reporter=list
}

$exitCode = $LASTEXITCODE

Set-Location ..

if ($exitCode -eq 0) {
    Write-Host ""
    Write-Status "All tests passed!"
} else {
    Write-Host ""
    Write-Error "Some tests failed. Check the output above."
    Write-Host "View report: npx playwright show-report"
}

exit $exitCode
