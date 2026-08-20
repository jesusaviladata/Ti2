# Plan de implementación: almacenamiento, conexiones y confiabilidad del agente

**Especificación:** `docs/superpowers/specs/2026-08-20-agent-storage-connections-reliability-design.md`  
**Versión objetivo del agente:** 0.4.0  
**Estrategia:** backend compatible primero, agente después, frontend al final de cada contrato

## Objetivo de ejecución

Entregar nombres diarios deterministas, origen visible, estado de entrega confiable, telemetría preventiva de disco, heartbeat independiente, perfiles administrables y un único módulo de Limpieza sin interrumpir agentes 0.3.0 ya instalados.

## Reglas de trabajo

- Cada bloque comienza con una prueba que falle por la ausencia del comportamiento.
- Las migraciones son sólo hacia adelante y conservan un único `head` de Alembic.
- El backend debe aceptar heartbeat de 0.3.0 durante toda la migración.
- No se elimina código heredado en la misma versión en la que se retiran sus consumidores.
- Ningún secreto aparece en fixtures, logs, respuestas API o commits.
- Cada commit listado es un punto reversible y desplegable.
- `BITACORA_CHAT_AGENTE_BACKUPS.md` permanece fuera de Git.

## Línea base

Antes de editar:

```powershell
cd "C:\Users\quech\OneDrive\Documentos\GESTOR PRIMEE\infra-platform"
git status --short
backend\.venv\Scripts\python.exe -m pytest -q backend\tests backend\tests_prod agent\tests
cd frontend
npm run type-check
npm run build
```

Registrar el commit inicial y no continuar si falla una prueba no relacionada.

---

## Entrega 1 — Contratos y persistencia compatibles

### Tarea 1. Crear modelos de origen, telemetría y perfiles

**Archivos:**

- Modificar `backend/app/models/backup.py`.
- Modificar `backend/app/models/operations.py`.
- Modificar `backend/app/models/__init__.py`.
- Crear `backend/alembic/versions/0008_agent_storage_and_profiles.py`.
- Crear `backend/tests_prod/test_agent_storage_profiles_migration.py`.
- Modificar `backend/tests_prod/test_agent_models.py`.

**Pruebas primero:**

1. Afirmar que `backups` contiene `origin_snapshot` JSONB.
2. Afirmar que `remote_agents` contiene `encryption_public_key`, `last_heartbeat_at`, `desired_config_revision`, `applied_config_revision` y `health_status`.
3. Afirmar tablas:
   - `agent_volume_states` con unicidad tenant/agente/volumen;
   - `agent_storage_alerts` con estado abierto/resuelto;
   - `agent_connection_profiles` con clase SQL/destino, configuración pública, sobre cifrado, revisión y estado.
4. Afirmar índices para agentes, alertas abiertas y perfiles activos.
5. Comprobar `down_revision = "0007"` y ausencia de múltiples heads.

**Implementación:**

- `origin_snapshot` será nullable para registros 0.3.0.
- Los perfiles tendrán `profile_type`, `profile_key`, `label`, `public_config`, `secret_envelope`, `desired_revision`, `applied_revision`, `sync_status`, `last_test_status`, `last_test_at`, `last_error` e `is_active`.
- Los volúmenes conservarán sólo el estado más reciente; no crearán una fila por heartbeat.
- Las alertas conservarán apertura, última observación, resolución, severidad y límites usados.

**Verificación:**

```powershell
backend\.venv\Scripts\python.exe -m pytest -q backend\tests_prod\test_agent_storage_profiles_migration.py backend\tests_prod\test_agent_models.py
backend\.venv\Scripts\alembic.exe -c backend\alembic.ini heads
```

**Commit:** `feat: add agent storage and managed profile schema`

### Tarea 2. Extender contratos de heartbeat y enrolamiento

**Archivos:**

- Modificar `backend/app/schemas/agent.py`.
- Modificar `backend/app/api/agent.py`.
- Modificar `backend/app/services/agent_enrollment_service.py`.
- Crear `backend/app/services/agent_health_service.py`.
- Crear `backend/app/repositories/agent_health_repository.py`.
- Modificar `backend/tests_prod/test_agent_routes_contract.py`.
- Crear `backend/tests_prod/test_agent_health_service.py`.
- Modificar `backend/tests_prod/test_agent_enrollment_service.py`.

**Pruebas primero:**

