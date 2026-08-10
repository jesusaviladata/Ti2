Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-InstallerConfig {
    param([Parameter(Mandatory)][string]$Path)

    $resolved = (Resolve-Path -LiteralPath $Path -ErrorAction Stop).Path
    $config = Import-PowerShellDataFile -LiteralPath $resolved
    $required = @(
        'InstallRoot', 'PostgresData', 'BackupRoot', 'PostgresMajor',
        'PostgresPort', 'PostgresServiceName', 'DatabaseName', 'DatabaseUser',
        'BackendPort', 'FrontendPort', 'IisSiteName', 'IisAppPoolName', 'PublicHost', 'IisHttpsPort',
        'FrontendHeapMb', 'FrontendMemoryWarnMb', 'FrontendMemoryRestartMb', 'FrontendMemorySamples'
    )
    foreach ($name in $required) {
        if (-not $config.ContainsKey($name) -or [string]::IsNullOrWhiteSpace([string]$config[$name])) {
            throw "Falta el valor obligatorio '$name' en $resolved"
        }
    }

    foreach ($name in @('InstallRoot', 'PostgresData', 'BackupRoot')) {
        if (-not [System.IO.Path]::IsPathRooted([string]$config[$name])) {
            throw "La ruta '$name' debe ser absoluta."
        }
    }

    $root = [System.IO.Path]::GetFullPath([string]$config.InstallRoot).TrimEnd('\')
    foreach ($name in @('PostgresData', 'BackupRoot')) {
        $candidate = [System.IO.Path]::GetFullPath([string]$config[$name])
        if (-not $candidate.StartsWith("$root\", [StringComparison]::OrdinalIgnoreCase)) {
            throw "La ruta '$name' debe permanecer dentro de InstallRoot."
        }
    }
    return $config
}

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-ConfiguredExecutable {
    param(
        [string]$ConfiguredPath,
        [Parameter(Mandatory)][string]$CommandName,
        [string[]]$FallbackPaths = @()
    )
    if ($ConfiguredPath -and (Test-Path -LiteralPath $ConfiguredPath -PathType Leaf)) {
        return (Resolve-Path -LiteralPath $ConfiguredPath).Path
    }
    $command = Get-Command $CommandName -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    foreach ($path in $FallbackPaths) {
        if (Test-Path -LiteralPath $path -PathType Leaf) { return $path }
    }
    return $null
}

function Read-EnvFile {
    param([Parameter(Mandatory)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "No existe el archivo de entorno: $Path"
    }
    $values = @{}
    foreach ($line in Get-Content -LiteralPath $Path) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith('#')) { continue }
        $parts = $trimmed.Split('=', 2)
        if ($parts.Count -ne 2) { throw "Linea invalida en $Path" }
        $values[$parts[0].Trim()] = $parts[1]
    }
    return $values
}

function Set-ProcessEnvironmentFromFile {
    param([Parameter(Mandatory)][string]$Path)
    $values = Read-EnvFile -Path $Path
    foreach ($entry in $values.GetEnumerator()) {
        [Environment]::SetEnvironmentVariable($entry.Key, [string]$entry.Value, 'Process')
    }
    return $values
}

function Assert-ExactParent {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$ExpectedParent
    )
    $actual = [System.IO.Path]::GetFullPath((Split-Path -Parent $Path)).TrimEnd('\')
    $expected = [System.IO.Path]::GetFullPath($ExpectedParent).TrimEnd('\')
    if (-not $actual.Equals($expected, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Operacion rechazada fuera de la carpeta esperada: $expected"
    }
}

function Get-ExpiredBackupFiles {
    param(
        [Parameter(Mandatory)][string]$Directory,
        [Parameter(Mandatory)][ValidateRange(1, 3650)][int]$Retain
    )
    if (-not (Test-Path -LiteralPath $Directory -PathType Container)) { return @() }
    return @(Get-ChildItem -LiteralPath $Directory -File -Filter '*.dump' | Sort-Object LastWriteTime -Descending | Select-Object -Skip $Retain)
}


function Write-MaintenanceEvent {
    param(
        [Parameter(Mandatory)][string]$LogPath,
        [Parameter(Mandatory)][string]$Event,
        [Parameter(Mandatory)][ValidateSet('info', 'warning', 'error')][string]$Level,
        [hashtable]$Data = @{}
    )
    $parent = Split-Path -Parent $LogPath
    if (-not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }
    $record = [ordered]@{
        timestamp = [DateTimeOffset]::Now.ToString('o')
        level = $Level
        event = $Event
        data = $Data
    }
    ($record | ConvertTo-Json -Compress -Depth 5) | Add-Content -LiteralPath $LogPath -Encoding utf8
}
