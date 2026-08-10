# Diseño: proxy de mismo origen para Railway

## Objetivo

Mantener los dominios gratuitos de Railway y hacer que autenticación, cookies HttpOnly y protección CSRF funcionen sin depender de cookies de terceros.

## Contexto

- Frontend: `https://dataexpressti.up.railway.app`
- Backend: `https://ti2.up.railway.app`
- `up.railway.app` figura en la Public Suffix List. Por ello, ambos hosts son sitios independientes para las reglas de cookies del navegador.
- El frontend actual llama directamente al backend mediante `NEXT_PUBLIC_API_URL` y trata de leer `csrf_token` desde `document.cookie`.
- Una cookie creada por el host del backend no puede ser leída por JavaScript ejecutado en el host del frontend.

## Enfoque aprobado

El navegador utilizará rutas relativas `/api/*` contra el dominio del frontend. Next.js reenviará internamente esas solicitudes al dominio público del backend mediante una regla `rewrites`.

```text
Navegador
  -> https://dataexpressti.up.railway.app/api/*
  -> proxy de Next.js
  -> https://ti2.up.railway.app/api/*
```

El navegador recibirá las cookies desde el dominio del frontend, podrá leer la cookie CSRF no-HttpOnly y seguirá sin tener acceso a las cookies de sesión HttpOnly.

## Cambios previstos

### Frontend

- Agregar una regla `rewrites` en `next.config.ts` para `/api/:path*`.
- Usar `BACKEND_URL=https://ti2.up.railway.app` como variable exclusiva del servidor.
- Eliminar `NEXT_PUBLIC_API_URL` para que Axios conserve su `baseURL` vacío y haga solicitudes relativas.
- Mantener `NEXT_PUBLIC_WS_URL` únicamente si se implementa WebSocket; actualmente no tiene consumidores.

### Backend

- `APP_ENV=production`
- `APP_ORIGIN=https://dataexpressti.up.railway.app`
- `ALLOWED_ORIGINS=["https://dataexpressti.up.railway.app"]`
- `COOKIE_SECURE=1`
- `COOKIE_SAMESITE=lax`

El backend conservará su dominio público para healthchecks y diagnóstico. No se cambiarán migraciones, esquema de base de datos ni endpoints.

## Flujo de autenticación

1. El navegador envía el login a `/api/v1/auth/login` en el frontend.
2. Next.js reenvía la solicitud al backend.
3. El backend valida `Origin` contra `APP_ORIGIN` y devuelve las cookies.
4. El navegador almacena las cookies bajo el host del frontend.
5. El interceptor de Axios lee `csrf_token` y agrega `X-CSRF-Token` en operaciones mutables.
6. Next.js reenvía cookies y encabezados al backend, que valida sesión y CSRF.

## Manejo de errores

- Si `BACKEND_URL` falta, el build debe usar el valor local `http://localhost:8000` únicamente fuera de Railway.
- Si el backend no está disponible, el proxy propagará el error HTTP al cliente.
- El healthcheck del frontend seguirá usando `/login`; el del backend seguirá usando `/health/ready`.

## Verificación

- Confirmar que frontend y backend despliegan como `Active`.
- Abrir `/login` sin errores de red.
- Iniciar sesión y comprobar que el navegador recibe `access_token`, `refresh_token` y `csrf_token` bajo el dominio del frontend.
- Ejecutar una operación POST protegida y comprobar que envía `X-CSRF-Token` y no devuelve `AUTH_CSRF_INVALID`.
- Confirmar que refresh y logout funcionan.
- Confirmar que `/health/ready` continúa devolviendo `200`.

## Fuera de alcance

- Compra o configuración de dominio propio.
- Cambio del modelo de autenticación a tokens en almacenamiento web.
- Reparación de textos con codificación dañada; se realizará como cambio independiente.
