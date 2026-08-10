"""
Servidor de DESARROLLO — auth en memoria, backups con SQL Server real.
No requiere PostgreSQL ni Docker.

Arranque:
    cd backend
    pip install fastapi "uvicorn[standard]" PyJWT bcrypt python-multipart pyodbc apscheduler paramiko
    python dev_server.py
"""

import asyncio
import base64
import ftplib
import functools
import hashlib
import io
import os
import re
import secrets
import stat as _stat
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

import bcrypt
import jwt
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel

# Lógica pura extraída a módulos propios (C-11) — probada en tests/test_units.py
from sql_helpers import ENCRYPT_MAP as _ENCRYPT_MAP, safe_error as _safe_error, stripe_paths as _stripe_paths
from cleanup_rules import apply_keep_policy as _apply_keep_policy
# Limpieza remota segura (Fase 1 + 3) — validación de rutas y simulación pura.
import posixpath
import remote_cleanup
import structural_cleanup

# ── Config ────────────────────────────────────────────────────────────────────
# Seguridad (C-6): nunca operar con un SECRET_KEY conocido/por defecto — permitiría
# falsificar tokens de administrador. Si se define explícitamente un valor débil, se
# aborta el arranque. Si no se define ninguno, se genera uno aleatorio por proceso
# (seguro, pero los tokens no sobreviven a un reinicio → en producción, fija SECRET_KEY).
_WEAK_SECRETS = {"CHANGE_ME", "dev-secret-key-change-in-prod", "changeme", ""}
SECRET_KEY = os.getenv("SECRET_KEY")
if SECRET_KEY is None:
    SECRET_KEY = secrets.token_hex(32)
    print("  [WARN] SECRET_KEY no definida — usando una aleatoria de este proceso.")
    print("         Las sesiones se invalidarán al reiniciar. Define SECRET_KEY en producción:")
    print("         $env:SECRET_KEY = python -c \"import secrets; print(secrets.token_hex(32))\"")
elif SECRET_KEY in _WEAK_SECRETS:
    raise SystemExit(
        "[FATAL] SECRET_KEY inseguro/por defecto. Genera uno con:\n"
        "  python -c \"import secrets; print(secrets.token_hex(32))\"\n"
        "y expórtalo como variable de entorno SECRET_KEY antes de arrancar."
    )
ALGORITHM  = "HS256"

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Ajusta estos valores a tu SQL Server local
SQLSERVER_SERVER   = os.getenv("SQLSERVER_SERVER",   "localhost")
SQLSERVER_PORT     = int(os.getenv("SQLSERVER_PORT", "1433"))
SQLSERVER_USER     = os.getenv("SQLSERVER_USER",     "sa")
SQLSERVER_PASSWORD = os.getenv("SQLSERVER_PASSWORD", "")
SQLSERVER_DRIVER   = os.getenv("SQLSERVER_DRIVER",   "ODBC Driver 17 for SQL Server")
BACKUP_PATH        = os.getenv("SQLSERVER_BACKUP_PATH", r"C:\Backups\InfraPlatform")

# Tuning de rendimiento de backups (todo opcional vía env; valores por defecto = seguros).
#  STRIPES: nº de archivos .bak escritos en paralelo (1 hilo escritor c/u). 2-4 acelera bases grandes.
#  BUFFERCOUNT: nº de buffers de I/O. Más buffers = más throughput (a costa de algo de memoria).
BACKUP_STRIPES     = max(1, int(os.getenv("SQLSERVER_BACKUP_STRIPES", "1")))
BACKUP_BUFFERCOUNT = max(1, int(os.getenv("SQLSERVER_BACKUP_BUFFERCOUNT", "8")))
#  VERIFY: valida que el .bak sea restaurable (RESTORE VERIFYONLY). Añade tiempo de lectura;
#  ponlo en "0" si priorizas velocidad sobre la comprobación de integridad.
BACKUP_VERIFY      = os.getenv("SQLSERVER_BACKUP_VERIFY", "1") not in ("0", "false", "False")
#  Retención automática: conservar N backups por BD; 0 = deshabilitada.
BACKUP_RETENTION_KEEP      = int(os.getenv("BACKUP_RETENTION_KEEP", "0"))
BACKUP_RETENTION_EVERY_MIN = max(5, int(os.getenv("BACKUP_RETENTION_EVERY_MIN", "60")))

# Pool rápido para operaciones cortas (test conexión, listar BDs) y pool dedicado
# para backups (largos) — así un backup grande no bloquea el resto de operaciones.
# BACKUP_CONCURRENCY: nº de backups simultáneos (por defecto 4). Subir con cuidado —
# demasiados backups a la vez saturan el disco/CPU del SQL Server. Es el total del
# servicio (compartido entre todas las instancias), no por instancia.
_executor        = ThreadPoolExecutor(max_workers=8, thread_name_prefix="quick")
_backup_executor = ThreadPoolExecutor(
    max_workers=max(1, int(os.getenv("BACKUP_CONCURRENCY", "4"))),
    thread_name_prefix="backup",
)


# ── Cookies de sesión (C-5) ────────────────────────────────────────────────────
# El token se entrega en una cookie HttpOnly (no accesible por JS → mitiga robo por
# XSS). `Secure` se activa en producción (HTTPS) vía COOKIE_SECURE=1. SameSite=lax
# funciona entre localhost:3000 y :8000 (mismo sitio, distinto puerto).
COOKIE_SECURE   = os.getenv("COOKIE_SECURE", "0") not in ("0", "false", "False", "")
COOKIE_SAMESITE = os.getenv("COOKIE_SAMESITE", "lax")
ACCESS_COOKIE_MAX_AGE  = 30 * 60            # 30 min (igual que el access token)
REFRESH_COOKIE_MAX_AGE = 60 * 60 * 24 * 7   # 7 días


def _set_auth_cookies(response: Response, access: str, refresh: str | None = None) -> None:
    response.set_cookie(
        "access_token", access, max_age=ACCESS_COOKIE_MAX_AGE,
        httponly=True, secure=COOKIE_SECURE, samesite=COOKIE_SAMESITE, path="/",
    )
    if refresh is not None:
        response.set_cookie(
            "refresh_token", refresh, max_age=REFRESH_COOKIE_MAX_AGE,
            httponly=True, secure=COOKIE_SECURE, samesite=COOKIE_SAMESITE, path="/",
        )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")


# ── Auth helpers ──────────────────────────────────────────────────────────────
# auto_error=False: el token puede venir en la cabecera Authorization O en la cookie.
oauth2 = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def _get_token(request: Request, header_token: str | None = Depends(oauth2)) -> str:
    """Extrae el token del header Authorization o, en su defecto, de la cookie HttpOnly."""
    token = header_token or request.cookies.get("access_token")
    if not token:
        raise HTTPException(401, "No autenticado", headers={"WWW-Authenticate": "Bearer"})
    return token


def _hash(plain: str) -> str:
    # Devuelve str (no bytes) para que el hash sea JSON-serializable al persistir (C-7).
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def _verify(plain: str, hashed) -> bool:
    hashed_bytes = hashed.encode() if isinstance(hashed, str) else hashed
    return bcrypt.checkpw(plain.encode(), hashed_bytes)


# Blocklist de tokens revocados + rate-limit de login (C-10). Backend Redis si
# REDIS_URL está definida (compartido entre workers, con expiración); en su defecto,
# memoria de proceso.
from session_store import store as _session_store


def _token(sub: str, kind: str, minutes: int) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    return jwt.encode(
        {"sub": sub, "type": kind, "exp": exp, "jti": str(uuid.uuid4())},
        SECRET_KEY, ALGORITHM,
    )


def _decode(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expirado")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Token inválido")
    if _session_store.is_revoked(payload.get("jti")):
        raise HTTPException(401, "Token revocado")
    return payload


# ── In-memory stores ──────────────────────────────────────────────────────────
TENANT_ID = str(uuid.uuid4())

USERS: dict[str, dict] = {
    "admin@primee.local": {
        "id":             str(uuid.uuid4()),
        "tenant_id":      TENANT_ID,
        "email":          "admin@primee.local",
        "username":       "admin",
        "full_name":      "Administrador PRIMEE",
        "role":           "admin",
        "is_active":      True,
        "hashed_password": _hash("Admin1234!"),
    }
}

BACKUPS: dict[str, dict] = {}          # backup_id -> backup dict
ACCESS_SESSIONS: dict[str, dict] = {}  # session_id -> session dict

# Rate-limiting de login: máx N intentos fallidos por usuario dentro de una ventana.
# El estado vive en el session_store (Redis o memoria) — compartible entre workers.
_LOGIN_MAX_FAILS = int(os.getenv("LOGIN_MAX_FAILS", "5"))
_LOGIN_WINDOW    = float(os.getenv("LOGIN_FAIL_WINDOW_SEC", "300"))


def _login_recent_fails(username: str) -> int:
    return _session_store.recent_login_fails(username, _LOGIN_WINDOW)


def _login_record_fail(username: str) -> None:
    _session_store.record_login_fail(username, _LOGIN_WINDOW)


def _current_user(token: str = Depends(_get_token)) -> dict:
    payload = _decode(token)
    if payload.get("type") != "access":
        raise HTTPException(401, "Tipo de token inválido")
    user = next((u for u in USERS.values() if u["id"] == payload["sub"]), None)
    if not user or not user["is_active"]:
        raise HTTPException(401, "Usuario no encontrado")
    return user


def _require_role(*roles: str):
    """Dependency factory: exige que el usuario tenga uno de los roles indicados."""
    def _dep(user: dict = Depends(_current_user)) -> dict:
        if user["role"] not in roles:
            raise HTTPException(403, "Permisos insuficientes para esta operación")
        return user
    return _dep


# Rutas base permitidas para operaciones LOCALES de archivos (File Manager).
# Si FM_ALLOWED_ROOTS está vacío, se permite navegar el host pero SIEMPRE se bloquean
# raíces de disco y directorios críticos del sistema (red de seguridad anti-borrado masivo).
_ALLOWED_LOCAL_ROOTS = [
    Path(p.strip()).resolve()
    for p in os.getenv("FM_ALLOWED_ROOTS", "").split(";")
    if p.strip()
]
_FORBIDDEN_LOCAL_PATHS = {
    Path(p).resolve()
    for p in (r"C:\Windows", r"C:\Program Files", r"C:\Program Files (x86)",
              r"C:\Users", "/", "/etc", "/boot", "/usr", "/bin", "/sys", "/proc")
}


def _ensure_local_path_allowed(raw_path: str) -> Path:
    """Resuelve raw_path y valida que sea seguro operar sobre él. Bloquea path traversal,
    raíces de disco y directorios de sistema. Devuelve la ruta resuelta."""
    try:
        resolved = Path(raw_path).resolve()
    except Exception:
        raise HTTPException(400, "Ruta inválida")

    # Seguridad (C-4): la allowlist es OBLIGATORIA (fail-closed). Sin FM_ALLOWED_ROOTS
    # configurada se DENIEGA toda operación local, en lugar de permitir navegar/borrar
    # casi todo el host. Evita borrados masivos accidentales o maliciosos.
    if not _ALLOWED_LOCAL_ROOTS:
        raise HTTPException(
            403,
            "Operaciones de archivos locales deshabilitadas: configure la variable de "
            "entorno FM_ALLOWED_ROOTS (rutas separadas por ';') para habilitarlas.",
        )

    # Bloquear raíces de disco (C:\, D:\, /) y directorios críticos (defensa adicional)
    if resolved.parent == resolved or resolved in _FORBIDDEN_LOCAL_PATHS:
        raise HTTPException(403, f"Operación no permitida sobre ruta protegida: {resolved}")

    # Exigir que la ruta esté contenida en alguna raíz permitida
    for root in _ALLOWED_LOCAL_ROOTS:
        try:
            resolved.relative_to(root)
            return resolved
        except ValueError:
            continue
    raise HTTPException(403, f"Ruta fuera de las carpetas permitidas: {raw_path}")


# ── SQL Server helpers ────────────────────────────────────────────────────────
# _ENCRYPT_MAP, _safe_error y _stripe_paths viven ahora en sql_helpers.py (C-11).

@functools.lru_cache(maxsize=1)
def _detect_driver() -> str:
    """Return the best available ODBC driver name (cacheado: los drivers no cambian en runtime)."""
    try:
        import pyodbc
        for name in pyodbc.drivers():
            if "SQL Server" in name:
                for pref in ("ODBC Driver 18", "ODBC Driver 17", "ODBC Driver 13"):
                    if name.startswith(pref):
                        return name
        # fallback: first driver that mentions SQL Server
        for name in pyodbc.drivers():
            if "SQL Server" in name:
                return name
    except Exception:
        pass
    return SQLSERVER_DRIVER


def _conn_str(
    server:     str | None = None,
    username:   str | None = None,
    password:   str | None = None,
    database:   str | None = None,
    trust_cert: bool = True,
    encrypt:    str  = "yes",
) -> str:
    srv = server   or f"{SQLSERVER_SERVER},{SQLSERVER_PORT}"
    usr = username or SQLSERVER_USER
    pwd = password or SQLSERVER_PASSWORD
    db  = database or "master"
    tc  = "yes" if trust_cert else "no"
    enc = _ENCRYPT_MAP.get((encrypt or "yes").lower(), "yes")
    drv = _detect_driver()
    return (
        f"DRIVER={{{drv}}};"
        f"SERVER={srv};"
        f"DATABASE={db};"
        f"UID={usr};"
        f"PWD={pwd};"
        f"TrustServerCertificate={tc};"
        f"Encrypt={enc};"
    )


# Cache TTL corto del listado de bases por conexión — evita reabrir conexión en
# llamadas repetidas (p. ej. refrescos del dropdown). La contraseña NO forma parte de la clave.
_DBS_CACHE: dict[tuple, tuple[float, list[str]]] = {}
_DBS_TTL   = 15.0  # segundos