1. Heartbeat 0.3.0 sin `health` ni `volumes` sigue aceptado.
2. Heartbeat 0.4.0 valida tamaños no negativos, porcentajes 0–100, unidad limitada y timestamp.
3. Una medición reemplaza el estado anterior del mismo volumen.
4. `lastHeartbeatAt` cambia únicamente con heartbeat, mientras `lastSeenAt` conserva compatibilidad.
5. Enrolamiento 0.4.0 guarda clave pública de cifrado; 0.3.0 puede enrolarse sin ella.
6. Metadatos desconocidos no pueden inyectar secretos ni documentos excesivos.

**Implementación:**

- Añadir campos opcionales versionados al heartbeat.
- Delegar upsert, umbrales y alertas a `AgentHealthService`.
- Mantener `metadata_json` público para perfiles 0.3.0, pero no usarlo como fuente administrada para 0.4.0.
- Limitar cantidad de volúmenes y longitud de etiquetas.

**Verificación:**

```powershell
backend\.venv\Scripts\python.exe -m pytest -q backend\tests_prod\test_agent_health_service.py backend\tests_prod\test_agent_enrollment_service.py backend\tests_prod\test_agent_routes_contract.py
```

**Commit:** `feat: accept versioned agent health telemetry`

### Tarea 3. Exponer inventario de almacenamiento y alertas

**Archivos:**

- Crear `backend/app/api/v1/agent_storage.py`.
- Crear `backend/app/services/agent_storage_service.py`.
- Modificar `backend/app/main.py`.
- Modificar `backend/app/api/v1/agents.py`.
- Crear `backend/tests_prod/test_agent_storage_api.py`.
- Modificar `backend/tests_prod/test_agent_list_payload.py`.

**Pruebas primero:**

1. GET de almacenamiento está limitado al tenant.
2. El resumen devuelve el volumen más crítico primero.
3. Advertencia se abre una sola vez y se actualiza, no se duplica.
4. Recuperación resuelve la alerta abierta.
5. Error de lectura produce `unknown`, nunca cero bytes.
6. La lista de agentes distingue `connected`, `busy`, `degraded`, `offline` y `revoked`.

**Endpoints:**

```text
GET /api/v1/agent-storage
GET /api/v1/agent-storage/alerts
PUT /api/v1/agent-storage/thresholds
```

**Verificación:**

```powershell
backend\.venv\Scripts\python.exe -m pytest -q backend\tests_prod\test_agent_storage_api.py backend\tests_prod\test_agent_list_payload.py
```

**Commit:** `feat: expose agent storage health and alerts`

---

## Entrega 2 — Agente 0.4.0: presencia y disco

### Tarea 4. Separar heartbeat de la ejecución de órdenes

**Archivos:**

- Crear `agent/data_express_agent/health.py`.
- Modificar `agent/data_express_agent/runner.py`.
- Modificar `agent/data_express_agent/client.py`.
- Modificar `agent/data_express_agent/config.py`.
- Modificar `agent/tests/test_runner.py`.
- Crear `agent/tests/test_health.py`.
- Modificar `agent/tests/test_client.py`.

**Pruebas primero:**

1. Una orden simulada de diez minutos no detiene heartbeat.
2. Heartbeat sale cada 30 segundos con estado `busy` mientras la orden sigue activa.
3. Fallos recuperables aplican backoff sin detener el ejecutor.
4. Error no recuperable de identidad detiene el servicio.
5. Cierre del agente termina supervisor y cliente sin dejar hilos activos.
6. El journal reporta al reconectar.

**Implementación:**

- Crear `AgentHealthSupervisor` con evento de parada y estado actual protegido por lock.
- Utilizar un cliente HTTP seguro para concurrencia o clientes separados que compartan identidad, nunca estado mutable de solicitudes.
- Heartbeat predeterminado de 30 segundos y umbral backend de cuatro intervalos más margen.
- Mantener long polling en el hilo ejecutor.

**Verificación:**

```powershell
backend\.venv\Scripts\python.exe -m pytest -q agent\tests\test_runner.py agent\tests\test_health.py agent\tests\test_client.py
```

**Commit:** `fix: keep agent heartbeat alive during long operations`

### Tarea 5. Recopilar volúmenes y estimar espacio de backup

**Archivos:**

- Crear `agent/data_express_agent/storage.py`.
- Modificar `agent/data_express_agent/backup.py`.
- Modificar `agent/data_express_agent/health.py`.
- Crear `agent/tests/test_storage.py`.
- Modificar `agent/tests/test_backup.py`.

**Pruebas primero:**

