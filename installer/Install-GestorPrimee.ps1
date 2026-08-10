#Requires -RunAsAdministrator
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$ReleasePath,
    [string]$ConfigPath = (Join-Path $PSScriptRoot 'install-config.psd1')
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Common.ps1')

function ConvertTo-PlainText {
    param([Parameter(Mandatory)][Security.SecureString]$Value)
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Value)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
}

function New-HexSecret {
    param([int]$Bytes = 32)
    $buffer = New-Object byte[] $Bytes
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($buffer)
    return ([BitConverter]::ToString($buffer)).Replace('-', '').ToLowerInvariant()
}

function Assert-SafeIdentifier {
    param([string]$Value, [string]$Name)
    if ($Value -notmatch '^[a-zA-Z][a-zA-Z0-9_]{0,62}$') { throw "$Name contiene caracteres no permitidos." }
}

function Assert-FileHash {
    param([string]$Path, [string]$Expected, [string]$Name)
    if ($Expected -notmatch '^[a-fA-F0-9]{64}$') { throw "Configure el SHA-256 de $Name antes de instalar." }
    $actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
    if (-not $actual.Equals($Expected, [StringComparison]::OrdinalIgnoreCase)) {
        throw "El hash SHA-256 de $Name no coincide."
    }
}
function Assert-ReleaseManifest {
    param([Parameter(Mandatory)][string]$Root)
    $manifestPath = Join-Path $Root 'release-manifest.json'
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) { throw 'ReleasePath no contiene release-manifest.json.' }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    if ([int]$manifest.schemaVersion -ne 1 -or -not $manifest.files) { throw 'release-manifest.json no es valido.' }
    $rootFull = [System.IO.Path]::GetFullPath($Root).TrimEnd('\')
    $listed = @{}
    foreach ($entry in @($manifest.files)) {
        $relative = [string]$entry.path
        if ($relative -notmatch '^[^/\\:]+(?:[/\\][^/\\:]+)*$' -or $relative -match '(^|[/\\])\.\.([/\\]|$)' -or $entry.sha256 -notmatch '^[a-fA-F0-9]{64}$') { throw "Entrada invalida en release-manifest.json: $relative" }
        $normalized = $relative.Replace('/', '\')
        $candidate = [System.IO.Path]::GetFullPath((Join-Path $rootFull $normalized))
        if (-not $candidate.StartsWith("$rootFull\", [StringComparison]::OrdinalIgnoreCase) -or -not (Test-Path -LiteralPath $candidate -PathType Leaf)) { throw "Falta el archivo protegido de release: $relative" }
        if ($listed.ContainsKey($normalized.ToLowerInvariant())) { throw "Archivo duplicado en release-manifest.json: $relative" }
        $actual = (Get-FileHash -LiteralPath $candidate -Algorithm SHA256).Hash
        if (-not $actual.Equals([string]$entry.sha256, [StringComparison]::OrdinalIgnoreCase)) { throw "Hash invalido en release: $relative" }
        $listed[$normalized.ToLowerInvariant()] = $true
    }
    if (-not $listed.ContainsKey('frontend\server.js')) { throw 'La release no contiene frontend/server.js.' }
    foreach ($file in Get-ChildItem -LiteralPath $rootFull -Recurse -File | Where-Object FullName -ne $manifestPath) {
        $relative = $file.FullName.Substring($rootFull.Length).TrimStart('\').ToLowerInvariant()
        if (-not $listed.ContainsKey($relative)) { throw "Archivo no incluido en release-manifest.json: $relative" }
    }
}

$config = Get-InstallerConfig -Path $ConfigPath
$preflightPowerShell = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
& $preflightPowerShell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'Test-InstallPrerequisites.ps1') -ConfigPath $ConfigPath
if ($LASTEXITCODE -ne 0) { throw 'El diagnostico previo no fue aprobado; no se realizaron cambios.' }

Assert-SafeIdentifier -Value $config.DatabaseName -Name 'DatabaseName'
Assert-SafeIdentifier -Value $config.DatabaseUser -Name 'DatabaseUser'
$releaseSource = (Resolve-Path -LiteralPath $ReleasePath -ErrorAction Stop).Path
Assert-ReleaseManifest -Root $releaseSource
if (-not (Test-Path -LiteralPath (Join-Path $releaseSource 'backend\requirements.txt') -PathType Leaf)) { throw 'ReleasePath no contiene backend\requirements.txt.' }
if ([string]::IsNullOrWhiteSpace([string]$config.CertificateThumbprint)) { throw 'Configure CertificateThumbprint antes de instalar.' }
$certificate = Get-Item -LiteralPath "Cert:\LocalMachine\My\$($config.CertificateThumbprint)" -ErrorAction Stop
if ($certificate.NotAfter -le (Get-Date)) { throw 'El certificado HTTPS configurado esta vencido.' }

$node = Get-ConfiguredExecutable -ConfiguredPath ([string]$config.NodePath) -CommandName 'node.exe'
$python = Get-ConfiguredExecutable -ConfiguredPath ([string]$config.PythonPath) -CommandName 'python.exe'
$winsw = Get-ConfiguredExecutable -ConfiguredPath ([string]$config.WinSWPath) -CommandName 'WinSW.exe'
if (-not $python -or -not $node -or -not $winsw) { throw 'Python, Node.js y WinSW deben estar disponibles.' }

Assert-FileHash -Path $winsw -Expected ([string]$config.WinSWSha256) -Name 'WinSW'
$directories = @(
    $config.InstallRoot,
    (Join-Path $config.InstallRoot 'app\releases'),
    (Join-Path $config.InstallRoot 'config'),
    $config.PostgresData,
    $config.BackupRoot,
    (Join-Path $config.InstallRoot 'logs\backend'),
    (Join-Path $config.InstallRoot 'logs\frontend'),
    (Join-Path $config.InstallRoot 'logs\maintenance'),
    (Join-Path $config.InstallRoot 'iis'),
    (Join-Path $config.InstallRoot 'installer')
)
foreach ($directory in $directories) { New-Item -ItemType Directory -Path $directory -Force | Out-Null }
Copy-Item -Path (Join-Path $PSScriptRoot '*') -Destination (Join-Path $config.InstallRoot 'installer') -Recurse -Force
$installedInstaller = Join-Path $config.InstallRoot 'installer'
$installedConfig = Join-Path $installedInstaller 'install-config.psd1'

$pgFallback = @("$env:ProgramFiles\PostgreSQL\$($config.PostgresMajor)\bin\psql.exe")
$psql = Get-ConfiguredExecutable -ConfiguredPath '' -CommandName 'psql.exe' -FallbackPaths $pgFallback
$superPasswordSecure = Read-Host 'Contrasena del superusuario postgres (no se mostrara)' -AsSecureString
$superPassword = ConvertTo-PlainText $superPasswordSecure
if ($superPassword.Length -lt 14) { throw 'La contrasena de PostgreSQL debe tener al menos 14 caracteres.' }

if (-not $psql) {
    $pgInstaller = [string]$config.PostgresInstallerPath
    if (-not $pgInstaller -or -not (Test-Path -LiteralPath $pgInstaller -PathType Leaf)) { throw 'PostgreSQL no esta instalado y PostgresInstallerPath no apunta a un instalador.' }
    $pgPrefix = Join-Path $env:ProgramFiles "PostgreSQL\$($config.PostgresMajor)"
    Assert-FileHash -Path $pgInstaller -Expected ([string]$config.PostgresInstallerSha256) -Name 'PostgreSQL'
    $arguments = @(
        '--mode', 'unattended', '--unattendedmodeui', 'minimal',
        '--prefix', $pgPrefix, '--datadir', $config.PostgresData,
        '--serverport', [string]$config.PostgresPort,
        '--servicename', $config.PostgresServiceName,
        '--superaccount', 'postgres', '--superpassword', $superPassword,
        '--servicepassword', $superPassword,
        '--enable-components', 'server,commandlinetools'
    )
    $process = Start-Process -FilePath $pgInstaller -ArgumentList $arguments -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw "El instalador PostgreSQL termino con codigo $($process.ExitCode)." }
    $psql = Get-ConfiguredExecutable -ConfiguredPath '' -CommandName 'psql.exe' -FallbackPaths $pgFallback
    if (-not $psql) { throw 'PostgreSQL termino de instalar, pero psql.exe no fue encontrado.' }
}

$envPath = Join-Path $config.InstallRoot 'config\production.env'
$environment = @{}
if (Test-Path -LiteralPath $envPath -PathType Leaf) {
    $environment = Read-EnvFile -Path $envPath
}
$existingUrl = if ($environment.ContainsKey('DATABASE_URL')) { [string]$environment.DATABASE_URL } else { '' }
$databaseMatch = [regex]::Match($existingUrl, '^postgresql\+asyncpg://(?<user>[^:]+):(?<password>[^@]+)@127\.0\.0\.1:(?<port>\d+)/(?<database>[^?]+)')
$reuseDatabasePassword = $databaseMatch.Success -and $databaseMatch.Groups['user'].Value -eq $config.DatabaseUser -and $databaseMatch.Groups['database'].Value -eq $config.DatabaseName
$appPassword = if ($reuseDatabasePassword) { [uri]::UnescapeDataString($databaseMatch.Groups['password'].Value) } else { New-HexSecret -Bytes 24 }
$secretKey = if ($environment.ContainsKey('SECRET_KEY') -and ([string]$environment.SECRET_KEY).Length -ge 32) { [string]$environment.SECRET_KEY } else { New-HexSecret -Bytes 32 }
$escapedPassword = $appPassword.Replace("'", "''")
$existingRoleAction = if ($reuseDatabasePassword) { 'NULL;' } else { "ALTER ROLE $($config.DatabaseUser) LOGIN PASSWORD '$escapedPassword';" }
$previousPgPassword = $env:PGPASSWORD
try {
    $env:PGPASSWORD = $superPassword
    $roleSql = @"
DO `$body`$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '$($config.DatabaseUser)') THEN
        CREATE ROLE $($config.DatabaseUser) LOGIN PASSWORD '$escapedPassword';
    ELSE
        $existingRoleAction
    END IF;
END
`$body`$;
"@
    $roleSql | & $psql --host 127.0.0.1 --port $config.PostgresPort --username postgres --dbname postgres --set ON_ERROR_STOP=1
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear o actualizar el rol PostgreSQL.' }
    $databaseSql = "SELECT 'CREATE DATABASE $($config.DatabaseName) OWNER $($config.DatabaseUser)' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '$($config.DatabaseName)')\gexec"
    $databaseSql | & $psql --host 127.0.0.1 --port $config.PostgresPort --username postgres --dbname postgres --set ON_ERROR_STOP=1
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear la base PostgreSQL.' }
    "ALTER SYSTEM SET listen_addresses = '127.0.0.1';" | & $psql --host 127.0.0.1 --port $config.PostgresPort --username postgres --dbname postgres --set ON_ERROR_STOP=1
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo limitar PostgreSQL a loopback.' }

}
finally {
    $env:PGPASSWORD = $previousPgPassword
    $superPassword = $null
}
$postgresService = Get-Service -Name $config.PostgresServiceName -ErrorAction Stop
Restart-Service -InputObject $postgresService -Force
$firewallPorts = @([int]$config.PostgresPort, [int]$config.BackendPort, [int]$config.FrontendPort)
foreach ($port in $firewallPorts) {
    $ruleName = "DataExpress-GestorPrimee-Block-$port"
    if (-not (Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -Name $ruleName -DisplayName "Data Express Gestor PRIMEE - bloquear TCP $port" -Direction Inbound -Action Block -Protocol TCP -LocalPort $port -Profile Any | Out-Null
    } else {
        Set-NetFirewallRule -Name $ruleName -Enabled True -Action Block | Out-Null
    }
}


$origin = "https://$($config.PublicHost)"
$allowedKeys = @(
    'PROJECT_NAME', 'API_VERSION', 'ACCESS_TOKEN_EXPIRE_MINUTES',
    'REFRESH_TOKEN_EXPIRE_DAYS', 'ALGORITHM', 'COOKIE_SAMESITE',
    'LOGIN_MAX_FAILS', 'LOGIN_FAIL_WINDOW_SEC', 'SQLSERVER_SERVER',
    'SQLSERVER_PORT', 'SQLSERVER_USER', 'SQLSERVER_PASSWORD',
    'SQLSERVER_DRIVER', 'SQLSERVER_BACKUP_PATH', 'SQLSERVER_BACKUP_STRIPES',
    'SQLSERVER_BACKUP_BUFFERCOUNT', 'SQLSERVER_BACKUP_VERIFY'
)
$preserved = @{}
foreach ($key in $allowedKeys) {
    if ($environment.ContainsKey($key)) { $preserved[$key] = [string]$environment[$key] }
}
$environment = $preserved
$environment['APP_ENV'] = 'production'
$environment['DEBUG'] = 'false'
$environment['APP_ORIGIN'] = $origin
$environment['SECRET_KEY'] = $secretKey
$environment['COOKIE_SECURE'] = 'true'
$environment['COOKIE_SAMESITE'] = if ($environment.ContainsKey('COOKIE_SAMESITE')) { $environment['COOKIE_SAMESITE'] } else { 'lax' }
$environment['LOGIN_MAX_FAILS'] = if ($environment.ContainsKey('LOGIN_MAX_FAILS')) { $environment['LOGIN_MAX_FAILS'] } else { '5' }
$environment['LOGIN_FAIL_WINDOW_SEC'] = if ($environment.ContainsKey('LOGIN_FAIL_WINDOW_SEC')) { $environment['LOGIN_FAIL_WINDOW_SEC'] } else { '300' }
$environment['DATABASE_URL'] = "postgresql+asyncpg://$($config.DatabaseUser):$appPassword@127.0.0.1:$($config.PostgresPort)/$($config.DatabaseName)"
$environment['ALLOWED_ORIGINS'] = "[`"$origin`"]"
$environment['CLEANUP_TRASH_PATH'] = Join-Path $config.InstallRoot 'data\cleanup-trash'
$fmRoots = @($config.FileManagerAllowedRoots | ForEach-Object { [System.IO.Path]::GetFullPath([string]$_) })
$environment['FM_ALLOWED_ROOTS'] = $fmRoots -join ';'
foreach ($root in $fmRoots) { New-Item -ItemType Directory -Path $root -Force | Out-Null }
New-Item -ItemType Directory -Path $environment['CLEANUP_TRASH_PATH'] -Force | Out-Null
$envLines = @($environment.GetEnumerator() | Sort-Object Key | ForEach-Object { "$($_.Key)=$($_.Value)" })
Set-Content -LiteralPath $envPath -Value $envLines -Encoding ascii
& icacls.exe $envPath /inheritance:r /grant:r '*S-1-5-18:(R)' '*S-1-5-32-544:(F)' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'No se pudieron restringir los permisos de production.env.' }

$releaseId = Get-Date -Format 'yyyyMMdd-HHmmss'
$releaseRoot = Join-Path $config.InstallRoot "app\releases\$releaseId"
$backendTarget = Join-Path $releaseRoot 'backend'
$frontendTarget = Join-Path $releaseRoot 'frontend'
New-Item -ItemType Directory -Path $backendTarget, $frontendTarget -Force | Out-Null
& robocopy.exe (Join-Path $releaseSource 'backend') $backendTarget /E /XD '.venv' '__pycache__' '.pytest_cache' 'tests' 'tests_prod' /XF 'infra_platform.db' 'access_sessions.log' /NFL /NDL /NJH /NJS /NP
$backendCopyCode = $LASTEXITCODE
if ($backendCopyCode -gt 7) { throw "No se pudo copiar el backend; robocopy termino con codigo $backendCopyCode." }
& robocopy.exe (Join-Path $releaseSource 'frontend') $frontendTarget /E /NFL /NDL /NJH /NJS /NP
$frontendCopyCode = $LASTEXITCODE
if ($frontendCopyCode -gt 7) { throw "No se pudo copiar el frontend; robocopy termino con codigo $frontendCopyCode." }

& $python -m venv (Join-Path $backendTarget '.venv')
if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear el entorno Python.' }
$releasePython = Join-Path $backendTarget '.venv\Scripts\python.exe'
& $releasePython -m pip install --disable-pip-version-check --requirement (Join-Path $backendTarget 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'No se pudieron instalar las dependencias Python.' }

if (-not (Test-Path -LiteralPath (Join-Path $frontendTarget 'server.js') -PathType Leaf)) { throw 'La release no contiene frontend\server.js.' }

Set-ProcessEnvironmentFromFile -Path $envPath | Out-Null
Push-Location $backendTarget
try {
    & (Join-Path $installedInstaller 'Backup-GestorPrimee.ps1') -ConfigPath $installedConfig
    & $releasePython -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw 'Alembic no pudo actualizar la base.' }
    $adminEmail = Read-Host 'Correo del administrador inicial de Data Express'
    $adminPasswordSecure = Read-Host 'Contrasena inicial (minimo 14 caracteres; no se mostrara)' -AsSecureString
    $adminPassword = ConvertTo-PlainText $adminPasswordSecure
    $env:BOOTSTRAP_ADMIN_EMAIL = $adminEmail
    $env:BOOTSTRAP_ADMIN_PASSWORD = $adminPassword
    & $releasePython scripts\seed_admin.py
    if ($LASTEXITCODE -ne 0) { throw 'El bootstrap de Data Express fallo.' }
}
finally {
    Remove-Item Env:BOOTSTRAP_ADMIN_EMAIL -ErrorAction SilentlyContinue
    Remove-Item Env:BOOTSTRAP_ADMIN_PASSWORD -ErrorAction SilentlyContinue
    $adminPassword = $null
    Pop-Location
}

& (Join-Path $installedInstaller 'Smoke-TestRelease.ps1') -BackendRoot $backendTarget -FrontendRoot $frontendTarget -PythonPath $releasePython -NodePath $node -LogRoot (Join-Path $config.InstallRoot 'logs\maintenance') -BackendPort ($config.BackendPort + 10000) -FrontendPort ($config.FrontendPort + 10000)

$current = Join-Path $config.InstallRoot 'app\current'
if (Test-Path -LiteralPath $current) {
    $item = Get-Item -LiteralPath $current -Force
    if ($item.LinkType -eq 'Junction') { Remove-Item -LiteralPath $current -Force }
    else { Move-Item -LiteralPath $current -Destination "$current.previous-$releaseId" }
}
New-Item -ItemType Junction -Path $current -Target $releaseRoot | Out-Null

$serviceRoot = Join-Path $config.InstallRoot 'services'
New-Item -ItemType Directory -Path $serviceRoot -Force | Out-Null
$serviceDefinitions = @(
    @{ Name = 'DataExpressGestorBackend'; Template = 'backend-service.xml.template'; Port = $config.BackendPort },
    @{ Name = 'DataExpressGestorFrontend'; Template = 'frontend-service.xml.template'; Port = $config.FrontendPort }
)
foreach ($definition in $serviceDefinitions) {
    $exe = Join-Path $serviceRoot "$($definition.Name).exe"
    $xml = Join-Path $serviceRoot "$($definition.Name).xml"
    Copy-Item -LiteralPath $winsw -Destination $exe -Force
    $template = Get-Content -LiteralPath (Join-Path $installedInstaller "services\$($definition.Template)") -Raw
    $rendered = $template.Replace('{{INSTALL_ROOT}}', $config.InstallRoot).Replace('{{BACKEND_PORT}}', [string]$config.BackendPort).Replace('{{FRONTEND_PORT}}', [string]$config.FrontendPort).Replace('{{NODE_PATH}}', $node).Replace('{{FRONTEND_HEAP_MB}}', [string]$config.FrontendHeapMb)
    Set-Content -LiteralPath $xml -Value $rendered -Encoding utf8
    if (Get-Service -Name $definition.Name -ErrorAction SilentlyContinue) {
        & $exe stop | Out-Null
    } else {
        & $exe install | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "No se pudo instalar el servicio $($definition.Name)." }
    }
    & $exe start | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "No se pudo iniciar el servicio $($definition.Name)." }
}

Import-Module WebAdministration
$siteRoot = Join-Path $config.InstallRoot 'iis'
$webConfig = (Get-Content -LiteralPath (Join-Path $installedInstaller 'iis\web.config.template') -Raw).Replace('{{BACKEND_PORT}}', [string]$config.BackendPort).Replace('{{FRONTEND_PORT}}', [string]$config.FrontendPort)
Set-Content -LiteralPath (Join-Path $siteRoot 'web.config') -Value $webConfig -Encoding utf8
Set-WebConfigurationProperty -PSPath 'MACHINE/WEBROOT/APPHOST' -Filter 'system.webServer/proxy' -Name enabled -Value $true
if (-not (Test-Path "IIS:\AppPools\$($config.IisAppPoolName)")) { New-WebAppPool -Name $config.IisAppPoolName | Out-Null }
Set-ItemProperty "IIS:\AppPools\$($config.IisAppPoolName)" -Name managedRuntimeVersion -Value ''
if (-not (Get-Website -Name $config.IisSiteName -ErrorAction SilentlyContinue)) {
    New-Website -Name $config.IisSiteName -PhysicalPath $siteRoot -ApplicationPool $config.IisAppPoolName -Port 80 -HostHeader $config.PublicHost | Out-Null
} else {
    Set-ItemProperty "IIS:\Sites\$($config.IisSiteName)" -Name physicalPath -Value $siteRoot
    Set-ItemProperty "IIS:\Sites\$($config.IisSiteName)" -Name applicationPool -Value $config.IisAppPoolName
}
$httpsBinding = Get-WebBinding -Name $config.IisSiteName -Protocol https -ErrorAction SilentlyContinue | Where-Object bindingInformation -eq "*:$($config.IisHttpsPort):$($config.PublicHost)"
if (-not $httpsBinding) { New-WebBinding -Name $config.IisSiteName -Protocol https -Port $config.IisHttpsPort -HostHeader $config.PublicHost -SslFlags 1 | Out-Null }
$sslPath = "IIS:\SslBindings\0.0.0.0!$($config.IisHttpsPort)!$($config.PublicHost)"
if (Test-Path $sslPath) { Remove-Item $sslPath -Force }
New-Item $sslPath -Thumbprint $certificate.Thumbprint -SSLFlags 1 | Out-Null

& (Join-Path $installedInstaller 'Register-MaintenanceTasks.ps1') -ConfigPath $installedConfig
$ready = $false
for ($attempt = 1; $attempt -le 12; $attempt++) {
    try {
        $response = Invoke-RestMethod -Uri "http://127.0.0.1:$($config.BackendPort)/health/ready" -TimeoutSec 5
        if ($response.status -eq 'ready') { $ready = $true; break }
    } catch { Start-Sleep -Seconds 5 }
}
if (-not $ready) { throw 'El backend no aprobo /health/ready despues del despliegue.' }
Write-Host "Instalacion terminada. Portal: $origin" -ForegroundColor Green
if (-not [string]$config.OffsiteRoot) { Write-Warning 'Configure OffsiteRoot cuando disponga de otra unidad o carpeta de red.' }
