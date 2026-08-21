# Plan de implementación: módulo Respaldo de archivos

**Especificación:** `docs/superpowers/specs/2026-08-20-file-backup-module-design.md`

**Versión objetivo:** Data Express Agent 0.5.0

**Estrategia:** contratos compatibles → agente local → motores de copia → restauración → interfaz → piloto

**Método:** pruebas primero, commits pequeños y despliegues reversibles

## Objetivo de ejecución

Entregar un módulo administrado para respaldar y restaurar archivos/carpetas de Windows con Full, incremental y diferencial, destinos local/UNC/SFTP, catálogo SQLite, VSS, verificación SHA-256, checkpoints, retención segura y un instalador que sólo solicite un código de vinculación.

## Reglas de trabajo

- No copiar código, recursos visuales ni marcas de Cobian Reflector.
- Mantener compatibilidad completa del backend con agentes 0.4.2.
- Ocultar el módulo si el agente no publica `file_backup_v1`.
- No habilitar el módulo en producción hasta terminar una restauración verificada en el piloto.
- Iniciar cada tarea con una prueba que demuestre la ausencia del comportamiento.
- Mantener un solo `head` de Alembic.
- No persistir secretos, sobres cifrados o listados completos de archivos en respuestas del API.
- No cargar catálogos o manifiestos completos en memoria.
- No seguir junctions, symlinks o reparse points.
- `BITACORA_CHAT_AGENTE_BACKUPS.md` y `.superpowers/` permanecen fuera de Git.

## Línea base

Antes de editar:

```powershell
cd "C:\Users\quech\OneDrive\Documentos\GESTOR PRIMEE\infra-platform"
git status --short
git switch -c feat/file-backup-module

backend\.venv\Scripts\python.exe -m pytest -q backend\tests backend\tests_prod agent\tests
backend\.venv\Scripts\alembic.exe -c backend\alembic.ini heads

cd frontend
npm run type-check
npm run build
```

Detenerse ante cualquier fallo no relacionado. Registrar el commit base y no incluir archivos sin seguimiento pertenecientes al usuario.

---

## Entrega 1 — Contratos y persistencia compatibles

### Tarea 1. Crear modelos y migración del módulo

**Archivos:**

- Crear `backend/app/models/file_backup.py`.
- Modificar `backend/app/models/__init__.py`.
- Crear `backend/alembic/versions/0011_file_backup_module.py`.
- Crear `backend/tests_prod/test_file_backup_migration.py`.
- Crear `backend/tests_prod/test_file_backup_models.py`.

**Pruebas primero:**

1. `down_revision` es `0010` y Alembic conserva un solo head.
2. Existen tablas `file_backup_tasks`, `file_backup_sources`, `file_backup_filters`, `file_backup_runs`, `file_backup_chains`, `file_backup_artifacts`, `file_restore_jobs` y `file_restore_confirmations`.
3. Todas las entidades operativas tienen `tenant_id` e índices por tenant/estado/fecha.
4. Una tarea referencia agente y perfil de destino sin guardar secretos.
5. Una ejecución conserva revisión de configuración, fase, progreso, bytes, archivos, error sanitizado y checkpoint lógico.
6. Una cadena enlaza Full e hijos sin permitir relaciones entre tenants.
7. Un artefacto tiene marca `protected` auditable.
8. PostgreSQL no contiene tabla de catálogo por archivo.

**Implementación:**

- Usar enums estables para estrategia, formato, estado de ejecución y tipo de filtro.
- Guardar fuentes y filtros normalizados en tablas hijas.
- Mantener resúmenes JSONB acotados para manifiesto, simulación y errores.
- Aplicar claves foráneas con eliminación restrictiva cuando exista historial.

**Verificación:**

```powershell
backend\.venv\Scripts\python.exe -m pytest -q backend\tests_prod\test_file_backup_migration.py backend\tests_prod\test_file_backup_models.py
backend\.venv\Scripts\alembic.exe -c backend\alembic.ini heads
```

**Commit:** `feat: add file backup persistence schema`

### Tarea 2. Añadir capacidades, esquemas y contratos API

**Archivos:**

