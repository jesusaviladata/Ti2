# Agente Windows para exploración y limpieza remota estructural

**Fecha:** 2026-08-10  
**Estado:** Diseño aprobado por el usuario  
**Objetivo:** Sustituir la configuración manual basada en SFTP y allowlists por una experiencia semejante a Remote Desktop Connection: vincular una vez cada Windows Server, explorar visualmente sus discos, elegir la raíz de propiedades y ejecutar barridos estructurales seguros desde Railway.

## 1. Contexto y problema

La pantalla actual registra host, puerto, usuario, protocolo, ruta base y una allowlist escrita manualmente. Ese modelo no representa el flujo operativo requerido.

La estructura real contiene aproximadamente 1500 propiedades bajo una única carpeta raíz de un disco de Windows:

```text
D:\Ipsofactu\
├── Propiedad001\
│   ├── Core\
│   └── Web\
├── Propiedad002\
│   ├── Core\
│   └── Web\
└── ...
```

El administrador debe conectarse al servidor, explorar discos y carpetas, seleccionar visualmente la raíz y validar la estructura. En cada propiedad la operación se limita a `Core`; `Web` nunca es objetivo.

RDP no ofrece una API de archivos adecuada para que un backend en Railway recorra y modifique carpetas. El producto conservará una experiencia parecida a Remote Desktop, pero la ejecución se realizará mediante un agente de Windows vinculado al backend.

## 2. Decisiones aprobadas

1. Cada Windows Server ejecutará **Data Express Agent** como servicio de Windows.
2. El agente se instalará y vinculará una sola vez por servidor.
3. El agente abrirá únicamente una conexión HTTPS/WSS saliente hacia Railway; no expondrá RDP, SMB, SFTP ni una API propia a Internet.
4. El administrador podrá explorar discos y carpetas desde la aplicación web.
5. La carpeta raíz se seleccionará visualmente y no se dependerá de escribir rutas manualmente.
6. Cada carpeta hija directa de la raíz será tratada como una propiedad.
7. En cada propiedad se inspeccionará únicamente la carpeta `Core`, sin distinguir mayúsculas de minúsculas.
8. La carpeta `Web` se ignorará y quedará protegida explícitamente.
9. Las carpetas y archivos objetivo serán configurables por servidor.
10. Antes de guardar la configuración se deberá validar la conexión y la estructura.
11. Antes de ejecutar una limpieza siempre se realizará una simulación vigente.
12. El modo predeterminado será mover a cuarentena; la purga definitiva será administrativa y explícita.

## 3. Arquitectura

```text
Panel web
    -> API de Railway
        -> canal autenticado de comandos
            -> Data Express Agent (servicio Windows)
                -> sistema de archivos local
```

### 3.1 Panel web

El panel administra servidores vinculados, solicita exploraciones, guarda reglas por servidor, inicia validaciones, presenta simulaciones y autoriza ejecuciones. Nunca accede directamente al disco remoto.

### 3.2 Backend de Railway

El backend será la autoridad para tenant, usuarios, permisos, configuración, trabajos, simulaciones y auditoría. Emitirá comandos acotados y firmados para un agente específico y validará sus respuestas.

### 3.3 Data Express Agent

El agente será un servicio de Windows con identidad propia. Sus responsabilidades serán:

- Vincularse una vez con un código temporal.
- Mantener o renovar una conexión saliente autenticada.
- Enumerar discos y carpetas cuando el administrador tenga permiso.
- Validar y normalizar rutas de Windows.
- Descubrir propiedades dentro de la raíz autorizada.
- Inspeccionar exclusivamente `Core` y los objetivos configurados.
- Simular, mover a cuarentena, restaurar y purgar cuando reciba una orden válida.
- Informar progreso, resultados y errores sin enviar secretos.

El agente no decidirá permisos de usuarios ni aceptará rutas arbitrarias fuera de la configuración autorizada.

## 4. Vinculación y ciclo de vida

### 4.1 Servidor nuevo

1. Un administrador crea una solicitud de vinculación.
2. Railway genera un código aleatorio de un solo uso y corta duración.
3. El instalador registra Data Express Agent como servicio de Windows.
4. El agente presenta el código al backend mediante TLS.
5. El backend entrega una identidad individual al agente y consume el código.
6. El servidor aparece en el panel como conectado.

### 4.2 Servidor ya vinculado

