# Paridad funcional del backend productivo `app.main`

**Fecha:** 2026-07-30  
**Estado:** Diseño aprobado por el usuario  
**Objetivo:** Convertir `backend/app/main.py` en el único backend completo y desplegable de Gestor PRIMEE, con paridad respecto del frontend actual y de la lógica funcional validada en `backend/dev_server.py`.

## 1. Contexto

Gestor PRIMEE tiene actualmente dos backends:

- `backend/dev_server.py`, que contiene la mayor parte de la funcionalidad operativa, pero usa una arquitectura monolítica de desarrollo y persistencia local.
- `backend/app/main.py`, que ya contiene autenticación productiva, PostgreSQL, sesiones seguras, migraciones y health checks, pero mantiene rutas `501` y no registra varios módulos consumidos por el frontend.

El despliegue Windows/IIS inicia `app.main:app`. Por tanto, apuntar IIS a `dev_server.py` no es una solución aceptable.

## 2. Decisiones aprobadas

1. `app.main:app` será el único backend productivo.
2. El alcance será paridad funcional completa con el frontend, no solamente reemplazar los 28 stubs `501`.
3. PostgreSQL será la única persistencia productiva.
4. Todas las entidades y consultas se aislarán obligatoriamente por `tenant_id`.
5. Las credenciales SQL, SFTP, FTP, FTPS, PEM y passphrases nunca se persistirán.
6. APScheduler administrará las programaciones desde el mismo backend, sin Redis ni Celery.
7. La ejecución programada quedará detrás de una interfaz que permita moverla a trabajadores externos en el futuro.
8. Las limpiezas usarán simulación obligatoria, cuarentena reversible y purga administrativa explícita.
9. El rol `admin` heredará todas las capacidades del resto de roles.
10. La implementación será una migración modular incremental, reutilizando la lógica segura existente.

## 3. Alcance funcional

### 3.1 Módulos existentes que deben completarse

- Backups y conexiones SQL Server.
- Limpieza local.
- Accesos remotos.
- Dashboard.
- Notificaciones.
- Reportes.

### 3.2 Módulos ausentes en `app.main` que deben incorporarse

- Perfiles y pruebas de conexiones SQL Server.
- Gestor de archivos remoto.
- Limpieza remota normal.
- Limpieza remota estructural.
- Cuarentena y restauración remota.
- Administración de servidores remotos.
- Verificación y administración de host keys SSH.
- Búsqueda global.

### 3.3 Rutas y contratos

Se conservarán las rutas actualmente consumidas por el frontend. Se permiten extensiones aditivas en las respuestas para seguridad, paginación o trazabilidad.

Grupos principales:

- `/api/v1/auth`
- `/api/v1/users`
- `/api/v1/connections`
- `/api/v1/backups`
- `/api/v1/cleanup`
- `/api/v1/cleanup/remote`
- `/api/v1/access`
- `/api/v1/fm`
- `/api/v1/ssh/hostkeys`
- `/api/v1/dashboard`
- `/api/v1/notifications`
- `/api/v1/reports`
- `/api/v1/search`

Las rutas históricas que no tengan consumidor activo deberán implementarse como compatibilidad documentada o retirarse explícitamente. No permanecerán como stubs `501`.

## 4. Arquitectura

`app.main` será solamente el punto de composición:

```text
Router FastAPI
    -> autenticación, tenant y autorización
    -> esquema de entrada/salida
    -> servicio de aplicación
        -> reglas de dominio
        -> repositorio PostgreSQL
        -> adaptador de infraestructura
            -> sistema de archivos
            -> SQL Server
            -> SFTP / FTP / FTPS
            -> APScheduler
```

### 4.1 Routers

Responsabilidades:

- Validar parámetros y cuerpos.
- Obtener el usuario autenticado.
- Resolver `tenant_id` únicamente desde la sesión.
- Aplicar capacidades por rol.
- Transformar errores de dominio a respuestas HTTP estables.
- Serializar respuestas según el contrato del frontend.

No contendrán SQL, recorridos de archivos, conexiones remotas ni reglas de selección.

### 4.2 Servicios

Responsabilidades:

- Orquestar transacciones.
- Aplicar reglas de negocio.
- Coordinar repositorios y adaptadores externos.
- Emitir auditoría y notificaciones.
- Administrar transiciones de estado.
- Impedir operaciones fuera del tenant.

### 4.3 Repositorios

Responsabilidades:

- Concentrar consultas SQLAlchemy.
- Exigir `tenant_id` en toda operación sobre datos de negocio.
- Proveer paginación y bloqueos transaccionales cuando correspondan.
- Evitar consultas directas desde routers.

