# Diseño unificado de agentes, backups, automatización y limpieza

**Fecha:** 2026-08-20

**Estado:** Aprobado para planificación

**Alcance:** frontend, contratos backend y agente Windows

## 1. Objetivo

Unificar Backups y Limpieza alrededor del agente Windows, retirar de la interfaz los flujos heredados de conexión directa y SFTP/FTP para operar servidores, y separar el éxito del respaldo SQL del trabajo posterior de compresión y entrega.

El diseño debe permitir que un operador identifique con claridad:

- qué agente ejecutará una operación;
- si el archivo `.bak` fue creado y validado realmente;
- si su compresión y entrega siguen en curso o fallaron;
- qué días corresponden a Full y Diferencial;
- qué archivos eliminará una limpieza antes de autorizarla.

## 2. Principios

1. El agente es el único medio visible para operar SQL Server y el disco local del servidor.
2. Un respaldo se considera listo cuando el `.bak` fue creado y validado, no cuando terminó su entrega.
3. La entrega es un proceso posterior independiente y reintentable.
4. La limpieza es manual, estructural, simulada primero y limitada a una raíz validada.
5. La interfaz usa lenguaje y estados operativos explícitos; no mezcla servidor, conexión y agente.
6. Ningún fallback de existencia, tamaño o hash sustituye una validación SQL correcta del `.bak`.

## 3. Arquitectura visible basada en agentes

### 3.1 Retiro del modelo heredado

La interfaz normal dejará de mostrar:

- Conexión directa en Nuevo Backup.
- Alta de servidores SFTP, FTPS o FTP para Limpieza.
- Host, puerto, usuario, contraseña y llave `.pem` en Limpieza.
- Claves SSH conocidas asociadas al flujo de Limpieza.

La conexión directa podrá conservarse temporalmente detrás de una bandera técnica no visible para usuarios. No formará parte del flujo de producción.

### 3.2 Configuración → Agentes

La pestaña `Servidores` se sustituirá por `Agentes`. Cada agente mostrará:

- nombre del equipo;
- estado conectado o desconectado;
- última comunicación;
- versión instalada;
- actualización pendiente, cuando corresponda;
- raíz fija de limpieza;
- cantidad de propiedades detectadas;
- perfiles SQL y destinos disponibles para backup, cuando apliquen.

Si existe un solo agente conectado, las pantallas operativas lo seleccionarán automáticamente. Si existen varios, el usuario elegirá uno en un desplegable. Si no existe ninguno disponible, se mostrará `Sin agentes conectados` y se bloquearán las acciones que requieren ejecución remota.

### 3.3 Vinculación y configuración obligatoria

El alta seguirá este flujo:

1. Un administrador genera un código de vinculación.
2. El código se introduce una sola vez durante la instalación del agente.
3. El agente aparece en el inventario con su identidad y estado.
4. Un asistente obligatorio permite explorar el disco y seleccionar una raíz de limpieza.
5. El agente valida la raíz y detecta la estructura esperada.
6. Solo una validación satisfactoria permite guardar la configuración.

Cada agente tendrá exactamente una raíz fija de limpieza.

## 4. Limpieza manual estructural

### 4.1 Alcance permitido

Dentro de la raíz, cada propiedad será una carpeta hija directa con esta forma:

```text
RAÍZ\
├─ Propiedad-A\
│  └─ core\
│     ├─ Log\
│     ├─ LogSec\
│     ├─ LogsRadian\
│     ├─ Respuesta\
│     └─ BD_log.txt
└─ Propiedad-B\
   └─ core\
      └─ ...
```

El agente solo podrá actuar sobre:

- `Propiedad\core\Log`;
- `Propiedad\core\LogSec`;
- `Propiedad\core\LogsRadian`;
- `Propiedad\core\Respuesta`;
- `Propiedad\core\BD_log.txt`.

Se eliminarán todos los archivos encontrados dentro de las cuatro carpetas objetivo, incluidos los contenidos en sus subcarpetas. `BD_log.txt` se eliminará cuando exista. Las carpetas y subcarpetas se conservarán.

El agente no seguirá enlaces simbólicos ni puntos de repetición, no aceptará rutas fuera de la raíz validada y no permitirá objetivos arbitrarios escritos por el usuario.

