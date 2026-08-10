# Protocolo Data Express Agent v1

## Solicitudes del agente

Cada solicitud autenticada incluye `X-Agent-Id`, `X-Agent-Timestamp`,
`X-Agent-Nonce` y `X-Agent-Signature`. La firma Ed25519 cubre exactamente:

```text
DATAEXPRESS-AGENT-REQUEST-V1
<MÉTODO MAYÚSCULAS>
<RUTA Y QUERY EXACTOS>
<TIMESTAMP UNIX>
<NONCE>
<SHA256 HEX DEL CUERPO REAL>
```

Railway acepta una diferencia máxima de reloj de 120 segundos y consume el nonce
en PostgreSQL. Una firma, agente, timestamp o nonce inválido devuelve el mismo mensaje
público; los códigos internos permiten auditar sin revelar la causa al atacante.

## Comandos de Railway

Railway firma los bytes reales del sobre JSON del comando:

```text
DATAEXPRESS-AGENT-COMMAND-V1
<KEY ID>
<SHA256 HEX DEL CUERPO REAL>
```

El agente verifica el `key id` contra las claves públicas incluidas en su configuración
antes de interpretar o ejecutar el JSON. Un tipo de comando desconocido siempre se
rechaza. Nunca existe un comando de shell genérico.

## Codificación y rotación

Claves y firmas crudas se codifican con Base64 URL-safe sin padding. Railway conserva
la clave privada de comandos únicamente como secreto de producción. El instalador del
agente contiene las claves públicas actual y siguiente para permitir una rotación gradual.

Cambiar cualquiera de los formatos anteriores requiere una nueva versión explícita del
protocolo; no se alterará silenciosamente `v1`.

