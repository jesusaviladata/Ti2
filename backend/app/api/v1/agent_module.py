"""Activacion del modulo de agentes desde el panel.

Estas rutas funcionan aunque el modulo este apagado: son las que permiten encenderlo.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.capabilities import Capability, has_capabilities, require_capabilities
from app.core.database import get_db
from app.models.user import User
from app.services import agent_module


router = APIRouter()
read_status = require_capabilities(Capability.OPERATION_READ)
manage_config = require_capabilities(Capability.CONFIG_MANAGE)


class AgentModuleUpdate(BaseModel):
    enabled: bool

    model_config = {"extra": "forbid"}


def _view(user: User) -> dict:
    return agent_module.public_view(
        agent_module.current(),
        can_manage=has_capabilities(user.role, Capability.CONFIG_MANAGE),
    )


@router.get("")
async def get_agent_module(current_user: User = Depends(read_status)):
    return _view(current_user)


@router.put("")
async def update_agent_module(
    body: AgentModuleUpdate,
    current_user: User = Depends(manage_config),
    db: AsyncSession = Depends(get_db),
):
    await agent_module.set_enabled(db, enabled=body.enabled, actor_id=current_user.id)
    return _view(current_user)


@router.get("/bootstrap")
async def download_bootstrap(current_user: User = Depends(manage_config)):
    document = agent_module.bootstrap_document(agent_module.current())
    return Response(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n",
        media_type="application/json",
        headers={
            "Content-Disposition": 'attachment; filename="bootstrap.json"',
            "Cache-Control": "no-store",
        },
    )
