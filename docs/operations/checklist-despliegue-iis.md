# Checklist de despliegue en IIS — Gestor PRIMEE (Data Express)

> Documento operativo generado el 2026-08-04. Sigue las fases en orden.
> El backend ya está verificado como listo (109 tests aprobados, migraciones en `0003`,
> sin stubs 501, dependencias fijadas). Todo lo pendiente es infraestructura del servidor.
>
> Arquitectura: IIS es el **único punto público HTTPS** y actúa como proxy inverso.
> El backend corre como servicio WinSW (uvicorn) en `127.0.0.1:8000`, el frontend
> Next standalone en `127.0.0.1:3000` y PostgreSQL en `127.0.0.1:5432`.

---

## Fase 0 — Construir la release (en el equipo de desarrollo, NO en el servidor)

- [ ] En `infra-platform`, ejecutar en el equipo de build:
  ```powershell
  .\installer\Build-Release.ps1 -OutputPath 'D:\DataExpress\releases\gestor-primee-2026-08-04'
  ```
- [ ] Verificar que la carpeta contiene: `release-manifest.json`, `backend/requirements.txt`,
      `frontend/server.js`, `frontend/.next/static` y los hashes SHA-256.
- [ ] Confirmar que NO se incluyó: `.env`, `backend/.venv`, `node_modules`, `.next/cache`,
      `tests`, ni credenciales.
- [ ] (Opcional pero recomendado) correr `Smoke-TestRelease.ps1` sobre la release → debe
      dar HTTP 200 para backend y frontend.

> Ya existe una release empaquetada y verificada por hash en `iis-audit-release-20260730-03/`
> (manifiesto de 1389 archivos). Si esa sigue vigente, puedes usarla en lugar de reconstruir.

---

## Fase 1 — Completar `installer/install-config.psd1`

### 🔴 Obligatorios (el instalador se detiene sin ellos)
- [ ] `CertificateThumbprint` — huella del certificado HTTPS instalado en `Cert:\LocalMachine\My`.
      Verificar con: `Get-ChildItem Cert:\LocalMachine\My | Format-List Subject, Thumbprint`
- [ ] `WinSWPath` — ruta local al `WinSW-x64.exe` (descargado de los releases oficiales de WinSW).
- [ ] `WinSWSha256` — SHA-256 publicado de ese ejecutable. Obtener con: `Get-FileHash <winsw.exe> -Algorithm SHA256`
- [ ] `PublicHost` — **CAMBIAR** el placeholder `gestor.dataexpress.local` por el nombre DNS real
      que usarán los usuarios (debe coincidir con el certificado).

### 🟡 Condicionales
- [ ] `PostgresInstallerPath` + `PostgresInstallerSha256` — solo si PostgreSQL 17 **no** está ya
      instalado. Descargar del sitio oficial de PostgreSQL para Windows.
- [ ] `PythonPath` / `NodePath` — solo si Python 3.11+ y Node.js 20.9+ **no** están en el `PATH`.

### 🟠 Rutas de datos (si NO hay unidad `D:`)
- [ ] Ajustar en este mismo archivo (NO buscar-y-reemplazar en el código):
      `InstallRoot`, `PostgresData`, `BackupRoot` y `FileManagerAllowedRoots`.

### 🔵 Recomendado (no bloquea la instalación)
- [ ] `OffsiteRoot` — otra unidad o ruta UNC de red para copia externa de respaldos.
      Mientras esté vacío, una falla de la unidad de datos deja los respaldos sin copia externa.

### ✅ Ya correctos (revisar, normalmente no tocar)
- Puertos `BackendPort=8000`, `FrontendPort=3000`, `PostgresPort=5432`, `IisHttpsPort=443`.
- Memoria frontend: heap 512 MB, avisa a 600 MB, reinicia a 900 MB tras 3 muestras.
- `DatabaseName=gestor_primee`, `DatabaseUser=gestor_primee_app`, nombres de sitio/app pool IIS.

---

## Fase 2 — Preparar los 7 requisitos del servidor (como administrador)

- [ ] **1. Unidad/rutas de datos** — existe `D:` (o se ajustaron las rutas en Fase 1).
- [ ] **2. IIS habilitado** con el rol **WebSocket Protocol**.
- [ ] **3. IIS URL Rewrite 2.1** instalado.
- [ ] **4. IIS Application Request Routing (ARR)** instalado y con **proxy habilitado**.
- [ ] **5. PostgreSQL 17** instalado (o su instalador local referenciado en la config).
- [ ] **6. WinSW x64** disponible localmente (ruta + hash en la config).
- [ ] **7. Certificado HTTPS** vigente para `PublicHost`, importado en `Cert:\LocalMachine\My`,
      con su thumbprint en la config.
