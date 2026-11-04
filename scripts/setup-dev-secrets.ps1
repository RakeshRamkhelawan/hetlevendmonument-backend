#
# Developer Setup Script (PowerShell) - Generates local development secrets
# Run this script once after cloning the repository
# Creates .env.local with unique secrets for local development
#
# Usage: .\scripts\setup-dev-secrets.ps1
#

param(
    [switch]$Force = $false
)

# Set error action
$ErrorActionPreference = "Stop"

# Get project root
$ScriptPath = if ($PSCommandPath) { $PSCommandPath } else { $MyInvocation.MyCommand.Path }
$ScriptDir = Split-Path -Parent $ScriptPath
$ProjectRoot = Split-Path -Parent $ScriptDir
Set-Location $ProjectRoot

# Colors for output
function Write-Success { Write-Host $args -ForegroundColor Green }
function Write-Info { Write-Host $args -ForegroundColor Cyan }
function Write-Warning { Write-Host $args -ForegroundColor Yellow }
function Write-Error { Write-Host $args -ForegroundColor Red }

Write-Info "============================================================"
Write-Info "Sanskriti Setu - Developer Secrets Setup (PowerShell)"
Write-Info "============================================================"
Write-Host ""

# Check if .env.local already exists
if ((Test-Path ".env.local") -and -not $Force) {
    Write-Warning ".env.local already exists"
    $response = Read-Host "Do you want to regenerate secrets? (y/N)"
    if ($response -ne "y" -and $response -ne "Y") {
        Write-Success "[OK] Using existing .env.local"
        exit 0
    }
    Write-Warning "Backing up existing .env.local to .env.local.backup"
    Move-Item ".env.local" ".env.local.backup" -Force
}

# Function to generate random secret (base64)
function New-Secret {
    param([int]$Length = 32)

    try {
        $bytes = New-Object byte[] $Length
        $rng = [System.Security.Cryptography.RNGCryptoServiceProvider]::new()
        $rng.GetBytes($bytes)
        $secret = [Convert]::ToBase64String($bytes)
        return $secret -replace '[^A-Za-z0-9+/]', ''  # Remove padding for cleaner secrets
    }
    catch {
        Write-Error "Failed to generate secret: $_"
        exit 1
    }
}

function New-HexSecret {
    param([int]$ByteLength = 16)

    try {
        $bytes = New-Object byte[] $ByteLength
        $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
        $rng.GetBytes($bytes)
        return ([System.BitConverter]::ToString($bytes)).Replace("-", "").ToLowerInvariant()
    }
    catch {
        Write-Error "Failed to generate hex secret: $_"
        exit 1
    }
}

function Convert-ToBase64Url {
    param([byte[]]$Bytes)

    return [Convert]::ToBase64String($Bytes).TrimEnd("=").Replace("+", "-").Replace("/", "_")
}

function New-ActivePiecesWorkerToken {
    param([string]$JwtSecret)

    $issuedAt = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    $expiresAt = $issuedAt + (100 * 365 * 24 * 3600)
    $headerJson = '{"alg":"HS256","typ":"JWT","kid":"1"}'
    $payloadObject = [ordered]@{
        id = [guid]::NewGuid().ToString("N")
        type = "WORKER"
        iss = "activepieces"
        iat = $issuedAt
        exp = $expiresAt
    }
    $payloadJson = $payloadObject | ConvertTo-Json -Compress

    $header = Convert-ToBase64Url ([System.Text.Encoding]::UTF8.GetBytes($headerJson))
    $payload = Convert-ToBase64Url ([System.Text.Encoding]::UTF8.GetBytes($payloadJson))
    $message = "$header.$payload"
    $hmac = [System.Security.Cryptography.HMACSHA256]::new([System.Text.Encoding]::UTF8.GetBytes($JwtSecret))
    $signatureBytes = $hmac.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($message))
    $signature = Convert-ToBase64Url $signatureBytes
    $hmac.Dispose()

    return "$message.$signature"
}

Write-Info "Generating secure secrets..."

