# Diseño del módulo Respaldo de archivos

**Fecha:** 2026-08-20  
**Estado:** aprobado por el usuario
**Versión objetivo del agente:** 0.5.0  
**Alcance:** agente Windows, backend, frontend, instalador y migraciones

## 1. Objetivo

Incorporar a Data Express un módulo centralizado para respaldar archivos y carpetas de servidores Windows. El módulo toma como referencia funcional la automatización de Cobian Reflector, pero se implementa de forma independiente, sin copiar su código, nombre o interfaz.

El operador debe poder:

- vincular un servidor sin editar archivos JSON;
- elegir qué carpetas proteger y dónde guardarlas;
- programar copias Full, incrementales o diferenciales;
- conocer si una copia quedó verificada;
- continuar una ejecución interrumpida sin repetir archivos confirmados;
- conservar cadenas completas y proteger copias especiales;
- simular y ejecutar una restauración al origen o a otra ubicación;
- administrar todo desde el dashboard usando lenguaje no técnico.

Fuentes funcionales consultadas:

- https://cobiansoft.com/crHelp/what_is.html
- https://cobiansoft.com/crHelp/tasks.html
- https://cobiansoft.com/crHelp/backups.html
- https://cobiansoft.com/crHelp/recovery.html
- https://cobiansoft.com/crHelp/license.html

## 2. Alcance de la primera versión

### 2.1 Incluido

- Archivos y carpetas de Windows.
- Una o varias fuentes por tarea.
- Destinos locales, UNC/SMB y SFTP.
- Backups Full, incrementales y diferenciales.
- Estructura directa de carpetas como formato predeterminado.
- ZIP64 opcional para tareas pequeñas o medianas.
- Filtros por ruta, máscara, extensión, tamaño y antigüedad.
- Volume Shadow Copy Service para archivos bloqueados.
- Catálogo local de cambios y hashes.
- Reanudación por archivo mediante checkpoints.
- Verificación de contenido en destino.
- Historial, alertas, retención y copias protegidas.
- Restauración al origen o a una ubicación alternativa.
- Simulación obligatoria antes de restaurar.
- Instalador universal con código temporal de vinculación.
- Configuración administrada desde el dashboard.

### 2.2 Excluido inicialmente

- Imagen completa del sistema operativo.
- Recuperación bare-metal.
- Backups de estado del sistema de Windows.
- FTP sin cifrado.
- Destinos de nube pública.
- Modo espejo destructivo.
- Ejecución arbitraria de programas antes o después de una tarea.
- Seguimiento de junctions, enlaces simbólicos o reparse points.
- Dependencia o integración binaria con Cobian Reflector.

## 3. Arquitectura

Se ampliará el Data Express Agent actual. No se instalará un segundo servicio.

```text
Dashboard
   ↓ REST
Backend
   ↓ orden firmada / long polling
Data Express Agent
   ├─ Supervisor de conectividad y salud
   ├─ Cola y coordinador de recursos
   ├─ Motor de backup SQL existente
   ├─ Motor de limpieza existente
   └─ Motor file_backup nuevo
        ├─ Preflight
        ├─ Exploración y filtros
        ├─ Catálogo de cambios
        ├─ VSS
        ├─ Copia y checkpoint
        ├─ Validación
        ├─ Publicación
        ├─ Entrega
        ├─ Retención
        └─ Restauración
```

El motor `file_backup` tendrá una interfaz independiente del motor SQL. Ambos compartirán el coordinador de recursos del agente. El coordinador impedirá dos operaciones pesadas simultáneas sobre el mismo volumen de origen, trabajo o destino.

El heartbeat continuará en su hilo independiente durante exploraciones, copias, verificaciones y restauraciones.

## 4. Instalación y conexión simplificadas

### 4.1 Experiencia de instalación

El paquete oficial contendrá un dominio estable de control —no una URL temporal del proveedor de hosting—, la confianza inicial para firmas de comandos y los valores seguros de funcionamiento. En PowerShell elevado se ejecutará:

```powershell
.\Install-DataExpressAgent.ps1
```

El instalador solicitará únicamente un código de vinculación temporal mediante entrada interactiva. El código:

- será de un solo uso;
- expirará en diez minutos;
- se almacenará sólo como hash en el backend;
- no se escribirá en la línea de comandos ni quedará en su historial;
- se eliminará localmente al completar o fallar definitivamente el enrolamiento.

