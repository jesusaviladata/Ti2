# Plan de implementación: agentes, backups, automatización y limpieza

**Especificación:** [`docs/superpowers/specs/2026-08-20-agent-backup-cleanup-dashboard-design.md`](../specs/2026-08-20-agent-backup-cleanup-dashboard-design.md)

**Objetivo:** migrar la operación visible a agentes Windows, separar respaldo y entrega, implementar automatización semanal y reemplazar la limpieza SFTP/FTP por limpieza estructural directa y manual.

## Reglas de ejecución

- Trabajar sobre una rama o worktree dedicado antes de modificar código.
- El checkout actual contiene cambios del agente sin versionar. No descartarlos, sobrescribirlos ni mezclarlos con cambios ajenos.
- Cada tarea debe comenzar con una prueba que falle por el comportamiento esperado, implementar el cambio mínimo y terminar con las verificaciones indicadas.
- Cada commit incluirá únicamente los archivos de su tarea.
- No eliminar código o tablas heredadas durante esta entrega. Primero se ocultan, se dejan sin consumidores y se comprueba telemetría.
- No desplegar Limpieza directa hasta completar una prueba controlada en Windows con una copia de datos.

## Resultado arquitectónico

```text
Frontend
  ├─ Configuración → Agentes
  ├─ Backups → AgentSelector → BackupRun
  └─ Limpieza → simulación → confirmación → ejecución
          │
          ▼
Backend FastAPI
  ├─ inventario/configuración de agentes
  ├─ orquestación de BackupRun y Delivery
  ├─ planes semanales
  └─ simulaciones/ejecuciones de limpieza
          │ órdenes tipadas, firmadas e idempotentes
          ▼
Agente Windows
  ├─ SQL BACKUP + RESTORE VERIFYONLY
  ├─ ZIP + transferencia + SHA-256 remoto
  └─ recorrido estructural + eliminación directa
```

## Fase 0. Reconciliar la base de trabajo

### Tarea 1. Establecer una revisión única del agente

**Archivos a inspeccionar y versionar de forma deliberada:**

- `agent/data_express_agent/backup.py`
- `agent/data_express_agent/cleanup.py`
- `agent/data_express_agent/runner.py`
- `agent/data_express_agent/config.py`
- `agent/data_express_agent/client.py`
- `agent/installer/Update-DataExpressAgent.ps1`
- `agent/installer/agent-profiles.example.json`
- resto de cambios ya presentes bajo `agent/`

**Pasos:**

1. Crear rama/worktree para esta entrega y registrar `git status`, `git diff` y archivos no rastreados.
2. Comparar cada cambio del agente con la bitácora y con la especificación aprobada.
3. Separar cambios funcionales de cambios de empaquetado/instalación.
4. Ejecutar las pruebas existentes antes de modificar comportamiento.
5. Versionar la base reconciliada en commits estrechos; no incluir la bitácora si no se decide expresamente.

**Verificación:**

```powershell
cd agent
python -m pytest tests -q
```

**Criterio de salida:** `backup.py` y `cleanup.py` están rastreados, el runner los importa desde una revisión reproducible y las pruebas existentes pasan.

## Fase 1. Endurecer el agente

### Tarea 2. Hacer estricta la validación del `.bak`

**Modificar:**

- `agent/data_express_agent/backup.py`
- `agent/data_express_agent/runner.py`

**Crear:**

- `agent/tests/test_backup.py`

**Pruebas primero:**

1. `RESTORE VERIFYONLY ... WITH CHECKSUM` satisfactorio produce `backupStatus=ready` y `validationMethod=restore_verifyonly`.
2. Falta de permiso para `RESTORE VERIFYONLY` produce error de validación; no acepta existencia, tamaño o SHA como sustituto.
3. Archivo ausente, vacío o modificado durante validación produce fallo.
4. El evento de progreso `backup_ready` ocurre antes de cualquier fase ZIP.

**Implementación:**

