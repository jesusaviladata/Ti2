# Ruta de archivo, almacenamiento preferido y progreso del backup

## Objetivo

Simplificar la ubicación de los backups Full, permitir que la empresa elija qué unidad aparece en el encabezado y recuperar un progreso general que se transfiera al menú lateral cuando el proceso continúe en segundo plano.

## Decisiones aprobadas

1. Los backups Full se guardan directamente dentro de la carpeta de fecha, sin una carpeta `FULL` intermedia.
2. `manifest.json` permanece dentro del ZIP como comprobante técnico del paquete.
3. La unidad visible en el encabezado se elige en Configuración y la selección se comparte para toda la empresa.
4. El modal muestra una barra general exclusivamente para creación y validación de los `.bak`.
5. Cuando el usuario continúa en segundo plano, el estado pasa al sidebar y sigue mostrando las fases posteriores de ZIP y envío.

## 1. Estructura del archivo

El agente seguirá creando ZIP, no RAR. La estructura Full será:

```text
<backupRoot>\
└─ 2026-08-20\
   └─ Backup_2026-08-20.zip
      ├─ Base1_2026-08-20.bak
      ├─ Base2_2026-08-20.bak
      └─ manifest.json
```

Los tipos que pueden coexistir con un Full del mismo día conservarán su carpeta para evitar colisiones:

```text
<backupRoot>\
└─ 2026-08-20\
   ├─ Backup_2026-08-20.zip
   ├─ DIFERENCIAL\
   │  └─ Backup_2026-08-20.zip
   └─ LOG\
      └─ Backup_2026-08-20.zip
```

La misma estructura relativa se utilizará al transferir el archivo a SFTP, SMB o filesystem. Un nuevo Full del mismo día sustituirá atómicamente al Full diario anterior, igual que sucede actualmente dentro de la carpeta `FULL`.

El reintento de entrega dejará de deducir siempre el tipo desde el directorio padre. Para Full reconocerá directamente `<fecha>/Backup_<fecha>.zip`; para diferencial y log seguirá validando `<fecha>/<tipo>/Backup_<fecha>.zip`.

## 2. Función de `manifest.json`

El manifiesto permanecerá en la raíz del ZIP. Contiene versión, ejecución, fecha, tipo, origen y una lista de las bases incluidas. Para cada `.bak` registra nombre, tamaño, hash SHA-256, resultado de validación y método utilizado.

No almacena contraseñas ni secretos. Permite auditar el origen del paquete, comprobar que los archivos no cambiaron y validar que el ZIP contiene exactamente los backups esperados. La creación atómica seguirá rechazando cualquier ZIP corrupto o sin manifiesto.

## 3. Unidad de almacenamiento preferida

### Persistencia

La preferencia será de alcance empresa/tenant, no del navegador. Se almacenará con:

- `preferred_agent_id`, nullable y vinculado al agente.
- `preferred_volume_key`, nullable.

La migración ampliará la configuración de almacenamiento existente. Si no existe una preferencia, el sistema conservará el comportamiento automático actual y mostrará la unidad de mayor riesgo.

### API

- `GET /api/v1/agent-storage` incluirá la preferencia vigente y el elemento resuelto para el encabezado.
- `PUT /api/v1/agent-storage/preference` validará que el agente y la unidad pertenecen al tenant antes de guardarlos.
- `DELETE /api/v1/agent-storage/preference` restaurará la selección automática.

Si la unidad elegida deja de reportarse, la API mantendrá la preferencia, indicará que no está disponible y entregará temporalmente la unidad de mayor riesgo como respaldo visual.

### Interfaz

Configuración tendrá una sección `Almacenamiento` con un selector `Unidad visible en el encabezado`. Cada opción mostrará `Agente · Etiqueta (Unidad)`. También habrá una opción `Automático · mostrar la unidad con mayor riesgo`.

El encabezado mostrará una sola unidad. El desplegable conservará el inventario completo y marcará cuál está configurada como principal.

## 4. Progreso general y segundo plano

### Modal de Nuevo backup

Después de iniciar el lote aparecerá una barra `Progreso general`. Su porcentaje será el promedio del progreso de creación y validación de todas las bases:

- Creación del `.bak`: avance operativo.
- `RESTORE VERIFYONLY`: validación en curso.
- `.bak` creado y validado: 100 % para esa base.

La barra general llega a 100 % cuando todas las bases del lote tienen un `.bak` válido. No incluirá compresión ni transferencia, para no retrasar el estado principal que el operador necesita confirmar.

Debajo se conservará el detalle por base y se distinguirá la segunda etapa `ZIP + envío`.

### Transferencia al sidebar

El botón `Continuar en segundo plano` y el cierre del modal guardarán `jobId`, IDs de backup, bases y hora de inicio en el estado persistente existente. El sidebar retomará inmediatamente el mismo trabajo.

El indicador lateral entenderá todas las fases emitidas por el agente:

- `creating_bak`
- `validating_bak`
- `backup_ready`
- `compressing`
- `archive_ready`
- `transferring`
- `cleaning_up`
- `completed`, `failed` y `cancelled`

Durante creación y validación mostrará el avance general de `.bak`. Una vez listos, cambiará el texto a `Creando ZIP`, `Enviando ZIP` o `Entrega verificada`. La navegación y una recarga de la página no perderán el seguimiento. Al terminar, el resultado quedará visible hasta que el usuario lo descarte.

## 5. Errores y recuperación

- Si una base falla antes de validarse, la barra se marca como fallida y muestra cuántas bases terminaron correctamente.
- Si los `.bak` están listos pero falla el ZIP o el envío, el estado principal permanece `Backup listo` y el sidebar marca `Entrega fallida`.
- El reintento de entrega reutiliza el ZIP validado y la nueva regla de rutas.
- Si no se puede resolver la unidad preferida, el encabezado muestra el respaldo automático con una advertencia discreta.

## 6. Compatibilidad y entrega

El cambio de carpetas vive en el agente de Windows, por lo que se publicará como agente `0.4.2`. Backend y frontend pueden desplegarse primero; la estructura nueva empezará a utilizarse cuando cada servidor actualice el agente.

No se migrarán ni moverán backups históricos. Las carpetas `FULL` existentes seguirán siendo válidas y consultables.

## 7. Verificación

- Pruebas del agente para Full directo, diferencial/log con carpeta, reemplazo atómico y reintento de entrega.
- Pruebas que aseguren que el manifiesto y los hashes permanecen dentro del ZIP.
- Pruebas de API para guardar, borrar, aislar por tenant y resolver una preferencia no disponible.
- Verificación del progreso general, traspaso al sidebar, recarga, éxito de `.bak` con entrega fallida y descarte final.
- TypeScript, pruebas backend/agente y compilación de producción del frontend.
