# Diseño de almacenamiento, conexiones y confiabilidad del agente

**Fecha:** 2026-08-20  
**Estado:** Aprobado para revisión escrita  
**Alcance:** agente Windows 0.4.0, backend, frontend y migraciones

## 1. Objetivo

Hacer que los backups sean identificables y previsibles, advertir antes de saturar un disco, administrar perfiles de conexión desde el dashboard sin exponer secretos, unificar Limpieza alrededor del agente y evitar falsas desconexiones mientras SQL Server ejecuta operaciones largas.

La experiencia final debe permitir que un operador responda rápidamente:

- de qué agente e instancia SQL proviene cada respaldo;
- si el `.bak` quedó creado y validado;
- si el ZIP sigue procesándose o ya fue entregado y verificado;
- cuánto espacio queda en los discos involucrados;
- qué configuración de SQL Server y destino está aplicada realmente en cada agente;
- por qué un agente está conectado, ocupado, degradado o desconectado.

## 2. Alcance dividido en entregas

El cambio se implementará como un solo programa versionado, pero se desplegará en este orden:

1. Confiabilidad, telemetría de disco y seguimiento correcto de entrega.
2. Convención de nombres, origen persistido y estructura del destino.
3. Administración central de perfiles y asistente de conexión.
4. Unificación del módulo de Limpieza.
5. Empaquetado, actualización y prueba real del agente 0.4.0.

Cada entrega conservará compatibilidad de lectura con registros creados por el agente 0.3.0. Las funciones que dependan del protocolo nuevo se bloquearán de forma explícita hasta que el agente correspondiente esté actualizado.

## 3. Convención de almacenamiento

### 3.1 Estructura del destino

La estructura visible será exactamente:

```text
Destino\
└─ 2026-08-20\
   ├─ FULL\
   │  └─ Backup_2026-08-20.zip
   └─ DIFERENCIAL\
      └─ Backup_2026-08-20.zip
```

En SFTP se utilizarán los mismos segmentos con `/`.

La raíz `Destino` pertenece al perfil asignado al agente. No se agregará una carpeta de origen entre la raíz y la fecha. Para impedir que dos agentes sobrescriban el mismo archivo, el asistente rechazará que dos agentes utilicen simultáneamente la misma combinación de perfil y raíz remota, salvo que el administrador confirme que el almacenamiento está aislado externamente.

### 3.2 Nombres de archivos SQL

Los archivos conservarán el nombre exacto de la base de datos y sustituirán `_FULL` por la fecha:

```text
ClienteCR_Alebrijes_TEST_2026-08-20.bak
ClienteCR_Alebrijes_TEST_2026-08-20_DIF.bak
ClienteCR_Alebrijes_TEST_2026-08-20_LOG.trn
```

- Full: `<Base>_<AAAA-MM-DD>.bak`.
- Diferencial: `<Base>_<AAAA-MM-DD>_DIF.bak`.
- Log: `<Base>_<AAAA-MM-DD>_LOG.trn`.
- No se normalizará, traducirá ni abreviará el nombre original de la base.
- Los caracteres no admitidos por Windows se rechazarán antes de iniciar la orden.

### 3.3 Repetición durante el mismo día

Existirá un solo ZIP vigente por fecha y tipo. Si se repite un Full o Diferencial el mismo día:

1. el agente construirá el nuevo ZIP bajo un nombre temporal `.part`;
2. verificará su integridad y SHA-256;
3. conservará el ZIP anterior hasta completar la verificación;
4. reemplazará el ZIP diario de manera atómica;
5. transferirá y verificará el nuevo artefacto en destino;
6. registrará en auditoría que reemplazó una revisión anterior.

No se agregarán identificadores de ejecución, horas ni números aleatorios al nombre visible. El `runId` seguirá existiendo únicamente como identificador interno de auditoría e idempotencia.

### 3.4 Diferenciador de origen