- Eliminar el fallback que devuelve `file_sha256` como validación suficiente.
- Separar las fases emitidas por el agente: `creating_bak`, `validating_bak`, `backup_ready`, `compressing`, `transferring`, `delivered`.
- Incluir metadatos por base: ruta, tamaño, SHA-256, método y hora de validación.
- Excluir del postprocesamiento cualquier `.bak` inválido. Los respaldos válidos del mismo lote podrán continuar a entrega y la corrida quedará como parcial con detalle por base.

**Verificación:**

```powershell
cd agent
python -m pytest tests/test_backup.py tests/test_runner.py -q
```

**Commit sugerido:** `fix(agent): require SQL validation before backup ready`

### Tarea 3. Separar respaldo y entrega reintentable en el agente

**Modificar:**

- `agent/data_express_agent/backup.py`
- `agent/data_express_agent/runner.py`
- `agent/data_express_agent/journal.py`

**Pruebas en:**

- `agent/tests/test_backup.py`
- `agent/tests/test_runner.py`

**Pruebas primero:**

1. Un ZIP fallido conserva el resultado durable de los `.bak` validados.
2. `retry_backup_delivery` reutiliza el mismo run y no ejecuta SQL BACKUP.
3. Una entrega interrumpida conserva el `.partial` hasta aplicar la política de recuperación.
4. La limpieza de temporales ocurre solo después de confirmar el artefacto final.
5. Una orden repetida con la misma idempotency key devuelve el resultado previo.

**Implementación:**

- Agregar el comando tipado `retry_backup_delivery` al runner.
- Persistir en journal el resultado primario antes de crear el ZIP.
- Modelar el postprocesamiento como un paso reiniciable que recibe `runId` y artefactos ya validados.
- Mantener los `.bak` necesarios hasta que la entrega termine o hasta que una política explícita permita descartarlos.

**Verificación:**

```powershell
cd agent
python -m pytest tests/test_backup.py tests/test_runner.py -q
```

**Commit sugerido:** `feat(agent): make backup delivery independently retryable`

### Tarea 4. Verificar contenido remoto y corregir el actualizador

**Modificar:**

- `agent/data_express_agent/backup.py`
- `agent/installer/Update-DataExpressAgent.ps1`
- `agent/installer/README-INSTALACION.txt`

**Pruebas en:**

- `agent/tests/test_backup.py`

**Pruebas primero:**

1. SMB compara tamaño y SHA-256 del archivo final antes de declarar entrega.
2. SFTP vuelve a leer el archivo remoto para calcular SHA-256; tamaño igual con contenido distinto falla.
3. El nombre `.partial` nunca se reporta como entregado.
4. Una falla de hash conserva información suficiente para reintentar.

**Actualizador:**

- Esperar que WinSW confirme el servicio detenido.
- Esperar la salida real del PID del agente y de procesos hijos antes de mover el bundle.
- Reintentar reemplazos por bloqueo durante un intervalo acotado.
- Mantener rollback atómico a `previous` si el nuevo servicio no inicia.
- Validar específicamente que `_bcrypt.pyd` pueda reemplazarse.

**Verificación:**

```powershell
cd agent
python -m pytest tests/test_backup.py -q
.\build.ps1
```

Además, ejecutar instalación → actualización → rollback en una VM Windows limpia.

**Commit sugerido:** `fix(agent): verify remote artifacts and wait for updater locks`

### Tarea 5. Ajustar la limpieza estructural a la política aprobada

**Modificar:**

- `agent/data_express_agent/cleanup.py`
- `agent/data_express_agent/runner.py`

**Crear:**

- `agent/tests/test_cleanup.py`

**Pruebas primero:**

1. Solo acepta propiedades hijas directas de la raíz.
2. Solo recorre `core/Log`, `LogSec`, `LogsRadian`, `Respuesta` y `BD_log.txt`.
3. Incluye todos los archivos normales dentro de las carpetas, sin filtro por edad.
4. Conserva carpetas y subcarpetas después de ejecutar.
5. Rechaza raíz de disco, rutas fuera de raíz, symlinks y reparse points.
6. Cambios de tamaño, fecha, raíz o configuración invalidan el manifiesto.
7. Una ejecución directa interrumpida no se reinicia automáticamente.
8. Archivos bloqueados producen resultado parcial con advertencias.

