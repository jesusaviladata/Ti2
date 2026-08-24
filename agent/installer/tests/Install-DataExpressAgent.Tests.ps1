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
        $validation = $source.IndexOf('$bootstrap = Test-OfficialBootstrap')
        $install = $source.IndexOf('& $serviceWrapper install')
        $validation | Should BeGreaterThan -1
        $install | Should BeGreaterThan $validation
    }

    It "elimina el codigo si falla la instalacion del servicio" {
        $source | Should Match 'Remove-Item -LiteralPath \$pairingPath'
    }
}