El origen no formará parte de la ruta visible del destino. Cada registro persistirá una instantánea de:

- identificador y nombre del agente;
- hostname del equipo;
- identificador y etiqueta del perfil SQL;
- servidor e instancia SQL sin credenciales;
- identificador y etiqueta del destino;
- ruta final del ZIP;
- revisión de configuración aplicada.

La tabla de Backups tendrá una columna `Origen` y el detalle mostrará la cadena `Agente · Instancia SQL`. El ZIP contendrá un `manifest.json` con esos mismos datos, lista de bases, tipo, hashes y fechas. El manifiesto no incluirá secretos.

## 4. Estados de backup y entrega

Se conservarán dos máquinas de estado separadas.

### 4.1 Respaldo SQL

```text
Pendiente → Creando .bak → Validando .bak → Backup listo
                                           ↘ Backup fallido
```

`Backup listo` exige archivo materializado y `RESTORE VERIFYONLY` correcto. Existencia, tamaño o SHA-256 no sustituyen esa validación.

### 4.2 ZIP y entrega

```text
Pendiente → Comprimiendo → Verificando ZIP → Enviando → Entregado
                                                ↘ Entrega fallida
```

`Entregado` exige verificar en destino tamaño y SHA-256. Un fallo de entrega no cambia un `.bak` validado a fallido. La entrega se podrá reintentar sin volver a ejecutar SQL Server.

El frontend continuará consultando mientras cualquiera de los dos estados no sea terminal. La ventana de ejecución y la tabla mostrarán el mismo estado durable; cerrar la ventana no afectará el trabajo.

## 5. Telemetría y protección de espacio

### 5.1 Datos reportados

El agente reportará cada 30 segundos, desde un hilo independiente, los volúmenes relacionados con:

- raíz local de backups;
- raíz de Limpieza;
- destinos locales o SMB montados cuando Windows pueda consultar su capacidad.

Por volumen se enviará:

- unidad o punto de montaje;
- etiqueta del volumen;
- capacidad total;
- espacio libre;
- porcentaje usado;
- funciones asociadas (`backup`, `cleanup`, `destination`);
- instante de observación;
- error de lectura, cuando exista.

### 5.2 Barra superior

El dashboard mostrará una banda compacta inspirada en el Explorador de Windows:

```text
Data (D:)
██████████████░░░░
2.20 TB disponibles de 3.40 TB
```

La banda aparecerá en la parte superior de todas las páginas operativas. Si hay varios agentes o discos, mostrará el más crítico y permitirá desplegar el resto. Siempre indicará agente, volumen y tiempo de la última medición.

Estados visuales:

- normal: verde;
- advertencia: menos de 20 % o menos de 20 GB libres;
- crítico: menos de 10 % o menos de 10 GB libres;
- sin datos: gris con hora del último reporte.

Los umbrales serán valores predeterminados configurables por tenant. Las alertas se deduplicarán por agente y volumen, se actualizarán mientras continúe el problema y se cerrarán automáticamente al recuperar espacio.

### 5.3 Reserva preventiva

Antes de iniciar un backup, el agente estimará el espacio temporal requerido usando historial de backups cuando exista y tamaño asignado de la base como respaldo conservador. Debe considerar simultáneamente `.bak`, ZIP temporal y reserva mínima del volumen.

La orden se bloqueará si:

```text
espacio_libre - espacio_estimado < reserva_critica
```

El bloqueo mostrará espacio libre, estimación, reserva y volumen. Una ejecución en curso que atraviese el umbral crítico emitirá alerta inmediata, pero SQL Server sólo se cancelará cuando exista un mecanismo seguro; no se terminará el proceso de forma abrupta dejando un estado ambiguo.

## 6. Confiabilidad y presencia del agente

### 6.1 Causa observada

En 0.3.0, heartbeat, long polling y ejecución comparten el mismo ciclo. Un `BACKUP DATABASE` largo bloquea el ciclo y puede dejar más de tres minutos sin solicitudes, por lo que el backend muestra al agente como desconectado aunque continúe trabajando.