**Implementación:**

- Sustituir la protección basada principalmente en extensiones por una frontera basada en ruta resuelta y objetivos estructurales fijos.
- Conservar límites operativos de propiedades, archivos y bytes como guardas, no como selectores funcionales.
- Incluir `configurationHash`, `manifestHash`, `simulatedAt` y `expiresAt` en el resultado.
- Mantener `execute_structural_quarantine` solo por compatibilidad interna; el frontend nuevo no lo consumirá.

**Verificación:**

```powershell
cd agent
python -m pytest tests/test_cleanup.py tests/test_runner.py tests/test_explorer.py -q
```

**Commit sugerido:** `feat(agent): enforce fixed-root direct cleanup policy`

## Fase 2. Persistencia y contratos backend

### Tarea 6. Agregar modelos durables de corrida, entrega y plan semanal

**Crear:**

- `backend/app/models/backup_run.py`
- `backend/app/models/backup_plan.py`
- `backend/alembic/versions/0005_agent_backup_delivery_cleanup.py`

**Modificar:**

- `backend/app/models/backup.py`
- `backend/app/models/operations.py`
- `backend/app/models/__init__.py`

**Crear pruebas:**

- `backend/tests/test_agent_backup_models.py`
- `backend/tests/test_agent_cleanup_models.py`

**Modelo propuesto:**

- `BackupRun`: tenant, agente, perfil SQL, destino, origen manual/programado, command id, estado primario, fase/progreso, estado de entrega, fase/progreso, ZIP y errores.
- `Backup`: referencia a `BackupRun`, base, tipo, estado, validación, `.bak` y timestamps.
- `BackupPlan`: agente, perfil SQL, destino, lista de bases, hora, zona horaria, días Full, días Diferencial, activo y último Full válido.
- `RemoteCleanupExecution`: agregar agente, simulación/manifiesto, expiración, conteos y estado parcial.

**Restricciones:**

- Enumeraciones o checks para estados conocidos.
- Índices por tenant/estado/fecha y por agente/estado.
- Idempotencia única para corridas programadas por plan, base y ventana.
- Días guardados como valores canónicos `mon` a `sun`; no guardar siglas de presentación.
- Una simulación expira a los 30 minutos y solo puede consumirse una vez.

**Verificación:**

```powershell
cd backend
python -m pytest tests/test_agent_backup_models.py tests/test_agent_cleanup_models.py -q
alembic upgrade head
alembic downgrade -1
alembic upgrade head
```

**Commit sugerido:** `feat(backend): persist agent backup and cleanup lifecycle`

### Tarea 7. Completar la allowlist y los resultados de comandos

**Modificar:**

- `backend/app/services/agent_command_service.py`
- `backend/app/api/agent.py`
- `backend/app/schemas/agent.py`
- `backend/app/repositories/agent_repository.py`

**Crear pruebas:**

- `backend/tests/test_agent_commands.py`

**Órdenes permitidas:**

- `list_sql_databases`
- `run_backup_batch`
- `retry_backup_delivery`
- `simulate_structural_cleanup`
- `execute_structural_direct`
- comandos existentes de exploración, validación y cancelación

**Pruebas primero:**

1. Cada orden nueva se acepta con agente y tenant correctos.
2. Una orden desconocida continúa rechazada.
3. El resultado de una fase actualiza `BackupRun` o `RemoteCleanupExecution` en la misma transacción.
4. Resultados repetidos son idempotentes.
5. Un agente revocado o incompatible no recibe órdenes.
6. El progreso distingue unidades procesadas, totales, fase primaria y fase de entrega.

**Verificación:**

```powershell
cd backend
python -m pytest tests/test_agent_commands.py -q
```

**Commit sugerido:** `feat(backend): allow typed backup and direct cleanup commands`

### Tarea 8. Exponer inventario y configuración de agentes a operaciones

**Modificar:**

