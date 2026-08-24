# Plan de implementación: respaldo directo de bases grandes

**Especificación:** `docs/superpowers/specs/2026-08-21-large-database-direct-backup-design.md`  
**Versión objetivo del agente:** 0.5.0

## Reglas

- Mantener compatible el flujo existente `.bak → ZIP → SMB/SFTP`.
- Activar el flujo nuevo únicamente con un destino de tipo `smb_direct`.
- No almacenar credenciales nuevas ni sobrescribir respaldos definitivos.
- Escribir pruebas antes del comportamiento y conservar un único head de Alembic.

## Entrega 1 — Contrato compatible

1. Permitir `smb_direct` en perfiles administrados y metadata pública.
2. Resolver el tipo de destino en backend y enviar `deliveryMode=direct` en la orden.
3. Proyectar el resultado directo como entrega verificada sin exigir campos ZIP.
4. Probar perfiles inválidos, payload de orden, progreso y finalización.

Archivos principales:

- `backend/app/services/agent_profile_service.py`
- `backend/app/services/agent_operation_service.py`
- `backend/app/services/agent_command_service.py`
- `backend/tests_prod/test_agent_profile_service.py`
- `backend/tests_prod/test_agent_backup_lifecycle.py`

## Entrega 2 — Motor del agente

1. Separar `run_batch` en flujo archivado y flujo directo.
2. Validar que el destino directo sea UNC y estimar el espacio en ese volumen.
3. Crear una carpeta diaria y un archivo temporal por ejecución en el destino.
4. Ejecutar `BACKUP ... WITH CHECKSUM, COMPRESSION` cuando la instancia lo admita;
   si SQL rechaza compresión, registrar la capacidad y reintentar sin ella antes de
   haber creado un respaldo parcial válido.
5. Ejecutar `RESTORE VERIFYONLY WITH CHECKSUM`, calcular SHA-256 y renombrar dentro
   del mismo volumen.
6. Rechazar conflictos de nombre y reportar `deliveryMode`, ruta, tamaño, hash y
   espacio restante.
7. Probar que no se crea carpeta `.work`, ZIP ni limpieza local en modo directo.

Archivos principales:

- `agent/data_express_agent/backup.py`
- `agent/data_express_agent/profiles.py`
- `agent/tests/test_backup.py`
- `agent/tests/test_profiles.py`

## Entrega 3 — Operación en frontend

1. Mostrar `Directo SMB` en el asistente de conexiones.
2. Identificar el tipo del destino en el modal de nuevo respaldo.
3. Cambiar las etiquetas de progreso de ZIP a respaldo directo cuando corresponda.
4. Mostrar `Directo y validado` como entrega terminal.
5. Mantener selección masiva y compatibilidad con destinos ZIP.

Archivos principales:

- `frontend/src/components/agents/agent-connection-wizard.tsx`
- `frontend/src/components/backups/agent-trigger-backup-modal.tsx`
- `frontend/src/types/agent.ts`
- `frontend/src/types/backup.ts`

## Entrega 4 — Verificación y paquete

1. Ejecutar pruebas backend y agente.
2. Ejecutar type-check y build del frontend.
3. Compilar el agente con Python 3.11.
4. Verificar hash y contenido del ejecutable.
5. Generar el paquete 0.5.0 únicamente con URL y claves públicas de producción;
   nunca inventar esos valores.

## Piloto de 1 TB

El despliegue global permanecerá desactivado hasta completar un piloto con una base
representativa. El piloto debe registrar espacio inicial/final, duración, tamaño
del `.bak`, validación y una restauración real en una instancia aislada.
