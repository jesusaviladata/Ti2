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
$versionPath = Join-Path $packageRoot "VERSION.txt"

if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Ejecute este actualizador como administrador."
}
if (-not (Test-Path -LiteralPath (Join-Path $bundleSource "DataExpressAgent.exe") -PathType Leaf)) {
    throw "El paquete no contiene DataExpressAgent.exe."
}
if (-not (Test-Path -LiteralPath $serviceWrapper -PathType Leaf)) {
    throw "No se encontro el servicio instalado de Data Express Agent."
}
if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) {
    throw "No se encontro agent.json; use el instalador para una instalacion nueva."
}

$version = (Get-Content -LiteralPath $versionPath -Raw).Trim()
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$previousBundle = Join-Path $InstallDirectory "DataExpressAgent.previous-$timestamp"
$configBackup = "$configPath.before-$version-$timestamp.bak"

Copy-Item -LiteralPath $configPath -Destination $configBackup -Force
& $serviceWrapper stop

try {
    Move-Item -LiteralPath $currentBundle -Destination $previousBundle
    Copy-Item -LiteralPath $bundleSource -Destination $currentBundle -Recurse -Force

    $config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
    $config.agentVersion = $version
    $json = $config | ConvertTo-Json -Depth 30
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($configPath, $json, $utf8NoBom)

    & $serviceWrapper start
    Start-Sleep -Seconds 5
    $service = Get-Service -Name DataExpressAgent
    if ($service.Status -ne "Running") {
        throw "El servicio no quedo en ejecucion despues de actualizar."
    }
}
catch {
    if (Test-Path -LiteralPath $currentBundle) {
        Remove-Item -LiteralPath $currentBundle -Recurse -Force
    }
    if (Test-Path -LiteralPath $previousBundle) {
        Move-Item -LiteralPath $previousBundle -Destination $currentBundle
    }
    Copy-Item -LiteralPath $configBackup -Destination $configPath -Force
    & $serviceWrapper start
    throw
}

Write-Host "Data Express Agent actualizado a $version."
Write-Host "Configuracion preservada: $configPath"
Write-Host "Version anterior conservada en: $previousBundle"
