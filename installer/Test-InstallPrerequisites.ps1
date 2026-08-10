[CmdletBinding()]
param(
    [string]$ConfigPath = (Join-Path $PSScriptRoot 'install-config.psd1')
)

. (Join-Path $PSScriptRoot 'Common.ps1')

$config = Get-InstallerConfig -Path $ConfigPath
$results = [System.Collections.Generic.List[object]]::new()

function Add-Check {
    param([string]$Name, [bool]$Passed, [string]$Detail, [bool]$Required = $true)
    $results.Add([pscustomobject]@{
        Check = $Name
        Status = if ($Passed) { 'OK' } elseif ($Required) { 'BLOCK' } else { 'WARN' }
        Detail = $Detail
    })
}

Add-Check 'Windows' ($env:OS -eq 'Windows_NT') 'Se requiere Windows 11.'
Add-Check 'Administrador' (Test-IsAdministrator) 'La instalacion final debe ejecutarse en PowerShell como administrador.' $false

$driveRoot = [System.IO.Path]::GetPathRoot([string]$config.InstallRoot)
$driveExists = Test-Path -LiteralPath $driveRoot
Add-Check 'Unidad de datos' $driveExists "Ruta configurada: $driveRoot"
if ($driveExists) {
    $drive = Get-PSDrive -Name $driveRoot.Substring(0, 1) -ErrorAction SilentlyContinue
    $freeGb = if ($drive) { [math]::Round($drive.Free / 1GB, 2) } else { 0 }
    Add-Check 'Espacio libre' ($freeGb -ge 10) "$freeGb GB libres; minimo recomendado: 10 GB."
}

foreach ($port in @([int]$config.PostgresPort, [int]$config.BackendPort, [int]$config.FrontendPort)) {
    $listener = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
    $serviceName = if ($port -eq [int]$config.PostgresPort) {
        [string]$config.PostgresServiceName
    } elseif ($port -eq [int]$config.BackendPort) {
        'DataExpressGestorBackend'
    } else {
        'DataExpressGestorFrontend'
    }
    $ownedService = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
    $available = (-not $listener) -or [bool]$ownedService
    $detail = if (-not $listener) { 'Disponible.' } elseif ($ownedService) { "En uso por el servicio esperado: $serviceName." } else { 'Ya existe un proceso ajeno escuchando.' }
    Add-Check "Puerto $port" $available $detail
}

$iisConfigPath = Join-Path $env:windir 'System32\inetsrv\config\applicationHost.config'
Add-Check 'IIS' (Test-Path -LiteralPath $iisConfigPath) 'IIS-WebServerRole debe estar habilitado.'
$rewritePath = Join-Path $env:windir 'System32\inetsrv\rewrite.dll'
Add-Check 'IIS URL Rewrite' (Test-Path -LiteralPath $rewritePath) 'Instale URL Rewrite 2.1 para IIS.'
$arrPath = Join-Path $env:ProgramFiles 'IIS\Application Request Routing\requestRouter.dll'
Add-Check 'IIS ARR' (Test-Path -LiteralPath $arrPath) 'Instale Application Request Routing y habilite proxy.'

$pgFallback = @("$env:ProgramFiles\PostgreSQL\$($config.PostgresMajor)\bin\psql.exe")
$psql = Get-ConfiguredExecutable -ConfiguredPath '' -CommandName 'psql.exe' -FallbackPaths $pgFallback
$pgInstaller = [string]$config.PostgresInstallerPath
Add-Check 'PostgreSQL' ([bool]$psql -or ($pgInstaller -and (Test-Path -LiteralPath $pgInstaller -PathType Leaf))) 'Debe existir psql o un instalador local de PostgreSQL.'

if (-not $psql -and $pgInstaller -and (Test-Path -LiteralPath $pgInstaller -PathType Leaf)) {
    $expectedHash = [string]$config.PostgresInstallerSha256
    $hashValid = $expectedHash -match '^[a-fA-F0-9]{64}$' -and (Get-FileHash -LiteralPath $pgInstaller -Algorithm SHA256).Hash -eq $expectedHash
    Add-Check 'Hash PostgreSQL' $hashValid 'Configure PostgresInstallerSha256 con el hash oficial del instalador.'
}
$winsw = Get-ConfiguredExecutable -ConfiguredPath ([string]$config.WinSWPath) -CommandName 'WinSW.exe'
Add-Check 'WinSW' ([bool]$winsw) 'Configure WinSWPath con el ejecutable WinSW x64.'
$python = Get-ConfiguredExecutable -ConfiguredPath ([string]$config.PythonPath) -CommandName 'python.exe'
if ($winsw) {
    $expectedHash = [string]$config.WinSWSha256
    $hashValid = $expectedHash -match '^[a-fA-F0-9]{64}$' -and (Get-FileHash -LiteralPath $winsw -Algorithm SHA256).Hash -eq $expectedHash
    Add-Check 'Hash WinSW' $hashValid 'Configure WinSWSha256 con el hash oficial del ejecutable.'
}
Add-Check 'Python' ([bool]$python) 'Configure PythonPath o agregue Python al PATH.'
$node = Get-ConfiguredExecutable -ConfiguredPath ([string]$config.NodePath) -CommandName 'node.exe'
Add-Check 'Node.js' ([bool]$node) 'Configure NodePath o agregue Node.js al PATH.'
if ($node) {
    $nodeVersionText = (& $node --version).Trim().TrimStart('v')
    $nodeVersion = [version]$nodeVersionText
    Add-Check 'Node.js compatible' ($nodeVersion -ge [version]'20.9.0') "Detectado: $nodeVersionText; Next.js requiere 20.9.0 o posterior."
}

$thumbprint = [string]$config.CertificateThumbprint
$certificateExists = $thumbprint -and (Test-Path -LiteralPath "Cert:\LocalMachine\My\$thumbprint")
Add-Check 'Certificado HTTPS' ([bool]$certificateExists) 'Configure CertificateThumbprint con un certificado vigente del host publico.'
$results | Format-Table -AutoSize -Wrap
$blocks = @($results | Where-Object Status -eq 'BLOCK')
if (-not [string]$config.OffsiteRoot) {
    Write-Warning 'OffsiteRoot esta vacio: los respaldos en D: no protegen contra perdida fisica de esa unidad.'
}
if ($blocks.Count -gt 0) {
    Write-Error "Hay $($blocks.Count) requisito(s) bloqueante(s). Corrijalos antes de instalar."
    exit 1
}
Write-Host 'Diagnostico aprobado. Puede ejecutar el instalador final en una consola elevada.' -ForegroundColor Green