def _sync_list_dbs(
    server: str | None = None,
    username: str | None = None,
    password: str | None = None,
    trust_cert: bool = True,
    encrypt: str = "yes",
    **_: object,   # ignore extra keys like database
) -> list[str]:
    import pyodbc
    key = (server or f"{SQLSERVER_SERVER},{SQLSERVER_PORT}", username or SQLSERVER_USER, encrypt)
    cached = _DBS_CACHE.get(key)
    if cached and (time.monotonic() - cached[0]) < _DBS_TTL:
        return cached[1]

    cs = _conn_str(server=server, username=username, password=password,
                   trust_cert=trust_cert, encrypt=encrypt)
    with pyodbc.connect(cs, timeout=8) as cn:
        cur = cn.execute(
            "SELECT name FROM sys.databases "
            "WHERE database_id > 4 AND state_desc = 'ONLINE' ORDER BY name"
        )
        dbs = [r[0] for r in cur.fetchall()]
    _DBS_CACHE[key] = (time.monotonic(), dbs)
    return dbs


def _sync_backup(backup_id: str, db_name: str, backup_type: str, dest_path: str,
                 conn_kwargs: dict | None = None, local_path: str = "",
                 dated_folder: bool = True, nas_path: str = ""):
    import pyodbc

    BACKUPS[backup_id]["status"] = "running"
    BACKUPS[backup_id]["startedAt"] = datetime.now(timezone.utc).isoformat()

    # Opciones seguras en todas las ediciones:
    #  - CHECKSUM: verifica integridad de páginas al respaldar
    #  - BUFFERCOUNT/MAXTRANSFERSIZE: aceleran el I/O en bases grandes
    base_opts = (f"FORMAT, INIT, CHECKSUM, STATS=10, "
                 f"BUFFERCOUNT={BACKUP_BUFFERCOUNT}, MAXTRANSFERSIZE=4194304")
    verb      = "BACKUP LOG" if backup_type == "log" else "BACKUP DATABASE"
    diff      = "DIFFERENTIAL, " if backup_type == "differential" else ""
    msdb_type = {"full": "D", "differential": "I", "log": "L"}.get(backup_type, "D")

    def _build_sql(paths: list[str], compression: bool) -> str:
        comp        = "COMPRESSION, " if compression else ""
        disk_clause = ", ".join(["DISK = ?"] * len(paths))
        return f"{verb} [{db_name}] TO {disk_clause} WITH {comp}{diff}{base_opts}"

    cs = _conn_str(**(conn_kwargs or {}))
    try:
        with pyodbc.connect(cs, timeout=0, autocommit=True) as cn:
            # ── Resolución de destino(s) ──────────────────────────────────────
            # El .bak lo escribe el SQL Server, así que las rutas deben ser accesibles
            # POR ÉL (disco local o UNC \\nas\share con permisos de la cuenta de servicio).
            # Destino principal: `local_path` (si se indica) o la carpeta de backup por
            # defecto de la instancia. Opcional: `nas_path` como 2ª copia completa.
            # `dated_folder` crea/usa una subcarpeta con la fecha (BACKUP no crea carpetas,
            # por eso se usa xp_create_subdir, que crea también los padres).
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            filename = Path(dest_path).name

            def _instance_backup_dir() -> str:
                try:
                    row = cn.execute(
                        "EXEC master.dbo.xp_instance_regread "
                        "N'HKEY_LOCAL_MACHINE', "
                        "N'Software\\Microsoft\\MSSQLServer\\MSSQLServer', "
                        "N'BackupDirectory'"
                    ).fetchone()
                    if row:
                        return str(row[1]).rstrip("\\")
                except Exception:
                    pass
                return str(Path(dest_path).parent)

            def _resolve_dir(custom: str) -> str:
                base = (custom or "").strip().rstrip("\\/") or _instance_backup_dir()
                if dated_folder:
                    base = f"{base}\\{date_str}"
                try:
                    cn.execute("EXEC master.dbo.xp_create_subdir ?", base)  # crea carpeta + padres
                except Exception:
                    pass
                return base

            target_files = [f"{_resolve_dir(local_path)}\\{filename}"]
            if (nas_path or "").strip():
                target_files.append(f"{_resolve_dir(nas_path)}\\{filename}")

            # Backup a cada destino (copia completa e independiente). Compresión con
            # fallback si la edición no la soporta. La verificación y el tamaño usan el
            # destino principal.
            paths = _stripe_paths(target_files[0], BACKUP_STRIPES)
            for tgt in target_files:
                tpaths = _stripe_paths(tgt, BACKUP_STRIPES)
                try:
                    cn.execute(_build_sql(tpaths, True), *tpaths)
                except pyodbc.Error as exc:
                    if "compress" in str(exc).lower():
                        cn.execute(_build_sql(tpaths, False), *tpaths)
                    else:
                        raise

            # Verificar que el backup sea restaurable (integridad real, no solo escrito).
            verified = None
            verify_error = None
            if BACKUP_VERIFY:
                try:
                    disk_clause = ", ".join(["DISK = ?"] * len(paths))
                    cn.execute(f"RESTORE VERIFYONLY FROM {disk_clause} WITH CHECKSUM", *paths)
                    verified = True
                except Exception as vexc:
                    verified = False
                    verify_error = _safe_error(vexc)

            # Tamaño real leído del PROPIO .bak con RESTORE HEADERONLY. Antes se leía de
            # msdb.dbo.backupset, pero esa tabla puede no registrar la corrida (según
            # permisos/estado del historial de la instancia) → devolvía 0. HEADERONLY lee
            # el encabezado del archivo recién escrito, así que es fiable siempre.
            size = 0
            try:
                disk_clause = ", ".join(["DISK = ?"] * len(paths))
                hcur = cn.execute(f"RESTORE HEADERONLY FROM {disk_clause}", *paths)
                hcols = [d[0] for d in hcur.description]
                for hrow in hcur.fetchall():
                    hd = dict(zip(hcols, hrow))
                    val = hd.get("CompressedBackupSize") or hd.get("BackupSize") or 0
                    size += int(val or 0)
            except Exception:
                size = 0

        # Si la verificación falló, el backup no es de fiar → marcarlo como fallido.
        BACKUPS[backup_id].update({
            "status":        "failed" if verified is False else "completed",
            "filePath":      "; ".join(target_files),
            "targets":       target_files,
            "stripeCount":   len(paths),
            "fileSizeBytes": size,
            "sha256Hash":    None,
            "verified":      verified,
            "finishedAt":    datetime.now(timezone.utc).isoformat(),
            "errorMessage":  f"Backup escrito pero la verificación falló: {verify_error}"
                             if verified is False else None,
        })
    except Exception as exc:
        BACKUPS[backup_id].update({
            "status":       "failed",
            "errorMessage": _safe_error(exc),
            "finishedAt":   datetime.now(timezone.utc).isoformat(),
        })


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="Infra Platform — DEV", version="dev", docs_url="/docs")
# CORS endurecido (C-9): orígenes por variable de entorno, métodos y cabeceras
# acotados a lo que la app usa (no comodines con credenciales).
_ALLOWED_ORIGINS = [
    o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# ── Auth ──────────────────────────────────────────────────────────────────────
class LoginResponse(BaseModel):
    authenticated: bool
    access_token: str | None = None
    refresh_token: str | None = None


class RegisterBody(BaseModel):
    full_name: str
    email:     str
    password:  str
    role:      str = "technician"


_VALID_ROLES = {"admin", "technician", "supervisor", "client"}


# Seguridad (C-3): la creación de cuentas es una operación de administración, NO un
# registro público. Sin este control, cualquiera con acceso de red al backend (que
# escucha en 0.0.0.0) podría crearse una cuenta activa. Se exige rol admin.
@app.post("/api/v1/auth/register", status_code=201)
def register(body: RegisterBody, _=Depends(_require_role("admin"))):
    if not _EMAIL_RE.match(body.email.strip()):
        raise HTTPException(400, "Formato de correo inválido")
    if body.email in USERS:
        raise HTTPException(400, "El correo ya está registrado")
    if len(body.password) < 8:
        raise HTTPException(400, "La contraseña debe tener al menos 8 caracteres")
    if body.role not in _VALID_ROLES:
        raise HTTPException(400, f"Rol inválido. Debe ser uno de: {', '.join(sorted(_VALID_ROLES))}")
    USERS[body.email] = {
        "id":              str(uuid.uuid4()),
        "tenant_id":       TENANT_ID,
        "email":           body.email,
        "username":        body.email.split("@")[0],
        "full_name":       body.full_name,
        "role":            body.role,
        "is_active":       True,
        "hashed_password": _hash(body.password),
    }
    return {"message": "Cuenta creada exitosamente"}


@app.post("/api/v1/auth/login", response_model=LoginResponse)
def login(response: Response, form: OAuth2PasswordRequestForm = Depends()):
    if _login_recent_fails(form.username) >= _LOGIN_MAX_FAILS:
        raise HTTPException(429, "Demasiados intentos fallidos. Espera unos minutos e inténtalo de nuevo.")
    user = USERS.get(form.username)
    ok   = _verify(form.password, user["hashed_password"]) if user else False
    if not user or not ok:
        _login_record_fail(form.username)
        raise HTTPException(401, "Credenciales inválidas", headers={"WWW-Authenticate": "Bearer"})
    if not user["is_active"]:
        raise HTTPException(403, "Cuenta desactivada")
    _session_store.reset_login_fails(form.username)  # login correcto → limpiar contador
    access  = _token(user["id"], "access",  30)
    refresh = _token(user["id"], "refresh", 60 * 24 * 7)
    _set_auth_cookies(response, access, refresh)   # cookies HttpOnly (C-5)
    return LoginResponse(authenticated=True, access_token=access, refresh_token=refresh)


@app.post("/api/v1/auth/refresh")
def refresh(request: Request, response: Response, body: dict | None = None):
    # El refresh token viaja en cookie HttpOnly (C-5/C-14); se admite el body como
    # respaldo para compatibilidad. Emite un nuevo access token y renueva la cookie.
    refresh_token = request.cookies.get("refresh_token") or (body or {}).get("refresh_token")
    if not refresh_token:
        raise HTTPException(401, "Falta refresh_token")
    p = _decode(refresh_token)
    if p.get("type") != "refresh":
        raise HTTPException(401, "Token inválido")
    access = _token(p["sub"], "access", 30)
    _set_auth_cookies(response, access)
    return {"access_token": access, "token_type": "bearer"}


@app.post("/api/v1/auth/logout")
def logout(response: Response, token: str = Depends(_get_token)):
    payload = _decode(token)
    jti = payload.get("jti")
    if jti:
        # TTL = tiempo restante del token, para que la blocklist expire sola en Redis.
        ttl = max(0, int(payload.get("exp", 0) - time.time()))
        _session_store.revoke(jti, ttl_seconds=ttl or REFRESH_COOKIE_MAX_AGE)
    _clear_auth_cookies(response)
    return {"message": "Sesión cerrada"}


@app.get("/api/v1/auth/me")
def me(user=Depends(_current_user)):
    return {k: v for k, v in {
        "id": user["id"], "tenantId": user["tenant_id"], "email": user["email"],
        "username": user["username"], "fullName": user["full_name"],
        "role": user["role"], "isActive": user["is_active"],
    }.items()}


# ── Users ─────────────────────────────────────────────────────────────────────
@app.get("/api/v1/users")
def list_users(_=Depends(_current_user)):
    safe = [{k: v for k, v in u.items() if k != "hashed_password"} for u in USERS.values()]
    return {"items": safe, "total": len(safe)}


# ── Connections ───────────────────────────────────────────────────────────────
class ConnectionBody(BaseModel):
    server:     str
    username:   str  = "sa"
    password:   str  = ""
    database:   str | None = None
    encrypt:    str  = "mandatory"
    trust_cert: bool = True

    def as_kwargs(self) -> dict:
        return {
            "server":     self.server,
            "username":   self.username,
            "password":   self.password,
            "database":   self.database,
            "encrypt":    self.encrypt,
            "trust_cert": self.trust_cert,
        }


@app.post("/api/v1/connections/test")
async def test_connection(body: ConnectionBody, _=Depends(_current_user)):
    loop = asyncio.get_event_loop()
    try:
        dbs = await loop.run_in_executor(
            _executor, lambda: _sync_list_dbs(**body.as_kwargs())
        )
        return {"connected": True, "databases": dbs}
    except Exception as exc:
        return {"connected": False, "databases": [], "error": _safe_error(exc)}


@app.post("/api/v1/connections/databases")
async def databases_for_connection(body: ConnectionBody, _=Depends(_current_user)):
    loop = asyncio.get_event_loop()
    try:
        dbs = await loop.run_in_executor(
            _executor, lambda: _sync_list_dbs(**body.as_kwargs())
        )
        return {"connected": True, "databases": dbs}
    except Exception as exc:
        return {"connected": False, "databases": [], "error": _safe_error(exc)}


# ── Backups ───────────────────────────────────────────────────────────────────
class TriggerBackupBody(BaseModel):
    database_name:  str = ""
    database_names: list[str] = []
    backup_type:    Literal["full", "differential", "log"] = "full"
    destination:    str = "local"   # etiqueta informativa; el destino real va en local_path/nas_path
    # Destino real (lo escribe el SQL Server; rutas accesibles POR ÉL):
    local_path:     str = ""       # base en el SQL Server; vacío = carpeta de backup por defecto
    dated_folder:   bool = True    # crear/usar subcarpeta con la fecha (YYYY-MM-DD)
    nas_path:       str = ""       # UNC opcional (\\servidor\share\...) para una 2ª copia completa
    connection:     ConnectionBody | None = None


@app.get("/api/v1/backups")
def list_backups(_=Depends(_current_user)):
    items = sorted(BACKUPS.values(), key=lambda b: b["createdAt"], reverse=True)
    return {"items": items, "total": len(items)}


@app.get("/api/v1/backups/databases")
async def list_databases(_=Depends(_current_user)):
    loop = asyncio.get_event_loop()
    try:
        dbs = await loop.run_in_executor(_executor, _sync_list_dbs)
        return {"databases": dbs, "connected": True}
    except Exception as exc:
        return {"databases": [], "connected": False, "error": _safe_error(exc)}


@app.post("/api/v1/backups/manual", status_code=202)
async def trigger_backup(body: TriggerBackupBody, user=Depends(_current_user)):
    names = body.database_names if body.database_names else ([body.database_name] if body.database_name else [])
    names = [n for n in names if re.match(r"^[A-Za-z0-9_\-\.]{1,128}$", n)]
    if not names:
        raise HTTPException(400, "Nombre de base de datos inválido")

    conn_kwargs = body.connection.as_kwargs() if body.connection else None
    loop       = asyncio.get_event_loop()
    results    = []

    for db_name in names:
        backup_id = str(uuid.uuid4())
        ts        = datetime.now(timezone.utc)
        ext       = ".trn" if body.backup_type == "log" else ".bak"
        filename  = f"{db_name}_{body.backup_type.upper()}_{ts.strftime('%Y%m%d_%H%M%S')}{ext}"
        dest_path = str(Path(BACKUP_PATH) / filename)

        BACKUPS[backup_id] = {
            "id":            backup_id,
            "databaseName":  db_name,
            "backupType":    body.backup_type,
            "status":        "pending",
            "destination":   body.destination,
            "filePath":      None,
            "fileSizeBytes": None,
            "sha256Hash":    None,
            "errorMessage":  None,
            "startedAt":     None,
            "finishedAt":    None,
            "durationSecs":  None,
            "createdAt":     ts.isoformat(),
            "createdById":   user["id"],
            "createdBy":     user["full_name"],
        }

        loop.run_in_executor(
            _backup_executor, _sync_backup,
            backup_id, db_name, body.backup_type, dest_path, conn_kwargs,
            body.local_path, body.dated_folder, body.nas_path,
        )
        results.append(BACKUPS[backup_id])

    return {"backups": results}


@app.get("/api/v1/backups/{backup_id}/status")
def backup_status(backup_id: str, _=Depends(_current_user)):
    b = BACKUPS.get(backup_id)
    if not b:
        raise HTTPException(404, "Backup no encontrado")
    # Compute duration
    if b.get("startedAt") and b.get("finishedAt"):
        start = datetime.fromisoformat(b["startedAt"])
        end   = datetime.fromisoformat(b["finishedAt"])
        b["durationSecs"] = int((end - start).total_seconds())
    return b


@app.delete("/api/v1/backups/{backup_id}")
def delete_backup(backup_id: str, _=Depends(_require_role("admin"))):
    if backup_id not in BACKUPS:
        raise HTTPException(404, "Backup no encontrado")
    BACKUPS.pop(backup_id)
    return {"deleted": backup_id}

@app.delete("/api/v1/backups/purge")
def purge_backups(body: dict, _=Depends(_require_role("admin"))):
    db_name = body.get("database_name", "")
    keep = int(body.get("keep_count", 10))
    completed = sorted(
        [b for b in BACKUPS.values() if b["databaseName"] == db_name and b["status"] == "completed"],
        key=lambda b: b["createdAt"],
    )
    # keep <= 0 → borrar todos; si no, conservar los `keep` más recientes
    to_delete = completed if keep <= 0 else completed[:-keep]
    for b in to_delete:
        BACKUPS.pop(b["id"], None)
    return {"deleted": len(to_delete)}


@app.get("/api/v1/backups/schedules")
def list_schedules(_=Depends(_current_user)):
    return {"items": [], "total": 0}


# ── Cleanup ───────────────────────────────────────────────────────────────────
import fnmatch, shutil, tempfile

CLEANUP_FOLDERS:   dict[str, dict] = {}
CLEANUP_RULES:     dict[str, dict] = {}
CLEANUP_TRASH:     dict[str, dict] = {}
CLEANUP_HISTORY:   list[dict]      = []
CLEANUP_SCHEDULES: dict[str, dict] = {}
TRASH_DIR = Path(tempfile.gettempdir()) / "infra_platform_trash"
TRASH_DIR.mkdir(parents=True, exist_ok=True)


def _scan_folder(folder_path: str, rules: list[dict]) -> list[dict]:
    """Return files in folder_path that match any of the given rules."""
    results = []
    base = Path(folder_path)
    if not base.exists():
        return results
    for f in base.rglob("*"):
        if not f.is_file():
            continue
        for rule in rules:
            patterns  = rule.get("patterns", ["*"])
            exts      = [e.lower() for e in rule.get("extensions", [])]
            matched_p = any(fnmatch.fnmatch(f.name, p) for p in patterns)
            matched_e = not exts or f.suffix.lower() in exts
            if matched_p and matched_e:
                stat = f.stat()
                age  = (datetime.now(timezone.utc).timestamp() - stat.st_mtime) / 86400
                results.append({
                    "id":           str(uuid.uuid4()),
                    "name":         f.name,
                    "path":         str(f),
                    "relativePath": str(f.relative_to(base)),
                    "sizeBytes":    stat.st_size,
                    "modifiedAt":   datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                    "ageDays":      round(age, 1),
                    "ruleId":       rule["id"],
                    "ruleName":     rule.get("name", ""),
                    "folderId":     rule.get("folderId", ""),
                })
                break  # one rule match per file
    return results


# _apply_keep_policy vive ahora en cleanup_rules.py (C-11).


# ── Folders ───────────────────────────────────────────────────────────────────
class FolderBody(BaseModel):
    path:    str
    label:   str = ""
    enabled: bool = True


@app.get("/api/v1/cleanup/folders")
def list_cleanup_folders(_=Depends(_current_user)):
    items = list(CLEANUP_FOLDERS.values())
    for f in items:
        f["exists"] = Path(f["path"]).exists()
    return {"items": items, "total": len(items)}


@app.post("/api/v1/cleanup/folders", status_code=201)
def add_cleanup_folder(body: FolderBody, _=Depends(_current_user)):
    fid = str(uuid.uuid4())
    folder = {
        "id":        fid,
        "path":      body.path,
        "label":     body.label or Path(body.path).name,
        "enabled":   body.enabled,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "exists":    Path(body.path).exists(),
    }
    CLEANUP_FOLDERS[fid] = folder
    return folder


@app.delete("/api/v1/cleanup/folders/{folder_id}", status_code=204)
def delete_cleanup_folder(folder_id: str, _=Depends(_current_user)):
    CLEANUP_FOLDERS.pop(folder_id, None)


# ── Rules ─────────────────────────────────────────────────────────────────────
class RuleBody(BaseModel):
    name:       str
    folderId:   str | None = None
    patterns:   list[str] = ["*BCK*"]
    extensions: list[str] = []
    keep:       str = "latest"    # latest | latest_n | none | all
    keepN:      int = 1
    minAgeDays: float = 0
    enabled:    bool = True


@app.get("/api/v1/cleanup/rules")
def list_cleanup_rules(_=Depends(_current_user)):
    return {"items": list(CLEANUP_RULES.values()), "total": len(CLEANUP_RULES)}


@app.post("/api/v1/cleanup/rules", status_code=201)
def create_cleanup_rule(body: RuleBody, _=Depends(_current_user)):
    rid = str(uuid.uuid4())
    rule = {
        "id":         rid,
        "name":       body.name,
        "folderId":   body.folderId,
        "patterns":   body.patterns,
        "extensions": body.extensions,
        "keep":       body.keep,
        "keepN":      body.keepN,
        "minAgeDays": body.minAgeDays,
        "enabled":    body.enabled,
        "createdAt":  datetime.now(timezone.utc).isoformat(),
    }
    CLEANUP_RULES[rid] = rule
    return rule


@app.put("/api/v1/cleanup/rules/{rule_id}")
def update_cleanup_rule(rule_id: str, body: RuleBody, _=Depends(_current_user)):
    if rule_id not in CLEANUP_RULES:
        raise HTTPException(404, "Regla no encontrada")
    CLEANUP_RULES[rule_id].update(body.model_dump())
    return CLEANUP_RULES[rule_id]


@app.delete("/api/v1/cleanup/rules/{rule_id}", status_code=204)
def delete_cleanup_rule(rule_id: str, _=Depends(_current_user)):
    CLEANUP_RULES.pop(rule_id, None)


# ── Scan ──────────────────────────────────────────────────────────────────────
@app.get("/api/v1/cleanup/scan")
def scan_cleanup(_=Depends(_current_user), folder_id: str | None = None):
    folders = [f for f in CLEANUP_FOLDERS.values() if f["enabled"]]
    if folder_id:
        folders = [f for f in folders if f["id"] == folder_id]

    rules = [r for r in CLEANUP_RULES.values() if r["enabled"]]

    all_files: list[dict] = []
    for folder in folders:
        folder_rules = [r for r in rules if not r["folderId"] or r["folderId"] == folder["id"]]
        if not folder_rules:
            continue
        found = _scan_folder(folder["path"], folder_rules)
        all_files.extend(found)

    # Apply keep policy per rule group
    eligible: list[dict] = []
    for rule in rules:
        rule_files = [f for f in all_files if f["ruleId"] == rule["id"]]
        eligible.extend(_apply_keep_policy(rule_files, rule))

    total_bytes = sum(f["sizeBytes"] for f in eligible)
    return {
        "files":       eligible,
        "total":       len(eligible),
        "totalBytes":  total_bytes,
        "scannedAt":   datetime.now(timezone.utc).isoformat(),
    }


# ── Execute cleanup ───────────────────────────────────────────────────────────
class ExecuteCleanupBody(BaseModel):
    file_paths: list[str]
    rule_id:    str | None = None


def _path_under_configured_folder(resolved: Path) -> bool:
    """True si `resolved` está dentro de alguna carpeta de limpieza registrada."""
    for folder in CLEANUP_FOLDERS.values():
        try:
            resolved.relative_to(Path(folder["path"]).resolve())
            return True
        except (ValueError, OSError):
            continue
    return False


@app.post("/api/v1/cleanup/execute")
def execute_cleanup(body: ExecuteCleanupBody, _=Depends(_current_user)):
    moved = []
    errors = []
    bytes_freed = 0
    for fp in body.file_paths:
        try:
            src = Path(fp).resolve()
        except Exception:
            errors.append({"path": fp, "error": "Ruta inválida"})
            continue
        # Solo se pueden limpiar archivos DENTRO de carpetas configuradas
        if not _path_under_configured_folder(src):
            errors.append({"path": fp, "error": "Ruta fuera de las carpetas de limpieza configuradas"})
            continue
        if not src.is_file():
            errors.append({"path": fp, "error": "Archivo no encontrado"})
            continue
        try:
            dest = TRASH_DIR / f"{uuid.uuid4()}_{src.name}"
            shutil.move(str(src), str(dest))
            tid  = str(uuid.uuid4())
            size = dest.stat().st_size
            bytes_freed += size
            entry = {
                "id":           tid,
                "name":         src.name,
                "originalPath": fp,
                "trashPath":    str(dest),
                "sizeBytes":    size,
                "ruleId":       body.rule_id,
                "deletedAt":    datetime.now(timezone.utc).isoformat(),
            }
            CLEANUP_TRASH[tid] = entry
            moved.append(entry)
        except Exception as exc:
            errors.append({"path": fp, "error": str(exc)})

    # Record history
    if moved:
        CLEANUP_HISTORY.insert(0, {
            "id":          str(uuid.uuid4()),
            "filesDeleted": len(moved),
            "bytesFreed":  bytes_freed,
            "errors":      len(errors),
            "executedAt":  datetime.now(timezone.utc).isoformat(),
            "status":      "completed" if not errors else "partial",
        })

    return {"moved": len(moved), "errors": errors, "bytesFreed": bytes_freed}


# ── Trash ─────────────────────────────────────────────────────────────────────
@app.get("/api/v1/cleanup/trash")
def list_trash(_=Depends(_current_user)):
    items = sorted(CLEANUP_TRASH.values(), key=lambda x: x["deletedAt"], reverse=True)
    return {"items": items, "total": len(items)}


@app.delete("/api/v1/cleanup/trash/{item_id}", status_code=204)
def permanent_delete(item_id: str, _=Depends(_require_role("admin"))):
    item = CLEANUP_TRASH.pop(item_id, None)
    if item:
        tp = Path(item["trashPath"])
        if tp.exists():
            tp.unlink()


@app.post("/api/v1/cleanup/restore/{item_id}")
def restore_from_trash(item_id: str, _=Depends(_current_user)):
    item = CLEANUP_TRASH.get(item_id)
    if not item:
        raise HTTPException(404, "Elemento no encontrado en papelera")
    src  = Path(item["trashPath"])
    dest = Path(item["originalPath"])
    if not src.exists():
        raise HTTPException(410, "El archivo en papelera ya no existe")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dest))
    CLEANUP_TRASH.pop(item_id)
    return {"restored": str(dest)}


