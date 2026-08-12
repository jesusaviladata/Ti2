$ErrorActionPreference = "Stop"
$agentRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $agentRoot
try {
    python -m pip install -r requirements-dev.txt pyinstaller==6.11.1
    python -m pytest tests -q
    python -m PyInstaller --clean --noconfirm DataExpressAgent.spec
    Write-Host "Agente creado en $agentRoot\dist\DataExpressAgent\DataExpressAgent.exe"
}
finally {
    Pop-Location
}

