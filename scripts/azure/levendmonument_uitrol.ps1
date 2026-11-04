# Uitrol Het Levend Monument naar Azure (resourcegroep levendmonument-prod, northeurope).
#
# Gebruik:  powershell -File scripts\azure\levendmonument_uitrol.ps1 -Fase <naam> -ImageTag levendmonument-<sha>
# Fases, in deze volgorde:
#   geheimen  - ontbrekende geheimen in de Key Vault zetten (bestaande blijven staan)
#   basis     - bicep fase 1: identiteit, logboek, opslag, omgeving, redis, jobs
#   opslag    - connection string van de opslag in de Key Vault
#   db        - migratiejob (eigenaar), daarna rollenjob (applicatierol en bypassrol)
#   apps      - bicep fase 2: api, worker, portal
#   controle  - rooktest via de portal
#
# De verbinding met Azure valt op deze pc regelmatig weg ("Connection aborted"); elke
# az-aanroep loopt daarom via Herhaal. Geheimen gaan via --file, nooit op de opdrachtregel.

param(
    [Parameter(Mandatory = $true)][ValidateSet('geheimen', 'basis', 'opslag', 'db', 'apps', 'controle')]
    [string]$Fase,
    [string]$ImageTag = '',
    [string]$SleutelMap = 'C:\tmp\lm-azure'
)

$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$RG = 'levendmonument-prod'
$KV = 'levendmonument-kv-prd'
$DBHOST = 'levendmonument-db-prd.postgres.database.azure.com'
$DBNAAM = 'levendmonument'
$Repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$Bicep = Join-Path $Repo 'infra\main-levendmonument-prod.bicep'

function Herhaal([scriptblock]$Blok, [int]$Pogingen = 6) {
    # In Windows PowerShell 5.1 maakt stderr van een native commando met 2>&1 een fout; met
    # 'Stop' zou de eerste weggevallen verbinding het script afbreken in plaats van herhalen.
    $ErrorActionPreference = 'Continue'
    for ($i = 1; $i -le $Pogingen; $i++) {
        $uit = & $Blok 2>&1
        $tekst = ($uit | Out-String)
        if ($LASTEXITCODE -eq 0 -or $tekst -match 'already exists') { return $uit }
        Write-Host "  poging $i mislukt: $($tekst.Trim().Split([Environment]::NewLine)[0])"
        Start-Sleep -Seconds (10 * $i)
    }
    throw "Na $Pogingen pogingen nog steeds mislukt."
}

function Geheim-Bestaat([string]$Naam) {
    $uit = Herhaal { az keyvault secret list --vault-name $KV --query "[].name" -o tsv }
    return ($uit -split "`r?`n") -contains $Naam
}

function Geheim-Lees([string]$Naam) {
    return "$(Herhaal { az keyvault secret show --vault-name $KV -n $Naam --query value -o tsv } | Select-Object -Last 1)".Trim()
}

function Geheim-Zet([string]$Naam, [string]$Waarde) {
    $tmp = Join-Path $env:TEMP ("lm-" + [guid]::NewGuid().ToString('N') + '.tmp')
    try {
        [IO.File]::WriteAllText($tmp, $Waarde)
        Herhaal { az keyvault secret set --vault-name $KV -n $Naam --file $tmp --encoding utf-8 --query name -o tsv } | Out-Null
        Write-Host "  geheim gezet: $Naam"
    } finally {
        Remove-Item $tmp -Force -ErrorAction SilentlyContinue
    }
}

function Willekeurig([int]$Lengte) {
    $tekens = [char[]]'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789'
    $bytes = New-Object byte[] $Lengte
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    return -join ($bytes | ForEach-Object { $tekens[$_ % $tekens.Length] })
}

# Schrijfacties op management.azure.com via `az` (Python) worden vanaf deze pc steeds
# afgebroken (ConnectionResetError 10054, gemeten 2026-11-02); dezelfde aanvraag via
# Invoke-RestMethod lukt wel. Lezen via `az` en de Key Vault (data plane) werken gewoon.
$Sub = '<azure-subscription-id>'
$Arm = 'https://management.azure.com'

function Arm-Token {
    $t = "$(Herhaal { az account get-access-token --resource https://management.azure.com/ --query accessToken -o tsv } | Select-Object -Last 1)".Trim()
    if (-not $t) { throw 'geen ARM-token' }
    return $t
}

