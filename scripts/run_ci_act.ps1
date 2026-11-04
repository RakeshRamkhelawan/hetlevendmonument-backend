<#
.SYNOPSIS
    Draait .github/workflows/ci-feature.yml lokaal in Docker via `act`.

.DESCRIPTION
    Executes the exact .github/workflows/ci-feature.yml workflow locally using
    Docker containers, avoiding GitHub Actions runner minutes and external costs.

    Ondersteunt zowel losse jobs (-Job) als sequentiële runs van de betrouwbare
    Docker jobs ('bicep', 'security', 'docker-validate', 'portal').

.PARAMETER Job
    Specifieke job om te draaien uit ci-feature.yml.
    Ondersteunt: 'security', 'portal', 'python', 'integration', 'bicep', 'docker-validate', 'any-type-baseline'.

.PARAMETER Event
    GitHub workflow event type. Standaard 'workflow_dispatch'.

.PARAMETER List
    Lijst van alle beschikbare jobs in de workflow.

.PARAMETER DryRun
    Simuleert de uitvoering zonder containers te starten.

.EXAMPLE
    .\scripts\run_ci_act.ps1 -List
    .\scripts\run_ci_act.ps1 -Job portal
    .\scripts\run_ci_act.ps1 -Job bicep
    .\scripts\run_ci_act.ps1
#>
[CmdletBinding()]
param(
    [ValidateSet('security', 'portal', 'python', 'integration', 'bicep', 'docker-validate', 'any-type-baseline')]
    [string]$Job = "",
    [string]$Event = 'workflow_dispatch',
    [switch]$List,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$workflowPath = ".github/workflows/ci-feature.yml"

if (-not (Test-Path $workflowPath)) {
    throw "Niet gevonden: $workflowPath. Draai dit script vanuit de repo-root."
}

if (-not (Get-Command act -ErrorAction SilentlyContinue)) {
    throw "act is niet gevonden. Installeer met: winget install nektos.act"
}

# Ensure Docker is running
try {
    $dockerCheck = docker info --format '{{.ServerVersion}}' 2>$null
    if (-not $dockerCheck) {
        Write-Error "Docker Desktop is niet actief. Start Docker Desktop en probeer opnieuw."
        exit 1
    }
} catch {
    Write-Error "Docker Desktop is niet actief of niet bereikbaar."
    exit 1
}

# Ensure clean environment
Remove-Item Env:\GITHUB_TOKEN -ErrorAction SilentlyContinue

$artifactPath = Join-Path $env:TEMP "act-artifacts"
if (-not (Test-Path $artifactPath)) {
    New-Item -ItemType Directory -Path $artifactPath -Force | Out-Null
}

if ($List) {
    Write-Host "Beschikbare CI jobs in $workflowPath :" -ForegroundColor Cyan
    act $Event -W $workflowPath -l
    exit 0
}

$baseArgs = @($Event, "-W", $workflowPath, "--artifact-server-path", $artifactPath)
if ($DryRun) { $baseArgs += "-n" }

# Jobs die bij voorkeur native draaien
$buitenAct = @{
    'python' = 'De volledige python pytest suite duurt lang in een gevirtualiseerde container. Draai native voor maximale snelheid: python -m pytest tests/unit tests/architecture tests/core tests/contracts -n 4 --timeout=60 -q --tb=short'
    'integration' = 'een matrix van vijf shards met elk een eigen PostgreSQL-dienst; NIET onder act gemeten. Draai per shard native met een eigen wegwerpdatabase: pytest -c pyproject.toml $(python scripts/ci_integratie_shard.py <n>) -q --timeout=180 -p no:randomly'
}

if ($Job) {
    Write-Host "[act] Starten van lokale CI job '$Job' (event: $Event)..." -ForegroundColor Cyan
    $actArgs = $baseArgs + @("-j", $Job)
    & act @actArgs
    exit $LASTEXITCODE
}

# Standaard betrouwbare jobs die sequentieel draaien in act.
# 'portal' is lichtgewicht (npm ci + tsc + vitest + vite build op een
# kleine app; bewust geen lint-stap, eslint is daar een dode stub) en draait
# daarom mee in de standaard batch.
$defaultTargets = @('bicep', 'security', 'docker-validate', 'portal')
$failed = @()

Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host " Starten van lokale CI-pipeline via act in Docker" -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan

foreach ($t in $defaultTargets) {
    Write-Host ""
    Write-Host ">>> [act] Draaien van job: $t..." -ForegroundColor Yellow
    $actArgs = $baseArgs + @("-j", $t)
    & act @actArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Host ">>> [act] ROOD: $t (exitcode $LASTEXITCODE)" -ForegroundColor Red
        $failed += $t
    } else {
        Write-Host ">>> [act] GROEN: $t" -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "[act] Niet standaard meegenomen in container batch:" -ForegroundColor Gray
foreach ($k in $buitenAct.Keys) {
    Write-Host "  - ${k}: $($buitenAct[$k])" -ForegroundColor Gray
}
Write-Host "  - any-type-baseline: optioneel/monitoring job. Aanroepen met: .\scripts\run_ci_act.ps1 -Job any-type-baseline" -ForegroundColor Gray

if ($failed.Count -gt 0) {
    Write-Host ""
    Write-Error "[act] EINDRESULTAAT: NIET groen. Mislukte jobs: $($failed -join ', ')"
    exit 1
}

Write-Host ""
Write-Host "=================================================================" -ForegroundColor Green
Write-Host " [act] EINDRESULTAAT: alle gedraaide jobs 100% GROEN!" -ForegroundColor Green
Write-Host "=================================================================" -ForegroundColor Green