# ── History ───────────────────────────────────────────────────────────────────
@app.get("/api/v1/cleanup/history")
def cleanup_history(_=Depends(_current_user), skip: int = 0, limit: int = 50):
    page = CLEANUP_HISTORY[skip: skip + limit]
    return {"items": page, "total": len(CLEANUP_HISTORY)}


# ── Schedules (stub for dev) ───────────────────────────────────────────────────
class CleanupScheduleBody(BaseModel):
    name:       str
    folderId:   str
    ruleId:     str
    cronExpr:   str = "0 2 * * *"
    enabled:    bool = True


@app.get("/api/v1/cleanup/schedules")
def list_cleanup_schedules(_=Depends(_current_user)):
    return {"items": list(CLEANUP_SCHEDULES.values()), "total": len(CLEANUP_SCHEDULES)}


@app.post("/api/v1/cleanup/schedules", status_code=201)
def create_cleanup_schedule(body: CleanupScheduleBody, _=Depends(_current_user)):
    sid = str(uuid.uuid4())
    sched = {
        "id":        sid,
        "name":      body.name,
        "folderId":  body.folderId,
        "ruleId":    body.ruleId,
        "cronExpr":  body.cronExpr,
        "enabled":   body.enabled,
        "lastRun":   None,
        "nextRun":   None,
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }
    CLEANUP_SCHEDULES[sid] = sched
    return sched


@app.put("/api/v1/cleanup/schedules/{sched_id}")
def update_cleanup_schedule(sched_id: str, body: CleanupScheduleBody, _=Depends(_current_user)):
    if sched_id not in CLEANUP_SCHEDULES:
        raise HTTPException(404, "Programación no encontrada")
    CLEANUP_SCHEDULES[sched_id].update(body.model_dump())
    return CLEANUP_SCHEDULES[sched_id]


@app.delete("/api/v1/cleanup/schedules/{sched_id}", status_code=204)
def delete_cleanup_schedule(sched_id: str, _=Depends(_current_user)):
    CLEANUP_SCHEDULES.pop(sched_id, None)


