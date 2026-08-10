# Plan de implementación: agente Windows para limpieza remota

**Fecha:** 2026-08-10  
**Especificación:** `docs/superpowers/specs/2026-08-10-windows-agent-remote-cleanup-design.md`  
**Objetivo:** Implementar un agente de Windows vinculado una sola vez, exploración visual de discos, validación de aproximadamente 1500 propiedades y limpieza estructural segura de `Core` desde Railway.

## 1. Estrategia técnica

### 1.1 Tecnología del agente

El agente se implementará en Python 3.11 para reutilizar la lógica estructural existente y reducir diferencias entre simulación y ejecución. Se distribuirá como una carpeta autocontenida generada con PyInstaller y se ejecutará como servicio de Windows mediante WinSW. El servidor no necesitará una instalación independiente de Python.

Esta elección permite entregar primero la funcionalidad operativa y conservar una sola base conceptual de recorrido. La interfaz del agente quedará aislada para poder sustituir su implementación en el futuro sin cambiar el backend ni el frontend.

### 1.2 Transporte

La primera versión utilizará HTTPS con sondeo largo:

```text
agente -> GET /agent/v1/commands/next?wait=25
agente <- comando firmado o 204
agente -> POST /agent/v1/commands/{id}/progress
agente -> POST /agent/v1/commands/{id}/complete
```

El agente siempre inicia la conexión. No habrá puertos entrantes, WebSocket obligatorio ni dependencia de Redis. PostgreSQL será la cola durable de comandos.

### 1.3 Identidad y firmas

- Cada agente generará una clave Ed25519 durante la vinculación.
- La clave privada del agente se almacenará cifrada mediante DPAPI para la cuenta del servicio.
- Railway guardará solamente la clave pública del agente.
- Cada solicitud del agente firmará método, ruta, timestamp, nonce y SHA-256 del cuerpo.
- Railway firmará cada respuesta de comando con una clave Ed25519 exclusiva para comandos.
- El agente incluirá la clave pública de verificación de Railway en su paquete de instalación.
- El backend conservará nonces durante una ventana corta para bloquear repeticiones.
- Los códigos de vinculación tendrán al menos 128 bits, un solo uso, vigencia de 10 minutos y almacenamiento mediante hash.

### 1.4 Límites de alcance

Esta entrega no implementará control de escritorio, RDP embebido, edición de archivos ni ejecución remota de scripts. Solo se admitirán comandos tipados y validados: explorar, validar, simular, ejecutar a cuarentena, restaurar, purgar y cancelar.

## 2. Contratos principales

### 2.1 Endpoints de administración con sesión web

```text
GET    /api/v1/agents
POST   /api/v1/agents/pairing-codes
POST   /api/v1/agents/{agent_id}/replace
POST   /api/v1/agents/{agent_id}/revoke
POST   /api/v1/agents/{agent_id}/browse
POST   /api/v1/agents/{agent_id}/validate
PUT    /api/v1/agents/{agent_id}/configuration
GET    /api/v1/agents/jobs/{job_id}
POST   /api/v1/agents/jobs/{job_id}/cancel
```

`CONFIG_MANAGE` será obligatorio para vincular, reemplazar, revocar, explorar, validar y cambiar configuración. Los trabajos de limpieza continuarán usando `CLEANUP_SIMULATE`, `CLEANUP_EXECUTE`, `JOB_CANCEL` y `PURGE`.

### 2.2 Endpoints exclusivos del agente

```text
POST   /agent/v1/enroll
GET    /agent/v1/commands/next
POST   /agent/v1/commands/{command_id}/progress
POST   /agent/v1/commands/{command_id}/complete
POST   /agent/v1/commands/{command_id}/fail
POST   /agent/v1/heartbeat
```

Vivirán fuera de `/api/` para no mezclar autenticación de agente con cookies y CSRF. Tendrán autenticación propia, límites de tamaño, frecuencia y tiempo, y nunca aceptarán cookies de usuario como identidad.

### 2.3 Comandos tipados

Cada comando tendrá `id`, `agentId`, `tenantId`, `type`, `payload`, `configRevision`, `issuedAt`, `expiresAt`, `idempotencyKey` y firma.

Tipos iniciales:

