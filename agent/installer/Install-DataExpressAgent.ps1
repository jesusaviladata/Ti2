[CmdletBinding()]
param(
    [string]$PairingCode = "",
    [string]$ProfilesFile = "",
    [string]$InstallDirectory = "$env:ProgramFiles\Data Express\Agent",
    [switch]$MigrationMode,
    [ValidatePattern('^https://')][string]$ServerUrl = "",
    [string]$CommandSigningPublicKey = "",
    [string]$CommandSigningKeyId = ""
)

$ErrorActionPreference = "Stop"
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$packageRoot = Split-Path -Parent $scriptRoot
$dataDirectory = "$env:ProgramData\DataExpress\Agent"
$serviceWrapper = Join-Path $InstallDirectory "DataExpressAgent.Service.exe"
$agentBundle = Join-Path $packageRoot "DataExpressAgent"
$packageBootstrap = Join-Path $packageRoot "bootstrap.json"
$installedBootstrap = Join-Path $InstallDirectory "bootstrap.json"
$pairingPath = Join-Path $dataDirectory "pairing-code.tmp"

function Test-OfficialBootstrap {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "El paquete no contiene bootstrap.json. Descargue un paquete oficial completo."
    }
    try {
        $document = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
        $uri = [Uri]$document.controlPlaneUrl
        $keys = @($document.commandTrust.keys)
        $active = [string]$document.commandTrust.activeKeyId
        $activeKey = @($keys | Where-Object { [string]$_.keyId -eq $active })
        if (
            [int]$document.schemaVersion -ne 1 -or
            $uri.Scheme -ne "https" -or
            -not $uri.Host -or
            $uri.AbsolutePath -ne "/" -or
            $keys.Count -lt 1 -or
            $activeKey.Count -ne 1 -or
            -not [string]$activeKey[0].publicKey -or
            -not [string]$document.agentVersion
        ) {
            throw "invalid"
        }
    }
    catch {
        throw "bootstrap.json no es válido; la instalación se canceló antes de crear el servicio."
    }
    return $document
}

if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Ejecute este instalador como administrador."
}
if (-not (Test-Path (Join-Path $agentBundle "DataExpressAgent.exe"))) {
    throw "Falta la carpeta autocontenida DataExpressAgent en el paquete."
}
if (-not (Test-Path (Join-Path $packageRoot "DataExpressAgent.Service.exe"))) {
    throw "Falta el ejecutable oficial de WinSW en el paquete."
}

$bootstrap = Test-OfficialBootstrap -Path $packageBootstrap
if ($ServerUrl -or $CommandSigningPublicKey -or $CommandSigningKeyId) {
    if (-not $MigrationMode) {
        throw "Los parámetros de servidor y firma sólo se aceptan con -MigrationMode."
    }
    if (-not $ServerUrl -or -not $CommandSigningPublicKey -or -not $CommandSigningKeyId) {
        throw "MigrationMode requiere ServerUrl, CommandSigningPublicKey y CommandSigningKeyId."
    }
    $bootstrap.controlPlaneUrl = $ServerUrl.TrimEnd('/')
    $bootstrap.commandTrust.activeKeyId = $CommandSigningKeyId
    $bootstrap.commandTrust.keys = @(
        [ordered]@{
            keyId = $CommandSigningKeyId
            publicKey = $CommandSigningPublicKey
        }
    )
}

if (-not $PairingCode) {
    $PairingCode = Read-Host -Prompt "Código de vinculación"
}
$PairingCode = $PairingCode.Trim()
if (-not $PairingCode -or $PairingCode.Length -gt 256) {
    throw "El código de vinculación no es válido."
}

if (Get-Service -Name DataExpressAgent -ErrorAction SilentlyContinue) {
    if (-not (Test-Path -LiteralPath $serviceWrapper)) {
        throw "Existe un servicio DataExpressAgent, pero no se encontró su WinSW para actualizarlo."
    }
    & $serviceWrapper stop
    & $serviceWrapper uninstall
}

New-Item -ItemType Directory -Force -Path $InstallDirectory, $dataDirectory | Out-Null
Copy-Item -Recurse -Force $agentBundle $InstallDirectory
Copy-Item -Force (Join-Path $packageRoot "DataExpressAgent.Service.exe") $InstallDirectory
Copy-Item -Force (Join-Path $scriptRoot "DataExpressAgent.Service.xml") $InstallDirectory

$bootstrapJson = $bootstrap | ConvertTo-Json -Depth 8
$utf8WithoutBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($installedBootstrap, $bootstrapJson, $utf8WithoutBom)

$sqlInstances = @()
$backupDestinations = @()
if ($ProfilesFile) {
    if (-not $MigrationMode) {
        throw "ProfilesFile sólo se acepta con -MigrationMode."
    }
    $resolvedProfiles = (Resolve-Path -LiteralPath $ProfilesFile).Path
    $profilesText = Get-Content -LiteralPath $resolvedProfiles -Raw -Encoding UTF8
    if ($profilesText -match '"(password|connectionString)"\s*:') {
        throw "El archivo de perfiles no puede contener contraseñas ni cadenas de conexión."
    }
    $profiles = $profilesText | ConvertFrom-Json
    $sqlInstances = @($profiles.sqlInstances)
    $backupDestinations = @($profiles.backupDestinations)
}

$configuration = [ordered]@{
    schemaVersion = 1
    dataDir = $dataDirectory
    sqlInstances = $sqlInstances
    backupDestinations = $backupDestinations
}
$configurationJson = $configuration | ConvertTo-Json -Depth 8
[System.IO.File]::WriteAllText(
    (Join-Path $dataDirectory "agent.json"),
    $configurationJson,
    $utf8WithoutBom
)
[System.IO.File]::WriteAllText($pairingPath, $PairingCode, [System.Text.Encoding]::ASCII)
$PairingCode = $null

& icacls $dataDirectory /inheritance:r /grant:r "SYSTEM:(OI)(CI)F" "Administrators:(OI)(CI)F" "LOCAL SERVICE:(OI)(CI)M" | Out-Null
& icacls $InstallDirectory /inheritance:r /grant:r "SYSTEM:(OI)(CI)F" "Administrators:(OI)(CI)F" "LOCAL SERVICE:(OI)(CI)RX" | Out-Null

try {
    & $serviceWrapper install
    & $serviceWrapper start
}
catch {
    Remove-Item -LiteralPath $pairingPath -Force -ErrorAction SilentlyContinue
    throw
}
Write-Host "Data Express Agent instalado. Espere a que aparezca conectado en el panel."