- Modificar `backend/app/core/capabilities.py`.
- Crear `backend/app/schemas/file_backup.py`.
- Crear `backend/app/api/v1/file_backups.py`.
- Modificar `backend/app/main.py`.
- Crear `backend/tests_prod/test_file_backup_routes_contract.py`.
- Crear `backend/tests_prod/test_file_backup_schemas.py`.

**Pruebas primero:**

1. Capacidades separadas para leer, administrar, ejecutar, cancelar, proteger y restaurar.
2. Las rutas aprobadas en la especificación aparecen en la aplicación.
3. Fuentes aceptan sólo rutas absolutas de Windows/UNC dentro de límites.
4. Filtros tienen allowlist de tipo y operador.
5. Calendario, zona horaria, retención y formato validan límites.
6. Una tarea incremental/diferencial se serializa sin inventar que su primera ejecución no será Full.
7. Las respuestas nunca incluyen `secretEnvelope`, llave privada o catálogo local.
8. Los errores siguen el contrato estándar de la aplicación.

**Commit:** `feat: define file backup API contracts`

### Tarea 3. Implementar repositorio y servicio administrativo

**Archivos:**

- Crear `backend/app/repositories/file_backup_repository.py`.
- Crear `backend/app/services/file_backup_service.py`.
- Modificar `backend/app/api/v1/file_backups.py`.
- Crear `backend/tests_prod/test_file_backup_service.py`.
- Crear `backend/tests_prod/test_file_backup_api.py`.

**Pruebas primero:**

1. CRUD queda aislado por tenant.
2. No se crea tarea para agente revocado o sin `file_backup_v1`.
3. El perfil de destino pertenece al mismo agente y está `applied`.
4. Editar una tarea activa incrementa revisión y conserva historial.
5. Eliminar desactiva cuando existe historial; no borra artefactos.
6. Las colecciones están paginadas y aceptan filtros por agente/estado/búsqueda.
7. Marcar `protected` sólo modifica ese campo y escribe auditoría.
8. Una edición offline queda en espera de reconciliación y no rompe la configuración aplicada anterior.

**Commit:** `feat: manage file backup tasks by tenant`

### Tarea 4. Extender protocolo y reconciliación del agente

**Archivos:**

- Modificar `backend/app/agent_protocol.py`.
- Modificar `backend/app/schemas/agent.py`.
- Modificar `backend/app/services/agent_command_service.py`.
- Modificar `backend/app/services/agent_operation_service.py`.
- Modificar `agent/data_express_agent/protocol.py`.
- Modificar `agent/data_express_agent/runner.py`.
- Crear `backend/tests_prod/test_file_backup_command_contract.py`.
- Modificar `agent/tests/test_runner.py`.

**Comandos:**

- `apply_file_backup_config`;
- `simulate_file_backup`;
- `run_file_backup`;
- `resume_file_backup`;
- `cancel_file_backup`;
- `simulate_file_restore`;
- `run_file_restore`;
- `test_file_destination`.

**Pruebas primero:**

1. El heartbeat 0.4.2 sin capacidades sigue aceptado.
2. 0.5.0 publica `file_backup_v1` y revisión de catálogo.
3. Cada orden exige firma, revisión, idempotency key y TTL.
4. Un resultado repetido no duplica ejecuciones ni artefactos.
5. Progreso agregado actualiza fase sin recibir una fila por archivo.
6. Resultado offline se reconcilia desde journal al volver.
7. El runner rechaza comandos desconocidos o no habilitados.

**Commit:** `feat: add file backup agent protocol`

---

## Entrega 2 — Instalación universal y migración 0.4.2

### Tarea 5. Separar bootstrap de configuración operativa

**Archivos:**

- Crear `agent/data_express_agent/bootstrap.py`.
- Modificar `agent/data_express_agent/config.py`.
- Modificar `agent/data_express_agent/client.py`.
- Modificar `agent/data_express_agent/runner.py`.
- Crear `agent/tests/test_bootstrap.py`.
- Modificar `agent/tests/test_config.py`.
- Modificar `agent/tests/test_client.py`.

**Pruebas primero:**