# ── Dashboard ─────────────────────────────────────────────────────────────────
@app.get("/api/v1/dashboard/summary")
def dashboard_summary(_=Depends(_current_user)):
    today_str       = datetime.now(_LOCAL_TZ).date().isoformat()
    completed_today = sum(1 for b in BACKUPS.values() if b["status"] == "completed" and (b.get("startedAt") or "")[:10] == today_str)
    failed          = sum(1 for b in BACKUPS.values() if b["status"] == "failed")
    active_sessions = sum(1 for s in ACCESS_SESSIONS.values() if s["status"] == "active")
    suspicious      = sum(1 for s in ACCESS_SESSIONS.values() if s["is_suspicious"] and s["status"] == "closed")
    return {
        "backups_today":    completed_today,
        "failed_backups":   failed,
        "active_sessions":  active_sessions,
        "critical_alerts":  failed + suspicious,
    }

@app.get("/api/v1/dashboard/backup-chart")
def backup_chart(_=Depends(_current_user)):
    from collections import defaultdict
    days: dict[str, dict] = defaultdict(lambda: {"completed": 0, "failed": 0, "running": 0})
    for b in BACKUPS.values():
        day = (b.get("startedAt") or b.get("createdAt") or "")[:10]
        if day:
            days[day][b["status"] if b["status"] in ("completed", "failed") else "running"] += 1
    result = [{"date": d, **v} for d, v in sorted(days.items())[-14:]]
    return {"chart": result}

@app.get("/api/v1/dashboard/activity")
def dashboard_activity(_=Depends(_current_user)):
    events = []
    for b in BACKUPS.values():
        events.append({
            "id":    b["id"],
            "kind":  "backup",
            "label": f'Backup — {b["databaseName"]}',
            "status": b["status"],
            "ts":    b.get("startedAt") or b.get("createdAt") or "",
        })
    for s in ACCESS_SESSIONS.values():
        events.append({
            "id":    s["id"],
            "kind":  "access",
            "label": f'Acceso — {s["server"]} ({s.get("engineer") or s["user"]})',
            "status": "alert" if s["is_suspicious"] else s["status"],
            "ts":    s["start"],
        })
    events.sort(key=lambda e: e["ts"], reverse=True)
    return {"activity": events[:10]}


@app.get("/health")
def health():
    return {"status": "ok", "mode": "development", "db": "in-memory", "sqlserver": SQLSERVER_SERVER}


# ── Access Sessions ───────────────────────────────────────────────────────────
import json as _json

ACCESS_LOG_FILE = Path(__file__).parent / "access_sessions.log"