### 6.2 Modelo nuevo

El agente 0.4.0 tendrá un supervisor de conectividad independiente del ejecutor:

- heartbeat cada 30 segundos aunque exista una orden larga;
- metadatos de salud y disco enviados sin esperar a SQL Server;
- reintentos con backoff y jitter;
- journal durable para reportes pendientes;
- estado actual de la orden sin incluir datos sensibles;
- recuperación automática del servicio mediante WinSW.

Estados visibles:

- `Conectado`: heartbeat reciente y sin operación activa;
- `Ocupado`: heartbeat reciente y orden activa;
- `Degradado`: heartbeat reciente con fallo de telemetría o sincronización;
- `Desconectado`: heartbeat vencido;
- `Revocado`: identidad invalidada deliberadamente.

El backend distinguirá `lastHeartbeatAt` de la última solicitud general. Una operación no se considerará fallida únicamente porque la interfaz perdió presencia temporal.

## 7. Administración central de conexiones

### 7.1 Principio

Los perfiles se administrarán desde `Configuración → Agentes → Conexiones`. El backend mantendrá la configuración deseada y el agente reportará la revisión realmente aplicada.

Estados de sincronización:

- `Aplicado`;
- `Pendiente de sincronizar`;
- `Probando`;
- `Error de configuración`;
- `Requiere secreto local`.

Una edición realizada mientras el agente esté desconectado quedará pendiente y se aplicará al reconectarse.

### 7.2 Perfiles SQL Server

El asistente ofrecerá:

1. detectar drivers ODBC instalados;
2. detectar instancias SQL locales visibles;
3. seleccionar instancia y raíz local de backup;
4. mostrar la identidad real del servicio Windows;
5. probar conexión a `master`;
6. listar bases accesibles;
7. probar permisos de backup y `RESTORE VERIFYONLY` con una operación controlada;
8. generar el script SQL mínimo requerido cuando falte un permiso;
9. guardar y aplicar el perfil.

La autenticación integrada de Windows será la opción recomendada. La autenticación SQL sólo se habilitará como compatibilidad avanzada y nunca devolverá la contraseña al navegador después de guardarla.

### 7.3 Perfiles de destino

Tipos disponibles:

- local;
- SMB/UNC;
- SFTP.

Cada perfil tendrá etiqueta, tipo, ruta, host, puerto, usuario, huella del host y referencia de secreto según corresponda. La prueba ejecutará:

1. conexión;
2. creación de archivo temporal;
3. lectura;
4. comparación SHA-256;
5. renombrado atómico;
6. eliminación del archivo de prueba.

El perfil sólo podrá marcarse `Aplicado` después de superar la prueba.

### 7.4 Secretos

Los valores no sensibles se persistirán normalmente en el backend. Contraseñas y llaves seguirán estas reglas:

- se capturan una sola vez en un formulario protegido;
- se cifran para la identidad de cifrado del agente;
- el backend persiste únicamente el sobre cifrado y metadatos de versión;
- el agente descifra y guarda localmente mediante DPAPI ligado a la cuenta del servicio;
- las respuestas del API nunca incluyen el secreto;
- editar datos no sensibles no obliga a volver a capturar el secreto;
- cambiar la cuenta del servicio invalida secretos DPAPI y lo muestra como `Requiere secreto local`.

El agente incorporará una clave de cifrado independiente de la clave Ed25519 utilizada para firmar solicitudes. No se reutilizarán claves de firma como claves de cifrado.

## 8. Asistente guiado

El alta o reparación de un agente seguirá una sola secuencia:

```text
Vincular agente
→ Detectar entorno
→ Configurar SQL Server
→ Validar permisos
→ Elegir raíz de backup
→ Configurar y probar destino
→ Configurar raíz de Limpieza
→ Resumen y activación
```

