# Diseño: identidad Data Express y administración de usuarios

## Alcance aprobado

Integrar la identidad de Data Express Latinoamérica sin sustituir la arquitectura del dashboard. El cambio incluye el login, la navegación principal, la pantalla de configuración y la administración de usuarios.

## Identidad visual

- Usar el logotipo oficial proporcionado, conservando su proporción.
- Mostrar `Data Express Latinoamérica` en la parte superior izquierda.
- Aplicar los colores institucionales del manual: azul profundo, azul claro, azul marino, gris y blanco.
- Usar los rombos del símbolo como motivo visual discreto.
- Eliminar el círculo genérico y el fondo rojo/morado del login.
- Mantener superficies planas, bordes suaves y profundidad mínima.

## Controles de apariencia

- Conservar únicamente el botón de tema del encabezado.
- Eliminar el botón de engranaje y su modal.
- Eliminar la pestaña `Apariencia` de Configuración.

## Login

- Aplicar las validaciones definidas en `2026-08-10-login-validation-alerts-design.md`.
- Mostrar etiquetas visibles y errores debajo de cada campo.
- Marcar campos con `aria-invalid` y asociar mensajes con `aria-describedby`.
- Enfocar el primer campo inválido.
- Mostrar errores de autenticación o disponibilidad en una alerta general.
- No revelar si una dirección de correo está registrada.

## Usuarios

- Agregar una pestaña `Usuarios` visible únicamente para administradores.
- Permitir listar, crear, cambiar rol, activar/desactivar y restablecer contraseñas.
- Usar la tabla `users` existente; no crear una migración.
- Exigir contraseñas de al menos 14 caracteres.
- Impedir que el administrador cambie su propio rol o desactive su propia cuenta.
- Mantener la separación por tenant existente en el servicio.

## Verificación

- Validar casos vacíos, correo inválido y errores HTTP del login.
- Verificar que un usuario no administrador no vea ni pueda consumir la administración de usuarios.
- Probar creación, actualización, activación, desactivación y cambio de contraseña.
- Ejecutar type-check, build y pruebas del backend.