def _load_log() -> None:
    """Load closed sessions from the .log file into ACCESS_SESSIONS on startup."""
    if not ACCESS_LOG_FILE.exists():
        return
    with open(ACCESS_LOG_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                s = _json.loads(line)
                ACCESS_SESSIONS[s["id"]] = s
            except Exception:
                pass

def _append_log(session: dict) -> None:
    """Append a closed session as a JSON line to the .log file."""
    with open(ACCESS_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(_json.dumps(session, ensure_ascii=False) + "\n")

_load_log()

class CreateSessionBody(BaseModel):
    server:   str
    ip:       str = ""
    tool:     str = "RDP"
    reason:   str = ""
    client:   str = ""
    engineer: str = ""

class CloseSessionBody(BaseModel):
    notes: str = ""

_LOCAL_TZ = timezone(timedelta(hours=-6))  # UTC-6 Mexico City

def _is_suspicious(session: dict) -> bool:
    start = datetime.fromisoformat(session["start"])
    if start.tzinfo is None:
        start = start.replace(tzinfo=_LOCAL_TZ)
    start_local = start.astimezone(_LOCAL_TZ)
    hour = start_local.hour
    if hour < 8 or hour >= 20:
        return True
    if session.get("end") and session["end"]:
        end = datetime.fromisoformat(session["end"])
        if end.tzinfo is None:
            end = end.replace(tzinfo=_LOCAL_TZ)
        if (end - start).total_seconds() / 60 > 240:
            return True
    return False

@app.post("/api/v1/access/sessions", status_code=201)
def create_session(body: CreateSessionBody, user=Depends(_current_user)):
    sid = str(uuid.uuid4())
    now = datetime.now(_LOCAL_TZ).isoformat()
    session = {
        "id":            sid,
        "user_id":       user["id"],
        "user":          user["full_name"],
        "role":          user["role"],
        "server":        body.server,
        "ip":            body.ip,
        "tool":          body.tool,
        "reason":        body.reason,
        "client":        body.client,
        "engineer":      body.engineer,
        "start":         now,
        "end":           None,
        "duration_min":  None,
        "status":        "active",
        "notes":         "",
        "is_suspicious": False,
    }
    session["is_suspicious"] = _is_suspicious(session)
    ACCESS_SESSIONS[sid] = session
    return session

@app.get("/api/v1/access/sessions")
def list_sessions(status: str = "active", _=Depends(_current_user)):
    sessions = [s for s in ACCESS_SESSIONS.values() if s["status"] == status]
    sessions.sort(key=lambda s: s["start"], reverse=True)
    return {"sessions": sessions}

@app.put("/api/v1/access/sessions/{session_id}/close")
def close_session(session_id: str, body: CloseSessionBody, _=Depends(_current_user)):
    session = ACCESS_SESSIONS.get(session_id)
    if not session:
        raise HTTPException(404, "Sesión no encontrada")
    if session["status"] == "closed":
        raise HTTPException(400, "Sesión ya cerrada")
    now   = datetime.now(_LOCAL_TZ)
    start = datetime.fromisoformat(session["start"])
    if start.tzinfo is None:
        start = start.replace(tzinfo=_LOCAL_TZ)
    session["end"]           = now.isoformat()
    session["duration_min"]  = round((now - start).total_seconds() / 60)
    session["status"]        = "closed"
    session["notes"]         = body.notes
    session["is_suspicious"] = _is_suspicious(session)
    _append_log(session)
    return session

@app.get("/api/v1/access/logs")
def access_logs(_=Depends(_current_user)):
    logs = [s for s in ACCESS_SESSIONS.values() if s["status"] == "closed"]
    logs.sort(key=lambda s: s["start"], reverse=True)
    return {"logs": logs}

@app.get("/api/v1/access/alerts")
def access_alerts(_=Depends(_current_user)):
    alerts = [s for s in ACCESS_SESSIONS.values() if s["is_suspicious"]]
    alerts.sort(key=lambda s: s["start"], reverse=True)
    return {"alerts": alerts}

@app.delete("/api/v1/access/sessions/{session_id}/delete")
def delete_access_session(session_id: str, _=Depends(_require_role("admin"))):
    if session_id not in ACCESS_SESSIONS:
        raise HTTPException(404, "Sesión no encontrada")
    ACCESS_SESSIONS.pop(session_id)
    # Rewrite log file without this entry
    remaining = [s for s in ACCESS_SESSIONS.values() if s["status"] == "closed"]
    with open(ACCESS_LOG_FILE, "w", encoding="utf-8") as f:
        for s in remaining:
            f.write(_json.dumps(s, ensure_ascii=False) + "\n")
    return {"deleted": session_id}

@app.get("/api/v1/access/download")
def download_log(_=Depends(_current_user)):
    from fastapi.responses import FileResponse
    if not ACCESS_LOG_FILE.exists():
        raise HTTPException(404, "Sin registros aún")
    return FileResponse(
        path=str(ACCESS_LOG_FILE),
        media_type="text/plain",
        filename=f"accesos_{datetime.now().strftime('%Y%m%d')}.log",
    )


# ── Search ────────────────────────────────────────────────────────────────────
@app.get("/api/v1/search")
def search(q: str = "", _=Depends(_current_user)):
    q_lower = q.lower().strip()
    if len(q_lower) < 2:
        return {"backups": [], "access": []}

    backup_results = []
    for b in list(BACKUPS.values()):
        haystack = " ".join(str(v) for v in [
            b.get("databaseName", ""), b.get("status", ""),
            b.get("backupType", ""), b.get("errorMessage", ""),
        ]).lower()
        if q_lower in haystack:
            backup_results.append({
                "id":     b["id"],
                "label":  f"{b.get('databaseName', '?')} — {b.get('backupType', '?')}",
                "sub":    b.get("databaseName", ""),
                "status": b.get("status", ""),
            })

    access_results = []
    for s in list(ACCESS_SESSIONS.values()):
        haystack = " ".join(str(v) for v in [
            s.get("server", ""), s.get("engineer", ""),
            s.get("client", ""), s.get("reason", ""), s.get("status", ""),
        ]).lower()
        if q_lower in haystack:
            access_results.append({
                "id":     s["id"],
                "label":  f"{s.get('server', '?')} — {s.get('engineer', '?')}",
                "sub":    s.get("client", ""),
                "status": s.get("status", ""),
            })

    return {"backups": backup_results[:10], "access": access_results[:10]}


# ── Notifications ─────────────────────────────────────────────────────────────
@app.get("/api/v1/notifications")
def get_notifications(_=Depends(_current_user)):
    notifs = []

    for b in list(BACKUPS.values()):
        if b.get("status") == "failed":
            notifs.append({
                "id":   f"backup-{b['id']}",
                "kind": "backup_fail",
                "title": f"Backup fallido: {b.get('databaseName', '?')}",
                "body":  b.get("errorMessage") or f"BD: {b.get('databaseName', '?')}",
                "ts":    b.get("finishedAt") or b.get("createdAt", ""),
            })

    for s in list(ACCESS_SESSIONS.values()):
        if s.get("is_suspicious"):
            notifs.append({
                "id":   f"access-{s['id']}",
                "kind": "suspicious",
                "title": f"Acceso sospechoso: {s.get('server', '?')}",
                "body":  f"{s.get('engineer', '?')} · {s.get('client', '?')}",
                "ts":    s.get("start", ""),
            })

    notifs.sort(key=lambda x: x.get("ts", ""), reverse=True)
    return {"notifications": notifs[:20], "unread": len(notifs)}


# ── File Manager ─────────────────────────────────────────────────────────────
class FMConnectionBody(BaseModel):
    host:     str
    port:     int  = 22
    protocol: Literal["sftp", "ftp", "ftps"] = "sftp"
    username: str  = ""
    password: str  = ""
    # Autenticación con llave privada (p. ej. .pem de AWS EC2). Solo SFTP. El contenido
    # PEM viaja en el body y vive solo en memoria — NUNCA se persiste (igual que password).
    privateKey: str = ""
    passphrase: str = ""

class FMPathBody(BaseModel):
    connection:  FMConnectionBody | None = None
    path:        str = "/"

class FMDeleteBody(BaseModel):
    connection:    FMConnectionBody | None = None
    path:          str
    contents_only: bool = False


# ── Verificación de clave de host SSH (H-5) ───────────────────────────────────
# Antes se aceptaba CUALQUIER clave de host (AutoAddPolicy) → riesgo de MITM. Ahora
# TOFU: la huella se fija en el primer uso y se persiste; si la clave del host CAMBIA
# después, la conexión se BLOQUEA (posible interceptación). Con SSH_HOSTKEY_STRICT=1
# no se acepta ningún host nuevo sin que un admin lo autorice explícitamente antes.
SSH_HOSTKEYS: dict[str, str] = {}   # "host:port" -> huella SHA256 (base64)


class _PinnedHostKeyPolicy:
    """Política paramiko (duck-typed, sin importar paramiko en carga) que fija/verifica
    la huella de la clave de host contra SSH_HOSTKEYS."""

    def __init__(self, host_port: str, strict: bool):
        self.key = host_port
        self.strict = strict

    def missing_host_key(self, client, hostname, key):
        fp = base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode()
        known = SSH_HOSTKEYS.get(self.key)
        if known is None:
            if self.strict:
                raise Exception(
                    f"Host SSH desconocido {self.key} (SHA256:{fp}). En modo estricto un "
                    f"administrador debe autorizarlo antes de conectar."
                )
            SSH_HOSTKEYS[self.key] = fp   # TOFU: fijar en el primer uso
            return
        if known != fp:
            raise Exception(
                f"¡La clave del host SSH {self.key} CAMBIÓ! (esperada SHA256:{known}, "
                f"recibida SHA256:{fp}). Conexión BLOQUEADA por posible MITM. Si el cambio "
                f"es legítimo, un administrador debe olvidar/re-autorizar el host."
            )


def _load_private_key(pem: str, passphrase: str = ""):
    """Carga una llave privada desde su contenido PEM/OpenSSH (RSA, Ed25519 o ECDSA —
    cubre las .pem que genera AWS EC2). Errores en español para el usuario."""
    import paramiko
    pw = passphrase or None
    last: Exception | None = None
    for cls in (paramiko.RSAKey, paramiko.Ed25519Key, paramiko.ECDSAKey):
        try:
            return cls.from_private_key(io.StringIO(pem), password=pw)
        except paramiko.PasswordRequiredException:
            raise Exception("La llave privada está cifrada: introduce su passphrase.")
        except Exception as exc:
            last = exc
    raise Exception(
        "No se pudo leer la llave privada (.pem). Verifica que el archivo sea la llave "
        f"privada correcta (formato PEM/OpenSSH, tipos RSA/Ed25519/ECDSA). Detalle: {last}"
    )


def _sftp_client(conn: FMConnectionBody):
    import paramiko
    client = paramiko.SSHClient()
    key = f"{conn.host}:{conn.port}"
    strict = os.getenv("SSH_HOSTKEY_STRICT", "0") not in ("0", "false", "False", "")
    client.set_missing_host_key_policy(_PinnedHostKeyPolicy(key, strict))
    auth: dict = {"password": conn.password}
    if (conn.privateKey or "").strip():
        auth = {"pkey": _load_private_key(conn.privateKey, conn.passphrase)}
    client.connect(
        conn.host, port=conn.port, username=conn.username,
        timeout=15, allow_agent=False, look_for_keys=False, **auth,
    )
    return client


class ForgetHostKeyBody(BaseModel):
    host: str
    port: int = 22


@app.get("/api/v1/ssh/hostkeys")
def list_hostkeys(_=Depends(_require_role("admin"))):
    return {"items": [{"host": k, "fingerprint": v} for k, v in SSH_HOSTKEYS.items()],
            "total": len(SSH_HOSTKEYS)}


@app.post("/api/v1/ssh/hostkeys/forget")
def forget_hostkey(body: ForgetHostKeyBody, _=Depends(_require_role("admin"))):
    key = f"{body.host}:{body.port}"
    existed = SSH_HOSTKEYS.pop(key, None) is not None
    return {"forgotten": existed, "host": key}


def _sync_fm_list(body: FMPathBody) -> list:
    import shutil

    if body.connection is None:
        p = _ensure_local_path_allowed(body.path)
        if not p.exists():
            raise FileNotFoundError(f"Ruta no encontrada: {body.path}")
        entries = []
        try:
            for item in sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
                try:
                    st = item.stat()
                    entries.append({
                        "name":        item.name,
                        "size":        st.st_size if item.is_file() else 0,
                        "modified":    st.st_mtime,
                        "isDir":       item.is_dir(),
                        "permissions": None,
                    })
                except PermissionError:
                    pass
        except PermissionError:
            pass
        return entries

    conn = body.connection
    if conn.protocol in ("ftp", "ftps"):
        ftp = ftplib.FTP_TLS() if conn.protocol == "ftps" else ftplib.FTP()
        ftp.connect(conn.host, conn.port or 21, timeout=15)
        ftp.login(conn.username, conn.password)
        if conn.protocol == "ftps":
            ftp.prot_p()
        entries = []
        try:
            for name, facts in ftp.mlsd(body.path, facts=["type", "size", "modify"]):
                if name in (".", ".."):
                    continue
                entries.append({
                    "name":        name,
                    "size":        int(facts.get("size", 0)),
                    "modified":    None,
                    "isDir":       facts.get("type") == "dir",
                    "permissions": None,
                })
        except Exception:
            for name in ftp.nlst(body.path):
                entries.append({"name": name.split("/")[-1], "size": 0, "modified": None, "isDir": False, "permissions": None})
        ftp.quit()
        return entries

    # SFTP
    client = _sftp_client(conn)
    sftp = client.open_sftp()
    entries = []
    try:
        for attr in sorted(sftp.listdir_attr(body.path), key=lambda a: (not _stat.S_ISDIR(a.st_mode or 0), a.filename.lower())):
            entries.append({
                "name":        attr.filename,
                "size":        attr.st_size or 0,
                "modified":    attr.st_mtime,
                "isDir":       _stat.S_ISDIR(attr.st_mode or 0),
                "permissions": oct(attr.st_mode)[-3:] if attr.st_mode else None,
            })
    finally:
        sftp.close()
        client.close()
    return entries


def _sync_fm_delete(body: FMDeleteBody) -> dict:
    import shutil

    def _local_delete_contents(p: Path) -> int:
        count = 0
        for child in list(p.iterdir()):
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
            count += 1
        return count

    if body.connection is None:
        p = _ensure_local_path_allowed(body.path)
        if not p.exists():
            raise FileNotFoundError(f"No existe: {body.path}")
        if body.contents_only:
            return {"deleted": _local_delete_contents(p)}
        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink()
        return {"deleted": 1}

    conn = body.connection

    if conn.protocol in ("ftp", "ftps"):
        ftp = ftplib.FTP_TLS() if conn.protocol == "ftps" else ftplib.FTP()
        ftp.connect(conn.host, conn.port or 21, timeout=15)
        ftp.login(conn.username, conn.password)
        if conn.protocol == "ftps":
            ftp.prot_p()

        def _ftp_del(path: str):
            try:
                ftp.delete(path); return
            except ftplib.error_perm:
                pass
            lines: list[str] = []
            ftp.retrlines(f"LIST {path}", lines.append)
            for line in lines:
                parts = line.split(None, 8)
                if len(parts) < 9: continue
                child = f"{path.rstrip('/')}/{parts[8]}"
                if line.startswith("d"):
                    _ftp_del(child)
                    try: ftp.rmd(child)
                    except: pass
                else:
                    try: ftp.delete(child)
                    except: pass

        if body.contents_only:
            lines: list[str] = []
            ftp.retrlines(f"LIST {body.path}", lines.append)
            deleted = 0
            for line in lines:
                parts = line.split(None, 8)
                if len(parts) < 9 or parts[8] in (".", ".."): continue
                child = f"{body.path.rstrip('/')}/{parts[8]}"
                if line.startswith("d"):
                    _ftp_del(child)
                    try: ftp.rmd(child)
                    except: pass
                else:
                    try: ftp.delete(child)
                    except: pass
                deleted += 1
        else:
            _ftp_del(body.path)
            deleted = 1
        ftp.quit()
        return {"deleted": deleted}

    # SFTP
    client = _sftp_client(conn)
    sftp = client.open_sftp()

    def _sftp_del(path: str):
        try:
            attrs = sftp.listdir_attr(path)
        except IOError:
            sftp.remove(path); return
        for a in attrs:
            child = f"{path.rstrip('/')}/{a.filename}"
            if _stat.S_ISDIR(a.st_mode or 0):
                _sftp_del(child)
                sftp.rmdir(child)
            else:
                sftp.remove(child)

    try:
        if body.contents_only:
            attrs = sftp.listdir_attr(body.path)
            for a in attrs:
                child = f"{body.path.rstrip('/')}/{a.filename}"
                if _stat.S_ISDIR(a.st_mode or 0):
                    _sftp_del(child); sftp.rmdir(child)
                else:
                    sftp.remove(child)
            result = {"deleted": len(attrs)}
        else:
            try:
                sftp.remove(body.path)
            except IOError:
                _sftp_del(body.path); sftp.rmdir(body.path)
            result = {"deleted": 1}
    finally:
        sftp.close()
        client.close()
    return result


@app.post("/api/v1/fm/test")
async def fm_test(body: FMConnectionBody, _=Depends(_current_user)):
    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(_executor, _sync_fm_list, FMPathBody(connection=body, path="/"))
        return {"connected": True}
    except Exception as exc:
        return {"connected": False, "error": str(exc)}


@app.post("/api/v1/fm/list")
async def fm_list(body: FMPathBody, _=Depends(_current_user)):
    loop = asyncio.get_event_loop()
    try:
        entries = await loop.run_in_executor(_executor, _sync_fm_list, body)
        return {"entries": entries, "path": body.path}
    except Exception as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/v1/fm/delete")
async def fm_delete(body: FMDeleteBody, _=Depends(_require_role("admin"))):
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(_executor, _sync_fm_delete, body)
        return result
    except Exception as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/v1/fm/mkdir")
async def fm_mkdir(body: FMPathBody, _=Depends(_current_user)):
    loop = asyncio.get_event_loop()
    def _do():
        if body.connection is None:
            _ensure_local_path_allowed(body.path).mkdir(parents=True, exist_ok=True)
            return
        conn = body.connection
        if conn.protocol in ("ftp", "ftps"):
            ftp = ftplib.FTP_TLS() if conn.protocol == "ftps" else ftplib.FTP()
            ftp.connect(conn.host, conn.port or 21, timeout=15)
            ftp.login(conn.username, conn.password)
            ftp.mkd(body.path); ftp.quit()
        else:
            client = _sftp_client(conn)
            sftp = client.open_sftp()
            try: sftp.mkdir(body.path)
            finally: sftp.close(); client.close()
    await loop.run_in_executor(_executor, _do)
    return {"created": body.path}


# ── Limpieza remota segura (Fase 1: navegación acotada · Fase 3: simulación) ───
# Servidores con LISTA BLANCA de rutas. Sin allowlist configurada por un admin, no se
# puede listar ni simular nada (fail-closed). Las contraseñas NO se almacenan: viajan
# por petición y solo en memoria (coherente con C-1). El borrado real (Fase 2/5) se
# implementará aparte, con cuarentena; aquí solo hay LECTURA y SIMULACIÓN.
CLEANUP_SERVERS: dict[str, dict] = {}


class CleanupServerBody(BaseModel):
    name:      str
    protocol:  Literal["sftp", "ftps", "ftp"] = "sftp"
    host:      str
    port:      int = 22
    username:  str = ""
    rutaBase:  str = "/"
    allowlist: list[str] = []


def _body_creds(body) -> dict:
    """Extrae las credenciales efímeras (contraseña o llave .pem) de un request body.
    Nunca se persisten: solo viajan del body a la conexión."""
    return {
        "password":   getattr(body, "password", "") or "",
        "privateKey": getattr(body, "privateKey", "") or "",
        "passphrase": getattr(body, "passphrase", "") or "",
    }


def _cleanup_conn(server: dict, creds: dict) -> "FMConnectionBody":
    protocol = server.get("protocol", "sftp")
    if creds.get("privateKey") and protocol != "sftp":
        raise HTTPException(400, "La autenticación con llave .pem solo aplica al protocolo SFTP.")
    return FMConnectionBody(
        host=server["host"], port=int(server.get("port", 22)),
        protocol=protocol,
        username=server.get("username", ""),
        password=creds.get("password", ""),
        privateKey=creds.get("privateKey", ""),
        passphrase=creds.get("passphrase", ""),
    )


def _remote_error(exc, server: dict) -> str:
    """Traduce errores de conexión SFTP/FTP a mensajes claros para el usuario."""
    raw = _safe_error(exc)
    low = raw.lower()
    host = server.get("host", "?")
    port = server.get("port", "?")
    if "timed out" in low or "timeout" in low:
        return (f"No se pudo conectar a {host}:{port} — tiempo de espera agotado. "
                f"Verifica que el host y el puerto sean correctos y accesibles desde este equipo "
                f"(¿VPN/firewall?, ¿el servicio SFTP/FTP está activo?).")
    if any(s in low for s in ("getaddrinfo", "name or service", "nodename", "no address")):
        return f"No se pudo resolver el host '{host}'. Verifica la dirección."
    if "refused" in low:
        return f"Conexión rechazada por {host}:{port}. ¿El servicio SFTP/FTP escucha en ese puerto?"
    if any(s in low for s in ("authentication", "auth failed", "password", "permission denied")):
        return "Autenticación fallida. Verifica el usuario y la contraseña (o que la llave .pem sea la del servidor)."
    if "no hostkey" in low or "host key" in low:
        return f"No se pudo verificar la clave del host {host}. Revisa la configuración del servidor."
    return raw


def _ftp_modify_to_epoch(s: str | None):
    if not s:
        return None
    try:
        return datetime.strptime(s[:14], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc).timestamp()
    except Exception:
        return None


def _sftp_list_one(sftp, path: str) -> list[dict]:
    out = []
    for a in sftp.listdir_attr(path):
        mode = a.st_mode or 0
        out.append({
            "name":        a.filename,
            "path":        posixpath.join(path, a.filename),
            "sizeBytes":   a.st_size or 0,
            "modified":    a.st_mtime,
            "isDir":       _stat.S_ISDIR(mode),
            "isLink":      _stat.S_ISLNK(mode),   # se detecta para NO seguir symlinks
            "permissions": oct(mode)[-3:] if mode else None,
        })
    return out


def _ftp_list_one(ftp, path: str) -> list[dict]:
    out = []
    try:
        for name, facts in ftp.mlsd(path, facts=["type", "size", "modify"]):
            if name in (".", ".."):
                continue
            out.append({
                "name":        name,
                "path":        posixpath.join(path, name),
                "sizeBytes":   int(facts.get("size", 0) or 0),
                "modified":    _ftp_modify_to_epoch(facts.get("modify")),
                "isDir":       facts.get("type") == "dir",
                "isLink":      False,   # FTP simple no distingue symlinks de forma fiable
                "permissions": None,
            })
    except Exception:
        pass
    return out


def _bfs_collect(list_one, roots: list[str], allowlist: list[str], cap: int):
    """Recorre en anchura las rutas objetivo recolectando SOLO archivos, acotado por
    `cap`. No sigue symlinks y revalida la allowlist en cada subruta (defensa en
    profundidad). Devuelve (archivos, truncado)."""
    files: list[dict] = []
    truncated = False
    stack = list(roots)
    while stack:
        if len(files) >= cap:
            truncated = True
            break
        d = stack.pop()
        try:
            entries = list_one(d)
        except Exception:
            continue
        for e in entries:
            if e.get("isLink"):
                continue  # nunca seguir enlaces simbólicos
            if e["isDir"] and posixpath.basename(e["path"].rstrip("/")) == remote_cleanup.QUARANTINE_DIRNAME:
                continue  # nunca recorrer ni limpiar la carpeta de cuarentena
            if not remote_cleanup.is_within_allowlist(e["path"], allowlist):
                continue
            if e["isDir"]:
                stack.append(e["path"])
            else:
                files.append(e)
                if len(files) >= cap:
                    truncated = True
                    break
    return files, truncated


def _sync_remote_list(server: dict, creds: dict, raw_path: str, page: int, page_size: int) -> dict:
    allowlist = server.get("allowlist", []) or []
    if not allowlist:
        raise HTTPException(403, "El servidor no tiene rutas autorizadas (allowlist vacía). "
                                 "Un administrador debe configurarlas antes de navegar.")
    if remote_cleanup.contains_traversal(raw_path):
        raise HTTPException(403, "Ruta con '..' no permitida")
    conn = _cleanup_conn(server, creds)

    if conn.protocol in ("ftp", "ftps"):
        ftp = ftplib.FTP_TLS() if conn.protocol == "ftps" else ftplib.FTP()
        ftp.connect(conn.host, conn.port or 21, timeout=15)
        ftp.login(conn.username, conn.password)
        if conn.protocol == "ftps":
            ftp.prot_p()
        try:
            resolved = remote_cleanup.normalize_remote(raw_path)
            if not remote_cleanup.is_within_allowlist(resolved, allowlist):
                raise HTTPException(403, "Ruta fuera de las rutas autorizadas (allowlist)")
            entries = _ftp_list_one(ftp, resolved)
        finally:
            try:
                ftp.quit()
            except Exception:
                pass
    else:
        client = _sftp_client(conn)
        sftp = client.open_sftp()
        try:
            # normalize() resuelve symlinks y '..' EN EL SERVIDOR → base de la validación.
            resolved = sftp.normalize(raw_path)
            if not remote_cleanup.is_within_allowlist(resolved, allowlist):
                raise HTTPException(403, "Ruta fuera de las rutas autorizadas (allowlist)")
            entries = _sftp_list_one(sftp, resolved)
        finally:
            sftp.close()
            client.close()

    entries.sort(key=lambda e: (not e["isDir"], e["name"].lower()))
    total = len(entries)
    start = max(0, (page - 1) * page_size)
    return {
        "path": resolved, "entries": entries[start:start + page_size],
        "total": total, "page": page, "pageSize": page_size,
    }


def _sync_remote_simulate(server: dict, creds: dict, rule: dict) -> dict:
    allowlist = server.get("allowlist", []) or []
    if not allowlist:
        raise HTTPException(403, "El servidor no tiene rutas autorizadas (allowlist vacía).")

    # Las rutas objetivo de la regla DEBEN estar dentro de la allowlist del servidor.
    targets = rule.get("rutasPermitidas") or allowlist
    safe_targets = []
    for t in targets:
        if remote_cleanup.contains_traversal(t):
            raise HTTPException(403, f"Ruta objetivo con '..' no permitida: {t}")
        tn = remote_cleanup.normalize_remote(t)
        if not remote_cleanup.is_within_allowlist(tn, allowlist):
            raise HTTPException(403, f"Ruta objetivo fuera de la allowlist: {t}")
        safe_targets.append(tn)

    conn = _cleanup_conn(server, creds)
    cap = int(os.getenv("CLEANUP_SIM_MAX_FILES", "50000"))

    if conn.protocol in ("ftp", "ftps"):
        ftp = ftplib.FTP_TLS() if conn.protocol == "ftps" else ftplib.FTP()
        ftp.connect(conn.host, conn.port or 21, timeout=15)
        ftp.login(conn.username, conn.password)
        if conn.protocol == "ftps":
            ftp.prot_p()
        try:
            files, truncated = _bfs_collect(lambda d: _ftp_list_one(ftp, d), safe_targets, allowlist, cap)
        finally:
            try:
                ftp.quit()
            except Exception:
                pass
    else:
        client = _sftp_client(conn)
        sftp = client.open_sftp()
        try:
            files, truncated = _bfs_collect(lambda d: _sftp_list_one(sftp, d), safe_targets, allowlist, cap)
        finally:
            sftp.close()
            client.close()

    report = remote_cleanup.select_candidates(files, rule, time.time())
    report["simulacion"] = True          # marca: NO se eliminó ni movió nada
    report["truncated"] = truncated
    report["targets"] = safe_targets
    if truncated:
        report["warnings"].append(
            f"Recorrido truncado en {cap} archivos; acota las rutas o sube CLEANUP_SIM_MAX_FILES."
        )
    return report


@app.get("/api/v1/cleanup/remote/servers")
def list_cleanup_servers(_=Depends(_current_user)):
    # Nunca se guarda contraseña, así que el objeto es seguro de devolver tal cual.
    return {"items": list(CLEANUP_SERVERS.values()), "total": len(CLEANUP_SERVERS)}


@app.post("/api/v1/cleanup/remote/servers", status_code=201)
def create_cleanup_server(body: CleanupServerBody, _=Depends(_require_role("admin"))):
    sid = str(uuid.uuid4())
    srv = {"id": sid, **body.model_dump(), "createdAt": datetime.now(timezone.utc).isoformat()}
    CLEANUP_SERVERS[sid] = srv
    return srv


@app.put("/api/v1/cleanup/remote/servers/{sid}")
def update_cleanup_server(sid: str, body: CleanupServerBody, _=Depends(_require_role("admin"))):
    if sid not in CLEANUP_SERVERS:
        raise HTTPException(404, "Servidor no encontrado")
    CLEANUP_SERVERS[sid].update(body.model_dump())
    return CLEANUP_SERVERS[sid]


@app.delete("/api/v1/cleanup/remote/servers/{sid}", status_code=204)
def delete_cleanup_server(sid: str, _=Depends(_require_role("admin"))):
    CLEANUP_SERVERS.pop(sid, None)


class RemoteListBody(BaseModel):
    server_id:  str
    password:   str = ""
    privateKey: str = ""
    passphrase: str = ""
    path:       str | None = None
    page:       int = 1
    pageSize:   int = 200


@app.post("/api/v1/cleanup/remote/list")
async def remote_cleanup_list(body: RemoteListBody, _=Depends(_current_user)):
    server = CLEANUP_SERVERS.get(body.server_id)
    if not server:
        raise HTTPException(404, "Servidor no encontrado")
    # Punto de entrada por defecto: la primera ruta autorizada.
    path = body.path or (server.get("allowlist") or [server.get("rutaBase", "/")])[0]
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(
            _executor, _sync_remote_list, server, _body_creds(body),
            path, max(1, body.page), min(1000, max(1, body.pageSize)),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400, _remote_error(exc, server))


class RemoteSimulateBody(BaseModel):
    server_id:  str
    password:   str = ""
    privateKey: str = ""
    passphrase: str = ""
    rule:       dict


@app.post("/api/v1/cleanup/remote/simulate")
async def remote_cleanup_simulate(body: RemoteSimulateBody, _=Depends(_current_user)):
    server = CLEANUP_SERVERS.get(body.server_id)
    if not server:
        raise HTTPException(404, "Servidor no encontrado")
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(
            _backup_executor, _sync_remote_simulate, server, _body_creds(body), body.rule,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400, _remote_error(exc, server))


# ── Ejecución (Fase 2: mover a cuarentena) · Cuarentena (Fase 5) · Auditoría (Fase 6) ──
# REGLA DE ORO: "eliminar" NO borra — mueve a cuarentena en el mismo servidor (rename
# atómico, reversible). La única operación irreversible es la PURGA, separada y solo-admin.
CLEANUP_EXECUTIONS: dict[str, dict] = {}   # id -> registro de ejecución (auditoría)
CLEANUP_QUARANTINE: dict[str, dict] = {}   # id -> metadatos de archivo en cuarentena

_CLEANUP_RUNNING: set[str] = set()          # candado anti-concurrencia por servidor
_CLEANUP_LOCK = threading.Lock()


def _resolve_safe_targets(server: dict, rule: dict) -> tuple[list, list]:
    """Valida (fail-closed) que las rutas objetivo de la regla estén dentro de la
    allowlist del servidor y sin '..'. Devuelve (allowlist, rutas_objetivo_seguras)."""
    allowlist = server.get("allowlist", []) or []
    if not allowlist:
        raise HTTPException(403, "El servidor no tiene rutas autorizadas (allowlist vacía).")
    targets = rule.get("rutasPermitidas") or allowlist
    safe = []
    for t in targets:
        if remote_cleanup.contains_traversal(t):
            raise HTTPException(403, f"Ruta objetivo con '..' no permitida: {t}")
        tn = remote_cleanup.normalize_remote(t)
        if not remote_cleanup.is_within_allowlist(tn, allowlist):
            raise HTTPException(403, f"Ruta objetivo fuera de la allowlist: {t}")
        safe.append(tn)
    return allowlist, safe


# ── Helpers de mover/crear directorios remotos ────────────────────────────────
def _sftp_mkdirs(sftp, directory: str) -> None:
    directory = directory.replace("\\", "/")
    parts = [p for p in directory.split("/") if p]
    cur = "" if not directory.startswith("/") else ""
    for p in parts:
        cur = f"{cur}/{p}"
        try:
            sftp.stat(cur)
        except IOError:
            try:
                sftp.mkdir(cur)
            except IOError:
                pass


def _sftp_move(sftp, src: str, dst: str) -> None:
    _sftp_mkdirs(sftp, posixpath.dirname(dst))
    try:
        sftp.posix_rename(src, dst)   # atómico si el servidor lo soporta
    except (IOError, AttributeError):
        sftp.rename(src, dst)


def _ftp_mkdirs(ftp, directory: str) -> None:
    parts = [p for p in directory.replace("\\", "/").split("/") if p]
    cur = ""
    for p in parts:
        cur = f"{cur}/{p}"
        try:
            ftp.mkd(cur)
        except Exception:
            pass


def _ftp_move(ftp, src: str, dst: str) -> None:
    _ftp_mkdirs(ftp, posixpath.dirname(dst))
    ftp.rename(src, dst)


def _check_conteo(report: dict, conteo_esperado) -> None:
    """Aborta si el nº de elegibles cambió respecto a la simulación que vio el usuario
    (evita ejecutar sobre un estado que derivó desde que se simuló)."""
    if conteo_esperado is not None and report["elegiblesCount"] != conteo_esperado:
        raise HTTPException(
            409,
            f"El conteo cambió desde la simulación (esperado {conteo_esperado}, "
            f"ahora {report['elegiblesCount']}). Vuelve a simular antes de ejecutar.",
        )


def _record_quarantine(entry: dict, dst: str, exec_id: str, actor: str,
                       rule: dict, server_id: str, moved: list) -> None:
    qid = str(uuid.uuid4())
    retention = int((rule.get("cuarentena") or {}).get("retencionDias", 15))
    item = {
        "id": qid, "execId": exec_id, "serverId": server_id,
        "name": entry.get("name", ""), "originalPath": entry["path"], "quarantinePath": dst,
        "sizeBytes": int(entry.get("sizeBytes", 0) or 0),
        "movedAt": datetime.now(timezone.utc).isoformat(), "actor": actor,
        "retentionDays": retention, "purged": False,
    }
    CLEANUP_QUARANTINE[qid] = item
    moved.append(item)


def _sync_remote_execute(server, creds, rule, exec_id, actor, conteo_esperado) -> dict:
    allowlist, safe_targets = _resolve_safe_targets(server, rule)
    conn = _cleanup_conn(server, creds)
    cap = int(os.getenv("CLEANUP_SIM_MAX_FILES", "50000"))
    ruta_base = server.get("rutaBase", "/")
    started = datetime.now(timezone.utc).isoformat()
    moved: list = []
    failed: list = []

    def _process(list_one, mover):
        files, truncated = _bfs_collect(list_one, safe_targets, allowlist, cap)
        report = remote_cleanup.select_candidates(files, rule, time.time())
        _check_conteo(report, conteo_esperado)      # gate de seguridad
        for e in report["elegibles"]:
            dst = remote_cleanup.quarantine_path(ruta_base, exec_id, e["path"])
            try:
                mover(e["path"], dst)
                _record_quarantine(e, dst, exec_id, actor, rule, server["id"], moved)
            except Exception as exc:
                failed.append({"path": e["path"], "error": _safe_error(exc)})
        return report, truncated

    if conn.protocol in ("ftp", "ftps"):
        ftp = ftplib.FTP_TLS() if conn.protocol == "ftps" else ftplib.FTP()
        ftp.connect(conn.host, conn.port or 21, timeout=15)
        ftp.login(conn.username, conn.password)
        if conn.protocol == "ftps":
            ftp.prot_p()
        try:
            report, truncated = _process(lambda d: _ftp_list_one(ftp, d), lambda s, d: _ftp_move(ftp, s, d))
        finally:
            try:
                ftp.quit()
            except Exception:
                pass
    else:
        client = _sftp_client(conn)
        sftp = client.open_sftp()
        try:
            report, truncated = _process(lambda d: _sftp_list_one(sftp, d), lambda s, d: _sftp_move(sftp, s, d))
        finally:
            sftp.close()
            client.close()

    record = {
        "id": exec_id, "tipo": "manual", "serverId": server["id"], "serverName": server.get("name"),
        "targets": safe_targets, "actor": actor,
        "startedAt": started, "finishedAt": datetime.now(timezone.utc).isoformat(),
        "encontrados": report["encontrados"], "elegibles": report["elegiblesCount"],
        "movidos": len(moved), "omitidos": report["excluidosCount"], "fallidos": len(failed),
        "espacioBytes": sum(m["sizeBytes"] for m in moved),
        "estado": "completado" if not failed else "parcial",
        "errores": failed[:50], "cuarentena": True, "truncated": truncated,
    }
    CLEANUP_EXECUTIONS[exec_id] = record
    return record


def _sync_remote_restore(server, creds, item) -> dict:
    conn = _cleanup_conn(server, creds)
    src = item["quarantinePath"]
    dst = item["originalPath"]
    if conn.protocol in ("ftp", "ftps"):
        ftp = ftplib.FTP_TLS() if conn.protocol == "ftps" else ftplib.FTP()
        ftp.connect(conn.host, conn.port or 21, timeout=15)
        ftp.login(conn.username, conn.password)
        if conn.protocol == "ftps":
            ftp.prot_p()
        try:
            _ftp_move(ftp, src, dst)
        finally:
            try:
                ftp.quit()
            except Exception:
                pass
    else:
        client = _sftp_client(conn)
        sftp = client.open_sftp()
        try:
            _sftp_move(sftp, src, dst)
        finally:
            sftp.close()
            client.close()
    CLEANUP_QUARANTINE.pop(item["id"], None)
    return {"restored": dst}


def _sync_remote_purge(server, creds, items) -> dict:
    conn = _cleanup_conn(server, creds)
    deleted, failed = [], []

    def _rm(remover):
        for it in items:
            try:
                remover(it["quarantinePath"])
                deleted.append(it["id"])
            except Exception as exc:
                failed.append({"id": it["id"], "error": _safe_error(exc)})

    if conn.protocol in ("ftp", "ftps"):
        ftp = ftplib.FTP_TLS() if conn.protocol == "ftps" else ftplib.FTP()
        ftp.connect(conn.host, conn.port or 21, timeout=15)
        ftp.login(conn.username, conn.password)
        if conn.protocol == "ftps":
            ftp.prot_p()
        try:
            _rm(lambda p: ftp.delete(p))
        finally:
            try:
                ftp.quit()
            except Exception:
                pass
    else:
        client = _sftp_client(conn)
        sftp = client.open_sftp()
        try:
            _rm(lambda p: sftp.remove(p))
        finally:
            sftp.close()
            client.close()
    for i in deleted:
        CLEANUP_QUARANTINE.pop(i, None)
    return {"deleted": len(deleted), "failed": failed}


class RemoteExecuteBody(BaseModel):
    server_id:      str
    password:       str = ""
    privateKey:     str = ""
    passphrase:     str = ""
    rule:           dict
    confirmar:      bool = False
    conteoEsperado: int | None = None


@app.post("/api/v1/cleanup/remote/execute")
async def remote_cleanup_execute(
    body: RemoteExecuteBody,
    user=Depends(_require_role("admin", "technician", "supervisor")),
):
    server = CLEANUP_SERVERS.get(body.server_id)
    if not server:
        raise HTTPException(404, "Servidor no encontrado")
    if not body.confirmar:
        raise HTTPException(400, "Debe confirmar la ejecución (confirmar=true) tras revisar la simulación.")
    _resolve_safe_targets(server, body.rule)   # fail-closed ANTES de conectar/bloquear

    key = body.server_id
    with _CLEANUP_LOCK:
        if key in _CLEANUP_RUNNING:
            raise HTTPException(409, "Ya hay una limpieza en curso sobre este servidor.")
        _CLEANUP_RUNNING.add(key)

    exec_id = str(uuid.uuid4())
    actor = user.get("full_name") or user.get("email")
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(
            _backup_executor, _sync_remote_execute,
            server, _body_creds(body), body.rule, exec_id, actor, body.conteoEsperado,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400, _remote_error(exc, server))
    finally:
        with _CLEANUP_LOCK:
            _CLEANUP_RUNNING.discard(key)


@app.get("/api/v1/cleanup/remote/history")
def remote_cleanup_history(_=Depends(_current_user)):
    items = sorted(CLEANUP_EXECUTIONS.values(), key=lambda x: x["startedAt"], reverse=True)
    return {"items": items, "total": len(items)}


@app.get("/api/v1/cleanup/remote/history/{eid}")
def remote_cleanup_history_detail(eid: str, _=Depends(_current_user)):
    r = CLEANUP_EXECUTIONS.get(eid)
    if not r:
        raise HTTPException(404, "Ejecución no encontrada")
    return r


@app.get("/api/v1/cleanup/remote/quarantine")
def remote_quarantine_list(_=Depends(_current_user)):
    items = sorted(
        [q for q in CLEANUP_QUARANTINE.values() if not q.get("purged")],
        key=lambda x: x["movedAt"], reverse=True,
    )
    return {"items": items, "total": len(items)}


class RemoteRestoreBody(BaseModel):
    server_id:  str = ""
    password:   str = ""
    privateKey: str = ""
    passphrase: str = ""


@app.post("/api/v1/cleanup/remote/quarantine/{qid}/restore")
async def remote_quarantine_restore(qid: str, body: RemoteRestoreBody, _=Depends(_require_role("admin"))):
    item = CLEANUP_QUARANTINE.get(qid)
    if not item:
        raise HTTPException(404, "Elemento no encontrado en cuarentena")
    server = CLEANUP_SERVERS.get(item.get("serverId")) or CLEANUP_SERVERS.get(body.server_id)
    if not server:
        raise HTTPException(404, "Servidor no encontrado")
    # Defensa: la ruta original debe seguir dentro de la allowlist.
    if not remote_cleanup.is_within_allowlist(item["originalPath"], server.get("allowlist", [])):
        raise HTTPException(403, "La ruta original ya no está autorizada")
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(_executor, _sync_remote_restore, server, _body_creds(body), item)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400, _safe_error(exc))


class RemotePurgeBody(BaseModel):
    server_id:      str
    password:       str = ""
    privateKey:     str = ""
    passphrase:     str = ""
    ids:            list[str] = []
    purgarVencidos: bool = False


@app.post("/api/v1/cleanup/remote/quarantine/purge")
async def remote_quarantine_purge(body: RemotePurgeBody, _=Depends(_require_role("admin"))):
    """PURGA DEFINITIVA (irreversible) — solo admin, selección explícita o vencidos."""
    server = CLEANUP_SERVERS.get(body.server_id)
    if not server:
        raise HTTPException(404, "Servidor no encontrado")
    items = []
    if body.purgarVencidos:
        now = datetime.now(timezone.utc)
        for it in CLEANUP_QUARANTINE.values():
            if it.get("serverId") != body.server_id:
                continue
            try:
                moved = datetime.fromisoformat(it["movedAt"])
                if (now - moved).days >= int(it.get("retentionDays", 15)):
                    items.append(it)
            except Exception:
                pass
    if body.ids:
        items += [CLEANUP_QUARANTINE[i] for i in body.ids if i in CLEANUP_QUARANTINE]
    if not items:
        return {"deleted": 0, "failed": []}
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(_executor, _sync_remote_purge, server, _body_creds(body), items)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400, _safe_error(exc))


