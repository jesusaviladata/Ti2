[CmdletBinding()]
param(
    # Instancia de SQL Server: "MSSQLSERVER" (predeterminada) o el nombre de una instancia con nombre.
    [string]$SqlInstance = "",
    # Carpeta donde SQL Server escribe los .bak (la raiz del perfil de destino local).
    [string]$WorkFolder = "",
    # Bases a autorizar. Vacio = todas las bases de usuario en linea.
    [string[]]$Databases = @(),
    # Muestra lo que haria sin cambiar nada.
    [switch]$DryRun
)

# Permisos que necesita Data Express Agent para respaldar SQL Server.
#
#  SQL Server (cuenta del agente: NETWORK SERVICE, autenticacion de Windows):
#   - Login de Windows para NETWORK SERVICE.
#   - CREATE ANY DATABASE: RESTORE VERIFYONLY y la lectura de sys.master_files
#     (calculo de espacio) lo exigen.
#   - VIEW ANY DATABASE: listar las bases.
#   - Rol db_backupoperator en cada base: BACKUP DATABASE y BACKUP LOG.
#  Compatible con SQL Server 2008 R2 y posteriores.
#  Carpeta de trabajo:
#   - Modificar para la cuenta del servicio de SQL Server (crea los .bak).
#   - Modificar para NETWORK SERVICE (lee, comprime y borra los .bak).
#
# Es idempotente: se puede ejecutar de nuevo cuando se agreguen bases.

$ErrorActionPreference = "Stop"
$NetworkServiceSid = "S-1-5-20"

function Get-NetworkServiceAccountName {
    # El nombre cambia con el idioma de Windows ("NT AUTHORITY\Servicio de red"); se resuelve por SID.
    $sid = New-Object System.Security.Principal.SecurityIdentifier($NetworkServiceSid)
    return $sid.Translate([System.Security.Principal.NTAccount]).Value
}

function Get-SqlServerTarget {
    param([Parameter(Mandatory = $true)][string]$Instance)
    if ($Instance -eq "MSSQLSERVER") {
        return [PSCustomObject]@{ Instance = $Instance; Server = "localhost"; Service = "MSSQLSERVER" }
    }
    return [PSCustomObject]@{ Instance = $Instance; Server = "localhost\$Instance"; Service = "MSSQL`$$Instance" }
}

function Get-LocalSqlInstances {
    $key = "HKLM:\SOFTWARE\Microsoft\Microsoft SQL Server\Instance Names\SQL"
    if (-not (Test-Path -LiteralPath $key)) { return @() }
    $properties = Get-ItemProperty -LiteralPath $key
    return @(
        $properties.PSObject.Properties |
            Where-Object { $_.Name -notlike "PS*" } |
            ForEach-Object { $_.Name } |
            Sort-Object
    )
}

function Test-IsUncPath {
    param([string]$Path)
    return $Path.StartsWith("\\")
}

function Get-ServerPermissionSql {
    # Lote T-SQL de nivel servidor. @login llega como parametro; los nombres se citan con QUOTENAME.
    return @"
DECLARE @sql nvarchar(max);
IF NOT EXISTS (SELECT 1 FROM sys.server_principals WHERE sid = SUSER_SID(@login))
BEGIN
    SET @sql = N'CREATE LOGIN ' + QUOTENAME(@login) + N' FROM WINDOWS';
    EXEC (@sql);
END;
DECLARE @principal sysname = (SELECT name FROM sys.server_principals WHERE sid = SUSER_SID(@login));
SET @sql = N'GRANT CREATE ANY DATABASE TO ' + QUOTENAME(@principal);
EXEC (@sql);
SET @sql = N'GRANT VIEW ANY DATABASE TO ' + QUOTENAME(@principal);
EXEC (@sql);
"@
}

function Get-DatabasePermissionSql {
    # Se ejecuta dentro de cada base. Reutiliza un usuario existente para ese login aunque tenga otro nombre.
    return @"
DECLARE @sql nvarchar(max);
DECLARE @principal sysname = (SELECT name FROM sys.server_principals WHERE sid = SUSER_SID(@login));
DECLARE @user sysname = (SELECT name FROM sys.database_principals WHERE sid = SUSER_SID(@login));
IF @user IS NULL
BEGIN
    SET @sql = N'CREATE USER ' + QUOTENAME(@principal) + N' FOR LOGIN ' + QUOTENAME(@principal);
    EXEC (@sql);
    SET @user = @principal;
END;
IF IS_ROLEMEMBER(N'db_backupoperator', @user) <> 1
BEGIN
    -- sp_addrolemember funciona tambien en SQL Server 2008 R2 (ALTER ROLE ADD MEMBER es 2012+).
    EXEC sp_addrolemember N'db_backupoperator', @user;
END;
"@
}