No requiere reinstalación ni nuevas credenciales. El servicio inicia con Windows y se reconecta automáticamente. El panel conserva su configuración y último estado conocido.

### 4.3 Reinstalación o revocación

Una reinstalación de Windows requiere una nueva vinculación. Un administrador podrá revocar un agente perdido o comprometido. La identidad revocada dejará de aceptar y recibir trabajos inmediatamente.

El backend impedirá duplicados durante la misma instalación mediante un identificador estable del agente. Si Windows o el agente se reinstalan, el administrador deberá usar **Reemplazar agente** sobre el registro existente; esta acción revocará la identidad anterior antes de emitir la nueva y conservará la configuración del servidor.

## 5. Configuración del servidor

Cada servidor vinculado tendrá:

- Alias visible.
- Identificador de agente.
- Nombre de host reportado por Windows.
- Estado y última conexión.
- Versión del agente.
- Raíz autorizada seleccionada visualmente, por ejemplo `D:\Ipsofactu`.
- Carpetas objetivo configurables.
- Archivos objetivo configurables.
- Resultado y fecha de la última validación.
- Límites operativos por ejecución.

Valores iniciales sugeridos, editables por servidor:

```text
Carpetas:
Log
LogSec
LogsRadian
Respuesta

Archivos:
BD_log.txt
```

La comparación de nombres será insensible a mayúsculas y minúsculas, pero no usará coincidencias parciales. `Log` no coincidirá con `LogBackup`.

## 6. Experiencia de administración

### 6.1 Lista de servidores

Cada tarjeta mostrará alias, host, estado, última conexión, versión y raíz configurada. Los estados serán `pendiente`, `conectado`, `desconectado`, `desactualizado`, `revocado` y `error`.

### 6.2 Explorador remoto

El botón **Explorar discos y carpetas** abrirá un navegador jerárquico:

1. Lista de unidades que la cuenta del servicio puede leer.
2. Navegación por carpetas mediante carga bajo demanda.
3. Selección explícita de una carpeta raíz.
4. Sin vista ni descarga del contenido de archivos.

El backend y el agente aplicarán límites de paginación, profundidad y tiempo. La interfaz no iniciará un recorrido recursivo mientras el administrador solamente navega.

### 6.3 Validación previa al guardado

Después de seleccionar la raíz y configurar objetivos, **Validar estructura** realizará un recorrido de solo lectura y devolverá:

- Propiedades detectadas.
- Propiedades que contienen `Core`.
- Propiedades sin `Core`.
- Propiedades que contienen `Web`, solo como información.
- Coincidencias por carpeta y archivo objetivo.
- Rutas inaccesibles y errores acotados.
- Duración y posible truncamiento.

**Guardar servidor** permanecerá deshabilitado hasta que la validación finalice correctamente. Un resultado con propiedades sin `Core` podrá guardarse con advertencia; un fallo de conexión, raíz inexistente o acceso denegado a la raíz bloqueará el guardado.

## 7. Algoritmo de descubrimiento

El recorrido será dirigido por estructura, no un barrido completo del disco:

1. Enumerar únicamente las carpetas hijas directas de la raíz.
2. Excluir la cuarentena y entradas que no sean directorios.
3. Considerar cada directorio restante como una propiedad.
4. Buscar un hijo directo llamado `Core`.
5. No abrir ni recorrer `Web`.
6. Dentro de `Core`, identificar solamente carpetas objetivo y archivos objetivo por nombre exacto.
7. Recorrer recursivamente únicamente el contenido de las carpetas objetivo.
8. Asociar cada candidato con su propiedad.

Para aproximadamente 1500 propiedades el trabajo será asíncrono, cancelable y con progreso. Se usará concurrencia acotada para evitar saturar el disco. El resultado indicará propiedades procesadas, total, coincidencias y errores.

## 8. Simulación y ejecución

### 8.1 Simulación

La simulación será obligatoria y no modificará archivos. Mostrará:

- Propiedades recorridas y afectadas.
- Archivos candidatos y protegidos.
- Tamaño que se liberaría.
- Desglose por propiedad y objetivo.
- Advertencias y errores.

La simulación tendrá un identificador, huella del conjunto, configuración usada y vencimiento corto.

### 8.2 Ejecución

