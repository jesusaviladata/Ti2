[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$WinSWPath,
    [string]$Version = "0.2.3"
)

$ErrorActionPreference = "Stop"
$agentRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$bundleSource = Join-Path $agentRoot "dist\DataExpressAgent"
$releaseRoot = Join-Path $agentRoot "release"
$packageName = "DataExpressAgent-Windows-x64-$Version"
$packageRoot = Join-Path $releaseRoot $packageName
$installerTarget = Join-Path $packageRoot "installer"

if (-not (Test-Path (Join-Path $bundleSource "DataExpressAgent.exe"))) {
    throw "Primero ejecute build.ps1 para generar el agente."
}
if (-not (Test-Path -LiteralPath $WinSWPath -PathType Leaf)) {
    throw "No se encontro WinSW en la ruta indicada."
}
if (Test-Path -LiteralPath $packageRoot) {
    throw "El paquete $packageRoot ya existe; revise o retire esa version antes de regenerarla."
}

New-Item -ItemType Directory -Force -Path $packageRoot, $installerTarget | Out-Null
Copy-Item -Recurse -Force $bundleSource (Join-Path $packageRoot "DataExpressAgent")
Copy-Item -Force -LiteralPath $WinSWPath (Join-Path $packageRoot "DataExpressAgent.Service.exe")
Copy-Item -Force (Join-Path $agentRoot "installer\*") $installerTarget
Set-Content -Encoding ASCII (Join-Path $packageRoot "VERSION.txt") $Version

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
