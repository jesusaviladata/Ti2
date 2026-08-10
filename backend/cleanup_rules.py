"""
Política de conservación de la limpieza inteligente, lógica pura (C-11). Dada una
lista de archivos coincidentes y una regla, devuelve los archivos ELEGIBLES para
borrado. Extraído de dev_server.py para probarlo de forma aislada.

Formato de archivo esperado: dicts con al menos `ageDays` (float) y `modifiedAt`
(ISO string ordenable). Formato de regla: `keep` in {all, latest, latest_n, none},
`keepN` (int), `minAgeDays` (float).
"""


def apply_keep_policy(files: list[dict], rule: dict) -> list[dict]:
    keep    = rule.get("keep", "latest")
    keep_n  = int(rule.get("keepN", 1))
    min_age = float(rule.get("minAgeDays", 0))

    # Filtrar por antigüedad mínima
    candidates = [f for f in files if f["ageDays"] >= min_age]

    if keep == "all":
        return []  # conservar todo, no borrar nada
    if keep == "latest":
        if len(candidates) <= 1:
            return []
        candidates.sort(key=lambda f: f["modifiedAt"])
        return candidates[:-1]   # borrar todos menos el más nuevo
    if keep == "latest_n":
        if keep_n <= 0:
            return candidates        # conservar 0 → borrar todos
        if len(candidates) <= keep_n:
            return []
        candidates.sort(key=lambda f: f["modifiedAt"])
        return candidates[:-keep_n]
    if keep == "none":
        return candidates        # borrar todos los coincidentes

    return candidates
