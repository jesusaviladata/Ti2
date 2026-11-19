"""Descubrimiento de carpetas de propiedad Ipsofactu bajo una raíz.

Una propiedad es una carpeta que contiene la carpeta contenedora (``core``) con
la "firma" de Ipsofactu: carpetas y archivos objetivo de la limpieza.

* Nivel 1 (hijas directas de la raíz): basta con que exista ``core``. Es el
  caso histórico, cuando la raíz era la carpeta de propiedades. Si la raíz
  es una unidad completa (``D:\\``), se exige la firma completa también aquí.
* Niveles más profundos: ``core`` debe contener al menos ``MIN_DEEP_SIGNATURE``
  objetivos (por ejemplo ``Log`` y ``LogSec``). Así una aplicación ajena con su
  propia carpeta ``core\\Log`` no se toma por una propiedad.

Nunca se siguen enlaces ni puntos de reanálisis, no se desciende dentro de una
propiedad ya encontrada y se omiten carpetas de sistema conocidas.
"""

from __future__ import annotations

import os
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .explorer import _is_reparse_point

DEFAULT_MAX_DEPTH = 8
MIN_DEEP_SIGNATURE = 2
DEFAULT_MAX_FOLDERS = 250_000

SKIPPED_FOLDERS = frozenset(
    name.casefold()
    for name in (
        ".dataexpress-quarantine",
        "$recycle.bin",
        "system volume information",
        "config.msi",
        "recovery",
        "windows",
        "program files",
        "program files (x86)",
        "programdata",
        "msocache",
        "node_modules",
        ".git",
    )
)


@dataclass
class DiscoveredProperty:
    path: Path
    relative: str
    depth: int
    signature: int


@dataclass
class DiscoveryResult:
    properties: list[DiscoveredProperty] = field(default_factory=list)
    scanned_folders: int = 0
    errors: list[dict[str, str]] = field(default_factory=list)
    truncated: bool = False


def _child_directories(path: Path) -> dict[str, os.DirEntry]:
    children: dict[str, os.DirEntry] = {}
    with os.scandir(path) as iterator:
        for entry in iterator:
            try:
                if entry.is_dir(follow_symlinks=False) and not entry.is_symlink():
                    children[entry.name.casefold()] = entry
            except OSError:
                continue
    return children


def _signature(core: Path, target_folders: list[str], target_files: list[str]) -> int:
    try:
        with os.scandir(core) as iterator:
            names = {}
            for entry in iterator:
                if entry.is_symlink():
                    continue
                names[entry.name.casefold()] = entry
    except OSError:
        return 0
    score = 0
    for name in target_folders:
        entry = names.get(name.casefold())
        if entry is not None and entry.is_dir(follow_symlinks=False):
            score += 1
    for name in target_files:
        entry = names.get(name.casefold())
        if entry is not None and entry.is_file(follow_symlinks=False):
            score += 1
    return score


def discover_properties(
    root: Path,
    *,
    container: str = "core",
    target_folders: list[str],
    target_files: list[str],
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_folders: int = DEFAULT_MAX_FOLDERS,
    max_seconds: float | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> DiscoveryResult:
    """Recorre ``root`` en anchura y devuelve las propiedades encontradas, ordenadas."""
    result = DiscoveryResult()
    started = time.monotonic()
    container_key = container.casefold()
    total_targets = max(1, len(target_folders) + len(target_files))
    required_deep = min(MIN_DEEP_SIGNATURE, total_targets)
    # Hijas directas de una carpeta de propiedades (raíz histórica): basta con ``core``.
    # Si la raíz es una unidad (D:\), incluso el primer nivel exige la firma completa.
    required_first = required_deep if root.parent == root else 0
    queue: deque[tuple[Path, int]] = deque([(root, 0)])

    while queue:
        if max_seconds is not None and time.monotonic() - started > max_seconds:
            result.truncated = True
            break
        if result.scanned_folders >= max_folders:
            result.truncated = True
            break
        current, depth = queue.popleft()
        try:
            children = _child_directories(current)
        except PermissionError:
            result.errors.append({"property": _relative(current, root), "code": "FOLDER_ACCESS_DENIED"})
            continue
        except OSError:
            result.errors.append({"property": _relative(current, root), "code": "FOLDER_READ_FAILED"})
            continue
        result.scanned_folders += 1
        if progress and result.scanned_folders % 200 == 0:
            progress(result.scanned_folders, result.scanned_folders + len(queue))

        core_entry = children.get(container_key)
        if depth >= 1 and core_entry is not None and not _is_reparse_point(Path(core_entry.path)):
            signature = _signature(Path(core_entry.path), target_folders, target_files)
            if signature >= (required_first if depth == 1 else required_deep):
                result.properties.append(
                    DiscoveredProperty(
                        path=current,
                        relative=_relative(current, root),
                        depth=depth,
                        signature=signature,
                    )
                )
                # Una propiedad no contiene otras propiedades: no se desciende.
                continue

        if depth >= max_depth:
            continue
        for key in sorted(children):
            if key in SKIPPED_FOLDERS or key.startswith("$"):
                continue
            child = Path(children[key].path)
            if _is_reparse_point(child):
                continue
            queue.append((child, depth + 1))

    result.properties.sort(key=lambda item: item.relative.casefold())
    if progress:
        progress(result.scanned_folders, result.scanned_folders)
    return result


def _relative(path: Path, root: Path) -> str:
    try:
        relative = str(path.relative_to(root))
    except ValueError:
        return path.name
    return "." if relative in {"", "."} else relative



def is_system_drive_root(root: Path) -> bool:
    """True si ``root`` es la raíz de la unidad donde está instalado Windows."""
    if root.parent != root:
        return False
    system_drive = os.environ.get("SystemDrive", "C:").rstrip("\\/").casefold()
    return str(root).rstrip("\\/").casefold() == system_drive or str(root) in {"/", "\\"}
