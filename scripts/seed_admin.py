"""Cria primeiro usuário do painel.

Uso:
    python -m scripts.seed_admin
"""
from __future__ import annotations

import asyncio
import getpass

from sqlalchemy import select

from app.core.config import settings
from app.db import async_session_factory
from app.models.usuarios_painel import UsuarioPainel
from app.services.auth_service import hash_password


async def main() -> None:
    user = settings.painel_default_admin_user or input("Username: ")
    pwd = settings.painel_default_admin_pass or getpass.getpass("Password: ")

    async with async_session_factory() as db:
        existing = await db.scalar(
            select(UsuarioPainel).where(UsuarioPainel.username == user)
        )
        if existing:
            print(f"Usuário '{user}' já existe.")
            return
        db.add(UsuarioPainel(
            username=user,
            senha_hash=hash_password(pwd),
            nome="Admin",
            ativo=True,
        ))
        await db.commit()
        print(f"✅ Usuário '{user}' criado.")


if __name__ == "__main__":
    asyncio.run(main())