### 4.2 Configuración local

El operador no editará `agent.json`. La configuración interna local contendrá sólo parámetros de bootstrap y runtime. Los perfiles SQL, raíces, tareas y destinos no permanecerán en el documento de bootstrap.

Los valores de confianza de comandos se instalarán con el paquete y podrán rotarse mediante un conjunto de claves firmado. La verificación TLS permanecerá obligatoria.

### 4.3 Configuración administrada

Después del enrolamiento:

1. el agente aparecerá en `Configuración → Agentes`;
2. el operador iniciará `Configurar`;
3. el agente detectará hostname, cuenta del servicio, drivers, instancias SQL, volúmenes y destinos locales candidatos;
4. el dashboard permitirá seleccionar y probar SQL, raíces y destinos;
5. la configuración deseada se enviará cifrada y versionada;
6. el agente la aplicará atómicamente y reportará la revisión efectiva.

Los secretos se capturarán una vez, se cifrarán para la clave X25519 del agente y se protegerán localmente con DPAPI. Las respuestas del API nunca devolverán contraseñas, llaves privadas ni sobres cifrados.

### 4.4 Migración desde 0.4.2

- La actualización conservará identidad, journal, claves y configuración previa.
- Los perfiles públicos de `sqlInstances` y `backupDestinations` se importarán al almacén administrado.
- Una llave SFTP existente por ruta podrá seguir utilizándose localmente durante la transición.
- El dashboard mostrará `Requiere secreto` cuando una credencial no pueda migrarse con seguridad.
- Los backups SQL continuarán funcionando durante la migración.
- El backend seguirá aceptando agentes 0.4.2, pero ocultará el módulo de archivos hasta que el agente reporte la capacidad `file_backup_v1`.

### 4.5 Identidad estable y cambios de infraestructura

El agente se identificará mediante su identidad criptográfica e `installation_id`, nunca mediante IP, hostname o URL de Railway. Un cambio de IP, nombre del host o interfaz de red en la misma instalación sólo actualizará metadatos del heartbeat; no creará otro servidor ni perderá tareas.

El instalador usará un dominio estable administrado por Data Express. Si el proveedor de backend cambia, el dominio conservará el mismo nombre y apuntará al nuevo servicio. Una migración excepcional de dominio o confianza se entregará como actualización firmada; no exigirá editar `agent.json`.

### 4.6 Reemplazo administrado de un servidor

Cuando cambie la máquina física, un administrador con capacidad de configuración utilizará `Reemplazar servidor`:

1. el backend creará una sesión de reemplazo y mostrará un código de un solo uso con diez minutos de vigencia;
2. el instalador universal se ejecutará en el servidor nuevo e introducirá ese código;
3. el agente nuevo se registrará como candidato y reportará hostname, versión, volúmenes, SQL detectado y huella de instalación;
4. el servidor anterior seguirá activo mientras el candidato completa heartbeat y preflight;
5. el dashboard comparará anterior y candidato, e indicará perfiles que requieren volver a capturar un secreto;
6. un administrador confirmará explícitamente el cambio;
7. una transacción reasignará configuración pública, tareas activas y programaciones al candidato, conservará la línea histórica y revocará al agente anterior;
8. el agente anterior dejará de recibir comandos aunque vuelva a conectarse.

Las ejecuciones en curso no se moverán entre máquinas. El administrador deberá terminarlas o cancelarlas antes de confirmar. Los historiales y artefactos anteriores conservarán la identidad física que los produjo, pero se mostrarán dentro de la misma línea lógica del servidor.

Los secretos cifrados para la clave del agente anterior no se copiarán al nuevo. Los perfiles afectados quedarán como `Requiere secreto` y no podrán ejecutar tareas hasta que un administrador capture y pruebe la credencial nuevamente. Rutas, horarios, filtros y demás configuración no sensible sí se transferirán.

Se descartan dos alternativas: crear siempre un agente independiente porque fragmenta historial y operación, y revocar automáticamente al servidor anterior al consumir el código porque un candidato defectuoso podría detener backups. Se adopta el reemplazo confirmado en dos fases.

## 5. Modelo de tarea

Cada tarea contendrá:

- nombre y estado activo/inactivo;
- agente;
- una o varias raíces de origen;
- inclusión de subcarpetas;
- filtros de inclusión y exclusión;
- perfil de destino;
- formato directo o ZIP64;
- estrategia Full, incremental o diferencial;
- calendario, hora y zona horaria;
- política para ejecuciones perdidas;
- cantidad de cadenas Full a conservar;
- política VSS;
- modo de verificación;
- límites operativos heredados del tenant.

