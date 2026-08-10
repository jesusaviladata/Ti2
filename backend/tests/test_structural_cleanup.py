"""
Pruebas del motor de limpieza ESTRUCTURAL (Ipsofactu: vaciar core/{Log,LogSec,
LogsRadian,Respuesta} y borrar core/BD_log.txt, replicado en cada propiedad).
Lógica pura, determinista, sin E/S.
"""
import structural_cleanup as sc

RULE = sc.default_rule()
ROOT = "/D:/Ipsofactu"


# ── Identificación de carpetas/archivos objetivo ────────────────────────────────
def test_carpeta_objetivo_dentro_de_core():
    assert sc.is_empty_target_folder(f"{ROOT}/Prop1/core/Log", RULE)
    assert sc.is_empty_target_folder(f"{ROOT}/Prop1/core/LogSec", RULE)
    assert sc.is_empty_target_folder(f"{ROOT}/Prop1/core/LogsRadian", RULE)
    assert sc.is_empty_target_folder(f"{ROOT}/Prop1/core/Respuesta", RULE)


def test_carpeta_objetivo_fuera_de_core_se_ignora():
    # Un 'Log' dentro de web u otra carpeta NO es objetivo (solo core).
    assert not sc.is_empty_target_folder(f"{ROOT}/Prop1/web/Log", RULE)
    assert not sc.is_empty_target_folder(f"{ROOT}/Prop1/otro/Respuesta", RULE)
    # 'core' en sí no es objetivo de vaciado.
    assert not sc.is_empty_target_folder(f"{ROOT}/Prop1/core", RULE)
    # Una carpeta con otro nombre dentro de core tampoco.
    assert not sc.is_empty_target_folder(f"{ROOT}/Prop1/core/Config", RULE)


def test_archivo_objetivo():
    assert sc.is_target_file(f"{ROOT}/Prop1/core/BD_log.txt", RULE)
    # Fuera de core no.
    assert not sc.is_target_file(f"{ROOT}/Prop1/web/BD_log.txt", RULE)
    # Otro archivo en core no.
    assert not sc.is_target_file(f"{ROOT}/Prop1/core/otro.txt", RULE)


def test_rutas_windows_con_backslash():
    # El cliente Windows puede mandar '\'; deben normalizarse.
    assert sc.is_empty_target_folder(f"{ROOT}\\Prop1\\core\\Log", RULE)
    assert sc.is_target_file(f"{ROOT}\\Prop1\\core\\BD_log.txt", RULE)


def test_match_insensible_a_mayusculas():
    # Windows no distingue mayúsculas: LOG / log / Core deben coincidir igual.
    assert sc.is_empty_target_folder(f"{ROOT}/Prop1/CORE/log", RULE)
    assert sc.is_empty_target_folder(f"{ROOT}/Prop1/Core/LOGSEC", RULE)
    assert sc.is_target_file(f"{ROOT}/Prop1/Core/bd_log.TXT", RULE)


# ── Clasificación (vaciado total con red de seguridad) ──────────────────────────
def test_vaciado_total_todo_elegible():
    files = [
        {"name": "a.log", "path": f"{ROOT}/P1/core/Log/a.log", "sizeBytes": 10, "propiedad": "P1"},
        {"name": "b.txt", "path": f"{ROOT}/P1/core/Log/b.txt", "sizeBytes": 20, "propiedad": "P1"},
        {"name": "sinext", "path": f"{ROOT}/P1/core/Respuesta/sinext", "sizeBytes": 5, "propiedad": "P1"},
        {"name": "BD_log.txt", "path": f"{ROOT}/P1/core/BD_log.txt", "sizeBytes": 7, "propiedad": "P1"},
    ]
    rep = sc.select_structural(files, RULE)
    assert rep["elegiblesCount"] == 4
    assert rep["espacioLiberadoBytes"] == 42
    assert rep["protegidosCount"] == 0


def test_extension_protegida_no_se_borra():
    # Aunque sea vaciado total, un .bak/.key/.exe se PROTEGE (defensa en profundidad).
    files = [
        {"name": "app.log", "path": f"{ROOT}/P1/core/Log/app.log", "sizeBytes": 10, "propiedad": "P1"},
        {"name": "backup.bak", "path": f"{ROOT}/P1/core/Log/backup.bak", "sizeBytes": 999, "propiedad": "P1"},
        {"name": "server.key", "path": f"{ROOT}/P1/core/Log/server.key", "sizeBytes": 1, "propiedad": "P1"},
    ]
    rep = sc.select_structural(files, RULE)
    assert rep["elegiblesCount"] == 1
    assert rep["protegidosCount"] == 2
    protegidos = {p["path"].split("/")[-1] for p in rep["protegidos"]}
    assert protegidos == {"backup.bak", "server.key"}


def test_cuarentena_nunca_se_toca():
    files = [
        {"name": "x.log", "path": f"{ROOT}/P1/core/Log/.cuarentena_limpieza/e1/x.log", "sizeBytes": 3, "propiedad": "P1"},
    ]
    rep = sc.select_structural(files, RULE)
    assert rep["elegiblesCount"] == 0
    assert rep["excluidos"][0]["reason"] == "en_cuarentena"


def test_agrupacion_por_propiedad():
    files = [
        {"name": "a.log", "path": f"{ROOT}/P1/core/Log/a.log", "sizeBytes": 1, "propiedad": "P1"},
        {"name": "b.log", "path": f"{ROOT}/P1/core/Log/b.log", "sizeBytes": 1, "propiedad": "P1"},
        {"name": "c.log", "path": f"{ROOT}/P2/core/Respuesta/c.log", "sizeBytes": 1, "propiedad": "P2"},
    ]
    rep = sc.select_structural(files, RULE)
    assert rep["propiedadesAfectadas"] == 2
    assert rep["porPropiedad"] == {"P1": 2, "P2": 1}


def test_limite_archivos():
    files = [
        {"name": f"f{i}.log", "path": f"{ROOT}/P1/core/Log/f{i}.log", "sizeBytes": 1, "modified": i, "propiedad": "P1"}
        for i in range(10)
    ]
    rep = sc.select_structural(files, RULE, limites={"maxArchivosPorEjecucion": 3})
    assert rep["elegiblesCount"] == 3
    assert any(x["reason"] == "limite_archivos" for x in rep["excluidos"])
    assert rep["warnings"]


def test_carpetas_se_excluyen_de_la_lista_plana():
    # Si la capa SFTP incluyera una carpeta por error, no cuenta como elegible.
    files = [
        {"name": "Log", "path": f"{ROOT}/P1/core/Log", "isDir": True, "propiedad": "P1"},
        {"name": "a.log", "path": f"{ROOT}/P1/core/Log/a.log", "sizeBytes": 1, "propiedad": "P1"},
    ]
    rep = sc.select_structural(files, RULE)
    assert rep["elegiblesCount"] == 1
