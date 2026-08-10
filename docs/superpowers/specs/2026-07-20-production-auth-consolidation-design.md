# Consolidación de autenticación para producción

Fecha: 2026-07-20

> **Estado vigente:** este archivo conserva el diseño histórico. Para operar Data Express use `docs/operations/production-readiness.md`: no se despliega Redis y TOTP/2FA está retirado del flujo activo; las columnas históricas de TOTP sólo se conservan por compatibilidad.


## Objetivo

Convertir `app.main:app` en el único backend desplegable y entregar un flujo de autenticación seguro, coherente con el frontend y preparado para la primera salida de Data Express bajo un solo dominio HTTPS.

El resultado de este bloque debe eliminar la divergencia actual entre `dev_server.py`, el frontend y la API productiva. `dev_server.py` quedará únicamente como referencia temporal y no será una opción de despliegue.

## Decisiones aprobadas

- La aplicación se publicará bajo un único dominio HTTPS.
- Nginx servirá el frontend en `/` y enviará `/api` a FastAPI.
- `app.main:app` será la única API productiva.
- La primera empresa será Data Express.
- Se conservará `tenant_id` en el modelo para evitar una migración estructural futura, aunque el primer lanzamiento tenga un solo tenant.
- La autenticación de la aplicación web será mediante cookies seguras de primera parte.
- El 2FA no será obligatorio. Permanecerá como capacidad TOTP opcional y agnóstica de proveedor.
- No habrá referencias a Google Authenticator en producto o documentación.
- PostgreSQL será la fuente de verdad de usuarios y Redis mantendrá sesiones, revocaciones y límites de intentos.

## Alcance

Este bloque incluye:

- Login, consulta de usuario actual, refresh y logout.
- Cookies `HttpOnly` para access y refresh.
- Rotación de refresh y detección de reutilización.
- Revocación inmediata de sesiones mediante Redis.
- Protección CSRF para peticiones autenticadas que modifican estado.
- Rate limiting por cuenta normalizada e IP.
- Desactivación de usuario con revocación de sesiones.
- Flujo TOTP opcional para usuarios que ya lo tengan habilitado.
- Eliminación de tokens de respuestas utilizadas por el frontend y de stores accesibles a JavaScript.
- Bootstrap seguro del tenant Data Express y su primer administrador.
- Pruebas backend, contractuales y del flujo frontend.
- Ajustes mínimos de Nginx, variables de entorno y Docker necesarios para este flujo.

No incluye todavía:

- Migración funcional de backups, limpieza, accesos, dashboard o reportes.
- Activación obligatoria de 2FA.
- SSO, OAuth social o integración con un proveedor corporativo de identidad.
- Administración multiempresa desde la interfaz.
- API pública para clientes externos.

## Arquitectura

```text
Navegador
   |
   | HTTPS, mismo origen
   v
Nginx
   |-- /        -> Next.js
   `-- /api     -> FastAPI app.main
                      |-- PostgreSQL: tenant y usuarios
                      `-- Redis: sesiones, revocación y rate limit
```

El frontend usará una URL relativa para la API. No deberá contener `localhost:8000` en el bundle productivo. CORS quedará restringido al dominio configurado; al operar en el mismo origen, no será el mecanismo principal de seguridad.

## Modelo de sesión

### Cookies

| Cookie | Propósito | Atributos productivos |
|---|---|---|
| `access_token` | JWT de acceso de 15 minutos | `HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/` |
| `refresh_token` | JWT rotatorio de 7 días | `HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/api/v1/auth` |
| `csrf_token` | Valor presentado también en `X-CSRF-Token` | `Secure`, `SameSite=Lax`, `Path=/`, legible por el frontend |
| `preauth_token` | Desafío TOTP opcional de 5 minutos | `HttpOnly`, `Secure`, `SameSite=Strict`, `Path=/api/v1/auth/totp` |

En desarrollo local se permitirá `Secure=false` mediante una configuración explícita de entorno. La configuración productiva deberá fallar al arrancar si HTTPS/cookies seguras o secretos requeridos no están correctamente definidos.

### Estado en Redis

Cada sesión tendrá un identificador `sid` y una familia de refresh. Redis conservará:

- Usuario y familia asociados.
- `jti` de refresh actualmente válido.
- Estado activo o revocado.
- Expiración máxima de la sesión.
- Marcadores temporales para detectar reutilización de refresh.
- Contadores de intentos por correo normalizado e IP.

La renovación consumirá atómicamente el refresh vigente y emitirá otro. Si se presenta un refresh anterior, se revocará toda la familia.