- `browse_drives`
- `browse_directory`
- `validate_structure`
- `simulate_structural_cleanup`
- `execute_structural_quarantine`
- `restore_quarantine_item`
- `purge_quarantine_items`
- `cancel_job`

El agente rechazará cualquier tipo desconocido. No existirá un comando genérico de shell.

## 3. Persistencia y migración

Crear `backend/alembic/versions/0004_windows_agents.py`.

### 3.1 Tablas nuevas

#### `remote_agents`

- `id`, `tenant_id`, `created_at`
- `installation_id`
- `hostname`
- `os_version`
- `agent_version`
- `public_key`
- `status`
- `last_seen_at`
- `revoked_at`
- `replaced_by_id`
- `metadata_json`

Restricciones: `tenant_id + installation_id` único e índices por estado y última conexión.

#### `agent_pairing_tokens`

- `id`, `tenant_id`, `created_at`
- `token_hash`
- `expires_at`
- `used_at`
- `created_by`
- `replace_agent_id`

El valor sin hash se devolverá una sola vez y nunca se registrará.

#### `agent_commands`

- `id`, `tenant_id`, `created_at`
- `agent_id`
- `job_id`
- `command_type`
- `payload`
- `payload_hash`
- `status`
- `idempotency_key`
- `expires_at`
- `claimed_at`
- `completed_at`
- `result_summary`
- `error_code`, `error_message`

Restricciones: idempotencia única por agente e índices para obtener el siguiente comando pendiente.

#### `agent_request_nonces`

- `agent_id`
- `nonce_hash`
- `expires_at`

Clave única por agente y nonce. Los registros vencidos se eliminarán periódicamente.

#### `remote_structure_validations`

- `id`, `tenant_id`, `created_at`
- `server_id`, `agent_id`, `job_id`
- `configuration_hash`
- `status`
- `summary`
- `validated_at`
- `expires_at`

### 3.2 Cambios en `remote_servers`

- Agregar `transport` con valores `legacy` o `agent`.
- Agregar `agent_id` nullable.
- Agregar `target_folders` y `target_files` como JSONB.
- Agregar `config_revision`, `configuration_hash` y `validated_at`.
- Agregar `validation_id` nullable.
- Hacer nullable `protocol`, `host`, `port` y `username` para servidores de agente.
- Mantener `base_path` como raíz de Windows.
- Mantener `allowlist` solo para registros `legacy`; la allowlist del agente será calculada.

Los registros existentes se migrarán con `transport='legacy'` sin pérdida de datos. La migración tendrá `downgrade` únicamente mientras no existan servidores de agente; si existen, abortará con un mensaje explícito para evitar pérdida silenciosa.

### 3.3 Simulaciones

El manifiesto completo de candidatos no se enviará a Railway. El agente lo almacenará temporalmente bajo `%ProgramData%\DataExpress\Agent\simulations`, protegido por permisos NTFS y un MAC derivado de una clave guardada con DPAPI. Railway almacenará identificador, hash, expiración, configuración, conteos y muestras acotadas.

Si el agente se reinstala, pierde el manifiesto o cambia la configuración, la simulación se invalida y debe repetirse.

## 4. Fases de implementación

Cada tarea se completará con pruebas primero, cambio mínimo, suite verde y commit independiente.

### Tarea 1: protocolo criptográfico y vectores de prueba

**Crear:**

- `backend/app/agent_protocol.py`
- `backend/tests_prod/test_agent_protocol.py`
- `agent/data_express_agent/protocol.py`
- `agent/tests/test_protocol.py`
- `docs/operations/agent-protocol.md`

**Pruebas iniciales:**

- Una solicitud válida verifica firma, timestamp y hash del cuerpo.
- Un byte modificado invalida la firma.
- Timestamp fuera de ventana se rechaza.
- Nonce repetido se rechaza por la capa de persistencia simulada.
- Un comando firmado por Railway se valida en el agente.
- Vectores dorados idénticos funcionan en ambos paquetes.

**Implementación:**

- Definir el formato exacto de la cadena firmada.
- Firmar los bytes reales del cuerpo, no un JSON reserializado.
- Limitar diferencia de reloj a 120 segundos.
- Usar comparación constante donde corresponda.
- Documentar versión del protocolo y estrategia de rotación de claves.

**Verificación:**

