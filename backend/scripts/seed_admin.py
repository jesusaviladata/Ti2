"""Create the Data Express tenant and its first administrator safely."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.client import Tenant
from app.models.user import User, UserRole


def bootstrap_credentials() -> tuple[str, str]:
    email = os.environ.get("BOOTSTRAP_ADMIN_EMAIL", "").strip().lower()
    password = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD", "")
    if not email or not password:
        raise SystemExit(
            "Define BOOTSTRAP_ADMIN_EMAIL y BOOTSTRAP_ADMIN_PASSWORD solo para este comando"
        )
    if len(password) < 14 or password.lower() in {
        "admin1234!",
        "password123456",
    }:
        raise SystemExit(
            "La contrasena inicial debe tener al menos 14 caracteres y no ser conocida"
        )
    return email, password


async def seed() -> None:
    email, password = bootstrap_credentials()
    async with AsyncSessionLocal() as db:
        tenant_result = await db.execute(
            select(Tenant).where(Tenant.slug == "data-express")
        )
        tenant = tenant_result.scalar_one_or_none()
        if tenant is None:
            tenant = Tenant(name="Data Express", slug="data-express")
            db.add(tenant)
            await db.flush()

        user_result = await db.execute(select(User).where(User.email == email))
        if user_result.scalar_one_or_none() is not None:
            print("El administrador de Data Express ya existe. Nada que hacer.")
            return

        db.add(
            User(
                tenant_id=tenant.id,
                email=email,
                username=email.split("@", 1)[0],
                full_name="Administrador Data Express",
                hashed_password=hash_password(password),
                role=UserRole.admin,
            )
        )
        await db.commit()
        print(f"Administrador de Data Express creado: {email}")


if __name__ == "__main__":
    asyncio.run(seed())