1. Rutas de una misma unidad se deduplican.
2. Etiqueta, total y libre se reportan correctamente.
3. Un volumen inaccesible reporta error sanitizado.
4. Estimación usa historial cuando existe y tamaño asignado como fallback.
5. El backup se rechaza antes de SQL cuando invade la reserva crítica.
6. Una operación ya iniciada emite telemetría crítica sin matar SQL abruptamente.

**Implementación:**

- Consultar `shutil.disk_usage` y etiqueta Windows mediante API local acotada.
- Relacionar volúmenes sólo con raíces configuradas.
- Añadir preflight SQL para tamaño estimado de las bases seleccionadas.
- Incluir estimación y reserva en el error `BACKUP_SPACE_INSUFFICIENT`.

**Verificación:**

```powershell
backend\.venv\Scripts\python.exe -m pytest -q agent\tests\test_storage.py agent\tests\test_backup.py
```

**Commit:** `feat: report disk health and prevent storage exhaustion`

---

## Entrega 3 — Nombres, origen y entrega durable

### Tarea 6. Implementar nombres diarios y reemplazo atómico

**Archivos:**

- Modificar `agent/data_express_agent/backup.py`.
- Modificar `agent/tests/test_backup.py`.
- Modificar `backend/tests_prod/test_agent_backup_lifecycle.py`.

**Pruebas primero:**

1. Full crea `Base_AAAA-MM-DD.bak`.
2. Diferencial crea `Base_AAAA-MM-DD_DIF.bak`.
3. ZIP queda bajo `Fecha/FULL` o `Fecha/DIFERENCIAL` con nombre diario.
4. No aparece `runId` en nombres visibles.
5. ZIP previo permanece si falla el ZIP nuevo.
6. Reemplazo ocurre sólo después de integridad y SHA correctos.
7. `manifest.json` contiene origen, bases, tipo y hashes, sin secretos.
8. Reintento de entrega encuentra el ZIP diario por la ruta durable registrada.

**Implementación:**

- Separar helpers puros de nombres y rutas.
- Crear ZIP temporal dentro de la misma unidad para permitir `os.replace` atómico.
- Mantener `.work/<runId>` sólo como implementación interna.
- Conservar artefacto anterior hasta finalizar el nuevo.

**Verificación:**

```powershell
backend\.venv\Scripts\python.exe -m pytest -q agent\tests\test_backup.py backend\tests_prod\test_agent_backup_lifecycle.py
```

**Commit:** `feat: use deterministic daily backup artifact names`

### Tarea 7. Persistir y mostrar origen

**Archivos:**

- Modificar `backend/app/services/agent_operation_service.py`.
- Modificar `backend/app/services/agent_backup_service.py`.
- Modificar `backend/app/services/agent_backup_scheduler.py`.
- Modificar `backend/app/services/agent_command_service.py`.
- Modificar `backend/app/services/backup_serializers.py`.
- Modificar `backend/tests_prod/test_agent_backup_service.py`.
- Modificar `backend/tests_prod/test_agent_backup_scheduler.py`.
- Modificar `backend/tests_prod/test_agent_command_service.py`.

**Pruebas primero:**

1. Manual y programado guardan la misma instantánea de origen.
2. Renombrar o revocar un agente no cambia el origen histórico.
3. El serializer no expone configuración sensible.
4. Resultado del agente y manifiesto deben coincidir con la revisión esperada.

**Verificación:**

```powershell
backend\.venv\Scripts\python.exe -m pytest -q backend\tests_prod\test_agent_backup_service.py backend\tests_prod\test_agent_backup_scheduler.py backend\tests_prod\test_agent_command_service.py
```

**Commit:** `feat: persist immutable backup origin snapshots`

### Tarea 8. Corregir seguimiento de entrega en frontend

**Archivos:**

- Modificar `frontend/src/hooks/useBackups.ts`.
- Modificar `frontend/src/components/backups/agent-trigger-backup-modal.tsx`.
- Modificar `frontend/src/components/backups/backup-list.tsx`.
- Modificar `frontend/src/types/backup.ts`.
- Crear pruebas de funciones de polling si se incorpora runner de tests; de lo contrario extraer y probar el predicado en TypeScript durante type-check/build.

**Pruebas/contrato primero:**

1. Polling continúa si `status=completed` y `deliveryStatus` es `pending` o `processing`.
2. Polling termina en `delivered` o `failed`.
3. Sin destino remoto se muestra `ZIP local listo`, no `Entregado`.
4. Con destino remoto y hash confirmado se muestra `Entregado`.
5. La tabla incluye `Origen` y conserva accesibilidad en ancho reducido.