La primera ejecución de cualquier tarea será Full aunque se haya configurado como incremental o diferencial.

## 6. Asistente de creación

El frontend usará cuatro pasos con lenguaje operativo.

### Paso 1: Qué proteger

- Seleccionar agente conectado.
- Explorar o escribir una o varias carpetas autorizadas.
- Incluir subcarpetas por defecto.
- Mostrar exclusiones recomendadas de temporales, caché y papelera.
- Mantener los filtros avanzados colapsados.

### Paso 2: Dónde guardarlo

- Elegir perfil local, UNC/SMB o SFTP.
- Probar conexión, creación, lectura, hash, renombrado y eliminación de un archivo reservado.
- Consultar capacidad cuando el destino lo permita.

### Paso 3: Cuándo y cómo

- Elegir Full, incremental o diferencial.
- Seleccionar días, hora y zona horaria.
- Configurar retención con valor inicial de cuatro cadenas Full.
- Permitir ejecutar una tarea perdida al reconectarse el agente.

### Paso 4: Revisar y activar

- Ejecutar simulación sin copiar datos.
- Mostrar archivos, bytes estimados, exclusiones y advertencias.
- Confirmar acceso y espacio del destino.
- Mostrar resumen en lenguaje sencillo.
- Activar únicamente si simulación y prueba del destino son válidas.

## 7. Detección de cambios

El agente no dependerá del atributo `Archive` de Windows.

El catálogo local conservará por tarea y ruta relativa:

- identidad estable cuando el sistema de archivos la permita;
- tamaño;
- fecha de modificación con precisión disponible;
- atributos relevantes;
- hash SHA-256;
- ejecución Full base;
- última ejecución confirmada;
- estado presente, eliminado o excluido.

Durante el escaneo, tamaño y fecha determinarán candidatos a cambio. El agente calculará SHA-256 para archivos nuevos, modificados o ambiguos. Un hash diferente confirmará el cambio.

### Full

Copia todo archivo incluido y establece una nueva base de cadena.

### Incremental

Copia archivos cambiados desde la última ejecución exitosa de la cadena.

### Diferencial

Copia archivos cambiados desde el último Full exitoso.

Los archivos eliminados se registrarán en el manifiesto, pero no se eliminarán automáticamente del destino en la primera versión.

## 8. Flujo de ejecución

```text
En cola
→ Revisando espacio
→ Explorando archivos
→ Preparando archivos bloqueados
→ Copiando
→ Verificando
→ Publicando
→ Aplicando retención
→ Protegido
```

1. Validar firma, tenant, agente, capacidad, revisión e idempotency key.
2. Resolver únicamente fuentes y destino autorizados.
3. Calcular espacio estimado y reserva crítica.
4. Explorar fuentes sin seguir reparse points.
5. Crear snapshot VSS cuando existan archivos bloqueados o la política lo exija.
6. Comparar con el catálogo y construir el plan de copia.
7. Copiar a un área temporal dentro del destino o volumen de trabajo.
8. Calcular hash mientras se lee el origen.
9. Leer el archivo escrito y comparar SHA-256.
10. Guardar checkpoint durable después de cada archivo confirmado.
11. Publicar cada archivo mediante renombrado atómico cuando el destino lo permita.
12. Escribir manifiesto y resumen.
13. Marcar la ejecución como protegida.
14. Aplicar retención sobre cadenas completas.
15. Reportar al backend; si no hay conexión, conservar el evento en el journal.

Una interrupción recuperable producirá `Pendiente de continuar`. Al reiniciar, el agente comprobará los checkpoints y continuará desde el siguiente archivo no confirmado.

## 9. Estructura y manifiestos

### 9.1 Formato directo predeterminado

```text
Destino\
└─ Tarea\
   └─ 2026-08-20_0100_FULL\
      ├─ Fuente-1\...
      ├─ Fuente-2\...
      └─ manifest.json
```

Las ejecuciones incrementales y diferenciales usarán `INCREMENTAL` y `DIFERENCIAL`. El identificador interno no aparecerá en el nombre visible, pero sí en el manifiesto.

### 9.2 ZIP64 opcional

