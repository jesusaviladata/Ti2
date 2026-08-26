[CmdletBinding()]
param(
    [string]$InstallDirectory = "$env:ProgramFiles\Data Express\Agent"
)

$ErrorActionPreference = "Stop"
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$packageRoot = Split-Path -Parent $scriptRoot
$bundleSource = Join-Path $packageRoot "DataExpressAgent"
$currentBundle = Join-Path $InstallDirectory "DataExpressAgent"
$serviceWrapper = Join-Path $InstallDirectory "DataExpressAgent.Service.exe"
$configPath = "$env:ProgramData\DataExpress\Agent\agent.json"
$dataDirectory = Split-Path -Parent $configPath
$versionPath = Join-Path $packageRoot "VERSION.txt"
$packageBootstrap = Join-Path $packageRoot "bootstrap.json"
$installedBootstrap = Join-Path $InstallDirectory "bootstrap.json"
$packageServiceConfig = Join-Path $scriptRoot "DataExpressAgent.Service.xml"
$installedServiceConfig = Join-Path $InstallDirectory "DataExpressAgent.Service.xml"
. (Join-Path $scriptRoot "Test-PackageIntegrity.ps1")

if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Ejecute este actualizador como administrador."
}
Test-PackageIntegrity -PackageRoot $packageRoot | Out-Null
if (-not (Test-Path -LiteralPath (Join-Path $bundleSource "DataExpressAgent.exe") -PathType Leaf)) {
    throw "El paquete no contiene DataExpressAgent.exe."
}
if (-not (Test-Path -LiteralPath $serviceWrapper -PathType Leaf)) {
    throw "No se encontro el servicio instalado de Data Express Agent."
}
if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) {
    throw "No se encontro agent.json; use el instalador para una instalacion nueva."
}
if (-not (Test-Path -LiteralPath $packageBootstrap -PathType Leaf)) {
    throw "El paquete no contiene bootstrap.json; no se modifico la instalacion."
}
if (-not (Test-Path -LiteralPath $packageServiceConfig -PathType Leaf)) {
    throw "El paquete no contiene la configuracion del servicio; no se modifico la instalacion."
}

$version = (Get-Content -LiteralPath $versionPath -Raw).Trim()
$serviceInfo = Get-CimInstance -ClassName Win32_Service -Filter "Name='DataExpressAgent'" -ErrorAction Stop
$previousServiceAccount = [string]$serviceInfo.StartName
$migrateBuiltInServiceAccount = $previousServiceAccount -match '^NT AUTHORITY\\(LocalService|LOCAL SERVICE)$'
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$previousBundle = Join-Path $InstallDirectory "DataExpressAgent.previous-$timestamp"
$configBackup = "$configPath.before-$version-$timestamp.bak"
$bootstrapBackup = "$installedBootstrap.before-$version-$timestamp.bak"
$serviceConfigBackup = "$installedServiceConfig.before-$version-$timestamp.bak"
$archivedServiceLogs = @()

Copy-Item -LiteralPath $configPath -Destination $configBackup -Force
if (Test-Path -LiteralPath $installedBootstrap -PathType Leaf) {
    Copy-Item -LiteralPath $installedBootstrap -Destination $bootstrapBackup -Force
}
Copy-Item -LiteralPath $installedServiceConfig -Destination $serviceConfigBackup -Force
& $serviceWrapper stop
$stopDeadline = (Get-Date).AddSeconds(60)
do {
    $service = Get-Service -Name DataExpressAgent -ErrorAction SilentlyContinue
    if (-not $service -or $service.Status -eq "Stopped") { break }
    Start-Sleep -Milliseconds 500
} while ((Get-Date) -lt $stopDeadline)
if ($service -and $service.Status -ne "Stopped") {
    throw "El servicio no se detuvo dentro de 60 segundos; no se reemplazaron binarios."
}

# Preserve prior logs so the post-update health check can only match a heartbeat
# emitted by the newly installed bundle.
$existingLogs = Get-ChildItem -LiteralPath $InstallDirectory -Filter "DataExpressAgent.Service*.log" -File -ErrorAction SilentlyContinue
foreach ($log in $existingLogs) {
    $archivedLog = "$($log.FullName).before-$version-$timestamp"
    Move-Item -LiteralPath $log.FullName -Destination $archivedLog
    $archivedServiceLogs += $archivedLog
}