- `backend/app/api/v1/agents.py`
- `backend/app/services/agent_admin_service.py`
- `backend/app/repositories/agent_admin_repository.py`

**Crear pruebas:**

- `backend/tests/test_agents_api.py`

**Contratos:**

- `GET /api/v1/agents`: lectura operativa; devuelve estado derivado de `lastSeenAt`, metadata pública, configuración y compatibilidad.
- Endpoints de vinculación, reemplazo, revocación y edición continúan limitados a administradores.
- `GET /api/v1/agents/{id}/profiles`: perfiles SQL y destinos públicos enviados por heartbeat.
- Exploración y validación de raíz continúan como jobs.
- Guardar configuración fuerza los objetivos estructurales del servidor; no acepta objetivos arbitrarios del navegador.

**Pruebas primero:** permisos por rol, autoestado offline, una sola configuración activa por agente y rechazo de validación antigua.

**Verificación:**

```powershell
cd backend
python -m pytest tests/test_agents_api.py -q
```

**Commit sugerido:** `feat(backend): expose operational agent inventory and profiles`

## Fase 3. Corte vertical de Limpieza

### Tarea 9. Orquestar simulación y ejecución directa por agente

**Crear:**

- `backend/app/services/agent_cleanup_service.py`
- `backend/app/repositories/agent_cleanup_repository.py`
- `backend/tests/test_agent_cleanup_service.py`

**Modificar:**

- `backend/app/api/v1/cleanup_runtime.py`
- `backend/app/api/v1/__init__.py` si requiere montar rutas adicionales

**Endpoints propuestos:**

- `POST /api/v1/cleanup/agent/simulations`
- `GET /api/v1/cleanup/agent/simulations/{id}`
- `POST /api/v1/cleanup/agent/simulations/{id}/execute`
- `GET /api/v1/cleanup/agent/executions`
- `GET /api/v1/cleanup/agent/executions/{id}`

**Pruebas primero:**

1. Simular exige agente conectado y configuración validada.
2. El payload usa exclusivamente raíz y objetivos guardados en backend.
3. Ejecutar exige simulación completada, vigente y no consumida.
4. Conteo, configuración y manifest hash deben coincidir.
5. El resultado parcial se serializa como `completed_with_warnings`.
6. No se crean registros de cuarentena.

**Verificación:**

```powershell
cd backend
python -m pytest tests/test_agent_cleanup_service.py -q
```

**Commit sugerido:** `feat(cleanup): orchestrate agent simulations and direct execution`

### Tarea 10. Migrar el frontend de Limpieza

**Crear:**

- `frontend/src/types/agent.ts`
- `frontend/src/types/agent-cleanup.ts`
- `frontend/src/services/agents.service.ts`
- `frontend/src/services/agent-cleanup.service.ts`
- `frontend/src/hooks/useAgents.ts`
- `frontend/src/hooks/useAgentCleanup.ts`
- `frontend/src/components/agents/agent-selector.tsx`
- `frontend/src/components/cleanup/cleanup-phase-rail.tsx`
- `frontend/src/components/cleanup/agent-cleanup-panel.tsx`
- `frontend/src/components/cleanup/cleanup-simulation-summary.tsx`
- `frontend/vitest.config.ts`
- `frontend/src/test/setup.ts`

**Modificar:**

- `frontend/src/app/dashboard/limpieza-remota/page.tsx`
- `frontend/package.json`
- `frontend/package-lock.json`

**Retirar de esta página:** credenciales, `.pem`, explorador SFTP/FTP, modo por reglas y pestaña Cuarentena.

**Estados requeridos:** cargando agentes, sin agentes, agente offline, sin raíz, simulando, simulación fallida, lista para confirmar, ejecutando, completada, completada con advertencias y fallida.

**Pruebas:** agregar Vitest y Testing Library si aún no existen, y crear:

- `frontend/src/components/cleanup/agent-cleanup-panel.test.tsx`
- `frontend/src/components/agents/agent-selector.test.tsx`

**Verificación:**

