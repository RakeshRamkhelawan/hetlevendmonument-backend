$logFile = "backend_debug.log"
Write-Host "Fetching backend logs to $logFile..."
if (-not (Test-Path ".env.local")) {
	Write-Host "Missing .env.local. Run .\\scripts\\setup-dev-secrets.ps1 first." -ForegroundColor Red
	exit 1
}

docker compose -p sanskritisetuorg --env-file .env.local -f docker-compose.yml -f docker-compose.dev.yml logs backend --tail 5000 > $logFile
Write-Host "Logs saved. Opening with notepad..."
Start-Process notepad $logFile
