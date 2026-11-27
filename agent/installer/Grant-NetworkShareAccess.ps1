[CmdletBinding()]
param(
    # Ruta LOCAL de la carpeta compartida en este servidor de archivos (por ejemplo E:\Respaldos).
    [string]$FolderPath = "",
    # Cuentas de equipo de los servidores con el agente, separadas por coma (por ejemplo DOMINIO\SQL01$).
    [string[]]$Accounts = @(),
    # Muestra lo que haria sin cambiar nada.
    [switch]$DryRun
)

# Se ejecuta en el SERVIDOR DE ARCHIVOS, no en el servidor del agente.
#
# En un dominio, NETWORK SERVICE (el agente) y las cuentas virtuales de SQL Server
# (NT Service\MSSQLSERVER) acceden a la red como la cuenta de equipo DOMINIO\SERVIDOR$.
# Este script concede a esas cuentas:
#   - NTFS: Modificar sobre la carpeta (heredado).
#   - Recurso compartido: Cambiar, en cada recurso que publique esa carpeta.
# Si SQL Server corre con una cuenta de dominio propia, agréguela también en -Accounts.

$ErrorActionPreference = "Stop"

function ConvertTo-AccountList {
    param([string[]]$Values)
    return @(
        $Values |
            ForEach-Object { $_ -split "[,;]" } |
            ForEach-Object { $_.Trim() } |
            Where-Object { $_ } |
            Select-Object -Unique
    )
}

function Test-ComputerAccountFormat {
    param([Parameter(Mandatory = $true)][string]$Account)
    # Una cuenta de equipo termina en "$"; se acepta tambien una cuenta de servicio de dominio.
    return $Account -match '^[^\\\s]+\\[^\\\s]+$'
}

function Resolve-AccountSid {
    param([Parameter(Mandatory = $true)][string]$Account)
    $nt = New-Object System.Security.Principal.NTAccount($Account)
    return $nt.Translate([System.Security.Principal.SecurityIdentifier]).Value
}

function Get-SharesForFolder {
    param([Parameter(Mandatory = $true)][string]$Folder)
    $normalized = [System.IO.Path]::GetFullPath($Folder).TrimEnd('\')
    return @(
        Get-SmbShare -Special $false -ErrorAction SilentlyContinue |
            Where-Object { $_.Path -and ([System.IO.Path]::GetFullPath($_.Path).TrimEnd('\') -ieq $normalized) }
    )
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

    Write-Host ""
    Write-Host "=== Permisos de carpeta de red para Data Express Agent ===" -ForegroundColor Cyan
    Write-Host "Ejecute esto en el servidor de ARCHIVOS donde esta la carpeta compartida."
    if ($DryRun) { Write-Host "MODO PRUEBA: no se cambiara nada." -ForegroundColor Yellow }

    if (-not $FolderPath) {
        $FolderPath = Read-Host "Ruta local de la carpeta compartida en este servidor (por ejemplo E:\Respaldos)"
    }
    $FolderPath = $FolderPath.Trim().Trim('"')
    if (-not $FolderPath -or $FolderPath.StartsWith("\\")) {
        throw "Indique la ruta LOCAL de la carpeta (E:\...), no la ruta de red \\servidor\recurso."
    }
    if (-not (Test-Path -LiteralPath $FolderPath -PathType Container)) {
        throw "La carpeta $FolderPath no existe en este servidor."
    }

    $accountList = ConvertTo-AccountList $Accounts
    if ($accountList.Count -eq 0) {
        $typed = Read-Host "Cuentas de equipo de los servidores con el agente, separadas por coma (por ejemplo DOMINIO\SQL01`$)"
        $accountList = ConvertTo-AccountList @($typed)
    }
    if ($accountList.Count -eq 0) { throw "Debe indicar al menos una cuenta." }

    $shares = @(Get-SharesForFolder -Folder $FolderPath)
    if ($shares.Count -eq 0) {
        Add-Result "Recurso compartido" "AVISO" "La carpeta no esta compartida; solo se aplicaran permisos NTFS"
    }

    foreach ($account in $accountList) {
        if (-not (Test-ComputerAccountFormat $account)) {
            Add-Result "Cuenta $account" "ERROR" "Formato no valido; use DOMINIO\EQUIPO`$"
            continue
        }
        try {
            $sid = Resolve-AccountSid $account
        }
        catch {
            Add-Result "Cuenta $account" "ERROR" "No existe en el dominio o no se pudo resolver"
            continue
        }

        $grant = "*${sid}:(OI)(CI)M"
        if ($DryRun) {
            Add-Result "NTFS: $account" "PRUEBA" "icacls `"$FolderPath`" /grant $grant"
        }
        else {
            $output = & icacls.exe $FolderPath /grant $grant 2>&1
            if ($LASTEXITCODE -eq 0) { Add-Result "NTFS: $account" "OK" "Modificar (heredado)" }
            else { Add-Result "NTFS: $account" "ERROR" (($output | Out-String).Trim()) }
        }

        foreach ($share in $shares) {
            if ($DryRun) {
                Add-Result "Recurso $($share.Name): $account" "PRUEBA" "Concederia Cambiar"
                continue
            }
            try {
                Grant-SmbShareAccess -Name $share.Name -AccountName $account -AccessRight Change -Force | Out-Null
                Add-Result "Recurso $($share.Name): $account" "OK" "Cambiar"
            }
            catch {
                Add-Result "Recurso $($share.Name): $account" "ERROR" $_.Exception.Message
            }
        }
    }

    Write-Host ""
    $results | Format-Table -AutoSize -Wrap | Out-String -Width 160 | Write-Host
    $errors = @($results | Where-Object { $_.Estado -eq "ERROR" })
    if ($errors.Count -gt 0) {
        Write-Host "Termino con $($errors.Count) error(es). Revise el detalle arriba." -ForegroundColor Red
        return 1
    }
    Write-Host "Permisos aplicados." -ForegroundColor Green
    return 0
}

if ($MyInvocation.InvocationName -ne ".") {
    try {
        exit (Main)
    }
    catch {
        Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
        exit 1
    }
}