1. Bootstrap oficial valida URL HTTPS y confianza de firma incluida en el paquete.
2. TLS no puede desactivarse.
3. El runtime funciona sin `sqlInstances` ni `backupDestinations` en `agent.json`.
4. Un archivo 0.4.2 se puede leer y migrar sin perder perfiles.
5. Una rotación de claves sólo se aplica si el conjunto está firmado por confianza existente.
6. El enrolamiento elimina el código temporal después de consumirlo.
7. Datos de bootstrap nunca sobrescriben identidad o secretos locales.

**Commit:** `feat: separate agent bootstrap from managed config`

### Tarea 6. Simplificar instalador a un código interactivo

**Archivos:**

- Modificar `agent/installer/Install-DataExpressAgent.ps1`.
- Crear `agent/installer/bootstrap.json` durante empaquetado.
- Modificar `agent/package.ps1`.
- Modificar `agent/installer/README-INSTALACION.txt`.
- Crear `agent/installer/tests/Install-DataExpressAgent.Tests.ps1`.
- Crear `agent/installer/tests/Update-DataExpressAgent.Tests.ps1`.

**Pruebas primero:**

1. Sin argumentos, el instalador solicita el código mediante `Read-Host`.
2. El código no aparece en argumentos, transcript ni configuración final.
3. Se siguen aceptando parámetros heredados sólo en modo de migración explícito.
4. El paquete sin bootstrap válido se rechaza antes de instalar el servicio.
5. Un fallo de enrolamiento elimina el código temporal.
6. Actualizar conserva identidad, journal, DPAPI, perfiles y catálogo.
7. Rollback restaura binarios y configuración anterior.

**Commit:** `feat: install agent with pairing code only`

### Tarea 7. Migrar perfiles locales al almacén administrado

**Archivos:**

- Modificar `agent/data_express_agent/profiles.py`.
- Modificar `agent/data_express_agent/discovery.py`.
- Modificar `backend/app/services/agent_profile_service.py`.
- Modificar `frontend/src/components/agents/agent-connection-wizard.tsx`.
- Modificar `agent/tests/test_profiles.py`.
- Crear `agent/tests/test_discovery.py`.
- Crear `backend/tests_prod/test_agent_profile_service.py`.

**Pruebas primero:**

1. Perfiles públicos 0.4.2 se importan una sola vez.
2. Una ruta de llave SFTP permanece local y no se devuelve al backend.
3. Secretos no migrables producen `requires_secret`.
4. Discovery reporta carpetas/volúmenes candidatos sin listar archivos.
5. El asistente puede completar configuración sin editar JSON.
6. La configuración nueva se aplica atómicamente o conserva la anterior.

**Commit:** `feat: migrate legacy agent profiles safely`

---

## Entrega 3 — Fundaciones locales del motor

### Tarea 8. Crear catálogo SQLite versionado

**Archivos:**

- Crear `agent/data_express_agent/file_catalog.py`.
- Crear `agent/data_express_agent/file_catalog_migrations.py`.
- Crear `agent/tests/test_file_catalog.py`.

**Pruebas primero:**

1. Inicialización crea tablas de tareas, archivos, cadenas, checkpoints y outbox.
2. Migración local es transaccional y conserva copia recuperable.
3. Upsert por tarea/ruta no cruza catálogos.
4. Lectura se pagina y no carga el catálogo completo.
5. Un checkpoint confirmado sobrevive reinicio abrupto.
6. Un commit de ejecución actualiza catálogo y cadena en una transacción.
7. Corrupción produce error explícito y no recrea silenciosamente la base.
8. Operaciones SQLite son seguras entre heartbeat y ejecutor.

**Commit:** `feat: add durable file backup catalog`

### Tarea 9. Implementar validación de rutas y filtros

**Archivos:**

- Crear `agent/data_express_agent/file_paths.py`.
- Crear `agent/data_express_agent/file_filters.py`.
- Crear `agent/tests/test_file_paths.py`.
- Crear `agent/tests/test_file_filters.py`.

**Pruebas primero:**

1. Sólo rutas absolutas locales/UNC son válidas.
2. Se rechazan segmentos de escape, dispositivos, ADS y nombres reservados.
3. La comparación usa semántica Windows sin distinguir mayúsculas.
4. Symlinks, junctions y reparse points se identifican antes de recorrer.
5. Include/exclude por glob, extensión, tamaño y antigüedad es determinista.
6. Exclusión tiene precedencia documentada sobre inclusión.
7. Una ruta enorme o patrón costoso se rechaza por límites.
8. Dos fuentes solapadas se normalizan o se rechazan.