**Checkpoint visual obligatorio antes de editar UI:**

```text
Intent: operador que necesita distinguir respaldo, origen y entrega sin abrir detalles.
Palette: tokens actuales; verde éxito, ámbar riesgo, rojo error, cian actividad.
Depth: bordes sutiles, sin sombras nuevas.
Surfaces: conservar carbon/musgo del sistema existente.
Typography: sans para estados y números tabulares; mono sólo para rutas/IDs.
Spacing: base 4 px.
```

**Verificación:**

```powershell
cd frontend
npm run type-check
npm run build
```

**Commit:** `fix: track backup delivery through terminal state`

---

## Entrega 4 — Barra de espacio

### Tarea 9. Añadir estado global de almacenamiento

**Archivos:**

- Crear `frontend/src/types/agent-storage.ts`.
- Crear `frontend/src/services/agent-storage.service.ts`.
- Crear `frontend/src/hooks/useAgentStorage.ts`.
- Crear `frontend/src/components/layout/storage-health-bar.tsx`.
- Modificar `frontend/src/app/dashboard/layout.tsx`.
- Modificar `frontend/src/app/dashboard/alerts/page.tsx` sólo para integrar alertas persistidas.

**Criterios:**

- Mostrar volumen más crítico y desplegar el resto.
- Texto exacto `X disponibles de Y`.
- Mostrar etiqueta y unidad como `Data (D:)`.
- No representar error de lectura como disco lleno.
- Mantener barra visible durante navegación sin producir waterfalls duplicados.
- `aria-valuemin`, `aria-valuemax`, `aria-valuenow` y descripción textual.

**Checkpoint visual:**

```text
Intent: advertencia operativa inmediata, familiar como el Explorador de Windows.
Palette: verde/ámbar/rojo exclusivamente por capacidad.
Depth: banda plana con borde inferior sutil.
Surfaces: un nivel sobre el lienzo, debajo de modales.
Typography: sans compacta con cifras tabulares.
Spacing: base 4 px; altura objetivo 48–64 px expandible.
```

**Verificación:**

```powershell
cd frontend
npm run type-check
npm run build
```

**Commit:** `feat: show Windows-style storage health banner`

---

## Entrega 5 — Perfiles administrados y secretos

### Tarea 10. Implementar cifrado por agente

**Archivos:**

- Modificar `agent/data_express_agent/identity.py`.
- Modificar `agent/data_express_agent/dpapi.py`.
- Crear `agent/data_express_agent/secrets.py`.
- Modificar `agent/data_express_agent/protocol.py`.
- Modificar `backend/app/agent_protocol.py`.
- Modificar `backend/app/services/agent_enrollment_service.py`.
- Modificar `backend/app/schemas/agent.py`.
- Crear/Modificar pruebas de identidad, protocolo y enrolamiento.

**Pruebas primero:**

1. Identidad 0.4.0 genera clave X25519 separada de Ed25519.
2. Sobre cifrado sólo abre con el agente destinatario.
3. Manipulación del ciphertext falla de forma segura.
4. DPAPI no permite recuperar el secreto con un contexto distinto.
5. Migración de identidad 0.3.0 conserva agent ID y genera sólo la clave faltante.
6. Serialización nunca incluye clave privada.

**Commit:** `feat: add per-agent encrypted secret envelopes`

### Tarea 11. Crear API y sincronización de perfiles

**Archivos:**

- Crear `backend/app/api/v1/agent_profiles.py`.
- Crear `backend/app/services/agent_profile_service.py`.
- Crear `backend/app/repositories/agent_profile_repository.py`.
- Modificar `backend/app/services/agent_command_service.py`.
- Modificar `backend/app/main.py`.
- Crear `backend/tests_prod/test_agent_profile_service.py`.
- Crear `backend/tests_prod/test_agent_profile_api.py`.
- Modificar `backend/tests_prod/test_agent_command_contract.py`.

**Endpoints:**

```text
GET    /api/v1/agents/{agentId}/managed-profiles
POST   /api/v1/agents/{agentId}/managed-profiles/discover
POST   /api/v1/agents/{agentId}/managed-profiles
PUT    /api/v1/agents/{agentId}/managed-profiles/{profileId}
DELETE /api/v1/agents/{agentId}/managed-profiles/{profileId}
POST   /api/v1/agents/{agentId}/managed-profiles/{profileId}/test
GET    /api/v1/agents/{agentId}/managed-profiles/{profileId}/jobs/{jobId}
```

