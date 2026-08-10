[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)][string]$DumpPath,
    [string]$ConfigPath = (Join-Path $PSScriptRoot 'install-config.psd1'),
    [string]$TargetDatabase = '',
    [switch]$DropAfterValidation
)

. (Join-Path $PSScriptRoot 'Common.ps1')
$config = Get-InstallerConfig -Path $ConfigPath
$resolvedDump = (Resolve-Path -LiteralPath $DumpPath -ErrorAction Stop).Path
$backupRoot = [IO.Path]::GetFullPath([string]$config.BackupRoot).TrimEnd('\')
if (-not $resolvedDump.StartsWith("$backupRoot\", [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Solo se restauran archivos ubicados dentro de BackupRoot.'
}
if ([IO.Path]::GetExtension($resolvedDump) -ne '.dump') { throw 'El respaldo debe tener extension .dump.' }

$values = Read-EnvFile -Path (Join-Path $config.InstallRoot 'config\production.env')
$match = [regex]::Match($values.DATABASE_URL, '^postgresql\+asyncpg://(?<user>[^:]+):(?<password>[^@]+)@(?<host>[^:]+):(?<port>\d+)/(?<database>[^?]+)')
if (-not $match.Success) { throw 'DATABASE_URL no tiene el formato PostgreSQL esperado.' }
if (-not $TargetDatabase) { $TargetDatabase = "$($config.DatabaseName)_restore_$(Get-Date -Format 'yyyyMMddHHmmss')" }
if ($TargetDatabase -eq $config.DatabaseName) { throw 'La restauracion automatica nunca puede apuntar a la base productiva.' }
if ($TargetDatabase -notmatch '^[a-zA-Z][a-zA-Z0-9_]{0,62}$') { throw 'TargetDatabase contiene caracteres no permitidos.' }

$pgBin = Join-Path $env:ProgramFiles "PostgreSQL\$($config.PostgresMajor)\bin"
$pgRestore = Get-ConfiguredExecutable -ConfiguredPath '' -CommandName 'pg_restore.exe' -FallbackPaths @((Join-Path $pgBin 'pg_restore.exe'))
$createdb = Get-ConfiguredExecutable -ConfiguredPath '' -CommandName 'createdb.exe' -FallbackPaths @((Join-Path $pgBin 'createdb.exe'))
$dropdb = Get-ConfiguredExecutable -ConfiguredPath '' -CommandName 'dropdb.exe' -FallbackPaths @((Join-Path $pgBin 'dropdb.exe'))
$psql = Get-ConfiguredExecutable -ConfiguredPath '' -CommandName 'psql.exe' -FallbackPaths @((Join-Path $pgBin 'psql.exe'))
if (-not $pgRestore -or -not $createdb -or -not $dropdb -or -not $psql) { throw 'Faltan herramientas PostgreSQL de restauracion.' }

$adminPasswordSecure = Read-Host 'Contrasena del superusuario postgres (no se mostrara)' -AsSecureString
$pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($adminPasswordSecure)
try { $adminPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
$appPassword = [uri]::UnescapeDataString($match.Groups['password'].Value)
$previousPassword = $env:PGPASSWORD
try {
    & $pgRestore --list $resolvedDump | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'El archivo no es un respaldo PostgreSQL custom valido.' }
    if ($PSCmdlet.ShouldProcess($TargetDatabase, "Crear base temporal y restaurar $resolvedDump")) {
        $env:PGPASSWORD = $adminPassword
        & $createdb --host $match.Groups['host'].Value --port $match.Groups['port'].Value --username postgres --owner $match.Groups['user'].Value $TargetDatabase
        if ($LASTEXITCODE -ne 0) { throw "No se pudo crear la base temporal $TargetDatabase." }
        $env:PGPASSWORD = $appPassword
        & $pgRestore --host $match.Groups['host'].Value --port $match.Groups['port'].Value --username $match.Groups['user'].Value --dbname $TargetDatabase --no-owner --no-privileges $resolvedDump
        if ($LASTEXITCODE -ne 0) { throw "La restauracion termino con codigo $LASTEXITCODE" }
        & $psql --host $match.Groups['host'].Value --port $match.Groups['port'].Value --username $match.Groups['user'].Value --dbname $TargetDatabase --tuples-only --command 'SELECT version_num FROM alembic_version;' | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'La base restaurada no paso la comprobacion de Alembic.' }
        Write-Host "Restauracion comprobada en la base temporal: $TargetDatabase" -ForegroundColor Green
        if ($DropAfterValidation) {
            $env:PGPASSWORD = $adminPassword
            & $dropdb --host $match.Groups['host'].Value --port $match.Groups['port'].Value --username postgres $TargetDatabase
            if ($LASTEXITCODE -ne 0) { throw "No se pudo eliminar la base temporal $TargetDatabase." }
        }
    }
}
finally {
    $env:PGPASSWORD = $previousPassword
    $adminPassword = $null
    $appPassword = $null
}
