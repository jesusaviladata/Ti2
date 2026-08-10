# Plan de implementación: Windows 11, IIS y PostgreSQL local

Especificación: `docs/superpowers/specs/2026-07-20-windows-iis-local-postgresql-design.md`

## Principios

- No modificar la lógica funcional de Backups, Limpieza, Accesos o Dashboard.
- Escribir primero una prueba que demuestre cada cambio de contrato.
- PostgreSQL será obligatorio para sesiones en producción; no habrá fallback en memoria.
- Los scripts elevados serán idempotentes, acotados a rutas y servicios del producto y fallarán antes de modificar si el preflight no pasa.
- Ningún script contendrá contraseñas, certificados o URLs secretas.
- La activación de una release ocurrirá después de migraciones y smoke tests.

## Paso 1: fijar el contrato del almacén PostgreSQL

Archivos:

- Crear `backend/tests_prod/test_postgres_session_store.py`.
- Crear `backend/app/models/auth_session.py`.
- Modificar `backend/app/models/__init__.py`.

Trabajo:

- Modelar sesiones, historial de refresh consumidos y rate limits.
- Probar creación, validación, rotación, reutilización, revocación, expiración y límite de intentos.
- Mantener claves de rate limit opacas mediante hash.

Validación:

- Las pruebas nuevas fallan antes de implementar el almacén y pasan después.

## Paso 2: sustituir Redis por PostgreSQL

Archivos:

- Reemplazar `backend/app/services/session_store.py`.
- Modificar fixtures en `backend/tests_prod/fakes.py` si cambia el protocolo.
- Modificar configuración y dependencias que todavía exigen Redis.

Trabajo:

- Usar una sesión SQLAlchemy independiente y transacciones cortas por operación.
- Bloquear la fila durante refresh con `SELECT ... FOR UPDATE`.
- Confirmar revocación por reutilización antes de devolver `401`.
- Traducir `SQLAlchemyError` a `503` sin filtrar detalles.
- Eliminar singleton y cliente Redis.

Validación:

- Ejecutar pruebas específicas de sesiones y toda la autenticación.

## Paso 3: crear migración Alembic

Archivos:

- Crear `backend/alembic/versions/0002_postgres_auth_sessions.py`.
- Ajustar `backend/alembic/env.py` únicamente si es necesario.

Trabajo:

- Crear tablas, índices, claves foráneas y expiraciones.
- Incluir downgrade simétrico y seguro.
- Verificar que el SQL offline usa PostgreSQL y parte de `0001`.

Validación:

- Ejecutar `alembic upgrade head --sql` con configuración de prueba.
- Inspeccionar que no existan operaciones destructivas sobre tablas funcionales.

## Paso 4: agregar health y readiness

Archivos:

- Modificar `backend/app/main.py`.
- Crear pruebas de health.

Trabajo:

- Separar liveness de readiness.
- Readiness comprobará `SELECT 1` y la revisión Alembic esperada.
- Fallos devolverán `503` estable, sin excepción interna.

Validación:

- Probar estado disponible, base caída y revisión atrasada.

## Paso 5: retirar Redis del despliegue

Archivos:

- Modificar `backend/requirements.txt`.
- Modificar `docker-compose.yml` como referencia no productiva.
- Modificar `.env.example`.

Trabajo:

- Retirar el paquete Redis directo y el servicio Redis.
- Retirar Celery del despliegue de este bloque, ya que sus tareas funcionales quedan fuera de alcance.
- Eliminar `REDIS_URL` de la configuración productiva.

Validación:

- Buscar imports, variables y servicios Redis activos.
- Ejecutar compilación y pruebas backend.

## Paso 6: preparar artefacto Windows

Archivos:

- Crear `installer/install-config.psd1`.
- Crear `installer/Test-InstallPrerequisites.ps1`.
- Crear `installer/Install-GestorPrimee.ps1`.
- Crear plantillas WinSW para backend y frontend.
- Crear plantilla `installer/iis/web.config`.

Trabajo:

- Centralizar rutas aprobadas de `D:`.
- Validar elevación, espacio, puertos, IIS, ARR, URL Rewrite, certificados, instaladores y hashes.
- Crear directorios y ACL sin tocar otros portales.
- Preparar PostgreSQL, entorno productivo, migraciones, bootstrap, servicios y activación de release.
- Permitir paquetes locales y descarga verificada.

Validación:

- Analizar sintaxis PowerShell.
- Ejecutar preflight no mutante en el equipo actual.
- Validar XML y rutas generadas.

## Paso 7: respaldo y restauración

Archivos:

- Crear `installer/Backup-GestorPrimee.ps1`.
- Crear `installer/Restore-GestorPrimee.ps1`.
- Crear `installer/Register-MaintenanceTasks.ps1`.

Trabajo:

- Generar `pg_dump` custom, hash SHA-256 y validación `pg_restore --list`.
- Aplicar 14 diarios y 8 semanales sin eliminar archivos fuera de la raíz configurada.
- Copiar a `OffsiteRoot` cuando exista.
- Restaurar primero en base temporal y exigir confirmación para promoción.
- Registrar tareas con el Programador de tareas de Windows.

Validación:

- Probar selección de retención con archivos temporales.
- Probar modo simulación y rechazo de rutas fuera de alcance.

## Paso 8: documentación operativa

Archivos:

- Crear `docs/operations/windows-iis-installation.md`.
- Crear `docs/operations/postgresql-backup-restore.md`.

Trabajo:

- Documentar qué ejecutar ahora y qué requiere administrador.
- Indicar cómo cambiar `InstallRoot`, `PostgresData`, `BackupRoot` y `OffsiteRoot`.
- Incluir instalación, actualización, rollback, diagnóstico y recuperación.
- Distinguir respaldo interno PostgreSQL de `.bak` de SQL Server.

## Paso 9: regresión

Trabajo:

- Ejecutar todas las pruebas backend.
- Ejecutar type-check y build frontend.
- Generar SQL Alembic offline.
- Analizar PowerShell, XML y `web.config`.
- Buscar secretos, credenciales conocidas, Redis y rutas públicas de base de datos.
- Documentar verificaciones bloqueadas hasta disponer de elevación y PostgreSQL real.

Resultado esperado:

- El repositorio contiene la implementación PostgreSQL y un paquete reproducible para instalar posteriormente en Windows 11/IIS, sin modificar todavía los módulos funcionales fuera de alcance.
