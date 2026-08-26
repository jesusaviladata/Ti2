$scriptPath = Join-Path $PSScriptRoot "..\Update-DataExpressAgent.ps1"
$source = Get-Content -LiteralPath $scriptPath -Raw

Describe "Update-DataExpressAgent" {
    It "preserva la configuracion operativa e identidad fuera del bundle" {
        $source | Should Match 'Copy-Item -LiteralPath \$configPath -Destination \$configBackup'
        $source | Should Not Match 'identity\.json.*Remove-Item'
    }

    It "actualiza el bootstrap oficial y lo restaura durante rollback" {
        $source | Should Match 'Copy-Item -LiteralPath \$packageBootstrap -Destination \$installedBootstrap'
        $source | Should Match 'Copy-Item -LiteralPath \$bootstrapBackup -Destination \$installedBootstrap'
    }

    It "conserva el journal perfiles DPAPI y catalogo en ProgramData" {
        $source | Should Not Match 'execution-journal|managed-profiles|file-catalog|identity\.json'
    }

    It "restaura bundle y configuracion cuando el heartbeat no confirma" {
        $stop = $source.LastIndexOf('& $serviceWrapper stop')
        $remove = $source.IndexOf('Remove-Item -LiteralPath $currentBundle')
        $stop | Should BeGreaterThan -1
        $remove | Should BeGreaterThan $stop
        $source | Should Match 'Move-Item -LiteralPath \$previousBundle -Destination \$currentBundle'
        $source | Should Match 'Copy-Item -LiteralPath \$configBackup -Destination \$configPath'
    }

    It "valida los hashes antes de detener el servicio" {
        $integrity = $source.IndexOf('Test-PackageIntegrity -PackageRoot $packageRoot')
        $stop = $source.IndexOf('& $serviceWrapper stop')
        $integrity | Should BeGreaterThan -1
        $stop | Should BeGreaterThan $integrity
    }

    It "migra LocalService a NetworkService y revierte la cuenta durante rollback" {
        $source | Should Match 'Get-CimInstance -ClassName Win32_Service'
        $source | Should Match 'LocalService\|LOCAL SERVICE'
        $source | Should Match 'sc\.exe config DataExpressAgent obj= "NT AUTHORITY\\NetworkService"'
        $source | Should Match 'sc\.exe config DataExpressAgent obj= \$previousServiceAccount'
    }
}
