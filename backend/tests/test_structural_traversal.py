"""
Prueba de la TRAVESÍA estructural (dev_server._structural_collect) con un árbol
Ipsofactu simulado en memoria — sin SFTP real. Valida: descubrimiento de propiedades,
scope a `core`, recolección recursiva de carpetas objetivo + BD_log.txt, y que `web`
y las carpetas no-objetivo se ignoran.
"""
import structural_cleanup as sc
import dev_server as ds

ROOT = "/D:/Ipsofactu"


def _e(path, is_dir, size=0):
    import posixpath
    return {
        "name": posixpath.basename(path.rstrip("/")),
        "path": path, "isDir": is_dir, "isLink": False,
        "sizeBytes": size, "modified": 1000,
    }


# Árbol simulado: 3 propiedades (P3 sin core), web con un Log que NO debe tocarse.
TREE = {
    ROOT: [_e(f"{ROOT}/P1", True), _e(f"{ROOT}/P2", True), _e(f"{ROOT}/P3", True),
           _e(f"{ROOT}/.cuarentena_limpieza", True)],
    f"{ROOT}/P1/core": [
        _e(f"{ROOT}/P1/core/Log", True), _e(f"{ROOT}/P1/core/Respuesta", True),
        _e(f"{ROOT}/P1/core/Config", True),                       # no objetivo
        _e(f"{ROOT}/P1/core/BD_log.txt", False, 7),              # archivo objetivo
        _e(f"{ROOT}/P1/core/otro.txt", False, 3),               # no objetivo
    ],
    f"{ROOT}/P1/core/Log": [_e(f"{ROOT}/P1/core/Log/a.log", False, 10),
                            _e(f"{ROOT}/P1/core/Log/b.log", False, 20)],
    f"{ROOT}/P1/core/Respuesta": [_e(f"{ROOT}/P1/core/Respuesta/r1.tmp", False, 5)],
    f"{ROOT}/P1/core/Config": [_e(f"{ROOT}/P1/core/Config/keep.ini", False, 1)],
    f"{ROOT}/P2/core": [_e(f"{ROOT}/P2/core/LogSec", True)],
    f"{ROOT}/P2/core/LogSec": [_e(f"{ROOT}/P2/core/LogSec/s.log", False, 8)],
    # web con un Log que NUNCA debe listarse ni tocarse
    f"{ROOT}/P1/web": [_e(f"{ROOT}/P1/web/Log", True)],
    f"{ROOT}/P1/web/Log": [_e(f"{ROOT}/P1/web/Log/secret.log", False, 99)],
    # P3 NO tiene core
}


def _list_one(path):
    if path in TREE:
        return TREE[path]
    raise FileNotFoundError(path)


def test_structural_collect():
    rule = sc.default_rule()
    files, truncated, total, con_core = ds._structural_collect(
        _list_one, ROOT, rule, [ROOT], max_props=0, cap=10000,
    )
    names = sorted(f["path"] for f in files)
    assert names == [
        f"{ROOT}/P1/core/BD_log.txt",
        f"{ROOT}/P1/core/Log/a.log",
        f"{ROOT}/P1/core/Log/b.log",
        f"{ROOT}/P1/core/Respuesta/r1.tmp",
        f"{ROOT}/P2/core/LogSec/s.log",
    ]
    # web/Log/secret.log NO aparece; Config/keep.ini NO aparece; otro.txt NO aparece.
    assert not truncated
    assert total == 3          # P1, P2, P3 (cuarentena excluida)
    assert con_core == 2       # solo P1 y P2 tienen core
    # cada archivo lleva su propiedad
    props = {f["propiedad"] for f in files}
    assert props == {"P1", "P2"}


def test_structural_collect_respeta_max_props():
    rule = sc.default_rule()
    files, _, total, con_core = ds._structural_collect(
        _list_one, ROOT, rule, [ROOT], max_props=1, cap=10000,
    )
    # Solo la primera propiedad (P1, orden alfabético) → sin s.log de P2
    assert all(f["propiedad"] == "P1" for f in files)
    assert con_core == 1


def test_structural_report_shape():
    rule = sc.default_rule()
    report, _files = ds._structural_report(_list_one, {"rutaBase": ROOT}, rule, [ROOT], ROOT, 0, 10000)
    assert report["elegiblesCount"] == 5
    assert report["propiedadesAfectadas"] == 2
    assert report["porPropiedad"] == {"P1": 4, "P2": 1}
    assert report["raiz"] == ROOT