function Get-IcaclsGrantArguments {
    param(
        [Parameter(Mandatory = $true)][string]$Folder,
        [Parameter(Mandatory = $true)][string]$Account
    )
    # (OI)(CI)M = Modificar, heredado por archivos y subcarpetas. Un SID se pasa con asterisco.
    $principal = if ($Account -match '^S-1-') { "*$Account" } else { $Account }
    return @($Folder, "/grant", "${principal}:(OI)(CI)M")
}

function Invoke-SqlBatch {
    param(
        [Parameter(Mandatory = $true)]$Connection,
        [Parameter(Mandatory = $true)][string]$Sql,
        [Parameter(Mandatory = $true)][string]$Login
    )
    $command = $Connection.CreateCommand()
    $command.CommandText = $Sql
    $command.CommandTimeout = 120
    [void]$command.Parameters.Add("@login", [System.Data.SqlDbType]::NVarChar, 256)
    $command.Parameters["@login"].Value = $Login
    [void]$command.ExecuteNonQuery()
}

function Main {
    $isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator
    )
    if (-not $isAdmin) { throw "Ejecute este script como administrador." }

    $results = New-Object System.Collections.Generic.List[object]
    function Add-Result([string]$Step, [string]$Status, [string]$Detail) {
        $results.Add([PSCustomObject]@{ Paso = $Step; Estado = $Status; Detalle = $Detail })
    }

    $login = Get-NetworkServiceAccountName
    Write-Host ""
    Write-Host "=== Permisos de backup para Data Express Agent ===" -ForegroundColor Cyan
    Write-Host "Cuenta del agente: $login"
    if ($DryRun) { Write-Host "MODO PRUEBA: no se cambiara nada." -ForegroundColor Yellow }

    # 1. Instancia de SQL Server
    if (-not $SqlInstance) {
        $instances = @(Get-LocalSqlInstances)
        if ($instances.Count -eq 0) { throw "No se encontro ninguna instancia de SQL Server en este equipo." }
        if ($instances.Count -eq 1) {
            $SqlInstance = $instances[0]
        }
        else {
            Write-Host ""
            Write-Host "Instancias encontradas:"
            for ($index = 0; $index -lt $instances.Count; $index++) { Write-Host "  [$($index + 1)] $($instances[$index])" }
            $choice = Read-Host "Elija el numero de la instancia"
            $position = 0
            if (-not [int]::TryParse($choice, [ref]$position) -or $position -lt 1 -or $position -gt $instances.Count) {
                throw "Opcion no valida."
            }
            $SqlInstance = $instances[$position - 1]
        }
    }
    $target = Get-SqlServerTarget -Instance $SqlInstance
    $service = Get-CimInstance -ClassName Win32_Service -Filter "Name='$($target.Service)'" -ErrorAction SilentlyContinue
    $serviceAccount = if ($service) { [string]$service.StartName } else { "" }
    Write-Host "Instancia: $($target.Server)  (servicio $($target.Service), cuenta '$serviceAccount')"

    # 2. Carpeta de trabajo
    if (-not $WorkFolder) {
        $WorkFolder = Read-Host "Carpeta donde SQL Server guardara los .bak (por ejemplo D:\Respaldos)"
    }
    $WorkFolder = $WorkFolder.Trim().Trim('"')
    if (-not $WorkFolder) { throw "Debe indicar la carpeta de trabajo." }

    # 3. Permisos en SQL Server
    $connection = New-Object System.Data.SqlClient.SqlConnection(
        "Server=$($target.Server);Database=master;Integrated Security=SSPI;Application Name=DataExpress-Permisos"
    )
    try {
        $connection.Open()
    }
    catch {
        throw "No fue posible conectar con $($target.Server) usando su usuario de Windows. Ejecute el script con un usuario sysadmin de SQL Server. Detalle: $($_.Exception.Message)"
    }
    try {
        $check = $connection.CreateCommand()
        $check.CommandText = "SELECT IS_SRVROLEMEMBER('sysadmin')"
        if ([int]$check.ExecuteScalar() -ne 1) {
            throw "Su usuario de Windows no es sysadmin en $($target.Server). Ejecute el script con un usuario administrador de SQL Server."
        }

        if ($DryRun) {
            Add-Result "Login y permisos de servidor" "PRUEBA" "Crearia el login $login y le daria CREATE ANY DATABASE y VIEW ANY DATABASE"
        }
        else {
            Invoke-SqlBatch -Connection $connection -Sql (Get-ServerPermissionSql) -Login $login
            Add-Result "Login y permisos de servidor" "OK" "CREATE ANY DATABASE, VIEW ANY DATABASE"
        }

        $list = $connection.CreateCommand()
        $list.CommandText = "SELECT name, is_read_only FROM sys.databases WHERE database_id > 4 AND state_desc = 'ONLINE' ORDER BY name"
        $reader = $list.ExecuteReader()
        $available = @()
        while ($reader.Read()) {
            $available += [PSCustomObject]@{ Name = $reader.GetString(0); ReadOnly = $reader.GetBoolean(1) }
        }
        $reader.Close()

        $selected = if ($Databases.Count -gt 0) {
            $available | Where-Object { $Databases -contains $_.Name }
        }
        else {
            $available
        }
        foreach ($missing in ($Databases | Where-Object { $available.Name -notcontains $_ })) {
            Add-Result "Base $missing" "OMITIDA" "No existe o no esta en linea"
        }

        foreach ($database in $selected) {
            if ($database.ReadOnly) {
                Add-Result "Base $($database.Name)" "OMITIDA" "Es de solo lectura; conceda el permiso manualmente si la respalda"
                continue
            }
            if ($DryRun) {
                Add-Result "Base $($database.Name)" "PRUEBA" "Agregaria $login a db_backupoperator"
                continue
            }
            try {
                $connection.ChangeDatabase($database.Name)
                Invoke-SqlBatch -Connection $connection -Sql (Get-DatabasePermissionSql) -Login $login
                Add-Result "Base $($database.Name)" "OK" "db_backupoperator"
            }
            catch {
                Add-Result "Base $($database.Name)" "ERROR" $_.Exception.Message
            }
            finally {
                $connection.ChangeDatabase("master")
            }
        }
        if (-not $selected) { Add-Result "Bases de usuario" "AVISO" "No hay bases de usuario en linea para autorizar" }
    }
    finally {
        $connection.Close()
    }

    # 4. Permisos de la carpeta de trabajo
    if (Test-IsUncPath $WorkFolder) {
        Add-Result "Carpeta $WorkFolder" "AVISO" "Es una carpeta de red: ejecute Configurar-Permisos-CarpetaRed.cmd en el servidor de archivos"
    }
    else {
        if (-not (Test-Path -LiteralPath $WorkFolder -PathType Container)) {
            if ($DryRun) { Add-Result "Carpeta $WorkFolder" "PRUEBA" "La crearia" }
            else {
                New-Item -ItemType Directory -Force -Path $WorkFolder | Out-Null
                Add-Result "Carpeta $WorkFolder" "OK" "Creada"
            }
        }
        $accounts = @($NetworkServiceSid)
        if ($serviceAccount -and $serviceAccount -notmatch '^(LocalSystem|NT AUTHORITY\\SYSTEM)$') {
            $accounts += $serviceAccount
        }
        elseif (-not $serviceAccount) {
            Add-Result "Cuenta del servicio SQL" "AVISO" "No se pudo leer; conceda Modificar a la cuenta del servicio manualmente"
        }
        foreach ($account in ($accounts | Select-Object -Unique)) {
            $label = if ($account -eq $NetworkServiceSid) { $login } else { $account }
            $arguments = Get-IcaclsGrantArguments -Folder $WorkFolder -Account $account
            if ($DryRun) {
                Add-Result "Carpeta: $label" "PRUEBA" "icacls $($arguments -join ' ')"
                continue
            }
            $output = & icacls.exe @arguments 2>&1
            if ($LASTEXITCODE -eq 0) { Add-Result "Carpeta: $label" "OK" "Modificar (heredado)" }
            else { Add-Result "Carpeta: $label" "ERROR" (($output | Out-String).Trim()) }
        }
    }

    Write-Host ""
    $results | Format-Table -AutoSize -Wrap | Out-String -Width 160 | Write-Host
    $errors = @($results | Where-Object { $_.Estado -eq "ERROR" })
    if ($errors.Count -gt 0) {
        Write-Host "Termino con $($errors.Count) error(es). Revise el detalle arriba." -ForegroundColor Red
        return 1
    }
    Write-Host "Permisos aplicados. Si agrega bases nuevas, vuelva a ejecutar este script." -ForegroundColor Green
    return 0
}

# Al importarse con punto (pruebas) solo se cargan las funciones.
if ($MyInvocation.InvocationName -ne ".") {
    try {
        exit (Main)
    }
    catch {
        Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
        exit 1
    }
}
