[CmdletBinding()]
param(
    [string]$InstallDirectory = "$env:ProgramFiles\Data Express\Agent",
    [switch]$DeleteIdentity
)

$ErrorActionPreference = "Stop"
$serviceWrapper = Join-Path $InstallDirectory "DataExpressAgent.Service.exe"
if (Test-Path $serviceWrapper) {
    & $serviceWrapper stop
    & $serviceWrapper uninstall
}
if ($DeleteIdentity) {
    $identityPath = "$env:ProgramData\DataExpress\Agent\identity.json"
    if (Test-Path $identityPath) {
        Remove-Item -LiteralPath $identityPath -Force
        Write-Host "La identidad local fue eliminada; deberá reemplazar el agente en el panel."
    }
}
Write-Host "Servicio desinstalado. Los registros y la identidad se conservaron salvo petición explícita."

