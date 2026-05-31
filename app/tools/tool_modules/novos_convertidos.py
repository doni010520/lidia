"""Tool: novos_convertidos — registra decisão por Cristo."""
from __future__ import annotations

from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def execute(
    args: dict,
    phone: str,
    db: AsyncSession,
) -> str:
    telefone = args.get("telefone", phone)
    nome = args.get("nome", "")

    if not nome:
        return "Erro: 'nome' é obrigatório."

    # INSERT ON CONFLICT DO NOTHING
    await db.execute(
        text("""
            INSERT INTO novos_convertidos (telefone, nome)
            VALUES (:telefone, :nome)
            ON CONFLICT (telefone) DO NOTHING
        """),
        {"telefone": telefone, "nome": nome},
    )
    await db.flush()

    logger.bind(phone=telefone).info(f"Novo convertido registrado: {nome}")
    return f"Decisão por Cristo registrada com sucesso para {nome}. Glória a Deus! 🙏"