function Arm([string]$Methode, [string]$Pad, $Body = $null) {
    $url = if ($Pad.StartsWith('http')) { $Pad } else { "$Arm$Pad" }
    for ($i = 1; $i -le 12; $i++) {
        try {
            $kop = @{ Authorization = "Bearer $(Arm-Token)" }
            if ($null -ne $Body) {
                $json = if ($Body -is [string]) { $Body } else { $Body | ConvertTo-Json -Depth 100 -Compress }
                # PS 5.1 codeert een string-body als ISO-8859-1; daarom expliciet UTF-8-bytes.
                return Invoke-RestMethod -Method $Methode -Uri $url -Headers $kop -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($json)) -TimeoutSec 120
            }
            return Invoke-RestMethod -Method $Methode -Uri $url -Headers $kop -TimeoutSec 120
        } catch {
            $status = $_.Exception.Response.StatusCode.value__
            $detail = $_.ErrorDetails.Message
            if ($status -and $status -ge 400 -and $status -lt 500) { throw "ARM $Methode $Pad -> $status $detail" }
            Write-Host "  ARM-poging $i mislukt: $($_.Exception.Message)"
            Start-Sleep -Seconds ([Math]::Min(5 * $i, 30))
        }
    }
    throw "ARM $Methode $Pad bleef mislukken"
}

function Bicep-Uitrol([bool]$Apps) {
    if (-not $ImageTag) { throw 'ImageTag ontbreekt' }
    $smtpUser = ''
    $f = Join-Path $SleutelMap 'brevo-smtp-login.txt'
    if (Test-Path $f) { $smtpUser = "$(Get-Content $f -Raw)".Trim() }
    if (-not $smtpUser) { $smtpUser = (Geheim-Lees 'smtp-user') }
    if ($smtpUser -eq 'NOG-NIET-INGESTELD') { $smtpUser = '' }
    $params = @{
        '$schema'      = 'https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#'
        contentVersion = '1.0.0.0'
        parameters     = @{
            imageTag    = @{ value = $ImageTag }
            smtpUser    = @{ value = $smtpUser }
            deployApps  = @{ value = $Apps }
        }
    }
    $tpl = Join-Path $env:TEMP ("lm-tpl-" + [guid]::NewGuid().ToString('N') + '.json')
    try {
        Herhaal { az bicep build --file $Bicep --outfile $tpl } | Out-Null
        $template = Get-Content $tpl -Raw -Encoding UTF8
        $naam = 'lm-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
        $body = '{"properties":{"mode":"Incremental","template":' + $template + ',"parameters":' + ($params.parameters | ConvertTo-Json -Depth 10 -Compress) + '}}'
        $pad = "/subscriptions/$Sub/resourceGroups/$RG/providers/Microsoft.Resources/deployments/${naam}?api-version=2021-04-01"
        Arm 'Put' $pad $body | Out-Null
        Write-Host "  deployment $naam gestart"
        for ($i = 0; $i -lt 120; $i++) {
            Start-Sleep -Seconds 20
            $d = Arm 'Get' $pad
            $st = $d.properties.provisioningState
            Write-Host "  deployment status: $st"
            if ($st -eq 'Succeeded') {
                $d.properties.outputs | ConvertTo-Json -Depth 5
                return
            }
            if ($st -in @('Failed', 'Canceled')) {
                $ops = Arm 'Get' "/subscriptions/$Sub/resourceGroups/$RG/providers/Microsoft.Resources/deployments/$naam/operations?api-version=2021-04-01"
                foreach ($o in $ops.value) {
                    if ($o.properties.provisioningState -eq 'Failed') {
                        Write-Host "  FOUT bij $($o.properties.targetResource.resourceName): $($o.properties.statusMessage | ConvertTo-Json -Depth 8 -Compress)"
                    }
                }
                throw "deployment ${naam}: $st"
            }
        }
        throw 'deployment duurde te lang'
    } finally {
        Remove-Item $tpl -Force -ErrorAction SilentlyContinue
    }
}

function Job-Draai([string]$Job) {
    $basis = "/subscriptions/$Sub/resourceGroups/$RG/providers/Microsoft.App/jobs/$Job"
    $start = Arm 'Post' "$basis/start?api-version=2024-03-01" '{}'
    $exec = $start.name
    if (-not $exec) { $exec = ($start.id -split '/')[-1] }
    Write-Host "  $Job gestart: $exec"
    for ($i = 0; $i -lt 90; $i++) {
        Start-Sleep -Seconds 20
        $st = (Arm 'Get' "$basis/executions/${exec}?api-version=2024-03-01").properties.status
        Write-Host "  $Job status: $st"
        if ($st -eq 'Succeeded') { return }
        if ($st -in @('Failed', 'Stopped', 'Degraded')) { throw "$Job eindigde met $st (logboek: Log Analytics levendmonument-logs, ContainerAppConsoleLogs_CL)" }
    }
    throw "$Job duurde te lang"
}