```powershell
python -m pytest backend/tests_prod/test_agent_protocol.py -q
python -m pytest agent/tests/test_protocol.py -q
```

### Tarea 2: modelos y migración 0004

**Modificar:**

- `backend/app/models/operations.py`
- `backend/app/models/__init__.py`
- `backend/app/repositories/remote_repository.py`

**Crear:**

- `backend/alembic/versions/0004_windows_agents.py`
- `backend/tests_prod/test_agent_models.py`

**Pruebas iniciales:**

- Todos los modelos nuevos exigen tenant.
- Las restricciones de instalación, nonce e idempotencia están presentes.
- Un servidor legado conserva sus campos.
- Un servidor de agente no necesita host, puerto ni usuario.
- Upgrade y downgrade seguro se validan contra PostgreSQL de prueba.

**Verificación:**

```powershell
alembic -c backend/alembic.ini upgrade head
python -m pytest backend/tests_prod/test_agent_models.py -q
```

### Tarea 3: configuración segura de Railway

**Modificar:**

- `backend/app/core/config.py`
- `.env.example`
- `docs/operations/production-readiness.md`

**Crear:**

- `backend/scripts/generate_agent_signing_key.py`
- `backend/tests_prod/test_agent_security_config.py`

**Variables:**

- `AGENT_COMMAND_SIGNING_PRIVATE_KEY`
- `AGENT_COMMAND_SIGNING_KEY_ID`
- `AGENT_ENROLLMENT_TTL_SEC=600`
- `AGENT_COMMAND_TTL_SEC=120`
- `AGENT_MAX_CLOCK_SKEW_SEC=120`
- `AGENT_MIN_VERSION`

**Reglas:** producción no inicia con claves ausentes, débiles o de ejemplo cuando el módulo esté habilitado. La clave privada nunca se imprime ni se guarda en Git. El script generará por separado el valor privado para Railway y las claves públicas actuales y siguientes para `agent-config.json`; el paquete del agente nunca contendrá la clave privada.

### Tarea 4: vinculación administrativa

**Crear:**

- `backend/app/api/v1/agents.py`
- `backend/app/schemas/agent.py`
- `backend/app/services/agent_enrollment_service.py`
- `backend/app/repositories/agent_repository.py`
- `backend/tests_prod/test_agent_admin_contract.py`

**Modificar:**

- `backend/app/main.py`
- `backend/app/core/capabilities.py` solo si se decide separar una capacidad de agentes; por defecto se reutiliza `CONFIG_MANAGE`.

**Pruebas iniciales:**

- Solo admin puede crear códigos, reemplazar y revocar.
- El código se muestra una sola vez, vence y no aparece en auditoría.
- Reemplazar revoca la identidad anterior y conserva el servidor.
- Un tenant no puede ver ni alterar agentes de otro tenant.

### Tarea 5: autenticación y enrollment del agente

**Crear:**

- `backend/app/api/agent.py`
- `backend/app/services/agent_auth_service.py`
- `backend/app/dependencies/agent_identity.py`
- `backend/tests_prod/test_agent_auth_contract.py`

**Modificar:**

- `backend/app/main.py`
- `backend/app/middleware/audit.py` para registrar identidad de agente sin fingir identidad de usuario.

**Pruebas iniciales:**

- Enrollment válido consume el código de forma atómica.
- Código vencido, usado o incorrecto falla sin indicar cuál condición facilitó el ataque.
- Firma inválida, timestamp viejo, nonce repetido y agente revocado devuelven rechazo estable.
- El cuerpo tiene un límite pequeño y los errores no incluyen claves.
- Endpoints `/agent/v1` no dependen de cookies ni de CSRF.

**Protección de abuso:** aplicar límite persistente de intentos por IP e `installation_id`, con espera incremental y auditoría resumida.

### Tarea 6: cola durable de comandos

**Crear:**

- `backend/app/services/agent_command_service.py`
- `backend/tests_prod/test_agent_command_queue.py`

**Modificar:**

- `backend/app/repositories/agent_repository.py`
- `backend/app/api/agent.py`

**Pruebas iniciales:**

- Solo un agente puede reclamar un comando pendiente.
- La selección usa bloqueo transaccional y respeta expiración.
- Un resultado repetido es idempotente.
- Un agente no puede completar comandos de otro agente.
- Cancelación y expiración actualizan el trabajo correspondiente.
- Reiniciar el backend no pierde comandos.