Los access tokens incluirán `sub`, `tenant_id`, `sid`, `jti`, `type`, `iat` y `exp`. La dependencia de autenticación validará la firma, el tipo y el estado de la sesión en Redis antes de cargar al usuario desde PostgreSQL.

## Flujos

### Login sin 2FA

1. El frontend envía correo y contraseña como formulario.
2. El backend normaliza el correo, registra el intento sin datos sensibles y aplica rate limit por cuenta e IP.
3. Se ejecuta una comparación bcrypt válida incluso si la cuenta no existe.
4. Si las credenciales son incorrectas, se devuelve el mismo error para usuario inexistente o contraseña incorrecta.
5. Si el usuario está activo y no tiene TOTP habilitado, se crea la familia de sesión en Redis.
6. Se escriben access, refresh y CSRF cookies.
7. La respuesta no incluye tokens. El frontend solicita `/api/v1/auth/me`, actualiza el perfil en Zustand y navega al dashboard.

### Login con TOTP opcional

1. Después de validar la contraseña, el backend escribe únicamente `preauth_token` y responde `requires_totp=true`.
2. El frontend solicita un código TOTP sin nombrar una aplicación específica.
3. El backend valida el desafío, el usuario y el código con límite de intentos.
4. Si es correcto, elimina `preauth_token` y crea la sesión normal.

La configuración o enrolamiento de TOTP no bloqueará el lanzamiento. Si se conserva habilitada para usuarios existentes, el secreto deberá almacenarse cifrado con una llave separada de `SECRET_KEY`.

### Refresh

1. Una petición recibe `401 AUTH_SESSION_EXPIRED` por access expirado.
2. El interceptor inicia una única llamada concurrente a `/auth/refresh`.
3. El backend valida cookie refresh, familia y `jti` actual en Redis.
4. Redis rota el `jti` de manera atómica.
5. El backend reemplaza access, refresh y CSRF cookies y responde sin tokens.
6. Axios repite una sola vez la petición original.

La llamada de refresh no podrá disparar otro refresh. Si falla, el cliente limpia su perfil y navega a login.

### Logout

Logout será idempotente. El backend intentará revocar la familia identificada por las cookies y siempre eliminará access, refresh, CSRF y preauth de la respuesta, incluso cuando el token esté expirado o sea inválido.

### Usuario desactivado

Al desactivar un usuario se revocarán todas sus familias de sesión. Las dependencias seguirán verificando `is_active` en PostgreSQL para defensa en profundidad.

## CSRF

Las peticiones `POST`, `PUT`, `PATCH` y `DELETE` autenticadas mediante cookies requerirán `X-CSRF-Token`. El valor deberá coincidir con la cookie y con el valor asociado a la sesión en Redis. Se excluyen login y health; refresh y logout se protegen mediante sus cookies restringidas, validación de origen y la política específica del endpoint.

El backend validará también `Origin` o `Referer` contra el origen productivo configurado. No se confiará únicamente en `SameSite`.

## Contrato de API

Los endpoints de autenticación mantendrán rutas existentes para reducir cambios, pero cambiarán a un contrato de cookie:

- `POST /api/v1/auth/login`: `200` con `{ "requires_totp": false }` o `{ "requires_totp": true }`.
- `POST /api/v1/auth/totp/verify`: `200` con `{ "authenticated": true }`.
- `POST /api/v1/auth/refresh`: `204`, sin body.
- `POST /api/v1/auth/logout`: `204`, idempotente.
- `GET /api/v1/auth/me`: perfil público del usuario.

Los errores usarán el formato:

```json
{
  "error": {
    "code": "AUTH_INVALID_CREDENTIALS",
    "message": "Correo o contraseña incorrectos"
  }
}
```

## Códigos de error

| HTTP | Código | Uso |
|---|---|---|
| 401 | `AUTH_INVALID_CREDENTIALS` | Login incorrecto sin revelar existencia de cuenta |
| 401 | `AUTH_SESSION_EXPIRED` | Sesión ausente, expirada o revocada |
| 401 | `AUTH_TOTP_INVALID` | Código o desafío TOTP inválido |
| 403 | `AUTH_CSRF_INVALID` | CSRF u origen inválido |
| 403 | `AUTH_USER_DISABLED` | Cuenta desactivada |
| 429 | `AUTH_RATE_LIMITED` | Exceso de intentos; incluye `Retry-After` |
| 503 | `AUTH_SERVICE_UNAVAILABLE` | PostgreSQL o Redis no disponibles |

No se expondrán excepciones, cadenas de conexión ni detalles internos. Los fallos esperados usarán errores de dominio; los inesperados se registrarán una sola vez con un identificador de correlación.