switch ($Fase) {
    'geheimen' {
        $willekeurig = [ordered]@{
            'secret-key'                 = 64
            'jwt-secret-key'             = 64
            'tool-payload-pseudonym-key' = 48
            'master-encryption-key'      = 48
            'audit-chain-hmac-key'       = 64
            'app-db-password'            = 40
            'bypass-db-password'         = 40
            'default-admin-password'     = 28
        }
        foreach ($n in $willekeurig.Keys) {
            if (Geheim-Bestaat $n) { Write-Host "  bestaat al: $n" } else { Geheim-Zet $n (Willekeurig $willekeurig[$n]) }
        }
        # Verbindingen. Het wachtwoord wordt URL-gecodeerd; de rolnamen staan vast in de migraties.
        $eigUser = Geheim-Lees 'postgres-admin-user'
        $eigPw = [uri]::EscapeDataString((Geheim-Lees 'postgres-admin-password'))
        $appPw = [uri]::EscapeDataString((Geheim-Lees 'app-db-password'))
        $bypPw = [uri]::EscapeDataString((Geheim-Lees 'bypass-db-password'))
        Geheim-Zet 'db-owner-url' "postgresql+asyncpg://${eigUser}:${eigPw}@${DBHOST}:5432/${DBNAAM}"
        Geheim-Zet 'app-database-url' "postgresql+asyncpg://sanskritisetu_app:${appPw}@${DBHOST}:5432/${DBNAAM}"
        Geheim-Zet 'bypass-database-url' "postgresql+asyncpg://sanskritisetu_bypass:${bypPw}@${DBHOST}:5432/${DBNAAM}"
        # Sleutels van externe diensten, uit losse bestanden die de gebruiker vult. Een leeg of
        # ontbrekend bestand laat een bestaand geheim staan; bestaat er nog niets, dan komt er
        # een duidelijke plaatshouder zodat de Key-Vault-verwijzing van de app niet faalt.
        $extern = [ordered]@{
            'hcaptcha-secret-key' = 'hcaptcha-secret.txt'
            'brevo-api-key'       = 'brevo-api.txt'
            'smtp-password'       = 'brevo-smtp-key.txt'
            'smtp-user'           = 'brevo-smtp-login.txt'
            'hcaptcha-site-key'   = 'hcaptcha-sitekey.txt'
        }
        foreach ($n in $extern.Keys) {
            $f = Join-Path $SleutelMap $extern[$n]
            $w = if (Test-Path $f) { "$(Get-Content $f -Raw)" } else { '' }
            if ($w) { $w = $w.Trim() }
            if ($w) {
                Geheim-Zet $n $w
                Remove-Item $f -Force
                Write-Host "  bestand gewist: $($extern[$n])"
            } elseif (-not (Geheim-Bestaat $n)) {
                Geheim-Zet $n 'NOG-NIET-INGESTELD'
            } else {
                Write-Host "  bestaat al: $n"
            }
        }
    }
    'basis' { Bicep-Uitrol $false }
    'opslag' {
        # De connection string zet de bicep zelf in de Key Vault (listKeys draait in Azure;
        # vanaf deze pc wordt elke aanroep die een sleutel teruggeeft afgebroken).
        if (Geheim-Bestaat 'storage-connection-string') { Write-Host '  storage-connection-string staat in de Key Vault' } else { throw 'storage-connection-string ontbreekt: eerst fase basis' }
    }
    'db' {
        Job-Draai 'levendmonument-migratie'
        Job-Draai 'levendmonument-dbrollen'
    }
    'apps' { Bicep-Uitrol $true }
    'controle' {
        $fqdn = (Herhaal { az containerapp show -g $RG -n levendmonument-portal --query properties.configuration.ingress.fqdn -o tsv } | Select-Object -Last 1).ToString().Trim()
        foreach ($pad in '/', '/privacy', '/api/v1/health') {
            try {
                $r = Invoke-WebRequest -UseBasicParsing -Uri "https://$fqdn$pad" -TimeoutSec 30
                Write-Host "  $pad -> $($r.StatusCode)"
            } catch {
                Write-Host "  $pad -> FOUT $($_.Exception.Message)"
            }
        }
    }
}
Write-Host "Fase $Fase klaar $(Get-Date -Format s)"
