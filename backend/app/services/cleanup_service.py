from __future__ import annotations

import asyncio
import fnmatch
import hashlib
import json
import os
import shutil
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import ConflictError, DomainError
from app.models.operations import (
    CleanupExecution,
    CleanupFolder,
    CleanupRule,
    CleanupSchedule,
    CleanupSimulation,
    CleanupTrashItem,
)
from app.repositories.cleanup_repository import CleanupRepository, tenant_uuid

from cleanup_rules import apply_keep_policy


SIMULATION_TTL_MINUTES = 15


def _is_dangerous_root(path: Path) -> bool:
    resolved = path.resolve(strict=False)
    anchor = Path(resolved.anchor)
    return resolved == anchor or resolved.parent == resolved


def validate_configured_folder(raw_path: str) -> Path:
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        raise DomainError("INVALID_FOLDER", "La carpeta debe ser una ruta absoluta", 422)
    if _is_dangerous_root(path):
        raise DomainError(
            "UNSAFE_FOLDER", "No se permite configurar la raíz de una unidad", 422
        )
    return path.resolve(strict=False)


def _rule_dict(rule: CleanupRule) -> dict:
    return {
        "id": str(rule.id),
        "name": rule.name,
        "folderId": str(rule.folder_id) if rule.folder_id else None,
        "patterns": list(rule.patterns or []),
        "extensions": list(rule.extensions or []),
        "keep": rule.keep_policy,
        "keepN": rule.keep_n,
        "minAgeDays": rule.min_age_days,
        "enabled": rule.enabled,
        "createdAt": rule.created_at.isoformat(),
    }


def _scan_sync(folder: CleanupFolder, rules: list[CleanupRule]) -> list[dict]:
    base = validate_configured_folder(folder.path)
    if not base.exists():
        return []
    if not base.is_dir():
        raise DomainError("INVALID_FOLDER", "La ruta configurada no es una carpeta", 422)

    now = datetime.now(timezone.utc)
    grouped: dict[str, list[dict]] = {str(rule.id): [] for rule in rules}
    rule_by_id = {str(rule.id): rule for rule in rules}
    for file_path in base.rglob("*"):
        try:
            if not file_path.is_file() or file_path.is_symlink():
                continue
            resolved = file_path.resolve(strict=True)
            if base != resolved and base not in resolved.parents:
                continue
            stat = resolved.stat()
        except OSError:
            continue

        for rule in rules:
            patterns = list(rule.patterns or ["*"])
            extensions = [value.lower() for value in (rule.extensions or [])]
            if not any(fnmatch.fnmatch(resolved.name, pattern) for pattern in patterns):
                continue
            if extensions and resolved.suffix.lower() not in extensions:
                continue
            modified = datetime.fromtimestamp(stat.st_mtime, timezone.utc)
            grouped[str(rule.id)].append(
                {
                    "id": str(uuid.uuid4()),
                    "name": resolved.name,
                    "path": str(resolved),
                    "relativePath": str(resolved.relative_to(base)),
                    "sizeBytes": stat.st_size,
                    "modifiedAt": modified.isoformat(),
                    "modifiedNs": stat.st_mtime_ns,
                    "ageDays": (now - modified).total_seconds() / 86400,
                    "ruleId": str(rule.id),
                    "ruleName": rule.name,
                    "folderId": str(folder.id),
                }
            )
            break

    eligible: list[dict] = []
    for rule_id, files in grouped.items():
        eligible.extend(apply_keep_policy(files, _rule_dict(rule_by_id[rule_id])))
    eligible.sort(key=lambda item: (item["path"], item["modifiedAt"]))
    return eligible


def _snapshot_hash(items: list[dict]) -> str:
    canonical = [
        {
            "path": item["path"],
            "sizeBytes": item["sizeBytes"],
            "modifiedNs": item["modifiedNs"],
        }
        for item in sorted(items, key=lambda item: item["path"])
    ]
    return hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _trash_root() -> Path:
    configured = getattr(settings, "CLEANUP_TRASH_PATH", "")
    root = Path(configured or (Path(tempfile.gettempdir()) / "gestor_primee_trash"))
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


