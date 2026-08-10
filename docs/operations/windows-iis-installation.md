# Instalacion en Windows 11 e IIS

Este procedimiento instala Gestor PRIMEE para una sola empresa operativa: Data Express. PostgreSQL queda como servicio local de Windows y sus datos se guardan fuera del codigo.

## Rutas y valores que se deben completar

Edite `installer/install-config.psd1` antes de instalar. La ruta propuesta es:

```text
D:\DataExpress\GestorPrimee
```

Para cambiarla, modifique `InstallRoot`, `PostgresData` y `BackupRoot` en ese archivo. No haga una busqueda y reemplazo en el codigo.

Complete tambien:

- `PublicHost`: nombre DNS real que usaran los usuarios;
- `CertificateThumbprint`: huella del certificado HTTPS en `Cert:\LocalMachine\My`;
- `PostgresInstallerPath`: instalador local de PostgreSQL 17, solo si PostgreSQL aun no existe;
- `PostgresInstallerSha256`: SHA-256 publicado para ese instalador;
- `WinSWPath`: ejecutable WinSW x64 guardado localmente;
- `WinSWSha256`: SHA-256 publicado para ese ejecutable;
- `PythonPath` y `NodePath`, si no estan en `PATH`;
- `OffsiteRoot`, cuando exista otra unidad o una carpeta de red.

No coloque instaladores, secretos ni la carpeta de datos PostgreSQL dentro del sitio publicado por IIS. Descargue PostgreSQL desde el [sitio oficial de PostgreSQL para Windows](https://www.postgresql.org/download/windows/) y WinSW desde sus [releases oficiales](https://github.com/winsw/winsw/releases).

## Diagnostico sin permisos administrativos

Desde PowerShell, en la raiz de `infra-platform`:

```powershell
.\installer\Test-InstallPrerequisites.ps1
```

Este comando no instala ni modifica el equipo. En el equipo de desarrollo actual detecto como pendientes la unidad `D:`, IIS, URL Rewrite, ARR, PostgreSQL, WinSW y el certificado. Es normal hasta ejecutar el proceso en el servidor y completar la configuracion.

## Construccion de la release fuera del servidor

No ejecute `npm run dev` en el servidor. Prepare el artefacto en el equipo de desarrollo o en un equipo de build:

```powershell
Set-Location 'C:\ruta\del\desarrollo\infra-platform'
$release = 'D:\DataExpress\releases\gestor-primee-2026-07-20'
.\installer\Build-Release.ps1 -OutputPath $release
```

El script ejecuta type-check y build con un heap de build controlado, copia el backend y genera `release-manifest.json` con SHA-256. La carpeta resultante se copia al servidor; el servidor no ejecuta npm ni Next en modo desarrollo.

## Componentes que requieren administrador

En la instalacion final deben estar disponibles:

1. IIS con WebSocket Protocol.
2. IIS URL Rewrite 2.1.
3. IIS Application Request Routing con proxy habilitado.
4. PostgreSQL 17 o su instalador local.
5. Python 3.11+ y Node.js 20.9+ compatibles con el proyecto.
6. WinSW x64.
7. Un certificado HTTPS vigente para `PublicHost`.

## Instalacion final

Abra PowerShell como administrador y ejecute:

```powershell
Set-Location 'C:\ruta\del\desarrollo\infra-platform'
.\installer\Test-InstallPrerequisites.ps1
.\installer\Install-GestorPrimee.ps1 -ReleasePath 'D:\DataExpress\releases\gestor-primee-2026-07-20'
```

El segundo comando se detiene sin cambios si el diagnostico no pasa. Solicita sin mostrar:

- la contrasena administrativa de PostgreSQL;
- el correo del administrador inicial de Data Express;
- su contrasena inicial de al menos 14 caracteres.

Luego crea la base y el rol, genera secretos aleatorios, restringe `production.env`, verifica los hashes de la release, ejecuta Alembic, crea el administrador de forma idempotente, registra los dos servicios, configura solo el sitio indicado en IIS y registra el respaldo diario. El servicio frontend ejecuta un unico `node server.js` standalone con `--max-old-space-size=512`; un monitor reinicia solo ese servicio tras tres muestras consecutivas por encima del umbral.

## Comprobaciones posteriores

```powershell
Get-Service DataExpressGestorBackend,DataExpressGestorFrontend
Invoke-RestMethod http://127.0.0.1:8000/health/live
Invoke-RestMethod http://127.0.0.1:8000/health/ready
Get-ScheduledTask -TaskName 'DataExpress-GestorPrimee-PostgreSQL-Backup'
Get-ScheduledTask -TaskName 'DataExpress-GestorPrimee-Frontend-Memory'
```

Compruebe tambien desde otro equipo que los puertos 3000, 5432 y 8000 no sean accesibles. Solo IIS/HTTPS debe estar publicado. PostgreSQL debe limitarse a loopback mediante `listen_addresses` y las reglas de Firewall de Windows.

## Actualizacion y recuperacion

Repita el instalador con un nuevo `ReleasePath`. Las migraciones y el bootstrap son idempotentes. Las versiones se conservan en `app\releases`; `app\current` apunta a la activa. Si una validacion final falla, no elimine la release anterior: revise `logs\maintenance`, corrija la causa y vuelva a ejecutar.

La release incluye los módulos productivos de Backups, Limpieza, Accesos, conexiones, Dashboard, Alertas y Reportes dentro de `app.main`. Los archivos `.bak` de SQL Server continúan siendo responsabilidad del módulo Backups.
