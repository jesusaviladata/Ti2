$scriptPath = Join-Path $PSScriptRoot "..\Test-PackageIntegrity.ps1"
. $scriptPath

function New-TestPackage([string]$Path) {
    New-Item -ItemType Directory -Force -Path $Path | Out-Null
    Set-Content -LiteralPath (Join-Path $Path "payload.txt") -Value "contenido" -Encoding UTF8
    $payloadHash = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $Path "payload.txt")).Hash.ToLowerInvariant()
    Set-Content -LiteralPath (Join-Path $Path "SHA256SUMS.txt") -Value "$payloadHash  payload.txt" -Encoding ASCII
    return $payloadHash
}

Describe "Test-PackageIntegrity" {
    It "acepta un paquete completo sin modificaciones" {
        $package = Join-Path $TestDrive "valid"
        New-TestPackage $package | Out-Null
        Test-PackageIntegrity -PackageRoot $package | Should Be $true
    }

    It "rechaza contenido modificado" {
        $package = Join-Path $TestDrive "modified"
        New-TestPackage $package | Out-Null
        Set-Content -LiteralPath (Join-Path $package "payload.txt") -Value "alterado" -Encoding UTF8
        $thrown = $false
        try { Test-PackageIntegrity -PackageRoot $package | Out-Null } catch { $thrown = $true }
        $thrown | Should Be $true
    }

    It "rechaza archivos no registrados" {
        $package = Join-Path $TestDrive "extra"
        New-TestPackage $package | Out-Null
        Set-Content -LiteralPath (Join-Path $package "extra.txt") -Value "extra" -Encoding UTF8
        $thrown = $false
        try { Test-PackageIntegrity -PackageRoot $package | Out-Null } catch { $thrown = $true }
        $thrown | Should Be $true
    }

    It "rechaza traversal fuera del paquete" {
        $package = Join-Path $TestDrive "traversal"
        $hash = New-TestPackage $package
        Set-Content -LiteralPath (Join-Path $package "SHA256SUMS.txt") -Value "$hash  ../fuera.txt" -Encoding ASCII
        $thrown = $false
        try { Test-PackageIntegrity -PackageRoot $package | Out-Null } catch { $thrown = $true }
        $thrown | Should Be $true
    }
}
