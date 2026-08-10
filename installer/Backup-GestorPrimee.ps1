[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$ConfigPath = (Join-Path $PSScriptRoot 'install-config.psd1'),
    [switch]$Weekly
)

. (Join-Path $PSScriptRoot 'Common.ps1')
$config = Get-InstallerConfig -Path $ConfigPath
$envPath = Join-Path $config.InstallRoot 'config\production.env'
$values = Read-EnvFile -Path $envPath
if (-not $values.ContainsKey('DATABASE_URL')) { throw 'DATABASE_URL no existe en production.env.' }

$match = [regex]::Match($values.DATABASE_URL, '^postgresql\+asyncpg://(?<user>[^:]+):(?<password>[^@]+)@(?<host>[^:]+):(?<port>\d+)/(?<database>[^?]+)')
if (-not $match.Success) { throw 'DATABASE_URL no tiene el formato PostgreSQL esperado.' }

$pgBin = Join-Path $env:ProgramFiles "PostgreSQL\$($config.PostgresMajor)\bin"
$pgDump = Get-ConfiguredExecutable -ConfiguredPath '' -CommandName 'pg_dump.exe' -FallbackPaths @((Join-Path $pgBin 'pg_dump.exe'))
$pgRestore = Get-ConfiguredExecutable -ConfiguredPath '' -CommandName 'pg_restore.exe' -FallbackPaths @((Join-Path $pgBin 'pg_restore.exe'))
if (-not $pgDump -or -not $pgRestore) { throw 'No se encontraron pg_dump y pg_restore.' }

$dailyDir = Join-Path $config.BackupRoot 'daily'
$weeklyDir = Join-Path $config.BackupRoot 'weekly'
$logPath = Join-Path $config.InstallRoot 'logs\maintenance\postgres-backup.jsonl'
function Copy-VerifiedBackup {
    param([Parameter(Mandatory)][string]$Source, [Parameter(Mandatory)][string]$Destination)
    Copy-Item -LiteralPath $Source -Destination $Destination -Force
    $sourceHash = (Get-FileHash -LiteralPath $Source -Algorithm SHA256).Hash
    $destinationHash = (Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash
    if (-not $sourceHash.Equals($destinationHash, [StringComparison]::OrdinalIgnoreCase)) {
        throw "La copia de respaldo no coincide: $Destination"
    }
}
New-Item -ItemType Directory -Path $dailyDir, $weeklyDir -Force | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$dumpPath = Join-Path $dailyDir "$($config.DatabaseName)-$stamp.dump"
$makeWeekly = $Weekly -or [DateTime]::Today.DayOfWeek -eq [DayOfWeek]::Sunday
Assert-ExactParent -Path $dumpPath -ExpectedParent $dailyDir

$previousPassword = $env:PGPASSWORD
try {
    $env:PGPASSWORD = [uri]::UnescapeDataString($match.Groups['password'].Value)
    Write-MaintenanceEvent -LogPath $logPath -Event 'backup_started' -Level info -Data @{ file = [IO.Path]::GetFileName($dumpPath); weekly = $makeWeekly }
    if ($PSCmdlet.ShouldProcess($dumpPath, 'Crear respaldo PostgreSQL diario')) {
        & $pgDump --host $match.Groups['host'].Value --port $match.Groups['port'].Value --username $match.Groups['user'].Value --dbname $match.Groups['database'].Value --format custom --compress 9 --file $dumpPath
        if ($LASTEXITCODE -ne 0) { throw "pg_dump termino con codigo $LASTEXITCODE" }
        & $pgRestore --list $dumpPath | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "pg_restore --list termino con codigo $LASTEXITCODE" }

        $hash = (Get-FileHash -LiteralPath $dumpPath -Algorithm SHA256).Hash
        $size = (Get-Item -LiteralPath $dumpPath).Length
        Write-MaintenanceEvent -LogPath $logPath -Event 'backup_completed' -Level info -Data @{ file = [IO.Path]::GetFileName($dumpPath); bytes = $size; sha256 = $hash; weekly = $makeWeekly }

        if ($makeWeekly) {
            $weeklyPath = Join-Path $weeklyDir ([IO.Path]::GetFileName($dumpPath))
            Assert-ExactParent -Path $weeklyPath -ExpectedParent $weeklyDir
            Copy-VerifiedBackup -Source $dumpPath -Destination $weeklyPath
        }
        if ([string]$config.OffsiteRoot) {
            $offsiteDaily = Join-Path $config.OffsiteRoot 'daily'
            New-Item -ItemType Directory -Path $offsiteDaily -Force | Out-Null
            $offsiteDailyPath = Join-Path $offsiteDaily ([IO.Path]::GetFileName($dumpPath))
            Copy-VerifiedBackup -Source $dumpPath -Destination $offsiteDailyPath
            if ($makeWeekly) {
                $offsiteWeekly = Join-Path $config.OffsiteRoot 'weekly'
                New-Item -ItemType Directory -Path $offsiteWeekly -Force | Out-Null
                $offsiteWeeklyPath = Join-Path $offsiteWeekly ([IO.Path]::GetFileName($dumpPath))
                Copy-VerifiedBackup -Source $dumpPath -Destination $offsiteWeeklyPath
            }
        }
    }

    foreach ($policy in @(@{ Directory = $dailyDir; Retain = 14 }, @{ Directory = $weeklyDir; Retain = 8 })) {
        foreach ($file in @(Get-ExpiredBackupFiles -Directory $policy.Directory -Retain $policy.Retain)) {
            Assert-ExactParent -Path $file.FullName -ExpectedParent $policy.Directory
            if ($PSCmdlet.ShouldProcess($file.FullName, "Eliminar respaldo excedente; retencion $($policy.Retain)")) {
                Remove-Item -LiteralPath $file.FullName -Force
            }
        }
    }
    if ([string]$config.OffsiteRoot) {
        foreach ($policy in @(@{ Directory = (Join-Path $config.OffsiteRoot 'daily'); Retain = 14 }, @{ Directory = (Join-Path $config.OffsiteRoot 'weekly'); Retain = 8 })) {
            if (-not (Test-Path -LiteralPath $policy.Directory -PathType Container)) { continue }
            foreach ($file in @(Get-ExpiredBackupFiles -Directory $policy.Directory -Retain $policy.Retain)) {
                Assert-ExactParent -Path $file.FullName -ExpectedParent $policy.Directory
                if ($PSCmdlet.ShouldProcess($file.FullName, "Eliminar respaldo externo excedente; retencion $($policy.Retain)")) {
                    Remove-Item -LiteralPath $file.FullName -Force
                }
            }
        }
    }
}
catch {
    Write-MaintenanceEvent -LogPath $logPath -Event 'backup_failed' -Level error -Data @{ message = $_.Exception.Message }
    throw
}
finally {
    $env:PGPASSWORD = $previousPassword
}
