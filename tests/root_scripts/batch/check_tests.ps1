# Get pytest summary
Write-Host "Running admin endpoint tests..." -ForegroundColor Cyan
$output = python -m pytest tests/unit/test_admin_endpoints.py --tb=no -q 2>&1
$summary = ($output | Select-String "passed|failed|error" | Select-Object -Last 1).ToString()
Write-Host $summary -ForegroundColor Green

Write-Host "`nRunning ALL unit tests..." -ForegroundColor Cyan
$output = python -m pytest tests/unit/ --tb=no -q 2>&1
$summary = ($output | Select-String "passed|failed|error" | Select-Object -Last 1).ToString()
Write-Host $summary -ForegroundColor Green