### Tarea 7: núcleo mínimo del agente y servicio Windows

**Crear:**

- `agent/requirements.txt`
- `agent/requirements-dev.txt`
- `agent/data_express_agent/__init__.py`
- `agent/data_express_agent/__main__.py`
- `agent/data_express_agent/config.py`
- `agent/data_express_agent/identity.py`
- `agent/data_express_agent/dpapi.py`
- `agent/data_express_agent/client.py`
- `agent/data_express_agent/runner.py`
- `agent/tests/test_identity.py`
- `agent/tests/test_client.py`
- `agent/installer/agent-service.xml.template`
- `agent/installer/Install-DataExpressAgent.ps1`
- `agent/installer/Uninstall-DataExpressAgent.ps1`

**Comportamiento:**

- El instalador solicita URL de Railway y código de vinculación.
- Genera identidad local, completa enrollment y registra el servicio.
- El servicio inicia automáticamente, envía heartbeat y sondea comandos.
- Las claves privadas y el contador local quedan protegidos para la cuenta del servicio.
- Los logs rotan, redactan secretos y no contienen cuerpos completos.

**Pruebas:** ejecutar lógica multiplataforma normalmente y pruebas DPAPI marcadas `windows` solamente en Windows.

### Tarea 8: seguridad de rutas Windows y explorador

**Crear:**

- `agent/data_express_agent/windows_paths.py`
- `agent/data_express_agent/explorer.py`
- `agent/tests/test_windows_paths.py`
- `agent/tests/test_explorer.py`

**Pruebas iniciales:**

- Enumeración de unidades permitidas.
- Ruta absoluta normalizada correctamente.
- Rechazo de `..`, UNC no autorizada, ADS, device paths y nombres ambiguos.
- Rechazo de symlinks, junctions o reparse points fuera de raíz.
- Paginación determinista y carga de un solo nivel.
- Ningún comando permite leer contenido de archivos.

**Backend y frontend:**

- Implementar `browse_drives` y `browse_directory` como trabajos cortos.
- Devolver únicamente nombre, ruta, tipo y accesibilidad.

### Tarea 9: interfaz de agentes y selector de carpeta

**Crear:**

- `frontend/src/types/agent.ts`
- `frontend/src/services/agents.service.ts`
- `frontend/src/components/agents/agents-admin.tsx`
- `frontend/src/components/agents/pair-agent-dialog.tsx`
- `frontend/src/components/agents/agent-card.tsx`
- `frontend/src/components/agents/remote-folder-browser.tsx`
- `frontend/src/components/agents/agent-status-badge.tsx`

**Modificar:**

- `frontend/src/app/dashboard/settings/page.tsx`
- `frontend/src/components/cleanup/server-admin.tsx` para retirar el formulario manual cuando el modo agente esté habilitado.

**Criterios UI:**

- Estados claros y última conexión.
- Código de vinculación copiable con cuenta regresiva y advertencia de un solo uso.
- Explorador por niveles con breadcrumb, carga, vacío y errores.
- Botón guardar todavía deshabilitado hasta validar.
- Accesibilidad por teclado, foco y nombres accesibles.

**Verificación:**

```powershell
npm --prefix frontend run type-check
npm --prefix frontend run build
```

### Tarea 10: validación estructural dirigida

**Crear:**

- `agent/data_express_agent/structural_scan.py`
- `agent/tests/test_structural_scan.py`
- `backend/app/services/agent_validation_service.py`
- `backend/tests_prod/test_agent_validation_contract.py`
- `frontend/src/components/agents/server-configuration-form.tsx`
- `frontend/src/components/agents/validation-report.tsx`

**Reutilizar:**

- `backend/structural_cleanup.py` como referencia de clasificación.
- Casos de `backend/tests/test_structural_traversal.py` convertidos en fixtures compartidos o vectores de contrato.

**Algoritmo:**

1. Listar hijos directos de la raíz.
2. Tratar directorios como propiedades.
3. Identificar `Core` y reportar `Web` sin recorrerlo.
4. Buscar nombres objetivo exactos dentro de `Core`.
5. Reportar conteos, accesos denegados y muestras acotadas.
6. Actualizar progreso por lotes y respetar cancelación.

