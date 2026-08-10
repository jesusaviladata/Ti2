r"""
Núcleo de seguridad y simulación de la Limpieza remota (Fase 1 + Fase 3).

Todo lo de este módulo es LÓGICA PURA, sin E/S de red: valida rutas contra una lista
blanca, bloquea recorridos de directorios (`../`) y calcula qué archivos se
eliminarían (simulación) SIN tocar nada. La E/S SFTP/FTP vive en dev_server.py y
llama a estas funciones. Así el corazón de seguridad es 100% testeable.

Convención de rutas: se trabaja en estilo POSIX (separador `/`). Si el Core es Windows
expuesto por SFTP, los `\` del cliente se convierten a `/` antes de validar.
"""
import fnmatch
import hashlib
import posixpath

# Carpeta de cuarentena (bajo la ruta base del servidor). Nunca debe limpiarse.
QUARANTINE_DIRNAME = ".cuarentena_limpieza"

# Extensiones que NUNCA deben eliminarse, pase lo que pase (defensa en profundidad).
# Se combinan con las 'extensionesBloqueadas' de cada regla.
PROTECTED_EXTENSIONS = {
    # ejecutables / scripts
    ".exe", ".dll", ".bat", ".sh", ".ps1", ".cmd", ".msi", ".com",
    # configuración
    ".conf", ".ini", ".yml", ".yaml", ".env", ".config", ".properties",
    # certificados / claves
    ".pem", ".crt", ".key", ".pfx", ".cer", ".p12",
    # respaldos / bases de datos
    ".bak", ".mdf", ".ldf", ".db", ".sqlite", ".bacpac", ".dmp",
}


def normalize_remote(path: str) -> str:
    """Normaliza una ruta remota a estilo POSIX absoluto, colapsando `.` y `..`
    de forma léxica. NO consulta el servidor (para SFTP se usa además sftp.normalize,
    que resuelve symlinks en el servidor)."""
    p = (path or "").replace("\\", "/").strip()
    if not p:
        return "/"
    norm = posixpath.normpath(p)
    return norm


def contains_traversal(raw_path: str) -> bool:
    """True si la ruta contiene un segmento `..` (recorrido de directorios)."""
    p = (raw_path or "").replace("\\", "/")
    return ".." in p.split("/")


def is_within_allowlist(resolved_path: str, roots: list[str]) -> bool:
    """True si `resolved_path` es exactamente una raíz permitida o está contenida
    dentro de ella. Si `roots` está vacía → SIEMPRE False (fail-closed)."""
    if not roots:
        return False
    r = normalize_remote(resolved_path).rstrip("/") or "/"
    for root in roots:
        root_n = normalize_remote(root).rstrip("/") or "/"
        if r == root_n or r.startswith(root_n + "/"):
            return True
    return False


def _matches_any(name: str, path: str, patterns: list[str]) -> bool:
    """True si el nombre o la ruta coinciden con algún patrón glob de exclusión."""
    posix_path = (path or "").replace("\\", "/")
    for pat in patterns or []:
        if fnmatch.fnmatch(name, pat) or fnmatch.fnmatch(posix_path, pat):
            return True
    return False


def compute_age_days(modified_epoch, now_epoch: float):
    if not modified_epoch:
        return None
    return (now_epoch - float(modified_epoch)) / 86400.0


def quarantine_path(ruta_base: str, exec_id: str, original_path: str) -> str:
    """Ruta destino en cuarentena para un archivo. Incluye un hash corto de la ruta
    original para evitar colisiones entre archivos con el mismo nombre en subcarpetas
    distintas. La restauración usa los metadatos (ruta original guardada aparte)."""
    base = normalize_remote(ruta_base).rstrip("/")
    name = posixpath.basename(original_path.replace("\\", "/"))
    h = hashlib.sha1(original_path.encode("utf-8")).hexdigest()[:8]
    return f"{base}/{QUARANTINE_DIRNAME}/{exec_id}/{h}_{name}"


