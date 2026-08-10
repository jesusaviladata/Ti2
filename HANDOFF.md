# Estado del proyecto y siguiente paso (traspaso)

Última actualización: **2026-07-30**.

## Estado actual

`backend/app/main.py` es el backend productivo y ya monta las implementaciones funcionales de todos los módulos. `backend/dev_server.py` se conserva sólo como referencia y compatibilidad de desarrollo. No quedan endpoints 501 montados en producción.

La arquitectura productiva es:

- IIS como único punto público HTTPS;
- FastAPI `app.main:app` en loopback mediante WinSW;
- Next.js standalone en loopback mediante WinSW;
- PostgreSQL 17 local;
- APScheduler dentro del backend, con programaciones persistidas;
- sin Docker, Redis ni Celery en el despliegue Windows/IIS.

## Funcionalidad completada

- RBAC por capacidades: administrador total; supervisor/técnico reversible; cliente lectura.
- Limpieza local/remota, simulación, cuarentena, restauración y purga admin.
- Administrador de archivos y host keys SSH por tenant.
- Accesos, conexiones SQL, respaldos, scheduler, dashboard, alertas, reportes y búsqueda.
- Alembic `0003` con tablas operativas y aislamiento por tenant.
- Credenciales remotas y SQL efímeras; no se persisten.

## Validación

- 116 pruebas backend aprobadas.
- 11 pruebas Pester del instalador aprobadas.
- TypeScript y build Next.js 16.2.12 aprobados.
- `npm audit`: 0 vulnerabilidades.
- Release verificada: `C:\tmp\gestor-appmain-release-20260730-02` (1,469 hashes correctos).

## Pendiente para instalar en esta PC

El preflight detecta siete bloqueos de infraestructura: unidad `D:`, IIS, URL Rewrite, ARR, PostgreSQL, WinSW y certificado HTTPS. `OffsiteRoot` también debe configurarse para tener una copia externa.

La guía vigente y el detalle de evidencia están en:

- `docs/operations/app-main-readiness-2026-07-30.md`
- `docs/operations/windows-iis-installation.md`
- `docs/operations/production-readiness.md`
