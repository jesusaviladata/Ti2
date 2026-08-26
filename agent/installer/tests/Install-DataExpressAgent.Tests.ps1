$scriptPath = Join-Path $PSScriptRoot "..\Install-DataExpressAgent.ps1"
$source = Get-Content -LiteralPath $scriptPath -Raw

Describe "Install-DataExpressAgent" {
    It "solicita el codigo de forma interactiva cuando no se entrega" {
        $source | Should Match 'Read-Host -Prompt "Código de vinculación"'
        $source | Should Match '\[string\]\$PairingCode = ""'
    }

    It "no incluye el codigo en la configuracion final" {
        $source | Should Not Match '"pairingCode"\s*:'
        $source | Should Match '\$PairingCode = \$null'
    }

    It "limita los parametros heredados al modo de migracion" {
        $source | Should Match '\[switch\]\$MigrationMode'
        $source | Should Match 'sólo se aceptan con -MigrationMode'
    }

    It "valida bootstrap antes de instalar el servicio" {
        $integrity = $source.IndexOf('Test-PackageIntegrity -PackageRoot $packageRoot')
        $validation = $source.IndexOf('$bootstrap = Test-OfficialBootstrap')
        $install = $source.IndexOf('& $serviceWrapper install')
        $integrity | Should BeGreaterThan -1
        $validation | Should BeGreaterThan $integrity
        $validation | Should BeGreaterThan -1
        $install | Should BeGreaterThan $validation
    }

    It "elimina el codigo si falla la instalacion del servicio" {
        $source | Should Match 'Remove-Item -LiteralPath \$pairingPath'
    }

    It "rechaza sobrescribir una instalacion existente" {
        $source | Should Match 'ya está instalado\. Use Update-DataExpressAgent\.ps1'
        $source | Should Not Match '& \$serviceWrapper uninstall\s*\r?\n}\s*\r?\n\s*New-Item'
    }

    It "confirma heartbeat antes de informar instalacion exitosa" {
        $source | Should Match 'Wait-AgentHeartbeat -TimeoutSeconds \$EnrollmentTimeoutSeconds -Version'
        $source | Should Match 'Heartbeat confirmado con backend para agente \$Version'
        $source | Should Match 'instalado y vinculado correctamente'
    }

    It "archiva logs anteriores para no aceptar un heartbeat viejo" {
        $source | Should Match 'before-install-\$installStamp'
    }

    It "usa NetworkService para acceso SMB con identidad de maquina" {
        $source | Should Match 'NETWORK SERVICE:\(OI\)\(CI\)M'
        $source | Should Not Match 'LOCAL SERVICE:\(OI\)\(CI\)M'
    }
}