# ── Limpieza ESTRUCTURAL (Ipsofactu: N propiedades) ───────────────────────────
# Vacía core/{Log,LogSec,LogsRadian,Respuesta} y borra core/BD_log.txt en cada
# propiedad hija de la raíz. Reutiliza el motor puro `structural_cleanup` y los
# helpers SFTP/FTP existentes. Modo de ejecución: 'cuarentena' (reversible) o
# 'directo' (borra). Simulación obligatoria + gate de conteo, igual que el resto.

def _structural_root(server: dict, rule: dict) -> str:
    return remote_cleanup.normalize_remote(rule.get("raiz") or server.get("rutaBase") or "/")


def _validate_structural_root(server: dict, rule: dict) -> tuple[str, list]:
    allowlist = server.get("allowlist", []) or []
    if not allowlist:
        raise HTTPException(403, "El servidor no tiene rutas autorizadas (allowlist vacía). "
                                 "Un administrador debe configurarla en Configuración → Servidores.")
    root = _structural_root(server, rule)
    if remote_cleanup.contains_traversal(root):
        raise HTTPException(403, "La raíz contiene '..' (no permitido).")
    if not remote_cleanup.is_within_allowlist(root, allowlist):
        raise HTTPException(403, "La raíz está fuera de las rutas autorizadas (allowlist).")
    if not (rule.get("vaciarCarpetas") or rule.get("borrarArchivos")):
        raise HTTPException(400, "La regla no indica carpetas a vaciar ni archivos a borrar.")
    return root, allowlist