# Generate secrets
$AppSecret = New-Secret 32
$JwtSecret = New-Secret 32
$RedisPassword = New-Secret 24
$SyncWebhookSecret = New-Secret 24
$ActivePiecesWebhookSecret = New-Secret 24
$ActivePiecesJwtSecret = New-Secret 48
$ActivePiecesEncryptionKey = New-HexSecret 16
$ActivePiecesWorkerToken = New-ActivePiecesWorkerToken $ActivePiecesJwtSecret

Write-Success "[OK] Secrets generated"

# Create .env.local content
$EnvContent = @"
# ============================================
# Development Secrets - GENERATED
# Generated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
# DO NOT COMMIT THIS FILE
# ============================================

# Environment
ENVIRONMENT=development
APP_ENV=development
DEBUG=true
LOG_LEVEL=DEBUG

# Database
DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/sanskritisetu
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=sanskritisetu

# Redis Cache
REDIS_URL=redis://:$RedisPassword@redis:6379/0
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=$RedisPassword

# Dramatiq (uses Redis as broker)
DRAMATIQ_BROKER_URL=redis://:$RedisPassword@redis:6379/1

# API & Ports
API_HOST=0.0.0.0
API_PORT=8110
BACKEND_URL=http://localhost:8110
ALLOWED_ORIGINS=http://localhost:5173,http://localhost:3000,http://localhost

# Authentication & Security
SECRET_KEY=$AppSecret
JWT_SECRET_KEY=$JwtSecret
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=30

# Sync Server
SYNC_SERVER_URL=ws://localhost:1234
SYNC_WEBHOOK_SECRET=$SyncWebhookSecret

# Compose
COMPOSE_PROJECT_NAME=sanskritisetuorg

# ActivePieces (Local Development)
AP_ENCRYPTION_KEY=$ActivePiecesEncryptionKey
AP_JWT_SECRET=$ActivePiecesJwtSecret
AP_WORKER_TOKEN=$ActivePiecesWorkerToken
ACTIVEPIECES_API_URL=http://localhost:8090/api/v1
ACTIVEPIECES_EMAIL=admin@sanskritisetu.org
ACTIVEPIECES_PASSWORD=change_me_locally
ACTIVEPIECES_WEBHOOK_SECRET=$ActivePiecesWebhookSecret

# Optional: LLM Providers
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://host.docker.internal:11434
# GOOGLE_API_KEY=your-key-here
# OPENAI_API_KEY=your-key-here
# ANTHROPIC_API_KEY=your-key-here

# Development
TEST_DATABASE_URL=sqlite:///./test.db
TESTING=0
"@

# Write .env.local
$EnvContent | Out-File -FilePath ".env.local" -Encoding UTF8

# Set file permissions (Windows ACL)
try {
    $Acl = Get-Acl ".env.local"
    $Acl.Access | ForEach-Object { $Acl.RemoveAccessRule($_) }
    $CurrentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
    $AccessRule = New-Object System.Security.AccessControl.FileSystemAccessRule($CurrentUser, "FullControl", "Allow")
    $Acl.AddAccessRule($AccessRule)
    Set-Acl -Path ".env.local" -AclObject $Acl
}
catch {
    Write-Warning "Could not set file permissions: $_"
}

Write-Host ""
Write-Info "============================================================"
Write-Success "[OK] Setup Complete"
Write-Info "============================================================"

Write-Host ""
Write-Warning "Next steps:"
Write-Host "  1. Start services: .\quickstart.ps1"
Write-Host "  2. Or run: docker compose --env-file .env.local -f docker-compose.yml -f docker-compose.dev.yml up -d"
Write-Host "  3. Run migrations if needed: alembic -c src/alembic.ini upgrade head"

Write-Host ""
Write-Warning "Security Reminders:"
Write-Host "  - NEVER commit .env.local to git"
Write-Host "  - NEVER share .env.local files with team members"
Write-Host "  - Each developer generates their own secrets"
Write-Host "  - For staging/production, use GitHub Actions secrets"

Write-Host ""
Write-Success "[OK] Happy coding"