**Commit:** `feat: validate file backup paths and filters`

### Tarea 10. Construir escáner streaming y simulación

**Archivos:**

- Crear `agent/data_express_agent/file_scanner.py`.
- Crear `agent/data_express_agent/file_simulation.py`.
- Crear `agent/tests/test_file_scanner.py`.
- Crear `agent/tests/test_file_simulation.py`.

**Pruebas primero:**

1. Escaneo produce elementos por iterator/lotes.
2. No sigue reparse points ni cruza raíces.
3. Errores de acceso se agregan sin filtrar rutas sensibles innecesarias.
4. Tamaño/mtime evita hash cuando el archivo no cambió.
5. Archivo nuevo, cambiado, eliminado y excluido se clasifica correctamente.
6. Diferencial compara contra Full; incremental contra último éxito.
7. Simulación devuelve archivos, bytes, exclusiones y advertencias acotadas.
8. Cancelación interrumpe el escaneo sin corromper catálogo.

**Commit:** `feat: scan and simulate file backup changes`

### Tarea 11. Añadir coordinador de recursos y preflight

**Archivos:**

- Crear `agent/data_express_agent/resource_coordinator.py`.
- Crear `agent/data_express_agent/file_preflight.py`.
- Modificar `agent/data_express_agent/runner.py`.
- Modificar `agent/data_express_agent/backup.py` para usar el coordinador compartido.
- Crear `agent/tests/test_resource_coordinator.py`.
- Crear `agent/tests/test_file_preflight.py`.

**Pruebas primero:**

1. SQL y archivos no ejecutan trabajo pesado sobre el mismo volumen.
2. Volúmenes diferentes pueden usar concurrencia limitada.
3. Preflight calcula origen, trabajo, destino y reserva crítica.
4. Espacio insuficiente detiene antes de snapshot/copia.
5. Destino inaccesible es recuperable; ruta no autorizada es terminal.
6. Locks se liberan después de éxito, error, cancelación o reinicio.

**Commit:** `feat: coordinate backup disk resources`

### Tarea 12. Integrar VSS mediante adaptador aislado

**Archivos:**

- Crear `agent/data_express_agent/vss.py`.
- Crear `agent/tests/test_vss.py`.
- Modificar `agent/data_express_agent/file_scanner.py`.

**Implementación:**

- Encapsular `diskshadow.exe` detrás de `VssProvider`.
- Generar scripts temporales sólo con unidades previamente validadas.
- Usar lista de argumentos, timeout y limpieza garantizada.
- Mapear origen real a snapshot sin aceptar texto de comando del backend.
- Eliminar snapshot/exposición al finalizar o recuperar tras reinicio.

**Pruebas primero:**

1. Sólo se aceptan letras de volumen validadas.
2. Comandos no interpolan rutas arbitrarias.
3. Timeout y código de salida producen error sanitizado.
4. Cleanup ocurre en éxito, error y cancelación.
5. Snapshot huérfano se descubre y elimina al arrancar.
6. Política `required` detiene; `when_needed` puede reportar advertencia sólo si no había archivos bloqueados.

**Commit:** `feat: snapshot locked files with VSS`

---

## Entrega 4 — Copia, destinos, cadenas y retención

### Tarea 13. Crear adaptadores de destino

**Archivos:**

- Crear `agent/data_express_agent/file_destinations.py`.
- Crear `agent/data_express_agent/file_destination_local.py`.
- Crear `agent/data_express_agent/file_destination_sftp.py`.
- Crear `agent/tests/test_file_destinations.py`.
- Crear `agent/tests/test_file_destination_sftp.py`.

**Contrato:**

- `preflight`;
- `open_writer`;
- `open_reader`;
- `stat`;
- `atomic_publish`;
- `delete`;
- `capacity` cuando esté disponible;
- `test_probe`.

**Pruebas primero:**