def _structural_discover_props(list_one, root, max_props):
    """Lista la raíz y devuelve (propiedades_ordenadas, total). Excluye enlaces y la
    carpeta de cuarentena. `max_props`>0 recorta para pruebas por lotes."""
    try:
        top = list_one(root)
    except Exception as exc:
        raise HTTPException(400, f"No se pudo listar la raíz {root}: {_safe_error(exc)}")
    props = [e for e in top
             if e.get("isDir") and not e.get("isLink")
             and not structural_cleanup.is_quarantine(e["path"])]
    props.sort(key=lambda e: e["name"].lower())
    total = len(props)
    if max_props and max_props > 0:
        props = props[:max_props]
    return props, total


def _collect_one_property(list_one, prop, rule, allowlist, cap):
    """Recolecta, para UNA propiedad, el contenido de sus carpetas objetivo + los
    archivos objetivo dentro de `core`. Devuelve (archivos, tuvo_core). Unidad de
    trabajo paralelizable (cada propiedad es independiente)."""
    contenedora = rule.get("carpetaContenedora", "core")
    core_path = posixpath.join(prop["path"], contenedora)
    if not remote_cleanup.is_within_allowlist(core_path, allowlist):
        return [], False
    try:
        core_entries = list_one(core_path)
    except Exception:
        return [], False   # propiedad sin carpeta `core` → se salta
    files: list[dict] = []
    for ce in core_entries:
        if ce.get("isLink"):
            continue
        if ce["isDir"]:
            if structural_cleanup.is_empty_target_folder(ce["path"], rule):
                sub, _t = _bfs_collect(list_one, [ce["path"]], [ce["path"]], cap)
                for s in sub:
                    s["propiedad"] = prop["name"]
                files.extend(sub)
        else:
            if structural_cleanup.is_target_file(ce["path"], rule):
                item = dict(ce); item["propiedad"] = prop["name"]
                files.append(item)
    return files, True


def _structural_collect(list_one, root, rule, allowlist, max_props, cap):
    """Versión SECUENCIAL (FTP/FTPS y tests). Descubre propiedades y recolecta.
    Devuelve (archivos, truncado, propiedades_totales, propiedades_con_core)."""
    props, total_props = _structural_discover_props(list_one, root, max_props)
    files: list[dict] = []
    truncated = False
    con_core = 0
    for prop in props:
        if len(files) >= cap:
            truncated = True
            break
        pf, had_core = _collect_one_property(list_one, prop, rule, allowlist, cap - len(files))
        if had_core:
            con_core += 1
        files.extend(pf)
        if len(files) >= cap:
            truncated = True
    return files, truncated, total_props, con_core


def _structural_report(list_one, server, rule, allowlist, root, max_props, cap):
    files, truncated, total, con_core = _structural_collect(list_one, root, rule, allowlist, max_props, cap)
    report = structural_cleanup.select_structural(files, rule, rule.get("limites") or {})
    report["truncated"] = truncated
    report["raiz"] = root
    report["propiedadesTotales"] = total
    report["propiedadesConCore"] = con_core
    if truncated:
        report["warnings"].append(
            f"Recorrido truncado en {cap} archivos. Usa 'límite de propiedades' para "
            f"probar por lotes, o sube CLEANUP_SIM_MAX_FILES."
        )
    return report, files


# ── Paralelismo + jobs en segundo plano (rendimiento a 800+ propiedades) ──────
# La travesía es E/S acotada por latencia (cada listdir ~200 ms). Se procesan las
# propiedades con varias conexiones SFTP simultáneas y el trabajo corre como JOB en
# segundo plano con progreso y cancelación (una petición síncrona daría timeout).
CLEANUP_JOBS: dict[str, dict] = {}
_JOBS_LOCK = threading.Lock()


def _cleanup_workers() -> int:
    # Windows OpenSSH limita ~10 sesiones concurrentes; 8 es un punto seguro.
    return max(1, min(16, int(os.getenv("CLEANUP_WORKERS", "8"))))


def _new_job(kind: str, server_id: str) -> str:
    jid = str(uuid.uuid4())
    with _JOBS_LOCK:
        # poda simple: conserva los 50 más recientes
        if len(CLEANUP_JOBS) > 60:
            for k in sorted(CLEANUP_JOBS, key=lambda k: CLEANUP_JOBS[k]["startedAt"])[:10]:
                CLEANUP_JOBS.pop(k, None)
        CLEANUP_JOBS[jid] = {
            "id": jid, "kind": kind, "serverId": server_id, "status": "running",
            "fase": "iniciando", "propiedadesTotales": 0, "propiedadesProcesadas": 0,
            "encontrados": 0, "result": None, "error": None, "cancel": False,
            "startedAt": datetime.now(timezone.utc).isoformat(),
        }
    return jid


def _job_progress(jid, procesadas=None, total=None, encontrados=None, fase=None) -> None:
    with _JOBS_LOCK:
        j = CLEANUP_JOBS.get(jid)
        if not j:
            return
        if procesadas is not None:  j["propiedadesProcesadas"] = procesadas
        if total is not None:       j["propiedadesTotales"] = total
        if encontrados is not None: j["encontrados"] = encontrados
        if fase is not None:        j["fase"] = fase


def _job_cancelled(jid) -> bool:
    with _JOBS_LOCK:
        j = CLEANUP_JOBS.get(jid)
        return bool(j and j["cancel"])


def _finish_job(jid, result) -> None:
    with _JOBS_LOCK:
        j = CLEANUP_JOBS.get(jid)
        if not j:
            return
        j["status"] = "cancelado" if j["cancel"] else "completado"
        j["result"] = result
        j["finishedAt"] = datetime.now(timezone.utc).isoformat()


def _fail_job(jid, msg) -> None:
    with _JOBS_LOCK:
        j = CLEANUP_JOBS.get(jid)
        if not j:
            return
        j["status"] = "error"; j["error"] = msg
        j["finishedAt"] = datetime.now(timezone.utc).isoformat()


def _run_pool(items, make_task, workers):
    """Ejecuta `make_task(item)` sobre cada item con N hilos, cada uno con su propia
    conexión SFTP (creada dentro de la tarea). Espera a que terminen todos."""
    import queue as _queue
    q = _queue.Queue()
    for it in items:
        q.put(it)
    n = min(workers, max(1, len(items)))

    def _drain():
        while True:
            try:
                it = q.get_nowait()
            except _queue.Empty:
                return
            make_task(it)

    ths = [threading.Thread(target=_drain, daemon=True) for _ in range(n)]
    for t in ths: t.start()
    for t in ths: t.join()


def _structural_collect_parallel(conn, root, rule, allowlist, max_props, cap, workers, jid=None):
    """Recorrido PARALELO por SFTP: descubre propiedades y las procesa con `workers`
    conexiones simultáneas. Reporta progreso y respeta cancelación."""
    import queue as _queue
    main_client = _sftp_client(conn); main_sftp = main_client.open_sftp()
    try:
        props, total_props = _structural_discover_props(lambda d: _sftp_list_one(main_sftp, d), root, max_props)
    finally:
        main_sftp.close(); main_client.close()
    if jid:
        _job_progress(jid, total=total_props, procesadas=0, fase="recorriendo")

    files: list[dict] = []
    con_core = 0
    processed = 0
    truncated = False
    lock = threading.Lock()
    stop = threading.Event()
    q = _queue.Queue()
    for p in props:
        q.put(p)

    def worker():
        nonlocal con_core, processed, truncated
        client = _sftp_client(conn); sftp = client.open_sftp()
        try:
            while not stop.is_set():
                try:
                    prop = q.get_nowait()
                except _queue.Empty:
                    break
                try:
                    pf, had_core = _collect_one_property(lambda d: _sftp_list_one(sftp, d), prop, rule, allowlist, cap)
                except Exception:
                    pf, had_core = [], False
                with lock:
                    processed += 1
                    if had_core:
                        con_core += 1
                    if len(files) < cap:
                        files.extend(pf)
                        if len(files) >= cap:
                            truncated = True
                    _job_progress(jid, procesadas=processed, encontrados=len(files)) if jid else None
                if jid and _job_cancelled(jid):
                    stop.set()
        finally:
            try: sftp.close(); client.close()
            except Exception: pass

    n = min(workers, max(1, len(props)))
    ths = [threading.Thread(target=worker, daemon=True) for _ in range(n)]
    for t in ths: t.start()
    for t in ths: t.join()
    return files, truncated, total_props, con_core


