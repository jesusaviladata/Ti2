[CmdletBinding()]
param(
    [string]$PackageRoot = (Split-Path -Parent $PSScriptRoot),
    [int64]$MinimumFreeBytes = 209715200
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "Test-PackageIntegrity.ps1")

$results = @()
function Add-Check([string]$Name, [bool]$Passed, [string]$Detail) {
    $script:results += [PSCustomObject]@{
        Check = $Name
        Passed = $Passed
        Detail = $Detail
    }
}

Add-Check "Windows 64 bits" ([Environment]::Is64BitOperatingSystem) ([Environment]::OSVersion.VersionString)
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator
)
Add-Check "Permisos administrativos" $isAdmin $(if ($isAdmin) { "Disponibles" } else { "Se solicitarán durante la instalación" })

try {
    Test-PackageIntegrity -PackageRoot $PackageRoot | Out-Null
    Add-Check "Integridad del paquete" $true "Todos los hashes SHA-256 coinciden"
}
catch {
    Add-Check "Integridad del paquete" $false $_.Exception.Message
}

$required = @(
    "DataExpressAgent\DataExpressAgent.exe",
    "DataExpressAgent.Service.exe",
    "bootstrap.json",
    "VERSION.txt"
)
foreach ($relative in $required) {
    Add-Check $relative (Test-Path -LiteralPath (Join-Path $PackageRoot $relative) -PathType Leaf) "Archivo requerido"
}

$drive = Get-PSDrive -Name ([System.IO.Path]::GetPathRoot($env:ProgramFiles).TrimEnd(':\')) -ErrorAction SilentlyContinue
$hasSpace = $drive -and $drive.Free -ge $MinimumFreeBytes
Add-Check "Espacio para instalación" $hasSpace $(if ($drive) { "$($drive.Free) bytes libres" } else { "No fue posible consultar la unidad" })

$results | Format-Table -AutoSize
if (@($results | Where-Object { -not $_.Passed -and $_.Check -ne "Permisos administrativos" }).Count -gt 0) {
    throw "Los requisitos previos contienen bloqueos."
}