class CleanupService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = CleanupRepository(db)

    async def list_folders(self, tenant_id: str) -> list[dict]:
        folders = await self.repo.list_folders(tenant_id)
        return [
            {
                "id": str(folder.id),
                "path": folder.path,
                "label": folder.label,
                "enabled": folder.enabled,
                "exists": Path(folder.path).is_dir(),
                "createdAt": folder.created_at.isoformat(),
            }
            for folder in folders
        ]

    async def create_folder(self, tenant_id: str, path: str, label: str = "") -> dict:
        resolved = validate_configured_folder(path)
        folder = CleanupFolder(
            tenant_id=tenant_uuid(tenant_id),
            path=str(resolved),
            label=label.strip() or resolved.name,
            enabled=True,
        )
        self.db.add(folder)
        await self.db.flush()
        return {
            "id": str(folder.id),
            "path": folder.path,
            "label": folder.label,
            "enabled": folder.enabled,
            "exists": resolved.is_dir(),
            "createdAt": folder.created_at.isoformat(),
        }

    async def delete_folder(self, tenant_id: str, folder_id: str) -> None:
        folder = await self.repo.get_folder(tenant_id, folder_id)
        await self.db.delete(folder)

    async def list_rules(self, tenant_id: str) -> list[dict]:
        return [_rule_dict(rule) for rule in await self.repo.list_rules(tenant_id)]

    async def create_rule(self, tenant_id: str, body: dict) -> dict:
        folder_id = body.get("folderId")
        if folder_id:
            await self.repo.get_folder(tenant_id, folder_id)
        rule = CleanupRule(
            tenant_id=tenant_uuid(tenant_id),
            name=str(body.get("name") or "").strip(),
            folder_id=uuid.UUID(folder_id) if folder_id else None,
            patterns=list(body.get("patterns") or ["*"]),
            extensions=list(body.get("extensions") or []),
            keep_policy=str(body.get("keep") or "latest"),
            keep_n=max(0, int(body.get("keepN", 1))),
            min_age_days=max(0, float(body.get("minAgeDays", 0))),
            enabled=bool(body.get("enabled", True)),
        )
        if not rule.name:
            raise DomainError("INVALID_RULE", "La regla requiere un nombre", 422)
        self.db.add(rule)
        await self.db.flush()
        return _rule_dict(rule)

    async def update_rule(self, tenant_id: str, rule_id: str, body: dict) -> dict:
        rule = await self.repo.get_rule(tenant_id, rule_id)
        if "folderId" in body:
            folder_id = body.get("folderId")
            if folder_id:
                await self.repo.get_folder(tenant_id, folder_id)
            rule.folder_id = uuid.UUID(folder_id) if folder_id else None
        mappings = {
            "name": "name",
            "patterns": "patterns",
            "extensions": "extensions",
            "keep": "keep_policy",
            "keepN": "keep_n",
            "minAgeDays": "min_age_days",
            "enabled": "enabled",
        }
        for source, target in mappings.items():
            if source in body:
                setattr(rule, target, body[source])
        await self.db.flush()
        return _rule_dict(rule)

    async def delete_rule(self, tenant_id: str, rule_id: str) -> None:
        rule = await self.repo.get_rule(tenant_id, rule_id)
        await self.db.delete(rule)

    async def scan(
        self, tenant_id: str, user_id: str, folder_id: str | None
    ) -> dict:
        folders = (
            [await self.repo.get_folder(tenant_id, folder_id)]
            if folder_id
            else [
                folder
                for folder in await self.repo.list_folders(tenant_id)
                if folder.enabled
            ]
        )
        files: list[dict] = []
        for folder in folders:
            rules = await self.repo.get_rules_for_folder(tenant_id, str(folder.id))
            files.extend(await asyncio.to_thread(_scan_sync, folder, rules))
        digest = _snapshot_hash(files)
        simulation = CleanupSimulation(
            tenant_id=tenant_uuid(tenant_id),
            user_id=uuid.UUID(user_id),
            folder_id=uuid.UUID(folder_id) if folder_id else None,
            snapshot=files,
            snapshot_hash=digest,
            expires_at=datetime.now(timezone.utc)
            + timedelta(minutes=SIMULATION_TTL_MINUTES),
        )
        self.db.add(simulation)
        await self.db.flush()
        return {
            "files": files,
            "total": len(files),
            "totalBytes": sum(item["sizeBytes"] for item in files),
            "scannedAt": simulation.created_at.isoformat(),
            "simulationId": str(simulation.id),
            "expiresAt": simulation.expires_at.isoformat(),
        }

    async def execute(
        self,
        tenant_id: str,
        user_id: str,
        file_paths: list[str],
        simulation_id: str | None = None,
    ) -> dict:
        simulation = await self.repo.latest_simulation(
            tenant_id, user_id, simulation_id
        )
        requested = {str(Path(path).resolve(strict=False)) for path in file_paths}
        snapshot = {
            str(Path(item["path"]).resolve(strict=False)): item
            for item in simulation.snapshot
        }
        if not requested or not requested.issubset(snapshot):
            raise ConflictError(
                "Los archivos no pertenecen a la simulación vigente",
                code="SIMULATION_MISMATCH",
            )

        validated: dict[str, os.stat_result] = {}
        for resolved_text in sorted(requested):
            item = snapshot[resolved_text]
            source = Path(resolved_text)
            try:
                stat = source.stat()
            except OSError as exc:
                raise ConflictError(
                    f"El archivo ya no está disponible: {source.name}",
                    code="SIMULATION_STALE",
                ) from exc
            if stat.st_size != item["sizeBytes"] or stat.st_mtime_ns != item["modifiedNs"]:
                raise ConflictError(
                    f"El archivo cambió desde la simulación: {source.name}",
                    code="SIMULATION_STALE",
                )
            validated[resolved_text] = stat

        execution = CleanupExecution(
            tenant_id=tenant_uuid(tenant_id),
            user_id=uuid.UUID(user_id),
            kind="local",
            status="running",
        )
        self.db.add(execution)
        await self.db.flush()

        moved = 0
        bytes_freed = 0
        errors: list[dict] = []
        root = _trash_root() / str(tenant_id) / str(execution.id)
        root.mkdir(parents=True, exist_ok=True)
        for resolved_text in sorted(requested):
            item = snapshot[resolved_text]
            source = Path(resolved_text)
            try:
                stat = validated[resolved_text]
                destination = root / f"{uuid.uuid4().hex}_{source.name}"
                await asyncio.to_thread(shutil.move, str(source), str(destination))
                trash = CleanupTrashItem(
                    tenant_id=tenant_uuid(tenant_id),
                    execution_id=execution.id,
                    rule_id=uuid.UUID(item["ruleId"]) if item.get("ruleId") else None,
                    name=source.name,
                    original_path=str(source),
                    trash_path=str(destination),
                    size_bytes=stat.st_size,
                    deleted_by=uuid.UUID(user_id),
                )
                self.db.add(trash)
                moved += 1
                bytes_freed += stat.st_size
            except ConflictError:
                raise
            except OSError as exc:
                errors.append({"path": str(source), "error": str(exc)[:512]})

        simulation.consumed_at = datetime.now(timezone.utc)
        execution.files_deleted = moved
        execution.bytes_freed = bytes_freed
        execution.errors_count = len(errors)
        execution.status = "completed" if not errors else "partial"
        execution.details = {"errors": errors}
        execution.finished_at = datetime.now(timezone.utc)
        return {"moved": moved, "errors": errors, "bytesFreed": bytes_freed}

    async def list_trash(self, tenant_id: str) -> list[dict]:
        return [
            {
                "id": str(item.id),
                "name": item.name,
                "originalPath": item.original_path,
                "trashPath": item.trash_path,
                "sizeBytes": item.size_bytes,
                "ruleId": str(item.rule_id) if item.rule_id else None,
                "deletedAt": item.created_at.isoformat(),
            }
            for item in await self.repo.list_trash(tenant_id)
        ]

    async def restore(self, tenant_id: str, item_id: str) -> dict:
        item = await self.repo.get_trash(tenant_id, item_id)
        if item.restored_at or item.purged_at:
            raise ConflictError("El elemento ya no está disponible en cuarentena")
        source = Path(item.trash_path)
        destination = Path(item.original_path)
        if destination.exists():
            raise ConflictError("La ruta original ya existe", code="RESTORE_CONFLICT")
        destination.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(shutil.move, str(source), str(destination))
        item.restored_at = datetime.now(timezone.utc)
        return {"restored": str(destination)}

    async def purge(self, tenant_id: str, item_id: str) -> dict:
        item = await self.repo.get_trash(tenant_id, item_id)
        if item.restored_at or item.purged_at:
            raise ConflictError("El elemento ya no está disponible en cuarentena")
        path = Path(item.trash_path)
        if path.exists():
            await asyncio.to_thread(os.remove, path)
        item.purged_at = datetime.now(timezone.utc)
        return {"deleted": str(item.id)}

    async def history(self, tenant_id: str, skip: int, limit: int) -> dict:
        items, total = await self.repo.list_history(tenant_id, skip, limit)
        return {
            "items": [
                {
                    "id": str(item.id),
                    "filesDeleted": item.files_deleted,
                    "bytesFreed": item.bytes_freed,
                    "errors": item.errors_count,
                    "executedAt": item.started_at.isoformat(),
                    "status": item.status,
                }
                for item in items
            ],
            "total": total,
        }

    async def list_schedules(self, tenant_id: str) -> list[dict]:
        return [self._schedule_dict(item) for item in await self.repo.list_schedules(tenant_id)]

    async def create_schedule(self, tenant_id: str, body: dict) -> dict:
        folder = await self.repo.get_folder(tenant_id, body["folderId"])
        rule = await self.repo.get_rule(tenant_id, body["ruleId"])
        schedule = CleanupSchedule(
            tenant_id=tenant_uuid(tenant_id),
            name=str(body["name"]).strip(),
            folder_id=folder.id,
            rule_id=rule.id,
            cron_expression=str(body["cronExpr"]).strip(),
            enabled=bool(body.get("enabled", True)),
        )
        self.db.add(schedule)
        await self.db.flush()
        from app.services.cleanup_scheduler import (
            next_run_for_cron,
            register_cleanup_schedule,
        )

        if schedule.enabled:
            schedule.next_run_at = next_run_for_cron(schedule.cron_expression)
            register_cleanup_schedule(schedule)
        return self._schedule_dict(schedule)

    async def update_schedule(
        self, tenant_id: str, schedule_id: str, body: dict
    ) -> dict:
        schedule = await self.repo.get_schedule(tenant_id, schedule_id)
        if "name" in body:
            schedule.name = str(body["name"]).strip()
        if "cronExpr" in body:
            schedule.cron_expression = str(body["cronExpr"]).strip()
        if "enabled" in body:
            schedule.enabled = bool(body["enabled"])
        from app.services.cleanup_scheduler import (
            next_run_for_cron,
            register_cleanup_schedule,
            remove_cleanup_schedule,
        )

        remove_cleanup_schedule(str(schedule.id))
        if schedule.enabled:
            schedule.next_run_at = next_run_for_cron(schedule.cron_expression)
            register_cleanup_schedule(schedule)
        else:
            schedule.next_run_at = None
        return self._schedule_dict(schedule)

    async def delete_schedule(self, tenant_id: str, schedule_id: str) -> None:
        schedule = await self.repo.get_schedule(tenant_id, schedule_id)
        from app.services.cleanup_scheduler import remove_cleanup_schedule

        remove_cleanup_schedule(str(schedule.id))
        await self.db.delete(schedule)

    @staticmethod
    def _schedule_dict(item: CleanupSchedule) -> dict:
        return {
            "id": str(item.id),
            "name": item.name,
            "folderId": str(item.folder_id),
            "ruleId": str(item.rule_id),
            "cronExpr": item.cron_expression,
            "enabled": item.enabled,
            "lastRun": item.last_run_at.isoformat() if item.last_run_at else None,
            "nextRun": item.next_run_at.isoformat() if item.next_run_at else None,
            "createdAt": item.created_at.isoformat(),
        }