El asistente podrá reabrirse para reparar únicamente el paso fallido. Mostrará comandos o scripts copiables cuando una acción requiera privilegios de Windows o SQL Server que el agente no debe autoasignarse.

## 9. Unificación de Limpieza

La navegación conservará una sola opción `Limpieza`, ubicada en `/dashboard/cleanup`. `/dashboard/limpieza-remota` redirigirá temporalmente a la ruta nueva. Se retirará de la interfaz normal el módulo `Archivos` FTP/SFTP y el formulario heredado de servidores remotos.

El flujo único será:

```text
Simular → Revisar → Confirmar → Resultado
```

Reglas:

- sólo agentes vinculados;
- una raíz fija validada por agente;
- propiedades hijas directas de la raíz;
- objetivos fijos `core\Log`, `LogSec`, `LogsRadian`, `Respuesta` y `BD_log.txt`;
- eliminación de archivos y conservación de carpetas;
- rechazo de enlaces, puntos de repetición y rutas fuera de alcance;
- simulación durable y manifiesto inmutable;
- confirmación explícita antes de eliminación definitiva;
- resultado parcial cuando existan archivos bloqueados;
- historial con actor, agente, manifiesto, bytes y errores.

No se expondrán cuarentena, FTP/FTPS/SFTP ni reglas arbitrarias en el nuevo frontend. El código heredado se conservará sin consumidores durante una versión y se retirará después de comprobar que no existen dependencias.

## 10. Persistencia y contratos

El backend agregará persistencia para:

- instantánea de origen en cada backup;
- telemetría de volúmenes y último heartbeat;
- alertas de espacio deduplicadas;
- perfiles SQL y destinos administrados;
- revisión deseada y revisión aplicada por agente;
- sobres cifrados de secretos;
- pruebas de conexión y sus resultados sanitizados.

Comandos nuevos o ampliados:

- `discover_agent_environment`;
- `apply_connection_profiles`;
- `test_sql_profile`;
- `test_destination_profile`;
- `collect_storage_telemetry`;
- `run_backup_batch` con convención de nombres y origen;
- comandos actuales de Limpieza reconciliados en una sola implementación.

Todas las órdenes seguirán firmadas, ligadas a tenant, agente, revisión e idempotency key.

## 11. Interfaz

La interfaz conservará el sistema oscuro existente, profundidad por bordes sutiles y colores semánticos. La firma visual será la combinación de barra de volumen y línea de fases operativas.

Componentes principales:

- `StorageHealthBar`: volumen, capacidad y alertas en la parte superior;
- `BackupOriginCell`: agente e instancia SQL;
- `BackupDeliveryStatus`: ZIP local, enviando, entregado o reintentar;
- `AgentConnectionWizard`: asistente de descubrimiento y configuración;
- `ManagedProfilesPanel`: edición, prueba y sincronización;
- `AgentHealthBadge`: conectado, ocupado, degradado o desconectado;
- `CleanupPhaseRail`: simulación, revisión, confirmación y resultado.

La tabla de Backups actualizará cada cinco segundos mientras existan entregas activas. El detalle individual consultará hasta que respaldo y entrega alcancen estados terminales.

## 12. Seguridad

- Nunca se mostrarán contraseñas, llaves privadas ni sobres cifrados.
- Los logs sanitizarán cadenas ODBC, passwords y rutas sensibles cuando sea necesario.
- El agente validará nuevamente rutas y revisiones; no confiará únicamente en el frontend.
- Los perfiles de destino tendrán allowlist de tipos y validación estricta.
- Las huellas SFTP deberán aprobarse explícitamente; no habrá política de aceptación automática.
- Las pruebas usarán archivos con prefijo reservado y los eliminarán al terminar.
- La telemetría no incluirá listados de archivos.
- Las capacidades separarán lectura, edición de perfiles, pruebas, ejecución de backup y eliminación.

## 13. Manejo de errores

