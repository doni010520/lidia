"""Tool: cadastrar_aniversario — atualiza birth_date do membro no Diacon."""
from __future__ import annotations

from datetime import date

from loguru import logger
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Contact
from app.services import diacon_client


async def execute(args: dict, phone: str, db: AsyncSession) -> str:
    telefone = args.get("telefone") or phone
    data_str = args.get("data")
    if not data_str:
        return "Erro: 'data' é obrigatória (YYYY-MM-DD)."

    try:
        d = date.fromisoformat(str(data_str)[:10])
    except Exception:
        return f"Erro: data '{data_str}' inválida (use YYYY-MM-DD)."

    if not diacon_client.is_enabled():
        return "Erro: integração Diacon não configurada."

    try:
        await diacon_client.member_update(phone=telefone, birth_date=str(d))
    except diacon_client.DiaconError as e:
        logger.warning(f"cadastrar_aniversario: Diacon {e.code} {e}")
        if e.code == "not_found":
            return (
                "Não encontrei seu cadastro ainda. Quer que eu te cadastre primeiro? "
                "Me diz seu nome completo."
            )
        return f"Não consegui salvar o aniversário agora ({e.code or 'erro'}). Tenta de novo."

    try:
        await db.execute(
            update(Contact).where(Contact.telefone == telefone).values(aniversario=d)
        )
        await db.commit()
    except Exception:
        logger.exception("cadastrar_aniversario: write-behind falhou (não crítico)")

    return f"Aniversário registrado: {d.strftime('%d/%m/%Y')}. 🎂"
