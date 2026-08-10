[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidatePattern('^https://')][string]$ServerUrl,
    [Parameter(Mandatory = $true)][string]$CommandSigningPublicKey,
    [Parameter(Mandatory = $true)][string]$CommandSigningKeyId,
    [Parameter(Mandatory = $true)][string]$PairingCode,
    [string]$InstallDirectory = "$env:ProgramFiles\Data Express\Agent"
)

$ErrorActionPreference = "Stop"
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$packageRoot = Split-Path -Parent $scriptRoot
$dataDirectory = "$env:ProgramData\DataExpress\Agent"
$serviceWrapper = Join-Path $InstallDirectory "DataExpressAgent.Service.exe"
$agentBundle = Join-Path $packageRoot "DataExpressAgent"

if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Ejecute este instalador como administrador."
}
if (-not (Test-Path (Join-Path $agentBundle "DataExpressAgent.exe"))) {
    throw "Falta la carpeta autocontenida DataExpressAgent en el paquete."
}
if (-not (Test-Path (Join-Path $packageRoot "DataExpressAgent.Service.exe"))) {
    throw "Falta el ejecutable oficial de WinSW en el paquete."
}

New-Item -ItemType Directory -Force -Path $InstallDirectory, $dataDirectory | Out-Null
Copy-Item -Recurse -Force $agentBundle $InstallDirectory
Copy-Item -Force (Join-Path $packageRoot "DataExpressAgent.Service.exe") $InstallDirectory
Copy-Item -Force (Join-Path $scriptRoot "DataExpressAgent.Service.xml") $InstallDirectory

$configuration = [ordered]@{
    serverUrl = $ServerUrl.TrimEnd('/')
    commandSigningPublicKey = $CommandSigningPublicKey
    commandSigningKeyId = $CommandSigningKeyId
    dataDir = $dataDirectory
    agentVersion = "0.1.0"
    pollWaitSeconds = 25
    requestTimeoutSeconds = 40
    verifyTls = $true
}
$configuration | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $dataDirectory "agent.json")
$PairingCode | Set-Content -Encoding ASCII -NoNewline (Join-Path $dataDirectory "pairing-code.tmp")

& icacls $dataDirectory /inheritance:r /grant:r "SYSTEM:(OI)(CI)F" "Administrators:(OI)(CI)F" "LOCAL SERVICE:(OI)(CI)M" | Out-Null
& icacls $InstallDirectory /inheritance:r /grant:r "SYSTEM:(OI)(CI)F" "Administrators:(OI)(CI)F" "LOCAL SERVICE:(OI)(CI)RX" | Out-Null

if (Get-Service -Name DataExpressAgent -ErrorAction SilentlyContinue) {
    & $serviceWrapper stop
    & $serviceWrapper uninstall
}
& $serviceWrapper install
& $serviceWrapper start
Write-Host "Data Express Agent instalado. Espere a que aparezca conectado en el panel."