### 4.2 Flujo de operación

La pantalla mostrará una línea de cuatro fases:

```text
Simular → Revisar → Confirmar → Resultado
```

El proceso será:

1. El usuario abre Limpieza y selecciona un agente, salvo que exista uno solo.
2. La pantalla muestra la raíz fija, las propiedades detectadas y los objetivos protegidos.
3. `Simular limpieza` ordena al agente recorrer únicamente la estructura permitida.
4. El agente genera un manifiesto con ruta, tamaño y fecha de modificación de cada archivo.
5. El backend conserva la simulación y presenta archivos elegibles, espacio a liberar y advertencias.
6. El usuario puede revisar el listado completo y confirmar la eliminación.
7. La ejecución referencia la simulación aprobada; no reconstruye libremente el alcance.
8. El agente vuelve a validar raíz, identidad, tamaño y fecha de modificación.
9. Si el conjunto cambió, la ejecución se rechaza y se exige una nueva simulación.
10. El agente elimina archivos elegibles, conserva las carpetas y reporta el resultado.
11. El historial registra usuario, agente, raíz, simulación, archivos, bytes, fallos y duración.

Una simulación será válida durante 30 minutos. También quedará invalidada inmediatamente si cambia el agente, la raíz, la revisión de configuración o cualquiera de los archivos del manifiesto.

### 4.3 Decisiones explícitas

- La ejecución será únicamente manual en esta entrega.
- No habrá programación nocturna.
- No habrá cuarentena ni restauración en el nuevo frontend.
- La eliminación será definitiva después de simulación y confirmación.
- Si algunos archivos están bloqueados, el resultado será `Completada con advertencias`; se detallarán los fallos y no se considerará un fallo total si otros archivos se eliminaron correctamente.

## 5. Backups: respaldo y entrega separados

### 5.1 Estado principal

La barra principal representará exclusivamente:

```text
Creando .bak → Validando .bak → Respaldo listo
```

El respaldo llegará a 100 % únicamente cuando:

1. SQL Server termine de crear el `.bak`;
2. el archivo exista en el destino esperado;
3. `RESTORE VERIFYONLY` termine correctamente para ese archivo.

Si la cuenta no tiene permiso para validar, el sistema no reemplazará la validación con tamaño, existencia o SHA. Se mostrará `Validación no ejecutada` o `Validación fallida`, y el respaldo no se contabilizará como listo.

### 5.2 Estado posterior de entrega

Después de `Respaldo listo`, el agente continuará en segundo plano:

```text
Comprimiendo ZIP → Enviando → Entregado
```

Los estados del respaldo y de la entrega serán independientes. Ejemplos:

- `Respaldo listo · Entrega en curso`;
- `Respaldo listo · Entregado`;
- `Respaldo listo · Entrega fallida`;
- `Respaldo fallido`.

Un fallo de compresión o transferencia no cambiará un `.bak` validado a fallido. La entrega podrá reintentarse sin repetir el backup SQL. La interfaz mostrará por separado `Estado del respaldo` y `Estado de entrega`.

`Entregado` exigirá verificar el artefacto almacenado en destino mediante tamaño y SHA-256. En transferencias SFTP, la comprobación deberá leer el archivo remoto o utilizar un mecanismo equivalente que pruebe su contenido; comparar únicamente el tamaño no será suficiente.

El contador `Completados` incluirá respaldos `.bak` validados, independientemente de que la entrega siga en curso. Los indicadores de entrega se calcularán aparte.

### 5.3 Progreso y limpieza de temporales

El porcentaje principal no incluirá ZIP, transferencia ni eliminación de temporales. Esos pasos tendrán progreso propio. La limpieza de archivos temporales se ejecutará después de que el artefacto de entrega quede confirmado o después de aplicar la política definida para destinos locales.

Si el proceso se interrumpe, el estado durable permitirá distinguir si debe reintentarse la entrega o repetirse el respaldo.

## 6. Automatización semanal

### 6.1 Selector

`Programar` abrirá un selector semanal con estas siglas:

```text
Full          L  Ma  Mi  J  V  S  D
Diferencial   L  Ma  Mi  J  V  S  D
```

