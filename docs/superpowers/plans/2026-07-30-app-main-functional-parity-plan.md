# Plan de implementación: paridad funcional de `app.main`

**Especificación:** `docs/superpowers/specs/2026-07-30-app-main-functional-parity-design.md`

## Regla de ejecución

Cada bloque debe:

1. agregar o actualizar pruebas;
2. implementar una sola frontera funcional;
3. ejecutar las pruebas afectadas;
4. mantener verdes las suites productivas;
5. no introducir secretos persistidos ni consultas sin `tenant_id`.

## Bloque 1 — Fundamentos

### Archivos

- `backend/app/core/errors.py`
- `backend/app/core/capabilities.py`
- `backend/app/core/security.py`
- `backend/app/core/redaction.py`
- `backend/app/models/*.py`
- `backend/app/schemas/*.py`
- `backend/alembic/versions/0003_app_main_parity.py`
- `backend/app/models/__init__.py`

### Trabajo

- Crear errores de dominio con códigos estables.
- Crear capacidades acumulativas por rol; `admin` incluye todas.
- Crear redacción recursiva de secretos.
- Crear modelos multiempresa para limpieza, servidores remotos, cuarentena, trabajos y notificaciones.
- Ampliar `AccessLog`.
- Incorporar `BackupSchedule` a metadata/migraciones.
- Crear esquemas Pydantic que conserven contratos del frontend.
- Crear migración Alembic `0003`.

### Verificación

- Pruebas de capacidades.
- Pruebas de redacción.
- Importación completa de metadata.
- Compilación Python.

## Bloque 2 — Limpieza local

### Archivos

- `backend/app/repositories/cleanup_repository.py`
- `backend/app/services/cleanup_service.py`
- `backend/app/api/v1/cleanup.py`
- `backend/app/domain/cleanup_rules.py`
- pruebas productivas de limpieza

### Trabajo

- CRUD de carpetas y reglas.
- Escaneo seguro.
- Simulación persistida.
- Ejecución a cuarentena.
- Restauración y purga administrativa.
- Historial y programaciones.
- Validación de rutas y cambios concurrentes.

## Bloque 3 — Limpieza remota, host keys y archivos

### Archivos

- `backend/app/domain/remote_cleanup.py`
- `backend/app/domain/structural_cleanup.py`
- `backend/app/services/remote_cleanup_service.py`
- `backend/app/services/filemanager_service.py`
- `backend/app/api/v1/remote_cleanup.py`
- `backend/app/api/v1/filemanager.py`
- `backend/app/api/v1/hostkeys.py`
- pruebas de seguridad e integración

### Trabajo

- Perfiles de servidor sin secretos.
- Listado, simulación y ejecución remota.
- Trabajos estructurales persistentes y cancelables.
- Cuarentena, restauración y purga.
- TOFU de host keys.
- Gestor de archivos con allowlist.

## Bloque 4 — Accesos

### Archivos

- `backend/app/repositories/access_repository.py`
- `backend/app/services/access_service.py`
- `backend/app/api/v1/access.py`
- pruebas productivas de accesos

### Trabajo

- Apertura, listado y cierre de sesiones.
- Historial, detalle, alertas y descarga.
- Detección básica de actividad sospechosa.
- Matriz de capacidades y endpoint de compatibilidad de permisos.

## Bloque 5 — Conexiones, backups y scheduler

### Archivos

- `backend/app/services/sqlserver_service.py`
- `backend/app/services/backup_service.py`
- `backend/app/services/schedule_service.py`
- `backend/app/core/scheduler.py`
- `backend/app/api/v1/connections.py`
- `backend/app/api/v1/backups.py`
- pruebas productivas

### Trabajo

- Conexiones SQL efímeras.
- Contrato manual con múltiples bases.
- Programaciones CRUD.
- Reconciliación PostgreSQL/APScheduler.
- Ejecución única e idempotente.
- Retención e integridad.
- Eliminar Celery del runtime.

## Bloque 6 — Lecturas agregadas

### Archivos

- `backend/app/services/dashboard_service.py`
- `backend/app/services/notification_service.py`
- `backend/app/services/report_service.py`
- `backend/app/services/search_service.py`
- routers correspondientes
- pruebas de contratos

### Trabajo

- Dashboard real.
- Notificaciones.
- Reportes.
- Búsqueda global.
- Paginación y aislamiento de tenant.

## Bloque 7 — Composición, health y runtime

### Archivos

- `backend/app/main.py`
- `backend/app/api/health.py`
- `backend/app/core/config.py`
- `backend/requirements.txt`
- `installer/Build-Release.ps1`
- documentación operativa

### Trabajo

- Registrar todos los routers.
- Eliminar todos los `501`.
- Comparar revisión Alembic contra el `head` incluido.
- Retirar Redis/Celery de configuración y dependencias.
- Corregir build de release para instalar dependencias de compilación.
- Validar versiones mínimas.

## Bloque 8 — Verificación integral

### Comandos

```powershell
cd backend
python -m pytest tests
python -m pytest tests_prod
python -m compileall app

cd ..\frontend
npm run type-check
npm run build

cd ..
Invoke-Pester .\installer\tests\Installer.Tests.ps1
.\installer\Build-Release.ps1 -OutputPath <carpeta-nueva>
```

### Aceptación

- Cero coincidencias de `HTTP_501` o `status_code=501`.
- Todas las rutas del frontend registradas.
- Todas las suites verdes.
- Release standalone verificable.
- Smoke test con PostgreSQL.
