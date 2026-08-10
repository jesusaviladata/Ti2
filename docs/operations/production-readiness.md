# Salida a producción: Data Express

Este documento es la referencia operativa vigente para el despliegue en Windows 11 + IIS. La empresa inicial es Data Express y se usa un único dominio HTTPS.

## Componentes que se ejecutan

- IIS: único punto público HTTPS.
- Un servicio WinSW para FastAPI en `127.0.0.1:8000`, con un worker.
- Un servicio WinSW para Next.js standalone en `127.0.0.1:3000`, con un único proceso Node y `--max-old-space-size=512`.
- PostgreSQL local en `127.0.0.1:5432`, con los puertos internos bloqueados por Firewall de Windows.
- Tarea programada de respaldo PostgreSQL y monitor de memoria del frontend.

No se inicia `next dev`, no se construye Next.js en el servidor y no se usan Docker, Redis ni procesos Node adicionales para producción.

## Cambios funcionales vigentes

- La autenticación productiva usa cookies HttpOnly, refresh rotatorio y protección CSRF.
- Google Authenticator/TOTP/2FA fue retirado del flujo activo. Las columnas históricas de TOTP permanecen únicamente para compatibilidad con bases ya existentes y no se leen ni se exponen.
- La base interna guarda usuarios, sesiones, auditoría, configuración y metadatos del portal.
- Los archivos `.bak` de SQL Server siguen siendo responsabilidad del módulo Backups; no se mezclan con el respaldo PostgreSQL.

## Archivos de una release

La release se genera en un equipo de construcción con `installer/Build-Release.ps1`. Debe contener `release-manifest.json`, `backend/requirements.txt`, `frontend/server.js`, `frontend/.next/static` y los hashes SHA-256 del manifiesto. En el servidor se sube la carpeta de release completa y se ejecuta `Install-GestorPrimee.ps1` como administrador.

No se suben `.env`, `backend/.venv`, `node_modules`, `.next/cache`, `tests` ni credenciales. `production.env` se crea localmente en `D:\DataExpress\GestorPrimee\config` durante la instalación.

## Respaldos y restauración

- Diarios: `D:\DataExpress\GestorPrimee\backups\postgresql\daily` (14 copias).
- Semanales: `D:\DataExpress\GestorPrimee\backups\postgresql\weekly` (8 copias).
- Si `OffsiteRoot` está configurado, cada copia se verifica por SHA-256 y se aplica la misma retención en la ubicación externa.
- La restauración siempre se hace a una base temporal; nunca se permite apuntar directamente a `gestor_primee`.
- Antes de confiar en el sistema, ejecutar una restauración de prueba y validar `/health/ready` y el login.

Mientras `OffsiteRoot` esté vacío, una falla física de la unidad D: puede dejar sin respaldo. Configurar otra unidad o una ruta UNC con permisos para la cuenta de la tarea programada.

## Verificaciones antes de publicar

1. `Invoke-Pester -Path .\\installer\\tests` debe terminar con todos los casos aprobados.
2. `backend/.venv/Scripts/python.exe -m pytest -q backend/tests backend/tests_prod` debe terminar sin fallos.
3. En `frontend`, ejecutar `npm run type-check` y `npm run build` en el equipo de construcción.
4. Ejecutar `Smoke-TestRelease.ps1` sobre la release; debe devolver HTTP 200 para backend y frontend.
5. En el servidor, comprobar que sólo IIS es público y que 3000/5432/8000 no aceptan conexiones externas.
6. Verificar tareas `DataExpress-GestorPrimee-PostgreSQL-Backup` y `DataExpress-GestorPrimee-Frontend-Memory`.

## Actualizaciones

Cada actualización usa una nueva carpeta `app\\releases\\<timestamp>`. Se valida el manifiesto, se ejecutan migraciones, smoke test y luego se cambia el junction `app\\current`. Mantener la release anterior hasta validar la nueva para permitir rollback controlado; no borrar la base ni los respaldos durante una actualización.