```powershell
cd frontend
npm run type-check
npm run test -- --run
npm run build
```

**Commit sugerido:** `feat(frontend): replace remote cleanup with agent workflow`

## Fase 4. Corte vertical de Backups

### Tarea 11. Orquestar bases y backups mediante agente

**Crear:**

- `backend/app/services/agent_backup_service.py`
- `backend/app/repositories/agent_backup_repository.py`
- `backend/tests/test_agent_backup_service.py`
- `backend/tests/test_agent_backups_api.py`

**Modificar:**

- `backend/app/api/v1/backups_runtime.py`
- `backend/app/services/backup_serializers.py`

**Contratos propuestos:**

- `GET /api/v1/backups/agents/{agentId}/databases?sqlProfileId=...`
- `POST /api/v1/backups/runs`
- `GET /api/v1/backups/runs/{runId}`
- `POST /api/v1/backups/runs/{runId}/retry-delivery`
- `GET /api/v1/backups` conserva la lista por base e incorpora estado de entrega.

**Pruebas primero:**

1. Un run crea registros por base y una orden batch de máximo 100 bases.
2. `backup_ready` finaliza el estado primario sin esperar ZIP.
3. Eventos posteriores solo modifican entrega.
4. Un fallo de entrega no altera respaldos listos.
5. Reintento crea una orden de entrega, no una nueva corrida SQL.
6. Fallo de validación no inicia entrega.
7. Una base fallida no impide entregar los `.bak` válidos del mismo lote; la corrida queda parcial.
8. Agente offline, perfil inexistente y orden duplicada producen errores tipados.

**Verificación:**

```powershell
cd backend
python -m pytest tests/test_agent_backup_service.py tests/test_agent_backups_api.py -q
```

**Commit sugerido:** `feat(backups): orchestrate agent runs and delivery states`

### Tarea 12. Rediseñar Nuevo Backup y el progreso

**Crear:**

- `frontend/src/components/backups/backup-primary-progress.tsx`
- `frontend/src/components/backups/backup-delivery-progress.tsx`
- `frontend/src/components/backups/agent-backup-form.tsx`
- `frontend/src/components/backups/backup-run-progress.test.tsx`

**Modificar:**

- `frontend/src/components/backups/trigger-backup-modal.tsx`
- `frontend/src/components/backups/backup-list.tsx`
- `frontend/src/components/backups/backup-status-badge.tsx`
- `frontend/src/hooks/useBackups.ts`
- `frontend/src/services/backups.service.ts`
- `frontend/src/types/backup.ts`
- `frontend/src/app/dashboard/backups/page.tsx`

**Retirar del flujo visible:**

- `ConnectionPayload` en consultas y ejecuciones nuevas.
- selector superior basado en `connections.store`.
- pestaña o botón `Conexión directa`.

**Comportamiento:**

- `AgentSelector` vive en el chrome de Backups.
- El único agente conectado se autoselecciona.
- La barra principal termina en `Respaldo listo`.
- ZIP y envío aparecen en una segunda línea.
- La tabla separa respaldo y entrega y ofrece `Reintentar entrega` cuando corresponde.
- Las métricas cuentan `.bak` validados.

**Verificación:**

```powershell
cd frontend
npm run type-check
npm run test -- --run
npm run build
```

**Commit sugerido:** `feat(frontend): show backup readiness separately from delivery`

## Fase 5. Automatización semanal

### Tarea 13. Implementar planes Full/Diferencial

**Crear:**

- `backend/app/services/backup_plan_service.py`
- `backend/app/repositories/backup_plan_repository.py`
- `backend/tests/test_backup_plans.py`
- `backend/tests/test_backup_plan_scheduler.py`

**Modificar:**

- `backend/app/api/v1/backups_runtime.py`
- `backend/app/core/scheduler.py`
- `backend/app/tasks/scheduled_backup.py`

**Endpoints:**

- `GET /api/v1/backups/plans`
- `POST /api/v1/backups/plans`
- `PUT /api/v1/backups/plans/{id}`
- `DELETE /api/v1/backups/plans/{id}`