La ejecución aceptará únicamente una simulación vigente del mismo servidor, raíz y reglas. Antes de modificar, el agente revalidará identidad, raíz, objetivos y conjunto esperado. Si existe una diferencia, cancelará con conflicto y exigirá simular nuevamente.

El modo normal moverá candidatos a una cuarentena dentro de una ubicación controlada en el mismo volumen cuando sea posible. Esto evita copias innecesarias y permite restaurar. La purga definitiva será una operación separada para administradores, con confirmación reforzada y auditoría.

## 9. Modelo de seguridad

### 9.1 Red

- Solo conexiones salientes HTTPS/WSS con TLS moderno.
- Validación estricta del certificado del backend.
- Sin puertos de escucha del agente accesibles desde la red.
- Reconexión con espera incremental y límite de frecuencia.

### 9.2 Identidad y órdenes

- Identidad criptográfica distinta para cada instalación.
- Código de vinculación aleatorio, de un solo uso y con expiración.
- Credenciales del agente almacenadas con protección de Windows, no en archivos de texto.
- Rotación de credenciales y revocación administrativa.
- Órdenes firmadas, con identificador único, audiencia, tenant, servidor, acción, ruta autorizada y expiración corta.
- Protección contra repetición: una orden consumida no podrá ejecutarse de nuevo.
- El agente rechazará órdenes desconocidas, vencidas, alteradas o destinadas a otro servidor.

### 9.3 Permisos mínimos

El servicio se ejecutará con una cuenta dedicada de Windows. Esa cuenta tendrá acceso solamente a las raíces necesarias y no será administradora local salvo que una instalación lo justifique expresamente. Los permisos NTFS serán la segunda barrera además de las validaciones del producto.

### 9.4 Seguridad de rutas

El agente resolverá rutas canónicas y aplicará todas estas condiciones:

- La raíz debe ser absoluta y pertenecer a un volumen permitido.
- Cada operación debe permanecer dentro de la raíz autorizada.
- Se rechazarán `..`, rutas UNC no aprobadas, dispositivos, streams alternativos y nombres ambiguos.
- Se rechazarán enlaces simbólicos, junctions y reparse points que salgan de la raíz.
- `Web` se bloqueará como segmento directo de una propiedad aunque aparezca en una orden.
- Solo se aceptarán nombres objetivo guardados y validados.
- La allowlist efectiva será calculada por el sistema a partir de la raíz y reglas; no se escribirá manualmente.

### 9.5 Datos y registros

- No se almacenarán contraseñas de RDP, SFTP, SMB ni usuarios interactivos.
- No se enviará contenido de archivos durante exploración o simulación.
- Logs y auditoría excluirán tokens, claves y contenidos.
- Los mensajes de error públicos no incluirán rutas ajenas a la raíz ni detalles internos.
- La información persistida estará aislada por `tenant_id`.

### 9.6 Defensa operativa

- Simulación obligatoria y de corta vigencia.
- Límites por archivos, bytes, duración, propiedades y concurrencia.
- Cancelación cooperativa.
- Cuarentena predeterminada y restauración auditada.
- Purga exclusiva para administradores con confirmación explícita.
- Bloqueo temporal y alertas ante órdenes inválidas repetidas.
- Actualizaciones del agente firmadas y verificación de versión mínima compatible.

## 10. Persistencia

Se conservarán los conceptos existentes de servidor, ejecución, cuarentena, trabajo y auditoría, adaptándolos al agente. Se agregarán o ampliarán datos para:

- Identidad, estado, versión y última conexión del agente.
- Vinculaciones temporales y revocaciones.
- Raíz autorizada y objetivos por servidor.
- Validaciones estructurales.
- Comandos con estado e identificador de idempotencia.
- Simulaciones con huella y vencimiento.
- Progreso y resultado de trabajos.

Ninguna tabla almacenará secretos reutilizables en texto claro.

## 11. Errores y recuperación

- **Agente desconectado:** el trabajo no inicia; se informa el último contacto.
- **Desconexión durante lectura:** el trabajo queda interrumpido y puede repetirse desde una nueva simulación.
- **Desconexión durante modificación:** cada elemento tendrá resultado idempotente. Al reconectar se reconciliará el estado y el trabajo quedará interrumpido; nunca continuará automáticamente una operación destructiva cuyo resultado sea incierto. El operador deberá revisar el informe y generar una nueva simulación.
- **Raíz inexistente o volumen desmontado:** se bloquea la operación y se exige validar nuevamente.
- **Acceso denegado:** se informa la propiedad o ruta relativa sin exponer secretos.
- **Estructura cambiada:** se invalida la simulación y no se modifica nada adicional.
- **Versión incompatible:** se bloquean operaciones destructivas hasta actualizar el agente.

