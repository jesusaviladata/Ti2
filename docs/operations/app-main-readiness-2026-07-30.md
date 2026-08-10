# Estado de `app.main` e IIS — 2026-07-30

## Resultado

El backend productivo `app.main:app` ya agrupa los módulos funcionales dentro del
mismo programa. Los routers heredados que contenían respuestas 501 ahora reexportan
las implementaciones productivas y no se montan stubs.

Módulos incluidos:

- autenticación y usuarios;
- permisos por capacidades y rol;
- limpieza local con simulación, cuarentena, restauración y purga;
- limpieza SFTP/FTP/FTPS y limpieza estructural en jobs;
- claves SSH conocidas por tenant;
- administrador de archivos local y remoto;
- accesos, alertas y exportación CSV;
- conexiones efímeras a SQL Server;
- respaldos manuales múltiples, integridad, retención y programación;
- dashboard, actividad, notificaciones, reportes y búsqueda;
- APScheduler embebido con programaciones persistidas en PostgreSQL.

Las credenciales de SQL Server, FTP y SSH no se persisten. Celery fue retirado del
runtime; no se requiere Redis.

## Persistencia y seguridad

- Alembic esperado: `0003`.
- PostgreSQL guarda configuración, simulaciones, ejecuciones, cuarentenas, jobs,
  notificaciones, sesiones y auditoría.
- El administrador tiene todas las capacidades.
- Supervisor y técnico tienen operaciones reversibles; la purga y configuración
  sensible quedan para administrador.
- Cliente conserva permisos de consulta.
- Las rutas remotas deben ser absolutas y pertenecer a la allowlist.
- Las rutas locales se limitan por `FM_ALLOWED_ROOTS`.
- SFTP usa fijación de host key por tenant y bloquea cambios hasta revisión.

## Evidencia de validación

- Backend: 116 pruebas aprobadas.
- OpenAPI: 74 paths generados.
- Instalador: 11 pruebas Pester aprobadas.
- Frontend: TypeScript y build standalone aprobados con Next.js 16.2.12.
- `npm audit`: 0 vulnerabilidades.
- Alembic: generación offline hasta `0003` aprobada.
- Release final de prueba:
  `C:\tmp\gestor-appmain-release-20260730-02`.
- Manifiesto: 1,469 archivos, 0 faltantes y 0 hashes inválidos.

## Bloqueos actuales de esta PC para instalar en IIS

El código y la release están listos, pero esta PC aún no cumple siete requisitos del
servidor:

1. no existe la unidad `D:`;
2. IIS no está habilitado;
3. falta IIS URL Rewrite 2.1;
4. falta IIS Application Request Routing;
5. falta PostgreSQL o su instalador configurado;
6. falta WinSW x64 configurado;
7. falta el certificado HTTPS y su thumbprint.

Además, `OffsiteRoot` está vacío; no bloquea la instalación, pero deja los respaldos
sin copia externa.

## Pasos para publicar

1. Preparar el servidor y editar `installer/install-config.psd1`.
2. Crear o cambiar las rutas de datos si no se usará `D:`.
3. Instalar/habilitar IIS, URL Rewrite y ARR.
4. Configurar PostgreSQL 17, WinSW y el certificado HTTPS.
5. Configurar `OffsiteRoot`.
6. Copiar la release final al servidor.
7. Abrir PowerShell como administrador y ejecutar:

```powershell
.\installer\Test-InstallPrerequisites.ps1
.\installer\Install-GestorPrimee.ps1 -ReleasePath 'C:\ruta\de\la\release'
```

8. Validar `/health/live`, `/health/ready`, login, servicios WinSW, tareas
   programadas y acceso externo únicamente por IIS/HTTPS.