ZIP64 se permitirá sólo cuando la simulación se encuentre dentro de los límites configurados. No será el formato recomendado para volúmenes cercanos a 1 TB ni para tareas con millones de archivos.

### 9.3 Manifiesto

Contendrá:

- versión del formato;
- tarea, ejecución, agente y tenant;
- tipo de backup y relación con la cadena;
- fuentes y destino sin secretos;
- inicio, fin y configuración aplicada;
- archivos copiados, omitidos, eliminados y fallidos;
- tamaños, atributos, fechas y hashes;
- método de verificación;
- resultado de VSS;
- totales y advertencias.

## 10. Retención

- Valor inicial: cuatro cadenas Full.
- Una cadena se elimina como unidad: Full y todos sus hijos.
- Una copia marcada `Protegida` no se elimina automática ni manualmente hasta retirar esa marca.
- La única cadena Full válida nunca se elimina.
- La retención no se ejecuta después de una copia incompleta o no validada.
- La simulación de retención mostrará cadenas, archivos y bytes que se liberarían.
- La eliminación usará límites por archivos y bytes, journal durable y auditoría.

## 11. Restauración

Se admitirán dos destinos:

- ruta original;
- ubicación alternativa autorizada.

Flujo:

```text
Seleccionar tarea y fecha
→ Reconstruir cadena
→ Elegir archivos/carpetas
→ Simular
→ Revisar conflictos
→ Confirmar
→ Restaurar
→ Verificar
```

La simulación clasificará archivos nuevos, reemplazados, idénticos, ausentes y bloqueados. El sistema nunca sobrescribirá silenciosamente.

La restauración reconstruirá el estado solicitado aplicando Full y sus hijos en orden. Cada archivo restaurado se verificará contra el hash del manifiesto. La auditoría conservará actor, agente, selección, destino, conflictos, resultado y hashes.

## 12. Persistencia

### 12.1 PostgreSQL

Tablas nuevas:

- `file_backup_tasks`;
- `file_backup_sources`;
- `file_backup_filters`;
- `file_backup_runs`;
- `file_backup_chains`;
- `file_backup_artifacts`;
- `file_restore_jobs`;
- `file_restore_confirmations`.

PostgreSQL no almacenará una fila por archivo. Guardará configuración, estados, totales, relación de cadenas, ubicación del manifiesto y resumen auditable.

### 12.2 SQLite local del agente

Archivo: `C:\ProgramData\DataExpress\Agent\file-backup.db`.

Responsabilidades:

- catálogo de archivos por tarea;
- checkpoints por ejecución;
- manifiestos y eventos pendientes;
- relaciones de cadenas;
- bloqueos de recursos;
- estado de reanudación.

Las actualizaciones usarán transacciones. El agente conservará una copia recuperable antes de cualquier migración del esquema local.

## 13. API

Recursos administrativos:

```text
GET    /api/v1/file-backup/tasks
POST   /api/v1/file-backup/tasks
GET    /api/v1/file-backup/tasks/{taskId}
PATCH  /api/v1/file-backup/tasks/{taskId}
DELETE /api/v1/file-backup/tasks/{taskId}

POST   /api/v1/file-backup/tasks/{taskId}/simulations
GET    /api/v1/file-backup/simulations/{simulationId}

GET    /api/v1/file-backup/tasks/{taskId}/runs
POST   /api/v1/file-backup/tasks/{taskId}/runs
GET    /api/v1/file-backup/runs/{runId}
POST   /api/v1/file-backup/runs/{runId}/cancellations

POST   /api/v1/file-backup/restores
GET    /api/v1/file-backup/restores/{restoreId}
POST   /api/v1/file-backup/restores/{restoreId}/confirmations

GET    /api/v1/file-backup/chains/{chainId}
PATCH  /api/v1/file-backup/artifacts/{artifactId}
```

`PATCH /artifacts/{artifactId}` sólo permitirá modificar la marca `protected` con control de capacidad y auditoría.

Las colecciones estarán paginadas y filtradas por tenant. Los errores usarán el formato estándar del proyecto con código estable, mensaje sanitizado y detalles operativos no sensibles.

Ciclo de vida del agente:

```text
POST   /api/v1/agents/{agentId}/replacements
GET    /api/v1/agents/{agentId}/replacements/{replacementId}
POST   /api/v1/agents/{agentId}/replacements/{replacementId}/confirmations
POST   /api/v1/agents/{agentId}/replacements/{replacementId}/cancellations
```