try {
    Move-Item -LiteralPath $currentBundle -Destination $previousBundle
    Copy-Item -LiteralPath $bundleSource -Destination $currentBundle -Recurse -Force
    Copy-Item -LiteralPath $packageBootstrap -Destination $installedBootstrap -Force
    Copy-Item -LiteralPath $packageServiceConfig -Destination $installedServiceConfig -Force

    if ($migrateBuiltInServiceAccount) {
        & sc.exe config DataExpressAgent obj= "NT AUTHORITY\NetworkService" password= "" | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "No fue posible migrar el servicio a NetworkService." }
        & icacls $dataDirectory /grant "NETWORK SERVICE:(OI)(CI)M" | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "No fue posible conceder acceso de datos a NetworkService." }
        & icacls $InstallDirectory /grant "NETWORK SERVICE:(OI)(CI)RX" | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "No fue posible conceder acceso de programa a NetworkService." }
    }

    & $serviceWrapper start
    $healthDeadline = (Get-Date).AddSeconds(90)
    $heartbeatConfirmed = $false
    do {
        Start-Sleep -Seconds 2
        $service = Get-Service -Name DataExpressAgent
        if ($service.Status -ne "Running") { break }
        $logs = Get-ChildItem -LiteralPath $InstallDirectory -Filter "DataExpressAgent.Service*.log" -File -ErrorAction SilentlyContinue
        foreach ($log in $logs) {
            if (Select-String -LiteralPath $log.FullName -SimpleMatch "Heartbeat confirmado con backend para agente $version" -Quiet) {
                $heartbeatConfirmed = $true
                break
            }
        }
    } while (-not $heartbeatConfirmed -and (Get-Date) -lt $healthDeadline)
    if ($service.Status -ne "Running" -or -not $heartbeatConfirmed) {
        throw "El agente $version no confirmo heartbeat dentro de 90 segundos. Se aplicara rollback."
    }
}
catch {
    # El agente nuevo puede seguir en ejecución cuando falló únicamente la
    # confirmación del heartbeat. Debe detenerse antes de reemplazar archivos.
    & $serviceWrapper stop 2>$null
    $rollbackStopDeadline = (Get-Date).AddSeconds(60)
    do {
        $rollbackService = Get-Service -Name DataExpressAgent -ErrorAction SilentlyContinue
        if (-not $rollbackService -or $rollbackService.Status -eq "Stopped") { break }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $rollbackStopDeadline)
    if ($rollbackService -and $rollbackService.Status -ne "Stopped") {
        throw "El agente nuevo falló y no pudo detenerse; no es seguro reemplazar sus binarios durante rollback."
    }
    if (Test-Path -LiteralPath $currentBundle) {
        Remove-Item -LiteralPath $currentBundle -Recurse -Force
    }
    if (Test-Path -LiteralPath $previousBundle) {
        Move-Item -LiteralPath $previousBundle -Destination $currentBundle
    }
    Copy-Item -LiteralPath $configBackup -Destination $configPath -Force
    if (Test-Path -LiteralPath $bootstrapBackup -PathType Leaf) {
        Copy-Item -LiteralPath $bootstrapBackup -Destination $installedBootstrap -Force
    }
    elseif (Test-Path -LiteralPath $installedBootstrap) {
        Remove-Item -LiteralPath $installedBootstrap -Force
    }
    Copy-Item -LiteralPath $serviceConfigBackup -Destination $installedServiceConfig -Force
    if ($migrateBuiltInServiceAccount) {
        & sc.exe config DataExpressAgent obj= $previousServiceAccount password= "" | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "Se restauraron los archivos anteriores, pero no la cuenta original del servicio."
        }
    }
    & $serviceWrapper start
    if ($LASTEXITCODE -ne 0) {
        throw "Se restauró la versión anterior, pero WinSW no pudo iniciarla."
    }
    throw
}

Write-Host "Data Express Agent actualizado a $version."
Write-Host "Configuracion preservada: $configPath"
Write-Host "Version anterior conservada en: $previousBundle"