- [ ] Python 3.11+ y Node.js 20.9+ disponibles (en PATH o referenciados en la config).

---

## Fase 3 — Diagnóstico previo (no modifica el equipo)

- [ ] Abrir PowerShell como administrador en la raíz de `infra-platform` y ejecutar:
  ```powershell
  .\installer\Test-InstallPrerequisites.ps1
  ```
- [ ] Resolver **todo** lo que marque como pendiente antes de continuar.
      El instalador se detiene sin cambios si este diagnóstico no pasa.

---

## Fase 4 — Instalación

- [ ] Copiar la carpeta de release completa al servidor.
- [ ] Ejecutar como administrador:
  ```powershell
  Set-Location 'C:\ruta\del\infra-platform'
  .\installer\Test-InstallPrerequisites.ps1
  .\installer\Install-GestorPrimee.ps1 -ReleasePath 'C:\ruta\de\la\release'
  ```
- [ ] Tener a mano para cuando el instalador los solicite (sin mostrarlos en pantalla):
  - [ ] contraseña administrativa de PostgreSQL;
  - [ ] correo del administrador inicial de Data Express;
  - [ ] su contraseña inicial (mínimo 14 caracteres).

> El instalador crea base/rol, genera secretos aleatorios, restringe `production.env`
> (se crea en `<InstallRoot>\config`), verifica los hashes de la release, ejecuta Alembic
> hasta `0003`, crea el administrador de forma idempotente, registra los dos servicios WinSW,
> configura el sitio en IIS y registra el respaldo diario.

---

## Fase 5 — Validaciones post-instalación

- [ ] Servicios arriba:
  ```powershell
  Get-Service DataExpressGestorBackend, DataExpressGestorFrontend
  ```
- [ ] Salud del backend:
  ```powershell
  Invoke-RestMethod http://127.0.0.1:8000/health/live
  Invoke-RestMethod http://127.0.0.1:8000/health/ready
  ```
      `/health/ready` debe reportar la revisión Alembic `0003`.
- [ ] Login funcional por HTTPS con el administrador inicial.
- [ ] Tareas programadas registradas:
  ```powershell
  Get-ScheduledTask -TaskName 'DataExpress-GestorPrimee-PostgreSQL-Backup'
  Get-ScheduledTask -TaskName 'DataExpress-GestorPrimee-Frontend-Memory'
  ```
- [ ] **Superficie pública**: desde OTRO equipo, comprobar que los puertos **3000, 5432 y 8000
      NO son accesibles**. Solo IIS/HTTPS (443) debe estar publicado.
- [ ] PostgreSQL limitado a loopback (`listen_addresses`) y reglas de Firewall de Windows activas.

---

## Fase 6 — Respaldo y prueba de restauración (antes de confiar en producción)

- [ ] Confirmar retención: diarios (14 copias) y semanales (8 copias) en `BackupRoot`.
- [ ] Ejecutar una **restauración de prueba** a una base temporal
      (nunca apuntar directo a `gestor_primee`).
- [ ] Validar tras la restauración: `/health/ready` y login.
- [ ] Si `OffsiteRoot` está configurado, verificar que cada copia se replica y se valida por SHA-256.

---

## Actualizaciones futuras (rollback controlado)

- Repetir el instalador con un nuevo `-ReleasePath`. Migraciones y bootstrap son idempotentes.
- Cada release vive en `app\releases\<timestamp>`; `app\current` (junction) apunta a la activa.
- **Mantener la release anterior** hasta validar la nueva. Si una validación falla:
  revisar `logs\maintenance`, corregir la causa y volver a ejecutar. **No borrar** la base
  ni los respaldos durante una actualización.

---

## Referencias del repositorio

- `docs/operations/production-readiness.md` — referencia operativa vigente.
- `docs/operations/windows-iis-installation.md` — procedimiento detallado de instalación.
- `docs/operations/app-main-readiness-2026-07-30.md` — estado de `app.main` e IIS.
- `docs/operations/postgresql-backup-restore.md` — respaldo y restauración de PostgreSQL.
- `installer/install-config.psd1` — configuración a completar.
- `installer/iis/web.config.template` — plantilla del proxy inverso IIS.
