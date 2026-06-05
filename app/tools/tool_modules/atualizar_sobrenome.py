"""Tool: atualizar_sobrenome — atualiza full_name do membro no Diacon."""
from __future__ import annotations

from loguru import logger
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Contact
from app.services import diacon_client


async def execute(args: dict, phone: str, db: AsyncSession) -> str:
    telefone = args.get("telefone") or phone
    nome_completo = (args.get("nome_completo") or "").strip()

    if not nome_completo:
        return "Erro: 'nome_completo' é obrigatório."

    if not diacon_client.is_enabled():
        return "Erro: integração Diacon não configurada."

    try:
        await diacon_client.member_update(phone=telefone, full_name=nome_completo)
    except diacon_client.DiaconError as e:
        logger.warning(f"atualizar_sobrenome: Diacon {e.code} {e}")
        if e.code == "not_found":
            return (
                "Não encontrei seu cadastro ainda. Me passa nome completo, telefone e "
                "status (membro ou visitante) que eu te cadastro."
            )
        return f"Não consegui atualizar agora ({e.code or 'erro'}). Tenta de novo."

    try:
        await db.execute(
            update(Contact)
            .where(Contact.telefone == telefone)
            .values(
                full_name=nome_completo,
                nome=nome_completo.split()[0] if nome_completo else None,
            )
        )
        await db.commit()
    except Exception:
        logger.exception("atualizar_sobrenome: write-behind falhou (não crítico)")

    return f"Nome atualizado para: {nome_completo}."