- Espacio insuficiente: orden bloqueada antes de SQL Server y alerta crítica.
- Telemetría no disponible: estado degradado; no se inventan valores.
- Perfil pendiente: no puede seleccionarse para una operación nueva.
- Secreto inválido: perfil marcado `Requiere secreto local`.
- Prueba de destino fallida: se conserva la configuración anterior aplicada.
- Desconexión durante una orden: el trabajo seguro continúa y el journal reporta al reconectar.
- ZIP nuevo inválido: se conserva el ZIP diario anterior.
- Transferencia fallida: se conserva `.bak` validado y ZIP local; se ofrece reintento.
- Limpieza modificada después de simular: ejecución rechazada y nueva simulación obligatoria.

## 14. Pruebas de aceptación

### Nombres y origen

1. Full produce `<Base>_<Fecha>.bak` y no contiene `_FULL`.
2. Diferencial conserva `_DIF` y la fecha.
3. El ZIP visible se llama `Backup_<Fecha>.zip`.
4. Full y Diferencial se almacenan en carpetas separadas.
5. Una repetición reemplaza atómicamente el ZIP diario sólo después de verificarlo.
6. La tabla y el manifiesto identifican agente e instancia SQL.

### Espacio

1. El agente reporta capacidad durante una orden SQL larga.
2. La barra representa correctamente libre y total.
3. Los umbrales producen y resuelven una sola alerta por volumen.
4. Un backup estimado que invadiría la reserva crítica no inicia.
5. Un error al consultar disco se muestra como degradado, no como cero bytes.

### Conectividad

1. Un backup mayor a diez minutos no cambia el agente a desconectado.
2. El estado ocupado conserva heartbeat.
3. Una caída de Railway reintenta y reporta el resultado durable al volver.
4. WinSW reinicia el proceso ante una salida inesperada.

### Perfiles y asistente

1. Se detectan drivers e instancias disponibles.
2. La prueba identifica permisos faltantes y genera el script correcto.
3. Un perfil editado offline queda pendiente y luego se aplica.
4. Los secretos nunca aparecen en respuestas ni logs.
5. SMB y SFTP verifican escritura, lectura y SHA-256.
6. Una huella SFTP distinta bloquea la conexión.

### Limpieza

1. Sólo existe un módulo visible de Limpieza.
2. No aparecen credenciales FTP/SFTP ni cuarentena.
3. No se puede ejecutar sin simulación vigente.
4. Sólo se vacían los cinco objetivos aprobados y se conservan carpetas.
5. El historial refleja éxitos parciales y archivos bloqueados.

## 15. Migración y despliegue

1. Añadir migraciones compatibles hacia adelante para telemetría, perfiles y origen.
2. Desplegar backend capaz de aceptar 0.3.0 y 0.4.0.
3. Publicar frontend con bloqueo por capacidades y versión.
4. Construir y probar el agente 0.4.0 en un servidor controlado.
5. Actualizar un agente piloto y observar heartbeat, disco, backup y entrega.
6. Migrar perfiles locales existentes al modelo administrado sin copiar secretos al navegador.
7. Actualizar el resto de agentes.
8. Activar el nuevo módulo único de Limpieza.
9. Retirar consumidores y navegación heredados después de una versión estable.

## 16. Decisiones finales

- La ruta visible será `Destino\Fecha\Tipo\Backup_Fecha.zip`.
- El origen se mostrará en metadatos, manifiesto y dashboard, no como carpeta adicional.
- La repetición diaria sustituirá el ZIP de forma atómica y auditable.
- La barra de disco imitará la lectura del Explorador de Windows.
- El heartbeat será independiente de las operaciones.
- Los perfiles se editarán centralmente y los secretos se protegerán por agente y DPAPI.
- SQL integrado y SMB serán las rutas recomendadas; SQL autenticado y SFTP serán avanzadas.
- Limpieza quedará unificada, manual, estructural y directa después de simular.
- El conjunto requiere el agente 0.4.0.