1. Local y UNC usan rutas normalizadas y publicación atómica.
2. Prueba de destino ejecuta escribir, leer, hash, renombrar y eliminar.
3. SFTP exige huella conocida y nunca usa auto-accept.
4. SFTP reanuda únicamente desde frontera confirmada segura.
5. Credenciales sólo existen en memoria durante la operación.
6. Errores de red se clasifican como recuperables.
7. Una ruta remota no puede escapar de la raíz del perfil.

**Commit:** `feat: add file backup destination adapters`

### Tarea 14. Implementar copia verificada y checkpoints

**Archivos:**

- Crear `agent/data_express_agent/file_copy.py`.
- Crear `agent/data_express_agent/file_backup.py`.
- Modificar `agent/data_express_agent/runner.py`.
- Crear `agent/tests/test_file_copy.py`.
- Crear `agent/tests/test_file_backup.py`.

**Pruebas primero:**

1. Copia streaming calcula SHA-256 sin leer el archivo completo en memoria.
2. Destino se relee y verifica antes de confirmar checkpoint.
3. Archivo modificado durante copia se descarta y reintenta dentro del límite.
4. Archivo confirmado no se repite al reiniciar.
5. Publicación falla sin sustituir archivo válido anterior.
6. Fechas y atributos se preservan.
7. ACL NTFS se preserva opcionalmente en local/UNC.
8. Progreso se agrega por bytes/archivos y limita frecuencia de reportes.
9. Cancelación deja un estado reanudable y limpia temporales no confirmados.

**Commit:** `feat: copy and verify files with checkpoints`

### Tarea 15. Construir manifiestos y cadenas

**Archivos:**

- Crear `agent/data_express_agent/file_manifest.py`.
- Crear `agent/data_express_agent/file_chains.py`.
- Crear `agent/tests/test_file_manifest.py`.
- Crear `agent/tests/test_file_chains.py`.

**Pruebas primero:**

1. Primera ejecución siempre crea Full.
2. Incremental referencia último éxito; diferencial referencia último Full.
3. Manifiesto contiene archivos copiados/eliminados/omitidos y hashes sin secretos.
4. Escritura del manifiesto es atómica.
5. Cadena incompleta no se marca válida.
6. Un run repetido por idempotencia no crea otro nodo.
7. Resumen para backend permanece acotado aunque el manifiesto sea grande.

**Commit:** `feat: track file backup manifests and chains`

### Tarea 16. Añadir ZIP64 opcional con límites

**Archivos:**

- Crear `agent/data_express_agent/file_archive.py`.
- Crear `agent/tests/test_file_archive.py`.
- Modificar `agent/data_express_agent/file_backup.py`.

**Pruebas primero:**

1. Formato directo sigue siendo predeterminado.
2. ZIP64 se rechaza cuando estimación excede límites de tenant/agente.
3. Archivo se construye temporalmente, se prueba y publica atómicamente.
4. No se comprimen extensiones ya comprimidas.
5. Fallo conserva contenido directo/temporal recuperable y no marca éxito.
6. Manifiesto siempre está presente y validado.

**Commit:** `feat: support bounded zip64 file backups`

### Tarea 17. Implementar retención por cadenas

**Archivos:**

- Crear `agent/data_express_agent/file_retention.py`.
- Crear `agent/tests/test_file_retention.py`.
- Modificar `backend/app/services/file_backup_service.py`.

**Pruebas primero:**

1. Simulación devuelve cadenas completas, archivos y bytes.
2. Nunca elimina hijos aislados.
3. Nunca elimina la única cadena Full válida.
4. Nunca elimina artefactos protegidos.
5. No ejecuta después de run incompleto/no verificado.
6. Límites por archivos/bytes producen resultado parcial reanudable.
7. Backend y agente convergen en el mismo resultado auditable.

**Commit:** `feat: retain complete file backup chains safely`

### Tarea 18. Programar y reconciliar ejecuciones

**Archivos:**

- Crear `backend/app/services/file_backup_scheduler.py`.
- Modificar `backend/app/main.py`.
- Modificar `backend/app/services/file_backup_service.py`.
- Crear `backend/tests_prod/test_file_backup_scheduler.py`.
- Crear `backend/tests_prod/test_file_backup_lifecycle.py`.

**Pruebas primero:**

