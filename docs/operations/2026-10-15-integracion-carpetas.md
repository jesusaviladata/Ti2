# Integración de tareas de carpetas

Implementación del tramo pendiente de la especificación aprobada `docs/superpowers/specs/2026-08-20-file-backup-module-design.md`: asistente lateral de cuatro pasos, destino local administrado o SMB existente, prueba de destino y simulación, activación y pausa, elección manual Full/incremental/diferencial e historial.

El planificador comprueba tareas activas cada 30 segundos, calcula la última franja debida en la zona configurada y evita repetirla consultando `scheduledFor` en las ejecuciones persistidas. Bloquea la fila de tarea mientras encola para coordinar instancias del backend. `run_once` conserva una franja pendiente si el agente está desconectado; `skip` descarta franjas con más de un minuto de retraso. No se ejecutan franjas anteriores a la creación de la tarea. La proyección del resultado conserva los metadatos de programación.

Se reutilizan los comandos firmados ya soportados por el agente 0.5.1. No se requiere reconstruirlo. La tarea del asistente se crea pausada y su botón de activación espera una simulación y una prueba de destino exitosas. Los destinos locales se validan como rutas absolutas Windows. La limpieza por retención, VSS, ZIP64, SFTP para archivos y la restauración desde el panel quedan fuera de este tramo; no se presentan como disponibles. La recuperación local por manifiestos ya se verificó por separado.

Validación inicial: 190 pruebas del backend aprobadas y compilación de producción del frontend aprobada. La comprobación real en Railway se registra al finalizar.