**Pruebas primero:**

1. Full exige al menos un día.
2. Diferencial acepta lista vacía.
3. Los conjuntos no pueden solaparse.
4. Un Diferencial sin Full válido se convierte en Full y registra el motivo.
5. Un Full satisfactorio actualiza la base para diferenciales.
6. Fallos de Full no habilitan diferenciales.
7. La idempotencia evita dos corridas para plan/base/ventana.
8. La zona horaria del plan calcula correctamente el siguiente disparo.

**Verificación:**

```powershell
cd backend
python -m pytest tests/test_backup_plans.py tests/test_backup_plan_scheduler.py -q
```

**Commit sugerido:** `feat(backups): add weekly full and differential plans`

### Tarea 14. Construir el selector semanal

**Crear:**

- `frontend/src/components/backups/weekly-backup-scheduler.tsx`
- `frontend/src/components/backups/weekly-backup-scheduler.test.tsx`

**Modificar:**

- `frontend/src/app/dashboard/backups/page.tsx`
- `frontend/src/hooks/useBackups.ts`
- `frontend/src/services/backups.service.ts`
- `frontend/src/types/backup.ts`

**Comportamiento probado:**

- Siglas exactas `L`, `Ma`, `Mi`, `J`, `V`, `S`, `D`.
- Selección excluyente entre Full y Diferencial.
- Diferencial opcional.
- Resumen `Full L/Mi/V · Diferencial Ma/J` o Full-only.
- Estados de crear, editar, desactivar y error.
- Controles accesibles por teclado y con `aria-pressed`.

**Verificación:**

```powershell
cd frontend
npm run type-check
npm run test -- --run
npm run build
```

**Commit sugerido:** `feat(frontend): add weekly backup day selector`

## Fase 6. Administración de agentes y consistencia visual

### Tarea 15. Sustituir Configuración → Servidores por Agentes

**Crear:**

- `frontend/src/components/agents/agents-admin.tsx`
- `frontend/src/components/agents/agent-root-wizard.tsx`
- `frontend/src/components/agents/agent-status.tsx`
- `frontend/src/components/agents/agents-admin.test.tsx`
- `frontend/src/components/agents/agent-root-wizard.test.tsx`

**Modificar:**

- `frontend/src/app/dashboard/settings/page.tsx`

**Dejar sin consumidores:**

- `frontend/src/components/cleanup/server-admin.tsx`
- operaciones de alta SFTP/FTP en `frontend/src/services/remote-cleanup.service.ts`

**Flujo:** vincular → esperar aparición → explorar → elegir raíz → validar → guardar. El wizard no permite omitir la configuración inicial.

**Verificación:**

```powershell
cd frontend
npm run type-check
npm run test -- --run
npm run build
```

**Commit sugerido:** `feat(frontend): manage Windows agents and validated roots`

### Tarea 16. Unificar tipografía numérica y estados operativos

**Modificar:**

- `frontend/src/app/globals.css`
- `frontend/src/app/dashboard/page.tsx`
- `frontend/src/app/dashboard/backups/page.tsx`
- páginas de dashboard que usen `font-display` o `font-title` exclusivamente para cifras
- componentes de métricas compartidos que se identifiquen durante la búsqueda

**Crear si evita duplicación:**

- `frontend/src/components/ui/metric-value.tsx`
- `frontend/src/components/ui/operation-phase-rail.tsx`

**Pruebas/comprobaciones:**

- Buscar cifras métricas con familia serif/cursiva y migrarlas a sans-serif.
- Aplicar `font-variant-numeric: tabular-nums` a valores alineados.
- Conservar mono únicamente para rutas, IDs, versiones y telemetría.
- Reutilizar la línea de fases en Backup, Entrega y Limpieza.
- Verificar contraste, foco, estados loading/empty/error y reflujo móvil.

**Verificación:**

```powershell
cd frontend
npm run type-check
npm run test -- --run
npm run build
```

Realizar inspección visual a 360 px, 736 px y escritorio.

**Commit sugerido:** `style(frontend): unify dashboard metrics and operation phases`

