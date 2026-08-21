# Respaldo directo de bases de datos grandes

Fecha: 2026-08-21  
Estado: aprobado para planificación

## Objetivo

Permitir respaldar bases de datos cercanas a 1 TB sin necesitar espacio local para
mantener simultáneamente un `.bak` y un `.zip`. SQL Server escribirá un respaldo
nativo comprimido directamente en el volumen de destino, el agente lo validará y
la plataforma conservará su trazabilidad.

## Decisión

Los respaldos grandes usarán un nuevo modo de entrega directa. Este modo no crea
ZIP y no utiliza la carpeta temporal local del agente. SQL Server escribe el `.bak`
o `.trn` en una ruta de red SMB/UNC accesible por el servicio de SQL Server.

El flujo ZIP actual permanece disponible para destinos SFTP y respaldos que sí
cuenten con almacenamiento temporal suficiente. No se intentará leer y comprimir
un `.bak` mientras SQL Server todavía lo escribe: ese flujo impediría validar con
seguridad un artefacto terminado y obligaría a repetir el respaldo completo ante
una interrupción.

## Estructura del destino

```text
\\servidor-respaldos\RespaldosTI\2026-08-21\
├── BaseVentas_2026-08-21.bak
├── BaseVentas_2026-08-21_DIF.bak
└── BaseVentas_2026-08-21_LOG.trn
```

El nombre original de la base se conserva después de sanear únicamente caracteres
no válidos de Windows. `FULL` no aparece en el nombre. La fecha identifica el día
del respaldo; `_DIF` y `_LOG` distinguen los otros tipos.

No se sobrescribirá silenciosamente un respaldo ya validado. Si el nombre final ya
existe, la ejecución se detendrá con un error de conflicto y la interfaz permitirá
elegir otra fecha/ejecución o retirar el archivo anterior de forma explícita.

## Perfiles de destino

Se añadirá un destino `smb_direct` con estos datos públicos:

- nombre visible;
- ruta UNC, nunca una unidad mapeada;
- umbrales de espacio disponible;
- indicación de que admite respaldos grandes directos.

Las credenciales no viajarán dentro de las órdenes ni se guardarán como texto
plano en la plataforma. La opción preferida es conceder acceso a la cuenta del
servicio de SQL Server mediante dominio o gMSA. Si se requiere otra identidad, se
configurará en Windows y el asistente solamente verificará el acceso.

El asistente probará por separado que el agente puede consultar el destino y que
SQL Server puede crear y eliminar un archivo de prueba. La segunda comprobación es
indispensable porque el proceso que ejecuta `BACKUP DATABASE` es SQL Server, no el
agente.

## Flujo de ejecución

1. El agente consulta tamaño asignado, edición y capacidades de SQL Server.
2. Comprueba espacio libre en el volumen de destino y conserva una reserva crítica.
3. Crea una carpeta diaria si no existe.
4. SQL Server escribe a un nombre temporal dentro del destino usando `CHECKSUM`,
   `STATS` y compresión nativa cuando la instancia la admite.
5. El agente espera el cierre del archivo y ejecuta `RESTORE VERIFYONLY WITH CHECKSUM`.
6. Calcula tamaño y SHA-256, y renombra el archivo temporal al nombre definitivo en
   el mismo volumen.
7. Reporta `backup_ready` al backend. No hay fase ZIP ni limpieza local.
8. Backend registra origen, instancia, base, tipo, ruta, tamaño, hash, método de
   verificación, duración y espacio restante.

Si la instancia no admite compresión nativa, el preflight usará el tamaño sin
comprimir y mostrará el requisito real antes de empezar. En modo de base grande se
debe fallar antes de ejecutar si el destino no tiene espacio suficiente; no se
debe cambiar automáticamente al flujo ZIP.

## Progreso y estados

La barra principal mantiene como éxito funcional la creación y validación del
respaldo. Para este modo mostrará:

```text
Comprobando destino → Creando respaldo → Validando → Registrando → Listo
```

La columna `ZIP / envío` cambiará a `Entrega` y mostrará `Directo` para estas
ejecuciones. El resultado seguirá diferenciando `Backup listo` de cualquier tarea
secundaria.

## Errores y recuperación

- Espacio insuficiente: no iniciar el respaldo y generar alerta crítica.
- SQL Server sin acceso al UNC: fallar el preflight con la cuenta y ruta que deben
  recibir permisos, sin mostrar secretos.
- Corte durante el respaldo: conservar el archivo temporal como incompleto y
  marcarlo para limpieza segura; nunca presentarlo como respaldo válido.
- Error de validación: conservar el temporal para diagnóstico, registrar el error y
  no publicarlo con el nombre definitivo.
- Pérdida de conexión con la plataforma: terminar y validar localmente; persistir el
  resultado en la cola del agente y reportarlo al recuperar conexión.
- Conflicto de nombre: no usar `WITH INIT` contra un archivo definitivo existente.

Los temporales incompletos tendrán identidad de ejecución y una política de
retención separada. Solo podrán eliminarse cuando no exista una operación de SQL
Server activa y hayan superado la antigüedad configurada.

## Manifiesto y restauración

En este modo no habrá `manifest.json` dentro de un ZIP. La misma información se
guardará en el resultado firmado del agente y en la base de datos de la plataforma.
No se escribirá un archivo lateral `.json`: el `.bak` validado será el único artefacto
del respaldo en el destino.

La interfaz ofrecerá una verificación posterior y, en una fase separada, una prueba
de restauración hacia una instancia de prueba. `RESTORE VERIFYONLY` detecta daños
estructurales del medio, pero no sustituye una restauración periódica real.

## Compatibilidad

- Los planes existentes conservan el flujo `.bak → ZIP → SFTP`.
- Un plan nuevo elige explícitamente `ZIP/SFTP` o `Directo SMB`.
- Un destino SFTP no puede seleccionarse para modo directo.
- El backend aceptará resultados de agentes 0.4.2 durante la actualización
  escalonada; solo un agente con la nueva capacidad recibirá órdenes directas.
- La capacidad se negociará mediante metadata del agente, no solamente comparando
  el texto de la versión.

## Pruebas de aceptación

- Preflight unitario para espacio suficiente, reserva crítica y falta de acceso.
- Pruebas de generación SQL para full, diferencial y log sin sobrescritura.
- Pruebas de estados y reanudación del reporte después de perder conexión.
- Integración en Windows con una ruta UNC y cuentas distintas para agente y SQL.
- Prueba con datos representativos para medir compresión, duración y consumo real.
- Piloto de gran tamaño antes de habilitarlo globalmente.
- Restauración real del piloto y comparación de consistencia de la base.

## Fuera de alcance

- Streaming de SQL Server directamente a ZIP o SFTP mediante VDI.
- Almacenar contraseñas SMB en órdenes o archivos de configuración sin protección.
- Eliminar automáticamente respaldos definitivos para liberar espacio.
- Considerar `RESTORE VERIFYONLY` como reemplazo de una restauración de prueba.
