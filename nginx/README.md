# TLS / Certificados (C-20)

El bloque HTTPS de `nginx.conf` espera dos archivos en `nginx/certs/`:

```
nginx/certs/fullchain.pem   # certificado + cadena
nginx/certs/privkey.pem     # clave privada
```

> ⚠️ Sin estos archivos, el contenedor `nginx` **no arranca**. Genera un certificado
> (autofirmado para pruebas o real con Certbot) antes de `docker compose up`.

## Opción A — Certificado autofirmado (pruebas / red interna)

Válido para probar HTTPS en LAN. El navegador mostrará una advertencia (certificado
no confiable), aceptable en entorno interno controlado.

**Con OpenSSL (Git Bash / WSL / Linux):**
```bash
mkdir -p nginx/certs
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout nginx/certs/privkey.pem \
  -out    nginx/certs/fullchain.pem \
  -subj "/CN=infra-platform.local"
```

**Con PowerShell (Windows, sin OpenSSL):**
```powershell
$cert = New-SelfSignedCertificate -DnsName "infra-platform.local" -CertStoreLocation "Cert:\CurrentUser\My"
# Exportar clave+cert a PEM requiere openssl; se recomienda usar Git Bash con el comando de arriba.
```

## Opción B — Certificado real con Certbot (producción, dominio público)

Requiere un dominio apuntando al servidor y el puerto 80 accesible.

```bash
mkdir -p nginx/certbot nginx/certs
docker run --rm \
  -v "$(pwd)/nginx/certbot:/var/www/certbot" \
  -v "$(pwd)/nginx/certs:/etc/letsencrypt/live/tu-dominio" \
  certbot/certbot certonly --webroot -w /var/www/certbot -d tu-dominio.com
```

Luego copia/enlaza `fullchain.pem` y `privkey.pem` a `nginx/certs/` y recarga Nginx:
```bash
docker compose exec nginx nginx -s reload
```

## Cabeceras de seguridad aplicadas

El bloque HTTPS añade: **HSTS** (1 año), **X-Content-Type-Options: nosniff**,
**X-Frame-Options: DENY**, **Referrer-Policy** y **Content-Security-Policy**.

Si la app se sirve con el backend en un origen distinto (no bajo `/api/` del mismo
host), añade ese origen a `connect-src` en la directiva CSP de `nginx.conf`.