No se utilizará un calendario mensual porque el plan es recurrente por semana.

### 6.2 Reglas

- Full tendrá al menos un día.
- Diferencial será opcional; un plan Full-only será válido.
- Un día pertenecerá como máximo a un tipo.
- Al elegir Full para un día, se quitará Diferencial para ese mismo día, y viceversa.
- Si llega un día Diferencial sin un Full válido previo, el agente ejecutará Full y registrará `Full inicial requerido`.
- No se permitirán dos backups simultáneos para la misma base de datos.

El resumen será:

- `Full L/Mi/V · Diferencial Ma/J`, cuando existan ambos tipos;
- `Full L/Mi/V`, cuando no existan diferenciales.

## 7. Tipografía y jerarquía visual

Los valores numéricos de tarjetas, métricas y tablas usarán la misma familia sans-serif que el texto principal. Se eliminará la tipografía serif cursiva usada actualmente en algunos indicadores.

Para conservar alineación y legibilidad, los datos numéricos usarán cifras tabulares mediante propiedades tipográficas, sin cambiar de familia. La tipografía monoespaciada se reservará para rutas, versiones, identificadores y telemetría técnica.

La interfaz conservará el lenguaje visual oscuro y operativo:

- azul oscuro para lienzo y superficies;
- cian para acciones y telemetría;
- verde para conectado y éxito;
- ámbar para advertencias;
- rojo exclusivamente para errores y eliminación definitiva;
- bordes sutiles como estrategia de profundidad.

La firma visual será una línea de fases operativas reutilizada en Limpieza, Backup y Entrega.

## 8. Componentes propuestos

### Frontend

- `AgentSelector`: selección automática, lista múltiple y estado vacío.
- `AgentsAdmin`: inventario, vinculación, versión, estado y acciones.
- `AgentRootWizard`: exploración, selección y validación obligatoria de raíz.
- `CleanupPhaseRail`: Simular, Revisar, Confirmar y Resultado.
- `CleanupSimulationSummary`: conteos, bytes, advertencias y listado.
- `BackupPrimaryProgress`: creación y validación del `.bak`.
- `BackupDeliveryProgress`: ZIP, transferencia y reintento.
- `WeeklyBackupScheduler`: selección excluyente por tipo y día.

### Backend

- Inventario y selección de agentes por tenant.
- Comandos permitidos para listar bases, ejecutar backups, simular limpieza y ejecutar limpieza directa.
- Persistencia separada de estado del respaldo y estado de entrega.
- Simulaciones durables ligadas a agente, raíz, configuración y manifiesto.
- Ejecuciones idempotentes y auditables.

### Agente

- Validación local de perfiles SQL y raíz de limpieza.
- Ejecución y validación estricta de `.bak`.
- Compresión y transferencia posteriores al respaldo.
- Reintento de entrega sin repetir el backup.
- Simulación estructural y eliminación directa restringida.
- Journal durable para reportar resultados después de una desconexión.

## 9. Estados y manejo de errores

- **Agente desconectado:** se bloquean nuevas operaciones y se muestra la última comunicación.
- **Desconexión durante una operación:** el trabajo local continúa cuando sea seguro; el agente registra y reporta el resultado al reconectarse.
- **Orden duplicada:** la idempotencia evita una segunda ejecución.
- **Versión incompatible:** la acción no se envía y se solicita actualizar el agente.
- **Backup o validación fallidos:** `Respaldo fallido`; no se inicia entrega.
- **Entrega fallida:** se conserva `Respaldo listo` y se ofrece reintento.
- **Simulación vencida o modificada:** se rechaza la limpieza y se solicita simular nuevamente.
- **Raíz inválida o fuera de alcance:** se bloquea guardar o ejecutar.
- **Archivos bloqueados:** resultado parcial con advertencias y detalle.
- **Programación coincidente:** no se ejecutan dos backups para la misma base a la vez.

## 10. Seguridad

