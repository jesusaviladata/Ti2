"""
Helpers puros de SQL Server, sin estado de la aplicación (C-11). Extraídos de
dev_server.py para poder probarlos de forma aislada y reducir el monolito.
"""
import re
from pathlib import Path

# Mapa de modos de cifrado (valor de la UI → valor del driver ODBC).
ENCRYPT_MAP = {
    "mandatory": "yes",
    "optional":  "no",
    "strict":    "strict",
    "yes":       "yes",
    "no":        "no",
}


def safe_error(exc, limit: int = 512) -> str:
    """Redacta credenciales (PWD/UID/PASSWORD/USER) de un mensaje de error antes de
    exponerlo al cliente. Devuelve como máximo `limit` caracteres."""
    msg = re.sub(r"(PWD|UID|PASSWORD|USER)=[^;]*", r"\1=***", str(exc), flags=re.IGNORECASE)
    return msg[:limit]


def stripe_paths(base: str, stripes: int) -> list[str]:
    """Divide un destino de backup en N archivos paralelos (striping). Con stripes<=1
    devuelve [base]; con N>1 devuelve rutas con sufijo _part{i}of{N}."""
    if stripes <= 1:
        return [base]
    p = Path(base)
    return [str(p.with_name(f"{p.stem}_part{i + 1}of{stripes}{p.suffix}")) for i in range(stripes)]