**Pruebas primero:**

- Capacidades separadas para leer, administrar y probar.
- Tenant isolation en todos los endpoints.
- Respuestas omiten `secret_envelope`.
- Editar metadatos conserva secreto existente.
- Cambio de secreto incrementa revisión.
- Edición offline queda `pending`.
- Perfil anterior aplicado permanece activo si la prueba nueva falla.
- Clave SFTP distinta produce error de identidad, no aceptación automática.

**Commit:** `feat: manage agent connection profiles centrally`

### Tarea 12. Aplicar, probar y recargar perfiles en el agente

**Archivos:**

- Crear `agent/data_express_agent/profiles.py`.
- Crear `agent/data_express_agent/discovery.py`.
- Modificar `agent/data_express_agent/config.py`.
- Modificar `agent/data_express_agent/runner.py`.
- Modificar `agent/data_express_agent/backup.py`.
- Crear `agent/tests/test_profiles.py`.
- Crear `agent/tests/test_discovery.py`.
- Modificar `agent/tests/test_runner.py`.

**Comandos:**

- `discover_agent_environment`;
- `apply_connection_profiles`;
- `test_sql_profile`;
- `test_destination_profile`.

**Pruebas primero:**

- Aplicación atómica con revisión monotónica.
- Rollback local si el archivo nuevo no valida.
- SQL integrado identifica cuenta del servicio y permisos.
- Prueba SMB/SFTP cubre crear, leer, hash, renombrar y eliminar.
- Secreto se descifra sólo durante aplicación/prueba y queda DPAPI local.
- BackupExecutor recarga perfiles sin reiniciar una orden en curso.

**Commit:** `feat: discover and apply managed connection profiles`

### Tarea 13. Construir panel y asistente de conexiones

**Archivos:**

- Crear `frontend/src/types/agent-profile.ts`.
- Crear `frontend/src/services/agent-profiles.service.ts`.
- Crear `frontend/src/hooks/useAgentProfilesAdmin.ts`.
- Crear `frontend/src/components/agents/agent-connection-wizard.tsx`.
- Crear `frontend/src/components/agents/managed-profiles-panel.tsx`.
- Modificar `frontend/src/components/agents/agents-admin.tsx`.
- Modificar `frontend/src/app/dashboard/settings/page.tsx`.

**Flujo:**

```text
Detectar → SQL Server → Permisos → Raíz → Destino → Limpieza → Activar
```

**Criterios:**

- Reabrir en el paso fallido.
- Copiar script SQL sin ejecutarlo automáticamente.
- Mostrar `Aplicado`, `Pendiente`, `Probando`, `Error` y `Requiere secreto`.
- Nunca rehidratar secretos existentes.
- Paralelizar consultas independientes y evitar cascadas de `useEffect`.

**Checkpoint visual:** conservar bordes, superficies y tipografía actuales; usar línea de fases como firma operacional; controles con estados de foco, error, carga y offline.

**Verificación:**

```powershell
cd frontend
npm run type-check
npm run build
```

**Commit:** `feat: add guided agent connection setup`

---

## Entrega 6 — Limpieza unificada

### Tarea 14. Reconciliar backend de Limpieza por agente

**Archivos:**

- Consolidar responsabilidades duplicadas entre `backend/app/services/agent_admin_service.py` y `backend/app/services/agent_operation_service.py` sin cambiar contratos públicos innecesarios.
- Modificar `backend/app/api/v1/agents.py`.
- Modificar `backend/app/services/agent_command_service.py`.
- Modificar `backend/tests_prod/test_agent_admin_service.py`.
- Modificar `backend/tests_prod/test_agent_command_service.py`.
- Crear `backend/tests_prod/test_agent_cleanup_flow.py`.

**Diagnóstico/pruebas primero:**

- Trazar qué endpoint consume hoy `StructuralPanel`.
- Reproducir simulación, ejecución directa, archivo bloqueado y manifiesto cambiado.
- Afirmar objetivos fijos y raíz validada.
- Afirmar eliminación de archivos y conservación de directorios.
- Afirmar rechazo de enlaces y rutas fuera del perímetro.
- Afirmar resultado parcial con detalle.

**Commit:** `fix: consolidate direct agent cleanup workflow`

### Tarea 15. Sustituir las pantallas heredadas

**Archivos:**