### 4.4 Dominio reutilizable

La lógica pura y segura existente en:

- `cleanup_rules.py`
- `remote_cleanup.py`
- `structural_cleanup.py`
- `sql_helpers.py`

se moverá o adaptará a módulos de dominio reutilizables bajo `backend/app/`. Durante la transición, `dev_server.py` podrá consumir esos módulos para mantener sus pruebas, pero la release productiva no dependerá de `dev_server.py`.

### 4.5 Adaptadores de infraestructura

Se crearán límites explícitos para:

- SQL Server y pyodbc.
- Sistema de archivos local.
- SFTP, FTP y FTPS.
- Hashes y verificación de integridad.
- APScheduler.
- Ejecución de trabajos en segundo plano.

Esto permitirá sustituir implementaciones en pruebas y mover trabajos a procesos externos en el futuro.

## 5. Persistencia

### 5.1 Tablas nuevas

#### Limpieza local

- `cleanup_folders`
- `cleanup_rules`
- `cleanup_schedules`
- `cleanup_executions`
- `cleanup_trash_items`

#### Limpieza remota

- `remote_servers`
- `ssh_host_keys`
- `remote_cleanup_executions`
- `remote_quarantine_items`
- `background_jobs`

#### Operación y avisos

- `notifications`

### 5.2 Tablas existentes

Se conservarán y ampliarán cuando sea necesario:

- `tenants`
- `users`
- `backups`
- `backup_schedules`
- `cleanup_logs`
- `access_logs`
- `audit_logs`
- `auth_sessions`
- `auth_refresh_history`
- `auth_login_limits`

`access_logs` se ampliará para cubrir cliente, notas, estado y cierre de una sesión. No se creará una segunda entidad duplicada si el modelo existente puede representar el ciclo completo.

### 5.3 Convenciones

- UUID para claves primarias.
- `tenant_id` obligatorio, con índice y clave foránea.
- Fechas UTC con zona horaria.
- `JSONB` para patrones, extensiones, allowlists y datos estructurados acotados.
- Restricciones únicas dentro de cada tenant.
- Índices para estado, fechas, `next_run_at`, trabajos pendientes y paginación.
- Borrado lógico para configuraciones cuando sea necesario conservar auditoría.
- Cuarentena como entidad explícita, no como borrado lógico genérico.

### 5.4 Datos sensibles

No se almacenarán:

- Contraseñas SQL Server.
- Contraseñas SFTP, FTP o FTPS.
- Llaves privadas PEM.
- Passphrases.
- Tokens de sesión en texto claro.

Los perfiles de servidores podrán guardar host, puerto, protocolo, usuario y allowlist, pero no secretos.

## 6. Programaciones y trabajos

### 6.1 APScheduler

- El backend tendrá un solo scheduler activo en el despliegue actual de un trabajador WinSW.
- Las definiciones de horario vivirán en PostgreSQL.
- Al iniciar, el backend reconciliará PostgreSQL con APScheduler.
- Crear, actualizar, activar o desactivar una programación actualizará ambos estados dentro de un flujo controlado.
- Los trabajos usarán identificadores persistentes e idempotentes.

### 6.2 Escalabilidad futura

Los servicios invocarán una interfaz de despacho. La implementación inicial ejecutará dentro del mismo backend; una implementación futura podrá publicar a trabajadores sin cambiar routers, esquemas ni reglas de dominio.

### 6.3 Recuperación

- Un trabajo persistirá estado, fase, progreso, resultado resumido y error.
- Al reiniciar, los trabajos que quedaron `running` se marcarán interrumpidos o se recuperarán según su tipo.
- No se repetirá automáticamente una operación destructiva sin prueba de idempotencia.
- La cancelación será cooperativa y persistente.

## 7. Flujos funcionales

### 7.1 Limpieza local

1. Escanear sin modificar archivos.
2. Persistir una simulación acotada al usuario, tenant y regla.
3. Mostrar candidatos y totales.
4. Ejecutar únicamente sobre una simulación vigente.
5. Revalidar existencia, ruta permitida y metadatos.
6. Si cambió el conjunto, responder `409`.
7. Mover a cuarentena.
8. Registrar resultado y auditoría.
9. Permitir restaurar.
10. Permitir purga solamente a `admin` con confirmación explícita.

### 7.2 Limpieza remota

Se conservarán:

- Allowlist fail-closed.
- Prevención de path traversal.
- Resolución segura de rutas.
- Simulación obligatoria.
- Conteo esperado.
- Verificación TOFU de host key SSH.
- Límites por cantidad y bytes.
- Cuarentena y restauración.
- Purga solamente administrativa.