def select_candidates(entries: list[dict], rule: dict, now_epoch: float) -> dict:
    """
    Simulación pura (read-only). Dada una lista PLANA de entradas ya recolectadas por
    la capa SFTP/FTP y una regla, devuelve qué se eliminaría y qué se excluye (con
    motivo), sin modificar nada.

    entry: {name, path, sizeBytes, modified (epoch|None), isDir}
    Devuelve el informe de simulación con elegibles, excluidos+motivo, protegidos,
    espacio, totales y advertencias.
    """
    allowed_ext = [e.lower() for e in rule.get("extensionesPermitidas", []) or []]
    blocked_ext = {e.lower() for e in rule.get("extensionesBloqueadas", []) or []} | PROTECTED_EXTENSIONS
    exclusions  = rule.get("exclusiones", []) or []
    min_age     = float(rule.get("antiguedadMinimaDias", 0) or 0)
    recent_h    = float(rule.get("noModificadoUltimasHoras", 0) or 0)
    del_dirs    = bool(rule.get("eliminarCarpetas", False))
    limites     = rule.get("limites", {}) or {}
    max_files   = int(limites.get("maxArchivosPorEjecucion", 0) or 0)
    max_bytes   = int(limites.get("maxBytesPorEjecucion", 0) or 0)

    eligible: list[dict] = []
    excluded: list[dict] = []
    protected: list[dict] = []

    for e in entries:
        name = e.get("name", "")
        path = e.get("path", "")
        size = int(e.get("sizeBytes", 0) or 0)
        is_dir = bool(e.get("isDir", False))
        mod = e.get("modified")
        ext = posixpath.splitext(name)[1].lower()

        if is_dir and not del_dirs:
            excluded.append({"path": path, "reason": "es_carpeta"}); continue
        if ext in blocked_ext:
            reason = f"extension_protegida ({ext})"
            protected.append({"path": path, "reason": reason})
            excluded.append({"path": path, "reason": reason}); continue
        if allowed_ext and ext not in allowed_ext:
            excluded.append({"path": path, "reason": "extension_no_autorizada"}); continue
        if _matches_any(name, path, exclusions):
            excluded.append({"path": path, "reason": "regla_exclusion"}); continue
        age = compute_age_days(mod, now_epoch)
        if min_age and (age is None or age < min_age):
            excluded.append({"path": path, "reason": f"no_cumple_antiguedad (<{min_age:g}d)"}); continue
        if recent_h and mod and (now_epoch - float(mod)) < recent_h * 3600:
            excluded.append({"path": path, "reason": f"modificado_reciente (<{recent_h:g}h)"}); continue

        eligible.append(e)

    # Orden determinista: más viejos primero (se limpian antes) para aplicar límites.
    eligible.sort(key=lambda e: e.get("modified") or 0)

    warnings: list[str] = []
    limited: list[dict] = []
    total_bytes = 0
    for e in eligible:
        size = int(e.get("sizeBytes", 0) or 0)
        if max_files and len(limited) >= max_files:
            excluded.append({"path": e["path"], "reason": "limite_archivos"})
            continue
        if max_bytes and (total_bytes + size) > max_bytes:
            excluded.append({"path": e["path"], "reason": "limite_espacio"})
            continue
        limited.append(e)
        total_bytes += size

    if max_files and len(eligible) > max_files:
        warnings.append(f"Se alcanzó el límite de {max_files} archivos; el resto quedó fuera de esta ejecución.")
    if max_bytes and sum(int(x.get('sizeBytes', 0) or 0) for x in eligible) > max_bytes:
        warnings.append(f"Se alcanzó el límite de espacio; el resto quedó fuera de esta ejecución.")

    return {
        "encontrados":          len(entries),
        "elegibles":            limited,
        "elegiblesCount":       len(limited),
        "espacioLiberadoBytes": total_bytes,
        "excluidos":            excluded,
        "excluidosCount":       len(excluded),
        "protegidos":           protected,
        "protegidosCount":      len(protected),
        "warnings":             warnings,
    }
