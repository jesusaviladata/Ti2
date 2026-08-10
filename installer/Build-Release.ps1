[CmdletBinding()]
param(
    [string]$SourceRoot = (Split-Path $PSScriptRoot -Parent),
    [Parameter(Mandatory)][string]$OutputPath,
    [string]$NodePath = '',
    [ValidateRange(1024, 8192)][int]$BuildHeapMb = 2048
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$source = (Resolve-Path -LiteralPath $SourceRoot -ErrorAction Stop).Path
$frontendSource = Join-Path $source 'frontend'
$backendSource = Join-Path $source 'backend'
if (-not (Test-Path -LiteralPath (Join-Path $frontendSource 'package.json') -PathType Leaf)) { throw 'SourceRoot no contiene frontend\package.json.' }
if (-not (Test-Path -LiteralPath (Join-Path $frontendSource 'package-lock.json') -PathType Leaf)) { throw 'SourceRoot no contiene frontend\package-lock.json.' }
if (-not (Test-Path -LiteralPath (Join-Path $backendSource 'requirements.txt') -PathType Leaf)) { throw 'SourceRoot no contiene backend\requirements.txt.' }

$node = if ($NodePath) { (Resolve-Path -LiteralPath $NodePath -ErrorAction Stop).Path } else {
    $command = Get-Command node.exe -ErrorAction SilentlyContinue
    if (-not $command) { throw 'No se encontro node.exe. Use -NodePath.' }
    $command.Source
}
$npm = Join-Path (Split-Path $node -Parent) 'npm.cmd'
if (-not (Test-Path -LiteralPath $npm -PathType Leaf)) { throw "No se encontro npm.cmd junto a $node." }

$output = [System.IO.Path]::GetFullPath($OutputPath).TrimEnd('\')
if ([System.IO.Path]::GetFullPath($source).TrimEnd('\').Equals($output, [StringComparison]::OrdinalIgnoreCase)) { throw 'OutputPath debe ser diferente de SourceRoot.' }
if (Test-Path -LiteralPath $output) { throw "OutputPath ya existe; use una carpeta nueva: $output" }
New-Item -ItemType Directory -Path $output -Force | Out-Null
$outputFrontend = Join-Path $output 'frontend'
$outputBackend = Join-Path $output 'backend'
New-Item -ItemType Directory -Path $outputFrontend, $outputBackend -Force | Out-Null

$oldNodeEnv = $env:NODE_ENV
$oldApiUrl = $env:NEXT_PUBLIC_API_URL
$oldWsUrl = $env:NEXT_PUBLIC_WS_URL
$oldNodeOptions = $env:NODE_OPTIONS
try {
    $env:NODE_ENV = 'production'
    $env:NEXT_PUBLIC_API_URL = ''
    $env:NEXT_PUBLIC_WS_URL = ''
    $env:NODE_OPTIONS = "--max-old-space-size=$BuildHeapMb"
    Push-Location $frontendSource
    try {
        & $npm ci --include=dev
        if ($LASTEXITCODE -ne 0) { throw "npm ci fallo con codigo $LASTEXITCODE." }
        & $npm run type-check
        if ($LASTEXITCODE -ne 0) { throw "type-check fallo con codigo $LASTEXITCODE." }
        & $npm run build
        if ($LASTEXITCODE -ne 0) { throw "El build de Next fallo con codigo $LASTEXITCODE." }
    }
    finally { Pop-Location }
}
finally {
    $env:NODE_ENV = $oldNodeEnv
    $env:NEXT_PUBLIC_API_URL = $oldApiUrl
    $env:NEXT_PUBLIC_WS_URL = $oldWsUrl
    $env:NODE_OPTIONS = $oldNodeOptions
}

$standalone = Join-Path $frontendSource '.next\standalone'
$static = Join-Path $frontendSource '.next\static'
if (-not (Test-Path -LiteralPath (Join-Path $standalone 'server.js') -PathType Leaf)) { throw 'Next no genero .next\standalone\server.js.' }
if (-not (Test-Path -LiteralPath $static -PathType Container)) { throw 'Next no genero .next\static.' }
Copy-Item -Path (Join-Path $standalone '*') -Destination $outputFrontend -Recurse -Force
New-Item -ItemType Directory -Path (Join-Path $outputFrontend '.next') -Force | Out-Null
Copy-Item -LiteralPath $static -Destination (Join-Path $outputFrontend '.next') -Recurse -Force
if (Test-Path -LiteralPath (Join-Path $frontendSource 'public') -PathType Container) { Copy-Item -LiteralPath (Join-Path $frontendSource 'public') -Destination $outputFrontend -Recurse -Force }
& robocopy.exe $backendSource $outputBackend /E /XD '.venv' '__pycache__' '.pytest_cache' 'tests' 'tests_prod' /XF 'infra_platform.db' 'access_sessions.log' /NFL /NDL /NJH /NJS /NP
$backendCode = $LASTEXITCODE
if ($backendCode -gt 7) { throw "No se pudo copiar el backend; robocopy termino con codigo $backendCode." }

$manifestPath = Join-Path $output 'release-manifest.json'
$entries = @()
foreach ($file in Get-ChildItem -LiteralPath $output -Recurse -File | Where-Object FullName -ne $manifestPath) {
    $relative = $file.FullName.Substring($output.Length).TrimStart('\').Replace('\', '/')
    $entries += [ordered]@{ path = $relative; sha256 = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant() }
}
$manifest = [ordered]@{ schemaVersion = 1; generatedAt = [DateTimeOffset]::Now.ToString('o'); nodeVersion = (& $node --version).Trim(); buildHeapMb = $BuildHeapMb; files = $entries }
$manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $manifestPath -Encoding utf8
Write-Host "Release lista: $output" -ForegroundColor Green
Write-Host "Archivos protegidos por SHA-256: $($entries.Count)"
