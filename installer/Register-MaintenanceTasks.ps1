#Requires -RunAsAdministrator
[CmdletBinding()]
param([string]$ConfigPath = (Join-Path $PSScriptRoot 'install-config.psd1'))

. (Join-Path $PSScriptRoot 'Common.ps1')
$config = Get-InstallerConfig -Path $ConfigPath
$powershell = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$backupScript = Join-Path $config.InstallRoot 'installer\Backup-GestorPrimee.ps1'
$arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$backupScript`" -ConfigPath `"$(Join-Path $config.InstallRoot 'installer\install-config.psd1')`""
$action = New-ScheduledTaskAction -Execute $powershell -Argument $arguments
$trigger = New-ScheduledTaskTrigger -Daily -At '02:00'
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 2) -RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 10)
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
Register-ScheduledTask -TaskName 'DataExpress-GestorPrimee-PostgreSQL-Backup' -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'Respaldo diario de la base interna de Gestor PRIMEE.' -Force | Out-Null
Write-Host 'Tarea diaria de respaldo registrada o actualizada.' -ForegroundColor Green

$monitorScript = Join-Path $config.InstallRoot 'installer\Monitor-FrontendMemory.ps1'
$monitorArguments = "-NoProfile -ExecutionPolicy Bypass -File `"$monitorScript`" -InstallRoot `"$($config.InstallRoot)`" -WarnMb $($config.FrontendMemoryWarnMb) -RestartMb $($config.FrontendMemoryRestartMb) -ConsecutiveSamples $($config.FrontendMemorySamples)"
$monitorAction = New-ScheduledTaskAction -Execute $powershell -Argument $monitorArguments
$monitorTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1)
$monitorTrigger.RepetitionInterval = New-TimeSpan -Minutes 1
$monitorTrigger.RepetitionDuration = New-TimeSpan -Days 3650
$monitorSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 2)
Register-ScheduledTask -TaskName 'DataExpress-GestorPrimee-Frontend-Memory' -Action $monitorAction -Trigger $monitorTrigger -Settings $monitorSettings -Principal $principal -Description 'Supervisa el consumo del unico proceso frontend de Data Express.' -Force | Out-Null
Write-Host 'Monitor de memoria frontend registrado o actualizado.' -ForegroundColor Green
