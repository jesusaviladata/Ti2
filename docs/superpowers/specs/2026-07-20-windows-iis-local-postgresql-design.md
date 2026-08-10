# Despliegue local en Windows 11, IIS y PostgreSQL

Fecha: 2026-07-20

## Objetivo

Preparar Gestor PRIMEE para instalarse en la PC Windows 11 de Data Express que ya publica portales mediante IIS. El desarrollo y las verificaciones que no requieren elevación se realizarán ahora. La instalación de componentes, el registro de servicios y la configuración de IIS se ejecutarán al final mediante un procedimiento administrativo reproducible.

No se contratará una instancia externa de base de datos. PostgreSQL residirá en el mismo equipo, pero sus archivos se mantendrán fuera del código fuente y fuera del directorio publicado por IIS.

## Decisiones aprobadas

- La primera y única empresa operativa será Data Express, conservando `tenant_id` en el modelo.
- IIS seguirá siendo el punto público de entrada y terminará HTTPS.
- PostgreSQL se instalará de forma nativa como servicio de Windows.
- Redis se eliminará de la arquitectura productiva. PostgreSQL almacenará también sesiones, revocaciones y rate limiting.
- FastAPI y Next.js se ejecutarán como servicios internos de Windows mediante WinSW.
- FastAPI escuchará en `127.0.0.1:8000` y Next.js en `127.0.0.1:3000`.
- IIS enviará `/api` a FastAPI y el resto del tráfico a Next.js mediante ARR y URL Rewrite.
- Los archivos `.bak` administrados por el módulo Backups no se almacenarán dentro de PostgreSQL ni en la carpeta de respaldos internos del portal.
- La lógica funcional de Backups, Limpieza, Accesos y Dashboard queda fuera de este bloque.
- La instalación elevada se hará al final, cuando el usuario recupere acceso administrativo.

## Estructura de archivos

La configuración predeterminada será:

```text
D:\DataExpress\GestorPrimee\
|-- app\
|   |-- releases\
|   `-- current\
|-- config\
|   `-- production.env
|-- data\
|   `-- postgresql\
|-- backups\
|   `-- postgresql\
|-- logs\
|   |-- backend\
|   |-- frontend\
|   `-- maintenance\
`-- installer\
```

Las rutas no estarán dispersas en scripts. Se definirán en `installer/install-config.psd1`:

```powershell
@{
    InstallRoot  = "D:\DataExpress\GestorPrimee"
    PostgresData = "D:\DataExpress\GestorPrimee\data\postgresql"
    BackupRoot   = "D:\DataExpress\GestorPrimee\backups\postgresql"
    OffsiteRoot  = ""
}
```

Para cambiar de unidad o carpeta bastará modificar ese archivo antes de instalar. `OffsiteRoot` será opcional y aceptará otra unidad o una ruta UNC.

## Límites de los datos

PostgreSQL será la fuente de verdad del portal y contendrá:

- tenants y usuarios;
- sesiones, familias de refresh, revocaciones y límites de intentos;
- auditoría y registros de acceso;
- configuración, historial y programación de limpiezas;
- metadatos, programación y estado de backups;
- alertas y configuración del portal.

PostgreSQL no contendrá los archivos `.bak` de SQL Server. Esos archivos seguirán usando la ruta configurada en el módulo Backups. Los respaldos de PostgreSQL bajo `backups\postgresql` protegerán únicamente la información interna del portal.

## Sesiones sin Redis

Se agregará una migración Alembic posterior a `0001` con tablas separadas para:

- `auth_sessions`: `sid`, usuario, tenant, refresh vigente, CSRF, revocación y expiración;
- `auth_refresh_history`: identificadores consumidos necesarios para detectar reutilización;
- `auth_login_limits`: clave opaca de cuenta e IP, contador y expiración.

La rotación de refresh se ejecutará en una transacción PostgreSQL con bloqueo de la fila de sesión. Solo el `jti` vigente podrá consumirse. Presentar un refresh anterior revocará la familia completa.

La dependencia de usuario actual validará la firma JWT, el tenant, la sesión activa y el estado del usuario. Los contadores expirados se eliminarán durante nuevas operaciones y mediante una tarea de mantenimiento.

Las operaciones de autenticación deberán fallar de forma cerrada con `503 AUTH_SERVICE_UNAVAILABLE` si PostgreSQL no está disponible. No habrá fallback en memoria en producción.

## Procesos de aplicación

WinSW administrará dos servicios:

- `DataExpressGestorBackend`: ejecutará Uvicorn/FastAPI desde el entorno Python distribuido.
- `DataExpressGestorFrontend`: ejecutará el servidor standalone de Next.js con Node.js.

Los servicios usarán rutas absolutas, un directorio de trabajo explícito, reinicio automático y rotación de stdout/stderr. Ninguno escuchará en una interfaz pública.

Los secretos vivirán en `config\production.env`. El instalador limitará sus permisos al grupo de administradores y a las identidades de servicio. El archivo no se copiará a `app\releases`, al sitio público de IIS ni a los respaldos de código.

## IIS

El instalador comprobará IIS, URL Rewrite y Application Request Routing. No sobrescribirá otros portales.

Creará o actualizará únicamente el sitio o aplicación asignado a Gestor PRIMEE y configurará:

- `/api/*` hacia `http://127.0.0.1:8000/api/*`;
- el resto hacia `http://127.0.0.1:3000`;
- conservación de `Host`, dirección del cliente y protocolo reenviado;
- WebSocket cuando el portal lo requiera;
- límites de tamaño y tiempos de espera explícitos;
- cabeceras de seguridad compatibles con el frontend;
- HTTPS obligatorio una vez asociado el certificado existente.

