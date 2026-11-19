# Data Express Agent 0.5.1

- Fecha de preparación: 19 de noviembre de 2026
- Base: 0.5.0
- Tipo: mejora de Limpieza. No cambia el protocolo, la vinculación ni los backups.

## Qué cambia

### Raíz de limpieza con descubrimiento de propiedades

Antes, la raíz tenía que ser la carpeta que contiene las propiedades (`D:\Ipsofactu`) y el agente solo miraba un nivel: `raíz\Propiedad\core`.

Ahora la raíz puede ser una unidad completa (`D:\`) o cualquier carpeta de grupo. El agente busca las propiedades **hasta 8 niveles** por debajo. Por ejemplo:

- `D:\Publicaciones\DX`
- `D:\IpsofactuPE\IPSOFACTU\EMPRESAS\PE\PE`
- `D:\Aplicaciones\DataExpress publications\DX\Test\Clientes\Hoteles Elite`

**Qué cuenta como propiedad.** Una carpeta es una propiedad si contiene `core` y, dentro de `core`, al menos **dos** objetivos de Ipsofactu: `Log`, `LogSec`, `LogsRadian`, `Respuesta` o `BD_log.txt`. Así no se toman por propiedades otras aplicaciones que tengan su propia carpeta `core\Log`.

En una raíz que es carpeta de propiedades, como antes (`D:\Ipsofactu`), las hijas directas con `core` siguen contando como propiedad igual que en 0.5.0.

**Protecciones del recorrido:**
- No se siguen enlaces ni puntos de reanálisis.
- No se desciende dentro de una propiedad ya encontrada.
- Se omiten carpetas de sistema: `$RECYCLE.BIN`, `System Volume Information`, `Config.Msi`, `Windows`, `Program Files`, `ProgramData`, `Recovery`, `node_modules`, `.git` y la cuarentena.
- La unidad del sistema (`C:\`) se rechaza como raíz con `ROOT_TOO_BROAD`.
- El recorrido tiene un límite de carpetas y de tiempo. Si se alcanza, el resultado se marca como incompleto.

### Validación de la raíz

La validación devuelve la lista de propiedades encontradas, con su ruta relativa y el número de objetivos de cada una (`properties`, hasta 300). También devuelve las carpetas revisadas y la profundidad máxima.

`propertiesDetected` ahora cuenta solo las propiedades reales. Antes contaba también las subcarpetas sin `core`.

### Simulación: desglose por propiedad y lotes

- `propertySummary` trae, por cada propiedad, los archivos y bytes elegibles, ordenados por espacio (hasta 300).
- **Lotes:** cuando hay más archivos que el límite de seguridad (200 000), la simulación devuelve un lote exacto de ese tamaño y lo marca con `batchLimited`. El lote se puede ejecutar; al terminar se vuelve a simular para el siguiente. Antes, el panel bloqueaba la ejecución y no había forma de limpiar volúmenes grandes.
- Se corrige que el límite de seguridad se superara en uno (200 001).

## Actualización

Desde 0.5.0, en PowerShell como administrador dentro de `installer`:

```powershell
.\Update-DataExpressAgent.ps1
```

Se conservan la identidad y la vinculación. Después hay que volver a validar la raíz en el panel si se quiere cambiar a `D:\`.

## Pruebas

- 12 pruebas nuevas en `agent/tests/test_discovery_properties.py`: rutas reales a distinta profundidad, aplicación ajena con `core\Log`, carpetas de sistema, límite de profundidad y de carpetas, cuarentena y restauración anidadas, lote exacto y reejecución.
- Se ajustó `test_explorer.py` al nuevo significado de `propertiesDetected`.
