"""Tool: excluir_usuario — exclui dados do usuário (LGPD)."""
from __future__ import annotations

from loguru import logger
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Contact, Message


async def execute(
    args: dict,
    phone: str,
    db: AsyncSession,
) -> str:
    """Exclui contato e todas as mensagens associadas.

    A LLM só deve chamar esta tool após confirmação explícita do usuário.
    """
    telefone = args.get("telefone", phone)

    # Verificar se existe
    result = await db.execute(
        select(Contact).where(Contact.telefone == telefone)
    )
    contact = result.scalar_one_or_none()

    if not contact:
        return f"Contato {telefone} não encontrado no sistema."

    nome = contact.full_name or contact.nome or telefone

    # Deletar mensagens primeiro
    del_msgs = await db.execute(
        delete(Message).where(Message.phone == telefone)
    )
    msgs_deleted = del_msgs.rowcount

    # Deletar contato
    await db.execute(
        delete(Contact).where(Contact.telefone == telefone)
    )

    await db.commit()

    logger.bind(phone=telefone).info(
        f"Usuário excluído (LGPD): {nome} — {msgs_deleted} mensagens removidas"
    )
    return (
        f"Dados excluídos com sucesso.\n"
        f"Nome: {nome}\n"
        f"Mensagens removidas: {msgs_deleted}\n"
        f"Contato removido do sistema."
    )
