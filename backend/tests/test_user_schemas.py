import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.v1.users import PasswordChangeBody, deactivate_user, update_user
from app.schemas.user import UserCreate, UserUpdate


def valid_user_payload() -> dict:
    return {
        "email": "persona@example.com",
        "username": "persona.test",
        "password": "Segura-Temporal-2026",
        "full_name": "Persona de Prueba",
        "role": "technician",
    }


def test_user_create_accepts_secure_password():
    user = UserCreate(**valid_user_payload())
    assert user.username == "persona.test"


def test_user_create_rejects_short_password():
    payload = valid_user_payload()
    payload["password"] = "muy-corta"
    with pytest.raises(ValidationError):
        UserCreate(**payload)


def test_password_reset_rejects_short_password():
    with pytest.raises(ValidationError):
        PasswordChangeBody(new_password="muy-corta")


@pytest.mark.asyncio
async def test_admin_cannot_change_own_role():
    user_id = uuid.uuid4()
    current_user = SimpleNamespace(id=user_id)
    with pytest.raises(HTTPException) as error:
        await update_user(
            str(user_id),
            UserUpdate(role="technician"),
            current_user=current_user,
            db=None,
        )
    assert error.value.status_code == 400


@pytest.mark.asyncio
async def test_admin_cannot_deactivate_self():
    user_id = uuid.uuid4()
    current_user = SimpleNamespace(id=user_id)
    with pytest.raises(HTTPException) as error:
        await deactivate_user(str(user_id), current_user=current_user, db=None)
    assert error.value.status_code == 400
