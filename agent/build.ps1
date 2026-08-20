$ErrorActionPreference = "Stop"
$agentRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $agentRoot
Push-Location $agentRoot
try {
    python -m pip install -r requirements-dev.txt pyinstaller==6.11.1
    if ($LASTEXITCODE -ne 0) {
        throw "No se pudieron instalar las dependencias de compilacion."
    }

    Push-Location $repoRoot
    try {
        python -m pytest agent\tests -q
        if ($LASTEXITCODE -ne 0) {
            throw "Las pruebas del agente fallaron; se cancela la compilacion."
        }
    }
    finally {
        Pop-Location
    }

    python -m PyInstaller --clean --noconfirm DataExpressAgent.spec
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller no pudo generar el ejecutable del agente."
    }

    Write-Host "Agente creado en $agentRoot\dist\DataExpressAgent\DataExpressAgent.exe"
}
finally {
    Pop-Location
}