- Reescribir `frontend/src/app/dashboard/cleanup/page.tsx` como flujo agente.
- Convertir `frontend/src/app/dashboard/limpieza-remota/page.tsx` en redirección temporal.
- Modificar `frontend/src/components/layout/sidebar.tsx`.
- Reutilizar/ajustar `frontend/src/components/cleanup/structural-panel.tsx`.
- Modificar `frontend/src/hooks/useAgentCleanup.ts`.
- Modificar `frontend/src/services/agent-cleanup.service.ts`.
- Retirar consumidores frontend de `filemanager.service.ts` y `remote-cleanup.service.ts`, sin eliminar todavía endpoints backend.

**Criterios:**

- Una sola opción `Limpieza`.
- Sin FTP/FTPS/SFTP, contraseña, PEM, cuarentena o reglas arbitrarias.
- Selección automática de un agente y selector cuando haya varios.
- Fases `Simular → Revisar → Confirmar → Resultado`.
- Resumen de propiedades, archivos, bytes y advertencias.
- Confirmación explícita para eliminación definitiva.

**Verificación:**

```powershell
cd frontend
npm run type-check
npm run build
```

**Commit:** `fix: replace legacy cleanup UI with agent flow`

---

## Entrega 7 — Empaquetado, compatibilidad y despliegue

### Tarea 16. Versionar y empaquetar agente 0.4.0

**Archivos:**

- Modificar `agent/data_express_agent/config.py`.
- Modificar `agent/installer/agent-profiles.example.json`.
- Modificar `agent/installer/README-INSTALACION.txt`.
- Modificar `agent/installer/DataExpressAgent.Service.xml` sólo si pruebas de identidad lo requieren.
- Modificar `agent/installer/Update-DataExpressAgent.ps1` para esperar la detención real antes de mover binarios y validar heartbeat 0.4.0 después del arranque.
- Modificar `agent/package.ps1`.
- Crear/actualizar documentación operativa.

**Pruebas:**

- Actualización desde 0.3.0 conserva identidad, perfiles y journal.
- Rollback restaura binarios y configuración.
- Cambio de cuenta del servicio marca secretos para recaptura.
- WinSW reinicia después de fallo.
- El paquete contiene `VERSION.txt = 0.4.0`.

**Build:**

```powershell
powershell -ExecutionPolicy Bypass -File agent\build.ps1
powershell -ExecutionPolicy Bypass -File agent\package.ps1 -Version 0.4.0
```

**Commit:** `feat: package Data Express Agent 0.4.0`

### Tarea 17. Verificación integral

**Automática:**

```powershell
backend\.venv\Scripts\python.exe -m pytest -q backend\tests backend\tests_prod agent\tests
backend\.venv\Scripts\alembic.exe -c backend\alembic.ini heads
cd frontend
npm run type-check
npm run build
```

**Servidor piloto:**

1. Actualizar 0.3.0 → 0.4.0.
2. Confirmar heartbeat durante un backup mayor a cinco minutos.
3. Confirmar barra `Data (D:)` y umbrales.
4. Ejecutar Full y revisar nombre `.bak`.
5. Confirmar ZIP en `Fecha/FULL/Backup_Fecha.zip`.
6. Confirmar origen y manifiesto.
7. Interrumpir transferencia, comprobar `Entrega fallida` y reintentar sin otro `.bak`.
8. Configurar y probar un destino desde dashboard.
9. Simular y ejecutar Limpieza sobre propiedades controladas.
10. Comparar manifiesto, archivos eliminados y carpetas conservadas.

**Despliegue:**

1. Push de rama de trabajo.
2. Desplegar backend y esperar `/health/ready` correcto.
3. Desplegar frontend.
4. Actualizar agente piloto.
5. Observar una jornada de backups.
6. Fusionar/push a `main` cuando el piloto cumpla criterios.

**Commit final:** `release: complete agent storage and connection reliability`

## Riesgos que detienen el despliegue

- Más de un head Alembic.
- Backend nuevo que rechaza heartbeat 0.3.0.
- Secretos visibles en respuesta o logs.
- Heartbeat detenido durante SQL.
- Reemplazo del ZIP anterior antes de verificar el nuevo.
- Dos agentes apuntando a la misma raíz remota sin aislamiento confirmado.
- Limpieza capaz de aceptar una ruta arbitraria.
- Agente 0.4.0 sin rollback probado.

## Resultado esperado

Al completar las 17 tareas, el operador verá nombres diarios simples, origen inequívoco, capacidad de disco como en Windows, conexiones configurables mediante asistente, estado real del envío, Limpieza única y un agente que permanece visible durante operaciones largas.