Los errores parciales conservarán resultados por elemento y nunca se convertirán silenciosamente en éxito.

## 12. Pruebas

### 12.1 Unidad

- Normalización y confinamiento de rutas Windows.
- Detección exacta de propiedades, `Core` y objetivos.
- Exclusión absoluta de `Web`.
- Rechazo de traversal, junctions y rutas fuera de raíz.
- Firmas, expiración, audiencia y protección contra repetición.
- Huella de simulación e idempotencia.

### 12.2 Integración

- Árbol temporal con más de 1500 propiedades.
- Propiedades con y sin `Core`.
- Objetivos con variaciones de mayúsculas.
- Permisos NTFS denegados.
- Desconexión y reconexión del agente.
- Cancelación durante exploración y ejecución.
- Cuarentena, restauración y purga.

### 12.3 Contrato

- Vinculación de un solo uso.
- Lista de servidores y estados.
- Exploración paginada.
- Validación previa al guardado.
- Simulación y ejecución ligadas al mismo servidor y configuración.
- Autorización por rol y aislamiento por tenant.

### 12.4 Seguridad

- Intentos de reutilizar órdenes.
- Orden destinada a otro agente o tenant.
- Manipulación de ruta después de firmar.
- Acceso a `Web` directo, por enlace o por cambio de mayúsculas.
- Código de vinculación vencido o utilizado.
- Agente revocado.
- Ausencia de secretos y contenido de archivos en logs.

### 12.5 Aceptación operativa

1. Instalar y vincular un servidor nuevo una sola vez.
2. Reiniciar Windows y comprobar reconexión automática.
3. Explorar discos y seleccionar `D:\Ipsofactu`.
4. Detectar aproximadamente 1500 propiedades sin bloquear la interfaz.
5. Confirmar que únicamente se inspecciona `Core`.
6. Cambiar objetivos configurables sin desplegar código.
7. Simular, mover a cuarentena y restaurar.
8. Ver auditoría completa sin secretos.

## 13. Entrega incremental

La implementación se dividirá en fases verificables:

1. Protocolo, identidad, vinculación y servicio mínimo del agente.
2. Estado y reconexión de agentes en Railway.
3. Explorador de discos y selección de raíz.
4. Configuración por servidor y validación estructural.
5. Simulación asíncrona con progreso.
6. Cuarentena, restauración y auditoría.
7. Purga administrativa y endurecimiento final.
8. Instalador, actualización firmada y pruebas de aceptación.

No se eliminará inmediatamente el transporte remoto existente. Permanecerá aislado durante la transición hasta que el agente complete las pruebas de aceptación; después se retirará mediante una migración explícita.

## 14. Fuera de alcance inicial

- Controlar visualmente el escritorio de Windows.
- Implementar un cliente RDP dentro del navegador.
- Transferir o editar contenido de archivos desde el explorador.
- Exponer SMB, RDP, SFTP o una API del agente a Internet.
- Ejecutar scripts arbitrarios enviados desde Railway.
- Actualizaciones automáticas sin firma y validación.

## 15. Criterios de aceptación

La funcionalidad estará terminada cuando:

1. Un agente nuevo pueda vincularse una vez y reconectarse después de reiniciar.
2. Un agente existente aparezca sin reinstalación ni duplicados.
3. El administrador pueda explorar discos y seleccionar la raíz visualmente.
4. No se pueda guardar una raíz sin una validación satisfactoria.
5. El descubrimiento trate cada hijo directo como propiedad y busque solo `Core`.
6. `Web` permanezca fuera de toda exploración destructiva.
7. Las carpetas y archivos objetivo sean configurables por servidor.
8. El barrido de 1500 propiedades sea asíncrono, cancelable y observable.
9. Toda ejecución requiera una simulación vigente y coincidente.
10. Cuarentena y restauración funcionen antes de habilitar purga.
11. Identidad, firma, expiración, revocación y antirrepetición estén probadas.
12. No existan puertos entrantes del agente ni secretos en texto claro o logs.
13. Las pruebas unitarias, de integración, contrato, seguridad y aceptación estén verdes.

