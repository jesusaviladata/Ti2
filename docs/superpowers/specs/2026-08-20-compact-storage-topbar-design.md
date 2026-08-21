# Indicador compacto de almacenamiento en la barra superior

## Objetivo

Mover la telemetría de almacenamiento de los agentes desde la franja de ancho completo hacia la barra superior, inmediatamente después del buscador, para recuperar espacio vertical sin perder visibilidad sobre discos con poco espacio.

## Diseño aprobado

- Mostrar hasta dos unidades como indicadores compactos junto al buscador.
- Cada indicador incluye nombre de unidad, espacio disponible y una barra delgada con el mismo código de color actual: verde saludable, ámbar advertencia y rojo crítico.
- Ordenar las unidades por severidad, de modo que las de mayor riesgo aparezcan primero.
- Al hacer clic en el bloque se despliega el inventario completo con agente, unidad, antigüedad de la lectura, capacidad y rol.
- En anchos intermedios mostrar únicamente la unidad de mayor riesgo; en móvil conservar un botón compacto que abre el detalle.
- Mantener la consulta automática cada 30 segundos y una acción manual para reintentar cuando la telemetría falle.
- Retirar por completo la franja de almacenamiento situada debajo de la barra superior.

## Estados

- Cargando: esqueleto compacto sin alterar la altura del encabezado.
- Sin telemetría: botón discreto con texto abreviado y opción de actualización.
- Error: indicador compacto de advertencia y reintento.
- Con datos: unidades compactas y detalle desplegable.

## Accesibilidad e interacción

- El activador es un botón con `aria-expanded`, `aria-haspopup` y una descripción del estado general.
- El detalle se cierra con Escape o al hacer clic fuera.
- Las barras exponen su porcentaje y capacidad mediante atributos de progreso.
- El color nunca es la única señal: se conserva el texto de capacidad y el estado en el detalle.

## Límites

El cambio es exclusivamente de presentación. No modifica el contrato del API, los umbrales, el sondeo ni la recopilación de volúmenes del agente.