1. Trigger respeta días, hora y timezone.
2. Primera ejecución programada fuerza Full.
3. `max_instances=1`, coalescing y grace time evitan duplicados.
4. Política de ejecución perdida se aplica sólo una vez al reconectar.
5. Run recuperable ofrece `Continuar` sin crear otro run.
6. Backend distingue `retryable`, `failed`, `cancelled` y `completed_with_warnings`.
7. Reinicio del backend recarga tareas activas.

**Commit:** `feat: schedule and reconcile file backups`

---

## Entrega 5 — Restauración segura

### Tarea 19. Simular restauraciones y resolver cadenas

**Archivos:**

- Crear `agent/data_express_agent/file_restore.py`.
- Crear `backend/app/services/file_restore_service.py`.
- Modificar `backend/app/api/v1/file_backups.py`.
- Crear `agent/tests/test_file_restore.py`.
- Crear `backend/tests_prod/test_file_restore_service.py`.

**Pruebas primero:**

1. Reconstruye estado en orden Full → hijos hasta la fecha elegida.
2. Selección por archivo/carpeta no escapa del manifiesto.
3. Destino original y alternativo requieren allowlist.
4. Simulación clasifica nuevo, idéntico, reemplazo, ausente y conflicto.
5. Confirmación queda ligada al hash inmutable de la simulación y expira.
6. Cambio de archivos o manifiesto invalida confirmación.
7. API no permite ejecutar restauración sin simulación vigente.

**Commit:** `feat: simulate file restores safely`

### Tarea 20. Ejecutar y verificar restauraciones

**Archivos:**

- Modificar `agent/data_express_agent/file_restore.py`.
- Modificar `agent/data_express_agent/runner.py`.
- Modificar `backend/app/services/file_restore_service.py`.
- Modificar `agent/tests/test_file_restore.py`.
- Modificar `backend/tests_prod/test_file_restore_service.py`.

**Pruebas primero:**

1. Restaura archivos nuevos sin afectar otros.
2. Sobrescribe sólo elementos confirmados.
3. Usa temporal + renombrado atómico.
4. Verifica hash después de restaurar.
5. Preserva fechas/atributos y ACL cuando aplique.
6. Interrupción deja checkpoint y puede continuar.
7. Resultado parcial enumera conflictos sin ocultarlos.
8. Auditoría conserva actor, selección, destino y sobrescrituras.

**Commit:** `feat: restore and verify protected files`

---

## Entrega 6 — Interfaz intuitiva aprobada

### Tarea 21. Crear capa de datos frontend

**Archivos:**

- Crear `frontend/src/types/file-backup.ts`.
- Crear `frontend/src/services/file-backups.service.ts`.
- Crear `frontend/src/hooks/useFileBackups.ts`.
- Crear `frontend/src/store/file-backup-progress.store.ts`.

**Pruebas/contrato:**

1. Tipos coinciden con schemas del backend.
2. Listas paginan y filtran sin cascadas de solicitudes.
3. Polling sólo permanece activo para estados no terminales.
4. Reintentos no duplican acciones mutables.
5. Errores preservan código y mensaje sanitizado.
6. Consultas independientes se paralelizan.

**Verificación:**

```powershell
cd frontend
npm run type-check
npm run build
```

**Commit:** `feat: add file backup frontend data layer`

### Tarea 22. Construir pantalla principal intuitiva

**Archivos:**

- Crear `frontend/src/app/dashboard/file-backups/page.tsx`.
- Crear `frontend/src/components/file-backups/file-backup-list.tsx`.
- Crear `frontend/src/components/file-backups/file-backup-row.tsx`.
- Crear `frontend/src/components/file-backups/file-backup-run-journey.tsx`.
- Crear `frontend/src/components/file-backups/file-backup-alert.tsx`.
- Modificar `frontend/src/components/layout/sidebar.tsx`.

**Checkpoint visual obligatorio:**

```text
Intent: operador no especialista que necesita confirmar qué está protegido y actuar ante una alerta.
Palette: superficies carbon/musgo existentes; azul sólo para control; verde/ámbar/rojo sólo para estado.
Depth: bordes suaves y cambios mínimos de superficie, sin sombras de tarjetas.
Surfaces: lista principal plana, fila expandida y una alerta prioritaria.
Typography: Segoe UI/Inter; monospace sólo para rutas y hashes.
Spacing: base 4 px; radio pequeño de 4–7 px.
```