## Frontend

- Axios usará una base relativa `/` o vacía para el mismo origen.
- `withCredentials` permanecerá habilitado.
- El interceptor compartirá una sola promesa de refresh para solicitudes concurrentes.
- El header CSRF se agregará únicamente en métodos mutantes.
- Zustand persistirá perfil mínimo, pero nunca tokens ni secretos.
- La existencia del perfil persistido no se considerará evidencia de una sesión válida.
- El middleware podrá usar la presencia de la cookie para navegación temprana, pero la API seguirá siendo la autoridad.
- Login, refresh y logout no aceptarán ni devolverán tokens al código cliente.
- Se eliminarán credenciales de prueba y referencias a Google Authenticator.
- Los errores dejarán de silenciarse y mostrarán un estado accionable.

## Bootstrap de Data Express

Una migración o comando administrativo idempotente creará el tenant `Data Express`. El primer administrador se creará mediante un comando explícito que reciba correo y contraseña desde entrada segura o variables de entorno temporales.

El comando:

- No contendrá contraseña por defecto.
- No imprimirá la contraseña.
- Fallará si intenta reutilizar una contraseña conocida o débil.
- Podrá ejecutarse nuevamente sin duplicar tenant o usuario.
- Registrará únicamente que el usuario fue creado o ya existía.

## Configuración y despliegue

Variables mínimas:

- `APP_ORIGIN=https://<dominio>`
- `SECRET_KEY=<secreto aleatorio fuerte>`
- `TOTP_ENCRYPTION_KEY=<llave independiente>` si TOTP está disponible
- `DATABASE_URL=postgresql+asyncpg://...`
- `REDIS_URL=redis://...`
- `COOKIE_SECURE=1`

La validación rechazará secretos vacíos, placeholders, valores cortos y los ejemplos distribuidos con el repositorio. `.env.example` no contendrá credenciales utilizables.

Docker usará `app.main:app` sin `--reload`. Las migraciones se ejecutarán como paso controlado antes de iniciar la aplicación. PostgreSQL y Redis no se publicarán a Internet.

## Observabilidad y auditoría

Se registrarán, sin datos sensibles:

- Login exitoso o fallido.
- Activación de rate limit.
- Refresh y detección de reutilización.
- Logout y revocación administrativa.
- Fallos de PostgreSQL o Redis.

Los registros incluirán timestamp, correlation ID, usuario cuando sea conocido, IP resuelta de proxies confiables y resultado. Nunca incluirán contraseña, JWT, cookie, secreto TOTP o código TOTP.

## Estrategia de pruebas

### Backend

- Usuario inexistente y contraseña incorrecta producen el mismo `401` y nunca un `500`.
- Cookies correctas para login, refresh, TOTP y logout.
- Respuestas sin access/refresh tokens.
- Refresh rotatorio y concurrencia controlada.
- Reutilización de refresh revoca la familia.
- Logout con access vigente, expirado, ausente o inválido.
- Usuario desactivado pierde acceso y refresh.
- Rate limit por correo e IP con expiración.
- CSRF válido, ausente, incorrecto y origen no autorizado.
- Separación por `tenant_id` en carga del usuario.
- Caídas de Redis/PostgreSQL devuelven `503` sin filtrar detalles.

### Frontend y contrato

- TypeScript y build.
- Login sin tokens en storage.
- Una sola renovación ante varios `401` concurrentes.
- No hay bucle de refresh.
- Logout limpia estado aun cuando la API falle, y comunica que el cierre remoto no pudo confirmarse.
- Redirección al login cuando `/me` confirma sesión inválida.
- Flujo TOTP opcional y texto agnóstico de proveedor.
- Contratos OpenAPI comparados con los tipos y servicios consumidos por el frontend.

### Integración

- Stack con PostgreSQL y Redis reales.
- Migración desde una base vacía.
- Bootstrap idempotente de Data Express.
- Login, refresh, logout y revocación desde navegador bajo el mismo origen HTTPS.

## Criterios de aceptación

- `app.main:app` ejecuta todo el flujo de autenticación productivo.
- El frontend no depende de `dev_server.py`.
- No hay tokens en JSON, localStorage o sessionStorage.
- No hay contraseñas conocidas ni secretos de ejemplo aceptables.
- Login, refresh, logout, CSRF, revocación y desactivación pasan pruebas automatizadas.
- TOTP es opcional y no contiene referencias a Google Authenticator.
- Data Express y su administrador pueden inicializarse sin editar código.
- El despliegue bajo un solo dominio funciona con cookies `Secure`.
- Los fallos de infraestructura son visibles y no se confunden con credenciales incorrectas.

