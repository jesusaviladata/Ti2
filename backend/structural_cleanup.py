r"""
Limpieza ESTRUCTURAL (para Ipsofactu: ~800+ propiedades bajo una raíz).

A diferencia de la limpieza por extensión+antigüedad (`remote_cleanup.select_candidates`),
aquí la regla es POR ESTRUCTURA:

    <raíz>/<propiedad>/<contenedora=core>/<carpetaObjetivo>/**   → vaciar TODO el contenido
    <raíz>/<propiedad>/<contenedora=core>/<archivoObjetivo>       → borrar ese archivo

Se replica en cada propiedad hija de la raíz. NUNCA se toca `web` ni la tercera carpeta:
solo se desciende a carpetas cuyo nombre está en `carpetaContenedora` y, dentro, a las
carpetas de `vaciarCarpetas`. La carpeta objetivo SE CONSERVA (solo se vacía su contenido).

Todo aquí es LÓGICA PURA y testeable. La E/S SFTP/FTP (descubrir propiedades, listar y
borrar) vive en dev_server.py y usa estas funciones para decidir dónde descender y qué
clasificar. Como red de seguridad se respetan siempre PROTECTED_EXTENSIONS.
"""
import posixpath

from remote_cleanup import (
    PROTECTED_EXTENSIONS,
    QUARANTINE_DIRNAME,
    normalize_remote,
)


def _base(path: str) -> str:
    return posixpath.basename(normalize_remote(path).rstrip("/"))


def _parent_name(path: str) -> str:
    return posixpath.basename(posixpath.dirname(normalize_remote(path).rstrip("/")))


def default_rule() -> dict:
    """Regla por defecto para el caso Ipsofactu (sirve de plantilla en la UI)."""
    return {
        "tipo":              "estructural",
        "carpetaContenedora": "core",
        "vaciarCarpetas":    ["Log", "LogSec", "LogsRadian", "Respuesta"],
        "borrarArchivos":    ["BD_log.txt"],
    }


def is_empty_target_folder(path: str, rule: dict) -> bool:
    """True si `path` es una carpeta cuyo CONTENIDO debe vaciarse: su nombre está en
    `vaciarCarpetas` y su carpeta padre se llama como `carpetaContenedora` (ej. 'core').
    Así solo se vacían las de `core`, nunca las de `web` u otra.
    Comparación insensible a mayúsculas/minúsculas (Windows no distingue)."""
    contenedora = rule.get("carpetaContenedora", "core").lower()
    vaciar = {v.lower() for v in (rule.get("vaciarCarpetas", []) or [])}
    return _base(path).lower() in vaciar and _parent_name(path).lower() == contenedora


def is_target_file(path: str, rule: dict) -> bool:
    """True si `path` es un archivo a borrar por nombre (ej. BD_log.txt) ubicado
    directamente dentro de una carpeta `carpetaContenedora` (core).
    Comparación insensible a mayúsculas/minúsculas (Windows no distingue)."""
    contenedora = rule.get("carpetaContenedora", "core").lower()
    borrar = {b.lower() for b in (rule.get("borrarArchivos", []) or [])}
    return _base(path).lower() in borrar and _parent_name(path).lower() == contenedora


def is_quarantine(path: str) -> bool:
    """True si la ruta está dentro de la carpeta de cuarentena (nunca se limpia)."""
    return QUARANTINE_DIRNAME in normalize_remote(path).split("/")


def classify_file(entry: dict) -> tuple[bool, str | None]:
    """Vaciado total: un archivo ya recolectado (dentro de una carpeta objetivo, o un
    archivo objetivo) es ELEGIBLE salvo que su extensión esté protegida (red de
    seguridad, defensa en profundidad). Devuelve (elegible, motivo_si_excluido)."""
    name = entry.get("name", "")
    ext = posixpath.splitext(name)[1].lower()
    if ext in PROTECTED_EXTENSIONS:
        return False, f"extension_protegida ({ext})"
    if is_quarantine(entry.get("path", "")):
        return False, "en_cuarentena"
    return True, None


def select_structural(files: list[dict], rule: dict, limites: dict | None = None) -> dict:
    """Dada la lista PLANA de archivos ya recolectados por la capa SFTP (solo los que
    están dentro de carpetas objetivo o son archivos objetivo), clasifica en elegibles /
    protegidos y aplica límites opcionales. Mismo formato de informe que
    `remote_cleanup.select_candidates` para reutilizar la UI.

    `files` incluye además, por cada entrada, la clave opcional `propiedad` (nombre de la
    propiedad) para agrupar el informe.
    """
    limites = limites or {}
    max_files = int(limites.get("maxArchivosPorEjecucion", 0) or 0)
    max_bytes = int(limites.get("maxBytesPorEjecucion", 0) or 0)

    eligible: list[dict] = []
    excluded: list[dict] = []
    protected: list[dict] = []
    por_propiedad: dict[str, int] = {}

    for e in files:
        if bool(e.get("isDir", False)):
            excluded.append({"path": e.get("path", ""), "reason": "es_carpeta"})
            continue
        ok, reason = classify_file(e)
        if not ok:
            excluded.append({"path": e.get("path", ""), "reason": reason})
            if reason and reason.startswith("extension_protegida"):
                protected.append({"path": e.get("path", ""), "reason": reason})
            continue
        eligible.append(e)

    # Determinista: más viejos primero (para aplicar límites de forma estable).
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
        prop = e.get("propiedad") or "?"
        por_propiedad[prop] = por_propiedad.get(prop, 0) + 1

    if max_files and len(eligible) > max_files:
        warnings.append(f"Se alcanzó el límite de {max_files} archivos; el resto quedó fuera de esta ejecución.")

    return {
        "tipo":                 "estructural",
        "encontrados":          len(files),
        "elegibles":            limited,
        "elegiblesCount":       len(limited),
        "espacioLiberadoBytes": total_bytes,
        "excluidos":            excluded,
        "excluidosCount":       len(excluded),
        "protegidos":           protected,
        "protegidosCount":      len(protected),
        "propiedadesAfectadas": len(por_propiedad),
        "porPropiedad":         por_propiedad,
        "warnings":             warnings,
    }
