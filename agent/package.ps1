[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$WinSWPath,
    [string]$Version = "0.5.0",
    [ValidatePattern('^https://')][string]$ControlPlaneUrl = "",
    [string]$CommandSigningPublicKey = "",
    [string]$CommandSigningKeyId = "",
    # bootstrap.json descargado del panel (Configuracion > Agentes). Sustituye a los
    # tres parametros anteriores: trae la URL del panel y la llave publica de firma.
    [string]$BootstrapFile = "",
    [switch]$ReplaceExisting
)

$ErrorActionPreference = "Stop"
$agentRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $agentRoot
$bundleSource = Join-Path $agentRoot "dist\DataExpressAgent"
$releaseRoot = Join-Path $agentRoot "release"
$packageName = "DataExpressAgent-Windows-x64-$Version"
$packageRoot = Join-Path $releaseRoot $packageName
$installerTarget = Join-Path $packageRoot "installer"
$releaseNotesSource = Join-Path $agentRoot "CAMBIOS-AGENTE-$Version.md"
$quickInstallerSource = Join-Path $agentRoot "Instalar-DataExpressAgent.cmd"
$specsSource = Join-Path $repoRoot "docs\superpowers\specs"

if ($BootstrapFile) {
    if ($ControlPlaneUrl -or $CommandSigningPublicKey -or $CommandSigningKeyId) {
        throw "Use -BootstrapFile o los parametros ControlPlaneUrl y CommandSigning*, no ambos."
    }
    if (-not (Test-Path -LiteralPath $BootstrapFile -PathType Leaf)) {
        throw "No se encontro el bootstrap.json indicado."
    }
    $downloaded = Get-Content -LiteralPath $BootstrapFile -Raw -Encoding UTF8 | ConvertFrom-Json
    $activeId = [string]$downloaded.commandTrust.activeKeyId
    $activeKey = @($downloaded.commandTrust.keys | Where-Object { [string]$_.keyId -eq $activeId })
    if ([int]$downloaded.schemaVersion -ne 1 -or $activeKey.Count -ne 1 -or -not [string]$activeKey[0].publicKey) {
        throw "bootstrap.json no es valido; descarguelo de nuevo desde Configuracion > Agentes."
    }
    $ControlPlaneUrl = [string]$downloaded.controlPlaneUrl
    $CommandSigningKeyId = $activeId
    $CommandSigningPublicKey = [string]$activeKey[0].publicKey
}
if ($ControlPlaneUrl -notmatch '^https://' -or -not $CommandSigningPublicKey -or -not $CommandSigningKeyId) {
    throw "Indique -BootstrapFile o los parametros ControlPlaneUrl, CommandSigningPublicKey y CommandSigningKeyId."
}

if (-not (Test-Path (Join-Path $bundleSource "DataExpressAgent.exe"))) {
    throw "Primero ejecute build.ps1 para generar el agente."
}
if (-not (Test-Path -LiteralPath $WinSWPath -PathType Leaf)) {
    throw "No se encontro WinSW en la ruta indicada."
}
if (-not (Test-Path -LiteralPath $releaseNotesSource -PathType Leaf)) {
    throw "Falta CAMBIOS-AGENTE-$Version.md en la fuente del agente."
}
if (-not (Test-Path -LiteralPath $quickInstallerSource -PathType Leaf)) {
    throw "Falta Instalar-DataExpressAgent.cmd en la fuente del agente."
}
if (-not (Test-Path -LiteralPath $specsSource -PathType Container)) {
    throw "Falta la carpeta versionada de especificaciones."
}
if (Test-Path -LiteralPath $packageRoot) {
    if (-not $ReplaceExisting) {
        throw "El paquete $packageRoot ya existe; use -ReplaceExisting para respaldarlo y regenerarlo."
    }
    $archiveRoot = Join-Path $releaseRoot "archive"
    New-Item -ItemType Directory -Force -Path $archiveRoot | Out-Null
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    Move-Item -LiteralPath $packageRoot -Destination (Join-Path $archiveRoot "$packageName-$stamp")
    $oldZip = Join-Path $releaseRoot "$packageName.zip"
    if (Test-Path -LiteralPath $oldZip -PathType Leaf) {
        Move-Item -LiteralPath $oldZip -Destination (Join-Path $archiveRoot "$packageName-$stamp.zip")
    }
}

New-Item -ItemType Directory -Force -Path $packageRoot, $installerTarget | Out-Null
Copy-Item -Recurse -Force $bundleSource (Join-Path $packageRoot "DataExpressAgent")
Copy-Item -Force -LiteralPath $WinSWPath (Join-Path $packageRoot "DataExpressAgent.Service.exe")
Copy-Item -Force (Join-Path $agentRoot "installer\*") $installerTarget
Copy-Item -Force -LiteralPath $releaseNotesSource (Join-Path $packageRoot "CAMBIOS-AGENTE-$Version.md")
Copy-Item -Force -LiteralPath $quickInstallerSource (Join-Path $packageRoot "Instalar-DataExpressAgent.cmd")
Copy-Item -Recurse -Force -LiteralPath $specsSource (Join-Path $packageRoot "specs")
Set-Content -Encoding ASCII (Join-Path $packageRoot "VERSION.txt") $Version

$bootstrap = [ordered]@{
    schemaVersion = 1
    controlPlaneUrl = $ControlPlaneUrl.TrimEnd('/')
    agentVersion = $Version
    commandTrust = [ordered]@{
        activeKeyId = $CommandSigningKeyId
        keys = @(
            [ordered]@{
                keyId = $CommandSigningKeyId
                publicKey = $CommandSigningPublicKey
            }
        )
    }
    pollWaitSeconds = 25
    requestTimeoutSeconds = 40
    heartbeatIntervalSeconds = 30
}
$bootstrapJson = $bootstrap | ConvertTo-Json -Depth 8
$utf8WithoutBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText(
    (Join-Path $packageRoot "bootstrap.json"),
    $bootstrapJson,
    $utf8WithoutBom
)

$hashLines = Get-ChildItem -File -Recurse $packageRoot |
    Where-Object { $_.Name -ne "SHA256SUMS.txt" } |
    Sort-Object FullName |
    ForEach-Object {
        $relative = $_.FullName.Substring($packageRoot.Length).TrimStart("\").Replace("\", "/")
        $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash.ToLowerInvariant()
        "$hash  $relative"
    }
$hashLines | Set-Content -Encoding ASCII (Join-Path $packageRoot "SHA256SUMS.txt")

$zipPath = Join-Path $releaseRoot "$packageName.zip"
Compress-Archive -Path $packageRoot -DestinationPath $zipPath -CompressionLevel Optimal
Write-Host "Paquete creado en $zipPath"
