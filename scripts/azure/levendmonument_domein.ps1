# Koppelt hetlevendmonument.nl en www.hetlevendmonument.nl aan de portal-app, met gratis
# managed certificates van Azure Container Apps (draaiboek stap 7).
# Volgorde: hostnamen toevoegen zonder certificaat (bindingType Disabled; Azure toetst het
# asuid-TXT-record) -> certificaat per hostnaam (HTTP-validatie, het A-record wijst al naar
# de omgeving) -> binden met SNI.
# Via Invoke-RestMethod: `az` breekt op deze pc schrijfacties af (zie levendmonument_uitrol.ps1).

$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$Sub = '<azure-subscription-id>'
$RG = 'levendmonument-prod'
$Base = "https://management.azure.com/subscriptions/$Sub/resourceGroups/$RG/providers/Microsoft.App"
$App = "$Base/containerApps/levendmonument-portal?api-version=2024-03-01"
$Domeinen = @(
    @{ host = 'hetlevendmonument.nl'; cert = 'hetlevendmonument-nl' },
    @{ host = 'www.hetlevendmonument.nl'; cert = 'www-hetlevendmonument-nl' }
)

function Token {
    $t = "$(az account get-access-token --resource https://management.azure.com/ --query accessToken -o tsv 2>$null)".Trim()
    if (-not $t) { throw 'geen token' }
    return $t
}

function Arm([string]$Methode, [string]$Url, $Body = $null) {
    for ($i = 1; $i -le 12; $i++) {
        try {
            $kop = @{ Authorization = "Bearer $(Token)" }
            if ($null -ne $Body) {
                $json = $Body | ConvertTo-Json -Depth 50 -Compress
                return Invoke-RestMethod -Method $Methode -Uri $Url -Headers $kop -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($json)) -TimeoutSec 120
            }
            return Invoke-RestMethod -Method $Methode -Uri $Url -Headers $kop -TimeoutSec 120
        } catch {
            $status = $_.Exception.Response.StatusCode.value__
            if ($status -and $status -ge 400 -and $status -lt 500) { throw "$Methode $Url -> $status $($_.ErrorDetails.Message)" }
            Write-Host "  poging $i mislukt: $($_.Exception.Message)"
            Start-Sleep -Seconds ([Math]::Min(5 * $i, 30))
        }
    }
    throw "$Methode $Url bleef mislukken"
}

function Wacht-App {
    for ($i = 0; $i -lt 40; $i++) {
        Start-Sleep -Seconds 10
        $st = (Arm 'Get' $App).properties.provisioningState
        if ($st -eq 'Succeeded') { return }
        if ($st -eq 'Failed') { throw 'portal-app provisioning Failed' }
    }
    throw 'portal-app bleef bezig'
}

function Zet-Domeinen($Lijst) {
    # Niet $app: PowerShell-namen zijn hoofdletterongevoelig en $App is de URL.
    $huidig = Arm 'Get' $App
    $ingress = $huidig.properties.configuration.ingress
    $body = @{ properties = @{ configuration = @{ ingress = @{
        external      = $ingress.external
        targetPort    = $ingress.targetPort
        transport     = $ingress.transport
        allowInsecure = $ingress.allowInsecure
        customDomains = $Lijst
    } } } }
    Arm 'Patch' $App $body | Out-Null
    Wacht-App
}

Write-Host 'Stap 1: hostnamen toevoegen (zonder certificaat)'
Zet-Domeinen @($Domeinen | ForEach-Object { @{ name = $_.host; bindingType = 'Disabled' } })

Write-Host 'Stap 2: managed certificates aanvragen'
$envId = (Arm 'Get' $App).properties.managedEnvironmentId
foreach ($d in $Domeinen) {
    $url = "https://management.azure.com$envId/managedCertificates/$($d.cert)?api-version=2024-03-01"
    Arm 'Put' $url @{ location = 'northeurope'; properties = @{ subjectName = $d.host; domainControlValidation = 'HTTP' } } | Out-Null
    Write-Host "  aangevraagd: $($d.host)"
}
foreach ($d in $Domeinen) {
    $url = "https://management.azure.com$envId/managedCertificates/$($d.cert)?api-version=2024-03-01"
    for ($i = 0; $i -lt 60; $i++) {
        $st = (Arm 'Get' $url).properties.provisioningState
        Write-Host "  $($d.host): $st"
        if ($st -eq 'Succeeded') { break }
        if ($st -eq 'Failed') { throw "certificaat $($d.host) Failed" }
        Start-Sleep -Seconds 20
    }
}

Write-Host 'Stap 3: binden met SNI'
Zet-Domeinen @($Domeinen | ForEach-Object { @{ name = $_.host; bindingType = 'SniEnabled'; certificateId = "$envId/managedCertificates/$($_.cert)" } })
Write-Host "DOMEIN KLAAR $(Get-Date -Format s)"
