"""
Persistencia ligera para dev_server.py usando `sqlite3` de la biblioteca estándar
(sin dependencias externas — funciona en Windows/LAN sin Docker ni PostgreSQL).

Modelo documento: cada colección se guarda en una tabla (id TEXT PRIMARY KEY,
data TEXT con JSON). Las colecciones en memoria (dicts/listas de dev_server.py) se
registran una vez y se vuelcan/cargan en bloque.

Escalabilidad (C-7): para migrar a PostgreSQL en producción basta reemplazar este
módulo por una capa equivalente que exponga la misma API (register/init/load/save),
sin tocar la lógica de negocio. La ruta de la BD es configurable con la variable de
entorno DB_PATH.
"""
import json
import os
import sqlite3
import threading
from pathlib import Path

DB_PATH = os.getenv("DB_PATH", str(Path(__file__).parent / "infra_platform.db"))

_lock = threading.RLock()
# name -> (container, kind)  con kind in {"dict", "list"}
_collections: dict[str, tuple] = {}


def register(name: str, container, kind: str = "dict") -> None:
    """Registra una colección en memoria para persistirla. `kind`:
    - "dict": diccionario id->documento (la clave del dict es el id de la fila).
    - "list": lista de documentos; cada elemento debe tener una clave 'id'."""
    _collections[name] = (container, kind)


def _connect() -> sqlite3.Connection:
    cn = sqlite3.connect(DB_PATH, timeout=10)
    cn.execute("PRAGMA journal_mode=WAL")  # mejor concurrencia lectura/escritura
    return cn


def init() -> None:
    """Crea las tablas si no existen. Llamar tras registrar todas las colecciones."""
    with _lock:
        cn = _connect()
        try:
            for name in _collections:
                cn.execute(
                    f'CREATE TABLE IF NOT EXISTS "{name}" '
                    f'(id TEXT PRIMARY KEY, data TEXT NOT NULL)'
                )
            cn.commit()
        finally:
            cn.close()


def load() -> None:
    """Carga cada colección desde la BD. Si la tabla tiene filas, reemplaza el
    contenido en memoria; si está vacía, se conserva el contenido inicial
    (por ejemplo, el usuario admin semilla del primer arranque)."""
    with _lock:
        cn = _connect()
        try:
            for name, (container, kind) in _collections.items():
                rows = cn.execute(f'SELECT id, data FROM "{name}"').fetchall()
                if not rows:
                    continue
                if kind == "dict":
                    container.clear()
                    for _id, data in rows:
                        container[_id] = json.loads(data)
                else:  # list
                    container.clear()
                    container.extend(json.loads(data) for _id, data in rows)
        finally:
            cn.close()


def save() -> None:
    """Vuelca todas las colecciones a la BD (upsert + purga de huérfanos).
    Thread-safe: puede llamarse desde el hilo de backups o el de flush periódico."""
    with _lock:
        cn = _connect()
        try:
            for name, (container, kind) in _collections.items():
                if kind == "dict":
                    items = list(container.items())
                    ids = [str(k) for k, _ in items]
                    payload = [
                        (str(k), json.dumps(v, ensure_ascii=False, default=str))
                        for k, v in items
                    ]
                else:  # list — usa item['id'] como clave
                    ids = [str(x.get("id")) for x in container]
                    payload = [
                        (str(x.get("id")), json.dumps(x, ensure_ascii=False, default=str))
                        for x in container
                    ]

                if payload:
                    cn.executemany(
                        f'INSERT INTO "{name}" (id, data) VALUES (?, ?) '
                        f'ON CONFLICT(id) DO UPDATE SET data=excluded.data',
                        payload,
                    )
                # purgar filas que ya no existen en memoria (borrados)
                if ids:
                    placeholders = ",".join("?" * len(ids))
                    cn.execute(f'DELETE FROM "{name}" WHERE id NOT IN ({placeholders})', ids)
                else:
                    cn.execute(f'DELETE FROM "{name}"')
            cn.commit()
        finally:
            cn.close()