def _structural_gather(server, creds, rule, max_props, jid):
    """Recolecta el informe (SFTP en paralelo; FTP secuencial). Devuelve
    (report, conn, root, allowlist)."""
    root, allowlist = _validate_structural_root(server, rule)
    conn = _cleanup_conn(server, creds)
    cap = int(os.getenv("CLEANUP_SIM_MAX_FILES", "50000"))
    if conn.protocol in ("ftp", "ftps"):
        ftp = ftplib.FTP_TLS() if conn.protocol == "ftps" else ftplib.FTP()
        ftp.connect(conn.host, conn.port or 21, timeout=15)
        ftp.login(conn.username, conn.password)
        if conn.protocol == "ftps":
            ftp.prot_p()
        try:
            files, truncated, total, con_core = _structural_collect(
                lambda d: _ftp_list_one(ftp, d), root, rule, allowlist, max_props, cap)
        finally:
            try: ftp.quit()
            except Exception: pass
    else:
        files, truncated, total, con_core = _structural_collect_parallel(
            conn, root, rule, allowlist, max_props, cap, _cleanup_workers(), jid)
    report = structural_cleanup.select_structural(files, rule, rule.get("limites") or {})
    report["truncated"] = truncated
    report["raiz"] = root
    report["propiedadesTotales"] = total
    report["propiedadesConCore"] = con_core
    if truncated:
        report["warnings"].append(
            f"Recorrido truncado en {cap} archivos. Usa 'límite de propiedades' para "
            f"probar por lotes, o sube CLEANUP_SIM_MAX_FILES.")
    return report, conn, root, allowlist


def _structural_delete(conn, elegibles, modo, ruta_base, exec_id, actor, rule, server_id, jid):
    """Borra/mueve en PARALELO (SFTP) o secuencial (FTP) los archivos elegibles.
    Devuelve (moved, deleted, failed)."""
    moved: list = []; deleted: list = []; failed: list = []
    lock = threading.Lock()
    done = [0]
    total = len(elegibles)
    if jid:
        _job_progress(jid, procesadas=0, total=total, fase="borrando" if modo == "directo" else "moviendo")

    def _one(sftp_remove, sftp_move, e):
        try:
            if modo == "directo":
                sftp_remove(e["path"])
                with lock: deleted.append(e["path"])
            else:
                dst = remote_cleanup.quarantine_path(ruta_base, exec_id, e["path"])
                sftp_move(e["path"], dst)
                with lock: _record_quarantine(e, dst, exec_id, actor, rule, server_id, moved)
        except Exception as exc:
            with lock: failed.append({"path": e["path"], "error": _safe_error(exc)})
        with lock:
            done[0] += 1
            if jid: _job_progress(jid, procesadas=done[0])

    if conn.protocol in ("ftp", "ftps"):
        ftp = ftplib.FTP_TLS() if conn.protocol == "ftps" else ftplib.FTP()
        ftp.connect(conn.host, conn.port or 21, timeout=15)
        ftp.login(conn.username, conn.password)
        if conn.protocol == "ftps":
            ftp.prot_p()
        try:
            for e in elegibles:
                if jid and _job_cancelled(jid): break
                _one(lambda p: ftp.delete(p), lambda s, d: _ftp_move(ftp, s, d), e)
        finally:
            try: ftp.quit()
            except Exception: pass
    else:
        def task(e):
            if jid and _job_cancelled(jid):
                return
            # cada tarea usa una conexión de su hilo (creada perezosamente)
            tl = threading.current_thread()
            if not getattr(tl, "_sftp", None):
                tl._client = _sftp_client(conn); tl._sftp = tl._client.open_sftp()
            sftp = tl._sftp
            _one(lambda p: sftp.remove(p), lambda s, d: _sftp_move(sftp, s, d), e)

        # pool que además cierra la conexión de cada hilo al terminar
        import queue as _queue
        q = _queue.Queue()
        for e in elegibles: q.put(e)
        n = min(_cleanup_workers(), max(1, total))

        def drain():
            tl = threading.current_thread()
            try:
                while True:
                    if jid and _job_cancelled(jid): return
                    try: e = q.get_nowait()
                    except _queue.Empty: return
                    task(e)
            finally:
                if getattr(tl, "_sftp", None):
                    try: tl._sftp.close(); tl._client.close()
                    except Exception: pass

        ths = [threading.Thread(target=drain, daemon=True) for _ in range(n)]
        for t in ths: t.start()
        for t in ths: t.join()

    return moved, deleted, failed


def _run_structural_simulate_job(jid, server, creds, rule, max_props) -> None:
    try:
        report, _conn, _root, _allow = _structural_gather(server, creds, rule, max_props, jid)
        report["simulacion"] = True
        _finish_job(jid, report)
    except HTTPException as e:
        _fail_job(jid, getattr(e, "detail", str(e)))
    except Exception as exc:
        _fail_job(jid, _remote_error(exc, server))


def _run_structural_execute_job(jid, server, creds, rule, exec_id, actor,
                                conteo_esperado, modo, max_props) -> None:
    key = server["id"]
    started = datetime.now(timezone.utc).isoformat()
    try:
        report, conn, root, _allow = _structural_gather(server, creds, rule, max_props, jid)
        if _job_cancelled(jid):
            _finish_job(jid, {"cancelado": True, "movidos": 0, "borrados": 0}); return
        _check_conteo(report, conteo_esperado)   # gate: conteo == simulación
        ruta_base = server.get("rutaBase") or root
        moved, deleted, failed = _structural_delete(
            conn, report["elegibles"], modo, ruta_base, exec_id, actor, rule, server["id"], jid)
        record = {
            "id": exec_id, "tipo": "estructural", "modo": modo,
            "serverId": server["id"], "serverName": server.get("name"),
            "raiz": root, "actor": actor,
            "startedAt": started, "finishedAt": datetime.now(timezone.utc).isoformat(),
            "encontrados": report["encontrados"], "elegibles": report["elegiblesCount"],
            "movidos": len(moved), "borrados": len(deleted),
            "omitidos": report["excluidosCount"], "fallidos": len(failed),
            "espacioBytes": report["espacioLiberadoBytes"],
            "propiedadesAfectadas": report.get("propiedadesAfectadas", 0),
            "estado": "cancelado" if _job_cancelled(jid) else ("completado" if not failed else "parcial"),
            "errores": failed[:50], "cuarentena": modo != "directo", "truncated": report.get("truncated", False),
        }
        CLEANUP_EXECUTIONS[exec_id] = record
        _finish_job(jid, record)
    except HTTPException as e:
        _fail_job(jid, getattr(e, "detail", str(e)))
    except Exception as exc:
        _fail_job(jid, _remote_error(exc, server))
    finally:
        with _CLEANUP_LOCK:
            _CLEANUP_RUNNING.discard(key)


class StructuralSimulateBody(BaseModel):
    server_id:      str
    password:       str = ""
    privateKey:     str = ""
    passphrase:     str = ""
    rule:           dict
    maxPropiedades: int = 0     # 0 = todas


class StructuralExecuteBody(BaseModel):
    server_id:      str
    password:       str = ""
    privateKey:     str = ""
    passphrase:     str = ""
    rule:           dict
    modo:           Literal["cuarentena", "directo"] = "cuarentena"
    maxPropiedades: int = 0
    confirmar:      bool = False
    conteoEsperado: int | None = None


@app.post("/api/v1/cleanup/remote/structural/simulate")
def structural_simulate(body: StructuralSimulateBody, _=Depends(_current_user)):
    server = CLEANUP_SERVERS.get(body.server_id)
    if not server:
        raise HTTPException(404, "Servidor no encontrado")
    _validate_structural_root(server, body.rule)   # validación temprana (fail-closed)
    jid = _new_job("simulate", body.server_id)
    _backup_executor.submit(
        _run_structural_simulate_job, jid, server, _body_creds(body),
        body.rule, max(0, body.maxPropiedades))
    return {"jobId": jid}


@app.post("/api/v1/cleanup/remote/structural/execute")
def structural_execute(
    body: StructuralExecuteBody,
    user=Depends(_require_role("admin", "technician", "supervisor")),
):
    server = CLEANUP_SERVERS.get(body.server_id)
    if not server:
        raise HTTPException(404, "Servidor no encontrado")
    if not body.confirmar:
        raise HTTPException(400, "Debe confirmar la ejecución (confirmar=true) tras revisar la simulación.")
    _validate_structural_root(server, body.rule)   # fail-closed ANTES de bloquear

    key = body.server_id
    with _CLEANUP_LOCK:
        if key in _CLEANUP_RUNNING:
            raise HTTPException(409, "Ya hay una limpieza en curso sobre este servidor.")
        _CLEANUP_RUNNING.add(key)

    exec_id = str(uuid.uuid4())
    actor = user.get("full_name") or user.get("email")
    jid = _new_job("execute", body.server_id)
    _backup_executor.submit(
        _run_structural_execute_job, jid, server, _body_creds(body), body.rule,
        exec_id, actor, body.conteoEsperado, body.modo, max(0, body.maxPropiedades))
    return {"jobId": jid}


@app.get("/api/v1/cleanup/remote/structural/job/{jid}")
def structural_job_status(jid: str, _=Depends(_current_user)):
    j = CLEANUP_JOBS.get(jid)
    if not j:
        raise HTTPException(404, "Job no encontrado")
    return j


@app.post("/api/v1/cleanup/remote/structural/job/{jid}/cancel")
def structural_job_cancel(jid: str, _=Depends(_current_user)):
    with _JOBS_LOCK:
        j = CLEANUP_JOBS.get(jid)
        if not j:
            raise HTTPException(404, "Job no encontrado")
        j["cancel"] = True
    return {"cancelling": True}


# ── Retención automática (scheduler) ──────────────────────────────────────────
_scheduler = None


def _retention_job() -> None:
    """Conserva solo los N backups completados más recientes por base de datos."""
    if BACKUP_RETENTION_KEEP <= 0:
        return
    from collections import defaultdict
    by_db: dict[str, list[dict]] = defaultdict(list)
    for b in list(BACKUPS.values()):
        if b["status"] == "completed":
            by_db[b["databaseName"]].append(b)
    for _db, items in by_db.items():
        items.sort(key=lambda b: b["createdAt"])
        for b in items[:-BACKUP_RETENTION_KEEP]:
            BACKUPS.pop(b["id"], None)


@app.on_event("startup")
def _start_scheduler() -> None:
    global _scheduler
    if BACKUP_RETENTION_KEEP <= 0:
        return
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        print("  [WARN] apscheduler no instalado — retención automática deshabilitada")
        return
    _scheduler = BackgroundScheduler(daemon=True)
    _scheduler.add_job(_retention_job, "interval",
                       minutes=BACKUP_RETENTION_EVERY_MIN, id="backup_retention")
    _scheduler.start()
    print(f"  [OK] Retención automática: {BACKUP_RETENTION_KEEP} backups/BD "
          f"cada {BACKUP_RETENTION_EVERY_MIN} min")


@app.on_event("shutdown")
def _stop_scheduler() -> None:
    if _scheduler:
        _scheduler.shutdown(wait=False)


# ── Persistencia (C-7) ─────────────────────────────────────────────────────────
# Los datos ya no viven solo en RAM: se guardan en SQLite (infra_platform.db) y
# sobreviven a reinicios. Las sesiones de acceso conservan además su .log existente.
import persistence as _persist

_persist.register("users",             USERS)
_persist.register("backups",           BACKUPS)
_persist.register("access_sessions",   ACCESS_SESSIONS)
_persist.register("cleanup_folders",   CLEANUP_FOLDERS)
_persist.register("cleanup_rules",     CLEANUP_RULES)
_persist.register("cleanup_trash",     CLEANUP_TRASH)
_persist.register("cleanup_schedules",  CLEANUP_SCHEDULES)
_persist.register("cleanup_servers",    CLEANUP_SERVERS)
_persist.register("cleanup_executions", CLEANUP_EXECUTIONS)
_persist.register("cleanup_quarantine", CLEANUP_QUARANTINE)
_persist.register("ssh_hostkeys",       SSH_HOSTKEYS)
_persist.register("cleanup_history",    CLEANUP_HISTORY, kind="list")
_persist.init()
_persist.load()
_persist.save()   # persiste el admin semilla en el primer arranque (BD vacía)

_persist_flush = None


@app.middleware("http")
async def _persist_after_mutation(request, call_next):
    """Guarda tras cada operación que muta estado (durabilidad inmediata de acciones
    del usuario). Las actualizaciones asíncronas de backups las cubre el flush periódico."""
    response = await call_next(request)
    if request.method in ("POST", "PUT", "DELETE", "PATCH"):
        try:
            _persist.save()
        except Exception as exc:
            print(f"  [WARN] persistencia: fallo al guardar tras {request.method}: {exc}")
    return response


@app.on_event("startup")
def _start_persist_flush() -> None:
    """Hilo de respaldo: vuelca a disco cada 5 s para capturar cambios en segundo
    plano (p. ej. el estado final de un backup que corre en un hilo aparte)."""
    import threading
    global _persist_flush
    _persist_flush = threading.Event()

    def _loop() -> None:
        while not _persist_flush.wait(5.0):
            try:
                _persist.save()
            except Exception:
                pass

    threading.Thread(target=_loop, daemon=True, name="persist-flush").start()


@app.on_event("shutdown")
def _stop_persist_flush() -> None:
    if _persist_flush:
        _persist_flush.set()
    try:
        _persist.save()  # guardado final al apagar
    except Exception:
        pass


# ── Start ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    print("\n  [OK] Servidor DEV: http://localhost:8000")
    print("  [OK] Swagger Docs: http://localhost:8000/docs")
    print(f"  [OK] SQL Server:   {SQLSERVER_SERVER}:{SQLSERVER_PORT} (user={SQLSERVER_USER})")
    print("  [OK] Credenciales: admin@primee.local / Admin1234!")
    print("\n  Para configurar SQL Server, exporta antes de arrancar:")
    print("    $env:SQLSERVER_PASSWORD = 'tuPassword'")
    print("    $env:SQLSERVER_SERVER   = 'localhost'  (o IP\\INSTANCIA)\n")
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