**Criterios:**

- Encabezados `Qué se respalda`, `Dónde se guarda`, `Próxima copia`, `Estado`.
- Sin cuadrícula de KPIs ni tarjetas bento.
- Una alerta prioritaria accionable.
- Fila expandida `Copiado → Verificado → Entregado`.
- Acciones `Restaurar`, `Ver detalles` y menú secundario.
- Estados de loading, vacío, error, offline e incompatible.
- Módulo oculto si ningún agente soporta `file_backup_v1`.
- Navegación por teclado y nombres accesibles.

**Commit:** `feat: add intuitive file backup workspace`

### Tarea 23. Implementar asistente lateral de cuatro pasos

**Archivos:**

- Crear `frontend/src/components/file-backups/file-backup-wizard.tsx`.
- Crear componentes pequeños por paso bajo `frontend/src/components/file-backups/wizard/`.
- Reutilizar `AgentSelector` y perfiles administrados.
- Crear `frontend/src/hooks/useFileBackupWizard.ts` si el estado lo justifica.

**Criterios/pruebas:**

1. Flujo `Qué proteger → Dónde guardarlo → Cuándo y cómo → Revisar`.
2. Reabre exactamente el paso fallido.
3. Filtros avanzados permanecen colapsados por defecto.
4. No activa sin simulación y prueba del destino.
5. Agente offline permite guardar borrador, no activar.
6. Navegador nunca recibe secretos existentes.
7. Cambio de agente limpia selecciones incompatibles.
8. Cierre accidental conserva borrador local no sensible durante la sesión.

**Commit:** `feat: guide file backup task creation`

### Tarea 24. Construir historial y restauración

**Archivos:**

- Crear `frontend/src/components/file-backups/file-backup-history.tsx`.
- Crear `frontend/src/components/file-backups/file-restore-wizard.tsx`.
- Crear `frontend/src/components/file-backups/restore-conflict-review.tsx`.
- Modificar `frontend/src/app/dashboard/file-backups/page.tsx`.

**Criterios/pruebas:**

1. Historial filtra por tarea, fecha y estado.
2. Cadena técnica se muestra sólo en detalles avanzados.
3. Restauración exige seleccionar fecha, archivos y destino.
4. Simulación muestra nuevos/reemplazos/idénticos/conflictos.
5. Confirmación resume exactamente lo que se sobrescribirá.
6. Progreso sobrevive cerrar el panel.
7. Resultado permite descargar/ver auditoría sin exponer secretos.

**Commit:** `feat: add file backup history and restore flow`

---

## Entrega 7 — Empaquetado, compatibilidad y piloto

### Tarea 25. Versionar y empaquetar agente 0.5.0

**Archivos:**

- Modificar `agent/data_express_agent/config.py`.
- Modificar `agent/build.ps1`.
- Modificar `agent/package.ps1`.
- Modificar `agent/installer/Update-DataExpressAgent.ps1`.
- Modificar `agent/installer/README-INSTALACION.txt`.
- Crear/actualizar notas operativas en `docs/`.

**Pruebas:**

1. `VERSION.txt` y metadata reportan 0.5.0.
2. Paquete incluye bootstrap y dependencias SQLite/VSS necesarias.
3. Actualización 0.4.2 → 0.5.0 conserva SQL, identidad, perfiles y journal.
4. Catálogo local nuevo se crea sin afectar otras bases.
5. Healthcheck posterior exige heartbeat 0.5.0 y capacidad `file_backup_v1`.
6. Rollback vuelve a 0.4.2 sin intentar abrir catálogo nuevo.
7. Instalación nueva sólo solicita pairing code.

**Build:**

```powershell
powershell -ExecutionPolicy Bypass -File agent\build.ps1
powershell -ExecutionPolicy Bypass -File agent\package.ps1 -Version 0.5.0
```

**Commit:** `release: package Data Express Agent 0.5.0`

### Tarea 26. Ejecutar verificación integral automatizada

```powershell
backend\.venv\Scripts\python.exe -m pytest -q backend\tests backend\tests_prod agent\tests
backend\.venv\Scripts\alembic.exe -c backend\alembic.ini heads

cd frontend
npm run type-check
npm run build

cd ..
powershell -ExecutionPolicy Bypass -File agent\build.ps1
powershell -ExecutionPolicy Bypass -File agent\package.ps1 -Version 0.5.0
```

