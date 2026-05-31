"""Tool: cadastrar_aniversario — registra data de aniversário pessoal."""
from __future__ import annotations

from datetime import date

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
    data_str = args.get("data", "")

    if not data_str:
        return "Erro: 'data' é obrigatório (formato YYYY-MM-DD)."

    try:
        aniversario = date.fromisoformat(data_str)
    except ValueError:
        return f"Erro: formato de data inválido '{data_str}'. Use YYYY-MM-DD."

    result = await db.execute(
        select(Contact).where(Contact.telefone == telefone)
    )
    contact = result.scalar_one_or_none()

    if not contact:
        return f"Contato {telefone} não encontrado no sistema."

    contact.aniversario = aniversario
    await db.flush()

    logger.bind(phone=telefone).info(f"Aniversário atualizado: {aniversario}")
    return f"Aniversário registrado: {aniversario.strftime('%d/%m/%Y')}."
