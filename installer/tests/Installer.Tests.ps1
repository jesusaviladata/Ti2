$installerRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $installerRoot 'Common.ps1')

Describe 'Installer Data Express' {
    It 'analiza todos los scripts sin errores de sintaxis' {
        $allErrors = @()
        Get-ChildItem -LiteralPath $installerRoot -Recurse -Filter '*.ps1' | ForEach-Object {
            $tokens = $null
            $errors = $null
            [System.Management.Automation.Language.Parser]::ParseFile($_.FullName, [ref]$tokens, [ref]$errors) | Out-Null
            $allErrors += @($errors)
        }
        $allErrors.Count | Should Be 0
    }

    It 'conserva los archivos mas recientes segun la retencion' {
        $backupDir = Join-Path $TestDrive 'daily'
        New-Item -ItemType Directory -Path $backupDir | Out-Null
        1..5 | ForEach-Object {
            $file = New-Item -ItemType File -Path (Join-Path $backupDir "backup-$_.dump")
            $file.LastWriteTime = (Get-Date).AddDays(-$_)
        }
        $expired = @(Get-ExpiredBackupFiles -Directory $backupDir -Retain 3)
        $expired.Count | Should Be 2
        $expired[0].Name | Should Be 'backup-4.dump'
        $expired[1].Name | Should Be 'backup-5.dump'
    }

    It 'ignora archivos que no son dump al calcular retencion' {
        $backupDir = Join-Path $TestDrive 'weekly'
        New-Item -ItemType Directory -Path $backupDir | Out-Null
        New-Item -ItemType File -Path (Join-Path $backupDir 'one.dump') | Out-Null
        New-Item -ItemType File -Path (Join-Path $backupDir 'notes.txt') | Out-Null
        @(Get-ExpiredBackupFiles -Directory $backupDir -Retain 1).Count | Should Be 0
    }

    It 'rechaza operaciones cuyo padre no es la carpeta exacta' {
        $allowed = Join-Path $TestDrive 'allowed'
        $outside = Join-Path $TestDrive 'outside\file.dump'
        { Assert-ExactParent -Path $outside -ExpectedParent $allowed } | Should Throw
    }

    It 'mantiene validas las plantillas XML' {
        $templates = Get-ChildItem -LiteralPath $installerRoot -Recurse -File | Where-Object {
            $_.Name -like '*.xml.template' -or $_.Name -eq 'web.config.template'
        }
        $templates.Count | Should Be 3
        foreach ($template in $templates) {
            { [xml](Get-Content -LiteralPath $template.FullName -Raw) } | Should Not Throw
        }
    }

    It 'solo publica procesos internos por loopback' {
        $backend = Get-Content -LiteralPath (Join-Path $installerRoot 'services\Start-Backend.ps1') -Raw
        $frontend = Get-Content -LiteralPath (Join-Path $installerRoot 'services\Start-Frontend.ps1') -Raw
        $proxy = Get-Content -LiteralPath (Join-Path $installerRoot 'iis\web.config.template') -Raw
        $backend | Should Match '127\.0\.0\.1'
        $frontend | Should Match '127\.0\.0\.1'
        $proxy | Should Match '127\.0\.0\.1'
        $backend | Should Not Match '--host 0\.0\.0\.0'
    }

    It 'exige una release frontend precompilada y no construye Next.js en produccion' {
        $installer = Get-Content -LiteralPath (Join-Path $installerRoot 'Install-GestorPrimee.ps1') -Raw
        $installer | Should Match 'frontend\\server\.js'
        $installer | Should Match 'release-manifest\.json'
        $installer | Should Not Match '(?i)npm\s+ci'
        $installer | Should Not Match '(?i)npm\s+run\s+build'
        $installer | Should Not Match '(?i)next\s+dev'
    }

    It 'genera el paquete fuera del servidor con hashes verificables' {
        $builderPath = Join-Path $installerRoot 'Build-Release.ps1'
        Test-Path -LiteralPath $builderPath -PathType Leaf | Should Be $true
        $builder = Get-Content -LiteralPath $builderPath -Raw
        $builder | Should Match 'npm\s+run\s+type-check'
        $builder | Should Match 'npm\s+run\s+build'
        $builder | Should Match 'release-manifest\.json'
        $builder | Should Match 'Get-FileHash'
    }

    It 'limita el heap del unico runtime frontend' {
        $frontend = Get-Content -LiteralPath (Join-Path $installerRoot 'services\Start-Frontend.ps1') -Raw
        $template = Get-Content -LiteralPath (Join-Path $installerRoot 'services\frontend-service.xml.template') -Raw
        $frontend | Should Match 'NODE_OPTIONS'
        $frontend | Should Match 'max-old-space-size'
        $frontend | Should Match 'MaxOldSpaceSizeMb'
        $template | Should Match 'FRONTEND_HEAP_MB'
    }

    It 'supervisa solo descendientes del servicio y contiene reincidencias' {
        $monitorPath = Join-Path $installerRoot 'Monitor-FrontendMemory.ps1'
        Test-Path -LiteralPath $monitorPath -PathType Leaf | Should Be $true
        $monitor = Get-Content -LiteralPath $monitorPath -Raw
        $monitor | Should Match 'DataExpressGestorFrontend'
        $monitor | Should Match 'ParentProcessId'
        $monitor | Should Match 'WorkingSetSize'
        $monitor | Should Match 'Restart-Service'
        $monitor | Should Match 'Stop-Service'
        $monitor | Should Not Match 'Get-Process\s+node\s*\|\s*Stop-Process'
    }

    It 'registra el monitor de memoria cada minuto' {
        $maintenance = Get-Content -LiteralPath (Join-Path $installerRoot 'Register-MaintenanceTasks.ps1') -Raw
        $maintenance | Should Match 'DataExpress-GestorPrimee-Frontend-Memory'
        $maintenance | Should Match 'Monitor-FrontendMemory\.ps1'
        $maintenance | Should Match 'New-TimeSpan -Minutes 1'
    }
}