La configuración se generará como un `web.config` versionado y una rutina PowerShell acotada al sitio del producto.

## Migraciones y bootstrap

La base se inicializará exclusivamente mediante Alembic. El instalador:

1. comprobará conexión y versión de PostgreSQL;
2. obtendrá la revisión Alembic actual;
3. generará un respaldo previo si la base ya existe;
4. ejecutará `alembic upgrade head`;
5. verificará que la revisión esperada quedó aplicada;
6. ejecutará el bootstrap idempotente de Data Express cuando no exista;
7. iniciará los servicios únicamente si todas las verificaciones anteriores pasan.

El correo y la contraseña iniciales se solicitarán durante la instalación o se recibirán mediante variables temporales. No habrá credenciales predeterminadas ni contraseñas impresas en logs.

## Instalador administrativo

Se prepararán dos comandos:

- `Test-InstallPrerequisites.ps1`: diagnóstico seguro que no modifica el equipo y puede ejecutarse antes de disponer de elevación.
- `Install-GestorPrimee.ps1`: instalación idempotente que exige una consola elevada.

El instalador administrativo realizará:

1. validación de configuración, elevación, arquitectura, espacio y puertos;
2. creación de directorios y ACL;
3. instalación o validación de PostgreSQL y sus herramientas;
4. creación de rol y base con contraseña aleatoria;
5. despliegue versionado del backend y frontend;
6. generación del entorno productivo;
7. migraciones y bootstrap;
8. registro o actualización de servicios WinSW;
9. configuración acotada de IIS;
10. registro de tareas de respaldo y mantenimiento;
11. pruebas de salud y contrato;
12. activación de `app\current` solo después de aprobar las pruebas.

Una instalación repetida no duplicará usuarios, tareas, servicios ni reglas IIS. Las descargas, cuando sean necesarias, exigirán HTTPS, una versión fijada y verificación SHA-256. También se permitirá proporcionar instaladores desde una carpeta local.

## Respaldos y recuperación

La política inicial será:

- un `pg_dump` diario en formato custom y comprimido;
- 14 respaldos diarios;
- 8 respaldos semanales;
- validación inmediata del archivo mediante `pg_restore --list`;
- log estructurado de inicio, resultado, tamaño y hash SHA-256;
- copia adicional a `OffsiteRoot` cuando se configure;
- prueba mensual de restauración en una base temporal durante una ventana de mantenimiento.

Los respaldos en la misma unidad `D:` no protegen contra la pérdida física de esa unidad. El instalador mostrará una advertencia persistente mientras `OffsiteRoot` esté vacío, pero esto no bloqueará la primera instalación aprobada.

La restauración nunca sobrescribirá automáticamente producción. `Restore-GestorPrimee.ps1` restaurará primero a una base temporal, ejecutará comprobaciones y pedirá confirmación administrativa antes de cualquier intercambio controlado.

## Salud, errores y rollback

FastAPI expondrá:

- `/health/live`: confirma que el proceso responde;
- `/health/ready`: confirma PostgreSQL, revisión Alembic y dependencias esenciales.

IIS solo enviará tráfico a una versión que pase readiness. Los errores de instalación se escribirán sin secretos en `logs\maintenance` y devolverán un código no cero.

Si fallan migraciones, bootstrap, servicios o smoke tests:

- no se cambiará `app\current`;
- se detendrán únicamente los servicios nuevos iniciados por esa ejecución;
- se conservarán logs y respaldo previo;
- no se ejecutará un downgrade destructivo automático;
- la versión anterior seguirá activa cuando exista.

## Estrategia de pruebas

Antes de la instalación elevada:

- pruebas unitarias del almacén de sesiones PostgreSQL;
- pruebas de concurrencia y reutilización de refresh;
- pruebas de expiración y rate limiting;
- generación SQL offline de Alembic;
- pruebas de scripts PowerShell con configuración temporal;
- validación estática de XML de WinSW y `web.config`;
- pruebas backend existentes, type-check y build frontend;
- búsqueda de secretos, rutas absolutas accidentales y dependencias de Redis.

Durante la instalación final:

- conexión real a PostgreSQL;
- migración desde base vacía y desde la revisión anterior;
- doble ejecución del instalador;
- bootstrap idempotente;
- inicio y reinicio de ambos servicios;
- comprobación de puertos limitados a loopback;
- login, `/me`, refresh y logout a través de IIS/HTTPS;
- creación y validación de un respaldo;
- restauración en base temporal;
- reinicio controlado de Windows y verificación de recuperación automática.

## Criterios de aceptación

- El portal funciona bajo IIS/HTTPS en Windows 11 sin Docker ni Redis.
- PostgreSQL persiste en la ruta configurada de `D:` y nunca dentro del código.
- Los puertos 3000, 5432 y 8000 no son accesibles desde la red.
- Todas las migraciones y el bootstrap son idempotentes.
- La autenticación conserva rotación, revocación, CSRF y rate limiting usando PostgreSQL.
- Los módulos existentes conservan su contrato funcional durante este bloque.
- El instalador puede repetirse sin dañar una instalación activa.
- Existe un respaldo PostgreSQL válido y una restauración comprobada.
- Cambiar las rutas requiere editar únicamente `install-config.psd1` antes de instalar.

## Trabajo posterior fuera de alcance

Después de este bloque se realizará el barrido funcional y la corrección específica de Backups, Limpieza, Accesos, Dashboard, Alertas y Reportes. También se definirá una ubicación externa para `OffsiteRoot` cuando Data Express disponga de otra unidad o carpeta de red.