## Fase 7. Retiro controlado del legado

### Tarea 17. Ocultar conexiones directas y rutas SFTP/FTP

**Modificar:**

- configuración de flags en `backend/app/core/config.py`
- `frontend/src/components/backups/connection-dropdown.tsx`
- `frontend/src/components/backups/sql-connection-modal.tsx`
- `frontend/src/store/connections.store.ts`
- `frontend/src/services/remote-cleanup.service.ts`
- navegación o imports que todavía expongan el legado

**Reglas:**

- El frontend de producción no importa ni renderiza estos componentes.
- Los endpoints heredados permanecen temporalmente detrás de una bandera desactivada por defecto.
- Registrar uso residual antes de eliminar código o tablas en otra entrega.
- Añadir pruebas que confirmen que la bandera no permite acceso accidental.

**Verificación:**

```powershell
cd backend
python -m pytest -q
cd ..\frontend
npm run type-check
npm run test -- --run
npm run build
```

**Commit sugerido:** `chore: disable legacy direct and remote-cleanup flows`

## Fase 8. Validación integral y entrega

### Tarea 18. Ejecutar pruebas end-to-end con agente Windows

**Crear:**

- `docs/operations/agent-backup-cleanup-acceptance.md`
- fixtures o scripts de prueba no destructivos bajo `scripts/` si son necesarios

**Escenarios obligatorios:**

1. Vincular agente nuevo y configurar raíz.
2. Detectar perfiles SQL/destinos mediante heartbeat.
3. Ejecutar un Full de dos bases: `.bak` válido, ZIP y entrega.
4. Interrumpir SFTP después de validar `.bak`; comprobar `Respaldo listo · Entrega fallida`.
5. Reintentar entrega y confirmar que no aparece otro SQL BACKUP.
6. Programar Full-only.
7. Programar Full + Diferencial y comprobar exclusión de días.
8. Disparar Diferencial sin base y confirmar Full inicial.
9. Simular limpieza sobre una copia controlada con varias propiedades.
10. Alterar un archivo entre simulación y confirmación y comprobar rechazo.
11. Ejecutar limpieza; comprobar archivos eliminados, carpetas intactas e historial.
12. Bloquear un archivo; comprobar `Completada con advertencias`.
13. Desconectar el agente durante una operación y comprobar journal/reporte al reconectar.
14. Actualizar el agente y comprobar reemplazo de `_bcrypt.pyd` y rollback.

**Verificación completa:**

```powershell
cd backend
python -m pytest -q
cd ..\agent
python -m pytest tests -q
cd ..\frontend
npm run type-check
npm run test -- --run
npm run build
```

**Criterio de salida:** todos los escenarios tienen evidencia, no existen falsos positivos de validación, no se repite un `.bak` durante reintento de entrega y Limpieza no modifica rutas fuera del manifiesto.

**Commit sugerido:** `test: document agent backup and cleanup acceptance`

## Orden de despliegue

1. Migración de base de datos.
2. Backend compatible con agente viejo y nuevo, con funciones nuevas todavía no visibles.
3. Agente actualizado en un servidor piloto.
4. Pruebas de Backups y Limpieza en el piloto.
5. Frontend nuevo detrás de bandera.
6. Activación para administradores internos.
7. Activación general del flujo por agente.
8. Desactivación del frontend heredado.
9. Observación de telemetría antes de programar la eliminación definitiva del legado.

## Condiciones para detener el despliegue

- El `.bak` aparece listo sin `RESTORE VERIFYONLY` satisfactorio.
- Una entrega reintentada vuelve a ejecutar SQL BACKUP.
- El hash remoto no coincide con el local.
- Una simulación puede ejecutarse después de cambiar archivos o configuración.
- La limpieza elimina una carpeta o alcanza una ruta fuera de la raíz.
- Una orden destructiva se reinicia automáticamente después de interrupción.
- El actualizador no puede reemplazar binarios o no restaura la versión anterior.
- El frontend permite operar sin agente seleccionado o con agente incompatible.