Crear la sesión devuelve el código temporal una sola vez. Confirmar exige que el candidato esté saludable, no existan ejecuciones activas y la revisión observada coincida con la sesión. Confirmación y cancelación aceptarán clave de idempotencia. Respuestas `409` distinguirán candidato no saludable, ejecución activa, revisión obsoleta y sesión terminal.

El endpoint existente `POST /api/v1/agents/{agentId}/replace` permanecerá temporalmente como alias compatible para crear la sesión; dejará de revocar al agente anterior durante el enrolamiento y devolverá aviso de deprecación.

Comandos agente:

- `simulate_file_backup`;
- `run_file_backup`;
- `resume_file_backup`;
- `cancel_file_backup`;
- `simulate_file_restore`;
- `run_file_restore`;
- `test_file_destination`;
- `apply_file_backup_config`.

## 14. Estados y errores

Estados de ejecución:

- `queued`;
- `preflight`;
- `scanning`;
- `snapshotting`;
- `copying`;
- `verifying`;
- `publishing`;
- `retaining`;
- `completed`;
- `completed_with_warnings`;
- `retryable`;
- `failed`;
- `cancelled`.

Errores relevantes:

- fuente no disponible;
- ruta fuera de alcance;
- reparse point rechazado;
- espacio insuficiente;
- VSS no disponible;
- archivo cambiado durante copia;
- permisos insuficientes;
- destino desconectado;
- huella SFTP diferente;
- verificación de hash fallida;
- cadena incompleta;
- manifiesto inválido;
- checkpoint incompatible;
- secreto requerido;
- versión de agente no compatible.

Los errores recuperables conservarán checkpoints y ofrecerán `Continuar`. Los errores de integridad, confianza o alcance serán terminales hasta corregir configuración.

## 15. Interfaz aprobada

La dirección visual será intuitiva y operacional, no un dashboard de tarjetas.

Principios:

- lenguaje `qué se respalda`, `dónde se guarda`, `próxima copia` y `estado`;
- lista familiar de tareas como vista principal;
- una alerta prioritaria en lugar de métricas decorativas;
- detalle desplegable sólo al seleccionar una tarea;
- acciones visibles `Restaurar`, `Ver detalles` y menú secundario;
- asistente lateral de cuatro pasos;
- información técnica bajo `Detalles avanzados`;
- profundidad por bordes suaves y cambios mínimos de superficie;
- radio pequeño y tipografía Segoe UI/Inter;
- monospace únicamente para rutas, hashes y datos técnicos;
- azul para control activo; verde, ámbar y rojo sólo para estados.

Navegación:

```text
Respaldo de archivos
├─ Activos
├─ Historial
├─ Restaurar archivos
└─ Destinos
```

Firma visual: una secuencia compacta `Copiado → Verificado → Entregado` para la última ejecución. La cadena técnica Full/incrementales estará disponible en el detalle avanzado.

## 16. Seguridad

- Todas las órdenes estarán firmadas y ligadas a tenant, agente, revisión e idempotency key.
- El agente volverá a validar rutas, filtros y límites.
- No se seguirán enlaces ni reparse points en la primera versión.
- No se aceptarán rutas relativas ni segmentos de escape.
- Las rutas de restauración requerirán allowlist explícita.
- TLS no se podrá desactivar.
- La huella SFTP se aprobará explícitamente.
- Los secretos sólo se descifrarán en el agente destinatario.
- Los logs, manifiestos y respuestas omitirán secretos y cadenas de conexión.
- Las pruebas de destino usarán nombres reservados y limpiarán sus archivos.
- Retención, cancelación y restauración requerirán capacidades separadas.
- Toda sobrescritura y eliminación quedará auditada.

## 17. Rendimiento y límites

- Un escaneo no cargará el árbol completo en memoria.
- El catálogo y los manifiestos se procesarán por páginas/lotes.
- Los buffers de copia serán configurables dentro de límites seguros.
- Los hashes se transmitirán en streaming.
- El agente aplicará backpressure por disco y red.
- El número de archivos concurrentes será reducido y configurable.
- Se evitará comprimir formatos ya comprimidos.
- ZIP64 tendrá límites previos a la ejecución.
- El backend recibirá progreso agregado, no un evento por archivo.
- Los manifiestos grandes permanecerán en el agente/destino; Railway conservará resumen y referencia.

## 18. Pruebas de aceptación

### Instalación y conexión

