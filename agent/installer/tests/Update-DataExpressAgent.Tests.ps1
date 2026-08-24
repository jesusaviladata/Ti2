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
        $source | Should Match 'Move-Item -LiteralPath \$previousBundle -Destination \$currentBundle'
        $source | Should Match 'Copy-Item -LiteralPath \$configBackup -Destination \$configPath'
    }
}
