from __future__ import annotations

import asyncio
import re
from typing import Any

from app.core.errors import DependencyUnavailableError, DomainError


def _safe_error(exc: Exception) -> str:
    return re.sub(
        r"(PWD|UID|PASSWORD|USER)=[^;]*",
        r"\1=***",
        str(exc),
        flags=re.IGNORECASE,
    )[:512]


def _connection_string(data: dict[str, Any]) -> str:
    auth = data.get("authentication", "sql")
    server = data["server"]
    port = data.get("port", 1433)
    driver = data.get("driver", "ODBC Driver 17 for SQL Server")
    base = (
        f"DRIVER={{{driver}}};SERVER={server},{port};DATABASE=master;"
        "TrustServerCertificate=yes;"
    )
    if auth == "windows":
        return base + "Trusted_Connection=yes;"
    return base + f"UID={data.get('username', '')};PWD={data.get('password', '')};"


def _connect(data: dict[str, Any]):
    try:
        import pyodbc

        return pyodbc.connect(_connection_string(data), timeout=10)
    except Exception as exc:
        raise DependencyUnavailableError(
            "SQL Server", _safe_error(exc)
        ) from exc


class ConnectionService:
    async def test(self, data: dict[str, Any]) -> dict[str, Any]:
        def operation() -> list[str]:
            with _connect(data) as connection:
                connection.execute("SELECT 1")
                rows = connection.execute(
                    "SELECT name FROM sys.databases "
                    "WHERE database_id > 4 AND state_desc = 'ONLINE' ORDER BY name"
                ).fetchall()
                return [row[0] for row in rows]

        try:
            databases = await asyncio.to_thread(operation)
            return {"connected": True, "databases": databases}
        except DependencyUnavailableError as exc:
            return {
                "connected": False,
                "databases": [],
                "error": exc.message,
            }

    async def databases(self, data: dict[str, Any]) -> dict[str, Any]:
        result = await self.test(data)
        if not result["connected"]:
            raise DomainError(
                "CONNECTION_FAILED", result.get("error", "No se pudo conectar"), 503
            )
        return result
