$scriptPath = Join-Path $PSScriptRoot "..\..\package.ps1"
$source = Get-Content -LiteralPath $scriptPath -Raw

Describe "package.ps1" {
    It "incluye el instalador rapido y el documento de cambios" {
        $source | Should Match 'Instalar-DataExpressAgent\.cmd'
        $source | Should Match 'CAMBIOS-AGENTE-\$Version\.md'
        $source | Should Match 'docs\\superpowers\\specs'
    }

    It "respalda una entrega existente solo con ReplaceExisting" {
        $source | Should Match '\[switch\]\$ReplaceExisting'
        $source | Should Match 'Move-Item -LiteralPath \$packageRoot'
        $source | Should Match 'archive'
    }

    It "genera hashes despues de copiar todos los artefactos" {
        $hash = $source.IndexOf('$hashLines = Get-ChildItem')
        $notes = $source.IndexOf('Copy-Item -Force -LiteralPath $releaseNotesSource')
        $quick = $source.IndexOf('Copy-Item -Force -LiteralPath $quickInstallerSource')
        $specs = $source.IndexOf('Copy-Item -Recurse -Force -LiteralPath $specsSource')
        $hash | Should BeGreaterThan $notes
        $hash | Should BeGreaterThan $quick
        $hash | Should BeGreaterThan $specs
    }
}