**Pruebas mínimas:** más de 1500 propiedades, ausencia de `Core`, cambios de mayúsculas, `Web` con nombres objetivo, junction maliciosa, acceso denegado y cancelación.

### Tarea 11: guardado de configuración validada

**Modificar:**

- `backend/app/api/v1/agents.py`
- `backend/app/services/agent_validation_service.py`
- `backend/app/repositories/agent_repository.py`
- componentes de configuración del frontend.

**Reglas:**

- Calcular hash canónico de raíz y objetivos.
- Guardar solo si la validación exitosa corresponde exactamente a ese hash y agente.
- Incrementar `config_revision` en cada cambio.
- Invalidar simulaciones al cambiar raíz u objetivos.
- Permitir propiedades sin `Core` con advertencia; bloquear raíz inaccesible o inexistente.

### Tarea 12: simulación estructural en el agente

**Crear:**

- `agent/data_express_agent/simulations.py`
- `agent/tests/test_simulations.py`
- `backend/app/services/agent_cleanup_service.py`
- `backend/tests_prod/test_agent_simulation_contract.py`

**Modificar:**

- `backend/app/api/v1/remote_cleanup.py`
- `backend/app/services/remote_cleanup_service.py` para despachar por `transport`.

**Reglas:**

- Servidor `agent` no acepta credenciales SFTP en la solicitud.
- El agente usa configuración guardada, no rutas enviadas libremente por el navegador.
- El manifiesto local incluye metadatos necesarios para revalidar candidatos.
- Railway recibe resumen, hash, expiración y hasta 100 muestras; nunca millones de rutas.
- La simulación se invalida por tiempo, cambio de configuración, reinicio de identidad o pérdida del manifiesto.

### Tarea 13: cuarentena, restauración y purga

**Crear:**

- `agent/data_express_agent/quarantine.py`
- `agent/tests/test_quarantine.py`
- `backend/tests_prod/test_agent_execution_contract.py`

**Modificar:**

- `backend/app/services/agent_cleanup_service.py`
- `backend/app/api/v1/remote_cleanup.py`
- repositorios y serializadores de cuarentena.

**Reglas:**

- Revalidar simulación y candidatos inmediatamente antes de mover.
- Cuarentena dentro del mismo volumen cuando sea posible.
- Operaciones por elemento con idempotency key.
- Desconexión durante modificación termina en `interrupted`; nunca reanuda automáticamente.
- Restaurar exige que el destino continúe bajo raíz y no haya sido ocupado por otro archivo.
- Purga requiere `PURGE`, confirmación reforzada y comando separado.

### Tarea 14: adaptar Limpieza remota al agente

**Modificar:**

- `frontend/src/app/dashboard/limpieza-remota/page.tsx`
- `frontend/src/components/cleanup/structural-panel.tsx`
- `frontend/src/services/remote-cleanup.service.ts`
- `frontend/src/types/remote-cleanup.ts`

**Cambios:**

- Eliminar campos de contraseña, PEM y passphrase para servidores `agent`.
- Mostrar estado del agente y bloquear acciones si está desconectado o desactualizado.
- Usar las reglas guardadas por servidor.
- Mostrar progreso por propiedades, resumen, advertencias y errores parciales.
- Mantener flujo legado oculto detrás de `transport='legacy'` durante la transición.

### Tarea 15: empaquetado, integridad e instalación

**Crear:**

- `agent/agent.spec`
- `agent/installer/Build-Agent.ps1`
- `agent/installer/Test-AgentPackage.ps1`
- `docs/operations/windows-agent-installation.md`
- `docs/operations/windows-agent-hardening.md`

**Paquete:**

- Ejecutable/carpeta PyInstaller.
- WinSW y plantilla de servicio.
- Scripts de instalación y desinstalación.
- Manifiesto SHA-256.
- Firma Ed25519 del manifiesto.
- Clave pública de comandos de Railway.
- Versión del protocolo y versión mínima compatible.

El instalador verificará firma y hashes antes de escribir en Program Files. La actualización automática permanecerá deshabilitada hasta disponer de un proceso de firma y rollback probado. Para producción se recomienda además Authenticode; sin certificado, Windows mostrará editor desconocido aunque la verificación interna siga funcionando.

