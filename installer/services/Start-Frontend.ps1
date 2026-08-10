[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$InstallRoot,
    [int]$Port = 3000,
    [Parameter(Mandatory)][string]$NodePath,
    [ValidateRange(256, 8192)][int]$MaxOldSpaceSizeMb = 512
)

$ErrorActionPreference = 'Stop'
. (Join-Path $InstallRoot 'installer\Common.ps1')
Set-ProcessEnvironmentFromFile -Path (Join-Path $InstallRoot 'config\production.env') | Out-Null
$frontendRoot = Join-Path $InstallRoot 'app\current\frontend'
$server = Join-Path $frontendRoot 'server.js'
if (-not (Test-Path -LiteralPath $NodePath -PathType Leaf)) { throw "No existe Node.js: $NodePath" }
if (-not (Test-Path -LiteralPath $server -PathType Leaf)) { throw "No existe el servidor standalone: $server" }
$env:NODE_ENV = 'production'
$env:HOSTNAME = '127.0.0.1'
$env:PORT = [string]$Port
$env:NODE_OPTIONS = "--max-old-space-size=$MaxOldSpaceSizeMb"
Set-Location -LiteralPath $frontendRoot
& $NodePath $server
exit $LASTEXITCODE