1. Instalar introduciendo sólo un código temporal.
2. Confirmar que el código no queda en historial ni configuración.
3. Detectar entorno y crear perfiles desde el dashboard.
4. Editar un perfil offline y aplicarlo al reconectar.
5. Confirmar que secretos no aparecen en API, logs o manifiestos.
6. Actualizar 0.4.2 a 0.5.0 conservando backups SQL.
7. Cambiar IP y hostname en la misma instalación sin perder identidad ni tareas.
8. Crear reemplazo y comprobar que el agente anterior sigue operativo mientras el nuevo es candidato.
9. Rechazar confirmación si el candidato no está saludable o existen ejecuciones activas.
10. Confirmar reemplazo y transferir perfiles públicos, tareas y programaciones en una transacción.
11. Conservar historial anterior con marca de máquina de origen.
12. Revocar al agente anterior y rechazar sus comandos posteriores.
13. Marcar secretos no transferibles como `Requiere secreto`.
14. Cancelar o dejar expirar la sesión sin modificar al agente anterior.

### Backup

1. Crear Full válido.
2. Crear incremental con sólo cambios posteriores.
3. Crear diferencial con cambios desde el Full.
4. Procesar miles de archivos pequeños y archivos grandes.
5. Manejar rutas largas, espacios y caracteres válidos de Windows.
6. Copiar archivos abiertos mediante VSS.
7. Detener si VSS requerido falla.
8. Reiniciar el servicio durante escaneo, copia y verificación.
9. Continuar desde checkpoint sin duplicar archivos confirmados.
10. Recuperarse de caída de internet o destino temporalmente inaccesible.
11. Rechazar destino lleno antes de copiar.
12. Detectar archivo modificado mientras se copia.
13. Preservar fechas y atributos.
14. Preservar permisos NTFS en local/UNC cuando esté habilitado.
15. Validar todos los hashes de una muestra restaurada.

### Retención

1. Eliminar una cadena completa y nunca hijos aislados.
2. Conservar al menos un Full válido.
3. Conservar elementos protegidos.
4. No ejecutar retención después de una copia inválida.
5. Simular bytes y archivos antes de eliminar.

### Restauración

1. Restaurar al origen.
2. Restaurar en ubicación alternativa.
3. Reconstruir correctamente Full más hijos.
4. Mostrar nuevos, reemplazados, idénticos y conflictos.
5. Exigir confirmación después de simular.
6. Verificar hashes del resultado.
7. Auditar actor, selección, sobrescrituras y resultado.

## 19. Despliegue

1. Añadir migraciones y contratos compatibles con 0.4.2.
2. Desplegar backend con capacidad desactivada por versión.
3. Publicar frontend con módulo oculto cuando el agente no soporte `file_backup_v1`.
4. Empaquetar agente 0.5.0 e instalador universal.
5. Actualizar un servidor piloto.
6. Ejecutar Full local y UNC.
7. Interrumpir y reanudar una copia.
8. Restaurar una muestra y comparar hashes.
9. Validar retención.
10. Probar SFTP.
11. Ejecutar un reemplazo controlado del agente piloto.
12. Confirmar continuidad de tareas, perfiles públicos e historial.
13. Observar una semana de ejecuciones.
14. Habilitar el módulo para los demás agentes.

## 20. Decisiones finales

- Se ampliará el agente actual; no habrá segundo servicio.
- El módulo será de archivos y carpetas, no imagen de sistema.
- Destinos iniciales: local, UNC/SMB y SFTP.
- Tipos: Full, incremental y diferencial con catálogo propio.
- Formato predeterminado: estructura directa; ZIP64 será opcional.
- Restauración: origen y ubicación alternativa con simulación obligatoria.
- Retención: cuatro cadenas por defecto y protección explícita.
- No habrá espejo destructivo ni eventos de comandos en la primera versión.
- El instalador pedirá únicamente un código temporal.
- El paquete usará un dominio estable de control y no dependerá de una URL temporal de Railway.
- `agent.json` dejará de ser configuración operativa editable.
- IP y hostname serán metadatos; la identidad real será criptográfica.
- Reemplazar una máquina será un proceso confirmado en dos fases.
- La configuración no sensible y la historia continuarán; los secretos ligados al agente deberán capturarse nuevamente.
- La interfaz aprobada será una lista intuitiva con asistente lateral de cuatro pasos.
- El agente 0.5.0 será requisito para `file_backup_v1`.
