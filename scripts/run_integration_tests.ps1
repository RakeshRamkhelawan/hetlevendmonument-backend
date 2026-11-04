#Requires -Version 5.1
<#
.SYNOPSIS
    Run integration tests in batches with proper database isolation.

.DESCRIPTION
    This script runs integration tests efficiently by:
    1. Grouping tests into priority-based batches
    2. Running without pytest-xdist (prevents database contention)
    3. Using proper timeouts for database operations
    4. Providing clear progress feedback

.PARAMETER Batch
    Which batch to run: "critical", "p1", "p2", "all"

.PARAMETER Timeout
    Timeout per test in seconds (default: 300 = 5 minutes)

.PARAMETER NoParallel
    Disable parallel execution within a single test file

.EXAMPLE
    # Run critical tests only (fast, ~2-3 min)
    .\scripts\run_integration_tests.ps1 -Batch critical

    # Run all integration tests (~40-60 min)
    .\scripts\run_integration_tests.ps1 -Batch all

    # Run with custom timeout
    .\scripts\run_integration_tests.ps1 -Batch p1 -Timeout 600
#>
[CmdletBinding()]
param(
    [Parameter()]
    [ValidateSet("critical", "p1", "p2", "all", "quick")]
    [string]$Batch = "critical",

    [Parameter()]
    [int]$Timeout = 300,

    [Parameter()]
    [switch]$NoParallel,

    [Parameter()]
    [switch]$FailFast
)

$ErrorActionPreference = "Stop"
$StartTime = Get-Date

# Colors for output
# Colors for output (PowerShell 5.1 compatible)
$Green = "[SUCCESS]"
$Yellow = "[WARNING]"
$Red = "[ERROR]"
$Blue = "[INFO]"

function Write-Status($Message, $Color = $Blue) {
    Write-Host "${Color}[$(Get-Date -Format 'HH:mm:ss')] $Message"
}

function Write-Success($Message) {
    Write-Status $Message $Green
}

function Write-Warning($Message) {
    Write-Status $Message $Yellow
}

function Write-Error($Message) {
    Write-Status $Message $Red
}

# Verify test database is running
Write-Status "Checking test database..."
try {
    $pgContainer = docker ps --format "{{.Names}}" | Select-String "postgres-test"
    if (-not $pgContainer) {
        Write-Warning "Test database not running. Starting..."
        docker-compose -f docker-compose.test-db.yml up -d
        Start-Sleep -Seconds 5
    }
    Write-Success "Test database is ready"
} catch {
    Write-Error "Failed to check/start test database: $_"
    exit 1
}

# Test file categorization based on INTEGRATION_TEST_BATCH_PLAN.md
$CriticalTests = @(
    "tests/integration/test_auth_integration.py",
    "tests/integration/test_auth_endpoints.py",
    "tests/integration/test_admin_integration.py",
    "tests/integration/test_admin_rbac.py",
    "tests/integration/test_company_layer_integration.py",
    "tests/integration/test_company_layer_api_integration.py",
    "tests/integration/test_tenant_middleware.py"
)

$P1Tests = @(
    "tests/integration/test_activepieces_integration.py",
    "tests/integration/test_agent_integration.py",
    "tests/integration/test_canvas_integration.py",
    "tests/integration/test_workflow_integration.py",
    "tests/integration/test_workflow_service_integration.py",
    "tests/integration/test_cva_integration.py",
    "tests/integration/test_cva_routing.py",
    "tests/integration/test_goal_integration.py",
    "tests/integration/test_digital_twin_integration.py"
)

$QuickTests = @(
    "tests/integration/test_auth_integration.py",
    "tests/integration/test_health_endpoints.py",
    "tests/integration/test_integration_smoke.py",
    "tests/integration/test_middleware_order_fix.py"
)

# Get all test files
$AllTestFiles = Get-ChildItem -Path "tests/integration" -Filter "test_*.py" |
    Select-Object -ExpandProperty FullName |
    ForEach-Object { $_.Replace("$PWD\", "").Replace("\", "/") } |
    Sort-Object

# Determine which tests to run
$TestsToRun = switch ($Batch) {
    "critical" { $CriticalTests | Where-Object { Test-Path $_ } }
    "p1" { $P1Tests | Where-Object { Test-Path $_ } }
    "quick" { $QuickTests | Where-Object { Test-Path $_ } }
    "p2" {
        $excluded = $CriticalTests + $P1Tests | ForEach-Object { Split-Path $_ -Leaf }
        $AllTestFiles | Where-Object { (Split-Path $_ -Leaf) -notin $excluded }
    }
    "all" { $AllTestFiles }
    default { $CriticalTests }
}

$TestCount = ($TestsToRun | Measure-Object).Count
Write-Status "Running $TestCount test files in batch: $Batch"

if ($TestCount -eq 0) {
    Write-Error "No tests found for batch: $Batch"
    exit 1
}

# Build pytest arguments
$PytestArgs = @(
    "-v",
    "--tb=short",
    "--timeout=$Timeout",
    "--timeout-method=thread",
    "--ignore=tests/root_scripts",
    "--ignore=tests/manual"
)

if ($FailFast) {
    $PytestArgs += "-x"
}

if ($NoParallel) {
    $PytestArgs += "--no-header"
}

# Run tests
$SuccessCount = 0
$FailCount = 0
$SkippedCount = 0

for ($i = 0; $i -lt $TestsToRun.Count; $i++) {
    $testFile = $TestsToRun[$i]
    $progress = "[$($i + 1)/$TestCount]"

    Write-Status "`n${progress} Running: $testFile"

    $testArgs = $PytestArgs + $testFile
    $proc = $null

    try {
        $proc = Start-Process -FilePath "python" -ArgumentList (@("-m", "pytest") + $testArgs) `
            -PassThru -NoNewWindow -Wait

        if ($proc.ExitCode -eq 0) {
            Write-Success "  PASSED"
            $SuccessCount++
        } elseif ($proc.ExitCode -eq 5) {
            Write-Warning "  NO TESTS COLLECTED"
            $SkippedCount++
        } else {
            Write-Error "  FAILED (Exit: $($proc.ExitCode))"
            $FailCount++
            if ($FailFast) {
                Write-Error "FailFast enabled, stopping..."
                break
            }
        }
    } catch {
        Write-Error "  ERROR: $_"
        $FailCount++
    }
}

# Summary
$EndTime = Get-Date
$Duration = $EndTime - $StartTime

Write-Host "`n========================================"
Write-Status "Test Run Complete"
Write-Host "========================================"
Write-Success "Passed:  $SuccessCount"
if ($FailCount -gt 0) {
    Write-Error "Failed:  $FailCount"
} else {
    Write-Host "Failed:  $FailCount"
}
Write-Warning "Skipped: $SkippedCount"
Write-Status "Duration: $($Duration.ToString('mm\:ss'))"
Write-Host "========================================"

exit $FailCount