Las credenciales existirán solamente dentro de la operación en curso.

### 7.3 Limpieza estructural

- Se ejecutará como trabajo persistente.
- Informará propiedades totales y procesadas.
- Permitirá simulación, ejecución y cancelación.
- El modo directo será exclusivo de `admin`, requerirá confirmación explícita y conservará auditoría completa.
- El modo predeterminado será cuarentena.

### 7.4 Backups

#### Manuales

1. Validar permiso y entrada.
2. Crear registros `pending`.
3. Despachar el trabajo.
4. Cambiar a `running`.
5. Ejecutar y verificar.
6. Guardar ruta, tamaño, hash y resultado.
7. Cambiar a `completed` o `failed`.
8. Generar notificación y auditoría.

#### Programados

- Usarán la conexión SQL Server configurada en `production.env`.
- No reutilizarán credenciales efímeras introducidas en una sesión web.
- Aplicarán retención e integridad.
- Una ejecución no podrá duplicarse para la misma programación y ventana.

### 7.5 Accesos

- Crear sesión con actor, servidor, IP, herramienta, motivo y cliente.
- Cerrar sesión con notas, hora final y duración.
- Consultar sesiones activas y cerradas.
- Detectar y marcar actividad sospechosa.
- Generar logs descargables sin secretos.
- Permitir eliminar registros solamente según la política de retención y permisos.

### 7.6 Dashboard

Se calculará desde información real:

- Resumen operativo.
- Historial de backups.
- Actividad reciente.
- Alertas.
- Crecimiento de almacenamiento.
- Métricas por estado.

Las rutas existentes del frontend (`summary`, `backup-chart`, `activity`) se conservarán. Las rutas productivas adicionales podrán mantenerse como alias documentados.

### 7.7 Notificaciones

Se generarán por:

- Backup completado o fallido.
- Limpieza completada, parcial o fallida.
- Acceso sospechoso.
- Error o interrupción de un trabajo.
- Dependencia no disponible.

El endpoint de prueba será administrativo.

### 7.8 Reportes y búsqueda

- Los reportes consultarán datos operativos sin duplicarlos.
- Toda exportación aplicará tenant y permisos.
- La búsqueda global consultará solamente recursos visibles para el usuario.
- Se limitarán resultados y se paginarán las búsquedas amplias.

### 7.9 Gestor de archivos

- Las credenciales serán efímeras.
- Se validará la ruta contra la allowlist.
- Listar y crear directorios requerirá capacidad operativa.
- Eliminar utilizará confirmación y las protecciones de ruta correspondientes.
- No se incluirán secretos en auditoría.

## 8. Autorización

Los roles existentes se conservarán:

### `admin`

- Hereda todas las capacidades de los demás roles.
- Administra usuarios, perfiles de servidores, programaciones y configuración.
- Ejecuta operaciones normales.
- Autoriza purgas y modos irreversibles.
- Puede enviar notificaciones de prueba.

### `supervisor`

- Consulta dashboard, historiales y reportes.
- Ejecuta backups.
- Opera accesos.
- Simula y ejecuta limpiezas reversibles.
- No purga ni administra usuarios o configuración crítica.

### `technician`

- Ejecuta operación diaria.
- Prueba conexiones.
- Ejecuta backups.
- Abre y cierra accesos.
- Simula y ejecuta limpiezas a cuarentena.
- Consulta sus resultados operativos.

### `client`

- Solo lectura de dashboard, estados, historiales y reportes permitidos.
- No ejecuta cambios.

La autorización se expresará mediante capacidades reutilizables. `admin` tendrá una capacidad global. Las verificaciones de rol del frontend serán solo de presentación; el backend será la autoridad.

## 9. Contrato de errores

- `400`: solicitud incoherente.
- `401`: sesión ausente, inválida o vencida.
- `403`: capacidad insuficiente.
- `404`: recurso inexistente dentro del tenant actual.
- `409`: conflicto, simulación vencida, cambio concurrente o estado incompatible.
- `422`: datos inválidos.
- `503`: PostgreSQL, SQL Server, SFTP, FTP, sistema de archivos u otra dependencia no disponible.
- `500`: fallo interno inesperado.

Los errores de dominio tendrán códigos estables. Los `500` incluirán un identificador de correlación y nunca devolverán stack traces, rutas sensibles, credenciales o consultas completas.

Todas las operaciones externas fallarán de forma cerrada. Sin tenant, capacidad, allowlist, host key o simulación válida no habrá modificación.

## 10. Auditoría

Se registrará:

- Tenant.
- Actor.
- Acción.
- Recurso y su identificador.
- Resultado.
- Fecha.
- IP y metadatos seguros.
- Identificador de correlación.

Antes de registrar solicitudes se eliminarán claves como:

- `password`
- `privateKey`
- `passphrase`
- `token`
- `secret`
- cadenas de conexión

La auditoría no sustituye a los historiales funcionales.

## 11. Health y migraciones

- Alembic tendrá migraciones pequeñas y ordenadas por dominio.
- Las migraciones conservarán datos existentes.
- Toda migración tendrá ruta de reversión cuando sea técnicamente segura.
- `/health/live` comprobará únicamente el proceso.
- `/health/ready` comprobará PostgreSQL y que la revisión aplicada coincida con el `head` incluido en la release.
- Se eliminará la revisión Alembic esperada codificada manualmente.

## 12. Pruebas

### 12.1 Unitarias

- Reglas de selección.
- Seguridad de rutas.
- Allowlist.
- Transiciones de estado.
- Permisos.
- Serialización.
- Cálculos de dashboard y reportes.
- Reconciliación del scheduler.

### 12.2 Repositorios

- PostgreSQL real de pruebas.
- Filtros obligatorios por tenant.
- Restricciones únicas.
- Paginación.
- Bloqueos y concurrencia.

### 12.3 Contratos API

- Todas las rutas consumidas por el frontend.
- Esquemas de entrada y salida.
- Códigos de error.
- Autenticación por cookies y CSRF.

### 12.4 Autorización

- Matriz completa de roles.
- `admin` puede realizar cualquier operación.
- `client` no puede modificar.
- Ningún rol accede a datos de otro tenant.

### 12.5 Integración

- Directorios temporales para limpieza local.
- SQL Server falso o adaptador simulado.
- SFTP, FTP y FTPS falsos.
- Reinicio y cancelación de trabajos.
- Scheduler y recuperaciones.

### 12.6 Seguridad

- Traversal.
- Symlinks o enlaces fuera de raíz.
- Allowlist fail-closed.
- Host key desconocida o cambiada.
- Simulación alterada.
- Secretos ausentes de logs.
- Acceso cruzado por tenant.
- CSRF y cookies seguras.

### 12.7 Regresión y release

- 79 pruebas del backend de desarrollo.
- 21 pruebas productivas existentes.
- 11 pruebas Pester del instalador.
- Type-check del frontend.
- Build standalone.
- Generación y validación del manifiesto SHA-256.
- Smoke test con PostgreSQL.
- Ensayo IIS/HTTPS.

## 13. Implementación incremental

Orden previsto:

1. Contratos comunes, capacidades y errores.
2. Modelos y migraciones PostgreSQL.
3. Repositorios base.
4. Limpieza local.
5. Limpieza remota y host keys.
6. Gestor de archivos.
7. Accesos.
8. Backups, conexiones y scheduler.
9. Dashboard, notificaciones, reportes y búsqueda.
10. Integración de routers en `app.main`.
11. Eliminación de Celery/Redis del runtime y documentación.
12. Regresión completa, release y ensayo IIS.

Cada bloque deberá quedar probado antes de continuar. No se sustituirán todos los módulos en un único cambio sin puntos de verificación.

## 14. Fuera de alcance

- Almacenar credenciales de conexiones definidas por usuarios.
- Redis.
- Celery.
- Escalado horizontal en la primera instalación.
- Rediseño visual del frontend.
- Integraciones externas de notificación no configuradas actualmente.
- Cambios de producto no necesarios para paridad.

La arquitectura dejará límites preparados para incorporar un almacén de secretos, trabajadores externos o múltiples instancias en una fase futura.

## 15. Criterios de aceptación

La paridad estará terminada cuando:

1. Todas las rutas activas del frontend estén registradas en `app.main`.
2. No queden respuestas `501`.
3. La release no dependa de `dev_server.py`.
4. La release no use SQLite, Redis ni Celery.
5. Toda consulta de negocio aplique `tenant_id`.
6. Las credenciales sensibles no se persistan ni aparezcan en logs.
7. Las limpiezas requieran simulación y sean reversibles salvo purga administrativa.
8. APScheduler cargue y ejecute programaciones persistidas.
9. Los trabajos sobrevivan o se recuperen de reinicios de forma definida.
10. `admin` pueda realizar todas las operaciones.
11. La matriz de permisos se aplique en el backend.
12. Todas las suites y builds estén verdes.
13. `/health/ready` valide dependencias y migración actual.
14. La release pase smoke test con PostgreSQL.
15. El flujo completo funcione a través de IIS y HTTPS.
