# Control de memoria del frontend en produccion

Fecha: 2026-07-20

## Objetivo

Evitar que Gestor PRIMEE vuelva a consumir decenas de gigabytes de RAM por una multiplicacion de procesos de Next.js. El cambio aplica solo al empaquetado, arranque y supervision del frontend de Data Express. No modifica la logica de Backups, Limpieza, Accesos ni Dashboard.

## Evidencia y causa operativa

El incidente local ocurrio al ejecutar `next dev`: se observaron cientos de procesos Node descendientes del mismo comando y el equipo de 32 GB supero 20 GB de uso. El backend no genero esa multiplicacion. El modo de desarrollo compila bajo demanda y no representa el runtime que debe ejecutarse detras de IIS.

No se atribuye la recuperacion de memoria a una limpieza automatica: la memoria bajo despues de reiniciar Windows.

## Arquitectura aprobada

1. `Build-Release.ps1` se ejecuta en la maquina de preparacion, nunca en el servidor productivo. Valida tipos, genera el build standalone y crea un paquete con `backend`, `frontend` y un manifiesto SHA-256.
2. `Install-GestorPrimee.ps1` acepta unicamente ese paquete precompilado. Verifica el manifiesto, copia `frontend\server.js` y no ejecuta `npm`, `next dev` ni `next build`.
3. WinSW mantiene un solo servicio `DataExpressGestorFrontend`. Este inicia directamente `node server.js` en loopback con `NODE_ENV=production` y `NODE_OPTIONS=--max-old-space-size=512`.
4. Una tarea programada cada minuto inspecciona exclusivamente los descendientes del servicio WinSW. No enumera ni termina procesos Node ajenos al portal.

## Limites y respuesta automatica

- Heap V8: 512 MB.
- Advertencia: memoria residente agregada de Node mayor o igual a 600 MB.
- Incidente de memoria: 900 MB o mas durante tres muestras consecutivas.
- Incidente de procesos: mas de dos procesos Node descendientes del servicio; la respuesta es inmediata porque el runtime normal requiere uno.
- Primeros dos incidentes dentro de una hora: reinicio controlado del servicio.
- Tercer incidente dentro de la misma hora: detencion del frontend para proteger el servidor y registro de un evento critico. El backend, PostgreSQL y otros portales permanecen intactos.

Los umbrales se centralizan en `install-config.psd1` para poder ajustarlos despues de la prueba de carga sin cambiar scripts.

## Registros y privacidad

El monitor escribe JSONL bajo `logs\maintenance`. Registra fecha, PID del servicio, cantidad de procesos Node, memoria agregada, contador de muestras e intervencion aplicada. No registra contrasenas, tokens ni variables de entorno.

## Validacion

- Pruebas Pester confirman que el instalador no contiene comandos npm o builds de Next.js.
- Todas las plantillas y scripts PowerShell deben analizar sin errores.
- El paquete debe incluir un manifiesto valido y `frontend\server.js`.
- El smoke test usa el mismo limite de heap que produccion.
- Se ejecutan type-check, build productivo, pruebas backend y pruebas del instalador.
- No se inicia `next dev` durante esta validacion.
- Antes de entregar se confirma que los puertos 3000 y 8000 estan cerrados y que no quedaron procesos del proyecto.

## Criterios de aceptacion

- El servidor productivo no compila el frontend.
- El servicio productivo ejecuta un solo `server.js` con heap limitado.
- Una tormenta de procesos queda contenida al arbol del servicio de Data Express.
- Dos intentos de recuperacion como maximo por hora evitan ciclos infinitos.
- El instalador conserva sin cambios funcionales los modulos del portal.
