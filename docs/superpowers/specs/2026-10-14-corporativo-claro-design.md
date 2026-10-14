# Interfaz Corporativo claro

Diseño aprobado por Jesús después de comparar tres propuestas. Integrar la primera con las tablas y filtros de la tercera y el seguimiento de tareas de la segunda.

## Propósito y expresión
El administrador necesita identificar servidores sin conexión, revisar fallos y confirmar copias. El dominio es protección, servidores, copias, verificación, entrega y continuidad. Blanco y gris claro separan superficies; azul corporativo señala navegación y acciones; verde, ámbar y rojo representan estados con etiquetas. Tipografía Segoe UI, base de espaciado de 4 px, radios de 8–12 px y bordes discretos. Sustituir los textos diminutos, las superficies azules y el calendario vacío dominante por jerarquía legible, tarjetas blancas y acciones contextuales.

## Alcance
- Actualizar tokens, controles, navegación, cabecera y pantallas existentes. Claro por defecto; conservar selección explícita de tema oscuro.
- Resumen con indicadores existentes, estado real de agentes, copias SQL en ejecución con progreso reportado, últimas copias y actividad. Mantener calendario histórico secundario cuando tenga actividad.
- Sección Servidores con tabla, búsqueda y filtros de conexión/incidencias/ocupados; conservar configuración, conexiones y reemplazo de agentes.
- No introducir cifras de demostración ni inferir que una copia está verificada por estar completada. No cambiar contratos API ni acciones de respaldo.
- Estados de carga, error y vacío explícitos; conservar enlaces y permisos. Diseño adaptable con navegación compacta en pantallas pequeñas y tablas con desplazamiento contenido.

## Validación e implementación
1. Migrar tokens y componentes comunes; adaptar etiquetas y tamaño de texto.
2. Integrar resumen operativo y tabla de servidores con servicios y consultas existentes, sin peticiones en cascada por servidor.
3. Verificar TypeScript y compilación de producción; revisar escritorio/móvil, filtros, estados vacíos y modo oscuro en navegador.
4. Publicar en la rama que Railway ya despliega y comprobar el panel.

Revisión: el alcance corresponde a la propuesta aprobada; los porcentajes provienen de cada registro SQL y las listas limitadas se identifican como recientes. No se añaden operaciones destructivas ni cambios de permisos.

## Comprobaciones realizadas
- Compilación de producción de Next.js y verificación de TypeScript satisfactorias.
- Prueba local aislada con agentes conectado/desconectado/ocupado y copias completada/fallida/en ejecución. Filtros de incidencias y ejecución, búsqueda combinada y resultado vacío correctos; progreso accesible de 68% mostrado desde el registro.
- Simulación de respuestas 503: métricas desconocidas con guion, mensajes de error visibles y recuperación mediante Actualizar. Respuestas vacías: indicadores en cero y enlaces de inicio, sin calendario vacío dominante.
- Revisión visual de escritorio y móvil de 390 px en claro y oscuro. Ancho del documento de 390 px, con desplazamiento contenido únicamente en tablas.
- Los datos de estas pruebas viven fuera del repositorio desplegado; el panel utiliza los servicios existentes.