### Tarea 16: observabilidad y mantenimiento

**Modificar:**

- `backend/app/api/health.py`
- `backend/app/core/scheduler.py`
- `backend/app/services/insights_service.py`
- frontend de alertas y servidor.

**Agregar:**

- Limpieza periódica de nonces, comandos y códigos vencidos.
- Métricas de agentes conectados, atrasados, revocados y versiones.
- Alertas por agente desconectado, firmas inválidas repetidas, versión obsoleta y trabajos interrumpidos.
- Correlation IDs compartidos entre comando, trabajo, ejecución y logs locales.

No se expondrán claves, nonces completos ni rutas fuera de la raíz en métricas.

### Tarea 17: pruebas de extremo a extremo y transición

**Crear:**

- `backend/tests_integration/test_agent_end_to_end.py`
- `agent/tests/integration/test_railway_contract.py`
- `installer/tests/AgentInstaller.Tests.ps1`
- `docs/operations/windows-agent-acceptance-checklist.md`

**Escenarios:**

1. Vincular agente nuevo.
2. Reiniciar servicio y reconectar sin duplicado.
3. Explorar discos y seleccionar raíz.
4. Validar 1500 propiedades.
5. Demostrar que `Web` no se recorre ni modifica.
6. Simular, mover a cuarentena y restaurar.
7. Alterar estructura entre simulación y ejecución y recibir conflicto.
8. Desconectar durante movimiento y reconciliar sin continuación automática.
9. Revocar agente y comprobar rechazo inmediato.
10. Intentar traversal, replay y comando para otro tenant.

Tras superar esta lista con un servidor piloto, el agente será el modo predeterminado. El transporte SFTP permanecerá disponible solamente para registros heredados durante una versión. Su eliminación será un cambio posterior con migración y respaldo.

## 5. Orden de despliegue

1. Desplegar migración y backend con el módulo deshabilitado.
2. Configurar claves de firma en Railway y verificar arranque.
3. Habilitar endpoints de agente sin cambiar la UI de producción.
4. Instalar un agente piloto y ejecutar exploración/validación de solo lectura.
5. Habilitar la nueva pestaña de servidores para administradores.
6. Ejecutar simulaciones del piloto y comparar conteos manualmente.
7. Probar cuarentena y restauración con archivos de prueba.
8. Habilitar operaciones reales por lotes pequeños.
9. Ampliar gradualmente hasta todas las propiedades.
10. Conservar rollback al transporte anterior mientras dure la versión de transición.

## 6. Puertas de seguridad antes de producción

No se habilitará limpieza real hasta cumplir todas:

- Revisión del protocolo y almacenamiento DPAPI.
- Pruebas negativas de rutas y reparse points.
- Pruebas de replay, expiración, revocación y aislamiento por tenant.
- Cuenta de servicio sin privilegios administrativos y permisos NTFS mínimos.
- Manifiesto del instalador firmado y verificado.
- Clave privada de Railway fuera de Git y con procedimiento de rotación.
- Simulación y restauración exitosas en un servidor piloto.
- Auditoría sin secretos ni contenido de archivos.
- Respaldo de PostgreSQL y procedimiento de rollback probado.

## 7. Verificación final

```powershell
python -m pytest backend/tests -q
python -m pytest backend/tests_prod -q
python -m pytest backend/tests_integration -q
python -m pytest agent/tests -q
npm --prefix frontend run type-check
npm --prefix frontend run build
Invoke-Pester installer/tests/AgentInstaller.Tests.ps1
```

Además se ejecutará el checklist operativo en Windows Server con un árbol representativo de más de 1500 propiedades y se archivará el informe de resultados sin datos sensibles.

## 8. Definición de terminado

- Agente instalable, vinculable, revocable y reconectable.
- Explorador de discos y carpetas funcional sin puertos entrantes.
- Configuración por servidor guardada únicamente tras validar.
- `Core` es el único contenedor operativo y `Web` está protegido.
- Objetivos configurables por servidor.
- Simulación durable y ejecución a cuarentena con idempotencia.
- Restauración y purga administrativa probadas.
- Identidad Ed25519, DPAPI, antirrepetición y rotación documentadas.
- Interfaz accesible y estados de error claros.
- Migración y rollback comprobados.
- Suites, build y aceptación operativa verdes.

