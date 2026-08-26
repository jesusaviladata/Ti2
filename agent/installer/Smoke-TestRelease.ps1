[CmdletBinding()]
param(
    [string]$PackageRoot = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "Test-PackageIntegrity.ps1")

Test-PackageIntegrity -PackageRoot $PackageRoot | Out-Null

$version = (Get-Content -LiteralPath (Join-Path $PackageRoot "VERSION.txt") -Raw).Trim()
$bootstrap = Get-Content -LiteralPath (Join-Path $PackageRoot "bootstrap.json") -Raw -Encoding UTF8 | ConvertFrom-Json
if ([string]$bootstrap.agentVersion -ne $version) {
    throw "VERSION.txt y bootstrap.json no contienen la misma versión."
}

[xml](Get-Content -LiteralPath (Join-Path $PSScriptRoot "DataExpressAgent.Service.xml") -Raw) | Out-Null
$releaseNotes = Join-Path $PackageRoot "CAMBIOS-AGENTE-$version.md"
if (-not (Test-Path -LiteralPath $releaseNotes -PathType Leaf)) {
    throw "Falta el documento de cambios de la versión $version."
}
if (Select-String -LiteralPath $releaseNotes -Pattern '\b(TODO|TBD)\b' -Quiet) {
    throw "El documento de cambios contiene marcadores pendientes."
}

Get-ChildItem -LiteralPath $PSScriptRoot -Filter "*.ps1" -File | ForEach-Object {
    $tokens = $null
    $errors = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile($_.FullName, [ref]$tokens, [ref]$errors)
    if ($errors.Count -gt 0) {
        throw "El script $($_.Name) contiene errores de sintaxis."
    }
}

Write-Host "Release $version verificada: integridad, configuración, documentación y sintaxis correctas."
