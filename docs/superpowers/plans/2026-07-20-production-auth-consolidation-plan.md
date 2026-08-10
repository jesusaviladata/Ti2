# Plan de implementación: autenticación productiva

Especificación: `docs/superpowers/specs/2026-07-20-production-auth-consolidation-design.md`

## Principios de ejecución

- Trabajar sobre `app.main:app`; `dev_server.py` solo sirve como referencia de comportamiento.
- Escribir una prueba que falle antes de cada corrección funcional.
- Aplicar un cambio causal por vez y ejecutar la prueba específica antes de continuar.
- No migrar módulos distintos de autenticación durante este bloque.
- No introducir credenciales, tokens o secretos en logs, fixtures distribuidos o respuestas del frontend.

## Paso 1: establecer pruebas productivas de autenticación

Archivos:

- Crear `backend/tests_prod/conftest.py`.
- Crear `backend/tests_prod/test_auth_contract.py`.
- Crear `backend/tests_prod/test_auth_security.py`.

Trabajo:

- Construir fixtures para una base de datos aislada y un almacén de sesiones falso con la misma interfaz que Redis.
- Demostrar los fallos actuales: correo inexistente provoca error interno, login no escribe cookies, refresh exige body, logout exige Bearer y los tokens aparecen en JSON.
- Verificar códigos de error, ausencia de secretos y atributos de cookies.

Validación:

- Las nuevas pruebas deben fallar por las causas esperadas antes de editar la implementación.

## Paso 2: endurecer configuración y errores de dominio

Archivos:

- Modificar `backend/app/core/config.py`.
- Crear `backend/app/core/errors.py`.
- Modificar `backend/app/main.py`.
- Modificar `.env.example`.

Trabajo:

- Agregar `APP_ORIGIN`, configuración de cookies y parámetros de sesión/rate limit.
- Rechazar placeholders, secretos cortos y configuración productiva insegura.
- Definir errores tipados con códigos estables y un handler uniforme.
- Conservar mensajes internos fuera de las respuestas.

Validación:

- Ejecutar pruebas de configuración y contrato de errores.

## Paso 3: crear el almacén de sesiones Redis

Archivos:

- Crear `backend/app/services/session_store.py`.
- Crear `backend/tests_prod/test_session_store.py`.

Trabajo:

- Definir una interfaz pequeña para crear, consultar, rotar y revocar familias.
- Implementar operaciones Redis con expiración.
- Implementar rotación atómica y detección de reutilización.
- Implementar rate limit por correo normalizado e IP.
- Traducir indisponibilidad de Redis a `AUTH_SERVICE_UNAVAILABLE`.

Validación:

- Probar creación, rotación, reutilización, revocación, expiración y concurrencia.

## Paso 4: unificar tokens, cookies y usuario actual

Archivos:

- Modificar `backend/app/core/security.py`.
- Crear `backend/app/core/cookies.py`.
- Crear `backend/app/core/csrf.py`.

Trabajo:

- Sustituir la blocklist global por estado de sesión.
- Emitir claims `tenant_id`, `sid`, `jti`, `type`, `iat` y `exp`.
- Leer access desde cookie para la aplicación web.
- Escribir y borrar cookies en helpers únicos.
- Validar CSRF y origen en métodos mutantes autenticados.
- Mantener la base de datos como autoridad de usuario activo y tenant.

Validación:

- Ejecutar pruebas de cookies, claims, revocación, CSRF y usuario desactivado.

## Paso 5: corregir servicio y endpoints de autenticación

Archivos:

- Modificar `backend/app/services/auth_service.py`.
- Modificar `backend/app/api/v1/auth.py`.
- Modificar `backend/app/schemas/auth.py`.

Trabajo:

- Sustituir el hash dummy malformado por uno bcrypt válido generado de forma estable.
- Normalizar correo y aplicar rate limit por cuenta/IP.
- Crear sesión y cookies sin devolver tokens.
- Implementar desafío TOTP opcional mediante cookie preauth.
- Implementar refresh rotatorio sin body.
- Implementar logout idempotente que siempre borre cookies.
- Verificar usuario activo en login, TOTP y refresh.

Validación:

- Ejecutar todos los tests productivos de autenticación.

## Paso 6: revocación al desactivar usuarios y bootstrap seguro

Archivos:

- Modificar `backend/app/services/user_service.py`.
- Modificar `backend/app/api/v1/users.py` si es necesario para inyectar el almacén de sesiones.
- Reemplazar `backend/scripts/seed_admin.py` por un bootstrap idempotente sin contraseña fija.
- Crear pruebas de bootstrap y desactivación.

Trabajo:

- Revocar todas las sesiones del usuario al desactivarlo.
- Crear o localizar el tenant Data Express de manera idempotente.
- Leer correo y contraseña administrativa desde entrada segura.
- Validar fortaleza y nunca imprimir la contraseña.

Validación:

- Probar doble ejecución, contraseña débil, usuario existente y revocación.

## Paso 7: alinear el frontend al contrato de cookies

Archivos:

- Modificar `frontend/src/lib/api.ts`.
- Modificar `frontend/src/hooks/useAuth.ts`.
- Modificar `frontend/src/services/auth.service.ts`.
- Modificar `frontend/src/store/auth.store.ts`.
- Modificar `frontend/src/app/(auth)/login/page.tsx`.
- Modificar textos de configuración relacionados con TOTP.

Trabajo:

- Usar API relativa en producción.
- Eliminar `accessToken` del store y parámetros de servicios.
- Agregar `X-CSRF-Token` en peticiones mutantes.
- Mantener una sola renovación concurrente y excluir refresh del reintento.
- Consultar `/me` después del login.
- Mostrar errores accionables y no ocultar fallos de logout.
- Eliminar credenciales de prueba y marcas específicas de autenticadores.

Validación:

- Ejecutar type-check, build y pruebas contractuales del cliente.

## Paso 8: preparar el despliegue mínimo productivo

Archivos:

- Modificar `docker-compose.yml`.
- Modificar `backend/Dockerfile`.
- Modificar `nginx/nginx.conf`.
- Modificar `.env.example`.
- Agregar un paso documentado de Alembic/bootstrap.

Trabajo:

- Eliminar `--reload` y bind mounts de producción.
- Usar la etapa productiva del frontend.
- Mantener PostgreSQL y Redis fuera de puertos públicos.
- Ejecutar migraciones antes del backend.
- Añadir health/readiness para PostgreSQL y Redis.
- Configurar proxy del mismo origen y encabezados de proxy confiables.

Validación:

- Validar configuración de Compose y Nginx.
- Arrancar el stack cuando Docker esté disponible.

## Paso 9: regresión y aceptación

Trabajo:

- Ejecutar suite backend existente y productiva.
- Ejecutar type-check, lint corregido y build frontend.
- Ejecutar login, refresh, logout y desactivación desde navegador.
- Confirmar que no hay tokens en body, localStorage o sessionStorage.
- Buscar credenciales y placeholders conocidos en archivos distribuibles.
- Documentar cualquier verificación que requiera Docker o infraestructura externa.

Resultado esperado:

- El flujo productivo de autenticación cumple todos los criterios de la especificación sin depender de `dev_server.py`.

