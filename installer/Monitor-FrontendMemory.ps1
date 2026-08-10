#Requires -RunAsAdministrator
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$InstallRoot,
    [int]$WarnMb = 600,
    [int]$RestartMb = 900,
    [ValidateRange(1, 20)][int]$ConsecutiveSamples = 3,
    [string]$ServiceName = 'DataExpressGestorFrontend'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $InstallRoot 'installer\Common.ps1')

$logPath = Join-Path $InstallRoot 'logs\maintenance\frontend-memory.jsonl'
$statePath = Join-Path $InstallRoot 'logs\maintenance\frontend-memory-state.json'
$service = Get-CimInstance Win32_Service -Filter "Name='$ServiceName'" -ErrorAction SilentlyContinue
if (-not $service -or [int]$service.ProcessId -eq 0) {
    Write-MaintenanceEvent -LogPath $logPath -Event 'frontend_service_not_running' -Level 'warning' -Data @{ service = $ServiceName }
    exit 0
}

$processes = @(Get-CimInstance Win32_Process -ErrorAction Stop)
$byParent = @{}
foreach ($process in $processes) {
    $parent = [int]$process.ParentProcessId
    if (-not $byParent.ContainsKey($parent)) { $byParent[$parent] = @() }
    $byParent[$parent] += $process
}
$descendants = @()
$queue = New-Object System.Collections.Queue
$queue.Enqueue([int]$service.ProcessId)
$seen = @{}
while ($queue.Count -gt 0) {
    $parentId = [int]$queue.Dequeue()
    if ($seen.ContainsKey($parentId)) { continue }
    $seen[$parentId] = $true
    foreach ($child in @($byParent[$parentId])) {
        $descendants += $child
        $queue.Enqueue([int]$child.ProcessId)
    }
}

$nodeProcesses = @($descendants | Where-Object { $_.Name -ieq 'node.exe' -or $_.Name -ieq 'node' })
$workingSet = [int64]0
foreach ($nodeProcess in $nodeProcesses) { $workingSet += [int64]$nodeProcess.WorkingSetSize }
$memoryMb = [math]::Round($workingSet / 1MB, 1)
$state = @{ consecutive = 0; restartCount = 0; restartDate = (Get-Date).ToString('yyyy-MM-dd') }
if (Test-Path -LiteralPath $statePath -PathType Leaf) {
    try {
        $loaded = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
        $state = @{ consecutive = [int]$loaded.consecutive; restartCount = [int]$loaded.restartCount; restartDate = [string]$loaded.restartDate }
    } catch { }
}
if ([string]$state.restartDate -ne (Get-Date).ToString('yyyy-MM-dd')) { $state.restartCount = 0; $state.restartDate = (Get-Date).ToString('yyyy-MM-dd') }

$tooMany = $nodeProcesses.Count -gt 2
$overRestart = $memoryMb -ge $RestartMb
$overWarn = $memoryMb -ge $WarnMb
if ($overRestart -or $tooMany) { $state.consecutive = [int]$state.consecutive + 1 } else { $state.consecutive = 0 }
$level = if ($overRestart -or $tooMany) { 'warning' } elseif ($overWarn) { 'warning' } else { 'info' }
Write-MaintenanceEvent -LogPath $logPath -Event 'frontend_memory_sample' -Level $level -Data @{
    service = $ServiceName; nodeProcesses = $nodeProcesses.Count; memoryMb = $memoryMb; warnMb = $WarnMb; restartMb = $RestartMb; consecutive = $state.consecutive
}

if (($overRestart -or $tooMany) -and [int]$state.consecutive -ge $ConsecutiveSamples) {
    if ([int]$state.restartCount -lt 2) {
        Write-MaintenanceEvent -LogPath $logPath -Event 'frontend_memory_restart' -Level 'warning' -Data @{ memoryMb = $memoryMb; nodeProcesses = $nodeProcesses.Count; attempt = ([int]$state.restartCount + 1) }
        try {
            Restart-Service -Name $ServiceName -Force -ErrorAction Stop
        }
        catch {
            Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
            Start-Service -Name $ServiceName -ErrorAction Stop
        }
        $state.restartCount = [int]$state.restartCount + 1
        $state.consecutive = 0
    }
    else {
        Write-MaintenanceEvent -LogPath $logPath -Event 'frontend_memory_restart_suppressed' -Level 'error' -Data @{ memoryMb = $memoryMb; nodeProcesses = $nodeProcesses.Count; reason = 'daily_restart_limit' }
    }
}
$state | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $statePath -Encoding utf8
