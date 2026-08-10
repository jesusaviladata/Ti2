"""
Almacén de sesión para revocación de tokens (blocklist) y rate-limiting de login.

Dos backends con la MISMA interfaz (C-10):
- RedisSessionStore: compartido entre workers y con expiración automática. Se usa si
  `REDIS_URL` está definida, el paquete `redis` está instalado y la conexión responde.
- MemorySessionStore: fallback en memoria de proceso (comportamiento original). Válido
  para un único proceso (dev / LAN sin Redis).

La selección es automática al importar; `store` es el singleton a usar.
"""
import os
import threading
import time


class MemorySessionStore:
    """Fallback en memoria (un solo proceso). Rate-limit por ventana deslizante."""

    backend = "memory"

    def __init__(self) -> None:
        self._revoked: set[str] = set()
        self._fails: dict[str, list[float]] = {}
        self._lock = threading.RLock()

    # ── Blocklist de tokens ─────────────────────────────────────────────────────
    def revoke(self, jti: str, ttl_seconds: int = 0) -> None:  # ttl ignorado en memoria
        if jti:
            with self._lock:
                self._revoked.add(jti)

    def is_revoked(self, jti: str) -> bool:
        return bool(jti) and jti in self._revoked

    # ── Rate-limit de login ─────────────────────────────────────────────────────
    def recent_login_fails(self, key: str, window: float) -> int:
        now = time.monotonic()
        with self._lock:
            fails = [t for t in self._fails.get(key, []) if now - t < window]
            self._fails[key] = fails
            return len(fails)

    def record_login_fail(self, key: str, window: float) -> None:
        with self._lock:
            self._fails.setdefault(key, []).append(time.monotonic())

    def reset_login_fails(self, key: str) -> None:
        with self._lock:
            self._fails.pop(key, None)


class RedisSessionStore:
    """Backend Redis: blocklist con TTL y rate-limit por contador con expiración."""

    backend = "redis"

    def __init__(self, client) -> None:
        self._r = client

    def revoke(self, jti: str, ttl_seconds: int = 0) -> None:
        if not jti:
            return
        # TTL: el token no necesita seguir en la blocklist tras expirar. Mínimo 60 s.
        self._r.set(f"revoked:{jti}", "1", ex=max(60, ttl_seconds or 0))

    def is_revoked(self, jti: str) -> bool:
        return bool(jti) and self._r.exists(f"revoked:{jti}") == 1

    def recent_login_fails(self, key: str, window: float) -> int:
        val = self._r.get(f"loginfail:{key}")
        return int(val) if val else 0

    def record_login_fail(self, key: str, window: float) -> None:
        k = f"loginfail:{key}"
        # INCR y fijar expiración de la ventana en el primer fallo (ventana fija).
        pipe = self._r.pipeline()
        pipe.incr(k)
        pipe.expire(k, int(window))
        pipe.execute()

    def reset_login_fails(self, key: str) -> None:
        self._r.delete(f"loginfail:{key}")


def _build_store():
    url = os.getenv("REDIS_URL")
    if not url:
        return MemorySessionStore()
    try:
        import redis  # dependencia opcional
        client = redis.Redis.from_url(url, decode_responses=True, socket_connect_timeout=2)
        client.ping()
        print(f"  [OK] session_store: Redis ({url})")
        return RedisSessionStore(client)
    except Exception as exc:
        print(f"  [WARN] session_store: Redis no disponible ({exc}); usando memoria.")
        return MemorySessionStore()


store = _build_store()