**Criterios:**

- Un head Alembic `0011`.
- Ninguna regresión SQL, limpieza, heartbeat, perfiles o almacenamiento.
- Ningún secreto en logs, fixtures, respuestas o artefactos de prueba.
- Build reproducible del paquete.
- Contratos OpenAPI y frontend alineados.

**Commit:** `test: verify file backup release contracts`

### Tarea 27. Validar servidor piloto

**Preparación:**

- Crear conjunto controlado con archivos pequeños, grandes, bloqueados, rutas largas y ACL.
- Configurar destinos local, UNC y SFTP de prueba.
- Registrar hashes de origen antes de comenzar.

**Pruebas piloto:**

1. Actualizar agente 0.4.2 a 0.5.0.
2. Confirmar que backups SQL siguen funcionando.
3. Crear tarea sin editar JSON.
4. Ejecutar Full local y UNC.
5. Modificar/agregar/eliminar archivos y ejecutar incremental.
6. Ejecutar diferencial desde el mismo Full.
7. Reiniciar servicio durante copia y continuar.
8. Desconectar destino y continuar al recuperarlo.
9. Validar VSS con archivo abierto.
10. Proteger una cadena y probar retención.
11. Simular restauración al origen y ubicación alternativa.
12. Restaurar muestra y comparar todos los hashes.
13. Probar SFTP con huella fija.
14. Observar heartbeat, CPU, memoria, disco y red.

**Bloqueos de despliegue:**

- pérdida o corrupción de un archivo validado;
- restauración con hash diferente;
- ruta fuera de alcance;
- secreto visible;
- heartbeat detenido;
- backup SQL afectado;
- retención que elimina una copia protegida o el único Full;
- imposibilidad de reanudar después de reinicio;
- más de un head Alembic;
- rollback 0.5.0 → 0.4.2 fallido.

**Resultado:** documento de piloto con hashes, tiempos, incidencias y decisión de habilitación.

**Commit:** `docs: record file backup pilot results`

### Tarea 28. Desplegar de forma escalonada

1. Push de rama y revisión de CI.
2. Desplegar backend compatible y esperar `/health/ready` correcto.
3. Desplegar frontend con feature gate cerrado.
4. Actualizar únicamente el agente piloto.
5. Completar Tarea 27 y observar siete días.
6. Habilitar módulo al tenant piloto.
7. Actualizar los demás agentes por lotes.
8. Abrir feature gate sólo para agentes 0.5.0 saludables.
9. Fusionar a `main` cuando el piloto cumpla todos los criterios.
10. Publicar paquete 0.5.0 y guía de instalación de un solo código.

**Commit final:** `release: enable managed file backups`

## Orden recomendado de commits

```text
feat: add file backup persistence schema
feat: define file backup API contracts
feat: manage file backup tasks by tenant
feat: add file backup agent protocol
feat: separate agent bootstrap from managed config
feat: install agent with pairing code only
feat: migrate legacy agent profiles safely
feat: add durable file backup catalog
feat: validate file backup paths and filters
feat: scan and simulate file backup changes
feat: coordinate backup disk resources
feat: snapshot locked files with VSS
feat: add file backup destination adapters
feat: copy and verify files with checkpoints
feat: track file backup manifests and chains
feat: support bounded zip64 file backups
feat: retain complete file backup chains safely
feat: schedule and reconcile file backups
feat: simulate file restores safely
feat: restore and verify protected files
feat: add file backup frontend data layer
feat: add intuitive file backup workspace
feat: guide file backup task creation
feat: add file backup history and restore flow
release: package Data Express Agent 0.5.0
test: verify file backup release contracts
docs: record file backup pilot results
release: enable managed file backups
```

## Resultado esperado

Al completar las 28 tareas, un administrador instalará el agente introduciendo un único código, configurará conexiones y tareas desde el dashboard, ejecutará respaldos Full/incrementales/diferenciales verificables, reanudará interrupciones, conservará cadenas seguras y restaurará archivos después de revisar una simulación. Los backups SQL existentes continuarán disponibles durante toda la migración.
