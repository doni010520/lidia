"""Tool: atualizar_sobrenome — atualiza nome completo do contato."""
from __future__ import annotations

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Contact


async def execute(
    args: dict,
    phone: str,
    db: AsyncSession,
) -> str:
    telefone = args.get("telefone", phone)
    nome_completo = args.get("nome_completo", "")

    if not nome_completo:
        return "Erro: 'nome_completo' é obrigatório."

    result = await db.execute(
        select(Contact).where(Contact.telefone == telefone)
    )
    contact = result.scalar_one_or_none()

    if not contact:
        return f"Contato {telefone} não encontrado no sistema."

    old_name = contact.full_name or contact.nome or "(sem nome)"
    contact.full_name = nome_completo
    # Atualizar nome curto também (primeiro nome)
    contact.nome = nome_completo.split()[0] if nome_completo else contact.nome
    await db.flush()

    logger.bind(phone=telefone).info(f"Nome atualizado: {old_name} → {nome_completo}")
    return f"Nome atualizado para: {nome_completo}."
