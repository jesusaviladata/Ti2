[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$InstallRoot,
    [int]$Port = 8000
)

$ErrorActionPreference = 'Stop'
. (Join-Path $InstallRoot 'installer\Common.ps1')
Set-ProcessEnvironmentFromFile -Path (Join-Path $InstallRoot 'config\production.env') | Out-Null
$backendRoot = Join-Path $InstallRoot 'app\current\backend'
$python = Join-Path $backendRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw "No existe el runtime backend: $python" }
Set-Location -LiteralPath $backendRoot
# Data Express opera en un solo servidor y el frontend ya tiene un unico runtime.
# Un worker evita duplicar scheduler, conexiones y memoria sin aportar capacidad
# real para este despliegue de una sola empresa.
& $python -m uvicorn app.main:app --host 127.0.0.1 --port $Port --workers 1 --proxy-headers --forwarded-allow-ips 127.0.0.1
exit $LASTEXITCODE
