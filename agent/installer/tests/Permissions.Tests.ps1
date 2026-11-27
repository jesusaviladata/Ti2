$installerRoot = Join-Path $PSScriptRoot ".."
$agentRoot = Join-Path $PSScriptRoot "..\.."

. (Join-Path $installerRoot "Grant-BackupPermissions.ps1")

Describe "Grant-BackupPermissions.ps1" {
    It "resuelve NETWORK SERVICE por SID, sin depender del idioma de Windows" {
        $name = Get-NetworkServiceAccountName
        $name | Should Not BeNullOrEmpty
        $sid = (New-Object System.Security.Principal.NTAccount($name)).Translate([System.Security.Principal.SecurityIdentifier]).Value
        $sid | Should Be "S-1-5-20"
    }

    It "traduce la instancia predeterminada y una instancia con nombre" {
        $default = Get-SqlServerTarget -Instance "MSSQLSERVER"
        $default.Server | Should Be "localhost"
        $default.Service | Should Be "MSSQLSERVER"

        $named = Get-SqlServerTarget -Instance "SQLEXPRESS"
        $named.Server | Should Be "localhost\SQLEXPRESS"
        $named.Service | Should Be 'MSSQL$SQLEXPRESS'
    }

    It "concede Modificar heredado y pasa los SID con asterisco" {
        $bySid = Get-IcaclsGrantArguments -Folder "D:\Respaldos" -Account "S-1-5-20"
        $bySid[0] | Should Be "D:\Respaldos"
        $bySid[1] | Should Be "/grant"
        $bySid[2] | Should Be "*S-1-5-20:(OI)(CI)M"

        $byName = Get-IcaclsGrantArguments -Folder "D:\Respaldos" -Account "NT Service\MSSQLSERVER"
        $byName[2] | Should Be "NT Service\MSSQLSERVER:(OI)(CI)M"
    }

    It "detecta rutas de red" {
        Test-IsUncPath "\\archivos\respaldos" | Should Be $true
        Test-IsUncPath "D:\Respaldos" | Should Be $false
    }

    It "el lote de servidor es idempotente y no interpola el nombre del login" {
        $sql = Get-ServerPermissionSql
        $sql | Should Match "IF NOT EXISTS \(SELECT 1 FROM sys\.server_principals WHERE sid = SUSER_SID\(@login\)\)"
        $sql | Should Match "CREATE LOGIN ' \+ QUOTENAME\(@login\)"
        $sql | Should Match "GRANT CREATE ANY DATABASE TO ' \+ QUOTENAME\(@principal\)"
        $sql | Should Match "GRANT VIEW ANY DATABASE"
        $sql | Should Not Match "NETWORK SERVICE"
    }

    It "el lote por base reutiliza el usuario existente y solo agrega el rol si falta" {
        $sql = Get-DatabasePermissionSql
        $sql | Should Match "sys\.database_principals WHERE sid = SUSER_SID\(@login\)"
        $sql | Should Match "IS_ROLEMEMBER\(N'db_backupoperator', @user\) <> 1"
        $sql | Should Match "EXEC sp_addrolemember N'db_backupoperator', @user"
    }

    It "no otorga sysadmin ni db_owner" {
        $all = (Get-ServerPermissionSql) + (Get-DatabasePermissionSql)
        $all | Should Not Match "sysadmin"
        $all | Should Not Match "db_owner"
    }
}

Describe "Grant-NetworkShareAccess.ps1" {
    . (Join-Path $installerRoot "Grant-NetworkShareAccess.ps1")

    It "acepta varias cuentas separadas por coma o punto y coma, sin repetir" {
        $list = ConvertTo-AccountList @("DOM\SQL01$, DOM\SQL02$;DOM\SQL01$", " ")
        $list.Count | Should Be 2
        $list[0] | Should Be 'DOM\SQL01$'
        $list[1] | Should Be 'DOM\SQL02$'
    }

    It "valida el formato DOMINIO\CUENTA" {
        Test-ComputerAccountFormat 'DOM\SQL01$' | Should Be $true
        Test-ComputerAccountFormat 'SQL01$' | Should Be $false
        Test-ComputerAccountFormat '\\archivos\respaldos' | Should Be $false
    }
}

Describe "Lanzadores de permisos" {
    foreach ($pair in @(
        @("Configurar-Permisos-SQL.cmd", "Grant-BackupPermissions.ps1"),
        @("Configurar-Permisos-CarpetaRed.cmd", "Grant-NetworkShareAccess.ps1")
    )) {
        $launcher = $pair[0]
        $script = $pair[1]
        It "$launcher pide administrador y ejecuta installer\$script" {
            $source = Get-Content -LiteralPath (Join-Path $agentRoot $launcher) -Raw
            $source | Should Match "fltmc"
            $source | Should Match "-Verb RunAs"
            $source | Should Match ([regex]::Escape("installer\$script"))
            Test-Path -LiteralPath (Join-Path $installerRoot $script) | Should Be $true
        }
    }

    It "package.ps1 copia ambos lanzadores antes de calcular los hashes" {
        $source = Get-Content -LiteralPath (Join-Path $agentRoot "package.ps1") -Raw
        $source | Should Match "Configurar-Permisos-SQL\.cmd"
        $source | Should Match "Configurar-Permisos-CarpetaRed\.cmd"
        $copy = $source.IndexOf('Copy-Item -Force -LiteralPath $launcher')
        $copy | Should BeGreaterThan 0
        $source.IndexOf('$hashLines = Get-ChildItem') | Should BeGreaterThan $copy
    }
}
