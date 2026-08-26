# Diseño de documentación incluida para Data Express Agent 0.5.0

## Objetivo

La entrega incluye `CAMBIOS-AGENTE-0.5.0.md` en la raíz del ZIP. El documento permite
instalar, operar, diagnosticar y continuar el desarrollo sin depender del historial de
la conversación.

## Fuente de verdad

El contenido se deriva del código, las pruebas y los documentos operativos versionados.
Una función no se marca terminada si no está conectada y cubierta por pruebas.

## Estados

| Estado | Significado |
| --- | --- |
| Disponible | Implementada, conectada y cubierta por pruebas |
| Piloto | Implementada y pendiente de validación sostenida |
| Pendiente | Diseñada, pero no ofrecida como función terminada |

## Contenido mínimo

El manual identifica versión, requisitos, instalación, actualización, arquitectura,
perfiles, backup SQL, bases grandes, almacenamiento, limpieza, backup de archivos,
reemplazo de agentes, seguridad, diagnóstico, pruebas, decisiones y limitaciones.

Debe distinguir claramente el motor SQL disponible del módulo de archivos piloto. La
restauración, VSS, retención, cancelación inmediata, ZIP64 y SFTP de archivos se marcan
como pendientes mientras no exista implementación operativa completa.

## Empaquetado

`agent/package.ps1` copia el manual, el instalador rápido y las especificaciones. Todos
los archivos quedan registrados en `SHA256SUMS.txt`. `-ReplaceExisting` conserva la
entrega anterior bajo `agent/release/archive` antes de regenerar una versión.

## Validación

- El Markdown no contiene marcadores editoriales pendientes.
- Las pruebas del agente y del instalador deben pasar.
- El ejecutable incluye versión de archivo y producto.
- El smoke test valida JSON, XML, scripts, versión, manual y hashes.
- El ZIP incluye el manual y todas las especificaciones registradas por SHA-256.

## Resultado esperado

El destinatario recibe un ZIP autocontenido, verificable y apto para instalación nueva o
actualización controlada, con una separación explícita entre disponible, piloto y
pendiente.
