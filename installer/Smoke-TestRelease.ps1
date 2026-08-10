[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$BackendRoot,
    [Parameter(Mandatory)][string]$FrontendRoot,
    [Parameter(Mandatory)][string]$PythonPath,
    [Parameter(Mandatory)][string]$NodePath,
    [Parameter(Mandatory)][string]$LogRoot,
    [int]$BackendPort = 18000,
    [int]$FrontendPort = 13000
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
# PowerShell puede heredar PATH y Path simultaneamente; Start-Process rechaza ese entorno duplicado.
$processPath = [Environment]::GetEnvironmentVariable('Path', 'Process')
[Environment]::SetEnvironmentVariable('PATH', $null, 'Process')
if ($processPath) { [Environment]::SetEnvironmentVariable('Path', $processPath, 'Process') }

function Wait-HttpSuccess {
    param([Parameter(Mandatory)][string]$Uri)
    for ($attempt = 1; $attempt -le 15; $attempt++) {
        try {
            $response = Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec 4
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) { return }
        } catch {
            if ($attempt -eq 15) { throw "Smoke test sin respuesta valida en $Uri" }
            Start-Sleep -Seconds 2
        }
    }
}

foreach ($port in @($BackendPort, $FrontendPort)) {
    if ($port -lt 1024 -or $port -gt 65535) { throw "Puerto temporal invalido: $port" }
    if (Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue) { throw "El puerto temporal $port ya esta ocupado." }
}
New-Item -ItemType Directory -Path $LogRoot -Force | Out-Null
$backendProcess = $null
$frontendProcess = $null
try {
    $backendProcess = Start-Process -FilePath $PythonPath -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', [string]$BackendPort, '--workers', '1') -WorkingDirectory $BackendRoot -RedirectStandardOutput (Join-Path $LogRoot 'smoke-backend.out.log') -RedirectStandardError (Join-Path $LogRoot 'smoke-backend.err.log') -PassThru
    Wait-HttpSuccess -Uri "http://127.0.0.1:$BackendPort/health/ready"

    $oldNodeEnv = $env:NODE_ENV
    $oldHostname = $env:HOSTNAME
    $oldPort = $env:PORT
    $oldNodeOptions = $env:NODE_OPTIONS
    try {
        $env:NODE_ENV = 'production'
        $env:HOSTNAME = '127.0.0.1'
        $env:NODE_OPTIONS = '--max-old-space-size=512'
        $env:PORT = [string]$FrontendPort
        $frontendServer = Join-Path $FrontendRoot 'server.js'
        $frontendArguments = '"' + $frontendServer + '"'
        $frontendProcess = Start-Process -FilePath $NodePath -ArgumentList @($frontendArguments) -WorkingDirectory $FrontendRoot -RedirectStandardOutput (Join-Path $LogRoot 'smoke-frontend.out.log') -RedirectStandardError (Join-Path $LogRoot 'smoke-frontend.err.log') -PassThru
    }
    finally {
        $env:NODE_ENV = $oldNodeEnv
        $env:HOSTNAME = $oldHostname
        $env:PORT = $oldPort
        $env:NODE_OPTIONS = $oldNodeOptions
    }
    Wait-HttpSuccess -Uri "http://127.0.0.1:$FrontendPort/login"
    Write-Host 'La release aprobo los smoke tests de backend y frontend.' -ForegroundColor Green
}
finally {
    foreach ($process in @($frontendProcess, $backendProcess)) {
        if ($process -and -not $process.HasExited) { Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue }
    }
}
