# Diseño: validaciones y alertas del login

## Objetivo

Mostrar mensajes claros y accesibles cuando el formulario de inicio de sesión esté incompleto, tenga un correo inválido o el backend rechace/no pueda procesar la autenticación.

## Comportamiento aprobado

### Validación local

- Correo vacío: `Ingresa tu correo electrónico.`
- Correo con formato inválido: `Ingresa un correo electrónico válido.`
- Contraseña vacía: `Ingresa tu contraseña.`
- La validación ocurre al enviar el formulario.
- El primer campo inválido recibe el foco.
- El error de un campo desaparece cuando el usuario corrige su valor.

### Errores de autenticación

- HTTP 401: `Correo o contraseña incorrectos.`
- HTTP 403: usar el mensaje seguro del backend cuando indique cuenta desactivada; para otros casos, `No fue posible autorizar el inicio de sesión.`
- HTTP 429: `Demasiados intentos. Espera unos minutos e inténtalo nuevamente.`
- HTTP 5xx o fallo de red: `El servicio no está disponible en este momento. Inténtalo nuevamente.`
- Otros errores: `No fue posible iniciar sesión. Inténtalo nuevamente.`

La respuesta 401 no distinguirá entre correo inexistente y contraseña incorrecta para evitar filtración de cuentas.

## Presentación

- Cada error local aparecerá debajo de su campo.
- Los campos inválidos usarán borde rojo, `aria-invalid` y `aria-describedby`.
- Los errores del backend aparecerán en la alerta roja general existente.
- La alerta general usará `role="alert"` y `aria-live="polite"`.
- No se usarán ventanas emergentes del navegador ni notificaciones duplicadas.

## Flujo

1. El usuario envía el formulario.
2. El frontend valida correo y contraseña.
3. Si hay errores locales, muestra mensajes, enfoca el primer campo inválido y no llama a la API.
4. Si los campos son válidos, llama a `/api/v1/auth/login`.
5. El hook normaliza la respuesta de error a un mensaje seguro.
6. La pantalla presenta la alerta general o redirige al dashboard si el login funciona.

## Verificación

- Enviar ambos campos vacíos.
- Enviar solamente el correo.
- Enviar un correo con formato inválido.
- Probar credenciales incorrectas.
- Simular 403, 429, fallo de red y 5xx.
- Confirmar navegación exitosa con credenciales válidas.
- Ejecutar `npm run type-check` y `npm run build`.

## Fuera de alcance

- Recuperación de contraseña.
- Registro público de usuarios.
- Cambios en el esquema de PostgreSQL.