- Todas las órdenes del agente serán tipadas y estarán en una lista explícita de comandos permitidos.
- El backend verificará tenant, agente activo, capacidades del usuario e idempotencia.
- La raíz de limpieza deberá haber sido validada por el mismo agente y la misma revisión de configuración.
- Ninguna ruta enviada por el frontend ampliará el alcance guardado.
- La ejecución de limpieza dependerá de una simulación vigente y coincidente.
- El agente rechazará raíces de sistema, enlaces y rutas resueltas fuera del perímetro.
- Los secretos permanecerán en el agente o en el mecanismo seguro definido; no se devolverán al navegador.

## 11. Pruebas de aceptación

### Agentes

1. Un agente se vincula y exige configurar su raíz.
2. Una raíz inválida no puede guardarse.
3. Un agente único se selecciona automáticamente.
4. Con varios agentes se puede elegir uno.
5. Sin agentes conectados se bloquean las acciones.
6. Una versión incompatible bloquea únicamente las funciones no soportadas.

### Limpieza

1. Solo se detectan propiedades hijas directas de la raíz.
2. Solo se incluyen los cinco objetivos estructurales aprobados.
3. Se eliminan archivos y se conservan carpetas y subcarpetas.
4. Se rechazan enlaces y rutas fuera de la raíz.
5. No se puede ejecutar sin simulación.
6. Un cambio de tamaño o fecha invalida la ejecución.
7. Un fallo parcial se reporta con advertencias.
8. El historial contiene alcance, usuario, agente y resultado.

### Backups

1. El progreso principal llega a 100 % solo después de validar el `.bak`.
2. La falta de permiso de validación no produce un falso éxito.
3. ZIP y transferencia tienen progreso independiente.
4. Un fallo de entrega no cambia el respaldo validado a fallido.
5. Reintentar la entrega no crea otro `.bak`.
6. Una desconexión conserva estado durable y evita duplicados.

### Automatización e interfaz

1. Full exige al menos un día.
2. Diferencial puede estar desactivado.
3. Un día no puede pertenecer a ambos tipos.
4. Un Diferencial sin base produce un Full inicial.
5. Las siglas se renderizan como `L`, `Ma`, `Mi`, `J`, `V`, `S`, `D`.
6. Los resúmenes Full-only y Full + Diferencial son correctos.
7. Las métricas usan la misma familia sans-serif y cifras tabulares.

## 12. Migración

1. Incorporar los comandos nuevos a la lista permitida del backend y reconciliar contratos con el agente.
2. Separar los estados durables de respaldo y entrega.
3. Implementar administración y selección de agentes en frontend.
4. Migrar Nuevo Backup al flujo exclusivo por agente.
5. Migrar Limpieza al flujo estructural directo por agente.
6. Retirar de navegación y formularios el modelo SFTP/FTP heredado.
7. Implementar automatización semanal y reglas de Full inicial.
8. Unificar tipografía numérica en dashboards.
9. Probar el flujo completo con un agente real antes de retirar definitivamente los endpoints heredados.

La eliminación física de endpoints, tablas o código heredado queda fuera de la primera migración. Primero se ocultarán y dejarán sin consumidores; su retiro se realizará después de comprobar que no existen dependencias activas.

## 13. Prerrequisitos de salida a producción

Antes de habilitar los flujos nuevos se deberá:

- reconciliar el código del agente, backend y frontend en una misma revisión versionada;
- incorporar `list_sql_databases`, `run_backup_batch` y `execute_structural_direct` a los comandos permitidos del backend;
- comprobar que las rutas API crean, siguen y finalizan esas órdenes de extremo a extremo;
- corregir el actualizador para esperar la terminación real del proceso del agente antes de reemplazar binarios bloqueados;
- probar `RESTORE VERIFYONLY` con la identidad real del servicio de Windows;
- probar el hash remoto y el reintento de entrega con una transferencia interrumpida;
- ejecutar primero la limpieza sobre un conjunto controlado de propiedades y comparar simulación, manifiesto e historial.

## 14. Fuera de alcance

- Limpieza programada o nocturna.
- Cuarentena y restauración en el nuevo flujo.
- Múltiples raíces de limpieza por agente.
- Objetivos de limpieza arbitrarios definidos por el usuario.
- Calendario mensual de backups.
- Conexión directa visible para usuarios.
- Eliminación inmediata del código heredado antes de validar la migración.
