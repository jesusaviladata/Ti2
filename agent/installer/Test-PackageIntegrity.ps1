function Test-PackageIntegrity {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$PackageRoot
    )

    $manifestPath = [System.IO.Path]::GetFullPath((Join-Path $PackageRoot "SHA256SUMS.txt"))
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        throw "El paquete no contiene SHA256SUMS.txt."
    }

    $root = [System.IO.Path]::GetFullPath($PackageRoot).TrimEnd('\') + '\'
    $expected = @{}
    foreach ($line in Get-Content -LiteralPath $manifestPath -Encoding ASCII) {
        if ($line -notmatch '^([0-9a-fA-F]{64})  ([^\r\n]+)$') {
            throw "SHA256SUMS.txt contiene una línea inválida."
        }
        $hash = $Matches[1].ToLowerInvariant()
        $relative = $Matches[2].Replace('/', '\')
        if ([System.IO.Path]::IsPathRooted($relative)) {
            throw "SHA256SUMS.txt contiene una ruta absoluta."
        }
        $candidate = [System.IO.Path]::GetFullPath((Join-Path $PackageRoot $relative))
        if (-not $candidate.StartsWith($root, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "SHA256SUMS.txt contiene una ruta fuera del paquete."
        }
        if ($expected.ContainsKey($candidate)) {
            throw "SHA256SUMS.txt contiene una ruta duplicada: $relative"
        }
        $expected[$candidate] = $hash
    }

    if ($expected.Count -eq 0) {
        throw "SHA256SUMS.txt está vacío."
    }

    foreach ($path in $expected.Keys) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw "Falta un archivo registrado en SHA256SUMS.txt: $path"
        }
        $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash.ToLowerInvariant()
        if ($actual -ne $expected[$path]) {
            throw "La integridad SHA-256 no coincide para: $path"
        }
    }

    $actualFiles = Get-ChildItem -LiteralPath $PackageRoot -File -Recurse |
        Where-Object { $_.FullName -ne $manifestPath }
    foreach ($file in $actualFiles) {
        if (-not $expected.ContainsKey([System.IO.Path]::GetFullPath($file.FullName))) {
            throw "El paquete contiene un archivo no registrado: $($file.FullName)"
        }
    }
    if ($actualFiles.Count -ne $expected.Count) {
        throw "La cantidad de archivos no coincide con SHA256SUMS.txt."
    }

    return $true
}
